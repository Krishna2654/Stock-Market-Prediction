import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from unittest.mock import AsyncMock, patch

from app.models.schemas import Candle, InstrumentConfig
from app.db.database import get_database_path, get_session_factory
from app.db.repository import CheckpointRepository, MWAlertRepository, StructureNotificationRepository
from app.market_processing.catchup_engine import CatchupEngine
from app.market_processing.worker import MarketProcessingWorker
from app.data.base import MarketDataProvider
from app.api.websocket import ws_manager


class MockMarketDataProvider(MarketDataProvider):
    """Controlled in-memory market data provider for recovery and worker tests."""

    def __init__(self, candles_map: Optional[Dict[str, List[Candle]]] = None):
        self._candles = candles_map or {}
        self._price = 24500.0

    @property
    def provider_name(self) -> str:
        return "Mock Provider (Test)"

    def set_candles(self, timeframe: str, candles: List[Candle]):
        self._candles[timeframe] = candles

    async def fetch_candles(
        self, symbol: str, ticker: str, timeframe: str, limit: int = 300
    ) -> List[Candle]:
        candles = self._candles.get(timeframe, [])
        return candles[-limit:] if limit else candles

    async def get_multi_timeframe_data(
        self, symbol: str, ticker: str, timeframes: List[str] = ["4H", "1H", "15M", "5M"], limit: int = 300
    ) -> Dict[str, List[Candle]]:
        return {
            tf: self._candles.get(tf, [])[-limit:] if limit else self._candles.get(tf, [])
            for tf in timeframes
        }

    async def get_current_price(self, ticker: str) -> Optional[float]:
        return self._price


def _generate_synthetic_candles(
    count: int = 50,
    start_dt: Optional[datetime] = None,
    step_minutes: int = 15,
    base_price: float = 1000.0
) -> List[Candle]:
    """Generates valid closed chronological candles with realistic swing dynamics."""
    start = start_dt or (datetime.now(timezone.utc) - timedelta(minutes=step_minutes * count + 60))
    candles = []
    price = base_price
    for i in range(count):
        candle_dt = start + timedelta(minutes=i * step_minutes)
        c_open = price
        # Gentle oscillation
        c_high = c_open + 5.0 + (i % 3)
        c_low = c_open - 4.0 - (i % 2)
        c_close = c_open + (1.5 if i % 2 == 0 else -1.0)
        vol = 1000.0 + (i * 10.0)
        candles.append(Candle(
            timestamp=candle_dt.isoformat(),
            open=round(c_open, 2),
            high=round(c_high, 2),
            low=round(c_low, 2),
            close=round(c_close, 2),
            volume=vol
        ))
        price = c_close
    return candles


# ---------------------------------------------------------------------------
# 1. Checkpoint Table & Repository CRUD Tests
# ---------------------------------------------------------------------------

def test_01_checkpoint_sync_crud():
    """Verifies synchronous checkpoint get, create, update, and conflict resolution."""
    symbol = "TEST_RECOVERY_SYM"
    tf = "15M"

    # Initial get -> None
    cp0 = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp0 is None

    # Insert checkpoint
    ts1 = "2026-09-09T09:15:00+00:00"
    res1 = CheckpointRepository.update_checkpoint_sync(
        symbol=symbol,
        timeframe=tf,
        last_candle_timestamp=ts1,
        processed_count=10,
        status="SYNCED"
    )
    assert res1 is True

    cp1 = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp1 is not None
    assert cp1.symbol == symbol
    assert cp1.timeframe == tf
    assert cp1.last_processed_candle_timestamp == ts1
    assert cp1.candles_processed_count == 10
    assert cp1.checkpoint_status == "SYNCED"

    # Update checkpoint (upsert on conflict)
    ts2 = "2026-09-09T10:00:00+00:00"
    res2 = CheckpointRepository.update_checkpoint_sync(
        symbol=symbol,
        timeframe=tf,
        last_candle_timestamp=ts2,
        processed_count=5,
        status="SYNCED"
    )
    assert res2 is True

    cp2 = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp2.last_processed_candle_timestamp == ts2
    assert cp2.candles_processed_count == 15
    assert cp2.checkpoint_status == "SYNCED"


