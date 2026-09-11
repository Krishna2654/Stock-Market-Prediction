from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)

from app.db.database import Base
from app.models.schemas import AlertNotification, MWBreakoutAlert, ProcessingCheckpoint


class MWBreakoutAlertModel(Base):
    """
    Persistent SQLAlchemy representation of MWBreakoutAlert.
    Enforces lossless representation of all 44 alert attributes and
    guarantees unique physical breakout identity via a composite constraint.
    """

    __tablename__ = "mw_breakout_alerts"

    # Primary key
    alert_id = Column(String, primary_key=True, index=True)

    # Core identification & taxonomy
    alert_type = Column(String, nullable=False)
    pattern_type = Column(String, nullable=False, index=True)
    direction = Column(String, nullable=False)
    symbol = Column(String, nullable=False, index=True)
    ticker = Column(String, nullable=False)
    timeframe = Column(String, nullable=False, index=True)
    pattern_id = Column(String, nullable=False, index=True)

    # Pattern geometry
    s1_price = Column(Float, nullable=False)
    s1_timestamp = Column(String, nullable=False)
    s2_price = Column(Float, nullable=False)
    s2_timestamp = Column(String, nullable=False)
    neckline_price = Column(Float, nullable=False)
    neckline_timestamp = Column(String, nullable=False)
    pattern_height = Column(Float, nullable=False)

    # Breakout candle exact metrics
    breakout_candle_timestamp = Column(String, nullable=False, index=True)
    breakout_open = Column(Float, nullable=False)
    breakout_high = Column(Float, nullable=False)
    breakout_low = Column(Float, nullable=False)
    breakout_close = Column(Float, nullable=False)

    # Confluence metrics
    trendline_price = Column(Float, nullable=False)
    ema20_price = Column(Float, nullable=False)
    volume = Column(Float, nullable=False, default=0.0)
    relative_volume = Column(Float, nullable=False, default=1.0)

    # Projections & Target Analysis
    measured_target = Column(Float, nullable=False)
    target_2 = Column(Float, nullable=False)
    nearest_support = Column(Float, nullable=True)
    nearest_resistance = Column(Float, nullable=True)
    invalidation_level = Column(Float, nullable=False)

    # Quality scoring & breakdown
    quality_score = Column(Integer, nullable=False)
    quality_breakdown = Column(JSON, nullable=False)
    reversal_score = Column(Integer, nullable=False, default=40)
    trendline_score = Column(Integer, nullable=False, default=0)
    ema_score = Column(Integer, nullable=False, default=0)
    reversal_points = Column(Integer, nullable=False, default=40)
    trendline_points = Column(Integer, nullable=False, default=0)
    ema_points = Column(Integer, nullable=False, default=0)

    # Lifecycle & status tracking
    status = Column(String, nullable=False, index=True, default="TARGET OPEN")
    trade_quality = Column(String, nullable=False, default="MEDIUM")
    entry_status = Column(String, nullable=False, default="VALID")
    outcome_timestamp = Column(String, nullable=True)
    stop_loss = Column(Float, nullable=True)
    event_created_at = Column(String, nullable=False)
    read = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        # 1. Physical Breakout Identity Unique Constraint
        UniqueConstraint(
            "symbol",
            "timeframe",
            "pattern_type",
            "breakout_candle_timestamp",
            name="uq_mw_breakout_identity",
        ),
        # 2. Chronological Ordering Index for unlimited newest-first pagination
        Index(
            "idx_mw_breakout_chronological",
            "breakout_candle_timestamp",
            "alert_id",
        ),
        # 3. Composite Filtering Index
        Index(
            "idx_mw_breakout_filter",
            "symbol",
            "timeframe",
            "status",
        ),
    )

    def to_schema(self) -> MWBreakoutAlert:
        """Converts the database model into the canonical Pydantic schema."""
        return MWBreakoutAlert(
            alert_id=self.alert_id,
            alert_type=self.alert_type,
            pattern_type=self.pattern_type,
            direction=self.direction,
            symbol=self.symbol,
            ticker=self.ticker,
            timeframe=self.timeframe,
            pattern_id=self.pattern_id,
            s1_price=self.s1_price,
            s1_timestamp=self.s1_timestamp,
            s2_price=self.s2_price,
            s2_timestamp=self.s2_timestamp,
            neckline_price=self.neckline_price,
            neckline_timestamp=self.neckline_timestamp,
            pattern_height=self.pattern_height,
            breakout_candle_timestamp=self.breakout_candle_timestamp,
            breakout_open=self.breakout_open,
            breakout_high=self.breakout_high,
            breakout_low=self.breakout_low,
            breakout_close=self.breakout_close,
            trendline_price=self.trendline_price,
            ema20_price=self.ema20_price,
            volume=self.volume,
            relative_volume=self.relative_volume,
            measured_target=self.measured_target,
            target_2=self.target_2,
            nearest_support=self.nearest_support,
            nearest_resistance=self.nearest_resistance,
            invalidation_level=self.invalidation_level,
            quality_score=self.quality_score,
            quality_breakdown=self.quality_breakdown or {},
            reversal_score=self.reversal_score,
            trendline_score=self.trendline_score,
            ema_score=self.ema_score,
            reversal_points=self.reversal_points,
            trendline_points=self.trendline_points,
            ema_points=self.ema_points,
            status=self.status,
            trade_quality=self.trade_quality,
            entry_status=self.entry_status,
            outcome_timestamp=self.outcome_timestamp,
            stop_loss=self.stop_loss,
            event_created_at=self.event_created_at,
            read=self.read,
        )

    @classmethod
    def from_schema(cls, alert: MWBreakoutAlert) -> "MWBreakoutAlertModel":
        """Instantiates a database model instance directly from a Pydantic schema."""
        d = alert.model_dump()
        return cls(**d)

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary representation of all stored fields."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class StructureNotificationModel(Base):
    """
    Persistent SQLAlchemy representation of structure break / trendline notifications.
    Ensures notifications survive backend restarts and provide an immutable audit trail.
    Enforces uniqueness at database level on (symbol, timeframe, event_type, timestamp, direction).
    """
    __tablename__ = "structure_notifications"

    id = Column(String, primary_key=True, index=True)
    timestamp = Column(String, nullable=False, index=True)  # Breakout candle timestamp
    symbol = Column(String, nullable=False, index=True)
    timeframe = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    direction = Column(String, nullable=True, index=True)
    touch_class = Column(String, nullable=True, index=True)  # "2-TOUCH", "3-TOUCH"
    message = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    level = Column(Float, nullable=False)
    evidence_score = Column(Integer, nullable=False)
    volume_confirmed = Column(Boolean, default=True)
    htf_alignment = Column(String, nullable=False)
    action_line_slope = Column(Float, nullable=True)
    action_line_intercept = Column(Float, nullable=True)
    safety_line_type = Column(String, nullable=True)
    safety_line_touches = Column(Integer, nullable=True)
    read = Column(Boolean, default=False)
    created_at = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "event_type", "timestamp", "direction",
            name="uq_structure_notification_event"
        ),
        Index("ix_structure_notif_sym_tf", "symbol", "timeframe"),
        Index("ix_structure_notif_timestamp", "timestamp"),
    )

    def to_schema(self) -> AlertNotification:
        return AlertNotification(
            id=self.id,
            timestamp=self.timestamp,
            symbol=self.symbol,
            timeframe=self.timeframe,
            event_type=self.event_type,
            direction=self.direction,
            touch_class=self.touch_class,
            message=self.message,
            price=self.price,
            level=self.level,
            evidence_score=self.evidence_score,
            volume_confirmed=self.volume_confirmed,
            htf_alignment=self.htf_alignment,
            action_line_slope=self.action_line_slope,
            action_line_intercept=self.action_line_intercept,
            safety_line_type=self.safety_line_type,
            safety_line_touches=self.safety_line_touches,
            read=self.read,
            created_at=self.created_at,
        )

    @classmethod
    def from_schema(cls, notif: AlertNotification) -> "StructureNotificationModel":
        d = notif.model_dump()
        if not d.get("created_at"):
            d["created_at"] = datetime.now(timezone.utc).isoformat()
        return cls(**d)

    def to_dict(self) -> Dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class ProcessingCheckpointModel(Base):
    """
    Persistent SQLAlchemy representation of processing checkpoints per (symbol, timeframe).
    Ensures missed-candle recovery can identify the exact last successfully processed
    completed candle across backend restarts or host sleep cycles.
    """
    __tablename__ = "processing_checkpoints"

    symbol = Column(String, primary_key=True, nullable=False)
    timeframe = Column(String, primary_key=True, nullable=False)
    last_processed_candle_timestamp = Column(String, nullable=False)
    last_processed_at = Column(String, nullable=False)
    candles_processed_count = Column(Integer, nullable=False, default=0)
    checkpoint_status = Column(String, nullable=False, default="SYNCED")  # "SYNCED", "RECOVERING"

    __table_args__ = (
        Index("ix_processing_checkpoints_lookup", "symbol", "timeframe"),
    )

    def to_schema(self) -> ProcessingCheckpoint:
        return ProcessingCheckpoint(
            symbol=self.symbol,
            timeframe=self.timeframe,
            last_processed_candle_timestamp=self.last_processed_candle_timestamp,
            last_processed_at=self.last_processed_at,
            candles_processed_count=self.candles_processed_count,
            checkpoint_status=self.checkpoint_status,
        )

    @classmethod
    def from_schema(cls, cp: ProcessingCheckpoint) -> "ProcessingCheckpointModel":
        return cls(**cp.model_dump())

    def to_dict(self) -> Dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
