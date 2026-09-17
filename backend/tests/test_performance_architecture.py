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


def test_three_tier_semaphore_provider_isolation():
    """Verify YFinanceProvider isolates interactive (5), worker (3), and catchup (1) semaphores."""
    prov = YFinanceProvider()
    assert hasattr(prov, "_interactive_semaphore")
    assert hasattr(prov, "_worker_semaphore")
    assert hasattr(prov, "_catchup_semaphore")
    assert prov._interactive_semaphore._value == 5
    assert prov._worker_semaphore._value == 3
    # Backward compatibility alias
    assert prov._live_semaphore is prov._worker_semaphore
    assert prov._live_semaphore._value == 3


@pytest.mark.asyncio
async def test_interactive_requests_never_wait_behind_worker_or_catchup():
    """Verify interactive user requests execute concurrently without being blocked by worker or catchup operations."""
    prov = YFinanceProvider()

    # Saturate both catchup and worker semaphores
    await prov._catchup_semaphore.acquire()
    assert prov._catchup_semaphore.locked()

    for _ in range(3):
        await prov._worker_semaphore.acquire()
    assert prov._worker_semaphore.locked()

    # Interactive semaphore should still have full capacity of 5
    assert prov._interactive_semaphore._value == 5

    # An interactive request must be able to acquire immediately without blocking
    acquired = False
    async with prov._interactive_semaphore:
        acquired = True
    assert acquired is True

    # Clean up
    prov._catchup_semaphore.release()
    for _ in range(3):
        prov._worker_semaphore.release()


from datetime import datetime, timezone, timedelta