@pytest.mark.asyncio
async def test_02_checkpoint_async_crud():
    """Verifies asynchronous checkpoint operations with SQLAlchemy session."""
    factory = get_session_factory()
    async with factory() as session:
        repo = CheckpointRepository(session)
        symbol = "ASYNC_SYM"
        tf = "1H"

        cp0 = await repo.get_checkpoint(symbol, tf)
        assert cp0 is None

        ts = "2026-09-10T12:00:00+00:00"
        saved = await repo.update_checkpoint(
            symbol=symbol,
            timeframe=tf,
            last_candle_timestamp=ts,
            processed_count=20,
            status="SYNCED"
        )
        assert saved.symbol == symbol
        assert saved.last_processed_candle_timestamp == ts
        assert saved.candles_processed_count == 20

        fetched = await repo.get_checkpoint(symbol, tf)
        assert fetched is not None
        assert fetched.last_processed_candle_timestamp == ts


# ---------------------------------------------------------------------------
# 2. Missed-Candle Catch-Up & Historical Replay Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_03_catchup_bootstrap_initialization():
    """Verifies initial bootstrap when no previous checkpoint exists."""
    symbol = "BOOTSTRAP_SYM"
    tf = "15M"
    candles = _generate_synthetic_candles(count=20, step_minutes=15)
    provider = MockMarketDataProvider({"15M": candles})

    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol,
        ticker=symbol,
        timeframe=tf,
        provider=provider
    )

    assert report["status"] == "BOOTSTRAP_COMPLETE"
    assert report["candles_processed"] == 20
    assert report["last_checkpoint"] == candles[-1].timestamp

    # Verify checkpoint stored in DB
    cp = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp is not None
    assert cp.last_processed_candle_timestamp == candles[-1].timestamp
    assert cp.checkpoint_status == "SYNCED"


@pytest.mark.asyncio
async def test_04_catchup_multi_day_gap_chronological_replay():
    """
    Simulates a 2-day offline gap:
    Checkpoint is at bar 10. Provider returns 40 bars (30 missed bars).
    CatchupEngine replays all 30 missed bars in order and advances checkpoint to bar 40.
    """
    symbol = "GAP_REPLAY_SYM"
    tf = "15M"
    all_candles = _generate_synthetic_candles(count=40, step_minutes=15)

    # Pre-seed checkpoint at candle index 9 (10th candle)
    initial_checkpoint_candle = all_candles[9]
    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol,
        timeframe=tf,
        last_candle_timestamp=initial_checkpoint_candle.timestamp,
        processed_count=10,
        status="SYNCED"
    )

    provider = MockMarketDataProvider({"15M": all_candles})

    # Run catch-up
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol,
        ticker=symbol,
        timeframe=tf,
        provider=provider
    )

    assert report["status"] == "RECOVERY_COMPLETE"
    assert report["candles_processed"] == 30
    assert report["last_checkpoint"] == all_candles[-1].timestamp

    # Verify final checkpoint in DB
    final_cp = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert final_cp.last_processed_candle_timestamp == all_candles[-1].timestamp
    assert final_cp.candles_processed_count == 40
    assert final_cp.checkpoint_status == "SYNCED"


@pytest.mark.asyncio
async def test_05_catchup_idempotency_zero_duplicates():
    """
    Verifies that running catch-up multiple times over the exact same data
    produces ZERO duplicates in database and reports ALREADY_UP_TO_DATE.
    """
    symbol = "IDEMPOTENT_SYM"
    tf = "15M"
    candles = _generate_synthetic_candles(count=25, step_minutes=15)
    provider = MockMarketDataProvider({"15M": candles})

    # Pass 1: Bootstrap
    rep1 = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker=symbol, timeframe=tf, provider=provider
    )
    assert rep1["status"] == "BOOTSTRAP_COMPLETE"

    # Pass 2: Exact same candles -> ALREADY_UP_TO_DATE
    rep2 = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker=symbol, timeframe=tf, provider=provider
    )
    assert rep2["status"] == "ALREADY_UP_TO_DATE"
    assert rep2["candles_processed"] == 0

    # Pass 3: Another run -> still ALREADY_UP_TO_DATE
    rep3 = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker=symbol, timeframe=tf, provider=provider
    )
    assert rep3["status"] == "ALREADY_UP_TO_DATE"
    assert rep3["candles_processed"] == 0


