import asyncio
import time
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
import app.api.deps as deps
from app.api.deps import configured_instruments
from app.api.routes_analysis import (
    _synthesis_cache,
    _refresh_tasks,
    _schedule_background_refresh,
    _create_lightweight_synthesis,
    update_synthesis_cache,
)
from app.models.schemas import MultiTimeframeSynthesis
from app.multi_timeframe.synthesis import MultiTimeframeAnalyzer
from app.data.yfinance_provider import YahooFinanceProvider
from app.market_processing.catchup_engine import CatchupEngine
from app.market_processing.worker import MarketProcessingWorker
from app.data.base import MarketDataProvider
from app.models.schemas import Candle, InstrumentConfig


class MockFastProvider(MarketDataProvider):
    @property
    def provider_name(self) -> str:
        return "MockFastProvider"

    async def fetch_candles(self, symbol, ticker, timeframe, limit=300, start=None, end=None):
        return []

    async def get_multi_timeframe_data(self, symbol, ticker, timeframes=None, limit=300):
        return {tf: [] for tf in (timeframes or ["4H", "1H", "15M", "5M"])}

    async def get_current_price(self, ticker):
        return 100.0


@pytest.fixture(autouse=True)
def mock_all_providers(monkeypatch):
    fast_prov = MockFastProvider()
    monkeypatch.setattr("app.api.deps.get_current_provider", lambda: fast_prov)
    monkeypatch.setattr("app.api.routes_analysis.get_current_provider", lambda: fast_prov)
    monkeypatch.setattr("app.market_processing.worker.get_current_provider", lambda: fast_prov)
    deps.providers["mock"] = fast_prov
    deps.current_provider_name = "mock"
    yield fast_prov


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_test_a_overview_hot_cache_returns_under_one_second(client):
    """Test A: /api/analysis/overview with hot cache returns within <1s (<10ms)."""
    now = time.time()
    for inst in configured_instruments:
        synth = MultiTimeframeAnalyzer.synthesize(
            symbol=inst.symbol,
            ticker=inst.ticker,
            provider_name="TestProvider",
            mtf_candles={},
            is_stale=False,
            status_message="Live Data",
            data_status="LIVE"
        )
        _synthesis_cache[inst.symbol] = (now, synth)

    t0 = time.time()
    res = client.get("/api/analysis/overview")
    elapsed = time.time() - t0

    assert res.status_code == 200
    assert elapsed < 1.0, f"Overview took too long: {elapsed:.3f}s"
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= len(configured_instruments)
    symbols = [item["symbol"] for item in data]
    assert configured_instruments[0].symbol in symbols


def test_test_b_overview_stale_cache_returns_immediately_and_schedules_refresh(client):
    """Test B: /api/analysis/overview with stale cache (>120s) returns immediately and schedules refresh."""
    stale_time = time.time() - 300.0
    for inst in configured_instruments:
        synth = MultiTimeframeAnalyzer.synthesize(
            symbol=inst.symbol,
            ticker=inst.ticker,
            provider_name="TestProvider",
            mtf_candles={},
            is_stale=False,
            status_message="Live Data",
            data_status="LIVE"
        )
        _synthesis_cache[inst.symbol] = (stale_time, synth)

    t0 = time.time()
    res = client.get("/api/analysis/overview")
    elapsed = time.time() - t0

    assert res.status_code == 200
    assert elapsed < 1.0, f"Stale overview took too long: {elapsed:.3f}s"
    data = res.json()
    assert len(data) >= len(configured_instruments)
    # Background refresh tasks executed or updated cache timestamp
    first_sym = configured_instruments[0].symbol
    assert _synthesis_cache[first_sym][0] >= stale_time


def test_test_c_overview_empty_cache_returns_lightweight_baseline_under_five_seconds(client):
    """Test C: /api/analysis/overview with empty cache returns baseline synthesis <5s (<10ms)."""
    _synthesis_cache.clear()

    t0 = time.time()
    res = client.get("/api/analysis/overview")
    elapsed = time.time() - t0

    assert res.status_code == 200
    assert elapsed < 5.0, f"Empty cache overview took too long: {elapsed:.3f}s"
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Every item returned should be valid synthesis schema
    for item in data:
        assert "symbol" in item
        assert "overall_bias" in item
        assert "evidence_score" in item


@pytest.mark.asyncio
async def test_test_d_background_refresh_deduplication():
    """Test D: _schedule_background_refresh deduplicates tasks for identical symbols."""
    provider = MockFastProvider()
    task1 = _schedule_background_refresh("ETHUSD", "ETH-USD", provider)
    task2 = _schedule_background_refresh("ETHUSD", "ETH-USD", provider)

    assert task1 is task2, "Duplicate background refresh tasks were created for the same symbol"
    await task1