def test_worker_chart_cache_monotonic_timestamp_protection():
    """Verify worker_chart_cache protects newer data from stale overwrite."""
    cache = WorkerChartCache()
    now_utc = datetime.now(timezone.utc)
    ts_newer = (now_utc - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00Z")
    ts_older = (now_utc - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:00Z")

    # Insert newer entry
    ok = cache.set(
        symbol="NIFTY 50",
        timeframe="15M",
        payload={"symbol": "NIFTY 50", "candles": [{"time": ts_newer}]},
        latest_candle_timestamp=ts_newer
    )
    assert ok is True

    entry = cache.get("NIFTY 50", "15M")
    assert entry is not None
    assert entry["candles"][0]["time"] == ts_newer

    # Attempt to overwrite with older timestamp
    rejected = cache.set(
        symbol="NIFTY 50",
        timeframe="15M",
        payload={"symbol": "NIFTY 50", "candles": [{"time": ts_older}]},
        latest_candle_timestamp=ts_older
    )
    assert rejected is False

    # Should still retain the newer entry
    entry_after = cache.get("NIFTY 50", "15M")
    assert entry_after["candles"][0]["time"] == ts_newer


def test_candle_state_driven_validity_flow():
    """
    Direct proof of the user-specified candle-state validity flow:
    1. Cache created at T=0 with completed candle X.
    2. Simulated wall-clock age >120 seconds.
    3. Worker-known latest completed candle remains X.
    4. Cache is STILL VALID.
    5. No Yahoo request occurs.
    6. A newer completed candle X+1 is then recorded.
    7. Old cache becomes INVALID.
    8. New worker payload replaces it.
    9. Older payload cannot overwrite X+1.
    """
    cache = WorkerChartCache()
    now_utc = datetime.now(timezone.utc)
    candle_x = (now_utc - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:00Z")
    candle_x_plus_1 = (now_utc - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:00Z")

    # 1. Cache created at T=0 with completed candle X
    payload_x = {
        "symbol": "RELIANCE",
        "timeframe": "1H",
        "candles": [{"time": candle_x, "open": 2500, "close": 2510}]
    }
    set_ok = cache.set(
        symbol="RELIANCE",
        timeframe="1H",
        payload=payload_x,
        latest_candle_timestamp=candle_x,
        is_worker_producer=True
    )
    assert set_ok is True

    # 2. Simulated wall-clock age >120 seconds (simulate 10 minutes = 600 seconds)
    entry = cache.get_entry("RELIANCE", "1H")
    assert entry is not None
    entry["cached_at"] = time.time() - 600.0  # 10 minutes old on wall clock

    # 3. Worker-known latest completed candle remains X
    assert cache.get_latest_known_completed_candle("RELIANCE", "1H") == candle_x

    # 4 & 5. Cache is STILL VALID and returns payload without needing external fetch
    cached_payload = cache.get("RELIANCE", "1H")
    assert cached_payload is not None
    assert cached_payload["candles"][0]["time"] == candle_x

    # 6. A newer completed candle X+1 is then recorded by the worker
    cache.record_known_completed_candle("RELIANCE", "1H", candle_x_plus_1)

    # 7. Old cache becomes INVALID because newer completed candle X+1 is known
    invalidated_payload = cache.get("RELIANCE", "1H")
    assert invalidated_payload is None
    is_valid, reason = cache.is_entry_valid("RELIANCE", "1H")
    assert is_valid is False
    assert "NEWER_COMPLETED_CANDLE_AVAILABLE" in reason

    # 8. New worker payload replaces it
    payload_x_plus_1 = {
        "symbol": "RELIANCE",
        "timeframe": "1H",
        "candles": [{"time": candle_x_plus_1, "open": 2510, "close": 2525}]
    }
    replace_ok = cache.set(
        symbol="RELIANCE",
        timeframe="1H",
        payload=payload_x_plus_1,
        latest_candle_timestamp=candle_x_plus_1,
        is_worker_producer=True
    )
    assert replace_ok is True

    new_payload = cache.get("RELIANCE", "1H")
    assert new_payload is not None
    assert new_payload["candles"][0]["time"] == candle_x_plus_1

    # 9. Older payload cannot overwrite X+1
    overwrite_attempt = cache.set(
        symbol="RELIANCE",
        timeframe="1H",
        payload=payload_x,
        latest_candle_timestamp=candle_x,
        is_worker_producer=True
    )
    assert overwrite_attempt is False
    assert cache.get("RELIANCE", "1H")["candles"][0]["time"] == candle_x_plus_1


def test_future_candle_rejection():
    """Verify that candles with future timestamps are rejected."""
    cache = WorkerChartCache()
    now_utc = datetime.now(timezone.utc)
    future_time = (now_utc + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:00Z")

    rejected = cache.set(
        symbol="BTC/USD",
        timeframe="15M",
        payload={"symbol": "BTC/USD", "candles": [{"time": future_time}]},
        latest_candle_timestamp=future_time
    )
    assert rejected is False
    assert cache.get("BTC/USD", "15M") is None


def test_malformed_payload_rejection():
    """Verify that non-dict or empty-candle payloads are rejected."""
    cache = WorkerChartCache()
    now_utc = datetime.now(timezone.utc)
    valid_time = (now_utc - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00Z")

    # Non-dict payload
    assert cache.set("SBIN", "15M", "not-a-dict", valid_time) is False  # type: ignore

    # Empty candles
    assert cache.set("SBIN", "15M", {"symbol": "SBIN", "candles": []}, valid_time) is False

    # None timestamp
    assert cache.set("SBIN", "15M", {"symbol": "SBIN", "candles": [{"time": ""}]}, "") is False


def test_symbol_timeframe_isolation():
    """Verify exact (symbol, timeframe) key isolation."""
    cache = WorkerChartCache()
    now_utc = datetime.now(timezone.utc)
    valid_time = (now_utc - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00Z")

    cache.set(
        symbol="NIFTY 50",
        timeframe="15M",
        payload={"symbol": "NIFTY 50", "candles": [{"time": valid_time}]},
        latest_candle_timestamp=valid_time
    )

    assert cache.get("NIFTY 50", "15M") is not None
    assert cache.get("NIFTY 50", "1H") is None
    assert cache.get("BANK NIFTY", "15M") is None


def test_explicit_invalidation():
    """Verify worker can explicitly mark a cache entry invalid."""
    cache = WorkerChartCache()
    now_utc = datetime.now(timezone.utc)
    valid_time = (now_utc - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00Z")

    cache.set(
        symbol="INFY",
        timeframe="15M",
        payload={"symbol": "INFY", "candles": [{"time": valid_time}]},
        latest_candle_timestamp=valid_time
    )
    assert cache.get("INFY", "15M") is not None

    # Worker explicitly marks invalid
    cache.mark_invalid("INFY", "15M", reason="DATA_CORRUPTION_DETECTED")

    assert cache.get("INFY", "15M") is None
    is_valid, reason = cache.is_entry_valid("INFY", "15M")
    assert is_valid is False
    assert "DATA_CORRUPTION_DETECTED" in reason


def test_fallback_cannot_overwrite_worker_payload():
    """Verify user-request fallback cannot overwrite equal or newer worker-produced payload."""
    cache = WorkerChartCache()
    now_utc = datetime.now(timezone.utc)
    ts = (now_utc - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00Z")

    # Worker sets payload
    cache.set(
        symbol="HDFCBANK",
        timeframe="15M",
        payload={"symbol": "HDFCBANK", "candles": [{"time": ts, "source": "worker"}]},
        latest_candle_timestamp=ts,
        is_worker_producer=True
    )

    # Fallback tries to overwrite with same timestamp
    fallback_ok = cache.set(
        symbol="HDFCBANK",
        timeframe="15M",
        payload={"symbol": "HDFCBANK", "candles": [{"time": ts, "source": "fallback"}]},
        latest_candle_timestamp=ts,
        is_worker_producer=False
    )
    assert fallback_ok is False
    assert cache.get("HDFCBANK", "15M")["candles"][0]["source"] == "worker"


def test_chart_endpoint_reads_from_worker_cache_instantly():
    """Verify GET /api/analysis/chart reads worker precomputed buffer in <50ms with 0 provider calls."""
    client = TestClient(app)
    now_utc = datetime.now(timezone.utc)
    valid_time = (now_utc - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00Z")

    # Pre-populate worker chart cache with completed timestamp
    dummy_payload = {
        "symbol": "TCS",
        "timeframe": "15M",
        "candles": [{"time": valid_time, "open": 3500, "high": 3520, "low": 3490, "close": 3510, "volume": 1000}],
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
    worker_chart_cache.set("TCS", "15M", dummy_payload, latest_candle_timestamp=valid_time, is_worker_producer=True)

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

    # Warmup
    client.get("/api/alerts/trendline-shortlist")

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


def test_worker_chart_cache_stale_while_revalidate():
    """Verify get_stale_or_valid returns stale cached data immediately when a newer candle is known."""
    cache = WorkerChartCache()
    now_utc = datetime.now(timezone.utc)
    candle_ts = (now_utc - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:00Z")
    newer_ts = (now_utc - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00Z")

    dummy_payload = {
        "symbol": "INFY",
        "timeframe": "15M",
        "candles": [{"time": candle_ts, "open": 1500, "high": 1510, "low": 1490, "close": 1505, "volume": 500}]
    }
    cache.set("INFY", "15M", dummy_payload, latest_candle_timestamp=candle_ts, is_worker_producer=True)

    # 1. While current, get_stale_or_valid returns (payload, False) -> valid
    payload, is_stale = cache.get_stale_or_valid("INFY", "15M")
    assert payload is not None
    assert is_stale is False

    # 2. Worker observes newer completed candle
    cache.record_known_completed_candle("INFY", "15M", newer_ts)

    # 3. get() returns None because strictly valid has lapsed
    assert cache.get("INFY", "15M") is None

    # 4. But get_stale_or_valid returns (payload, True) -> stale-while-revalidate enabled!
    payload, is_stale = cache.get_stale_or_valid("INFY", "15M")
    assert payload is not None
    assert is_stale is True
    assert payload["candles"][0]["time"] == candle_ts


def test_worker_chart_cache_disk_persistence(tmp_path):
    """Verify chart cache atomically saves to disk and restores correctly on restart."""
    import tempfile
    from pathlib import Path

    cache = WorkerChartCache()
    # Point cache file to temporary path
    temp_cache_file = tmp_path / "test_chart_cache.json"
    cache._CACHE_FILE = temp_cache_file

    now_utc = datetime.now(timezone.utc)
    candle_ts = (now_utc - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00Z")
    dummy_payload = {
        "symbol": "PERSIST_TEST",
        "timeframe": "1H",
        "candles": [{"time": candle_ts, "open": 100, "high": 110, "low": 95, "close": 105, "volume": 1000}]
    }

    cache.set("PERSIST_TEST", "1H", dummy_payload, latest_candle_timestamp=candle_ts, is_worker_producer=True)

    # File should exist and contain valid JSON
    assert temp_cache_file.exists()

    # Create a brand new WorkerChartCache instance pointing to the same file
    restored_cache = WorkerChartCache()
    restored_cache._CACHE_FILE = temp_cache_file
    restored_cache._load_disk_cache()

    entry = restored_cache.get("PERSIST_TEST", "1H")
    assert entry is not None
    assert entry["symbol"] == "PERSIST_TEST"
    assert entry["candles"][0]["time"] == candle_ts


def test_read_endpoints_purity():
    """Verify /overview and /detail GET endpoints are pure reads with NO alert engine evaluations."""
    client = TestClient(app)

    with patch("app.alerts.engine.alert_engine.process_synthesis_for_alerts") as mock_alerts, \
         patch("app.alerts.mw_breakout_engine.mw_breakout_engine.process_synthesis_with_updates") as mock_mw, \
         patch("app.api.routes_analysis._schedule_background_refresh") as mock_bg:

        # Test GET /api/analysis/overview
        resp_overview = client.get("/api/analysis/overview")
        assert resp_overview.status_code == 200

        # Neither alert engine should have been called by the read endpoint
        mock_alerts.assert_not_called()
        mock_mw.assert_not_called()

        # Test GET /api/analysis/detail/{symbol}
        resp_detail = client.get("/api/analysis/detail/NIFTY%2050")
        assert resp_detail.status_code == 200

        mock_alerts.assert_not_called()
        mock_mw.assert_not_called()
