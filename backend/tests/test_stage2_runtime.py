import hashlib
import json
from pathlib import Path
import pytest
import pytest_asyncio
from sqlalchemy import select, func

from app.db.database import (
    create_engine_and_sessionmaker,
    init_db,
    get_database_path,
)
from app.db.models import MWBreakoutAlertModel
from app.db.repository import MWAlertRepository, MigrationConflictError
from app.models.schemas import MWBreakoutAlert, Candle

PROD_JSON_PATH = Path(__file__).resolve().parents[1] / "data" / "mw_breakout_alerts_store.json"
PROD_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "market_analyzer.db"
BASELINE_JSON_HASH = "ed53202221eb06113dfbfab99c010bdaece1758104b5c3586ff211155f923fbc"


def _make_sample_alert(
    alert_id: str = "mw_SAMPLE_001",
    symbol: str = "TEST_SYM",
    timeframe: str = "15M",
    pattern_type: str = "W",
    breakout_ts: str = "2026-09-01T10:00:00+00:00",
    status: str = "TARGET OPEN",
    neckline: float = 100.0,
) -> MWBreakoutAlert:
    return MWBreakoutAlert(
        alert_id=alert_id,
        alert_type="W_BREAKOUT_CONFIRMED" if pattern_type == "W" else "M_BREAKDOWN_CONFIRMED",
        pattern_type=pattern_type,
        direction="UP" if pattern_type == "W" else "DOWN",
        symbol=symbol,
        ticker=f"{symbol}-TICK",
        timeframe=timeframe,
        pattern_id=f"pat_{alert_id}",
        s1_price=90.0,
        s1_timestamp="2026-09-01T09:00:00+00:00",
        s2_price=92.0,
        s2_timestamp="2026-09-01T09:30:00+00:00",
        neckline_price=neckline,
        neckline_timestamp="2026-09-01T09:15:00+00:00",
        pattern_height=10.0,
        breakout_candle_timestamp=breakout_ts,
        breakout_open=99.0,
        breakout_high=102.0,
        breakout_low=98.5,
        breakout_close=101.5,
        trendline_price=100.0,
        ema20_price=99.0,
        volume=1000.0,
        relative_volume=1.35,
        measured_target=110.0 if pattern_type == "W" else 90.0,
        target_2=116.18 if pattern_type == "W" else 83.82,
        invalidation_level=89.0 if pattern_type == "W" else 102.0,
        quality_score=85,
        quality_breakdown={"reversal": 40, "trendline": 25, "ema": 20},
        reversal_score=40,
        trendline_score=25,
        ema_score=20,
        reversal_points=40,
        trendline_points=25,
        ema_points=20,
        status=status,
        trade_quality="HIGH",
        entry_status="VALID",
        event_created_at="2026-09-01T10:01:00+00:00",
        read=False,
    )


# ---------------------------------------------------------------------------
# Tests 1-6: Database-backed Pagination, Chronological Order, Production Data
# ---------------------------------------------------------------------------

@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_01_all_543_migrated_alerts_accessible_in_prod():
    """1. All 543 migrated historical alerts remain accessible directly in SQLite."""
    assert PROD_DB_PATH.exists()
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        metrics = await repo.get_metrics()
        assert metrics["total_count"] == 543
        assert metrics["w_count"] == 278
        assert metrics["m_count"] == 265
        assert metrics["unique_identities"] == 543
        assert metrics["duplicate_identities"] == 0
        assert metrics["earliest_timestamp"] == "2026-05-14T15:15:00+05:30"
        assert metrics["latest_timestamp"] == "2026-09-09T11:00:00+05:30"
    await eng.dispose()


