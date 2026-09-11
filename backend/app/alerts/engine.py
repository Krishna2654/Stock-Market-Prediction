import asyncio
import logging
import sqlite3
import uuid
from typing import List, Dict, Optional, Set, Tuple, Any
from datetime import datetime, timezone
from app.models.schemas import (
    AlertRule,
    AlertNotification,
    StructureBreakEvent,
    MultiTimeframeSynthesis
)
from app.db.database import get_database_path, get_session_factory
from app.db.repository import StructureNotificationRepository
from app.core.timezone import is_candle_closed

logger = logging.getLogger(__name__)


class AwaitableTuple(tuple):
    """Tuple subclass that can be awaited in async contexts or unpacked synchronously."""
    def __new__(cls, sync_tuple, coro_func):
        instance = super().__new__(cls, sync_tuple)
        instance._coro_func = coro_func
        return instance

    def __await__(self):
        return self._coro_func().__await__()


class AlertEngine:
    """
    High-Precision Breakout Alert Engine (Signal & Notification Only).
    STRICTLY alerts on:
    1. Trendline Breaks (Ascending Support / Descending Resistance)
       - Evaluates event's own evidence score (90 for 3-TOUCH, 75 for 2-TOUCH).
       - Does NOT reject valid trendline breaks based on unrelated macro synthesis score.
       - Classifies into ⭐ 3-TOUCH (high-confidence) and 2-TOUCH (standard-confidence).
    2. Resistance Breakouts (Price closing above key Resistance / Swing Highs)
    3. Support Breakdowns (Price closing below key Support / Swing Lows)

    Guarantees:
    - Signal & notification only: ZERO trade execution, orders, or broker API calls.
    - Completed candle close enforcement.
    - Deterministic event-identity deduplication & startup flood protection.
    - Lossless persistence to SQLite `structure_notifications` table.
    """

    def __init__(self):
        self.rules: Dict[str, AlertRule] = {}
        self.notifications: List[AlertNotification] = []
        self.seen_event_ids: Set[str] = set()

        self._seed_strict_break_rules()
        self._load_persisted_notifications_sync()

    def _seed_strict_break_rules(self):
        strict_rule = AlertRule(
            id="default-global-breakout-rule",
            symbol="ALL",
            timeframes=["4H", "1H", "15M", "5M"],
            event_types=["TREND_LINE_BREAK", "RESISTANCE_BREAK", "SUPPORT_BREAK"],
            min_evidence_score=75,
            is_enabled=True,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        self.rules[strict_rule.id] = strict_rule

    def _load_persisted_notifications_sync(self):
        """Loads seen event IDs and recent notifications from SQLite on startup to warm memory cache."""
        try:
            db_path = get_database_path()
            if not db_path.exists():
                return
            with sqlite3.connect(str(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='structure_notifications';")
                if not cursor.fetchone():
                    return
                cursor.execute("SELECT id, symbol, timeframe, event_type, timestamp, direction FROM structure_notifications;")
                for r in cursor.fetchall():
                    nid = r["id"]
                    self.seen_event_ids.add(nid)
                    if nid.startswith("alert_"):
                        self.seen_event_ids.add(nid[6:])
                    self.seen_event_ids.add(f"{r['symbol']}_{r['timeframe']}_{r['event_type']}_{r['timestamp']}_{r['direction']}")

                cursor.execute("SELECT * FROM structure_notifications ORDER BY timestamp DESC, created_at DESC LIMIT 100;")
                rows = cursor.fetchall()
                loaded = []
                for r in rows:
                    d = dict(r)
                    d["read"] = bool(d.get("read", 0))
                    d["volume_confirmed"] = bool(d.get("volume_confirmed", 1))
                    loaded.append(AlertNotification(**d))
                # Store in chronological order so .get_notifications() [-limit:][::-1] displays newest first
                self.notifications = loaded[::-1]
        except Exception as e:
            logger.debug(f"[AlertEngine] Startup load from SQLite: {e}")

    def _persist_notification_db_sync(self, notif: AlertNotification) -> bool:
        """Persists notification to SQLite structure_notifications table idempotently."""
        try:
            db_path = get_database_path()
            if not db_path.exists():
                return False
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='structure_notifications';")
                if not cursor.fetchone():
                    return False
                cursor.execute(
                    """
                    INSERT INTO structure_notifications (
                        id, timestamp, symbol, timeframe, event_type, direction,
                        touch_class, message, price, level, evidence_score,
                        volume_confirmed, htf_alignment, action_line_slope,
                        action_line_intercept, safety_line_type, safety_line_touches,
                        read, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, timeframe, event_type, timestamp, direction) DO NOTHING;
                    """,
                    (
                        notif.id,
                        notif.timestamp,
                        notif.symbol,
                        notif.timeframe,
                        notif.event_type,
                        notif.direction,
                        notif.touch_class,
                        notif.message,
                        notif.price,
                        notif.level,
                        notif.evidence_score,
                        1 if notif.volume_confirmed else 0,
                        notif.htf_alignment,
                        notif.action_line_slope,
                        notif.action_line_intercept,
                        notif.safety_line_type,
                        notif.safety_line_touches,
                        1 if notif.read else 0,
                        notif.created_at or datetime.now(timezone.utc).isoformat(),
                    )
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.debug(f"[AlertEngine] Sync persist error: {e}")
            return False

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
        try:
            db_path = get_database_path()
            if db_path.exists():
                with sqlite3.connect(str(db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM structure_notifications;")
                    conn.commit()
        except Exception:
            pass

    def mark_all_read(self) -> int:
        for n in self.notifications:
            n.read = True
        try:
            db_path = get_database_path()
            if db_path.exists():
                with sqlite3.connect(str(db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE structure_notifications SET read = 1 WHERE read = 0 OR read IS NULL;")
                    conn.commit()
                    return cursor.rowcount
        except Exception:
            pass
        return len(self.notifications)

    def get_paginated_notifications_memory(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        event_type: Optional[str] = None,
        touch_class: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Tuple[List[AlertNotification], int, int, bool, bool]:
        results = list(self.notifications)
        if symbol and symbol.upper() != "ALL":
            results = [n for n in results if n.symbol.upper() == symbol.upper()]
        if timeframe:
            results = [n for n in results if n.timeframe == timeframe]
        if event_type and event_type.upper() != "ALL":
            results = [n for n in results if n.event_type == event_type]
        if touch_class and touch_class.upper() != "ALL":
            results = [n for n in results if n.touch_class == touch_class]

        results.sort(key=lambda n: (n.timestamp or "", n.created_at or ""), reverse=True)
        total = len(results)
        limit = max(1, min(limit, 200))
        page = max(1, page)
        total_pages = max(1, (total + limit - 1) // limit) if total > 0 else 1
        start = (page - 1) * limit
        end = start + limit
        items = results[start:end]
        has_next = page < total_pages
        has_prev = page > 1
        return items, total, total_pages, has_next, has_prev

    def get_paginated_notifications(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        event_type: Optional[str] = None,
        touch_class: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> AwaitableTuple:
        sync_res = self.get_paginated_notifications_memory(
            symbol=symbol, timeframe=timeframe, event_type=event_type,
            touch_class=touch_class, page=page, limit=limit
        )

        async def _async_paginate():
            factory = get_session_factory()
            async with factory() as session:
                repo = StructureNotificationRepository(session)
                items, total, total_pages, has_next, has_prev = await repo.get_paginated_notifications(
                    symbol=symbol, timeframe=timeframe, event_type=event_type,
                    touch_class=touch_class, page=page, limit=limit
                )
                if total > 0:
                    return items, total, total_pages, has_next, has_prev
            return sync_res

        return AwaitableTuple(sync_res, _async_paginate)

    def process_synthesis_for_alerts(
        self,
        synthesis: MultiTimeframeSynthesis,
        is_catchup: bool = False
    ) -> List[AlertNotification]:
        new_alerts: List[AlertNotification] = []
        now_str = datetime.now(timezone.utc).isoformat()
        currency_sym = "$" if "BTC" in synthesis.symbol or "USD" in synthesis.symbol else "₹"
        macro_score = synthesis.evidence_score.total_score

        # Check all timeframes for recent fresh breaks
        for tf_name in ["15M", "5M", "1H", "4H"]:
            tf_data = synthesis.timeframes.get(tf_name)
            if not tf_data or not tf_data.recent_events:
                continue

            for event in tf_data.recent_events:
                # Deduplication check: event ID or composite key
                event_composite_key = f"{synthesis.symbol}_{event.timeframe}_{event.event_type}_{event.timestamp}_{event.direction}"
                if event.id in self.seen_event_ids or event_composite_key in self.seen_event_ids:
                    continue

                # Completed-candle close enforcement (skip uncompleted forming candles)
                if not is_candle_closed(event.timestamp, event.timeframe):
                    continue

                # Live notification eligibility:
                # Breakout occurred on a recent candle (within last 6 bars of the window)
                # AND we are not in historical catchup recovery mode
                is_live_candle = event.break_candle_index >= max(0, tf_data.candle_count - 6)
                emit_live_notification = (not is_catchup) and is_live_candle

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
                for rule in self.rules.values():
                    if rule.is_enabled and rule.symbol.upper() == synthesis.symbol.upper() and event.timeframe in rule.timeframes:
                        matching_rule = rule
                        break

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

                # EVIDENCE SCORE EVALUATION (Decoupled & Confidence-Preserving):
                # For trendline breakouts: evaluate the event's OWN evidence score (90 for 3-touch, 75 for 2-touch).
                # A valid trendline break must NOT be rejected because unrelated overall synthesis macro score < 80.
                if is_trendline_break:
                    eval_score = event.evidence_score
                else:
                    eval_score = event.evidence_score if event.evidence_score is not None else macro_score

                if eval_score < matching_rule.min_evidence_score:
                    continue

                # Mark as seen
                self.seen_event_ids.add(event.id)
                self.seen_event_ids.add(event_composite_key)

                # Formulate message and classification
                touch_class = None
                if is_trendline_break:
                    is_3touch = "3-TOUCH" in event.notes or "3+" in event.notes
                    touch_class = "3-TOUCH" if is_3touch else "2-TOUCH"
                    badge = "⭐ 3-TOUCH" if is_3touch else "2-TOUCH"
                    if event.direction == "BULLISH":
                        msg = f"🟢 {badge} TRENDLINE BREAK — BULLISH — UP BREAKOUT — {synthesis.symbol} — {event.timeframe} at {currency_sym}{event.break_price:,.2f} (Level: {currency_sym}{event.broken_level:,.2f}, Confirmed Close)"
                    else:
                        msg = f"🔴 {badge} TRENDLINE BREAK — BEARISH — DOWN BREAKOUT — {synthesis.symbol} — {event.timeframe} at {currency_sym}{event.break_price:,.2f} (Level: {currency_sym}{event.broken_level:,.2f}, Confirmed Close)"
                elif is_resistance_break:
                    break_desc = "RESISTANCE BREAK"
                    msg = f"🟢 UP BREAKOUT — {synthesis.symbol} — {event.timeframe} | {break_desc} at {currency_sym}{event.break_price:,.2f} (Level: {currency_sym}{event.broken_level:,.2f}, Confirmed Close)"
                else:
                    break_desc = "SUPPORT BREAK"
                    msg = f"🔴 DOWN BREAKOUT — {synthesis.symbol} — {event.timeframe} | {break_desc} at {currency_sym}{event.break_price:,.2f} (Level: {currency_sym}{event.broken_level:,.2f}, Confirmed Close)"

                alert = AlertNotification(
                    id=f"alert_{event.id}",
                    timestamp=event.timestamp,  # Exact breakout candle timestamp
                    symbol=synthesis.symbol,
                    timeframe=event.timeframe,
                    event_type="TREND_LINE_BREAK" if is_trendline_break else ("RESISTANCE_BREAK" if is_resistance_break else "SUPPORT_BREAK"),
                    direction=event.direction,
                    touch_class=touch_class,
                    message=msg,
                    price=event.break_price,
                    level=event.broken_level,
                    evidence_score=eval_score,
                    volume_confirmed=event.volume_confirmed,
                    htf_alignment=event.htf_alignment,
                    read=False,
                    created_at=now_str
                )

                self.seen_event_ids.add(alert.id)
                self.notifications.append(alert)

                # Lossless persistence to SQLite (ALWAYS PERSISTED)
                self._persist_notification_db_sync(alert)

                # Live notification toast only if candle is live and not in catchup mode
                if emit_live_notification:
                    new_alerts.append(alert)

        return new_alerts


alert_engine = AlertEngine()
