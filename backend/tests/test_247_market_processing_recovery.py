import asyncio
import pytest
from datetime import datetime, timezone, timedelta, time as dtime
import zoneinfo
from typing import List, Dict, Optional
from unittest.mock import AsyncMock, patch

from app.models.schemas import Candle, InstrumentConfig
from app.db.database import get_database_path, get_session_factory
from app.db.repository import CheckpointRepository, MWAlertRepository, StructureNotificationRepository
from app.market_processing.catchup_engine import CatchupEngine
from app.market_processing.worker import MarketProcessingWorker
from app.data.base import MarketDataProvider
from app.api.websocket import ws_manager

KOLKATA_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")


class MockMarketDataProvider(MarketDataProvider):
    """Controlled in-memory market data provider for recovery and worker tests."""

    def __init__(
        self,
        candles_map: Optional[Dict[str, List[Candle]]] = None,
        chunk_size: Optional[int] = None,
        fail_on_call: Optional[int] = None,
        return_newest_page_first: bool = False
    ):
        self._candles = candles_map or {}
        self._price = 24500.0
        self._chunk_size = chunk_size
        self._fail_on_call = fail_on_call
        self._call_count = 0
        self._return_newest_page_first = return_newest_page_first

    @property
    def provider_name(self) -> str:
        return "Mock Provider (Test)"

    def set_candles(self, timeframe: str, candles: List[Candle]):
        self._candles[timeframe] = candles

    async def fetch_candles(
        self,
        symbol: str,
        ticker: str,
        timeframe: str,
        limit: int = 300,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[Candle]:
        self._call_count += 1
        if self._fail_on_call is not None and self._call_count == self._fail_on_call:
            raise RuntimeError(f"Simulated network/provider failure on call {self._call_count}")

        candles = list(self._candles.get(timeframe, []))

        # Filter by start / end if provided
        if start is not None or end is not None:
            filtered = []
            for c in candles:
                c_dt = CatchupEngine._parse_timestamp(c.timestamp)
                if start is not None and c_dt < start:
                    continue
                if end is not None and c_dt > end:
                    continue
                filtered.append(c)
            candles = filtered

        eff_limit = self._chunk_size or limit

        if self._return_newest_page_first and end is None and eff_limit and len(candles) > eff_limit:
            return candles[-eff_limit:]

        if eff_limit and len(candles) > eff_limit:
            if start is not None and not self._return_newest_page_first:
                candles = candles[:eff_limit]
            else:
                candles = candles[-eff_limit:]

        return candles

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


def _generate_crypto_candles(count: int, step_minutes: int, start_dt: Optional[datetime] = None) -> List[Candle]:
    """Generates contiguous 24/7 crypto candles."""
    base_dt = start_dt or (datetime.now(timezone.utc) - timedelta(minutes=step_minutes * count + 60))
    candles = []
    price = 65000.0
    for i in range(count):
        c_dt = base_dt + timedelta(minutes=i * step_minutes)
        c_open = price
        c_high = c_open + 25.0
        c_low = c_open - 20.0
        c_close = c_open + (10.0 if i % 2 == 0 else -8.0)
        candles.append(Candle(
            timestamp=c_dt.isoformat(),
            open=round(c_open, 2),
            high=round(c_high, 2),
            low=round(c_low, 2),
            close=round(c_close, 2),
            volume=150.0
        ))
        price = c_close
    return candles


def _generate_nse_candles(trading_days: int = 4, step_minutes: int = 5) -> List[Candle]:
    """Generates session-bound NSE candles starting from past Monday at 09:15 IST."""
    curr = datetime(2026, 8, 24, 9, 15, tzinfo=KOLKATA_TZ)
    candles = []
    days_done = 0
    price = 2500.0
    while days_done < trading_days:
        if curr.weekday() < 5:  # Mon-Fri
            market_close = datetime.combine(curr.date(), dtime(15, 30), tzinfo=KOLKATA_TZ)
            c_time = curr
            while c_time < market_close:
                c_open = price
                c_high = c_open + 5.0
                c_low = c_open - 4.0
                c_close = c_open + 1.0
                candles.append(Candle(
                    timestamp=c_time.isoformat(),
                    open=round(c_open, 2),
                    high=round(c_high, 2),
                    low=round(c_low, 2),
                    close=round(c_close, 2),
                    volume=5000.0
                ))
                price = c_close
                c_time += timedelta(minutes=step_minutes)
            days_done += 1
        next_day = curr.date() + timedelta(days=1)
        curr = datetime.combine(next_day, dtime(9, 15), tzinfo=KOLKATA_TZ)
    return candles


# ---------------------------------------------------------------------------
# 1. Checkpoint Table & Repository CRUD Tests
# ---------------------------------------------------------------------------

def test_01_checkpoint_sync_crud():
    """Verifies synchronous checkpoint get, create, update, and conflict resolution."""
    symbol = "TEST_RECOVERY_SYM"
    tf = "15M"

    cp0 = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp0 is None

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


def test_02_checkpoint_status_transitions():
    """Verifies valid status updates including RECOVERING and GAP_DETECTED."""
    symbol = "STATUS_TRANS_SYM"
    tf = "5M"

    CheckpointRepository.update_checkpoint_sync(symbol, tf, "2026-09-09T09:15:00+00:00", 1, "SYNCED")
    cp = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp.checkpoint_status == "SYNCED"

    CheckpointRepository.update_checkpoint_sync(symbol, tf, "2026-09-09T09:20:00+00:00", 1, "RECOVERING")
    cp = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp.checkpoint_status == "RECOVERING"

    CheckpointRepository.update_checkpoint_sync(symbol, tf, "2026-09-09T09:25:00+00:00", 1, "GAP_DETECTED")
    cp = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp.checkpoint_status == "GAP_DETECTED"


# ---------------------------------------------------------------------------
# 2. Catch-up Engine Historical Recovery Logic Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_03_catchup_bootstrap_initial_state():
    """
    Verifies that when an instrument has no checkpoint,
    CatchupEngine bootstraps up to latest completed candle and marks SYNCED.
    """
    symbol = "BOOTSTRAP_SYM"
    tf = "15M"
    candles = _generate_synthetic_candles(count=30, step_minutes=15)
    provider = MockMarketDataProvider({"15M": candles})

    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol,
        ticker=symbol,
        timeframe=tf,
        provider=provider
    )

    assert report["status"] == "BOOTSTRAP_COMPLETE"
    assert report["candles_processed"] == 30
    assert report["last_checkpoint"] == candles[-1].timestamp

    cp = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp is not None
    assert cp.last_processed_candle_timestamp == candles[-1].timestamp
    assert cp.checkpoint_status == "SYNCED"


