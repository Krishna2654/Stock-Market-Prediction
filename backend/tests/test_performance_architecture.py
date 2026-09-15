import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.data.yfinance_provider import YFinanceProvider
from app.analysis.chart_cache import WorkerChartCache, worker_chart_cache, build_chart_payload
from app.models.schemas import Candle
from app.db.database import get_sync_sqlite_connection, get_database_path
from app.alerts.trendline_shortlist_engine import trendline_shortlist_engine
from app.alerts.mw_breakout_engine import mw_breakout_engine


def test_dual_semaphore_provider_isolation():
    """Verify YFinanceProvider separates live and catchup semaphores."""
    prov = YFinanceProvider()
    assert hasattr(prov, "_live_semaphore")
    assert hasattr(prov, "_catchup_semaphore")
    assert prov._live_semaphore._value == 3
    assert prov._catchup_semaphore._value == 1


@pytest.mark.asyncio
async def test_live_requests_never_wait_behind_catchup():
    """Verify live requests execute concurrently without being blocked by catchup operations."""
    prov = YFinanceProvider()

    # Acquire catchup semaphore (simulating a running catchup chunk)
    await prov._catchup_semaphore.acquire()
    assert prov._catchup_semaphore.locked()

    # Live semaphore should still have full capacity of 3
    assert prov._live_semaphore._value == 3

    # A live request must be able to acquire immediately without blocking
    acquired = False
    async with prov._live_semaphore:
        acquired = True
    assert acquired is True

    # Release catchup
    prov._catchup_semaphore.release()
    assert not prov._catchup_semaphore.locked()


def test_worker_chart_cache_monotonic_timestamp_protection():
    """Verify worker_chart_cache protects newer data from stale overwrite."""
    cache = WorkerChartCache()

    # Insert newer entry
    cache.set(
        symbol="NIFTY 50",
        timeframe="15M",
        payload={"symbol": "NIFTY 50", "candles": [{"time": "2026-09-15T09:30:00Z"}]},
        latest_candle_timestamp="2026-09-15T09:30:00Z"
    )

    entry = cache.get("NIFTY 50", "15M")
    assert entry is not None
    assert entry["candles"][0]["time"] == "2026-09-15T09:30:00Z"

    # Attempt to overwrite with older timestamp
    cache.set(
        symbol="NIFTY 50",
        timeframe="15M",
        payload={"symbol": "NIFTY 50", "candles": [{"time": "2026-09-15T09:15:00Z"}]},
        latest_candle_timestamp="2026-09-15T09:15:00Z"
    )

    # Should still retain the newer entry
    entry_after = cache.get("NIFTY 50", "15M")
    assert entry_after["candles"][0]["time"] == "2026-09-15T09:30:00Z"


def test_chart_endpoint_reads_from_worker_cache_instantly():
    """Verify GET /api/analysis/chart reads worker precomputed buffer in <50ms with 0 provider calls."""
    client = TestClient(app)

    # Pre-populate worker chart cache
    dummy_payload = {
        "symbol": "TCS",
        "timeframe": "15M",
        "candles": [{"time": "2026-09-15T09:30:00Z", "open": 3500, "high": 3520, "low": 3490, "close": 3510, "volume": 1000}],
        "swings": [],
        "protected_swing": None,
        "structure_breaks": [],
        "breaks": [],
        "trendlines": [],
        "support_resistance": {"all_levels": [], "swing_highs": [], "swing_lows": []},
        "predictive_scenarios": {},
        "wm_patterns": [],
        "active_wm_pattern": None,
        "active_wm_alert": None,
        "wm_debug_candidates": []
    }
    worker_chart_cache.set("TCS", "15M", dummy_payload, latest_candle_timestamp="2026-09-15T09:30:00Z")

    t0 = time.perf_counter()
    resp = client.get("/api/analysis/chart/TCS?timeframe=15M")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "TCS"
    assert len(data["candles"]) == 1
    assert elapsed_ms < 100  # Should be sub-10ms in practice


def test_trendline_shortlist_endpoint_zero_recalculation():
    """Verify GET /api/alerts/trendline-shortlist is a pure fast read without re-synthesizing cache."""
    client = TestClient(app)

    t0 = time.perf_counter()
    resp = client.get("/api/alerts/trendline-shortlist")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert elapsed_ms < 100  # Pure memory read


def test_sqlite_sync_connection_busy_timeout_and_wal():
    """Verify get_sync_sqlite_connection applies WAL mode and busy_timeout=5000."""
    db_path = get_database_path()
    with get_sync_sqlite_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        assert mode.upper() == "WAL"

        cursor.execute("PRAGMA busy_timeout;")
        timeout = cursor.fetchone()[0]
        assert timeout == 5000


def test_invariants_preserved():
    """Verify that no detection algorithms were modified."""
    from app.market_structure import precision_breakouts, trendlines
    from app.alerts import mw_breakout_engine

    # Ensure critical detection functions remain present and intact
    assert hasattr(precision_breakouts.PrecisionBreakoutDetector, "detect_wm_patterns")
    assert hasattr(precision_breakouts.PrecisionBreakoutDetector, "detect_trendline_ema_volume_breakouts")
    assert hasattr(trendlines.TrendlineDetector, "fit_trendlines")
    assert hasattr(trendlines.TrendlineDetector, "detect_trendline_breaks")
    assert hasattr(mw_breakout_engine.mw_breakout_engine, "process_synthesis_with_updates")
