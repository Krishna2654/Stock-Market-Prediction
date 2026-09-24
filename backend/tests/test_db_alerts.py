import hashlib
import json
import os
from pathlib import Path
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.database import Base, create_engine_and_sessionmaker, init_db
from app.db.models import MWBreakoutAlertModel
from app.db.repository import MigrationConflictError, MWAlertRepository
from app.models.schemas import MWBreakoutAlert

SOURCE_JSON_PATH = Path(__file__).resolve().parents[1] / "data" / "mw_breakout_alerts_store.json"


def get_json_sha256() -> str:
    with open(SOURCE_JSON_PATH, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


@pytest_asyncio.fixture
async def test_db(tmp_path):
    """Provides an isolated temporary SQLite database for testing."""
    db_file = tmp_path / "test_market_analyzer.db"
    eng, sess_factory = create_engine_and_sessionmaker(db_file)
    await init_db(eng)
    yield eng, sess_factory
    await eng.dispose()


@pytest.mark.asyncio
async def test_db_initialization_and_wal_mode(test_db):
    eng, _ = test_db
    async with eng.connect() as conn:
        res = await conn.execute(text("PRAGMA journal_mode;"))
        mode = res.scalar()
        assert str(mode).lower() == "wal", f"Expected WAL mode, got {mode}"

        res_sync = await conn.execute(text("PRAGMA synchronous;"))
        sync_mode = res_sync.scalar()
        # Normal is typically 1 in SQLite
        assert sync_mode in (1, "NORMAL", "1"), f"Expected synchronous NORMAL, got {sync_mode}"


@pytest.mark.asyncio
async def test_schema_and_physical_identity_constraint(test_db):
    _, sess_factory = test_db

    sample_alert_1 = MWBreakoutAlert(
        alert_id="mw_TEST_1",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="TEST_SYM",
        ticker="TEST-TKR",
        timeframe="5M",
        pattern_id="TEST_PAT_1",
        s1_price=100.0,
        s1_timestamp="2026-09-01T10:00:00+00:00",
        s2_price=101.0,
        s2_timestamp="2026-09-01T10:30:00+00:00",
        neckline_price=105.0,
        neckline_timestamp="2026-09-01T10:15:00+00:00",
        pattern_height=5.0,
        breakout_candle_timestamp="2026-09-01T10:45:00+00:00",
        breakout_open=104.5,
        breakout_high=106.0,
        breakout_low=104.0,
        breakout_close=105.5,
        trendline_price=105.0,
        ema20_price=104.0,
        measured_target=110.0,
        target_2=113.09,
        invalidation_level=100.25,
        quality_score=80,
        quality_breakdown={"reversal": 40, "trendline": 20, "ema": 20},
        status="TARGET OPEN",
        event_created_at="2026-09-01T10:46:00+00:00",
    )

    # Identical physical identity (TEST_SYM, 5M, W, 2026-09-01T10:45:00+00:00) but different alert_id
    sample_alert_duplicate = sample_alert_1.model_copy(update={"alert_id": "mw_TEST_DUPLICATE_ID"})

    async with sess_factory() as session:
        m1 = MWBreakoutAlertModel.from_schema(sample_alert_1)
        session.add(m1)
        await session.commit()

    # Attempting raw insertion of duplicate physical identity must raise IntegrityError
    async with sess_factory() as session:
        m2 = MWBreakoutAlertModel.from_schema(sample_alert_duplicate)
        session.add(m2)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_migrate_single_alert_safe_logic(test_db):
    _, sess_factory = test_db

    alert = MWBreakoutAlert(
        alert_id="mw_SAFE_1",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="SAFE_SYM",
        ticker="SAFE-TKR",
        timeframe="15M",
        pattern_id="SAFE_PAT_1",
        s1_price=200.0,
        s1_timestamp="2026-09-01T10:00:00+00:00",
        s2_price=201.0,
        s2_timestamp="2026-09-01T10:30:00+00:00",
        neckline_price=210.0,
        neckline_timestamp="2026-09-01T10:15:00+00:00",
        pattern_height=10.0,
        breakout_candle_timestamp="2026-09-01T11:00:00+00:00",
        breakout_open=209.0,
        breakout_high=212.0,
        breakout_low=208.5,
        breakout_close=211.5,
        trendline_price=210.0,
        ema20_price=208.0,
        measured_target=220.0,
        target_2=226.18,
        invalidation_level=199.5,
        quality_score=85,
        quality_breakdown={"reversal": 40, "trendline": 25, "ema": 20},
        status="TARGET OPEN",
        event_created_at="2026-09-01T11:01:00+00:00",
    )

    # 1. First migration: INSERTED
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        action, _ = await repo.migrate_single_alert_safe(alert)
        assert action == "INSERTED"
        await session.commit()

    # 2. Second migration with exact same data: SKIPPED
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        action, _ = await repo.migrate_single_alert_safe(alert)
        assert action == "SKIPPED"
        await session.commit()

    # 3. Third migration with modified field (e.g. altered neckline_price): must raise MigrationConflictError
    conflicting_alert = alert.model_copy(update={"neckline_price": 999.99})
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        with pytest.raises(MigrationConflictError) as exc_info:
            await repo.migrate_single_alert_safe(conflicting_alert)
        assert "Migration conflict detected" in str(exc_info.value)
        assert "neckline_price" in str(exc_info.value)


@pytest.mark.asyncio
async def test_lossless_migration_and_field_parity(test_db):
    _, sess_factory = test_db
    assert SOURCE_JSON_PATH.exists()

    with open(SOURCE_JSON_PATH, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    raw_alerts = raw_data.get("alerts", [])
    alerts = [MWBreakoutAlert(**item) for item in raw_alerts]
    assert len(alerts) >= 500
    total_source = len(alerts)

    # Migrate all alerts into test_db
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        for a in alerts:
            action, _ = await repo.migrate_single_alert_safe(a)
            assert action == "INSERTED"
        await session.commit()

    # Verify metrics
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        metrics = await repo.get_metrics()
        assert metrics["total_count"] == total_source
        assert metrics["w_count"] + metrics["m_count"] == total_source
        assert metrics["w_count"] > 0
        assert metrics["m_count"] > 0
        assert metrics["unique_identities"] == total_source
        assert metrics["duplicate_identities"] == 0

    # Verify field parity across all records
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        for a in alerts:
            model = await repo.get_by_physical_identity(
                symbol=a.symbol,
                timeframe=a.timeframe,
                pattern_type=a.pattern_type,
                breakout_candle_timestamp=a.breakout_candle_timestamp,
            )
            assert model is not None, f"Alert {a.alert_id} not found in DB"
            reconstructed = model.to_schema()

            # Compare pydantic dump to ensure 100% equivalence
            assert reconstructed.model_dump() == a.model_dump()


@pytest.mark.asyncio
async def test_migration_idempotency(test_db):
    _, sess_factory = test_db
    with open(SOURCE_JSON_PATH, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    alerts = [MWBreakoutAlert(**item) for item in raw_data.get("alerts", [])]
    total_source = len(alerts)
    assert total_source >= 500

    # Pass 1: All inserted
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        inserted = 0
        for a in alerts:
            act, _ = await repo.migrate_single_alert_safe(a)
            if act == "INSERTED":
                inserted += 1
        await session.commit()
    assert inserted == total_source

    # Pass 2: All skipped, 0 inserted
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        inserted_p2 = 0
        skipped_p2 = 0
        for a in alerts:
            act, _ = await repo.migrate_single_alert_safe(a)
            if act == "INSERTED":
                inserted_p2 += 1
            elif act == "SKIPPED":
                skipped_p2 += 1
        await session.commit()

    assert inserted_p2 == 0
    assert skipped_p2 == total_source

    # Total DB count remains exactly total_source
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        metrics = await repo.get_metrics()
        assert metrics["total_count"] == total_source


@pytest.mark.asyncio
async def test_json_source_remains_unmodified():
    initial_hash = get_json_sha256()
    with open(SOURCE_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert "alerts" in data
    assert len(data["alerts"]) >= 500
    final_hash = get_json_sha256()
    assert initial_hash == final_hash



@pytest.mark.asyncio
async def test_transaction_rollback(test_db):
    _, sess_factory = test_db

    alert = MWBreakoutAlert(
        alert_id="mw_ROLLBACK_TEST",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="ROLLBACK_SYM",
        ticker="ROLLBACK-TKR",
        timeframe="5M",
        pattern_id="ROLLBACK_PAT",
        s1_price=10.0,
        s1_timestamp="2026-09-01T10:00:00+00:00",
        s2_price=10.0,
        s2_timestamp="2026-09-01T10:30:00+00:00",
        neckline_price=12.0,
        neckline_timestamp="2026-09-01T10:15:00+00:00",
        pattern_height=2.0,
        breakout_candle_timestamp="2026-09-01T10:45:00+00:00",
        breakout_open=11.5,
        breakout_high=13.0,
        breakout_low=11.0,
        breakout_close=12.5,
        trendline_price=12.0,
        ema20_price=11.0,
        measured_target=14.0,
        target_2=15.24,
        invalidation_level=9.5,
        quality_score=75,
        quality_breakdown={"reversal": 40, "trendline": 20, "ema": 15},
        status="TARGET OPEN",
        event_created_at="2026-09-01T10:46:00+00:00",
    )

    async with sess_factory() as session:
        m = MWBreakoutAlertModel.from_schema(alert)
        session.add(m)
        await session.rollback()

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        found = await repo.get_by_id("mw_ROLLBACK_TEST")
        assert found is None


@pytest.mark.asyncio
async def test_repository_pagination_sorting(test_db):
    _, sess_factory = test_db
    with open(SOURCE_JSON_PATH, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    alerts = [MWBreakoutAlert(**item) for item in raw_data.get("alerts", [])]

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        for a in alerts:
            await repo.migrate_single_alert_safe(a)
        await session.commit()

    total_source = len(alerts)
    expected_pages = (total_source + 49) // 50
    last_page_count = total_source - (expected_pages - 1) * 50

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        items, total, total_pages, has_next, has_prev = await repo.get_paginated_alerts(
            page=1, limit=50
        )
        assert total == total_source
        assert total_pages == expected_pages
        assert len(items) == min(50, total_source)
        assert has_next is (expected_pages > 1)
        assert has_prev is False

        # Verify sorted newest first
        for i in range(len(items) - 1):
            assert items[i].breakout_candle_timestamp >= items[i + 1].breakout_candle_timestamp

        # Check last page
        items_last, _, _, has_next_last, has_prev_last = await repo.get_paginated_alerts(
            page=expected_pages, limit=50
        )
        assert len(items_last) == last_page_count
        assert has_next_last is False
        assert has_prev_last is (expected_pages > 1)