@pytest.mark.asyncio
async def test_04_catchup_missed_completed_candles():
    """
    Verifies that when a checkpoint is in the past,
    CatchupEngine replays ONLY the missed completed candles in chronological order.
    """
    symbol = "MISSED_CANDLES_SYM"
    tf = "15M"
    all_candles = _generate_synthetic_candles(count=40, step_minutes=15)
    initial_checkpoint_candle = all_candles[9]

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol,
        timeframe=tf,
        last_candle_timestamp=initial_checkpoint_candle.timestamp,
        processed_count=10,
        status="SYNCED"
    )

    provider = MockMarketDataProvider({"15M": all_candles})

    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol,
        ticker=symbol,
        timeframe=tf,
        provider=provider
    )

    assert report["status"] == "RECOVERY_COMPLETE"
    assert report["candles_processed"] == 30
    assert report["last_checkpoint"] == all_candles[-1].timestamp

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

    rep1 = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker=symbol, timeframe=tf, provider=provider
    )
    assert rep1["status"] == "BOOTSTRAP_COMPLETE"

    rep2 = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker=symbol, timeframe=tf, provider=provider
    )
    assert rep2["status"] == "ALREADY_UP_TO_DATE"
    assert rep2["candles_processed"] == 0

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

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol,
        timeframe=tf,
        last_candle_timestamp=candles[4].timestamp,
        processed_count=5,
        status="SYNCED"
    )

    provider = MockMarketDataProvider({"15M": candles})

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

    assert report["candles_processed"] == 2
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

    await asyncio.sleep(0.5)

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
    assert len(report["results"]) == 4


