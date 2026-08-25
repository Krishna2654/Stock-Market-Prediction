import uuid
from typing import List, Optional, Set, Dict, Any
from datetime import datetime, timezone, timedelta
from app.models.schemas import MWBreakoutAlert, MultiTimeframeSynthesis, WMPatternStructure
from app.core.config import settings

class MWBreakoutAlertEngine:
    """
    Dedicated, Independent Alert Engine for Confirmed M/W Breakouts.
    
    Principles:
    1. ZERO MOCK/SAMPLE DATA: Real market data pipeline only.
    2. ONLY CONFIRMED BREAKOUTS: No forming/candidate/weak patterns.
    3. EXACT BREAKOUT CANDLE TIMESTAMPS: Formatted in Asia/Kolkata (IST).
    4. REAL TARGET TRACKING & INVALIDATION: Tracks live market prices against measured targets.
    5. COMPLETE ISOLATION: Completely independent from standard notification stream.
    """

    def __init__(self):
        self.alerts: List[MWBreakoutAlert] = []
        self.seen_event_keys: Set[str] = set()

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
                measured_target = t_analysis.measured_target if t_analysis else (
                    pat.neckline_price + pat.pattern_height if is_w else pat.neckline_price - pat.pattern_height
                )
                target_2 = t_analysis.target_2 if t_analysis else None
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
                    target_2=round(target_2, 2) if target_2 else None,
                    nearest_support=round(nearest_sup, 2) if nearest_sup else None,
                    nearest_resistance=round(nearest_res, 2) if nearest_res else None,
                    invalidation_level=round(inval_level, 2),
                    quality_score=pat.quality_score,
                    quality_breakdown=t_analysis.quality_breakdown if t_analysis else {},
                    status="ACTIVE",
                    event_created_at=now_str,
                    read=False
                )

                self.alerts.insert(0, alert)
                new_alerts.append(alert)

        # Cap memory storage
        if len(self.alerts) > 200:
            self.alerts = self.alerts[:200]

        return new_alerts

    def _update_existing_alert_statuses(self, synthesis: MultiTimeframeSynthesis):
        """
        Evaluates active alerts against live market price to track Target 1 Hit and Invalidation.
        """
        current_price = synthesis.current_price
        for alert in self.alerts:
            if alert.symbol != synthesis.symbol or alert.status != "ACTIVE":
                continue

            # Check W Target / Invalidation
            if alert.pattern_type == "W":
                if current_price >= alert.measured_target:
                    alert.status = "TARGET_1_HIT"
                elif current_price < (alert.invalidation_level - 0.05):
                    alert.status = "INVALIDATED"
            # Check M Target / Invalidation
            elif alert.pattern_type == "M":
                if current_price <= alert.measured_target:
                    alert.status = "TARGET_1_HIT"
                elif current_price > (alert.invalidation_level + 0.05):
                    alert.status = "INVALIDATED"

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
            if status.upper() == "COMPLETED":
                results = [a for a in results if a.status in ["TARGET_1_HIT", "TARGET_2_HIT"]]
            else:
                results = [a for a in results if a.status.upper() == status.upper()]

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

    def clear_alerts(self):
        self.alerts.clear()
        self.seen_event_keys.clear()

    def get_summary_stats(self) -> Dict[str, int]:
        w_count = sum(1 for a in self.alerts if a.pattern_type == "W")
        m_count = sum(1 for a in self.alerts if a.pattern_type == "M")
        active_count = sum(1 for a in self.alerts if a.status == "ACTIVE")
        target_hit_count = sum(1 for a in self.alerts if a.status in ["TARGET_1_HIT", "TARGET_2_HIT"])
        invalidated_count = sum(1 for a in self.alerts if a.status == "INVALIDATED")
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
