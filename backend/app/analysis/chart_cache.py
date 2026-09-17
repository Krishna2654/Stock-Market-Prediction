import os
import json
from pathlib import Path
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import pandas as pd

from app.models.schemas import Candle
from app.core.config import settings
from app.core.timezone import is_candle_closed
from app.indicators.technical import TechnicalIndicatorEngine
from app.market_structure.swings import SwingDetector
from app.market_structure.bos_choch import BOSCHoCHDetector
from app.market_structure.trendlines import TrendlineDetector
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.market_structure.support_resistance import SupportResistanceDetector
from app.market_structure.predictive_scenarios import PredictiveScenarioEngine
from app.alerts.mw_breakout_engine import mw_breakout_engine

logger = logging.getLogger(__name__)


def build_chart_payload(
    symbol: str,
    ticker: str,
    timeframe: str,
    candles: List[Candle]
) -> Dict[str, Any]:
    """
    Builds the complete, canonical ChartView response payload from a list of candles.
    Ensures 100% parity between on-demand requests and worker precomputation.
    """
    if not candles:
        return {}

    df_indicators, _ = TechnicalIndicatorEngine.compute_all_indicators(candles)
    tf_clean = (timeframe or "15M").upper()
    eff_swing_length = 3 if tf_clean in ["5M", "1M", "3M"] else 5
    swings, protected_swing = SwingDetector.detect_swings(candles, swing_length=eff_swing_length, confirmation_candles=2)
    breaks = BOSCHoCHDetector.detect_structure_breaks(
        candles=candles,
        swings=swings,
        symbol=symbol,
        timeframe=timeframe,
        df_indicators=df_indicators
    )
    trendlines = TrendlineDetector.fit_trendlines(candles, swings, max_lines_per_direction=settings.MAX_TRENDLINES_PER_DIRECTION)
    atr_val = (
        float(df_indicators["atr_14"].iloc[-1])
        if "atr_14" in df_indicators and not pd.isna(df_indicators["atr_14"].iloc[-1])
        else (candles[-1].close * 0.005)
    )

    # Standard trendline breaks
    tl_breaks = TrendlineDetector.detect_trendline_breaks(candles, trendlines, symbol, timeframe, atr_val=atr_val)
    for tb in tl_breaks:
        breaks.append(tb)

    # Precision Breakouts (Notification 1 & 2)
    tl_ema_vol_breaks = PrecisionBreakoutDetector.detect_trendline_ema_volume_breakouts(
        candles=candles,
        trendlines=trendlines,
        df_indicators=df_indicators,
        symbol=symbol,
        timeframe=timeframe,
        atr_val=atr_val,
        good_volume_threshold=settings.GOOD_VOLUME_THRESHOLD
    )
    for pb in tl_ema_vol_breaks:
        breaks.append(pb)

    sr_summary = SupportResistanceDetector.detect_levels(candles, swings, timeframe)
    key_sups = [lvl.price for lvl in sr_summary.all_levels if lvl.level_type == "SUPPORT"]
    key_res = [lvl.price for lvl in sr_summary.all_levels if lvl.level_type == "RESISTANCE"]

    wm_breaks, confirmed_wm_patterns, active_wm_pattern, debug_wm_candidates = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles,
        swings=swings,
        trendlines=trendlines,
        df_indicators=df_indicators,
        symbol=symbol,
        timeframe=timeframe,
        atr_val=atr_val,
        price_tolerance_atr=settings.W_M_SWING_TOLERANCE_ATR,
        min_depth_atr=settings.MIN_PATTERN_DEPTH_ATR,
        min_bar_spacing=settings.MIN_W_M_SWING_SEPARATION,
        key_supports=key_sups,
        key_resistances=key_res
    )
    for wb in wm_breaks:
        breaks.append(wb)

    # Single Source of Truth: Synchronize canonical chart patterns with mw_breakout_engine
    canonical_active_alert = mw_breakout_engine.sync_chart_patterns(
        symbol=symbol,
        timeframe=timeframe,
        confirmed_patterns=confirmed_wm_patterns,
        active_pattern=active_wm_pattern,
        candles=candles,
        ticker=ticker
    )

    predictive_scenarios = PredictiveScenarioEngine.compute_scenarios(
        candles=candles,
        swings=swings,
        sr_summary=sr_summary,
        recent_events=breaks,
        timeframe=timeframe,
        symbol=symbol
    )

    chart_candles = []
    for i, c in enumerate(candles):
        row = df_indicators.iloc[i] if i < len(df_indicators) else None
        item = {
            "time": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "rsi_14": float(row["rsi_14"]) if row is not None and "rsi_14" in row and not pd.isna(row["rsi_14"]) else None,
            "ema_20": float(row["ema_20"]) if row is not None and "ema_20" in row and not pd.isna(row["ema_20"]) else None,
            "ema_50": float(row["ema_50"]) if row is not None and "ema_50" in row and not pd.isna(row["ema_50"]) else None,
            "ema_200": float(row["ema_200"]) if row is not None and "ema_200" in row and not pd.isna(row["ema_200"]) else None,
            "atr_14": float(row["atr_14"]) if row is not None and "atr_14" in row and not pd.isna(row["atr_14"]) else None
        }
        chart_candles.append(item)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": chart_candles,
        "swings": [s.model_dump() for s in swings],
        "protected_swing": protected_swing.model_dump() if protected_swing else None,
        "structure_breaks": [b.model_dump() for b in breaks],
        "breaks": [b.model_dump() for b in breaks],
        "trendlines": trendlines,
        "support_resistance": sr_summary.model_dump(),
        "predictive_scenarios": predictive_scenarios,
        "wm_patterns": [p.model_dump() for p in confirmed_wm_patterns],
        "active_wm_pattern": active_wm_pattern.model_dump() if active_wm_pattern else None,
        "active_wm_alert": canonical_active_alert.model_dump() if canonical_active_alert else None,
        "wm_debug_candidates": [c.model_dump() for c in debug_wm_candidates]
    }