# ---------------------------------------------------------------------------
# 4. Rigorous 4-Day / 10-Day & Multi-Chunk Historical Recovery Scenarios (A - O)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_10_crypto_5m_4day_recovery_1152_candles():
    """
    Test A: 5M crypto 4-day outage (1,152 candles missed).
    Verifies that all 1,152 missed completed candles are recovered chronologically.
    """
    symbol = "TEST_A_BTC_5M"
    tf = "5M"
    start_dt = datetime.now(timezone.utc) - timedelta(days=4, hours=2)
    warmup_candles = _generate_crypto_candles(count=50, step_minutes=5, start_dt=start_dt - timedelta(minutes=250))
    missed_candles = _generate_crypto_candles(count=1152, step_minutes=5, start_dt=start_dt)
    all_candles = warmup_candles + missed_candles

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=warmup_candles[-1].timestamp,
        processed_count=50, status="SYNCED"
    )

    provider = MockMarketDataProvider({"5M": all_candles})
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider
    )

    assert report["status"] == "RECOVERY_COMPLETE"
    assert report["candles_processed"] == 1152
    assert report["last_checkpoint"] == missed_candles[-1].timestamp
    assert report["processed_timestamps"] == [c.timestamp for c in missed_candles]

    cp = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp.last_processed_candle_timestamp == missed_candles[-1].timestamp
    assert cp.checkpoint_status == "SYNCED"


@pytest.mark.asyncio
async def test_11_crypto_5m_10day_recovery_2880_candles():
    """
    Test B: 5M crypto 10-day outage (2,880 candles missed).
    Verifies that extensive multi-thousand candle gaps are seamlessly recovered.
    """
    symbol = "TEST_B_BTC_5M"
    tf = "5M"
    start_dt = datetime.now(timezone.utc) - timedelta(days=10, hours=2)
    warmup_candles = _generate_crypto_candles(count=50, step_minutes=5, start_dt=start_dt - timedelta(minutes=250))
    missed_candles = _generate_crypto_candles(count=2880, step_minutes=5, start_dt=start_dt)
    all_candles = warmup_candles + missed_candles

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=warmup_candles[-1].timestamp,
        processed_count=50, status="SYNCED"
    )

    provider = MockMarketDataProvider({"5M": all_candles})
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider
    )

    assert report["status"] == "RECOVERY_COMPLETE"
    assert report["candles_processed"] == 2880
    assert report["last_checkpoint"] == missed_candles[-1].timestamp
    assert report["processed_timestamps"] == [c.timestamp for c in missed_candles]


@pytest.mark.asyncio
async def test_12_crypto_15m_4day_recovery_384_candles():
    """
    Test C: 15M crypto 4-day outage (384 candles missed).
    """
    symbol = "TEST_C_BTC_15M"
    tf = "15M"
    start_dt = datetime.now(timezone.utc) - timedelta(days=4, hours=2)
    warmup_candles = _generate_crypto_candles(count=50, step_minutes=15, start_dt=start_dt - timedelta(minutes=750))
    missed_candles = _generate_crypto_candles(count=384, step_minutes=15, start_dt=start_dt)
    all_candles = warmup_candles + missed_candles

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=warmup_candles[-1].timestamp,
        processed_count=50, status="SYNCED"
    )

    provider = MockMarketDataProvider({"15M": all_candles})
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider
    )

    assert report["status"] == "RECOVERY_COMPLETE"
    assert report["candles_processed"] == 384
    assert report["processed_timestamps"] == [c.timestamp for c in missed_candles]


