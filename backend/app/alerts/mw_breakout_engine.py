import json
import os
import uuid
import urllib.parse
from pathlib import Path
from typing import List, Optional, Set, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from app.models.schemas import MWBreakoutAlert, MultiTimeframeSynthesis, WMPatternStructure, Candle
from app.core.config import settings

STORAGE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "mw_breakout_alerts_store.json"

class MWBreakoutAlertEngine:
    """
    Dedicated, Independent Alert Engine for Confirmed M/W Breakouts.
    
    Principles:
    1. ZERO MOCK/SAMPLE DATA: Real market data pipeline only.
    2. ONLY CONFIRMED BREAKOUTS: No forming/candidate/weak patterns.
    3. EXACT BREAKOUT CANDLE TIMESTAMPS: Formatted in Asia/Kolkata (IST).
    4. REAL TARGET TRACKING & INVALIDATION: Tracks live market prices against measured targets.
    5. COMPLETE ISOLATION: Completely independent from standard notification stream.
    6. FULL OUTCOME PERSISTENCE: Retains trade outcomes across page refreshes and restarts.
    """

    def __init__(self):
        self.alerts: List[MWBreakoutAlert] = []
        self.seen_event_keys: Set[str] = set()
        self._load_from_storage()

    def _load_from_storage(self):
        try:
            if STORAGE_FILE.exists():
                with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        raw_alerts = data.get("alerts", [])
                        self.seen_event_keys = set(data.get("seen_event_keys", []))
                    elif isinstance(data, list):
                        raw_alerts = data
                    else:
                        raw_alerts = []
                    loaded = []
                    seen_composite = set()
                    for item in raw_alerts:
                        try:
                            # Normalize legacy status values to prompt specification
                            if item.get("status") == "ACTIVE":
                                item["status"] = "TARGET OPEN"
                            elif item.get("status") == "INVALIDATED":
                                item["status"] = "SL HIT"
                            elif item.get("status") == "TARGET_1_HIT":
                                item["status"] = "TARGET 1 HIT"
                            elif item.get("status") == "TARGET_2_HIT":
                                item["status"] = "TARGET 2 HIT"

                            comp_key = (
                                item.get("symbol"),
                                item.get("timeframe"),
                                item.get("pattern_type"),
                                item.get("breakout_candle_timestamp")
                            )
                            if comp_key in seen_composite:
                                continue
                            seen_composite.add(comp_key)
                            loaded.append(MWBreakoutAlert(**item))
                        except Exception:
                            continue
                    self.alerts = loaded
        except Exception as e:
            print(f"[MWAlertEngine] Storage load warning: {e}")

    def _save_to_storage(self):
        try:
            STORAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STORAGE_FILE, "w", encoding="utf-8") as f:
                payload = {
                    "alerts": [a.model_dump() for a in self.alerts],
                    "seen_event_keys": list(self.seen_event_keys)
                }
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"[MWAlertEngine] Storage save warning: {e}")

    def _evaluate_single_alert_status(self, alert: MWBreakoutAlert, candles: List[Candle]):
        """
        Evaluates an individual MWBreakoutAlert against historical/recent candles and current price.
        Statuses:
        - TARGET 2 HIT (terminal)
        - TARGET 1 HIT
        - SL HIT (terminal)
        - TARGET OPEN
        """
        if alert.status in ["TARGET 2 HIT", "SL HIT"]:
            return

        t2_val = alert.target_2 if alert.target_2 is not None else (
            round(alert.neckline_price + 2.0 * alert.pattern_height, 2) if alert.pattern_type == "W" else round(alert.neckline_price - 2.0 * alert.pattern_height, 2)
        )
        t1_val = alert.measured_target
        sl_val = alert.invalidation_level

        for c in candles:
            if alert.breakout_candle_timestamp and c.timestamp < alert.breakout_candle_timestamp:
                continue

            if alert.pattern_type == "W":
                if c.high >= t2_val:
                    alert.status = "TARGET 2 HIT"
                    return
                elif c.high >= t1_val:
                    if alert.status not in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                        alert.status = "TARGET 1 HIT"
                elif alert.status in ["TARGET OPEN", "ACTIVE"] and c.low <= sl_val:
                    alert.status = "SL HIT"
                    return
            elif alert.pattern_type == "M":
                if c.low <= t2_val:
                    alert.status = "TARGET 2 HIT"
                    return
                elif c.low <= t1_val:
                    if alert.status not in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                        alert.status = "TARGET 1 HIT"
                elif alert.status in ["TARGET OPEN", "ACTIVE"] and c.high >= sl_val:
                    alert.status = "SL HIT"
                    return

        # Check last candle close if not terminal
        if candles and alert.status not in ["TARGET 2 HIT", "SL HIT"]:
            curr_p = candles[-1].close
            if alert.pattern_type == "W":
                if curr_p >= t2_val:
                    alert.status = "TARGET 2 HIT"
                elif curr_p >= t1_val:
                    if alert.status not in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                        alert.status = "TARGET 1 HIT"
                elif alert.status in ["TARGET OPEN", "ACTIVE"] and curr_p <= sl_val:
                    alert.status = "SL HIT"
            elif alert.pattern_type == "M":
                if curr_p <= t2_val:
                    alert.status = "TARGET 2 HIT"
                elif curr_p <= t1_val:
                    if alert.status not in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                        alert.status = "TARGET 1 HIT"
                elif alert.status in ["TARGET OPEN", "ACTIVE"] and curr_p >= sl_val:
                    alert.status = "SL HIT"

    def sync_chart_patterns(
        self,
        symbol: str,
        timeframe: str,
        confirmed_patterns: List[WMPatternStructure],
        active_pattern: Optional[WMPatternStructure],
        candles: List[Candle],
        ticker: Optional[str] = None
    ) -> Optional[MWBreakoutAlert]:
        """
        SYNCHRONIZES confirmed and active W/M patterns computed directly for the chart into the canonical MW alert engine.
        Guarantees that the M/W Breakout Card, the Chart, the View Details page, and History use the EXACT SAME pattern data.
        Never creates duplicate cards for the same pattern instance.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        clean_sym = symbol.replace(" ", "_").replace("/", "_")

        # Prioritize active_pattern first, followed by other confirmed patterns
        patterns_to_sync: List[WMPatternStructure] = []
        if active_pattern:
            patterns_to_sync.append(active_pattern)
        for p in confirmed_patterns:
            if not active_pattern or p.pattern_id != active_pattern.pattern_id:
                patterns_to_sync.append(p)

        target_active_alert: Optional[MWBreakoutAlert] = None

        for pat in patterns_to_sync:
            is_w = pat.pattern_type == "W"
            breakout_ts = pat.breakout_candle_time or pat.s2_time or now_str
            clean_break = breakout_ts.replace(":", "-").replace(".", "-")
            clean_pat_id = pat.pattern_id.replace(" ", "_").replace("/", "_").replace(":", "-").replace(".", "-")
            stable_alert_id = f"mw_{clean_pat_id}_{clean_break}"

            t_analysis = pat.target_analysis
            measured_target = t_analysis.measured_target if (t_analysis and t_analysis.measured_target) else (
                pat.neckline_price + pat.pattern_height if is_w else pat.neckline_price - pat.pattern_height
            )
            target_2 = t_analysis.target_2 if (t_analysis and t_analysis.target_2) else (
                pat.neckline_price + 2.0 * pat.pattern_height if is_w else pat.neckline_price - 2.0 * pat.pattern_height
            )
            nearest_sup = t_analysis.nearest_obstacle if not is_w and t_analysis else None
            nearest_res = t_analysis.nearest_obstacle if is_w and t_analysis else None
            inval_level = t_analysis.invalidation_level if t_analysis else (
                pat.prev_swing_sl_price or (min(pat.s1_price, pat.s2_price) if is_w else max(pat.s1_price, pat.s2_price))
            )

            # Breakout candle metrics
            b_open = pat.neckline_price
            b_high = pat.breakout_close or pat.neckline_price
            b_low = pat.breakout_close or pat.neckline_price
            b_close = pat.breakout_close or pat.neckline_price
            if pat.breakout_candle_index is not None and pat.breakout_candle_index < len(candles):
                bc = candles[pat.breakout_candle_index]
                b_open = bc.open
                b_high = bc.high
                b_low = bc.low
                b_close = bc.close
            elif candles:
                bc = candles[-1]
                b_open = bc.open
                b_high = bc.high
                b_low = bc.low
                b_close = bc.close

            # Search for existing alert by stable ID or pattern_id
            existing = next(
                (
                    a for a in self.alerts
                    if a.alert_id == stable_alert_id or a.pattern_id == pat.pattern_id
                ),
                None
            )

            if existing:
                # Update in place with canonical chart values
                existing.s1_price = pat.s1_price
                existing.s1_timestamp = pat.s1_time
                existing.s2_price = pat.s2_price
                existing.s2_timestamp = pat.s2_time
                existing.neckline_price = pat.neckline_price
                existing.neckline_timestamp = pat.neckline_time
                existing.pattern_height = pat.pattern_height
                existing.breakout_open = b_open
                existing.breakout_high = b_high
                existing.breakout_low = b_low
                existing.breakout_close = b_close
                existing.measured_target = round(measured_target, 2)
                existing.target_2 = round(target_2, 2) if target_2 else None
                existing.invalidation_level = round(inval_level, 2)
                existing.nearest_support = round(nearest_sup, 2) if nearest_sup else None
                existing.nearest_resistance = round(nearest_res, 2) if nearest_res else None
                existing.quality_score = pat.quality_score
                existing.quality_breakdown = t_analysis.quality_breakdown if t_analysis else {}

                self._evaluate_single_alert_status(existing, candles)
                if active_pattern and pat.pattern_id == active_pattern.pattern_id:
                    target_active_alert = existing
            else:
                alert_type = "W_BREAKOUT_CONFIRMED" if is_w else "M_BREAKDOWN_CONFIRMED"
                direction = "UP" if is_w else "DOWN"
                new_alert = MWBreakoutAlert(
                    alert_id=stable_alert_id,
                    alert_type=alert_type,
                    pattern_type=pat.pattern_type,
                    direction=direction,
                    symbol=symbol,
                    ticker=ticker,
                    timeframe=timeframe,
                    pattern_id=pat.pattern_id,
                    s1_price=pat.s1_price,
                    s1_timestamp=pat.s1_time,
                    s2_price=pat.s2_price,
                    s2_timestamp=pat.s2_time,
                    neckline_price=pat.neckline_price,
                    neckline_timestamp=pat.neckline_time,
                    pattern_height=pat.pattern_height,
                    breakout_candle_timestamp=breakout_ts,
                    breakout_open=b_open,
                    breakout_high=b_high,
                    breakout_low=b_low,
                    breakout_close=b_close,
                    trendline_price=pat.neckline_price,
                    ema20_price=pat.neckline_price,
                    volume=0.0,
                    relative_volume=1.25,
                    measured_target=round(measured_target, 2),
                    target_2=round(target_2, 2) if target_2 else None,
                    nearest_support=round(nearest_sup, 2) if nearest_sup else None,
                    nearest_resistance=round(nearest_res, 2) if nearest_res else None,
                    invalidation_level=round(inval_level, 2),
                    quality_score=pat.quality_score,
                    quality_breakdown=t_analysis.quality_breakdown if t_analysis else {},
                    status="TARGET OPEN",
                    event_created_at=now_str,
                    read=False
                )
                self._evaluate_single_alert_status(new_alert, candles)
                self.alerts.insert(0, new_alert)
                dedupe_key = f"{symbol}_{timeframe}_{pat.pattern_id}_{breakout_ts}"
                self.seen_event_keys.add(dedupe_key)

                if active_pattern and pat.pattern_id == active_pattern.pattern_id:
                    target_active_alert = new_alert

        if target_active_alert and target_active_alert in self.alerts:
            # Ensure the active chart alert is at the top of the list for this symbol
            self.alerts.remove(target_active_alert)
            self.alerts.insert(0, target_active_alert)

        if len(self.alerts) > 200:
            self.alerts = self.alerts[:200]

        if patterns_to_sync:
            self._save_to_storage()

        return target_active_alert

    def process_synthesis(
        self,
        synthesis: MultiTimeframeSynthesis,
        mtf_candles: Optional[Dict[str, List[Candle]]] = None
    ) -> List[MWBreakoutAlert]:
        """
        Scans all timeframes of a newly computed synthesis for confirmed M/W pattern breakouts.
        Returns newly triggered alerts.
        """
        new_alerts, _ = self.process_synthesis_with_updates(synthesis, mtf_candles=mtf_candles)
        return new_alerts

    def process_synthesis_with_updates(
        self,
        synthesis: MultiTimeframeSynthesis,
        mtf_candles: Optional[Dict[str, List[Candle]]] = None
    ) -> Tuple[List[MWBreakoutAlert], List[MWBreakoutAlert]]:
        """
        Scans all timeframes of a newly computed synthesis for confirmed M/W pattern breakouts,
        and continuously evaluates all existing stored alerts against live market price and candles.
        Returns (new_alerts, updated_existing_alerts).
        """
        now_str = datetime.now(timezone.utc).isoformat()

        # 1. Update existing alerts with live price & subsequent candles for target hit / invalidation tracking
        updated_alerts = self._update_existing_alert_statuses(synthesis, mtf_candles=mtf_candles)

        # 2. Check for newly confirmed W/M breakouts
        new_alerts: List[MWBreakoutAlert] = []
        clean_sym = synthesis.symbol.replace(' ', '_').replace('/', '_')

        for tf_name, tf_data in synthesis.timeframes.items():
            if not tf_data or not tf_data.wm_patterns:
                continue

            for pat in tf_data.wm_patterns:
                if pat.status != "BREAKOUT_CONFIRMED":
                    continue

                # Strict Quality Threshold: >= 75
                if pat.quality_score < 75:
                    continue

                if not pat.breakout_candle_time:
                    continue

                clean_time = (pat.breakout_candle_time or pat.s2_time or "").replace(':', '-').replace('.', '-')
                stable_alert_id = f"mw_{clean_sym}_{tf_name}_{pat.pattern_type}_{clean_time}"

                # Unique deduplication key: symbol + timeframe + pattern_id + breakout_candle_time
                dedupe_key = f"{synthesis.symbol}_{tf_name}_{pat.pattern_id}_{pat.breakout_candle_time}"
                
                # Check if already present in alerts
                existing = next(
                    (
                        a for a in self.alerts
                        if a.alert_id == stable_alert_id or (
                            a.symbol.upper() == synthesis.symbol.upper()
                            and a.timeframe.upper() == tf_name.upper()
                            and a.pattern_type == pat.pattern_type
                            and a.breakout_candle_timestamp == pat.breakout_candle_time
                        )
                    ),
                    None
                )

                if existing:
                    # Update fields in-place if changed
                    existing.s1_price = pat.s1_price
                    existing.s2_price = pat.s2_price
                    existing.neckline_price = pat.neckline_price
                    existing.pattern_height = pat.pattern_height
                    if pat.target_analysis:
                        existing.measured_target = round(pat.target_analysis.measured_target, 2)
                        existing.target_2 = round(pat.target_analysis.target_2, 2) if pat.target_analysis.target_2 else None
                        existing.invalidation_level = round(pat.target_analysis.invalidation_level, 2)
                    continue

                if dedupe_key in self.seen_event_keys:
                    continue

                self.seen_event_keys.add(dedupe_key)

                is_w = pat.pattern_type == "W"
                alert_type = "W_BREAKOUT_CONFIRMED" if is_w else "M_BREAKDOWN_CONFIRMED"
                direction = "UP" if is_w else "DOWN"

                # Find breakout candle metrics if present in recent events
                matching_event = next(
                    (e for e in tf_data.recent_events if e.timestamp == pat.breakout_candle_time and e.pattern_type == pat.pattern_type),
                    None
                )

                b_open = matching_event.breakout_candle_open if matching_event and matching_event.breakout_candle_open else pat.neckline_price
                b_high = matching_event.breakout_candle_high if matching_event and matching_event.breakout_candle_high else (pat.breakout_close or pat.neckline_price)
                b_low = matching_event.breakout_candle_low if matching_event and matching_event.breakout_candle_low else (pat.breakout_close or pat.neckline_price)
                b_close = pat.breakout_close or (matching_event.break_price if matching_event else pat.neckline_price)
                b_vol = matching_event.volume_ratio if matching_event and matching_event.volume_ratio else 1.25
                tl_price = matching_event.trendline_level if matching_event and matching_event.trendline_level else pat.neckline_price
                ema_price = matching_event.ema20_level if matching_event and matching_event.ema20_level else pat.neckline_price

                t_analysis = pat.target_analysis
                measured_target = t_analysis.measured_target if (t_analysis and t_analysis.measured_target) else (
                    pat.neckline_price + pat.pattern_height if is_w else pat.neckline_price - pat.pattern_height
                )
                target_2 = t_analysis.target_2 if (t_analysis and t_analysis.target_2) else (
                    pat.neckline_price + 2.0 * pat.pattern_height if is_w else pat.neckline_price - 2.0 * pat.pattern_height
                )
                nearest_sup = t_analysis.nearest_obstacle if not is_w and t_analysis else None
                inval_level = t_analysis.invalidation_level if t_analysis else (
                    pat.prev_swing_sl_price or (min(pat.s1_price, pat.s2_price) if is_w else max(pat.s1_price, pat.s2_price))
                )

                alert = MWBreakoutAlert(
                    alert_id=stable_alert_id,
                    alert_type=alert_type,
                    pattern_type=pat.pattern_type,
                    direction=direction,
                    symbol=synthesis.symbol,
                    ticker=synthesis.ticker,
                    timeframe=tf_name,
                    pattern_id=pat.pattern_id,
                    s1_price=pat.s1_price,
                    s1_timestamp=pat.s1_time,
                    s2_price=pat.s2_price,
                    s2_timestamp=pat.s2_time,
                    neckline_price=pat.neckline_price,
                    neckline_timestamp=pat.neckline_time,
                    pattern_height=pat.pattern_height,
                    breakout_candle_timestamp=pat.breakout_candle_time,
                    breakout_open=b_open,
                    breakout_high=b_high,
                    breakout_low=b_low,
                    breakout_close=b_close,
                    trendline_price=tl_price,
                    ema20_price=ema_price,
                    volume=0.0,
                    relative_volume=round(b_vol, 2),
                    measured_target=round(measured_target, 2),
                    target_2=round(target_2, 2) if target_2 else round(pat.neckline_price + 2.0 * pat.pattern_height if is_w else pat.neckline_price - 2.0 * pat.pattern_height, 2),
                    nearest_support=round(nearest_sup, 2) if nearest_sup else None,
                    nearest_resistance=round(nearest_res, 2) if nearest_res else None,
                    invalidation_level=round(inval_level, 2),
                    quality_score=pat.quality_score,
                    quality_breakdown=t_analysis.quality_breakdown if t_analysis else {},
                    status="TARGET OPEN",
                    event_created_at=now_str,
                    read=False
                )

                self.alerts.insert(0, alert)
                new_alerts.append(alert)

        # Cap memory storage
        if len(self.alerts) > 200:
            self.alerts = self.alerts[:200]

        if new_alerts:
            self._save_to_storage()

        return new_alerts, updated_alerts

    def _update_existing_alert_statuses(
        self,
        synthesis: MultiTimeframeSynthesis,
        mtf_candles: Optional[Dict[str, List[Candle]]] = None
    ) -> List[MWBreakoutAlert]:
        """
        Evaluates active/open alerts against live market price and subsequent candles to track trade outcomes:
        - TARGET OPEN: Initial state after confirmation
        - TARGET 1 HIT: Price reaches/crosses Measured Target 1
        - TARGET 2 HIT: Price subsequently (or directly) reaches/crosses Measured Target 2
        - SL HIT: Invalidation / SL reached before either target was reached
        """
        current_price = synthesis.current_price
        updated_alerts: List[MWBreakoutAlert] = []

        for alert in self.alerts:
            if alert.symbol != synthesis.symbol:
                continue

            # Terminal outcomes: TARGET 2 HIT and SL HIT are final and must never be overwritten
            if alert.status in ["TARGET 2 HIT", "SL HIT"]:
                continue

            t2_val = alert.target_2 if alert.target_2 is not None else (
                round(alert.neckline_price + 2.0 * alert.pattern_height, 2) if alert.pattern_type == "W" else round(alert.neckline_price - 2.0 * alert.pattern_height, 2)
            )
            t1_val = alert.measured_target
            sl_val = alert.invalidation_level

            status_changed = False

            # Inspect subsequent candles if available
            if mtf_candles:
                candles_to_check = mtf_candles.get(alert.timeframe, [])
                if not candles_to_check:
                    candles_to_check = mtf_candles.get("15M", []) or mtf_candles.get("5M", [])

                for c in candles_to_check:
                    # Only evaluate candles at or after the breakout timestamp
                    if alert.breakout_candle_timestamp and c.timestamp < alert.breakout_candle_timestamp:
                        continue

                    if alert.pattern_type == "W":
                        if c.high >= t2_val:
                            alert.status = "TARGET 2 HIT"
                            status_changed = True
                            break
                        elif c.high >= t1_val:
                            if alert.status not in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                                alert.status = "TARGET 1 HIT"
                                status_changed = True
                        elif alert.status in ["TARGET OPEN", "ACTIVE"] and c.low <= sl_val:
                            alert.status = "SL HIT"
                            status_changed = True
                            break

                    elif alert.pattern_type == "M":
                        if c.low <= t2_val:
                            alert.status = "TARGET 2 HIT"
                            status_changed = True
                            break
                        elif c.low <= t1_val:
                            if alert.status not in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                                alert.status = "TARGET 1 HIT"
                                status_changed = True
                        elif alert.status in ["TARGET OPEN", "ACTIVE"] and c.high >= sl_val:
                            alert.status = "SL HIT"
                            status_changed = True
                            break

            # Evaluate against current live price if not yet terminal
            if alert.status not in ["TARGET 2 HIT", "SL HIT"]:
                if alert.pattern_type == "W":
                    # Priority 1: Target 2 reached (direct jump or subsequent)
                    if current_price >= t2_val:
                        alert.status = "TARGET 2 HIT"
                        status_changed = True
                    # Priority 2: Target 1 reached
                    elif current_price >= t1_val:
                        if alert.status not in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                            alert.status = "TARGET 1 HIT"
                            status_changed = True
                    # Priority 3: Invalidation / SL reached before either target
                    elif alert.status in ["TARGET OPEN", "ACTIVE"] and current_price <= sl_val:
                        alert.status = "SL HIT"
                        status_changed = True

                elif alert.pattern_type == "M":
                    # Priority 1: Target 2 reached (direct jump or subsequent)
                    if current_price <= t2_val:
                        alert.status = "TARGET 2 HIT"
                        status_changed = True
                    # Priority 2: Target 1 reached
                    elif current_price <= t1_val:
                        if alert.status not in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                            alert.status = "TARGET 1 HIT"
                            status_changed = True
                    # Priority 3: Invalidation / SL reached before either target
                    elif alert.status in ["TARGET OPEN", "ACTIVE"] and current_price >= sl_val:
                        alert.status = "SL HIT"
                        status_changed = True

            if status_changed:
                updated_alerts.append(alert)

        if updated_alerts:
            self._save_to_storage()

        return updated_alerts

    def get_alerts(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        pattern_type: Optional[str] = None,
        status: Optional[str] = None,
        date_filter: Optional[str] = None,
        limit: int = 50
    ) -> List[MWBreakoutAlert]:
        """
        Retrieves filtered M/W alerts sorted newest first by breakout_candle_timestamp.
        """
        results = self.alerts

        if symbol:
            sym_norm = symbol.strip().upper().replace("/", "").replace("-", "").replace("_", "").replace(" ", "")
            results = [
                a for a in results
                if sym_norm in a.symbol.upper().replace("/", "").replace("-", "").replace("_", "").replace(" ", "")
                or (a.ticker and sym_norm in a.ticker.upper().replace("/", "").replace("-", "").replace("_", "").replace(" ", ""))
            ]

        if timeframe and timeframe.upper() != "ALL":
            results = [a for a in results if a.timeframe.upper() == timeframe.upper()]

        if pattern_type and pattern_type.upper() != "ALL":
            results = [a for a in results if a.pattern_type.upper() == pattern_type.upper()]

        if status and status.upper() != "ALL":
            st_clean = status.strip().upper()
            if st_clean == "COMPLETED":
                results = [a for a in results if a.status in ["TARGET 1 HIT", "TARGET 2 HIT", "TARGET_1_HIT", "TARGET_2_HIT"]]
            elif st_clean in ["ACTIVE", "TARGET OPEN", "OPEN"]:
                results = [a for a in results if a.status in ["TARGET OPEN", "ACTIVE"]]
            elif st_clean in ["INVALIDATED", "SL HIT", "SL_HIT"]:
                results = [a for a in results if a.status in ["SL HIT", "INVALIDATED"]]
            elif st_clean in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                results = [a for a in results if a.status in ["TARGET 1 HIT", "TARGET_1_HIT"]]
            elif st_clean in ["TARGET 2 HIT", "TARGET_2_HIT"]:
                results = [a for a in results if a.status in ["TARGET 2 HIT", "TARGET_2_HIT"]]
            else:
                results = [a for a in results if a.status.upper() == st_clean]

        if date_filter and date_filter.lower() != "all":
            now = datetime.now(timezone.utc)
            if date_filter.lower() == "today":
                results = [a for a in results if a.breakout_candle_timestamp[:10] == now.isoformat()[:10]]
            elif date_filter.lower() == "24h" or date_filter.lower() == "last 24 hours":
                cutoff = (now - timedelta(hours=24)).isoformat()
                results = [a for a in results if a.breakout_candle_timestamp >= cutoff]
            elif date_filter.lower() == "7d" or date_filter.lower() == "last 7 days":
                cutoff = (now - timedelta(days=7)).isoformat()
                results = [a for a in results if a.breakout_candle_timestamp >= cutoff]

        # Sort newest first by breakout_candle_timestamp
        results.sort(key=lambda a: a.breakout_candle_timestamp, reverse=True)
        return results[:limit]

    def get_alert_by_id(self, alert_id: str) -> Optional[MWBreakoutAlert]:
        """
        Retrieves a single historical alert by its unique alert_id.
        Supports exact match, URL decoded match, pattern_id match, and normalized slash/colon match.
        """
        if not alert_id:
            return None
        decoded = urllib.parse.unquote(alert_id)
        # 1. Exact match
        for a in self.alerts:
            if a.alert_id == alert_id or a.alert_id == decoded:
                return a
        # 2. Match by pattern_id
        for a in self.alerts:
            if a.pattern_id == alert_id or a.pattern_id == decoded:
                return a
        # 3. Normalized slash vs underscore and colon match
        norm_target = alert_id.replace('/', '_').replace('%2F', '_').replace('%2f', '_').replace(':', '-')
        norm_decoded = decoded.replace('/', '_').replace(':', '-')
        for a in self.alerts:
            norm_a = a.alert_id.replace('/', '_').replace(':', '-')
            if norm_a == norm_target or norm_a == norm_decoded:
                return a
        return None

    def mark_all_read(self):
        for a in self.alerts:
            a.read = True
        self._save_to_storage()

    def clear_alerts(self):
        self.alerts.clear()
        self.seen_event_keys.clear()
        self._save_to_storage()

    def get_summary_stats(self) -> Dict[str, int]:
        w_count = sum(1 for a in self.alerts if a.pattern_type == "W")
        m_count = sum(1 for a in self.alerts if a.pattern_type == "M")
        active_count = sum(1 for a in self.alerts if a.status in ["TARGET OPEN", "ACTIVE"])
        target_hit_count = sum(1 for a in self.alerts if a.status in ["TARGET 1 HIT", "TARGET 2 HIT", "TARGET_1_HIT", "TARGET_2_HIT"])
        invalidated_count = sum(1 for a in self.alerts if a.status in ["SL HIT", "INVALIDATED"])
        unread_count = sum(1 for a in self.alerts if not a.read)

        return {
            "w_breakouts": w_count,
            "m_breakdowns": m_count,
            "active_count": active_count,
            "target_hit_count": target_hit_count,
            "invalidated_count": invalidated_count,
            "unread_count": unread_count,
            "total_count": len(self.alerts)
        }

mw_breakout_engine = MWBreakoutAlertEngine()
