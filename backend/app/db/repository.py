import logging
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MWBreakoutAlertModel, StructureNotificationModel, ProcessingCheckpointModel
from app.models.schemas import AlertNotification, MWBreakoutAlert, ProcessingCheckpoint

logger = logging.getLogger(__name__)


class MigrationConflictError(Exception):
    """Raised when an alert record conflicts with existing data for the same physical identity."""
    pass


class MWAlertRepository:
    """
    Dedicated database repository for persistent W/M Breakout alerts.
    Provides lossless persistence, unique physical identity enforcement,
    active-only lifecycle updates, and index-backed chronological pagination.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_physical_identity(
        self,
        symbol: str,
        timeframe: str,
        pattern_type: str,
        breakout_candle_timestamp: str,
    ) -> Optional[MWBreakoutAlertModel]:
        """Finds an alert model by its unique physical breakout identity."""
        stmt = select(MWBreakoutAlertModel).where(
            MWBreakoutAlertModel.symbol == symbol,
            MWBreakoutAlertModel.timeframe == timeframe,
            MWBreakoutAlertModel.pattern_type == pattern_type,
            MWBreakoutAlertModel.breakout_candle_timestamp == breakout_candle_timestamp,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_id(self, alert_id: str) -> Optional[MWBreakoutAlertModel]:
        """Finds an alert by its primary key alert_id."""
        stmt = select(MWBreakoutAlertModel).where(
            MWBreakoutAlertModel.alert_id == alert_id
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def ingest_alert_safe(
        self,
        alert: MWBreakoutAlert,
        deduplicate_structural: bool = True,
    ) -> Tuple[str, MWBreakoutAlertModel]:
        """
        Executes strict 3-way ingest/migration logic for a physical breakout identity:
        1. Not in DB -> INSERT, returns ("INSERTED", new_model)
        2. In DB with IDENTICAL fields -> SKIP, returns ("SKIPPED", existing_model)
        3. In DB with CONFLICTING geometry -> RAISES MigrationConflictError (aborts transaction)

        When deduplicate_structural=True (default for live ingestion), if an alert for this
        exact structural pattern (pattern_id) has already been inserted, returns ("SKIPPED", existing_model).
        """
        existing = await self.get_by_physical_identity(
            symbol=alert.symbol,
            timeframe=alert.timeframe,
            pattern_type=alert.pattern_type,
            breakout_candle_timestamp=alert.breakout_candle_timestamp,
        )

        incoming_data = alert.model_dump()

        if existing is None:
            # Check if this structural pattern has already broken out in the database
            if deduplicate_structural:
                conds = [
                    (MWBreakoutAlertModel.s1_timestamp == alert.s1_timestamp) & (MWBreakoutAlertModel.neckline_timestamp == alert.neckline_timestamp)
                ]
                if alert.pattern_id:
                    conds.append(MWBreakoutAlertModel.pattern_id == alert.pattern_id)
                stmt_structural = select(MWBreakoutAlertModel).where(
                    MWBreakoutAlertModel.symbol == alert.symbol,
                    MWBreakoutAlertModel.timeframe == alert.timeframe,
                    MWBreakoutAlertModel.pattern_type == alert.pattern_type,
                    or_(*conds)
                ).order_by(MWBreakoutAlertModel.breakout_candle_timestamp.asc())
                res_structural = await self.session.execute(stmt_structural)
                existing_structural = res_structural.scalars().first()
                if existing_structural is not None:
                    return "SKIPPED", existing_structural

            new_model = MWBreakoutAlertModel(**incoming_data)
            self.session.add(new_model)
            await self.session.flush()
            return "INSERTED", new_model

        # Identity already exists: verify field parity across critical geometric properties
        existing_data = {
            col.name: getattr(existing, col.name)
            for col in existing.__table__.columns
        }
        diffs = {}
        for field, in_val in incoming_data.items():
            ex_val = existing_data.get(field)
            if isinstance(in_val, float) and isinstance(ex_val, (float, int)):
                if abs(in_val - float(ex_val)) > 1e-5:
                    diffs[field] = {"incoming": in_val, "existing": ex_val}
            elif in_val != ex_val:
                diffs[field] = {"incoming": in_val, "existing": ex_val}

        if diffs:
            identity_str = (
                f"(symbol={alert.symbol}, timeframe={alert.timeframe}, "
                f"pattern_type={alert.pattern_type}, timestamp={alert.breakout_candle_timestamp})"
            )
            msg = (
                f"Migration conflict detected for physical breakout identity {identity_str}. "
                f"alert_id='{alert.alert_id}'. "
                f"Conflicting fields: {diffs}. "
                f"Aborting to protect existing historical record."
            )
            logger.error(msg)
            raise MigrationConflictError(msg)

        return "SKIPPED", existing

    async def migrate_single_alert_safe(
        self,
        alert: MWBreakoutAlert,
    ) -> Tuple[str, MWBreakoutAlertModel]:
        """Backward-compatible alias for ingest_alert_safe preserving lossless historical migration."""
        return await self.ingest_alert_safe(alert, deduplicate_structural=False)

    async def get_active_alerts(
        self,
        symbol: Optional[str] = None,
    ) -> List[MWBreakoutAlertModel]:
        """
        Queries only active/open trades from the database for lifecycle evaluation.
        Never scans terminal outcomes (TARGET 2 HIT, SL HIT).
        """
        active_statuses = ["TARGET OPEN", "ACTIVE", "TARGET 1 HIT", "TARGET_1_HIT"]
        stmt = select(MWBreakoutAlertModel).where(
            MWBreakoutAlertModel.status.in_(active_statuses)
        )
        if symbol:
            sym_clean = symbol.strip().upper()
            stmt = stmt.where(func.upper(MWBreakoutAlertModel.symbol) == sym_clean)

        stmt = stmt.order_by(
            MWBreakoutAlertModel.breakout_candle_timestamp.desc(),
            MWBreakoutAlertModel.alert_id.desc(),
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def update_alert_status(
        self,
        alert_id: str,
        new_status: str,
        outcome_timestamp: Optional[str] = None,
    ) -> bool:
        """
        Updates trade status and outcome timestamp in SQLite atomically,
        strictly enforcing terminal outcome immutability:
        - TARGET 2 HIT and SL HIT are final and can never be reverted.
        - TARGET 1 HIT locks trade as winner and can never revert to SL HIT.
        Returns True if updated, False if skipped/blocked.
        """
        model = await self.get_by_id(alert_id)
        if not model:
            return False

        cur_status = (model.status or "").upper()
        target_status = (new_status or "").upper()

        # Terminal outcomes are immutable
        if cur_status in ["TARGET 2 HIT", "TARGET_2_HIT", "SL HIT", "SL_HIT", "INVALIDATED"]:
            return False

        # TARGET 1 HIT locks winner: cannot revert to SL HIT
        if cur_status in ["TARGET 1 HIT", "TARGET_1_HIT"] and target_status in ["SL HIT", "SL_HIT", "INVALIDATED"]:
            return False

        model.status = new_status
        if outcome_timestamp:
            model.outcome_timestamp = outcome_timestamp
        await self.session.flush()
        return True

    async def update_alert_geometry(
        self,
        alert_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """
        Updates canonical pattern geometry / scoring from chart synchronization,
        without overwriting terminal outcomes.
        """
        model = await self.get_by_id(alert_id)
        if not model:
            return False

        allowed_keys = {
            "s1_price", "s1_timestamp", "s2_price", "s2_timestamp",
            "neckline_price", "neckline_timestamp", "pattern_height",
            "breakout_open", "breakout_high", "breakout_low", "breakout_close",
            "measured_target", "target_2", "invalidation_level",
            "nearest_support", "nearest_resistance", "quality_score",
            "quality_breakdown", "reversal_score", "trendline_score", "ema_score",
            "reversal_points", "trendline_points", "ema_points", "trade_quality",
            "entry_status", "outcome_timestamp",
        }
        for k, v in updates.items():
            if k in allowed_keys and hasattr(model, k):
                setattr(model, k, v)
        await self.session.flush()
        return True

    async def get_alert_by_flexible_id(
        self,
        target_id: str,
    ) -> Optional[MWBreakoutAlertModel]:
        """
        Retrieves a single historical alert by unique alert_id or pattern_id.
        Supports exact match, URL-decoded match, and normalized slash/colon variants.
        """
        if not target_id:
            return None

        decoded = urllib.parse.unquote(target_id)

        # 1. Exact match by alert_id or pattern_id
        stmt = select(MWBreakoutAlertModel).where(
            or_(
                MWBreakoutAlertModel.alert_id == target_id,
                MWBreakoutAlertModel.alert_id == decoded,
                MWBreakoutAlertModel.pattern_id == target_id,
                MWBreakoutAlertModel.pattern_id == decoded,
            )
        )
        res = await self.session.execute(stmt)
        found = res.scalars().first()
        if found:
            return found

        # 2. Normalized slash vs underscore and colon match
        norm_target = target_id.replace("/", "_").replace("%2F", "_").replace("%2f", "_").replace(":", "-")
        norm_decoded = decoded.replace("/", "_").replace(":", "-")

        norm_col = func.replace(func.replace(MWBreakoutAlertModel.alert_id, "/", "_"), ":", "-")
        stmt2 = select(MWBreakoutAlertModel).where(
            or_(
                norm_col == norm_target,
                norm_col == norm_decoded,
            )
        )
        res2 = await self.session.execute(stmt2)
        return res2.scalars().first()

    async def get_paginated_alerts(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        pattern_type: Optional[str] = None,
        status: Optional[str] = None,
        date_filter: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Tuple[List[MWBreakoutAlert], int, int, bool, bool]:
        """
        Database-backed chronological pagination.
        Sorts strictly by breakout_candle_timestamp DESC, alert_id DESC.
        Returns: (items, total_count, total_pages, has_next, has_previous).
        """
        stmt = select(MWBreakoutAlertModel)
        count_stmt = select(func.count()).select_from(MWBreakoutAlertModel)

        # Filter: Symbol (handles slash, hyphen, underscore, spaces seamlessly)
        if symbol:
            sym_clean = symbol.strip().upper().replace("/", "").replace("-", "").replace(" ", "").replace("_", "")
            norm_sym = func.replace(
                func.replace(
                    func.replace(
                        func.replace(func.upper(MWBreakoutAlertModel.symbol), "/", ""),
                        "-", ""
                    ),
                    " ", ""
                ),
                "_", ""
            )
            norm_tkr = func.replace(
                func.replace(
                    func.replace(
                        func.replace(func.upper(MWBreakoutAlertModel.ticker), "/", ""),
                        "-", ""
                    ),
                    " ", ""
                ),
                "_", ""
            )
            sym_cond = norm_sym.like(f"%{sym_clean}%") | norm_tkr.like(f"%{sym_clean}%")
            stmt = stmt.where(sym_cond)
            count_stmt = count_stmt.where(sym_cond)

        # Filter: Timeframe
        if timeframe and timeframe.upper() != "ALL":
            tf_cond = func.upper(MWBreakoutAlertModel.timeframe) == timeframe.upper()
            stmt = stmt.where(tf_cond)
            count_stmt = count_stmt.where(tf_cond)

        # Filter: Pattern Type
        if pattern_type and pattern_type.upper() != "ALL":
            pt_cond = func.upper(MWBreakoutAlertModel.pattern_type) == pattern_type.upper()
            stmt = stmt.where(pt_cond)
            count_stmt = count_stmt.where(pt_cond)

        # Filter: Status
        if status and status.upper() != "ALL":
            st_clean = status.strip().upper()
            if st_clean == "COMPLETED":
                st_cond = MWBreakoutAlertModel.status.in_(["TARGET 1 HIT", "TARGET 2 HIT", "TARGET_1_HIT", "TARGET_2_HIT"])
            elif st_clean in ["ACTIVE", "TARGET OPEN", "OPEN"]:
                st_cond = MWBreakoutAlertModel.status.in_(["TARGET OPEN", "ACTIVE"])
            elif st_clean in ["INVALIDATED", "SL HIT", "SL_HIT"]:
                st_cond = MWBreakoutAlertModel.status.in_(["SL HIT", "INVALIDATED"])
            elif st_clean in ["TARGET 1 HIT", "TARGET_1_HIT"]:
                st_cond = MWBreakoutAlertModel.status.in_(["TARGET 1 HIT", "TARGET_1_HIT"])
            elif st_clean in ["TARGET 2 HIT", "TARGET_2_HIT"]:
                st_cond = MWBreakoutAlertModel.status.in_(["TARGET 2 HIT", "TARGET_2_HIT"])
            else:
                st_cond = func.upper(MWBreakoutAlertModel.status) == st_clean
            stmt = stmt.where(st_cond)
            count_stmt = count_stmt.where(st_cond)

        # Filter: Date Filter
        if date_filter and date_filter.lower() not in ["all", "latest"]:
            now = datetime.now(timezone.utc)
            if date_filter.lower() == "today":
                today_str = now.isoformat()[:10]
                df_cond = MWBreakoutAlertModel.breakout_candle_timestamp.like(f"{today_str}%")
            elif date_filter.lower() in ["24h", "last 24 hours"]:
                cutoff = (now - timedelta(hours=24)).isoformat()
                df_cond = MWBreakoutAlertModel.breakout_candle_timestamp >= cutoff
            elif date_filter.lower() in ["7d", "last 7 days"]:
                cutoff = (now - timedelta(days=7)).isoformat()
                df_cond = MWBreakoutAlertModel.breakout_candle_timestamp >= cutoff
            else:
                df_cond = None

            if df_cond is not None:
                stmt = stmt.where(df_cond)
                count_stmt = count_stmt.where(df_cond)

        # Execute total count
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one()

        page = max(1, page)
        limit = max(1, limit)
        total_pages = max(1, (total + limit - 1) // limit)
        offset = (page - 1) * limit

        # Order chronologically newest first
        stmt = (
            stmt.order_by(
                MWBreakoutAlertModel.breakout_candle_timestamp.desc(),
                MWBreakoutAlertModel.alert_id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        res = await self.session.execute(stmt)
        models = res.scalars().all()
        items = [m.to_schema() for m in models]

        has_next = page < total_pages
        has_previous = page > 1

        return items, total, total_pages, has_next, has_previous

    async def get_summary_stats(self) -> Dict[str, int]:
        """
        Calculates summary statistics directly via database-level aggregation.
        Matches exact dictionary schema expected by the frontend.
        """
        stmt = select(
            func.count(MWBreakoutAlertModel.alert_id).label("total_count"),
            func.sum(case((MWBreakoutAlertModel.pattern_type == "W", 1), else_=0)).label("w_breakouts"),
            func.sum(case((MWBreakoutAlertModel.pattern_type == "M", 1), else_=0)).label("m_breakdowns"),
            func.sum(case((MWBreakoutAlertModel.status.in_(["TARGET OPEN", "ACTIVE"]), 1), else_=0)).label("active_count"),
            func.sum(case((MWBreakoutAlertModel.status.in_(["TARGET 1 HIT", "TARGET 2 HIT", "TARGET_1_HIT", "TARGET_2_HIT"]), 1), else_=0)).label("target_hit_count"),
            func.sum(case((MWBreakoutAlertModel.status.in_(["SL HIT", "INVALIDATED"]), 1), else_=0)).label("invalidated_count"),
            func.sum(case((MWBreakoutAlertModel.read.is_(False) | MWBreakoutAlertModel.read.is_(None), 1), else_=0)).label("unread_count"),
        )
        res = await self.session.execute(stmt)
        row = res.one_or_none()
        if not row:
            return {
                "w_breakouts": 0,
                "m_breakdowns": 0,
                "active_count": 0,
                "target_hit_count": 0,
                "invalidated_count": 0,
                "unread_count": 0,
                "total_count": 0,
            }
        return {
            "w_breakouts": int(row.w_breakouts or 0),
            "m_breakdowns": int(row.m_breakdowns or 0),
            "active_count": int(row.active_count or 0),
            "target_hit_count": int(row.target_hit_count or 0),
            "invalidated_count": int(row.invalidated_count or 0),
            "unread_count": int(row.unread_count or 0),
            "total_count": int(row.total_count or 0),
        }

    async def mark_all_read(self) -> int:
        """Marks all unread alerts as read in SQLite."""
        stmt = update(MWBreakoutAlertModel).where(
            or_(MWBreakoutAlertModel.read.is_(False), MWBreakoutAlertModel.read.is_(None))
        ).values(read=True)
        res = await self.session.execute(stmt)
        await self.session.flush()
        return res.rowcount

    async def clear_all_alerts(self) -> int:
        """Clears all alerts from the database."""
        stmt = delete(MWBreakoutAlertModel)
        res = await self.session.execute(stmt)
        await self.session.flush()
        return res.rowcount

    async def get_metrics(self) -> Dict[str, Any]:
        """Calculates comprehensive audit metrics directly from database."""
        total = await self.session.scalar(select(func.count(MWBreakoutAlertModel.alert_id))) or 0
        w_count = await self.session.scalar(
            select(func.count(MWBreakoutAlertModel.alert_id)).where(MWBreakoutAlertModel.pattern_type == "W")
        ) or 0
        m_count = await self.session.scalar(
            select(func.count(MWBreakoutAlertModel.alert_id)).where(MWBreakoutAlertModel.pattern_type == "M")
        ) or 0

        earliest = await self.session.scalar(
            select(func.min(MWBreakoutAlertModel.breakout_candle_timestamp))
        )
        latest = await self.session.scalar(
            select(func.max(MWBreakoutAlertModel.breakout_candle_timestamp))
        )

        unique_identities = await self.session.scalar(
            select(
                func.count(
                    func.distinct(
                        MWBreakoutAlertModel.symbol
                        + "||"
                        + MWBreakoutAlertModel.timeframe
                        + "||"
                        + MWBreakoutAlertModel.pattern_type
                        + "||"
                        + MWBreakoutAlertModel.breakout_candle_timestamp
                    )
                )
            )
        ) or 0

        return {
            "total_count": total,
            "w_count": w_count,
            "m_count": m_count,
            "unique_identities": unique_identities,
            "duplicate_identities": total - unique_identities,
            "earliest_timestamp": earliest,
            "latest_timestamp": latest,
        }


class StructureNotificationRepository:
    """
    Dedicated database repository for persistent structure and trendline notifications.
    Enforces lossless persistence, unique constraint enforcement on (symbol, timeframe, event_type, timestamp, direction),
    and fast index-backed retrieval.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_physical_identity(
        self,
        symbol: str,
        timeframe: str,
        event_type: str,
        timestamp: str,
        direction: Optional[str] = None,
    ) -> Optional[StructureNotificationModel]:
        """Finds a notification by its unique physical event identity."""
        stmt = select(StructureNotificationModel).where(
            StructureNotificationModel.symbol == symbol,
            StructureNotificationModel.timeframe == timeframe,
            StructureNotificationModel.event_type == event_type,
            StructureNotificationModel.timestamp == timestamp,
            StructureNotificationModel.direction == direction,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_id(self, notif_id: str) -> Optional[StructureNotificationModel]:
        """Finds a notification by its primary key ID."""
        stmt = select(StructureNotificationModel).where(
            StructureNotificationModel.id == notif_id
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def save_notification(
        self,
        notif: AlertNotification,
    ) -> Tuple[bool, StructureNotificationModel]:
        """
        Saves a structure notification idempotently.
        If notification already exists by (symbol, timeframe, event_type, timestamp, direction) or id:
            returns (False, existing_model).
        Otherwise:
            inserts new model and returns (True, new_model).
        """
        existing = await self.get_by_physical_identity(
            symbol=notif.symbol,
            timeframe=notif.timeframe,
            event_type=notif.event_type,
            timestamp=notif.timestamp,
            direction=notif.direction,
        )
        if existing is not None:
            return False, existing

        if notif.id:
            existing_by_id = await self.get_by_id(notif.id)
            if existing_by_id is not None:
                return False, existing_by_id

        model = StructureNotificationModel.from_schema(notif)
        self.session.add(model)
        try:
            await self.session.flush()
            return True, model
        except Exception:
            await self.session.rollback()
            existing = await self.get_by_physical_identity(
                symbol=notif.symbol,
                timeframe=notif.timeframe,
                event_type=notif.event_type,
                timestamp=notif.timestamp,
                direction=notif.direction,
            )
            if existing is not None:
                return False, existing
            raise

    async def get_seen_event_ids(self) -> Set[str]:
        """Returns set of all notification IDs and composite event keys for fast in-memory deduplication."""
        stmt = select(
            StructureNotificationModel.id,
            StructureNotificationModel.symbol,
            StructureNotificationModel.timeframe,
            StructureNotificationModel.event_type,
            StructureNotificationModel.timestamp,
            StructureNotificationModel.direction,
        )
        res = await self.session.execute(stmt)
        seen: Set[str] = set()
        for row in res.all():
            notif_id, sym, tf, evt, ts, direct = row
            seen.add(notif_id)
            if notif_id.startswith("alert_"):
                seen.add(notif_id[6:])
            seen.add(f"{sym}_{tf}_{evt}_{ts}_{direct}")
        return seen

    async def get_recent_notifications(self, limit: int = 100) -> List[AlertNotification]:
        """Returns most recent structure notifications sorted chronologically descending."""
        stmt = (
            select(StructureNotificationModel)
            .order_by(
                StructureNotificationModel.timestamp.desc(),
                StructureNotificationModel.created_at.desc()
            )
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        models = res.scalars().all()
        return [m.to_schema() for m in models]

    async def get_paginated_notifications(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        event_type: Optional[str] = None,
        touch_class: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Tuple[List[AlertNotification], int, int, bool, bool]:
        """Returns paginated notifications with count and paging navigation flags."""
        base_query = select(StructureNotificationModel)
        count_query = select(func.count(StructureNotificationModel.id))

        filters = []
        if symbol and symbol.upper() != "ALL":
            filters.append(StructureNotificationModel.symbol.ilike(symbol))
        if timeframe:
            filters.append(StructureNotificationModel.timeframe == timeframe)
        if event_type and event_type.upper() != "ALL":
            filters.append(StructureNotificationModel.event_type == event_type)
        if touch_class and touch_class.upper() != "ALL":
            filters.append(StructureNotificationModel.touch_class == touch_class)

        if filters:
            base_query = base_query.where(*filters)
            count_query = count_query.where(*filters)

        total_res = await self.session.execute(count_query)
        total_count = total_res.scalar() or 0

        page = max(1, page)
        limit = max(1, min(limit, 200))
        offset = (page - 1) * limit
        total_pages = max(1, (total_count + limit - 1) // limit) if total_count > 0 else 1

        items_stmt = (
            base_query.order_by(
                StructureNotificationModel.timestamp.desc(),
                StructureNotificationModel.created_at.desc()
            )
            .offset(offset)
            .limit(limit)
        )
        res = await self.session.execute(items_stmt)
        models = res.scalars().all()

        has_next = page < total_pages
        has_prev = page > 1

        return [m.to_schema() for m in models], total_count, total_pages, has_next, has_prev

    async def mark_all_read(self) -> int:
        """Marks all structure notifications as read."""
        stmt = update(StructureNotificationModel).where(
            or_(StructureNotificationModel.read.is_(False), StructureNotificationModel.read.is_(None))
        ).values(read=True)
        res = await self.session.execute(stmt)
        await self.session.flush()
        return res.rowcount

    async def clear_all(self) -> int:
        """Clears all structure notifications."""
        stmt = delete(StructureNotificationModel)
        res = await self.session.execute(stmt)
        await self.session.flush()
        return res.rowcount

    async def get_metrics(self) -> Dict[str, Any]:
        """Calculates audit metrics for structure notifications dynamically from SQLite."""
        total = await self.session.scalar(select(func.count(StructureNotificationModel.id))) or 0
        touch2_count = await self.session.scalar(
            select(func.count(StructureNotificationModel.id)).where(StructureNotificationModel.touch_class == "2-TOUCH")
        ) or 0
        touch3_count = await self.session.scalar(
            select(func.count(StructureNotificationModel.id)).where(StructureNotificationModel.touch_class == "3-TOUCH")
        ) or 0
        earliest = await self.session.scalar(select(func.min(StructureNotificationModel.timestamp)))
        latest = await self.session.scalar(select(func.max(StructureNotificationModel.timestamp)))

        return {
            "total_count": total,
            "2_touch_count": touch2_count,
            "3_touch_count": touch3_count,
            "earliest_timestamp": earliest,
            "latest_timestamp": latest,
        }


class CheckpointRepository:
    """
    Dedicated database repository for persistent processing checkpoints per (symbol, timeframe).
    Guarantees atomic updates, retrieval, and crash recovery.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_checkpoint(self, symbol: str, timeframe: str) -> Optional[ProcessingCheckpointModel]:
        stmt = select(ProcessingCheckpointModel).where(
            ProcessingCheckpointModel.symbol == symbol,
            ProcessingCheckpointModel.timeframe == timeframe
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_all_checkpoints(self) -> List[ProcessingCheckpointModel]:
        stmt = select(ProcessingCheckpointModel).order_by(
            ProcessingCheckpointModel.symbol,
            ProcessingCheckpointModel.timeframe
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def update_checkpoint(
        self,
        symbol: str,
        timeframe: str,
        last_candle_timestamp: str,
        processed_count: int = 0,
        status: str = "SYNCED"
    ) -> ProcessingCheckpointModel:
        now_str = datetime.now(timezone.utc).isoformat()
        existing = await self.get_checkpoint(symbol, timeframe)
        if existing:
            existing.last_processed_candle_timestamp = last_candle_timestamp
            existing.last_processed_at = now_str
            existing.candles_processed_count += processed_count
            existing.checkpoint_status = status
            await self.session.flush()
            return existing
        else:
            model = ProcessingCheckpointModel(
                symbol=symbol,
                timeframe=timeframe,
                last_processed_candle_timestamp=last_candle_timestamp,
                last_processed_at=now_str,
                candles_processed_count=processed_count,
                checkpoint_status=status
            )
            self.session.add(model)
            await self.session.flush()
            return model

    # Synchronous helpers using sqlite3 for zero-overhead background operations
    @staticmethod
    def get_checkpoint_sync(symbol: str, timeframe: str) -> Optional[ProcessingCheckpoint]:
        try:
            import sqlite3
            from app.db.database import get_database_path
            db_path = get_database_path()
            if not db_path.exists():
                return None
            with sqlite3.connect(str(db_path), timeout=10.0) as conn:
                conn.execute("PRAGMA busy_timeout = 5000;")
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT symbol, timeframe, last_processed_candle_timestamp,
                           last_processed_at, candles_processed_count, checkpoint_status
                    FROM processing_checkpoints
                    WHERE symbol = ? AND timeframe = ?
                    LIMIT 1
                    """,
                    (symbol, timeframe)
                )
                row = cursor.fetchone()
                if row:
                    return ProcessingCheckpoint(**dict(row))
        except Exception as e:
            logger.warning(f"[CheckpointRepo] get_checkpoint_sync error for {symbol} {timeframe}: {e}")
        return None

    @staticmethod
    def get_all_checkpoints_sync() -> List[ProcessingCheckpoint]:
        try:
            import sqlite3
            from app.db.database import get_database_path
            db_path = get_database_path()
            if not db_path.exists():
                return []
            with sqlite3.connect(str(db_path), timeout=10.0) as conn:
                conn.execute("PRAGMA busy_timeout = 5000;")
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT symbol, timeframe, last_processed_candle_timestamp,
                           last_processed_at, candles_processed_count, checkpoint_status
                    FROM processing_checkpoints
                    ORDER BY symbol, timeframe
                    """
                )
                rows = cursor.fetchall()
                return [ProcessingCheckpoint(**dict(r)) for r in rows]
        except Exception as e:
            logger.warning(f"[CheckpointRepo] get_all_checkpoints_sync error: {e}")
        return []

    @staticmethod
    def update_checkpoint_sync(
        symbol: str,
        timeframe: str,
        last_candle_timestamp: str,
        processed_count: int = 0,
        status: str = "SYNCED"
    ) -> bool:
        try:
            import sqlite3
            from app.db.database import get_database_path
            db_path = get_database_path()
            if not db_path.exists():
                return False
            now_str = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(str(db_path), timeout=10.0) as conn:
                conn.execute("PRAGMA busy_timeout = 5000;")
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO processing_checkpoints (
                        symbol, timeframe, last_processed_candle_timestamp,
                        last_processed_at, candles_processed_count, checkpoint_status
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, timeframe) DO UPDATE SET
                        last_processed_candle_timestamp = excluded.last_processed_candle_timestamp,
                        last_processed_at = excluded.last_processed_at,
                        candles_processed_count = processing_checkpoints.candles_processed_count + excluded.candles_processed_count,
                        checkpoint_status = excluded.checkpoint_status;
                    """,
                    (symbol, timeframe, last_candle_timestamp, now_str, processed_count, status)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.warning(f"[CheckpointRepo] update_checkpoint_sync error for {symbol} {timeframe}: {e}")
            return False