@pytest.mark.asyncio
async def test_13_nse_5m_4day_recovery_300_candles():
    """
    Test D: 5M NSE equity 4 trading-day outage (300 candles missed).
    Verifies overnight and weekend market closures are handled without false gap detection.
    """
    symbol = "TEST_D_RELIANCE_5M"
    tf = "5M"
    all_nse_5m = _generate_nse_candles(trading_days=5, step_minutes=5)
    warmup = all_nse_5m[:75]
    missed = all_nse_5m[75:]

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=warmup[-1].timestamp,
        processed_count=75, status="SYNCED"
    )

    provider = MockMarketDataProvider({"5M": all_nse_5m})
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="RELIANCE.NS", timeframe=tf, provider=provider
    )

    assert report["status"] == "RECOVERY_COMPLETE"
    assert report["candles_processed"] == 300
    assert report["processed_timestamps"] == [c.timestamp for c in missed]


@pytest.mark.asyncio
async def test_14_nse_15m_4day_recovery_100_candles():
    """
    Test E: 15M NSE equity 4 trading-day outage (100 candles missed).
    """
    symbol = "TEST_E_RELIANCE_15M"
    tf = "15M"
    all_nse_15m = _generate_nse_candles(trading_days=5, step_minutes=15)
    warmup = all_nse_15m[:25]
    missed = all_nse_15m[25:]

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=warmup[-1].timestamp,
        processed_count=25, status="SYNCED"
    )

    provider = MockMarketDataProvider({"15M": all_nse_15m})
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="RELIANCE.NS", timeframe=tf, provider=provider
    )

    assert report["status"] == "RECOVERY_COMPLETE"
    assert report["candles_processed"] == 100
    assert report["processed_timestamps"] == [c.timestamp for c in missed]


@pytest.mark.asyncio
async def test_15_crypto_1h_4day_recovery_96_candles():
    """
    Test F: 1H crypto 4-day outage (96 candles missed).
    """
    symbol = "TEST_F_BTC_1H"
    tf = "1H"
    start_dt = datetime.now(timezone.utc) - timedelta(days=4, hours=4)
    warmup = _generate_crypto_candles(count=50, step_minutes=60, start_dt=start_dt - timedelta(hours=50))
    missed = _generate_crypto_candles(count=96, step_minutes=60, start_dt=start_dt)
    all_candles = warmup + missed

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=warmup[-1].timestamp,
        processed_count=50, status="SYNCED"
    )

    provider = MockMarketDataProvider({"1H": all_candles})
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider
    )

    assert report["status"] == "RECOVERY_COMPLETE"
    assert report["candles_processed"] == 96
    assert report["processed_timestamps"] == [c.timestamp for c in missed]


@pytest.mark.asyncio
async def test_16_crypto_4h_4day_recovery_24_candles():
    """
    Test G: 4H crypto 4-day outage (24 candles missed).
    """
    symbol = "TEST_G_BTC_4H"
    tf = "4H"
    start_dt = datetime.now(timezone.utc) - timedelta(days=4, hours=8)
    warmup = _generate_crypto_candles(count=20, step_minutes=240, start_dt=start_dt - timedelta(hours=80))
    missed = _generate_crypto_candles(count=24, step_minutes=240, start_dt=start_dt)
    all_candles = warmup + missed

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=warmup[-1].timestamp,
        processed_count=20, status="SYNCED"
    )

    provider = MockMarketDataProvider({"4H": all_candles})
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider
    )

    assert report["status"] == "RECOVERY_COMPLETE"
    assert report["candles_processed"] == 24
    assert report["processed_timestamps"] == [c.timestamp for c in missed]


@pytest.mark.asyncio
async def test_17_multi_chunk_recovery_chunk_size_500():
    """
    Test H: Multi-chunk recovery with provider returning batches of 500 candles.
    Verifies that 1,152 candles spanning across 3 separate provider chunks are reassembled.
    """
    symbol = "TEST_H_CHUNKED_5M"
    tf = "5M"
    start_dt = datetime.now(timezone.utc) - timedelta(days=4, hours=2)
    warmup = _generate_crypto_candles(count=100, step_minutes=5, start_dt=start_dt - timedelta(minutes=500))
    missed = _generate_crypto_candles(count=1152, step_minutes=5, start_dt=start_dt)
    all_candles = warmup + missed

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=warmup[-1].timestamp,
        processed_count=100, status="SYNCED"
    )

    provider = MockMarketDataProvider({"5M": all_candles}, chunk_size=500)
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider, max_fetch_limit=500
    )

    assert report["status"] == "RECOVERY_COMPLETE"
    assert report["candles_processed"] == 1152
    assert report["processed_timestamps"] == [c.timestamp for c in missed]


