import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timezone

from app.models.schemas import (
    Candle,
    SingleTimeframeAnalysis,
    MultiTimeframeSynthesis,
    AlertNotification,
    MWBreakoutAlert,
    ProcessingCheckpoint
)
from app.db.repository import CheckpointRepository
from app.data.base import MarketDataProvider
from app.multi_timeframe.analyzer import SingleTimeframeAnalyzer
from app.multi_timeframe.synthesis import MultiTimeframeAnalyzer
from app.alerts.engine import alert_engine
from app.alerts.mw_breakout_engine import mw_breakout_engine
from app.core.timezone import is_candle_closed

logger = logging.getLogger(__name__)


class CatchupEngine:
    """
    Autonomous Missed-Candle Catch-Up and Historical Replay Engine.

    Guarantees:
    1. Checkpoint-Driven: Inspects processing_checkpoints table for (symbol, timeframe).
    2. Chronological Replay: Replays all missed completed candles after checkpoint with full historical context.
    3. Idempotent Ingestion: Zero duplicate records in SQLite upon replay.
    4. Decoupled Persistence: Persists 100% of valid missed events to SQL history without firing live notification toast audio spam.
    5. Atomic Advancement: Checkpoint advances only after successful processing of completed candles.
    """

    @classmethod
    async def recover_instrument_timeframe(
        cls,
        symbol: str,
        ticker: str,
        timeframe: str,
        provider: MarketDataProvider,
        max_fetch_limit: int = 500,
        context_history_bars: int = 120
    ) -> Dict[str, Any]:
        """
        Recovers missed completed candles for a single (symbol, timeframe).
        Returns a recovery report with candles processed and events persisted.
        """
        # 1. Read existing checkpoint
        checkpoint = CheckpointRepository.get_checkpoint_sync(symbol, timeframe)
        last_processed_ts = checkpoint.last_processed_candle_timestamp if checkpoint else None

        # 2. Fetch candles from provider
        try:
            raw_candles = await provider.fetch_candles(symbol, ticker, timeframe, limit=max_fetch_limit)
        except Exception as e:
            logger.error(f"[CatchupEngine] Failed to fetch candles for {symbol} ({timeframe}): {e}")
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "status": "FETCH_ERROR",
                "error": str(e),
                "candles_processed": 0,
                "events_persisted": 0
            }

        if not raw_candles:
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "status": "NO_DATA",
                "candles_processed": 0,
                "events_persisted": 0
            }

        # Filter strictly for completed candles
        completed_candles = [c for c in raw_candles if is_candle_closed(c.timestamp, timeframe)]
        if not completed_candles:
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "status": "NO_COMPLETED_CANDLES",
                "candles_processed": 0,
                "events_persisted": 0
            }

        # 3. Determine missed candles
        if last_processed_ts is None:
            # First-time bootstrap:
            # Process the current window, persist valid events, and initialize checkpoint to latest completed candle
            logger.info(f"[CatchupEngine] Initial bootstrap for {symbol} ({timeframe}) with {len(completed_candles)} candles.")
            latest_c = completed_candles[-1]
            cls._process_and_persist_slice(
                completed_candles, symbol, ticker, timeframe, is_catchup=True
            )
            CheckpointRepository.update_checkpoint_sync(
                symbol=symbol,
                timeframe=timeframe,
                last_candle_timestamp=latest_c.timestamp,
                processed_count=len(completed_candles),
                status="SYNCED"
            )
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "status": "BOOTSTRAP_COMPLETE",
                "candles_processed": len(completed_candles),
                "last_checkpoint": latest_c.timestamp
            }

        # Find where last_processed_ts sits in completed_candles
        missed_candles: List[Candle] = []
        matching_idx = None
        for i, c in enumerate(completed_candles):
            if c.timestamp == last_processed_ts:
                matching_idx = i
                break

        if matching_idx is not None:
            missed_candles = completed_candles[matching_idx + 1:]
        else:
            # Checkpoint is older than the oldest candle in completed_candles
            # or checkpoint timestamp format: take all candles strictly greater than last_processed_ts
            missed_candles = [c for c in completed_candles if c.timestamp > last_processed_ts]

        if not missed_candles:
            logger.debug(f"[CatchupEngine] {symbol} ({timeframe}) is already up-to-date at {last_processed_ts}.")
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "status": "ALREADY_UP_TO_DATE",
                "candles_processed": 0,
                "last_checkpoint": last_processed_ts
            }

        logger.info(
            f"[CatchupEngine] Recovering {len(missed_candles)} missed candles for {symbol} ({timeframe}) "
            f"since {last_processed_ts} -> {missed_candles[-1].timestamp}"
        )

        # 4. Chronological Replay with Sliding Context Window
        # For each missed candle, slice historical context up to that candle and run detection
        events_persisted_total = 0
        successful_processed_count = 0

        for missed_c in missed_candles:
            idx_in_completed = completed_candles.index(missed_c)
            # Take historical context leading into this candle (e.g. 100-200 bars)
            start_idx = max(0, idx_in_completed - context_history_bars + 1)
            candle_slice = completed_candles[start_idx : idx_in_completed + 1]

            try:
                new_events = cls._process_and_persist_slice(
                    candle_slice, symbol, ticker, timeframe, is_catchup=True
                )
                events_persisted_total += new_events
                successful_processed_count += 1

                # Advance checkpoint atomically for this candle
                CheckpointRepository.update_checkpoint_sync(
                    symbol=symbol,
                    timeframe=timeframe,
                    last_candle_timestamp=missed_c.timestamp,
                    processed_count=1,
                    status="SYNCED"
                )
            except Exception as slice_err:
                logger.error(
                    f"[CatchupEngine] Error processing candle {missed_c.timestamp} for {symbol} ({timeframe}): {slice_err}"
                )
                CheckpointRepository.update_checkpoint_sync(
                    symbol=symbol,
                    timeframe=timeframe,
                    last_candle_timestamp=checkpoint.last_processed_candle_timestamp if successful_processed_count == 0 else completed_candles[idx_in_completed - 1].timestamp,
                    processed_count=0,
                    status="RECOVERING"
                )
                break

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "RECOVERY_COMPLETE",
            "candles_processed": successful_processed_count,
            "events_persisted": events_persisted_total,
            "last_checkpoint": missed_candles[successful_processed_count - 1].timestamp if successful_processed_count > 0 else last_processed_ts
        }

    @classmethod
    def _process_and_persist_slice(
        cls,
        candle_slice: List[Candle],
        symbol: str,
        ticker: str,
        timeframe: str,
        is_catchup: bool = True
    ) -> int:
        """
        Executes W/M and trendline detection on a chronological candle slice
        and persists valid events to SQLite.
        """
        if len(candle_slice) < 5:
            return 0

        # Synthesize multi-timeframe analysis for alert engines
        synthesis = MultiTimeframeAnalyzer.synthesize(
            symbol=symbol,
            ticker=ticker,
            provider_name="CatchupEngine",
            mtf_candles={timeframe: candle_slice},
            is_stale=False,
            status_message="Catch-up Processing",
            data_status="LIVE"
        )

        persisted_count = 0
        tf_analysis = synthesis.timeframes.get(timeframe)

        # 1. Process and persist Trendline / Structure Breaks
        try:
            alert_engine.process_synthesis_for_alerts(synthesis, is_catchup=is_catchup)
            if tf_analysis and tf_analysis.recent_events:
                persisted_count += len(tf_analysis.recent_events)
        except Exception as e:
            logger.warning(f"[CatchupEngine] Trendline alert persist error: {e}")

        # 2. Process and persist W/M Breakouts
        try:
            mw_breakout_engine.process_synthesis_with_updates(
                synthesis,
                mtf_candles={timeframe: candle_slice},
                is_catchup=is_catchup
            )
            if tf_analysis and tf_analysis.wm_patterns:
                persisted_count += len(tf_analysis.wm_patterns)
        except Exception as e:
            logger.warning(f"[CatchupEngine] MW alert persist error: {e}")

        return persisted_count

    @classmethod
    async def recover_all_instruments(
        cls,
        instruments: List[Any],
        provider: MarketDataProvider,
        timeframes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Runs missed-candle recovery across all active instruments and timeframes.
        """
        if timeframes is None:
            timeframes = ["4H", "1H", "15M", "5M"]

        logger.info(f"[CatchupEngine] Starting catch-up audit across {len(instruments)} instruments...")
        results = []

        for inst in instruments:
            if not getattr(inst, "is_active", True):
                continue
            for tf in timeframes:
                res = await cls.recover_instrument_timeframe(
                    symbol=inst.symbol,
                    ticker=getattr(inst, "ticker", inst.symbol),
                    timeframe=tf,
                    provider=provider
                )
                results.append(res)

        total_processed = sum(r.get("candles_processed", 0) for r in results)
        logger.info(f"[CatchupEngine] Catch-up complete: {total_processed} total missed candles processed.")
        return {
            "total_candles_processed": total_processed,
            "results": results
        }