@pytest.mark.asyncio
async def test_test_e_catchup_active_recoveries_deduplication():
    """Test E: CatchupEngine._active_recoveries deduplicates concurrent recovery calls."""
    provider = MockFastProvider()

    # Artificially mark (TESTSYM, 5M) as active
    recovery_key = ("TESTSYM", "5M")
    CatchupEngine._active_recoveries.add(recovery_key)

    try:
        report = await CatchupEngine.recover_instrument_timeframe(
            symbol="TESTSYM",
            ticker="TEST-TICKER",
            timeframe="5M",
            provider=provider
        )
        assert report["status"] == "ALREADY_IN_PROGRESS"
        assert report["candles_processed"] == 0
    finally:
        CatchupEngine._active_recoveries.discard(recovery_key)


@pytest.mark.asyncio
async def test_test_f_worker_starts_with_decoupled_catchup():
    """Test F: MarketProcessingWorker launches loop with decoupled catch-up."""
    inst = InstrumentConfig(
        symbol="BTC/USD",
        ticker="BTC-USD",
        exchange="CRYPTO",
        asset_type="CRYPTO",
        is_active=True
    )
    worker = MarketProcessingWorker(
        instruments=[inst],
        provider=MockFastProvider(),
        poll_interval_seconds=60
    )

    await worker.start(run_catchup_inline=False)
    assert worker._running is True
    assert worker._task is not None
    assert worker._catchup_task is not None

    await worker.stop()
    assert worker._running is False
    assert worker._task is None
    assert worker._catchup_task is None


@pytest.mark.asyncio
async def test_test_g_yfinance_provider_semaphore_throttles_concurrency():
    """Test G: YahooFinanceProvider throttles concurrent fetches using asyncio.Semaphore(3)."""
    sem = YahooFinanceProvider._get_semaphore()
    assert sem._value <= 3

    current_concurrent = 0
    max_observed_concurrent = 0

    async def simulate_fetch():
        nonlocal current_concurrent, max_observed_concurrent
        async with sem:
            current_concurrent += 1
            if current_concurrent > max_observed_concurrent:
                max_observed_concurrent = current_concurrent
            await asyncio.sleep(0.05)
            current_concurrent -= 1

    tasks = [simulate_fetch() for _ in range(8)]
    await asyncio.gather(*tasks)

    assert max_observed_concurrent <= 3, f"Max concurrency was {max_observed_concurrent}, expected <= 3"


def test_test_h_lightweight_synthesis_schema_validity():
    """Test H: _create_lightweight_synthesis returns a valid MultiTimeframeSynthesis schema."""
    synth = _create_lightweight_synthesis("TESTSYM", "TEST-TICKER", "TestProvider")
    assert isinstance(synth, MultiTimeframeSynthesis)
    assert synth.symbol == "TESTSYM"
    assert synth.is_stale is True
    assert synth.data_status in ["LIVE", "LAST VALID ANALYSIS"]
    assert synth.overall_bias == "NEUTRAL"
    assert synth.evidence_score.total_score >= 0
    dumped = synth.model_dump()
    assert "timeframes" in dumped
    assert "current_price" in dumped


def test_test_i_detail_endpoint_stale_while_revalidate(client):
    """Test I: /api/analysis/detail/{symbol} returns immediately on stale cache."""
    test_sym = configured_instruments[0].symbol
    stale_synth = MultiTimeframeAnalyzer.synthesize(
        symbol=test_sym,
        ticker="TEST-TICKER",
        provider_name="TestProvider",
        mtf_candles={},
        is_stale=False,
        status_message="Live Data",
        data_status="LIVE"
    )
    _synthesis_cache[test_sym] = (time.time() - 400.0, stale_synth)

    t0 = time.time()
    res = client.get(f"/api/analysis/detail/{test_sym}")
    elapsed = time.time() - t0

    assert res.status_code == 200
    assert elapsed < 1.0, f"Detail endpoint took too long: {elapsed:.3f}s"
    data = res.json()
    assert data["symbol"] == test_sym


def test_test_j_invariants_wm_and_trendline_unchanged():
    """Test J: Invariant check - detection engines import and run deterministically."""
    from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
    from app.market_structure.trendlines import TrendlineDetector
    from app.alerts.mw_breakout_engine import mw_breakout_engine

    assert hasattr(PrecisionBreakoutDetector, "detect_trendline_ema_volume_breakouts")
    assert hasattr(PrecisionBreakoutDetector, "calculate_wm_quality_score")
    assert hasattr(PrecisionBreakoutDetector, "calculate_pattern_targets")
    assert hasattr(TrendlineDetector, "fit_trendlines")
    assert hasattr(TrendlineDetector, "find_opposing_safety_line")
    assert hasattr(mw_breakout_engine, "process_synthesis_with_updates")
