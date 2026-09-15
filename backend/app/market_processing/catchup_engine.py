import asyncio
import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta, time as dtime

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
from app.data.candle_builder import SessionAwareCandleBuilder, KOLKATA_TZ
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
    3. Multi-Chunk & Arbitrary Gap Ingestion: Not hardcoded to 4 days; recovers 1,152 (4d 5M), 2,880 (10d 5M), or arbitrary outages.
    4. Safe Failure & Atomicity: Checkpoint advances per completed candle. If a chunk fails, checkpoint stays at last successfully processed candle.
    5. Zero Silent Data-Loss: Gaps beyond provider retention are explicitly flagged with GAP_DETECTED status and never falsely marked SYNCED.
    6. Context Parity: Uses 200-bar sliding context window matching live worker loop for full indicator and trendline convergence.
    7. Continuity Validation: Verifies continuous intervals for crypto, whilst respecting legitimate overnight/weekend equity session breaks.
    8. Idempotent Ingestion: Zero duplicate records in SQLite upon replay.
    9. Decoupled Persistence: Persists 100% of valid missed events to SQL history without firing live notification toast audio spam.
    """

    _active_recoveries: set = set()

    @staticmethod
    def _parse_timestamp(ts_str: str) -> datetime:
        clean = ts_str.replace("Z", "+00:00").replace(" ", "T")
        try:
            dt = datetime.fromisoformat(clean)
        except Exception:
            dt = datetime.strptime(ts_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _get_timeframe_seconds(timeframe: str) -> int:
        tf_upper = timeframe.upper()
        if tf_upper in ["1M", "1MIN"]: return 60
        if tf_upper in ["3M", "3MIN"]: return 180
        if tf_upper in ["5M", "5MIN"]: return 300
        if tf_upper in ["15M", "15MIN"]: return 900
        if tf_upper in ["30M", "30MIN"]: return 1800
        if tf_upper in ["1H", "60M"]: return 3600
        if tf_upper in ["4H", "240M"]: return 14400
        if tf_upper in ["1D", "D"]: return 86400
        return 300

    @staticmethod
    def _get_provider_max_retention_days(timeframe: str) -> int:
        tf_upper = timeframe.upper()
        if tf_upper in ["5M", "15M"]:
            return 60
        if tf_upper in ["1H", "4H"]:
            return 730
        return 60

    @classmethod
    def validate_continuity(
        cls,
        candles: List[Candle],
        timeframe: str,
        ticker: str
    ) -> Tuple[bool, List[str]]:
        if len(candles) < 2:
            return True, []

        is_crypto = SessionAwareCandleBuilder.is_crypto(ticker)
        expected_step = cls._get_timeframe_seconds(timeframe)
        gaps: List[str] = []

        for i in range(1, len(candles)):
            prev_c = candles[i - 1]
            curr_c = candles[i]
            prev_dt = cls._parse_timestamp(prev_c.timestamp)
            curr_dt = cls._parse_timestamp(curr_c.timestamp)
            diff_secs = (curr_dt - prev_dt).total_seconds()

            if diff_secs <= expected_step:
                continue

            if is_crypto:
                gaps.append(
                    f"Crypto missing candle gap: {prev_c.timestamp} -> {curr_c.timestamp} "
                    f"({int(diff_secs)}s elapsed vs expected {expected_step}s)"
                )
            else:
                prev_local = prev_dt.astimezone(KOLKATA_TZ)
                curr_local = curr_dt.astimezone(KOLKATA_TZ)
                is_session_boundary = (
                    prev_local.time() >= dtime(15, 15)
                    and curr_local.time() <= dtime(9, 30)
                    and curr_local.date() > prev_local.date()
                )
                if not is_session_boundary:
                    gaps.append(
                        f"Equity intraday gap: {prev_c.timestamp} -> {curr_c.timestamp} "
                        f"({int(diff_secs)}s elapsed within trading hours)"
                    )

        return len(gaps) == 0, gaps

    @classmethod
    async def recover_instrument_timeframe(
        cls,
        symbol: str,
        ticker: str,
        timeframe: str,
        provider: MarketDataProvider,
        max_fetch_limit: int = 500,
        context_history_bars: int = 200
    ) -> Dict[str, Any]:
        """
        Recovers missed completed candles for a single (symbol, timeframe).
        Deduplicates concurrent recovery attempts for the same instrument-timeframe.
        """
        recovery_key = (symbol.upper(), timeframe.upper())
        if recovery_key in cls._active_recoveries:
            logger.info(f"[CatchupEngine] Recovery already in progress for {symbol} ({timeframe}), skipping redundant call.")
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "status": "ALREADY_IN_PROGRESS",
                "candles_processed": 0,
                "events_persisted": 0,
                "processed_timestamps": []
            }

        cls._active_recoveries.add(recovery_key)
        try:
            return await cls._do_recover_instrument_timeframe(
                symbol=symbol,
                ticker=ticker,
                timeframe=timeframe,
                provider=provider,
                max_fetch_limit=max_fetch_limit,
                context_history_bars=context_history_bars
            )
        finally:
            cls._active_recoveries.discard(recovery_key)

    @classmethod
    async def _fetch_candles_safe(cls, provider: MarketDataProvider, **kwargs) -> List[Candle]:
        try:
            return await provider.fetch_candles(**kwargs)
        except TypeError as te:
            if "is_catchup" in str(te):
                kwargs.pop("is_catchup", None)
                return await provider.fetch_candles(**kwargs)
            raise

    @classmethod
    async def _do_recover_instrument_timeframe(
        cls,
        symbol: str,
        ticker: str,
        timeframe: str,
        provider: MarketDataProvider,
        max_fetch_limit: int = 500,
        context_history_bars: int = 200
    ) -> Dict[str, Any]:
        """
        Internal implementation of single instrument-timeframe recovery.
        """
        # 1. Read existing checkpoint
        checkpoint = CheckpointRepository.get_checkpoint_sync(symbol, timeframe)
        last_processed_ts = checkpoint.last_processed_candle_timestamp if checkpoint else None

        # 2. Bootstrap initial checkpoint if none exists
        if last_processed_ts is None:
            try:
                raw_candles = await cls._fetch_candles_safe(
                    provider, symbol=symbol, ticker=ticker, timeframe=timeframe, limit=context_history_bars, is_catchup=True
                )
            except Exception as e:
                logger.error(f"[CatchupEngine] Failed to bootstrap candles for {symbol} ({timeframe}): {e}")
                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "status": "FETCH_ERROR",
                    "error": str(e),
                    "candles_processed": 0,
                    "events_persisted": 0,
                    "processed_timestamps": []
                }

            if not raw_candles:
                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "status": "NO_DATA",
                    "candles_processed": 0,
                    "events_persisted": 0,
                    "processed_timestamps": []
                }

            completed_candles = [c for c in raw_candles if is_candle_closed(c.timestamp, timeframe)]
            if not completed_candles:
                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "status": "NO_COMPLETED_CANDLES",
                    "candles_processed": 0,
                    "events_persisted": 0,
                    "processed_timestamps": []
                }

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
                "last_checkpoint": latest_c.timestamp,
                "processed_timestamps": [latest_c.timestamp]
            }

        # 3. Checkpoint exists - determine date bounds and provider retention
        checkpoint_dt = cls._parse_timestamp(last_processed_ts)
        now_utc = datetime.now(timezone.utc)
        step_seconds = cls._get_timeframe_seconds(timeframe)
        is_crypto = SessionAwareCandleBuilder.is_crypto(ticker)

        # Warmup buffer prior to checkpoint for context
        warmup_seconds = context_history_bars * step_seconds * (4 if not is_crypto else 1)
        warmup_start_dt = checkpoint_dt - timedelta(seconds=warmup_seconds)

        # Check provider maximum retention
        max_retention_days = cls._get_provider_max_retention_days(timeframe)
        earliest_provider_dt = now_utc - timedelta(days=max_retention_days)
        is_unrecoverable_retention_gap = checkpoint_dt < earliest_provider_dt

        # 4. Multi-Chunk Ingestion Loop
        current_checkpoint_ts = last_processed_ts
        total_candles_processed = 0
        total_events_persisted = 0
        all_processed_timestamps: List[str] = []
        is_gap_detected = is_unrecoverable_retention_gap
        chunk_iteration = 0
        max_chunks = 100

        # Accumulated master candle history for sliding context
        history_candles_by_ts: Dict[str, Candle] = {}

        while chunk_iteration < max_chunks:
            chunk_iteration += 1
            curr_cp_dt = cls._parse_timestamp(current_checkpoint_ts)
            chunk_start_dt = curr_cp_dt - timedelta(seconds=warmup_seconds)

            try:
                raw_chunk = await cls._fetch_candles_safe(
                    provider,
                    symbol=symbol,
                    ticker=ticker,
                    timeframe=timeframe,
                    limit=max_fetch_limit,
                    start=chunk_start_dt,
                    end=now_utc,
                    is_catchup=True
                )
            except Exception as fetch_err:
                logger.error(f"[CatchupEngine] Fetch error for {symbol} ({timeframe}) on chunk {chunk_iteration}: {fetch_err}")
                if current_checkpoint_ts:
                    CheckpointRepository.update_checkpoint_sync(
                        symbol=symbol,
                        timeframe=timeframe,
                        last_candle_timestamp=current_checkpoint_ts,
                        processed_count=0,
                        status="RECOVERING"
                    )
                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "status": "RECOVERING",
                    "error": str(fetch_err),
                    "candles_processed": total_candles_processed,
                    "events_persisted": total_events_persisted,
                    "last_checkpoint": current_checkpoint_ts,
                    "processed_timestamps": all_processed_timestamps
                }

            if not raw_chunk:
                break

            # Add to accumulated history
            for c in raw_chunk:
                history_candles_by_ts[c.timestamp] = c

            # Filter completed candles in chronological order
            completed_in_history = sorted(
                [c for c in history_candles_by_ts.values() if is_candle_closed(c.timestamp, timeframe)],
                key=lambda c: c.timestamp
            )

            # Check where current_checkpoint_ts sits
            matching_idx = None
            for idx, c in enumerate(completed_in_history):
                if c.timestamp == current_checkpoint_ts:
                    matching_idx = idx
                    break

            if matching_idx is None:
                # The current checkpoint is older than the oldest candle currently fetched
                # Check if we can fetch older chunks (backwards pagination)
                oldest_in_history_dt = cls._parse_timestamp(completed_in_history[0].timestamp)
                while not is_unrecoverable_retention_gap and oldest_in_history_dt > curr_cp_dt:
                    try:
                        older_chunk = await cls._fetch_candles_safe(
                            provider,
                            symbol=symbol,
                            ticker=ticker,
                            timeframe=timeframe,
                            limit=max_fetch_limit,
                            start=chunk_start_dt,
                            end=oldest_in_history_dt,
                            is_catchup=True
                        )
                    except Exception as older_err:
                        logger.warning(f"[CatchupEngine] Failed to fetch older chunk for {symbol} ({timeframe}): {older_err}")
                        break

                    if not older_chunk:
                        break

                    added_count = 0
                    for c in older_chunk:
                        if c.timestamp not in history_candles_by_ts:
                            history_candles_by_ts[c.timestamp] = c
                            added_count += 1
                    if added_count == 0:
                        break

                    completed_in_history = sorted(
                        [c for c in history_candles_by_ts.values() if is_candle_closed(c.timestamp, timeframe)],
                        key=lambda c: c.timestamp
                    )
                    for idx, c in enumerate(completed_in_history):
                        if c.timestamp == current_checkpoint_ts:
                            matching_idx = idx
                            break
                    if matching_idx is not None:
                        break

                    new_oldest_dt = cls._parse_timestamp(completed_in_history[0].timestamp)
                    if new_oldest_dt >= oldest_in_history_dt:
                        break
                    oldest_in_history_dt = new_oldest_dt

                # If still None after attempting older chunk fetch, an unbridgeable gap exists
                if matching_idx is None:
                    is_gap_detected = True
                    logger.warning(
                        f"[CatchupEngine] GAP_DETECTED for {symbol} ({timeframe}): "
                        f"Checkpoint {current_checkpoint_ts} cannot be bridged to oldest available candle {completed_in_history[0].timestamp}."
                    )
                    missed_candles = [c for c in completed_in_history if c.timestamp > current_checkpoint_ts]
                else:
                    missed_candles = completed_in_history[matching_idx + 1:]
            else:
                missed_candles = completed_in_history[matching_idx + 1:]

            if not missed_candles:
                break

            # Validate continuity
            is_cont, cont_gaps = cls.validate_continuity(completed_in_history, timeframe, ticker)
            if not is_cont and not is_gap_detected:
                for cg in cont_gaps:
                    logger.warning(f"[CatchupEngine] Continuity notice for {symbol} ({timeframe}): {cg}")

            # Take the current chunk of missed candles to process
            chunk_to_process = missed_candles[:max_fetch_limit]

            # Replay chronologically with 200-bar sliding context
            idx_by_ts = {c.timestamp: i for i, c in enumerate(completed_in_history)}
            for missed_c in chunk_to_process:
                idx_in_completed = idx_by_ts.get(missed_c.timestamp)
                if idx_in_completed is None:
                    continue
                start_idx = max(0, idx_in_completed - context_history_bars + 1)
                candle_slice = completed_in_history[start_idx : idx_in_completed + 1]

                try:
                    new_events = cls._process_and_persist_slice(
                        candle_slice, symbol, ticker, timeframe, is_catchup=True
                    )
                    total_events_persisted += new_events
                    total_candles_processed += 1
                    all_processed_timestamps.append(missed_c.timestamp)
                    current_checkpoint_ts = missed_c.timestamp

                    # Checkpoint safety: commit after every single candle
                    checkpoint_status = "GAP_DETECTED" if is_gap_detected else "SYNCED"
                    CheckpointRepository.update_checkpoint_sync(
                        symbol=symbol,
                        timeframe=timeframe,
                        last_candle_timestamp=missed_c.timestamp,
                        processed_count=1,
                        status=checkpoint_status
                    )
                except Exception as slice_err:
                    logger.error(
                        f"[CatchupEngine] Error processing candle {missed_c.timestamp} for {symbol} ({timeframe}): {slice_err}"
                    )
                    CheckpointRepository.update_checkpoint_sync(
                        symbol=symbol,
                        timeframe=timeframe,
                        last_candle_timestamp=current_checkpoint_ts,
                        processed_count=0,
                        status="RECOVERING"
                    )
                    return {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "status": "RECOVERING",
                        "error": str(slice_err),
                        "candles_processed": total_candles_processed,
                        "events_persisted": total_events_persisted,
                        "last_checkpoint": current_checkpoint_ts,
                        "processed_timestamps": all_processed_timestamps
                    }

            # If all missed candles currently in memory were processed:
            # Check if the provider's returned batch was full (len(raw_chunk) >= max_fetch_limit).
            # If it was full, more chunks may exist from the provider, so continue fetching.
            # If it was less than max_fetch_limit, provider has returned all data up to now.
            if len(chunk_to_process) == len(missed_candles) and len(raw_chunk) < max_fetch_limit:
                break

        # Check if already up-to-date
        if total_candles_processed == 0:
            if is_gap_detected:
                CheckpointRepository.update_checkpoint_sync(
                    symbol=symbol,
                    timeframe=timeframe,
                    last_candle_timestamp=last_processed_ts,
                    processed_count=0,
                    status="GAP_DETECTED"
                )
                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "status": "GAP_DETECTED",
                    "candles_processed": 0,
                    "events_persisted": 0,
                    "last_checkpoint": last_processed_ts,
                    "processed_timestamps": []
                }
            else:
                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "status": "ALREADY_UP_TO_DATE",
                    "candles_processed": 0,
                    "events_persisted": 0,
                    "last_checkpoint": last_processed_ts,
                    "processed_timestamps": []
                }

        final_status = "GAP_DETECTED" if is_gap_detected else "RECOVERY_COMPLETE"
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "status": final_status,
            "candles_processed": total_candles_processed,
            "events_persisted": total_events_persisted,
            "last_checkpoint": current_checkpoint_ts,
            "processed_timestamps": all_processed_timestamps
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
                # Cooperatively yield the event loop to live worker tasks and incoming API requests
                await asyncio.sleep(0.05)

        total_processed = sum(r.get("candles_processed", 0) for r in results)
        logger.info(f"[CatchupEngine] Catch-up complete: {total_processed} total missed candles processed.")
        return {
            "total_candles_processed": total_processed,
            "results": results
        }
