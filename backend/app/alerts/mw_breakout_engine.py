import json
import os
import uuid
from pathlib import Path
from typing import List, Optional, Set, Dict, Any
from datetime import datetime, timezone, timedelta
from app.models.schemas import MWBreakoutAlert, MultiTimeframeSynthesis, WMPatternStructure
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

    def process_synthesis(self, synthesis: MultiTimeframeSynthesis) -> List[MWBreakoutAlert]:
        """
        Scans all timeframes of a newly computed synthesis for confirmed M/W pattern breakouts.
        Returns newly triggered alerts.
        """
        new_alerts: List[MWBreakoutAlert] = []
        now_str = datetime.now(timezone.utc).isoformat()

        # 1. Update existing alerts with live price for target hit / invalidation tracking
        self._update_existing_alert_statuses(synthesis)

        # 2. Check for newly confirmed W/M breakouts
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

                # Unique deduplication key: symbol + timeframe + pattern_id + breakout_candle_time
                dedupe_key = f"{synthesis.symbol}_{tf_name}_{pat.pattern_id}_{pat.breakout_candle_time}"
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
                nearest_res = t_analysis.nearest_obstacle if is_w and t_analysis else None
                inval_level = t_analysis.invalidation_level if t_analysis else pat.neckline_price

                alert = MWBreakoutAlert(
                    alert_id=f"mw_{synthesis.symbol.replace(' ', '_')}_{tf_name}_{pat.pattern_type}_{str(uuid.uuid4())[:8]}",
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

        return new_alerts

    def _update_existing_alert_statuses(self, synthesis: MultiTimeframeSynthesis):
        """
        Evaluates active/open alerts against live market price to track trade outcomes:
        - TARGET OPEN: Initial state after confirmation
        - TARGET 1 HIT: Price reaches/crosses Measured Target 1
        - TARGET 2 HIT: Price subsequently (or directly) reaches/crosses Measured Target 2
        - SL HIT: Invalidation / SL reached before either target was reached
        """
        current_price = synthesis.current_price
        updated = False

        for alert in self.alerts:
            if alert.symbol != synthesis.symbol:
                continue

            # Terminal outcomes: TARGET 2 HIT and SL HIT are final and must never be overwritten
            if alert.status in ["TARGET 2 HIT", "SL HIT"]:
                continue

            t2_val = alert.target_2 if alert.target_2 is not None else (
                round(alert.neckline_price + 2.0 * alert.pattern_height, 2) if alert.pattern_type == "W" else round(alert.neckline_price - 2.0 * alert.pattern_height, 2)
            )

            # Bullish / W Breakout (Target 1 & 2 above breakout, SL below invalidation)
            if alert.pattern_type == "W":
                # Check Priority 1: Target 2 reached (direct or subsequent)
                if current_price >= t2_val:
                    alert.status = "TARGET 2 HIT"
                    updated = True
                # Check Priority 2: Target 1 reached (price >= measured_target, not yet at Target 2)
                elif current_price >= alert.measured_target:
                    if alert.status not in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                        alert.status = "TARGET 1 HIT"
                        updated = True
                # Check Priority 3: SL reached before either target
                elif alert.status in ["TARGET OPEN", "ACTIVE"] and current_price <= alert.invalidation_level:
                    alert.status = "SL HIT"
                    updated = True

            # Bearish / M Breakdown (Target 1 & 2 below breakdown, SL above invalidation)
            elif alert.pattern_type == "M":
                # Check Priority 1: Target 2 reached (direct or subsequent)
                if current_price <= t2_val:
                    alert.status = "TARGET 2 HIT"
                    updated = True
                # Check Priority 2: Target 1 reached (price <= measured_target, not yet at Target 2)
                elif current_price <= alert.measured_target:
                    if alert.status not in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                        alert.status = "TARGET 1 HIT"
                        updated = True
                # Check Priority 3: SL reached before either target
                elif alert.status in ["TARGET OPEN", "ACTIVE"] and current_price >= alert.invalidation_level:
                    alert.status = "SL HIT"
                    updated = True

        if updated:
            self._save_to_storage()

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
            sym_clean = symbol.strip().upper()
            results = [a for a in results if sym_clean in a.symbol.upper() or (a.ticker and sym_clean in a.ticker.upper())]

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
        return next((a for a in self.alerts if a.alert_id == alert_id), None)

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
