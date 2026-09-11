import asyncio
import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timezone

from app.models.schemas import (
    InstrumentConfig,
    MultiTimeframeSynthesis,
    AlertNotification,
    MWBreakoutAlert,
)
from app.api.deps import get_current_provider, configured_instruments
from app.data.base import MarketDataProvider
from app.db.repository import CheckpointRepository
from app.market_processing.catchup_engine import CatchupEngine
from app.multi_timeframe.synthesis import MultiTimeframeAnalyzer
from app.api.routes_analysis import update_synthesis_cache
from app.api.websocket import ws_manager
from app.alerts.engine import alert_engine
from app.alerts.high_confluence_engine import high_confluence_alert_engine
from app.alerts.mw_breakout_engine import mw_breakout_engine
from app.alerts.trendline_shortlist_engine import trendline_shortlist_engine
from app.core.timezone import is_candle_closed

logger = logging.getLogger(__name__)


class MarketProcessingWorker:
    """
    Continuous 24/7 Autonomous Background Market Processing Worker.

    Core Guarantees:
    1. Independent of Frontend: Operates continuously in the background whether user is online or offline.
    2. Missed-Candle Catch-Up: Automatically replays and recovers historical missed candles on startup or after disconnects.
    3. Live Candle Detection: Polls providers, detects closed candles across all active timeframes (4H, 1H, 15M, 5M).
    4. Deterministic Persistence: W/M and trendline breakouts are persisted into SQLite with unique constraints.
    5. Real-Time Broadcasting: Live candle events emit WebSocket broadcasts (ALERT_TRIGGERED, MW_BREAKOUT_TRIGGERED, etc.).
    6. Synthesis Priming: Keeps synthesis cache hot so frontend overview/chart endpoints respond with 0ms delay.
    """

    def __init__(
        self,
        instruments: Optional[List[InstrumentConfig]] = None,
        provider: Optional[MarketDataProvider] = None,
        poll_interval_seconds: int = 15,
        timeframes: Optional[List[str]] = None
    ):
        self.instruments = instruments
        self.provider = provider
        self.poll_interval = poll_interval_seconds
        self.timeframes = timeframes or ["4H", "1H", "15M", "5M"]
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._catchup_task: Optional[asyncio.Task] = None
        self.catchup_engine = CatchupEngine

    def get_provider(self) -> MarketDataProvider:
        return self.provider or get_current_provider()

    def get_active_instruments(self) -> List[InstrumentConfig]:
        target_list = self.instruments if self.instruments is not None else configured_instruments
        return [inst for inst in target_list if getattr(inst, "is_active", True)]

    async def run_catchup(self) -> Dict[str, Any]:
        """
        Runs missed-candle catch-up across all active instruments and timeframes.
        Persists all valid historical breakout events without emitting live audio/toast notifications.
        """
        active_insts = self.get_active_instruments()
        provider = self.get_provider()
        logger.info(f"[MarketProcessingWorker] Starting missed-candle catch-up for {len(active_insts)} instruments...")
        report = await self.catchup_engine.recover_all_instruments(
            instruments=active_insts,
            provider=provider,
            timeframes=self.timeframes
        )
        logger.info(
            f"[MarketProcessingWorker] Catch-up finished. Processed {report.get('total_candles_processed', 0)} missed candles."
        )
        return report

    async def _safe_run_catchup(self):
        try:
            await asyncio.sleep(1.0)
            await self.run_catchup()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[MarketProcessingWorker] Background catch-up failed: {e}")

    async def start(self, run_catchup_inline: bool = False):
        """
        Starts the background worker.
        If run_catchup_inline is True, awaits recovery before launching loop.
        Otherwise, runs recovery as a decoupled background task.
        """
        if self._running:
            logger.warning("[MarketProcessingWorker] Worker already running.")
            return

        self._running = True
        if run_catchup_inline:
            try:
                await self.run_catchup()
            except Exception as e:
                logger.error(f"[MarketProcessingWorker] Inline catch-up error: {e}")
        else:
            self._catchup_task = asyncio.create_task(self._safe_run_catchup())

        self._task = asyncio.create_task(
            self._run_loop(run_catchup_first=False)
        )
        logger.info("[MarketProcessingWorker] Background worker started successfully.")

    async def stop(self):
        """
        Stops the continuous background worker cleanly.
        """
        if not self._running:
            return

        logger.info("[MarketProcessingWorker] Stopping background worker...")
        self._running = False
        if self._catchup_task and not self._catchup_task.done():
            self._catchup_task.cancel()
            try:
                await self._catchup_task
            except asyncio.CancelledError:
                pass
        self._catchup_task = None

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("[MarketProcessingWorker] Background worker stopped.")

    async def _run_loop(self, run_catchup_first: bool = True):
        """
        Main worker execution loop.
        Immediately starts the monitoring cycle to prime live data and cache,
        while decoupling catch-up into a dedicated background task.
        """
        if run_catchup_first:
            self._catchup_task = asyncio.create_task(self._safe_run_catchup())

        logger.info("[MarketProcessingWorker] Entering continuous 24/7 market monitoring loop.")
        while self._running:
            try:
                await self.process_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MarketProcessingWorker] Error during process cycle: {e}")

            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break

    async def process_cycle(self):
        """
        Executes one monitoring cycle across all active instruments concurrently.
        """
        active_insts = self.get_active_instruments()
        provider = self.get_provider()

        tasks = [
            self.process_instrument(inst, provider)
            for inst in active_insts
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def process_instrument(
        self,
        inst: InstrumentConfig,
        provider: Optional[MarketDataProvider] = None
    ) -> Optional[MultiTimeframeSynthesis]:
        """
        Monitors a single instrument:
        - Fetches multi-timeframe candles.
        - Identifies if intermediate missed candles need catch-up.
        - Runs synthesis, primes cache, and broadcasts SYNTHESIS_UPDATE.
        - If new candle closed, runs breakout detection and emits live WebSocket alerts.
        - Advances persistent checkpoints in SQLite.
        """
        prov = provider or self.get_provider()
        symbol = inst.symbol
        ticker = inst.ticker

        try:
            mtf_candles = await prov.get_multi_timeframe_data(
                symbol=symbol,
                ticker=ticker,
                timeframes=self.timeframes,
                limit=200
            )
        except Exception as e:
            logger.error(f"[MarketProcessingWorker] Failed to fetch MTF candles for {symbol}: {e}")
            return None

        # Check for gap / newly closed candles in each timeframe
        newly_closed_candles: Dict[str, str] = {}
        for tf in self.timeframes:
            candles = mtf_candles.get(tf, [])
            completed = [c for c in candles if is_candle_closed(c.timestamp, tf)]
            if not completed:
                continue

            latest_completed_ts = completed[-1].timestamp
            checkpoint = CheckpointRepository.get_checkpoint_sync(symbol, tf)
            last_processed = checkpoint.last_processed_candle_timestamp if checkpoint else None

            if last_processed is None:
                # Bootstrap checkpoint
                CheckpointRepository.update_checkpoint_sync(
                    symbol=symbol,
                    timeframe=tf,
                    last_candle_timestamp=latest_completed_ts,
                    processed_count=len(completed),
                    status="SYNCED"
                )
            elif latest_completed_ts > last_processed:
                # Find how many completed candles are newer than last_processed
                matching_idx = None
                for idx, c in enumerate(completed):
                    if c.timestamp == last_processed:
                        matching_idx = idx
                        break

                missed_count = (
                    len(completed) - 1 - matching_idx
                    if matching_idx is not None
                    else sum(1 for c in completed if c.timestamp > last_processed)
                )

                # If more than 1 missed candle (e.g. gap during network lapse), run recovery for older ones
                if missed_count > 1:
                    try:
                        await self.catchup_engine.recover_instrument_timeframe(
                            symbol=symbol,
                            ticker=ticker,
                            timeframe=tf,
                            provider=prov
                        )
                    except Exception as catchup_err:
                        logger.warning(f"[MarketProcessingWorker] Mid-flight catchup error for {symbol} ({tf}): {catchup_err}")

                newly_closed_candles[tf] = latest_completed_ts

        # Synthesize multi-timeframe analysis
        has_data = any(len(c) > 0 for c in mtf_candles.values())
        status_msg = (
            f"Live Market Data from {prov.provider_name}"
            if has_data
            else f"No data received from {prov.provider_name}"
        )
        data_status = getattr(prov, "get_connection_status", lambda t: "LIVE")(ticker)

        synthesis = MultiTimeframeAnalyzer.synthesize(
            symbol=symbol,
            ticker=ticker,
            provider_name=prov.provider_name,
            mtf_candles=mtf_candles,
            is_stale=False,
            status_message=status_msg,
            data_status=data_status
        )

        # Update cache so REST API (/overview, /fast-overview) responds instantly
        update_synthesis_cache(symbol, synthesis)

        # Broadcast synthesis update to WebSocket clients
        await ws_manager.broadcast({
            "type": "SYNTHESIS_UPDATE",
            "symbol": symbol,
            "overall_bias": synthesis.overall_bias,
            "evidence_score": synthesis.evidence_score.total_score,
            "current_price": synthesis.current_price,
            "current_state": synthesis.current_state,
            "latest_event": synthesis.latest_important_event.model_dump() if synthesis.latest_important_event else None
        })

        # Process alerts (live candle notifications)
        try:
            new_alerts = alert_engine.process_synthesis_for_alerts(synthesis, is_catchup=False)
            for alert in new_alerts:
                await ws_manager.broadcast({
                    "type": "ALERT_TRIGGERED",
                    "alert": alert.model_dump()
                })
        except Exception as e:
            logger.error(f"[MarketProcessingWorker Alert Error for {symbol}]: {e}")

        try:
            new_high = high_confluence_alert_engine.process_synthesis_for_high_confluence_alerts(synthesis)
            for hca in new_high:
                await ws_manager.broadcast({
                    "type": "HIGH_CONFLUENCE_ALERT_TRIGGERED",
                    "alert": hca.model_dump()
                })
        except Exception as e:
            logger.error(f"[MarketProcessingWorker High Confluence Error for {symbol}]: {e}")

        try:
            new_mw, updated_mw = mw_breakout_engine.process_synthesis_with_updates(
                synthesis,
                mtf_candles=mtf_candles,
                is_catchup=False
            )
            for mwa in new_mw:
                await ws_manager.broadcast({
                    "type": "MW_BREAKOUT_TRIGGERED",
                    "alert": mwa.model_dump()
                })
            for mwa in updated_mw:
                await ws_manager.broadcast({
                    "type": "MW_BREAKOUT_STATUS_UPDATED",
                    "alert": mwa.model_dump()
                })
        except Exception as e:
            logger.error(f"[MarketProcessingWorker MW Error for {symbol}]: {e}")

        try:
            new_shortlist = trendline_shortlist_engine.process_synthesis(synthesis)
            for cand in new_shortlist:
                await ws_manager.broadcast({
                    "type": "TRENDLINE_SHORTLIST_UPDATED",
                    "candidate": cand.model_dump()
                })
        except Exception as e:
            logger.error(f"[MarketProcessingWorker Shortlist Error for {symbol}]: {e}")

        # Advance checkpoints for all timeframes with newly completed candles
        for tf, latest_ts in newly_closed_candles.items():
            CheckpointRepository.update_checkpoint_sync(
                symbol=symbol,
                timeframe=tf,
                last_candle_timestamp=latest_ts,
                processed_count=1,
                status="SYNCED"
            )

        return synthesis
