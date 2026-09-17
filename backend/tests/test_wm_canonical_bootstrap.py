import asyncio
import json
import os
import subprocess
from pathlib import Path
import pytest
import pytest_asyncio

from app.db.database import Base, create_engine_and_sessionmaker, init_db
from app.db.models import MWBreakoutAlertModel, ProcessingCheckpointModel
from app.db.repository import MWAlertRepository, CheckpointRepository
from app.db.seeder import (
    bootstrap_canonical_alerts,
    resolve_canonical_seed_file,
    load_canonical_seed_alerts,
)
from app.models.schemas import MWBreakoutAlert
from app.alerts.mw_breakout_engine import mw_breakout_engine


@pytest_asyncio.fixture
async def clean_test_db(tmp_path, monkeypatch):
    """Provides a pristine, isolated SQLite database without any pre-seeded data."""
    db_file = tmp_path / "test_bootstrap.db"
    monkeypatch.setattr("app.core.config.settings.DATABASE_PATH", str(db_file))
    eng, sess_factory = create_engine_and_sessionmaker(db_file)
    await init_db(eng, seed_canonical=False)
    yield eng, sess_factory
    await eng.dispose()


@pytest.mark.asyncio
async def test_fresh_db_automatically_imports_canonical_alerts(clean_test_db):
    """
    Test 1: Proves that a fresh empty SQLite database automatically imports
    all canonical historical W/M alerts with exact parity and no hardcoded dependencies.
    """
    eng, sess_factory = clean_test_db
    seed_file = resolve_canonical_seed_file()
    assert seed_file is not None and seed_file.exists(), "Canonical seed file must exist"

    with open(seed_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    raw_alerts = raw_data.get("alerts", [])
    expected_total = len(raw_alerts)
    assert expected_total > 0

    res = await bootstrap_canonical_alerts(session_factory=sess_factory)
    assert res["total_canonical"] == expected_total
    assert res["inserted"] == expected_total
    assert res["skipped"] == 0

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        metrics = await repo.get_metrics()
        assert metrics["total_count"] == expected_total
        assert metrics["unique_identities"] == expected_total
        assert metrics["duplicate_identities"] == 0

        # Verify summary stats
        stats = await repo.get_summary_stats()
        assert stats["total_count"] == expected_total
        assert stats["w_breakouts"] > 0
        assert stats["m_breakdowns"] > 0
        assert stats["w_breakouts"] + stats["m_breakdowns"] == expected_total


@pytest.mark.asyncio
async def test_startup_twice_idempotency(clean_test_db):
    """
    Test 2: Proves running startup/bootstrap twice consecutively is 100% idempotent:
    inserts zero duplicate records on the second run and leaves the database intact.
    """
    eng, sess_factory = clean_test_db

    # Pass 1: Fresh import
    res1 = await bootstrap_canonical_alerts(session_factory=sess_factory)
    assert res1["inserted"] > 0
    total = res1["total_canonical"]

    # Pass 2: Immediate subsequent startup
    res2 = await bootstrap_canonical_alerts(session_factory=sess_factory)
    assert res2["inserted"] == 0
    assert res2["skipped"] == total

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        metrics = await repo.get_metrics()
        assert metrics["total_count"] == total
        assert metrics["duplicate_identities"] == 0


@pytest.mark.asyncio
async def test_existing_db_records_preserved(clean_test_db):
    """
    Test 3: Proves that existing database records are preserved:
    - Status progressions (e.g. TARGET 1 HIT) are NOT overwritten or reverted.
    - New records detected during live trading are NOT deleted.
    """
    eng, sess_factory = clean_test_db

    # First load all canonical alerts
    canonical_alerts = load_canonical_seed_alerts()
    assert len(canonical_alerts) > 2
    first_alert = canonical_alerts[0]

    # Insert first alert with a modified status (progressed in live market to TARGET 1 HIT)
    modified_alert = first_alert.model_copy(update={"status": "TARGET 1 HIT"})

    # Insert a brand new live alert (from today, not in canonical store)
    new_live_alert = MWBreakoutAlert(
        alert_id="mw_LIVE_TODAY_NEW_1",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="NIFTY",
        ticker="^NSEI",
        timeframe="5M",
        pattern_id="PAT_LIVE_1",
        s1_price=25000.0,
        s1_timestamp="2026-09-11T12:00:00+05:30",
        s2_price=25010.0,
        s2_timestamp="2026-09-11T12:30:00+05:30",
        neckline_price=25100.0,
        neckline_timestamp="2026-09-11T12:15:00+05:30",
        pattern_height=100.0,
        breakout_candle_timestamp="2026-09-11T13:00:00+05:30",
        breakout_open=25095.0,
        breakout_high=25120.0,
        breakout_low=25090.0,
        breakout_close=25115.0,
        trendline_price=25100.0,
        ema20_price=25080.0,
        measured_target=25200.0,
        target_2=25261.8,
        invalidation_level=24995.0,
        quality_score=85,
        quality_breakdown={"reversal": 40, "trendline": 25, "ema": 20},
        status="TARGET OPEN",
        event_created_at="2026-09-11T13:01:00+05:30",
    )

    async with sess_factory() as session:
        session.add(MWBreakoutAlertModel.from_schema(modified_alert))
        session.add(MWBreakoutAlertModel.from_schema(new_live_alert))
        await session.commit()

    # Run canonical bootstrap
    res = await bootstrap_canonical_alerts(session_factory=sess_factory)

    # The pre-existing modified alert was skipped; all other canonical alerts were inserted
    assert res["skipped"] == 1
    assert res["inserted"] == len(canonical_alerts) - 1

    async with sess_factory() as session:
        repo = MWAlertRepository(session)

        # 1. Verify the modified alert was PRESERVED and its status was NOT reverted to TARGET OPEN
        saved_modified = await repo.get_by_physical_identity(
            symbol=first_alert.symbol,
            timeframe=first_alert.timeframe,
            pattern_type=first_alert.pattern_type,
            breakout_candle_timestamp=first_alert.breakout_candle_timestamp,
        )
        assert saved_modified is not None
        assert saved_modified.status == "TARGET 1 HIT", "Status must NOT be reverted to TARGET OPEN"

        # 2. Verify the new live alert from today was NOT deleted
        saved_live = await repo.get_by_id("mw_LIVE_TODAY_NEW_1")
        assert saved_live is not None
        assert saved_live.symbol == "NIFTY"

        # 3. Verify total is canonical + 1
        metrics = await repo.get_metrics()
        assert metrics["total_count"] == len(canonical_alerts) + 1


@pytest.mark.asyncio
async def test_missing_canonical_records_imported_without_duplication(clean_test_db):
    """
    Test 4: Proves that if a database has a partial set of canonical alerts,
    only the genuinely missing ones are imported without creating duplicates.
    """
    eng, sess_factory = clean_test_db
    canonical_alerts = load_canonical_seed_alerts()
    assert len(canonical_alerts) > 10

    # Pre-populate first 10 alerts
    subset_10 = canonical_alerts[:10]
    async with sess_factory() as session:
        for a in subset_10:
            session.add(MWBreakoutAlertModel.from_schema(a))
        await session.commit()

    # Run bootstrap
    res = await bootstrap_canonical_alerts(session_factory=sess_factory)
    assert res["skipped"] == 10
    assert res["inserted"] == len(canonical_alerts) - 10

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        metrics = await repo.get_metrics()
        assert metrics["total_count"] == len(canonical_alerts)
        assert metrics["duplicate_identities"] == 0


@pytest.mark.asyncio
async def test_worker_continues_processing_new_candles_after_bootstrap(clean_test_db):
    """
    Test 5: Proves that after bootstrap, the autonomous processing system continues
    processing newly closed candles without inserting duplicates or errors.
    """
    eng, sess_factory = clean_test_db
    await bootstrap_canonical_alerts(session_factory=sess_factory)

    canonical_alerts = load_canonical_seed_alerts()
    existing_alert = canonical_alerts[0]

    # 1. Attempting to persist an existing canonical alert through the engine's sync persistence layer
    status_result = mw_breakout_engine._persist_alert_to_db_sync(existing_alert)
    assert status_result == "SKIPPED", "Engine must detect existing physical identity and skip insert"

    # 2. Persisting a genuinely new live candle alert
    brand_new_alert = existing_alert.model_copy(
        update={
            "alert_id": "mw_NEW_LIVE_CANDLE_99",
            "pattern_id": "NEW_LIVE_PATTERN_99",
            "s1_timestamp": "2026-09-12T09:15:00+05:30",
            "neckline_timestamp": "2026-09-12T09:30:00+05:30",
            "breakout_candle_timestamp": "2026-09-12T10:00:00+05:30",
        }
    )
    new_result = mw_breakout_engine._persist_alert_to_db_sync(brand_new_alert)
    assert new_result == "INSERTED"

    # Verify new alert is in the database
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        inserted_model = await repo.get_by_id("mw_NEW_LIVE_CANDLE_99")
        assert inserted_model is not None
        assert inserted_model.breakout_candle_timestamp == "2026-09-12T10:00:00+05:30"


@pytest.mark.asyncio
async def test_checkpoints_remain_correct(clean_test_db):
    """
    Test 6: Proves that canonical alert bootstrap does NOT alter or corrupt
    checkpoint records, and checkpoint persistence remains correct.
    """
    eng, sess_factory = clean_test_db

    # Establish an initial checkpoint
    async with sess_factory() as session:
        repo = CheckpointRepository(session)
        await repo.update_checkpoint(
            symbol="BTC/USD",
            timeframe="5M",
            last_candle_timestamp="2026-09-11T15:00:00+00:00",
            status="IDLE",
        )
        await session.commit()

    # Run canonical alert bootstrap
    await bootstrap_canonical_alerts(session_factory=sess_factory)

    # Verify checkpoint is untouched
    async with sess_factory() as session:
        repo = CheckpointRepository(session)
        cp = await repo.get_checkpoint("BTC/USD", "5M")
        assert cp is not None
        assert cp.last_processed_candle_timestamp == "2026-09-11T15:00:00+00:00"
        assert cp.checkpoint_status == "IDLE"

        # Verify checkpoint can advance to new candle
        await repo.update_checkpoint(
            symbol="BTC/USD",
            timeframe="5M",
            last_candle_timestamp="2026-09-11T15:05:00+00:00",
            status="SYNCED",
        )
        await session.commit()

        cp_updated = await repo.get_checkpoint("BTC/USD", "5M")
        assert cp_updated.last_processed_candle_timestamp == "2026-09-11T15:05:00+00:00"
        assert cp_updated.checkpoint_status == "SYNCED"


@pytest.mark.asyncio
async def test_stats_endpoint_returns_persistent_count(clean_test_db):
    """
    Test 7: Proves that MWAlertRepository.get_summary_stats() immediately returns
    the persistent canonical historical counts after bootstrap, eliminating the 0-count bug.
    """
    eng, sess_factory = clean_test_db
    canonical_alerts = load_canonical_seed_alerts()

    # Before bootstrap: 0
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        pre_stats = await repo.get_summary_stats()
        assert pre_stats["total_count"] == 0
        assert pre_stats["w_breakouts"] == 0

    # Bootstrap
    await bootstrap_canonical_alerts(session_factory=sess_factory)

    # After bootstrap: full persistent counts available immediately
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        post_stats = await repo.get_summary_stats()
        assert post_stats["total_count"] == len(canonical_alerts)
        assert post_stats["w_breakouts"] > 0
        assert post_stats["m_breakdowns"] > 0
        assert post_stats["total_count"] == post_stats["w_breakouts"] + post_stats["m_breakdowns"]


def test_invariants_no_detection_files_modified():
    """
    Test 8: Strict verification that zero detection, scoring, target, SL,
    or pattern files were modified in git working tree.
    """
    repo_root = Path(__file__).resolve().parents[2]
    protected_files = [
        "backend/app/market_structure/mw_patterns.py",
        "backend/app/market_structure/trendlines.py",
    ]

    # Run git diff against HEAD for protected files
    res = subprocess.run(
        ["git", "diff", "HEAD", "--"] + protected_files,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert res.stdout.strip() == "", f"Protected detection files were modified: {res.stdout}"
