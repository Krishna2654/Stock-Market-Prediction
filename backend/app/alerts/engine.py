import asyncio
import uuid
from typing import List, Dict, Optional, Set
from datetime import datetime, timezone
from app.models.schemas import (
    AlertRule,
    AlertNotification,
    StructureBreakEvent,
    MultiTimeframeSynthesis
)

class AlertEngine:
    """
    High-Precision Breakout Alert Engine.
    STRICTLY alerts on:
    1. Trendline Breaks (Ascending Support / Descending Resistance)
    2. Resistance Breakouts (Price closing above key Resistance / Swing Highs)
    3. Support Breakdowns (Price closing below key Support / Swing Lows)
    
    Filters strictly by user-configured min_evidence_score (e.g. >= 80) and deduplicates events.
    """

    def __init__(self):
        self.rules: Dict[str, AlertRule] = {}
        self.notifications: List[AlertNotification] = []
        self.seen_event_ids: Set[str] = set()
        
        self._seed_strict_break_rules()

    def _seed_strict_break_rules(self):
        strict_rule = AlertRule(
            id="default-global-breakout-rule",
            symbol="ALL",
            timeframes=["4H", "1H", "15M", "5M"],
            event_types=["TREND_LINE_BREAK", "RESISTANCE_BREAK", "SUPPORT_BREAK"],
            min_evidence_score=80,
            is_enabled=True,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        self.rules[strict_rule.id] = strict_rule

    def add_rule(self, rule: AlertRule) -> AlertRule:
        # If adding a rule for 'ALL', overwrite any existing 'ALL' rules to avoid loose duplicate filters
        if rule.symbol == "ALL":
            keys_to_remove = [k for k, v in self.rules.items() if v.symbol == "ALL"]
            for k in keys_to_remove:
                del self.rules[k]
        elif rule.symbol:
            keys_to_remove = [k for k, v in self.rules.items() if v.symbol.upper() == rule.symbol.upper()]
            for k in keys_to_remove:
                del self.rules[k]

        self.rules[rule.id] = rule
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False

    def get_rules(self) -> List[AlertRule]:
        return list(self.rules.values())

    def get_notifications(self, limit: int = 50) -> List[AlertNotification]:
        return self.notifications[-limit:][::-1]

    def clear_notifications(self):
        self.notifications.clear()
        self.seen_event_ids.clear()

    def process_synthesis_for_alerts(
        self,
        synthesis: MultiTimeframeSynthesis
    ) -> List[AlertNotification]:
        new_alerts: List[AlertNotification] = []
        now_str = datetime.now(timezone.utc).isoformat()
        currency_sym = "$" if "BTC" in synthesis.symbol or "USD" in synthesis.symbol else "₹"
        current_score = synthesis.evidence_score.total_score

        # Check all timeframes for recent fresh breaks (within the last 6 candles)
        for tf_name in ["15M", "5M", "1H", "4H"]:
            tf_data = synthesis.timeframes.get(tf_name)
            if not tf_data or not tf_data.recent_events:
                continue

            for event in tf_data.recent_events[-6:]:
                # Ensure break occurred on recent candles
                if event.break_candle_index < max(0, tf_data.candle_count - 6):
                    continue

                if event.id in self.seen_event_ids:
                    continue

                # Skip precision confluence breakouts (handled separately by HighConfluenceAlertEngine)
                if "EMA_VOLUME" in event.event_type or "PATTERN_TRENDLINE" in event.event_type:
                    continue

                is_trendline_break = "TREND_LINE" in event.event_type or "TRENDLINE" in event.event_type
                is_resistance_break = (
                    "RESISTANCE" in event.event_type or
                    (event.direction == "BULLISH" and ("BOS" in event.event_type or "CHOCH" in event.event_type))
                )
                is_support_break = (
                    "SUPPORT" in event.event_type or
                    (event.direction == "BEARISH" and ("BOS" in event.event_type or "CHOCH" in event.event_type))
                )

                if not (is_trendline_break or is_resistance_break or is_support_break):
                    continue

                # Find matching active rule
                matching_rule: Optional[AlertRule] = None
                
                # Check specific symbol rule first
                for rule in self.rules.values():
                    if rule.is_enabled and rule.symbol.upper() == synthesis.symbol.upper() and event.timeframe in rule.timeframes:
                        matching_rule = rule
                        break
                        
                # If no specific rule, check global 'ALL' rule
                if matching_rule is None:
                    for rule in self.rules.values():
                        if rule.is_enabled and rule.symbol == "ALL" and event.timeframe in rule.timeframes:
                            matching_rule = rule
                            break

                if matching_rule is None:
                    continue

                # Match event category
                matches = False
                if is_trendline_break and any(k in matching_rule.event_types for k in ["TREND_LINE_BREAK", "TRENDLINE", "ALL"]):
                    matches = True
                elif is_resistance_break and any(k in matching_rule.event_types for k in ["RESISTANCE_BREAK", "RESISTANCE", "BULLISH_BOS", "ALL"]):
                    matches = True
                elif is_support_break and any(k in matching_rule.event_types for k in ["SUPPORT_BREAK", "SUPPORT", "BEARISH_BOS", "ALL"]):
                    matches = True

                if not matches:
                    continue

                # STRICT MINIMUM EVIDENCE SCORE CHECK
                if current_score < matching_rule.min_evidence_score:
                    continue

                self.seen_event_ids.add(event.id)

                # Formulate directional breakout title & message
                if is_trendline_break:
                    touch_prefix = "3-TOUCH" if ("3-TOUCH" in event.notes or "3+" in event.notes) else "2-TOUCH"
                    if event.direction == "BULLISH":
                        msg = f"🟢 {touch_prefix} TRENDLINE BREAK — BULLISH — UP BREAKOUT — {synthesis.symbol} — {event.timeframe} at {currency_sym}{event.break_price:,.2f} (Level: {currency_sym}{event.broken_level:,.2f}, Confirmed Close)"
                    else:
                        msg = f"🔴 {touch_prefix} TRENDLINE BREAK — BEARISH — DOWN BREAKOUT — {synthesis.symbol} — {event.timeframe} at {currency_sym}{event.break_price:,.2f} (Level: {currency_sym}{event.broken_level:,.2f}, Confirmed Close)"
                elif is_resistance_break:
                    break_desc = "RESISTANCE BREAK"
                    msg = f"🟢 UP BREAKOUT — {synthesis.symbol} — {event.timeframe} | {break_desc} at {currency_sym}{event.break_price:,.2f} (Level: {currency_sym}{event.broken_level:,.2f}, Confirmed Close)"
                else:
                    break_desc = "SUPPORT BREAK"
                    msg = f"🔴 DOWN BREAKOUT — {synthesis.symbol} — {event.timeframe} | {break_desc} at {currency_sym}{event.break_price:,.2f} (Level: {currency_sym}{event.broken_level:,.2f}, Confirmed Close)"

                alert = AlertNotification(
                    id=f"alert_{event.id}",
                    timestamp=now_str,
                    symbol=synthesis.symbol,
                    timeframe=event.timeframe,
                    event_type="TREND_LINE_BREAK" if is_trendline_break else ("RESISTANCE_BREAK" if is_resistance_break else "SUPPORT_BREAK"),
                    message=msg,
                    price=event.break_price,
                    level=event.broken_level,
                    evidence_score=current_score,
                    volume_confirmed=event.volume_confirmed,
                    htf_alignment=event.htf_alignment,
                    read=False
                )
                self.notifications.append(alert)
                new_alerts.append(alert)

        return new_alerts

alert_engine = AlertEngine()
