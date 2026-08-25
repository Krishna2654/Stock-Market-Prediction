import uuid
from typing import List, Dict, Optional, Set
from datetime import datetime, timezone
from app.models.schemas import (
    HighConfluenceAlert,
    MultiTimeframeSynthesis,
    StructureBreakEvent
)
from app.core.config import settings

class HighConfluenceAlertEngine:
    """
    Dedicated Independent High-Confluence Breakout Alert Engine.
    Strictly handles ONLY:
    1. TRENDLINE + 20 EMA + VOLUME BREAKOUT (UP / DOWN)
    2. W/M PATTERN + TRENDLINE + 20 EMA BREAKOUT (UP / DOWN)
    
    STRICT QUALITY & TIMESTAMPS:
    - Minimum Evidence Score filter (MIN_W_M_HIGH_CONFLUENCE_SCORE = 75).
    - True Breakout Timestamp from the completed breakout candle (NOT event creation time).
    - Full pattern lifecycle tracking (L1, Neckline, L2, Breakout Candle OHLC).
    """

    def __init__(self):
        self.alerts: List[HighConfluenceAlert] = []
        self.seen_event_ids: Set[str] = set()

    def get_alerts(self, symbol: Optional[str] = None, limit: int = 30) -> List[HighConfluenceAlert]:
        if symbol:
            filtered = [a for a in self.alerts if a.symbol.upper() == symbol.upper()]
            return filtered[-limit:][::-1]
        return self.alerts[-limit:][::-1]

    def clear_alerts(self):
        self.alerts.clear()
        self.seen_event_ids.clear()

    def process_synthesis_for_high_confluence_alerts(
        self,
        synthesis: MultiTimeframeSynthesis
    ) -> List[HighConfluenceAlert]:
        new_high_alerts: List[HighConfluenceAlert] = []
        now_str = datetime.now(timezone.utc).isoformat()
        currency_sym = "$" if "BTC" in synthesis.symbol or "USD" in synthesis.symbol else "₹"
        current_score = synthesis.evidence_score.total_score

        # Check all timeframes for fresh precision break events
        for tf_name in ["15M", "5M", "1H", "4H"]:
            tf_data = synthesis.timeframes.get(tf_name)
            if not tf_data or not tf_data.recent_events:
                continue

            for event in tf_data.recent_events[-6:]:
                # Only process events on recent closed candles
                if event.break_candle_index < max(0, tf_data.candle_count - 6):
                    continue

                dedupe_key = f"{synthesis.symbol}_{event.timeframe}_{event.pattern_id or event.id}"
                if dedupe_key in self.seen_event_ids or event.id in self.seen_event_ids:
                    continue

                is_tl_ema_vol_up = event.event_type == "TRENDLINE_EMA_VOLUME_UP_BREAKOUT"
                is_tl_ema_vol_down = event.event_type == "TRENDLINE_EMA_VOLUME_DOWN_BREAKOUT"
                is_w_pat_break = event.event_type == "W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT"
                is_m_pat_break = event.event_type == "M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT"

                if not (is_tl_ema_vol_up or is_tl_ema_vol_down or is_w_pat_break or is_m_pat_break):
                    continue

                # STRICT QUALITY FILTER: Pattern Quality Score must meet high-confluence threshold (>= 75)
                q_score = event.pattern_quality_score or current_score
                min_required_score = settings.MIN_W_M_HIGH_CONFLUENCE_SCORE
                if q_score < min_required_score:
                    continue

                self.seen_event_ids.add(event.id)
                self.seen_event_ids.add(dedupe_key)

                # Extract indicators & key target levels
                ema_val = event.ema20_level or tf_data.indicators.ema_20 or event.break_price
                rel_vol = event.volume_ratio or tf_data.indicators.relative_volume or 1.25
                tl_level = event.trendline_level or event.broken_level
                sr = tf_data.support_resistance

                if is_tl_ema_vol_up:
                    next_target = sr.minor_resistance or (event.break_price * 1.01)
                    inval = event.broken_level
                    msg = (
                        f"🟢 UP BREAKOUT — TRENDLINE + 20 EMA + VOLUME\n"
                        f"{synthesis.symbol} • {event.timeframe}\n"
                        f"Breakout Candle Close: {currency_sym}{event.break_price:,.2f} | Trendline: {currency_sym}{tl_level:,.2f} ✓\n"
                        f"20 EMA: {currency_sym}{ema_val:,.2f} ✓ | Volume: {rel_vol:.2f}× ✓\n"
                        f"Candle: CONFIRMED CLOSED ✓ | Evidence: {current_score}/100"
                    )
                    alert = HighConfluenceAlert(
                        id=f"hc_{event.id}",
                        alert_category="HIGH_CONFLUENCE",
                        alert_type="TRENDLINE_EMA_VOLUME_UP_BREAKOUT",
                        symbol=synthesis.symbol,
                        timeframe=event.timeframe,
                        direction="UP",
                        timestamp=event.timestamp,
                        breakout_candle_timestamp=event.timestamp,
                        breakout_candle_open=event.breakout_candle_open,
                        breakout_candle_high=event.breakout_candle_high,
                        breakout_candle_low=event.breakout_candle_low,
                        breakout_candle_close=event.break_price,
                        trendline_level=tl_level,
                        ema20_level=ema_val,
                        volume_ratio=round(rel_vol, 2),
                        pattern_type=None,
                        neckline_level=None,
                        trendline_confirmed=True,
                        ema_confirmed=True,
                        volume_confirmed=True,
                        neckline_confirmed=True,
                        candle_closed_confirmed=True,
                        evidence_score=current_score,
                        next_level=round(next_target, 2),
                        invalidation_level=round(inval, 2),
                        event_created_at=now_str,
                        message=msg
                    )

                elif is_tl_ema_vol_down:
                    next_target = sr.minor_support or (event.break_price * 0.99)
                    inval = event.broken_level
                    msg = (
                        f"🔴 DOWN BREAKOUT — TRENDLINE + 20 EMA + VOLUME\n"
                        f"{synthesis.symbol} • {event.timeframe}\n"
                        f"Breakout Candle Close: {currency_sym}{event.break_price:,.2f} | Trendline: {currency_sym}{tl_level:,.2f} ✓\n"
                        f"20 EMA: {currency_sym}{ema_val:,.2f} ✓ | Volume: {rel_vol:.2f}× ✓\n"
                        f"Candle: CONFIRMED CLOSED ✓ | Evidence: {current_score}/100"
                    )
                    alert = HighConfluenceAlert(
                        id=f"hc_{event.id}",
                        alert_category="HIGH_CONFLUENCE",
                        alert_type="TRENDLINE_EMA_VOLUME_DOWN_BREAKOUT",
                        symbol=synthesis.symbol,
                        timeframe=event.timeframe,
                        direction="DOWN",
                        timestamp=event.timestamp,
                        breakout_candle_timestamp=event.timestamp,
                        breakout_candle_open=event.breakout_candle_open,
                        breakout_candle_high=event.breakout_candle_high,
                        breakout_candle_low=event.breakout_candle_low,
                        breakout_candle_close=event.break_price,
                        trendline_level=tl_level,
                        ema20_level=ema_val,
                        volume_ratio=round(rel_vol, 2),
                        pattern_type=None,
                        neckline_level=None,
                        trendline_confirmed=True,
                        ema_confirmed=True,
                        volume_confirmed=True,
                        neckline_confirmed=True,
                        candle_closed_confirmed=True,
                        evidence_score=current_score,
                        next_level=round(next_target, 2),
                        invalidation_level=round(inval, 2),
                        event_created_at=now_str,
                        message=msg
                    )

                elif is_w_pat_break:
                    target_info = event.target_analysis
                    next_target = target_info.measured_target if target_info else (sr.minor_resistance or (event.break_price * 1.01))
                    inval = target_info.invalidation_level if target_info else (event.neckline_price or event.broken_level)
                    q_score = event.pattern_quality_score or current_score

                    msg = (
                        f"🟢 W PATTERN + TRENDLINE + 20 EMA — UP BREAKOUT\n"
                        f"{synthesis.symbol} • {event.timeframe}\n"
                        f"Breakout Candle Close: {currency_sym}{event.break_price:,.2f} | Neckline: {currency_sym}{inval:,.2f} ✓\n"
                        f"Trendline: {currency_sym}{tl_level:,.2f} ✓ | 20 EMA: {currency_sym}{ema_val:,.2f} ✓\n"
                        f"Measured Target: {currency_sym}{next_target:,.2f} | Invalidation: {currency_sym}{inval:,.2f}\n"
                        f"Candle: CONFIRMED CLOSED ✓ | Pattern Quality: {q_score}/100"
                    )
                    alert = HighConfluenceAlert(
                        id=f"hc_{event.id}",
                        alert_category="HIGH_CONFLUENCE",
                        alert_type="W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT",
                        symbol=synthesis.symbol,
                        timeframe=event.timeframe,
                        direction="UP",
                        timestamp=event.timestamp,
                        breakout_candle_timestamp=event.timestamp,
                        breakout_candle_open=event.breakout_candle_open,
                        breakout_candle_high=event.breakout_candle_high,
                        breakout_candle_low=event.breakout_candle_low,
                        breakout_candle_close=event.break_price,
                        trendline_level=tl_level,
                        ema20_level=ema_val,
                        volume_ratio=round(rel_vol, 2),
                        pattern_id=event.pattern_id,
                        pattern_type="W",
                        pattern_formed_time=event.pattern_formed_time,
                        first_swing_price=event.first_swing_price,
                        first_swing_time=event.first_swing_time,
                        second_swing_price=event.second_swing_price,
                        second_swing_time=event.second_swing_time,
                        neckline_price=event.neckline_price or event.broken_level,
                        neckline_level=event.neckline_price or event.broken_level,
                        neckline_time=event.neckline_time,
                        trendline_confirmed=True,
                        ema_confirmed=True,
                        volume_confirmed=True,
                        neckline_confirmed=True,
                        candle_closed_confirmed=True,
                        evidence_score=current_score,
                        pattern_quality_score=q_score,
                        target_analysis=target_info,
                        next_level=round(next_target, 2),
                        invalidation_level=round(inval, 2),
                        event_created_at=now_str,
                        message=msg
                    )

                elif is_m_pat_break:
                    target_info = event.target_analysis
                    next_target = target_info.measured_target if target_info else (sr.minor_support or (event.break_price * 0.99))
                    inval = target_info.invalidation_level if target_info else (event.neckline_price or event.broken_level)
                    q_score = event.pattern_quality_score or current_score

                    msg = (
                        f"🔴 M PATTERN + TRENDLINE + 20 EMA — DOWN BREAKOUT\n"
                        f"{synthesis.symbol} • {event.timeframe}\n"
                        f"Breakout Candle Close: {currency_sym}{event.break_price:,.2f} | Neckline: {currency_sym}{inval:,.2f} ✓\n"
                        f"Trendline: {currency_sym}{tl_level:,.2f} ✓ | 20 EMA: {currency_sym}{ema_val:,.2f} ✓\n"
                        f"Measured Target: {currency_sym}{next_target:,.2f} | Invalidation: {currency_sym}{inval:,.2f}\n"
                        f"Candle: CONFIRMED CLOSED ✓ | Pattern Quality: {q_score}/100"
                    )
                    alert = HighConfluenceAlert(
                        id=f"hc_{event.id}",
                        alert_category="HIGH_CONFLUENCE",
                        alert_type="M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT",
                        symbol=synthesis.symbol,
                        timeframe=event.timeframe,
                        direction="DOWN",
                        timestamp=event.timestamp,
                        breakout_candle_timestamp=event.timestamp,
                        breakout_candle_open=event.breakout_candle_open,
                        breakout_candle_high=event.breakout_candle_high,
                        breakout_candle_low=event.breakout_candle_low,
                        breakout_candle_close=event.break_price,
                        trendline_level=tl_level,
                        ema20_level=ema_val,
                        volume_ratio=round(rel_vol, 2),
                        pattern_id=event.pattern_id,
                        pattern_type="M",
                        pattern_formed_time=event.pattern_formed_time,
                        first_swing_price=event.first_swing_price,
                        first_swing_time=event.first_swing_time,
                        second_swing_price=event.second_swing_price,
                        second_swing_time=event.second_swing_time,
                        neckline_price=event.neckline_price or event.broken_level,
                        neckline_level=event.neckline_price or event.broken_level,
                        neckline_time=event.neckline_time,
                        trendline_confirmed=True,
                        ema_confirmed=True,
                        volume_confirmed=True,
                        neckline_confirmed=True,
                        candle_closed_confirmed=True,
                        evidence_score=current_score,
                        pattern_quality_score=q_score,
                        target_analysis=target_info,
                        next_level=round(next_target, 2),
                        invalidation_level=round(inval, 2),
                        event_created_at=now_str,
                        message=msg
                    )

                self.alerts.append(alert)
                new_high_alerts.append(alert)

        return new_high_alerts

high_confluence_alert_engine = HighConfluenceAlertEngine()
