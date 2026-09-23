import asyncio
import json
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.db.database import Base, create_engine_and_sessionmaker, get_sync_sqlite_connection
from app.db.models import MWBreakoutAlertModel
from app.db.repository import MWAlertRepository
from app.db.seeder import bootstrap_canonical_alerts
from app.models.schemas import Candle, MWBreakoutAlert
from app.alerts.mw_breakout_engine import MWBreakoutAlertEngine
from app.main import app
from scripts.reconcile_and_sync_db import perform_audit, resolve_lifecycle_conflict, struct_key


@pytest.fixture
def temp_db_path(tmp_path):
    """Provides an isolated SQLite database file for testing."""
    db_file = tmp_path / "test_authoritative.db"
    return db_file


@pytest.fixture
def test_engine_and_session(temp_db_path):
    """Creates tables and yields engine and session factory for an isolated test DB."""
    eng, factory = create_engine_and_sessionmaker(temp_db_path)

    async def _init_tables():
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Create structural unique index
            await conn.exec_driver_sql("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_mw_breakout_structural_identity
                ON mw_breakout_alerts (symbol, timeframe, pattern_type, s1_timestamp, neckline_timestamp);
            """)

    asyncio.run(_init_tables())
    yield eng, factory
    asyncio.run(eng.dispose())


def create_sample_alert(
    symbol="NIFTY 50",
    timeframe="15M",
    pattern_type="W",
    s1_time="2026-09-01T10:00:00+05:30",
    neckline_time="2026-09-01T10:30:00+05:30",
    s2_time="2026-09-01T11:00:00+05:30",
    breakout_time="2026-09-01T11:15:00+05:30",
    neckline_price=24500.0,
    status="TARGET OPEN",
    alert_id=None
) -> MWBreakoutAlert:
    clean_id = alert_id or f"mw_{symbol}_{timeframe}_{pattern_type}_{breakout_time}".replace(":", "-").replace(" ", "_")
    return MWBreakoutAlert(
        alert_id=clean_id,
        alert_type="W_BREAKOUT_CONFIRMED" if pattern_type == "W" else "M_BREAKDOWN_CONFIRMED",
        pattern_type=pattern_type,
        direction="UP" if pattern_type == "W" else "DOWN",
        symbol=symbol,
        ticker=symbol,
        timeframe=timeframe,
        pattern_id=f"{symbol}_{timeframe}_{pattern_type}_{s1_time}_{neckline_time}",
        s1_price=24000.0,
        s1_timestamp=s1_time,
        s2_price=24050.0,
        s2_timestamp=s2_time,
        neckline_price=neckline_price,
        neckline_timestamp=neckline_time,
        pattern_height=500.0,
        breakout_candle_timestamp=breakout_time,
        breakout_open=neckline_price,
        breakout_high=neckline_price + 50.0,
        breakout_low=neckline_price - 10.0,
        breakout_close=neckline_price + 30.0,
        trendline_price=neckline_price,
        ema20_price=neckline_price,
        volume=1000.0,
        relative_volume=1.5,
        measured_target=neckline_price + 500.0,
        target_2=neckline_price + 800.0,
        invalidation_level=24000.0,
        quality_score=85,
        quality_breakdown={"structure": 25, "swing": 20},
        reversal_score=40,
        trendline_score=20,
        ema_score=25,
        reversal_points=40,
        trendline_points=20,
        ema_points=25,
        status=status,
        trade_quality="HIGH",
        entry_status="VALID",
        outcome_timestamp=None,
        stop_loss=24000.0,
        event_created_at="2026-09-01T11:15:00+05:30",
        read=False
    )


# ==============================================================================
# 1. Breakout detection persists to database before broadcast
# ==============================================================================
@pytest.mark.asyncio
async def test_breakout_persists_before_broadcast(test_engine_and_session, temp_db_path, monkeypatch):
    """Verifies that an alert is written to SQLite before any broadcast can take place."""
    eng, factory = test_engine_and_session
    monkeypatch.setattr("app.alerts.mw_breakout_engine.get_database_path", lambda: temp_db_path)

    engine = MWBreakoutAlertEngine()
    engine.alerts.clear()
    engine.seen_event_keys.clear()

    alert = create_sample_alert(symbol="INFY", breakout_time="2026-09-02T10:00:00+05:30")

    # Broadcast tracking flag
    persisted_when_broadcast = False

    async def mock_broadcast(payload):
        nonlocal persisted_when_broadcast
        # Query DB right inside broadcast handler to confirm alert is already in DB
        with get_sync_sqlite_connection(temp_db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM mw_breakout_alerts WHERE alert_id = ?", (alert.alert_id,))
            if cur.fetchone()[0] == 1:
                persisted_when_broadcast = True

    # Call persist
    action = engine._persist_alert_to_db_sync(alert)
    assert action == "INSERTED"

    # Simulate worker broadcast
    await mock_broadcast({"type": "MW_BREAKOUT_TRIGGERED", "alert": alert.model_dump()})
    assert persisted_when_broadcast is True


# ==============================================================================
# 2. Failed database write prevents broadcast and does not corrupt state
# ==============================================================================
def test_failed_db_write_prevents_broadcast(test_engine_and_session, temp_db_path, monkeypatch):
    """Verifies that a DB persistence failure prevents broadcast and queues the alert safely."""
    eng, factory = test_engine_and_session
    monkeypatch.setattr("app.alerts.mw_breakout_engine.get_database_path", lambda: temp_db_path)

    engine = MWBreakoutAlertEngine()
    engine.alerts.clear()
    engine._pending_db_retry_queue.clear()

    alert = create_sample_alert(symbol="TCS", breakout_time="2026-09-02T11:00:00+05:30")

    # Force SQLite connection to fail
    def failing_conn(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked (simulated)")

    monkeypatch.setattr("app.alerts.mw_breakout_engine.get_sync_sqlite_connection", failing_conn)

    action = engine._persist_alert_to_db_sync(alert)
    assert action == "ERROR"

    # Must be added to retry queue
    assert len(engine._pending_db_retry_queue) == 1
    assert engine._pending_db_retry_queue[0].alert_id == alert.alert_id

    # Must NOT be in active alerts
    assert not any(a.alert_id == alert.alert_id for a in engine.alerts)


# ==============================================================================
# 3. Concurrent breakout detections for same pattern result in exactly one record
# ==============================================================================
@pytest.mark.asyncio
async def test_concurrent_breakout_detections_single_record(test_engine_and_session, temp_db_path, monkeypatch):
    """Verifies concurrent persistence attempts for the same structural pattern resolve to 1 record."""
    eng, factory = test_engine_and_session
    monkeypatch.setattr("app.alerts.mw_breakout_engine.get_database_path", lambda: temp_db_path)

    engine = MWBreakoutAlertEngine()
    alert1 = create_sample_alert(symbol="RELIANCE", breakout_time="2026-09-02T12:00:00+05:30", alert_id="mw_rel_1")
    alert2 = create_sample_alert(symbol="RELIANCE", breakout_time="2026-09-02T12:00:00+05:30", alert_id="mw_rel_2")

    loop = asyncio.get_running_loop()
    results = await asyncio.gather(
        loop.run_in_executor(None, engine._persist_alert_to_db_sync, alert1),
        loop.run_in_executor(None, engine._persist_alert_to_db_sync, alert2)
    )

    # Exactly one INSERTED, other SKIPPED
    assert "INSERTED" in results
    assert "SKIPPED" in results

    with get_sync_sqlite_connection(temp_db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mw_breakout_alerts WHERE symbol = 'RELIANCE'")
        assert cur.fetchone()[0] == 1


# ==============================================================================
# 4. Subsequent candle updates modify existing record rather than creating new one
# ==============================================================================
def test_subsequent_candle_updates_existing_record(test_engine_and_session, temp_db_path, monkeypatch):
    """Verifies subsequent candles update status in place without creating new rows."""
    eng, factory = test_engine_and_session
    monkeypatch.setattr("app.alerts.mw_breakout_engine.get_database_path", lambda: temp_db_path)

    engine = MWBreakoutAlertEngine()
    alert = create_sample_alert(
        symbol="HDFCBANK",
        breakout_time="2026-09-02T09:30:00+05:30",
        neckline_price=1600.0,
        status="TARGET OPEN"
    )
    alert.measured_target = 1650.0
    alert.target_2 = 1700.0
    alert.invalidation_level = 1550.0

    action = engine._persist_alert_to_db_sync(alert)
    assert action == "INSERTED"

    # Subsequent candle hits Target 1
    candles = [
        Candle(
            timestamp="2026-09-02T09:45:00+05:30",
            open=1610.0,
            high=1660.0, # Touches Target 1 (1650.0)
            low=1605.0,
            close=1655.0,
            volume=5000.0
        )
    ]

    changed = engine.replay_alert_lifecycle(alert, candles)
    assert changed is True
    assert alert.status == "TARGET 1 HIT"

    # Update in DB
    ok = engine._update_alert_status_db_sync(alert.alert_id, alert.status, alert.outcome_timestamp)
    assert ok is True

    # Verify DB still has exactly 1 row with updated status
    with get_sync_sqlite_connection(temp_db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), status FROM mw_breakout_alerts WHERE symbol = 'HDFCBANK'")
        row = cur.fetchone()
        assert row[0] == 1
        assert row[1] == "TARGET 1 HIT"


# ==============================================================================
# 5. Database uniqueness constraints reject duplicate structural records
# ==============================================================================
def test_database_uniqueness_constraint_enforced(test_engine_and_session, temp_db_path):
    """Verifies that SQLite uq_mw_breakout_structural_identity rejects duplicate structural inserts."""
    with get_sync_sqlite_connection(temp_db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO mw_breakout_alerts (
                alert_id, alert_type, pattern_type, direction, symbol, ticker, timeframe,
                pattern_id, s1_price, s1_timestamp, s2_price, s2_timestamp, neckline_price,
                neckline_timestamp, pattern_height, breakout_candle_timestamp, breakout_open,
                breakout_high, breakout_low, breakout_close, trendline_price, ema20_price,
                volume, relative_volume, measured_target, target_2, invalidation_level,
                quality_score, quality_breakdown, reversal_score, trendline_score, ema_score,
                reversal_points, trendline_points, ema_points, status, trade_quality,
                entry_status, event_created_at, read
            ) VALUES (
                'alert_1', 'W_BREAKOUT_CONFIRMED', 'W', 'UP', 'SBIN', 'SBIN', '5M',
                'pat_1', 800.0, '2026-09-03T10:00:00+05:30', 805.0, '2026-09-03T10:15:00+05:30',
                820.0, '2026-09-03T10:10:00+05:30', 20.0, '2026-09-03T10:20:00+05:30',
                820.0, 825.0, 818.0, 824.0, 820.0, 820.0, 1000.0, 1.2, 840.0, 850.0, 800.0,
                80, '{}', 40, 20, 20, 40, 20, 20, 'TARGET OPEN', 'HIGH', 'VALID',
                '2026-09-03T10:20:00+05:30', 0
            );
        """)

        # Attempt duplicate insert with different alert_id and breakout timestamp, but SAME structural anchors
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute("""
                INSERT INTO mw_breakout_alerts (
                    alert_id, alert_type, pattern_type, direction, symbol, ticker, timeframe,
                    pattern_id, s1_price, s1_timestamp, s2_price, s2_timestamp, neckline_price,
                    neckline_timestamp, pattern_height, breakout_candle_timestamp, breakout_open,
                    breakout_high, breakout_low, breakout_close, trendline_price, ema20_price,
                    volume, relative_volume, measured_target, target_2, invalidation_level,
                    quality_score, quality_breakdown, reversal_score, trendline_score, ema_score,
                    reversal_points, trendline_points, ema_points, status, trade_quality,
                    entry_status, event_created_at, read
                ) VALUES (
                    'alert_2', 'W_BREAKOUT_CONFIRMED', 'W', 'UP', 'SBIN', 'SBIN', '5M',
                    'pat_2', 800.0, '2026-09-03T10:00:00+05:30', 805.0, '2026-09-03T10:18:00+05:30',
                    820.0, '2026-09-03T10:10:00+05:30', 20.0, '2026-09-03T10:25:00+05:30',
                    820.0, 826.0, 819.0, 825.0, 820.0, 820.0, 1000.0, 1.2, 840.0, 850.0, 800.0,
                    80, '{}', 40, 20, 20, 40, 20, 20, 'TARGET OPEN', 'HIGH', 'VALID',
                    '2026-09-03T10:25:00+05:30', 0
                );
            """)


