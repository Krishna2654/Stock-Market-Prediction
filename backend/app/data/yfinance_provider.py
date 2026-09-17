import asyncio
import time
import logging
from typing import List, Dict, Optional
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
from app.models.schemas import Candle
from app.data.base import MarketDataProvider
from app.data.normalizer import DataNormalizer
from app.data.candle_builder import SessionAwareCandleBuilder, CandleValidator

logger = logging.getLogger(__name__)

class YahooFinanceProvider(MarketDataProvider):
    """
    100% Real Live Market Data Provider via Yahoo Finance with High-Speed Session Caching.
    Streams genuine OHLCV candles from global and Indian exchanges (NSE, BSE, NASDAQ, NYSE, Crypto).
    Never uses synthetic or fake data.
    Features:
    - Single-flight in-flight request deduplication (prevents redundant Yahoo queries).
    - Tiered TTL caching for lightning fast responses.
    - Zero-latency 4H memory aggregation from 1H candles.
    """
    
    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._last_valid_state: Dict[str, List[Candle]] = {}
        self._connection_status: Dict[str, str] = {}
        self._ticker_instances: Dict[str, yf.Ticker] = {}
        self._in_flight_tasks: Dict[str, asyncio.Task] = {}
        self._cache_ttl_seconds = {
            "5M": 30,   # 30s cache for 5M candles
            "15M": 60,  # 60s cache for 15M candles
            "1H": 120,  # 120s cache for 1H candles
            "4H": 300   # 300s cache for 4H candles
        }
        self._retry_attempts = 2
        self._backoff_factor = 1.0
        self._init_semaphores()

    _interactive_semaphore: Optional[asyncio.Semaphore] = None
    _worker_semaphore: Optional[asyncio.Semaphore] = None
    _catchup_semaphore: Optional[asyncio.Semaphore] = None
    _live_semaphore: Optional[asyncio.Semaphore] = None
    _semaphore_loop: Optional[asyncio.AbstractEventLoop] = None

    @classmethod
    def _init_semaphores(cls):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if cls._interactive_semaphore is None or cls._semaphore_loop != loop:
            cls._interactive_semaphore = asyncio.Semaphore(5)
            cls._worker_semaphore = asyncio.Semaphore(3)
            cls._catchup_semaphore = asyncio.Semaphore(1)
            cls._live_semaphore = cls._worker_semaphore  # backward-compatible alias (value 3)
            cls._semaphore_loop = loop

    @classmethod
    def _get_interactive_semaphore(cls) -> asyncio.Semaphore:
        cls._init_semaphores()
        return cls._interactive_semaphore

    @classmethod
    def _get_worker_semaphore(cls) -> asyncio.Semaphore:
        cls._init_semaphores()
        return cls._worker_semaphore

    @classmethod
    def _get_catchup_semaphore(cls) -> asyncio.Semaphore:
        cls._init_semaphores()
        return cls._catchup_semaphore

    @classmethod
    def _get_live_semaphore(cls) -> asyncio.Semaphore:
        # Backward-compatible alias (capacity 3)
        return cls._get_worker_semaphore()

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        # Backward-compatible alias (capacity 3)
        return cls._get_worker_semaphore()

    @property
    def provider_name(self) -> str:
        return "Yahoo Finance (Live Exchange Feed)"

    def get_connection_status(self, ticker: str) -> str:
        clean_ticker = (ticker or "").strip().replace("/", "-")
        return self._connection_status.get(clean_ticker, "LIVE")

    def _get_cache_key(self, ticker: str, timeframe: str) -> str:
        clean_ticker = (ticker or "").strip().replace("/", "-")
        return f"{clean_ticker}_{timeframe}"

    def _get_ticker_instance(self, ticker: str) -> yf.Ticker:
        clean_ticker = (ticker or "").strip().replace("/", "-")
        if clean_ticker not in self._ticker_instances:
            self._ticker_instances[clean_ticker] = yf.Ticker(clean_ticker)
        return self._ticker_instances[clean_ticker]

    def _sync_fetch(
        self,
        ticker: str,
        timeframe: str,
        limit: int,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[Candle]:
        clean_ticker = (ticker or "").strip().replace("/", "-")
        tf_config = {
            "5M": {"interval": "5m", "period": "60d"},
            "15M": {"interval": "15m", "period": "60d"},
            "1H": {"interval": "60m", "period": "730d"},
            "4H": {"interval": "60m", "period": "730d"}
        }
        
        cfg = tf_config.get(timeframe, {"interval": "60m", "period": "60d"})
        t = self._get_ticker_instance(clean_ticker)
        
        try:
            if start is not None or end is not None:
                df = t.history(start=start, end=end, interval=cfg["interval"], auto_adjust=False, raise_errors=False)
            else:
                df = t.history(period=cfg["period"], interval=cfg["interval"], auto_adjust=False, raise_errors=False)
            
            if df is None or df.empty:
                return []
            
            raw_candles: List[Candle] = []
            for ts, row in df.iterrows():
                ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                c = Candle(
                    timestamp=ts_str,
                    open=round(float(row["Open"]), 2),
                    high=round(float(row["High"]), 2),
                    low=round(float(row["Low"]), 2),
                    close=round(float(row["Close"]), 2),
                    volume=float(row["Volume"]) if "Volume" in row and not pd.isna(row["Volume"]) else 0.0
                )
                raw_candles.append(c)

            # Aggregate with session awareness
            aggregated = SessionAwareCandleBuilder.aggregate_candles(raw_candles, timeframe, clean_ticker)
            
            # Truncate to limit ONLY when not requesting a specific date range
            if start is None and end is None and len(aggregated) > limit:
                aggregated = aggregated[-limit:]
                
            normalized, _, _ = DataNormalizer.normalize_candles(aggregated)
            self._connection_status[clean_ticker] = "LIVE"
            return normalized

        except Exception as e:
            logger.warning(f"[YahooFinanceProvider] Fetch error for {clean_ticker} ({timeframe}): {e}")
            self._connection_status[clean_ticker] = "RECONNECTING"
            return []

    async def fetch_candles(
        self,
        symbol: str,
        ticker: str,
        timeframe: str,
        limit: int = 300,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        is_catchup: bool = False,
        is_interactive: bool = False,
        is_worker: bool = False,
        **kwargs
    ) -> List[Candle]:
        # Concurrency isolation:
        # 1. Catchup/range queries use _catchup_semaphore (1 slot)
        # 2. Worker background cycles use _worker_semaphore (3 slots)
        # 3. Interactive user requests use _interactive_semaphore (5 slots)
        if is_catchup or (start is not None or end is not None):
            target_semaphore = self._get_catchup_semaphore()
        elif is_worker:
            target_semaphore = self._get_worker_semaphore()
        else:
            target_semaphore = self._get_interactive_semaphore()

        clean_ticker = (ticker or "").strip().replace("/", "-")

        # If date range is requested, bypass the short-term live TTL cache
        if start is not None or end is not None:
            async with target_semaphore:
                try:
                    return await asyncio.wait_for(
                        asyncio.to_thread(self._sync_fetch, clean_ticker, timeframe, limit, start, end),
                        timeout=12.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"[YahooFinanceProvider] Range fetch timed out after 12s for {clean_ticker} ({timeframe})")
                    return []

        cache_key = self._get_cache_key(clean_ticker, timeframe)
        now = time.time()
        ttl = self._cache_ttl_seconds.get(timeframe, 45)
        
        # Check TTL cache for instant return (0ms)
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry["timestamp"] < ttl:
                return entry["data"]

        # If already in flight, reuse existing future to avoid duplicate requests
        if cache_key in self._in_flight_tasks:
            try:
                return await self._in_flight_tasks[cache_key]
            except Exception:
                pass

        async def _do_fetch() -> List[Candle]:
            try:
                async with target_semaphore:
                    try:
                        candles = await asyncio.wait_for(
                            asyncio.to_thread(self._sync_fetch, clean_ticker, timeframe, limit, None, None),
                            timeout=12.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"[YahooFinanceProvider] Fetch timed out after 12s for {clean_ticker} ({timeframe})")
                        candles = []
                if candles:
                    self._cache[cache_key] = {
                        "timestamp": time.time(),
                        "data": candles
                    }
                    self._last_valid_state[cache_key] = candles
                    self._connection_status[clean_ticker] = "LIVE"
                    return candles
                
                # Fallback to last valid real state
                if cache_key in self._last_valid_state:
                    return self._last_valid_state[cache_key]
                    
                return []
            finally:
                self._in_flight_tasks.pop(cache_key, None)

        task = asyncio.create_task(_do_fetch())
        self._in_flight_tasks[cache_key] = task
        return await task

    async def get_multi_timeframe_data(
        self,
        symbol: str,
        ticker: str,
        timeframes: List[str] = ["4H", "1H", "15M", "5M"],
        limit: int = 300,
        is_catchup: bool = False,
        is_interactive: bool = False,
        is_worker: bool = False,
        **kwargs
    ) -> Dict[str, List[Candle]]:
        # Fetch 5M, 15M, and 1H in parallel using the specified concurrency class
        needed_fetch = [tf for tf in timeframes if tf != "4H"]
        tasks = [
            self.fetch_candles(
                symbol,
                ticker,
                tf,
                limit,
                is_catchup=is_catchup,
                is_interactive=is_interactive,
                is_worker=is_worker
            )
            for tf in needed_fetch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        result_map: Dict[str, List[Candle]] = {}
        for tf, res in zip(needed_fetch, results):
            if isinstance(res, list):
                result_map[tf] = res
            else:
                result_map[tf] = []

        # If 4H is requested, aggregate from 1H candles in memory with zero network delay
        if "4H" in timeframes:
            if "1H" in result_map and len(result_map["1H"]) > 0:
                h4_candles = SessionAwareCandleBuilder.aggregate_candles(result_map["1H"], "4H", ticker)
                result_map["4H"] = h4_candles
            else:
                result_map["4H"] = await self.fetch_candles(
                    symbol,
                    ticker,
                    "4H",
                    limit,
                    is_catchup=is_catchup,
                    is_interactive=is_interactive,
                    is_worker=is_worker
                )

        return result_map

    async def get_current_price(self, ticker: str) -> Optional[float]:
        try:
            candles = await self.fetch_candles("", ticker, "5M", limit=5)
            if candles:
                return candles[-1].close
        except Exception:
            pass
        return None


# Alias for backward compatibility
YFinanceProvider = YahooFinanceProvider