class WorkerChartCache:
    """
    In-memory precomputed chart buffer populated authoritatively by MarketProcessingWorker.
    Keyed strictly by (symbol.upper(), timeframe.upper()).
    Stores the full ChartView response payload.

    Validity Contract (Candle-State-Driven, Non-Wall-Clock):
    VALID when:
    1. (symbol, timeframe) matches
    2. payload contains only completed candles
    3. latest_candle_timestamp is valid
    4. there is no newer completed candle known to the worker
    5. payload generation is valid

    INVALID only when:
    - wrong symbol/timeframe
    - malformed cache
    - future/uncompleted candle
    - newer completed candle is available
    - worker explicitly marks the entry invalid
    """
    _CACHE_FILE = Path(__file__).resolve().parents[2] / "data" / "market_chart_cache.json"

    def __init__(self):
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._latest_known_completed: Dict[Tuple[str, str], str] = {}
        self._load_disk_cache()

    def _load_disk_cache(self) -> None:
        """
        Gracefully restores precomputed chart cache from disk.
        Safely handles missing or corrupted cache files.
        """
        if not self._CACHE_FILE.exists():
            return
        try:
            with open(self._CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            for key_str, entry in data.items():
                if not isinstance(entry, dict):
                    continue
                parts = key_str.split("__")
                if len(parts) != 2:
                    continue
                sym, tf = parts[0].upper(), parts[1].upper()
                key = (sym, tf)
                payload = entry.get("payload")
                latest_ts = entry.get("latest_candle_timestamp")
                if isinstance(payload, dict) and isinstance(latest_ts, str) and payload.get("candles"):
                    self._cache[key] = {
                        "payload": payload,
                        "latest_candle_timestamp": latest_ts,
                        "cached_at": entry.get("cached_at", time.time()),
                        "symbol": sym,
                        "timeframe": tf,
                        "is_valid": True,
                        "producer": entry.get("producer", "worker")
                    }
                    self._latest_known_completed[key] = latest_ts
            logger.info(f"[WorkerChartCache] Restored {len(self._cache)} precomputed chart payloads from disk.")
        except Exception as e:
            logger.warning(f"[WorkerChartCache] Disk cache load error (gracefully starting fresh): {e}")

    def _save_disk_cache(self) -> None:
        """
        Safely and atomically persists precomputed chart cache to disk.
        Uses temporary file + atomic rename to prevent corruption.
        """
        try:
            self._CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            dump_data = {}
            for (sym, tf), entry in self._cache.items():
                key_str = f"{sym}__{tf}"
                dump_data[key_str] = {
                    "payload": entry.get("payload"),
                    "latest_candle_timestamp": entry.get("latest_candle_timestamp"),
                    "cached_at": entry.get("cached_at", time.time()),
                    "symbol": sym,
                    "timeframe": tf,
                    "producer": entry.get("producer", "worker")
                }
            tmp_file = self._CACHE_FILE.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(dump_data, f)
            os.replace(tmp_file, self._CACHE_FILE)
        except Exception as e:
            logger.warning(f"[WorkerChartCache] Disk cache save warning: {e}")

    def record_known_completed_candle(self, symbol: str, timeframe: str, timestamp: str) -> None:
        """
        Authoritatively records the latest completed candle observed by the worker for (symbol, timeframe).
        This serves as the freshness authority: a cached entry remains valid until this timestamp advances.
        """
        if not symbol or not timeframe or not timestamp:
            return
        key = (symbol.upper(), timeframe.upper())
        current = self._latest_known_completed.get(key)
        if not current or timestamp > current:
            self._latest_known_completed[key] = timestamp

    def get_latest_known_completed_candle(self, symbol: str, timeframe: str) -> Optional[str]:
        return self._latest_known_completed.get((symbol.upper(), timeframe.upper()))

    def mark_invalid(self, symbol: str, timeframe: str, reason: str = "") -> None:
        """
        Explicitly marks the cache entry for (symbol, timeframe) as invalid.
        """
        key = (symbol.upper(), timeframe.upper())
        if key in self._cache:
            self._cache[key]["is_valid"] = False
            self._cache[key]["invalidation_reason"] = reason

    def invalidate(self, symbol: str, timeframe: str) -> None:
        """
        Explicitly invalidates and evicts the entry for (symbol, timeframe).
        """
        self.mark_invalid(symbol, timeframe, reason="explicit_invalidation")

    def is_entry_valid(
        self,
        symbol: str,
        timeframe: str,
        now: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Evaluates the validity of the cached entry against strict candle-state rules.
        Does NOT use wall-clock age as the invalidation authority.
        """
        key = (symbol.upper(), timeframe.upper())
        entry = self._cache.get(key)
        if not entry:
            return False, "CACHE_MISS_NO_ENTRY"

        # 1. (symbol, timeframe) match
        if entry.get("symbol") != symbol.upper() or entry.get("timeframe") != timeframe.upper():
            return False, "SYMBOL_TIMEFRAME_MISMATCH"

        # 2. Worker explicit invalidation check
        if not entry.get("is_valid", True):
            reason = entry.get("invalidation_reason", "MARKED_INVALID_BY_WORKER")
            return False, f"WORKER_EXPLICITLY_MARKED_INVALID: {reason}"

        # 3. Malformed cache check (payload structure)
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            return False, "MALFORMED_CACHE_PAYLOAD_NOT_DICT"

        candles = payload.get("candles")
        if not isinstance(candles, list) or len(candles) == 0:
            return False, "MALFORMED_CACHE_NO_CANDLES"

        # 4. latest_candle_timestamp is valid
        latest_ts = entry.get("latest_candle_timestamp")
        if not latest_ts or not isinstance(latest_ts, str):
            return False, "INVALID_LATEST_CANDLE_TIMESTAMP"

        # 5. Future / uncompleted candle check
        # Verify that the latest candle has actually reached its timeframe close boundary
        if not is_candle_closed(latest_ts, timeframe, now=now):
            return False, f"FUTURE_OR_UNCOMPLETED_CANDLE: {latest_ts}"

        # 6. Newer completed candle check
        # The authoritative freshness signal is the latest COMPLETED candle known to the worker
        known_latest = self._latest_known_completed.get(key)
        if known_latest and known_latest > latest_ts:
            return False, f"NEWER_COMPLETED_CANDLE_AVAILABLE: {known_latest} > {latest_ts}"

        return True, "VALID"

    def set(
        self,
        symbol: str,
        timeframe: str,
        payload: Dict[str, Any],
        latest_candle_timestamp: Optional[str] = None,
        is_worker_producer: bool = True
    ) -> bool:
        """
        Sets a precomputed chart payload into the cache.
        Enforces:
        - Symbol/timeframe isolation
        - Malformed payload rejection
        - Future/uncompleted candle rejection
        - Monotonic timestamp protection (cannot overwrite with older timestamp)
        - Fallback cannot overwrite equal or newer worker-produced payload
        """
        if not symbol or not timeframe:
            return False

        key = (symbol.upper(), timeframe.upper())

        # Malformed payload check
        if not isinstance(payload, dict):
            logger.debug(f"[WorkerChartCache] Rejecting non-dict payload for {key}")
            return False

        candles = payload.get("candles")
        if not isinstance(candles, list) or len(candles) == 0:
            logger.debug(f"[WorkerChartCache] Rejecting payload with empty candles for {key}")
            return False

        # Extract latest candle timestamp if not provided
        if not latest_candle_timestamp:
            last_candle = candles[-1]
            if isinstance(last_candle, dict):
                latest_candle_timestamp = last_candle.get("time")
            elif hasattr(last_candle, "timestamp"):
                latest_candle_timestamp = getattr(last_candle, "timestamp")

        if not latest_candle_timestamp or not isinstance(latest_candle_timestamp, str):
            logger.debug(f"[WorkerChartCache] Rejecting payload without valid latest candle timestamp for {key}")
            return False

        # Future / uncompleted candle rejection
        if not is_candle_closed(latest_candle_timestamp, timeframe):
            logger.debug(f"[WorkerChartCache] Rejecting uncompleted/future candle {latest_candle_timestamp} for {key}")
            return False

        existing = self._cache.get(key)
        if existing and existing.get("latest_candle_timestamp"):
            existing_ts = existing["latest_candle_timestamp"]
            # Monotonic protection: cannot overwrite with older timestamp
            if latest_candle_timestamp < existing_ts:
                logger.debug(
                    f"[WorkerChartCache] Rejecting older timestamp overwrite for {key}: "
                    f"{latest_candle_timestamp} < {existing_ts}"
                )
                return False

            # Producer authority: Fallback cannot overwrite equal or newer worker payload
            if not is_worker_producer and existing.get("producer") == "worker":
                if latest_candle_timestamp <= existing_ts:
                    logger.debug(f"[WorkerChartCache] Fallback request will not overwrite worker-produced payload for {key}")
                    return False

        # If worker is producer, authoritatively record latest known completed candle
        if is_worker_producer:
            self.record_known_completed_candle(symbol, timeframe, latest_candle_timestamp)

        self._cache[key] = {
            "payload": payload,
            "latest_candle_timestamp": latest_candle_timestamp,
            "cached_at": time.time(),
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "is_valid": True,
            "producer": "worker" if is_worker_producer else "fallback"
        }
        self._save_disk_cache()
        return True

    def get_stale_or_valid(
        self,
        symbol: str,
        timeframe: str
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Retrieves precomputed chart payload:
        - If strictly valid under candle-state rules, returns (payload, False).
        - If expired/stale under candle-state rules but a non-empty payload exists in cache,
          returns (payload, True) enabling instant Stale-While-Revalidate response.
        - If no entry exists, returns (None, False).
        """
        is_valid, _ = self.is_entry_valid(symbol, timeframe)
        key = (symbol.upper(), timeframe.upper())
        entry = self._cache.get(key)
        if not entry:
            return None, False

        payload = entry.get("payload")
        if not isinstance(payload, dict) or not payload.get("candles"):
            return None, False

        return payload, (not is_valid)

    def get(
        self,
        symbol: str,
        timeframe: str,
        max_age_seconds: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves precomputed chart payload if VALID under candle-state rules.
        Does NOT invalidate based on wall-clock time.
        """
        is_valid, reason = self.is_entry_valid(symbol, timeframe)
        if not is_valid:
            logger.debug(f"[WorkerChartCache] Miss for ({symbol}, {timeframe}): {reason}")
            return None

        entry = self._cache.get((symbol.upper(), timeframe.upper()))
        return entry.get("payload") if entry else None

    def get_entry(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        return self._cache.get((symbol.upper(), timeframe.upper()))

    def clear(self) -> None:
        self._cache.clear()
        self._latest_known_completed.clear()

    def count(self) -> int:
        return len(self._cache)


worker_chart_cache = WorkerChartCache()