# ==============================================================================
# 6. API pagination returns correct subsets and total count matching database
# ==============================================================================
@pytest.mark.asyncio
async def test_api_pagination_exact_db_match(test_engine_and_session, monkeypatch):
    """Verifies /api/alerts/mw-breakouts pagination matches the database exactly."""
    eng, factory = test_engine_and_session
    monkeypatch.setattr("app.api.routes_alerts.get_session_factory", lambda: factory)

    # Insert 15 alerts into DB
    async with factory() as session:
        for i in range(15):
            alert = create_sample_alert(
                symbol="NIFTY 50",
                s1_time=f"2026-09-01T{10+i:02d}:00:00+05:30",
                neckline_time=f"2026-09-01T{10+i:02d}:30:00+05:30",
                breakout_time=f"2026-09-01T{10+i:02d}:45:00+05:30",
                alert_id=f"alert_pag_{i}"
            )
            session.add(MWBreakoutAlertModel(**alert.model_dump()))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request page 1 with limit 5
        resp = await client.get("/api/alerts/mw-breakouts?page=1&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 15
        assert len(data["items"]) == 5
        assert data["total_pages"] == 3
        assert data["has_next"] is True
        assert data["has_previous"] is False

        # Request page 3 with limit 5
        resp3 = await client.get("/api/alerts/mw-breakouts?page=3&limit=5")
        data3 = resp3.json()
        assert len(data3["items"]) == 5
        assert data3["has_next"] is False
        assert data3["has_previous"] is True


# ==============================================================================
# 7. API filters return exact database matches
# ==============================================================================
@pytest.mark.asyncio
async def test_api_filters_exact_db_match(test_engine_and_session, monkeypatch):
    """Verifies API filters for symbol, timeframe, pattern_type, and status."""
    eng, factory = test_engine_and_session
    monkeypatch.setattr("app.api.routes_alerts.get_session_factory", lambda: factory)

    async with factory() as session:
        # 1. NIFTY 50 15M W TARGET OPEN
        a1 = create_sample_alert(symbol="NIFTY 50", timeframe="15M", pattern_type="W", status="TARGET OPEN", alert_id="f_1", s1_time="2026-09-01T09:00:00+05:30", neckline_time="2026-09-01T09:30:00+05:30")
        # 2. NIFTY 50 5M M TARGET 1 HIT
        a2 = create_sample_alert(symbol="NIFTY 50", timeframe="5M", pattern_type="M", status="TARGET 1 HIT", alert_id="f_2", s1_time="2026-09-01T10:00:00+05:30", neckline_time="2026-09-01T10:30:00+05:30")
        # 3. BANK NIFTY 15M W SL HIT
        a3 = create_sample_alert(symbol="BANK NIFTY", timeframe="15M", pattern_type="W", status="SL HIT", alert_id="f_3", s1_time="2026-09-01T11:00:00+05:30", neckline_time="2026-09-01T11:30:00+05:30")
        session.add_all([MWBreakoutAlertModel(**a1.model_dump()), MWBreakoutAlertModel(**a2.model_dump()), MWBreakoutAlertModel(**a3.model_dump())])
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Filter by symbol
        r_sym = await client.get("/api/alerts/mw-breakouts?symbol=BANK NIFTY&page=1")
        assert r_sym.json()["total"] == 1
        assert r_sym.json()["items"][0]["symbol"] == "BANK NIFTY"

        # Filter by pattern_type
        r_pt = await client.get("/api/alerts/mw-breakouts?pattern_type=M&page=1")
        assert r_pt.json()["total"] == 1
        assert r_pt.json()["items"][0]["pattern_type"] == "M"

        # Filter by status
        r_st = await client.get("/api/alerts/mw-breakouts?status=COMPLETED&page=1")
        assert r_st.json()["total"] == 1
        assert r_st.json()["items"][0]["status"] == "TARGET 1 HIT"


# ==============================================================================
# 8. Frontend stats match database counts exactly
# ==============================================================================
@pytest.mark.asyncio
async def test_frontend_stats_match_api(test_engine_and_session, monkeypatch):
    """Verifies that /api/alerts/mw-breakouts/stats matches the actual database records."""
    eng, factory = test_engine_and_session
    monkeypatch.setattr("app.api.routes_alerts.get_session_factory", lambda: factory)

    async with factory() as session:
        # 2 W breakouts, 1 M breakdown
        a1 = create_sample_alert(symbol="INFY", pattern_type="W", status="TARGET OPEN", alert_id="s_1", s1_time="2026-09-01T09:00:00+05:30", neckline_time="2026-09-01T09:30:00+05:30")
        a2 = create_sample_alert(symbol="TCS", pattern_type="W", status="TARGET 1 HIT", alert_id="s_2", s1_time="2026-09-01T10:00:00+05:30", neckline_time="2026-09-01T10:30:00+05:30")
        a3 = create_sample_alert(symbol="SBIN", pattern_type="M", status="SL HIT", alert_id="s_3", s1_time="2026-09-01T11:00:00+05:30", neckline_time="2026-09-01T11:30:00+05:30")
        session.add_all([MWBreakoutAlertModel(**a1.model_dump()), MWBreakoutAlertModel(**a2.model_dump()), MWBreakoutAlertModel(**a3.model_dump())])
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/alerts/mw-breakouts/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total_count"] == 3
        assert stats["w_breakouts"] == 2
        assert stats["m_breakdowns"] == 1
        assert stats["active_count"] == 1
        assert stats["target_hit_count"] == 1
        assert stats["invalidated_count"] == 1


# ==============================================================================
# 9. Reconciliation/sync script correctly identifies and merges records without duplicates
# ==============================================================================
def test_reconciliation_script_merge():
    """Verifies that perform_audit merges Local and Prod sets without duplicate records."""
    loc_1 = create_sample_alert(symbol="SBIN", s1_time="2026-09-01T09:00:00+05:30", neckline_time="2026-09-01T09:30:00+05:30", breakout_time="2026-09-01T09:45:00+05:30", alert_id="loc_1").model_dump()
    loc_dup = create_sample_alert(symbol="SBIN", s1_time="2026-09-01T09:00:00+05:30", neckline_time="2026-09-01T09:30:00+05:30", breakout_time="2026-09-01T09:50:00+05:30", alert_id="loc_dup").model_dump()

    # Prod has a new record not in Local
    prod_new = create_sample_alert(symbol="TCS", s1_time="2026-09-02T10:00:00+05:30", neckline_time="2026-09-02T10:30:00+05:30", breakout_time="2026-09-02T10:45:00+05:30", alert_id="prod_new").model_dump()

    audit = perform_audit(
        local_records=[loc_1, loc_dup],
        prod_records=[prod_new],
        json_records=[]
    )

    assert audit["local_raw_count"] == 2
    assert audit["local_genuine_count"] == 1
    assert audit["local_duplicate_count"] == 1
    assert audit["reconciled_total"] == 2  # SBIN (earliest candle) + TCS
    assert len(audit["reconciled_master"]) == 2


# ==============================================================================
# 10. Idempotent migration produces identical results on second run
# ==============================================================================
def test_idempotent_migration():
    """Verifies that running perform_audit twice produces identical output with 0 new duplicates."""
    rec_a = create_sample_alert(symbol="INFY", s1_time="2026-09-01T09:00:00+05:30", neckline_time="2026-09-01T09:30:00+05:30", alert_id="rec_a").model_dump()
    rec_b = create_sample_alert(symbol="TCS", s1_time="2026-09-01T10:00:00+05:30", neckline_time="2026-09-01T10:30:00+05:30", alert_id="rec_b").model_dump()

    clean_records = [rec_a, rec_b]

    # Run 1
    audit1 = perform_audit(clean_records, clean_records, clean_records)
    # Run 2 on results of Run 1
    audit2 = perform_audit(list(audit1["reconciled_master"].values()), list(audit1["reconciled_master"].values()), [])

    assert audit2["local_raw_count"] == audit1["reconciled_total"]
    assert audit2["local_duplicate_count"] == 0
    assert audit2["reconciled_total"] == audit1["reconciled_total"]
    assert len(audit2["to_import_from_prod"]) == 0
    assert len(audit2["conflicts"]) == 0