@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_02_pagination_page1_newest_records():
    """2. Page 1 returns the newest records chronologically."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        items, total, total_pages, has_next, has_prev = await repo.get_paginated_alerts(page=1, limit=50)
        assert len(items) == 50
        assert total == 543
        assert total_pages == 11
        assert has_next is True
        assert has_prev is False
        assert items[0].breakout_candle_timestamp == "2026-09-09T11:00:00+05:30"
    await eng.dispose()


@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_03_pagination_page2_next_older_records():
    """3. Page 2 returns the next older records, disjoint from Page 1."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        p1_items, _, _, _, _ = await repo.get_paginated_alerts(page=1, limit=50)
        p2_items, _, _, _, _ = await repo.get_paginated_alerts(page=2, limit=50)
        assert len(p2_items) == 50

        p1_ids = {a.alert_id for a in p1_items}
        p2_ids = {a.alert_id for a in p2_items}
        assert p1_ids.isdisjoint(p2_ids), "Page 1 and Page 2 must not overlap"

        # Page 1 oldest must be >= Page 2 newest
        assert p1_items[-1].breakout_candle_timestamp >= p2_items[0].breakout_candle_timestamp
    await eng.dispose()


@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_04_multiple_pages_work_correctly():
    """4. Multiple sequential pages work correctly with consistent totals."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        all_ids = []
        for p in range(1, 4):
            items, total, pages, has_next, has_prev = await repo.get_paginated_alerts(page=p, limit=50)
            assert len(items) == 50
            assert total == 543
            assert pages == 11
            all_ids.extend([a.alert_id for a in items])
        assert len(set(all_ids)) == 150
    await eng.dispose()


@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_05_no_artificial_maximum_page():
    """5. There is no artificial maximum page cap (e.g. 200 or page 4)."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        # Page 11 contains remaining 43 records
        items_11, total, total_pages, has_next_11, has_prev_11 = await repo.get_paginated_alerts(page=11, limit=50)
        assert len(items_11) == 43
        assert total_pages == 11
        assert has_next_11 is False
        assert has_prev_11 is True
        assert items_11[-1].breakout_candle_timestamp == "2026-05-14T15:15:00+05:30"

        # Page 12 beyond total returns empty items
        items_12, _, _, has_next_12, _ = await repo.get_paginated_alerts(page=12, limit=50)
        assert len(items_12) == 0
        assert has_next_12 is False
    await eng.dispose()


@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_06_chronological_ordering_deterministic():
    """6. Ordering is strictly deterministic by breakout_candle_timestamp DESC, alert_id DESC."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        items, _, _, _, _ = await repo.get_paginated_alerts(page=1, limit=100)
        for i in range(len(items) - 1):
            cur = items[i]
            nxt = items[i + 1]
            assert cur.breakout_candle_timestamp >= nxt.breakout_candle_timestamp
            if cur.breakout_candle_timestamp == nxt.breakout_candle_timestamp:
                assert cur.alert_id >= nxt.alert_id
    await eng.dispose()


# ---------------------------------------------------------------------------
# Tests 7-10: Filtering (Symbol, Timeframe, Pattern Type, Status)
# ---------------------------------------------------------------------------

@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_07_symbol_filtering():
    """7. Symbol filtering works at the database level for BTC/USD and NIFTY 50."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        # Exact slash symbol
        btc_items, btc_total, _, _, _ = await repo.get_paginated_alerts(symbol="BTC/USD", limit=50)
        assert btc_total > 0
        assert all("BTC" in a.symbol for a in btc_items)

        # Unslashed search query
        btc_unslashed, btc_unslashed_tot, _, _, _ = await repo.get_paginated_alerts(symbol="BTCUSD", limit=50)
        assert btc_unslashed_tot == btc_total

        # NIFTY 50 search
        nifty_items, nifty_tot, _, _, _ = await repo.get_paginated_alerts(symbol="NIFTY 50", limit=50)
        assert nifty_tot > 0
        assert all("NIFTY" in a.symbol for a in nifty_items)
    await eng.dispose()


@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_08_timeframe_filtering():
    """8. Timeframe filtering works at the database level."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        for tf in ["15M", "1H", "4H", "5M"]:
            items, total, _, _, _ = await repo.get_paginated_alerts(timeframe=tf, limit=50)
            assert total > 0
            assert all(a.timeframe.upper() == tf.upper() for a in items)
    await eng.dispose()


@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_09_pattern_type_filtering():
    """9. Pattern type filtering returns exactly 278 W and 265 M."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        w_items, w_total, _, _, _ = await repo.get_paginated_alerts(pattern_type="W", limit=50)
        m_items, m_total, _, _, _ = await repo.get_paginated_alerts(pattern_type="M", limit=50)
        assert w_total == 278
        assert m_total == 265
        assert all(a.pattern_type == "W" for a in w_items)
        assert all(a.pattern_type == "M" for a in m_items)
    await eng.dispose()


