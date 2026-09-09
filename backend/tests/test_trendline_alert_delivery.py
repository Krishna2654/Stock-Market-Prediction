import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import text, select, func

from app.models.schemas import (
    AlertRule,
    AlertNotification,
    StructureBreakEvent,
    MultiTimeframeSynthesis,
    SingleTimeframeAnalysis,
    EvidenceScoreBreakdown,
    TechnicalIndicators,
    SupportResistanceSummary,
)
from app.alerts.engine import AlertEngine
from app.db.database import create_engine_and_sessionmaker, init_db
from app.db.models import StructureNotificationModel, MWBreakoutAlertModel
from app.db.repository import StructureNotificationRepository, MWAlertRepository


def make_synthesis(
    events_15m,
    macro_score: int = 85,
    symbol: str = "NIFTY 50",
    candle_count: int = 50,
    latest_time: str = "2026-08-25T11:00:00+05:30"
):
    score = EvidenceScoreBreakdown(
        total_score=macro_score,
        category="Strong Evidence Alignment" if macro_score >= 80 else "Mixed Evidence",
        structure_points=25,
        htf_alignment_points=20,
        momentum_points=15,
        volume_points=10,
        breakout_points=10,
        details=["Analysis"]
    )
    analysis_15m = SingleTimeframeAnalysis(
        timeframe="15M",
        trend="BULLISH",
        structure_type="BULLISH",
        swings=[],
        recent_events=events_15m,
        support_resistance=SupportResistanceSummary(
            all_levels=[],
            major_support=24000.0,
            minor_support=24100.0,
            minor_resistance=24300.0,
            major_resistance=24400.0,
            current_price=24250.0
        ),
        trendlines=[],
        indicators=TechnicalIndicators(
            rsi_14=62.0,
            ema_20=24180.0,
            relative_volume=1.45,
            atr_14=20.0
        ),
        breakout_status="CONFIRMED BREAKOUT",
        candle_count=candle_count,
        latest_candle_time=latest_time
    )
    return MultiTimeframeSynthesis(
        symbol=symbol,
        ticker="^NSEI",
        provider="yfinance",
        data_status="LIVE",
        last_updated=datetime.now(timezone.utc).isoformat(),
        is_stale=False,
        status_message="Live feed",
        current_price=24250.0,
        timeframes={"15M": analysis_15m},
        overall_bias="BULLISH",
        current_state="FULL BULLISH ALIGNMENT",
        evidence_score=score,
        confirmation_state="HIGH",
        short_term_state="EXPANDING",
        key_supports=[24000.0, 24100.0],
        key_resistances=[24300.0, 24400.0],
        synthesis_rationale="Bullish breakout"
    )


def test_2touch_trendline_breakout_reaches_alert_engine():
    """Requirement 1: Valid 2-touch trendline breakout reaches AlertEngine."""
    engine = AlertEngine()
    engine.clear_notifications()

    event_2t = StructureBreakEvent(
        id="test_nifty_2t_1",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T11:00:00+05:30",
        event_type="TREND_LINE_BREAK",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=75,
        notes="2-TOUCH TRENDLINE BREAK — BULLISH | PRIMARY intermediate descending resistance broken"
    )

    synthesis = make_synthesis([event_2t], macro_score=70)
    alerts = engine.process_synthesis_for_alerts(synthesis)

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.touch_class == "2-TOUCH"
    assert alert.evidence_score == 75
    assert "2-TOUCH" in alert.message
    assert alert.direction == "BULLISH"
    assert alert.price == 24250.0


def test_3touch_trendline_breakout_reaches_alert_engine():
    """Requirement 2: Valid 3-touch trendline breakout reaches AlertEngine."""
    engine = AlertEngine()
    engine.clear_notifications()

    event_3t = StructureBreakEvent(
        id="test_nifty_3t_1",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T11:00:00+05:30",
        event_type="TREND_LINE_BREAK",
        direction="BEARISH",
        broken_level=24300.0,
        break_price=24220.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BEARISH",
        evidence_score=90,
        notes="3-TOUCH TRENDLINE BREAK — BEARISH | PRIMARY intermediate ascending support broken"
    )

    synthesis = make_synthesis([event_3t], macro_score=65)
    alerts = engine.process_synthesis_for_alerts(synthesis)

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.touch_class == "3-TOUCH"
    assert alert.evidence_score == 90
    assert "⭐ 3-TOUCH" in alert.message
    assert alert.direction == "BEARISH"
    assert alert.price == 24220.0