@pytest.mark.asyncio
async def test_18_provider_failure_during_chunk_2_halts_safe():
    """
    Test I: Provider failure during chunk 2.
    Verifies that chunk 1 is committed safely and checkpoint status is set to RECOVERING.
    """
    symbol = "TEST_I_FAIL_CHUNK2"
    tf = "5M"
    start_dt = datetime.now(timezone.utc) - timedelta(days=4)
    warmup = _generate_crypto_candles(count=50, step_minutes=5, start_dt=start_dt - timedelta(minutes=250))
    missed = _generate_crypto_candles(count=1000, step_minutes=5, start_dt=start_dt)
    all_candles = warmup + missed

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=warmup[-1].timestamp,
        processed_count=50, status="SYNCED"
    )

    provider = MockMarketDataProvider({"5M": all_candles}, chunk_size=500, fail_on_call=2)
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider, max_fetch_limit=500
    )

    assert report["status"] == "RECOVERING"
    chunk1_processed = report["candles_processed"]
    assert chunk1_processed > 0

    cp = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp.last_processed_candle_timestamp == report["processed_timestamps"][-1]
    assert cp.checkpoint_status == "RECOVERING"


@pytest.mark.asyncio
async def test_19_restart_during_recovery_resumes_from_checkpoint():
    """
    Test J: Restart during recovery.
    Verifies that restarting resumes exactly from the halted checkpoint.
    """
    symbol = "TEST_J_RESUME"
    tf = "5M"
    start_dt = datetime.now(timezone.utc) - timedelta(days=4)
    warmup = _generate_crypto_candles(count=50, step_minutes=5, start_dt=start_dt - timedelta(minutes=250))
    missed = _generate_crypto_candles(count=1000, step_minutes=5, start_dt=start_dt)
    all_candles = warmup + missed

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=warmup[-1].timestamp,
        processed_count=50, status="SYNCED"
    )

    prov_fail = MockMarketDataProvider({"5M": all_candles}, chunk_size=500, fail_on_call=2)
    rep1 = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=prov_fail, max_fetch_limit=500
    )
    assert rep1["status"] == "RECOVERING"
    chunk1_count = rep1["candles_processed"]
    assert chunk1_count > 0

    cp_mid = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp_mid is not None
    assert cp_mid.checkpoint_status == "RECOVERING"
    assert cp_mid.last_processed_candle_timestamp == rep1["processed_timestamps"][-1]

    prov_ok = MockMarketDataProvider({"5M": all_candles}, chunk_size=500, fail_on_call=None)
    rep2 = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=prov_ok, max_fetch_limit=500
    )
    assert rep2["status"] == "RECOVERY_COMPLETE"
    expected_remainder = len(missed) - chunk1_count
    assert rep2["candles_processed"] == expected_remainder
    assert rep2["last_checkpoint"] == missed[-1].timestamp

    cp_final = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp_final.last_processed_candle_timestamp == missed[-1].timestamp
    assert cp_final.checkpoint_status == "SYNCED"


@pytest.mark.asyncio
async def test_20_duplicate_replayed_recovery_zero_duplicates():
    """
    Test K: Duplicate / replayed recovery.
    Verifies that running recovery on an already synced checkpoint processes 0 candles.
    """
    symbol = "TEST_K_REPLAY"
    tf = "5M"
    start_dt = datetime.now(timezone.utc) - timedelta(days=4)
    warmup = _generate_crypto_candles(count=50, step_minutes=5, start_dt=start_dt - timedelta(minutes=250))
    missed = _generate_crypto_candles(count=500, step_minutes=5, start_dt=start_dt)
    all_candles = warmup + missed

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=all_candles[-1].timestamp,
        processed_count=len(all_candles), status="SYNCED"
    )

    provider = MockMarketDataProvider({"5M": all_candles}, chunk_size=500)
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider
    )

    assert report["status"] == "ALREADY_UP_TO_DATE"
    assert report["candles_processed"] == 0