@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_10_status_filtering():
    """10. Status filtering works for TARGET OPEN, COMPLETED, SL HIT."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        comp_items, comp_total, _, _, _ = await repo.get_paginated_alerts(status="COMPLETED", limit=50)
        assert comp_total > 0
        assert all(a.status in ["TARGET 1 HIT", "TARGET 2 HIT", "TARGET_1_HIT", "TARGET_2_HIT"] for a in comp_items)

        sl_items, sl_total, _, _, _ = await repo.get_paginated_alerts(status="SL HIT", limit=50)
        assert sl_total > 0
        assert all(a.status in ["SL HIT", "INVALIDATED"] for a in sl_items)
    await eng.dispose()


# ---------------------------------------------------------------------------
# Tests 11-12: Exact & Flexible Alert Lookup
# ---------------------------------------------------------------------------

@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_11_exact_alert_lookup():
    """11. Exact alert lookup by primary key alert_id."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        # Fetch first alert
        items, _, _, _, _ = await repo.get_paginated_alerts(limit=1)
        target = items[0]

        model = await repo.get_by_id(target.alert_id)
        assert model is not None
        assert model.alert_id == target.alert_id
        assert model.symbol == target.symbol
    await eng.dispose()


@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_12_flexible_alert_lookup():
    """12. Flexible lookup works with URL decoding, pattern_id, and slash normalization."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        items, _, _, _, _ = await repo.get_paginated_alerts(symbol="BTC/USD", limit=1)
        target = items[0]

        # 1. By exact ID
        m1 = await repo.get_alert_by_flexible_id(target.alert_id)
        assert m1 is not None and m1.alert_id == target.alert_id

        # 2. By pattern_id
        m2 = await repo.get_alert_by_flexible_id(target.pattern_id)
        assert m2 is not None and m2.alert_id == target.alert_id

        # 3. URL encoded alert_id
        encoded_id = target.alert_id.replace("/", "%2F")
        m3 = await repo.get_alert_by_flexible_id(encoded_id)
        assert m3 is not None and m3.alert_id == target.alert_id
    await eng.dispose()


# ---------------------------------------------------------------------------
# Tests 13-16: Physical Breakout Ingestion, Duplication & Conflict Handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage2_13_duplicate_physical_breakout_rejection(tmp_path):
    """13. Duplicate physical breakout ingestion skips safely without creating a 2nd record."""
    eng, sess_factory = create_engine_and_sessionmaker(tmp_path / "test_iso_db.db")
    await init_db(eng)

    alert1 = _make_sample_alert(alert_id="mw_ORIGINAL_1")
    alert_dup = alert1.model_copy()  # Exact same physical identity and fields

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        act1, m1 = await repo.ingest_alert_safe(alert1)
        assert act1 == "INSERTED"
        await session.commit()

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        act2, m2 = await repo.ingest_alert_safe(alert_dup)
        assert act2 == "SKIPPED"
        assert m2.alert_id == "mw_ORIGINAL_1"
        await session.commit()

    async with sess_factory() as session:
        count = await session.scalar(select(func.count()).select_from(MWBreakoutAlertModel))
        assert count == 1
    await eng.dispose()


@pytest.mark.asyncio
async def test_stage2_14_conflicting_physical_identity_rejection(tmp_path):
    """14. Conflicting physical identity does not silently overwrite; raises MigrationConflictError."""
    eng, sess_factory = create_engine_and_sessionmaker(tmp_path / "test_iso_db.db")
    await init_db(eng)

    alert = _make_sample_alert(neckline=100.0)
    conflicting = alert.model_copy(update={"neckline_price": 999.0})

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        await repo.ingest_alert_safe(alert)
        await session.commit()

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        with pytest.raises(MigrationConflictError) as exc_info:
            await repo.ingest_alert_safe(conflicting)
        err_msg = str(exc_info.value)
        assert "Migration conflict detected" in err_msg
        assert "neckline_price" in err_msg
        assert "999.0" in err_msg
        assert "100.0" in err_msg
    await eng.dispose()


@pytest.mark.asyncio
async def test_stage2_15_new_alert_insertion_persists(tmp_path):
    """15. New alert insertion persists and flushes cleanly to SQLite."""
    eng, sess_factory = create_engine_and_sessionmaker(tmp_path / "test_iso_db.db")
    await init_db(eng)

    alert = _make_sample_alert()
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        action, model = await repo.ingest_alert_safe(alert)
        assert action == "INSERTED"
        assert model.alert_id == alert.alert_id
        await session.commit()

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        found = await repo.get_by_id(alert.alert_id)
        assert found is not None
        assert found.symbol == alert.symbol
    await eng.dispose()


@pytest.mark.asyncio
async def test_stage2_16_existing_alert_fields_unchanged_on_duplicate(tmp_path):
    """16. Existing alert fields remain 100% unchanged on duplicate ingestion."""
    eng, sess_factory = create_engine_and_sessionmaker(tmp_path / "test_iso_db.db")
    await init_db(eng)

    alert = _make_sample_alert()
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        await repo.ingest_alert_safe(alert)
        await session.commit()

    # Re-ingest
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        await repo.ingest_alert_safe(alert)
        await session.commit()

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        stored = await repo.get_by_id(alert.alert_id)
        assert stored.to_schema().model_dump() == alert.model_dump()
    await eng.dispose()


# ---------------------------------------------------------------------------
# Tests 17-20: Lifecycle, Terminal Immutability, Read-All, Summary Stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage2_17_lifecycle_status_update(tmp_path):
    """17. Lifecycle status update changes status and outcome_timestamp in SQLite."""
    eng, sess_factory = create_engine_and_sessionmaker(tmp_path / "test_iso_db.db")
    await init_db(eng)

    alert = _make_sample_alert(status="TARGET OPEN")
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        await repo.ingest_alert_safe(alert)
        await session.commit()

    outcome_ts = "2026-09-01T10:45:00+00:00"
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        success = await repo.update_alert_status(alert.alert_id, "TARGET 1 HIT", outcome_ts)
        assert success is True
        await session.commit()

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        updated = await repo.get_by_id(alert.alert_id)
        assert updated.status == "TARGET 1 HIT"
        assert updated.outcome_timestamp == outcome_ts
    await eng.dispose()


@pytest.mark.asyncio
async def test_stage2_18_terminal_outcome_immutability(tmp_path):
    """18. Terminal outcome (TARGET 2 HIT, SL HIT) cannot be reverted."""
    eng, sess_factory = create_engine_and_sessionmaker(tmp_path / "test_iso_db.db")
    await init_db(eng)

    # 1. TARGET 2 HIT terminal
    a_t2 = _make_sample_alert(alert_id="mw_T2_TERMINAL", breakout_ts="2026-09-01T10:00:00Z", status="TARGET 2 HIT")
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        await repo.ingest_alert_safe(a_t2)
        await session.commit()

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        # Attempting to revert TARGET 2 HIT to TARGET OPEN must be rejected
        res = await repo.update_alert_status(a_t2.alert_id, "TARGET OPEN")
        assert res is False
        await session.commit()

    # 2. SL HIT terminal
    a_sl = _make_sample_alert(alert_id="mw_SL_TERMINAL", breakout_ts="2026-09-01T11:00:00Z", status="SL HIT")
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        await repo.ingest_alert_safe(a_sl)
        await session.commit()

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        # Attempting to revert SL HIT to TARGET 1 HIT must be rejected
        res_sl = await repo.update_alert_status(a_sl.alert_id, "TARGET 1 HIT")
        assert res_sl is False
        await session.commit()

    # 3. TARGET 1 HIT cannot revert to SL HIT
    a_t1 = _make_sample_alert(alert_id="mw_T1_WINNER", breakout_ts="2026-09-01T12:00:00Z", status="TARGET 1 HIT")
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        await repo.ingest_alert_safe(a_t1)
        await session.commit()

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        res_t1 = await repo.update_alert_status(a_t1.alert_id, "SL HIT")
        assert res_t1 is False
        # But progressing to TARGET 2 HIT is allowed
        res_t1_t2 = await repo.update_alert_status(a_t1.alert_id, "TARGET 2 HIT")
        assert res_t1_t2 is True
        await session.commit()

    await eng.dispose()


@pytest.mark.asyncio
async def test_stage2_19_read_all_works(tmp_path):
    """19. read-all marks all records as read=True in SQLite."""
    eng, sess_factory = create_engine_and_sessionmaker(tmp_path / "test_iso_db.db")
    await init_db(eng)

    a1 = _make_sample_alert(alert_id="mw_R1", breakout_ts="2026-09-01T10:00:00Z")
    a2 = _make_sample_alert(alert_id="mw_R2", breakout_ts="2026-09-01T11:00:00Z")
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        await repo.ingest_alert_safe(a1)
        await repo.ingest_alert_safe(a2)
        await session.commit()

    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        stats_before = await repo.get_summary_stats()
        assert stats_before["unread_count"] == 2

        count = await repo.mark_all_read()
        assert count == 2
        await session.commit()

        stats_after = await repo.get_summary_stats()
        assert stats_after["unread_count"] == 0
    await eng.dispose()


@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_20_summary_statistics_match_database():
    """20. Summary statistics match database contents."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        stats = await repo.get_summary_stats()
        assert stats["total_count"] == 543
        assert stats["w_breakouts"] == 278
        assert stats["m_breakdowns"] == 265
        assert stats["active_count"] + stats["target_hit_count"] + stats["invalidated_count"] <= 543
    await eng.dispose()