@pytest.mark.asyncio
async def test_06_checkpoint_does_not_advance_on_processing_failure():
    """
    Verifies that if an error occurs while processing a candle slice,
    the checkpoint does NOT advance to the failed candle and is marked RECOVERING.
    """
    symbol = "FAIL_SAFE_SYM"
    tf = "15M"
    candles = _generate_synthetic_candles(count=15, step_minutes=15)

    # Seed initial checkpoint at index 4
    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol,
        timeframe=tf,
        last_candle_timestamp=candles[4].timestamp,
        processed_count=5,
        status="SYNCED"
    )

    provider = MockMarketDataProvider({"15M": candles})

    # Mock _process_and_persist_slice to fail on candle index 7
    call_count = 0
    original_fn = CatchupEngine._process_and_persist_slice

    def mock_process_slice(slice_candles, sym, tick, tframe, is_catchup=True):
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            raise RuntimeError("Simulated Database / Processing Fault")
        return original_fn(slice_candles, sym, tick, tframe, is_catchup=is_catchup)

    with patch.object(CatchupEngine, "_process_and_persist_slice", side_effect=mock_process_slice):
        report = await CatchupEngine.recover_instrument_timeframe(
            symbol=symbol, ticker=symbol, timeframe=tf, provider=provider
        )

    # Should process 2 candles before stopping at failure
    assert report["candles_processed"] == 2
    # Checkpoint must NOT have advanced past the last successfully processed candle (index 6)
    cp = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp.last_processed_candle_timestamp == candles[6].timestamp
    assert cp.checkpoint_status == "RECOVERING"


# ---------------------------------------------------------------------------
# 3. Continuous Background Worker Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_07_worker_lifecycle_start_and_stop():
    """Verifies that MarketProcessingWorker starts, runs, and stops cleanly."""
    inst = InstrumentConfig(symbol="WORKER_TEST", ticker="WORKER_TEST", exchange="NSE", asset_type="EQUITY", is_active=True)
    candles = _generate_synthetic_candles(count=30, step_minutes=15)
    provider = MockMarketDataProvider({
        "4H": candles, "1H": candles, "15M": candles, "5M": candles
    })

    worker = MarketProcessingWorker(
        instruments=[inst],
        provider=provider,
        poll_interval_seconds=1
    )

    assert not worker._running
    await worker.start(run_catchup_inline=True)
    assert worker._running
    assert worker._task is not None

    # Let worker run one cycle
    await asyncio.sleep(0.5)

    # Stop cleanly
    await worker.stop()
    assert not worker._running
    assert worker._task is None


@pytest.mark.asyncio
async def test_08_worker_runs_without_active_websocket_clients():
    """
    Verifies that when zero WebSocket clients are connected,
    the background worker still processes market data, persists events,
    and updates checkpoints in SQLite without throwing errors.
    """
    ws_manager.active_connections.clear()
    assert len(ws_manager.active_connections) == 0

    inst = InstrumentConfig(symbol="HEADLESS_SYM", ticker="HEADLESS_SYM", exchange="NSE", asset_type="EQUITY", is_active=True)
    candles = _generate_synthetic_candles(count=30, step_minutes=15)
    provider = MockMarketDataProvider({
        "4H": candles, "1H": candles, "15M": candles, "5M": candles
    })

    worker = MarketProcessingWorker(
        instruments=[inst],
        provider=provider,
        poll_interval_seconds=1
    )

    synthesis = await worker.process_instrument(inst, provider)
    assert synthesis is not None
    assert synthesis.symbol == "HEADLESS_SYM"

    # Checkpoint must be advanced in DB
    cp = CheckpointRepository.get_checkpoint_sync("HEADLESS_SYM", "15M")
    assert cp is not None
    assert cp.last_processed_candle_timestamp == candles[-1].timestamp
    assert cp.checkpoint_status == "SYNCED"


@pytest.mark.asyncio
async def test_09_recover_all_instruments():
    """Verifies multi-instrument catchup across multiple timeframes."""
    inst1 = InstrumentConfig(symbol="INST_1", ticker="INST_1", exchange="NSE", asset_type="EQUITY", is_active=True)
    inst2 = InstrumentConfig(symbol="INST_2", ticker="INST_2", exchange="NSE", asset_type="EQUITY", is_active=True)
    candles = _generate_synthetic_candles(count=20, step_minutes=15)

    provider = MockMarketDataProvider({
        "4H": candles, "1H": candles, "15M": candles, "5M": candles
    })

    report = await CatchupEngine.recover_all_instruments(
        instruments=[inst1, inst2],
        provider=provider,
        timeframes=["15M", "5M"]
    )

    assert report["total_candles_processed"] >= 40
    assert len(report["results"]) == 4  # 2 instruments * 2 timeframes