@pytest.mark.asyncio
async def test_21_checkpoint_exactly_at_previous_candle_up_to_date():
    """
    Test L: Checkpoint exactly at previous completed candle.
    Verifies immediate ALREADY_UP_TO_DATE return.
    """
    symbol = "TEST_L_EXACT_SYNC"
    tf = "15M"
    candles = _generate_crypto_candles(count=30, step_minutes=15)

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=candles[-1].timestamp,
        processed_count=30, status="SYNCED"
    )

    provider = MockMarketDataProvider({"15M": candles})
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider
    )

    assert report["status"] == "ALREADY_UP_TO_DATE"
    assert report["candles_processed"] == 0


@pytest.mark.asyncio
async def test_22_checkpoint_older_than_first_page_backward_pagination():
    """
    Test M: Checkpoint older than first currently fetched page.
    Verifies backward pagination successfully bridges older checkpoint and processes all missed candles.
    """
    symbol = "TEST_M_OLDER_PAGE"
    tf = "5M"
    start_dt = datetime.now(timezone.utc) - timedelta(days=4)
    warmup = _generate_crypto_candles(count=50, step_minutes=5, start_dt=start_dt - timedelta(minutes=250))
    missed = _generate_crypto_candles(count=1152, step_minutes=5, start_dt=start_dt)
    all_candles = warmup + missed

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=warmup[-1].timestamp,
        processed_count=50, status="SYNCED"
    )

    provider = MockMarketDataProvider({"5M": all_candles}, chunk_size=500, return_newest_page_first=True)
    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider, max_fetch_limit=500
    )

    assert report["status"] == "RECOVERY_COMPLETE"
    assert report["candles_processed"] == 1152
    assert report["processed_timestamps"] == [c.timestamp for c in missed]


@pytest.mark.asyncio
async def test_23_insufficient_provider_history_marks_gap_detected():
    """
    Test N: Insufficient provider history.
    Verifies that when checkpoint is beyond provider retention (>60 days for 5M),
    the system marks GAP_DETECTED explicitly and does NOT report SYNCED.
    """
    symbol = "TEST_N_INSUFFICIENT"
    tf = "5M"
    old_ts = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=old_ts,
        processed_count=100, status="SYNCED"
    )

    today_candles = _generate_crypto_candles(count=50, step_minutes=5)
    provider = MockMarketDataProvider({"5M": today_candles})

    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider
    )

    assert report["status"] == "GAP_DETECTED"
    cp = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp.checkpoint_status == "GAP_DETECTED"


@pytest.mark.asyncio
async def test_24_no_silent_checkpoint_skip_on_gap():
    """
    Test O: No silent checkpoint skip.
    Verifies that when an unbridgeable gap exists, the engine never falsely reports SYNCED.
    """
    symbol = "TEST_O_NO_SILENT_SKIP"
    tf = "5M"
    old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

    CheckpointRepository.update_checkpoint_sync(
        symbol=symbol, timeframe=tf,
        last_candle_timestamp=old_ts,
        processed_count=10, status="SYNCED"
    )

    recent_candles = _generate_crypto_candles(
        count=50, step_minutes=5, start_dt=datetime.now(timezone.utc) - timedelta(days=2)
    )
    provider = MockMarketDataProvider({"5M": recent_candles}, return_newest_page_first=True)

    report = await CatchupEngine.recover_instrument_timeframe(
        symbol=symbol, ticker="BTC-USD", timeframe=tf, provider=provider
    )

    assert report["status"] == "GAP_DETECTED"
    cp = CheckpointRepository.get_checkpoint_sync(symbol, tf)
    assert cp.checkpoint_status == "GAP_DETECTED"