# ---------------------------------------------------------------------------
# Tests 21-24: WebSocket, Restart Persistence, JSON Read-Only & Active Scope
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage2_21_websocket_behavior_compatibility(tmp_path):
    """21. WebSocket broadcast payload maintains schema compatibility."""
    alert = _make_sample_alert()
    payload = alert.model_dump()
    assert "alert_id" in payload
    assert "pattern_type" in payload
    assert "breakout_candle_timestamp" in payload
    assert "measured_target" in payload
    assert "target_2" in payload
    assert "status" in payload


@pytest.mark.asyncio
async def test_stage2_22_restart_preserves_alerts_from_sqlite(tmp_path):
    """22. Restart / new session reloads all records directly from SQLite."""
    test_db = tmp_path / "restart_test.db"
    eng1, factory1 = create_engine_and_sessionmaker(test_db)
    await init_db(eng1)

    alert = _make_sample_alert(alert_id="mw_PERSIST_1")
    async with factory1() as session:
        repo = MWAlertRepository(session)
        await repo.ingest_alert_safe(alert)
        await session.commit()
    await eng1.dispose()

    # Restart: initialize fresh engine and sessionmaker on same file
    eng2, factory2 = create_engine_and_sessionmaker(test_db)
    async with factory2() as session:
        repo2 = MWAlertRepository(session)
        reloaded = await repo2.get_by_id(alert.alert_id)
        assert reloaded is not None
        assert reloaded.alert_id == alert.alert_id
        assert reloaded.symbol == alert.symbol
    await eng2.dispose()


def test_stage2_23_json_sha256_remains_identical():
    """23. JSON source remains strictly read-only and SHA-256 hash is unmodified."""
    with open(PROD_JSON_PATH, "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()
    assert current_hash == BASELINE_JSON_HASH, f"JSON hash changed! Expected {BASELINE_JSON_HASH}, got {current_hash}"


@pytest.mark.production_db
@pytest.mark.asyncio
async def test_stage2_24_active_lifecycle_queries_only_active_records():
    """24. get_active_alerts queries only active/open records, never terminal ones."""
    eng, sess_factory = create_engine_and_sessionmaker(PROD_DB_PATH)
    async with sess_factory() as session:
        repo = MWAlertRepository(session)
        active_alerts = await repo.get_active_alerts()
        # All returned alerts must be non-terminal
        for a in active_alerts:
            assert a.status in ["TARGET OPEN", "ACTIVE", "TARGET 1 HIT", "TARGET_1_HIT"]
            assert a.status not in ["TARGET 2 HIT", "TARGET_2_HIT", "SL HIT", "SL_HIT", "INVALIDATED"]
    await eng.dispose()
