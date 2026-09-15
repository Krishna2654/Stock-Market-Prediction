import logging
import time
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd

from app.models.schemas import Candle
from app.core.config import settings
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
    In-memory precomputed chart buffer populated by MarketProcessingWorker.
    Keyed by (symbol.upper(), timeframe.upper()).
    Stores the full ChartView response payload.
    """
    def __init__(self):
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def set(
        self,
        symbol: str,
        timeframe: str,
        payload: Dict[str, Any],
        latest_candle_timestamp: Optional[str] = None
    ) -> None:
        key = (symbol.upper(), timeframe.upper())
        existing = self._cache.get(key)

        # Check monotonic candle timestamp to prevent stale overwrites
        if existing and latest_candle_timestamp and existing.get("latest_candle_timestamp"):
            if latest_candle_timestamp < existing["latest_candle_timestamp"]:
                logger.debug(
                    f"[WorkerChartCache] Ignoring older payload for {key}: "
                    f"{latest_candle_timestamp} < {existing['latest_candle_timestamp']}"
                )
                return

        self._cache[key] = {
            "payload": payload,
            "latest_candle_timestamp": latest_candle_timestamp,
            "cached_at": time.time(),
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper()
        }

    def get(
        self,
        symbol: str,
        timeframe: str,
        max_age_seconds: Optional[float] = 120.0
    ) -> Optional[Dict[str, Any]]:
        key = (symbol.upper(), timeframe.upper())
        entry = self._cache.get(key)
        if not entry:
            return None

        if max_age_seconds is not None:
            age = time.time() - entry.get("cached_at", 0)
            if age > max_age_seconds:
                return None

        return entry.get("payload")

    def get_entry(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        return self._cache.get((symbol.upper(), timeframe.upper()))

    def clear(self) -> None:
        self._cache.clear()

    def count(self) -> int:
        return len(self._cache)


worker_chart_cache = WorkerChartCache()