def test_3touch_not_rejected_when_macro_synthesis_score_below_80():
    """Requirement 3: 3-touch event is not rejected solely because overall synthesis score < 80."""
    engine = AlertEngine()
    engine.clear_notifications()

    event_3t = StructureBreakEvent(
        id="test_macro_low_score_1",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T11:00:00+05:30",
        event_type="TREND_LINE_BREAK",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24260.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=90,
        notes="3-TOUCH TRENDLINE BREAK — BULLISH"
    )

    # Synthesis macro score is only 55 (choppy / neutral market)
    synthesis = make_synthesis([event_3t], macro_score=55)
    alerts = engine.process_synthesis_for_alerts(synthesis)

    assert len(alerts) == 1
    assert alerts[0].evidence_score == 90
    assert alerts[0].touch_class == "3-TOUCH"


def test_2touch_and_3touch_confidence_distinction_under_stricter_rule():
    """Requirement 4: Preserves 2-touch vs 3-touch confidence distinction under user rules."""
    engine = AlertEngine()
    engine.clear_notifications()

    # Configure custom strict rule requiring min_evidence_score = 85
    strict_rule = AlertRule(
        id="custom-strict-rule",
        symbol="ALL",
        timeframes=["15M"],
        event_types=["TREND_LINE_BREAK"],
        min_evidence_score=85,
        is_enabled=True,
        created_at=datetime.now(timezone.utc).isoformat()
    )
    engine.add_rule(strict_rule)

    event_2t = StructureBreakEvent(
        id="test_gated_2t",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T11:00:00+05:30",
        event_type="TREND_LINE_BREAK",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=75,
        notes="2-TOUCH TRENDLINE BREAK — BULLISH"
    )

    event_3t = StructureBreakEvent(
        id="test_gated_3t",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T11:00:00+05:30",
        event_type="TREND_LINE_BREAK",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=90,
        notes="3-TOUCH TRENDLINE BREAK — BULLISH"
    )

    # 2-touch has evidence_score 75 < 85 -> rejected
    synthesis_2t = make_synthesis([event_2t])
    alerts_2t = engine.process_synthesis_for_alerts(synthesis_2t)
    assert len(alerts_2t) == 0

    # 3-touch has evidence_score 90 >= 85 -> accepted
    synthesis_3t = make_synthesis([event_3t])
    alerts_3t = engine.process_synthesis_for_alerts(synthesis_3t)
    assert len(alerts_3t) == 1
    assert alerts_3t[0].touch_class == "3-TOUCH"


def test_event_deduplication_across_repeated_evaluations():
    """Requirement 5 & 6: Deterministic deduplication across multiple cycles."""
    engine = AlertEngine()
    engine.clear_notifications()

    event = StructureBreakEvent(
        id="test_dedupe_tl_1",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T11:00:00+05:30",
        event_type="TREND_LINE_BREAK",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=90,
        notes="3-TOUCH TRENDLINE BREAK — BULLISH"
    )

    synthesis = make_synthesis([event])

    pass1 = engine.process_synthesis_for_alerts(synthesis)
    assert len(pass1) == 1

    pass2 = engine.process_synthesis_for_alerts(synthesis)
    assert len(pass2) == 0

    pass3 = engine.process_synthesis_for_alerts(synthesis)
    assert len(pass3) == 0

    assert len(engine.get_notifications()) == 1


def test_startup_flood_protection_skips_older_historical_breaks():
    """Requirement 7: Startup protection ignores breaks beyond active window."""
    engine = AlertEngine()
    engine.clear_notifications()

    # Event occurred at index 10 in a 50-candle series (40 candles ago)
    ancient_event = StructureBreakEvent(
        id="ancient_break_1",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-20T10:00:00+05:30",
        event_type="TREND_LINE_BREAK",
        direction="BULLISH",
        broken_level=24000.0,
        break_price=24050.0,
        break_candle_index=10,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=90,
        notes="3-TOUCH TRENDLINE BREAK — BULLISH"
    )

    synthesis = make_synthesis([ancient_event], candle_count=50)
    alerts = engine.process_synthesis_for_alerts(synthesis)

    # Ancient historical break must NOT emit a live alert
    assert len(alerts) == 0
    # But it must be recorded in seen_event_ids to prevent future alerts
    assert "ancient_break_1" in engine.seen_event_ids


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    db_file = tmp_path / "test_structure.db"
    eng, sess_factory = create_engine_and_sessionmaker(db_file)
    await init_db(eng)
    yield eng, sess_factory
    await eng.dispose()


@pytest.mark.asyncio
async def test_structure_notifications_repository_persistence_and_unique_constraint(temp_db):
    """Requirement 8 & 9: Persistence in SQLite and database-level unique constraint."""
    _, sess_factory = temp_db

    async with sess_factory() as session:
        repo = StructureNotificationRepository(session)

        notif = AlertNotification(
            id="alert_test_persist_1",
            timestamp="2026-08-25T11:00:00+05:30",
            symbol="NIFTY 50",
            timeframe="15M",
            event_type="TREND_LINE_BREAK",
            direction="BULLISH",
            touch_class="3-TOUCH",
            message="🟢 ⭐ 3-TOUCH TRENDLINE BREAK",
            price=24250.0,
            level=24200.0,
            evidence_score=90,
            volume_confirmed=True,
            htf_alignment="BULLISH",
            read=False,
            created_at="2026-08-25T11:15:05+05:30"
        )

        inserted, model = await repo.save_notification(notif)
        await session.commit()
        assert inserted is True
        assert model.id == "alert_test_persist_1"
        assert model.touch_class == "3-TOUCH"

        # Attempt to insert identical physical identity
        dup_notif = AlertNotification(
            id="alert_test_persist_2_different_id",
            timestamp="2026-08-25T11:00:00+05:30",
            symbol="NIFTY 50",
            timeframe="15M",
            event_type="TREND_LINE_BREAK",
            direction="BULLISH",
            touch_class="3-TOUCH",
            message="Duplicate breakout attempt",
            price=24250.0,
            level=24200.0,
            evidence_score=90,
            volume_confirmed=True,
            htf_alignment="BULLISH",
            read=False,
            created_at="2026-08-25T11:16:00+05:30"
        )

        inserted_dup, existing_model = await repo.save_notification(dup_notif)
        assert inserted_dup is False
        assert existing_model.id == "alert_test_persist_1"

        # Query seen IDs
        seen = await repo.get_seen_event_ids()
        assert "alert_test_persist_1" in seen
        assert "test_persist_1" in seen

        # Paginated retrieval
        items, total, total_pages, has_next, has_prev = await repo.get_paginated_notifications(
            symbol="NIFTY 50", touch_class="3-TOUCH", page=1, limit=10
        )
        assert total == 1
        assert len(items) == 1
        assert items[0].id == "alert_test_persist_1"

        # Dynamic metrics
        metrics = await repo.get_metrics()
        assert metrics["total_count"] == 1
        assert metrics["3_touch_count"] == 1
        assert metrics["2_touch_count"] == 0


@pytest.mark.asyncio
async def test_notification_survives_backend_restart(tmp_path):
    """Requirement 10: Notification survives simulated backend restart."""
    import sqlite3
    db_file = tmp_path / "restart_test.db"
    eng, sess_factory = create_engine_and_sessionmaker(db_file)
    await init_db(eng)

    # Insert a notification using repository
    async with sess_factory() as session:
        repo = StructureNotificationRepository(session)
        notif = AlertNotification(
            id="alert_survive_1",
            timestamp="2026-08-25T11:00:00+05:30",
            symbol="BTC/USD",
            timeframe="1H",
            event_type="TREND_LINE_BREAK",
            direction="BEARISH",
            touch_class="3-TOUCH",
            message="🔴 ⭐ 3-TOUCH TRENDLINE BREAK — BTC/USD",
            price=62000.0,
            level=62500.0,
            evidence_score=90,
            volume_confirmed=True,
            htf_alignment="BEARISH",
            read=False,
            created_at="2026-08-25T11:00:05+05:30"
        )
        await repo.save_notification(notif)
        await session.commit()
    await eng.dispose()

    # Simulate fresh backend boot: monkeypatch database path to point to db_file
    import app.alerts.engine as engine_mod
    orig_get_path = engine_mod.get_database_path
    engine_mod.get_database_path = lambda: db_file

    try:
        fresh_engine = AlertEngine()
        # Verify notifications loaded from SQLite on boot
        notifs = fresh_engine.get_notifications()
        assert len(notifs) == 1
        assert notifs[0].id == "alert_survive_1"
        assert notifs[0].symbol == "BTC/USD"
        assert notifs[0].touch_class == "3-TOUCH"
        assert "alert_survive_1" in fresh_engine.seen_event_ids
    finally:
        engine_mod.get_database_path = orig_get_path


def test_production_sqlite_mw_alerts_history_intact():
    """Requirement 11: Production SQLite W/M alerts table remains intact with all history."""
    import sqlite3
    db_path = Path(__file__).resolve().parents[1] / "data" / "market_analyzer.db"
    if not db_path.exists():
        pytest.skip("Production DB not found")

    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM mw_breakout_alerts;")
        total_mw = cursor.fetchone()[0]
        # Must have historical W/M alerts intact
        assert total_mw > 0, "W/M alerts must not be empty"
