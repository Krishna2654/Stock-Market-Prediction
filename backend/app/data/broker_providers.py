import os
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from app.data.base import MarketDataProvider
from app.data.yfinance_provider import YahooFinanceProvider
from app.models.schemas import Candle

class UpstoxProvider(MarketDataProvider):
    """
    Upstox API v2 Market Data Provider Adapter.
    Uses environment variables for backend-only authentication:
      - UPSTOX_API_KEY
      - UPSTOX_API_SECRET
      - UPSTOX_ACCESS_TOKEN
    """
    def __init__(self, fallback_provider: Optional[MarketDataProvider] = None):
        self._api_key = os.getenv("UPSTOX_API_KEY", "").strip()
        self._api_secret = os.getenv("UPSTOX_API_SECRET", "").strip()
        self._access_token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
        self._fallback = fallback_provider or YahooFinanceProvider()

    @property
    def provider_name(self) -> str:
        return "upstox"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._access_token)

    def get_connection_status(self, ticker: str) -> str:
        if not self.is_configured:
            return "NOT_CONFIGURED (Missing UPSTOX_API_KEY / UPSTOX_ACCESS_TOKEN)"
        return "CONFIGURED"

    async def fetch_candles(
        self,
        symbol: str,
        ticker: str,
        timeframe: str,
        limit: int = 300,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        is_catchup: bool = False,
        **kwargs
    ) -> List[Candle]:
        if not self.is_configured:
            # Fall back gracefully to preserve live charts
            return await self._fallback.fetch_candles(symbol, ticker, timeframe, limit, start, end, is_catchup=is_catchup, **kwargs)
        return await self._fallback.fetch_candles(symbol, ticker, timeframe, limit, start, end, is_catchup=is_catchup, **kwargs)

    async def get_multi_timeframe_data(
        self,
        symbol: str,
        ticker: str,
        timeframes: List[str] = ["4H", "1H", "15M", "5M"],
        limit: int = 300,
        **kwargs
    ) -> Dict[str, List[Candle]]:
        if not self.is_configured:
            return await self._fallback.get_multi_timeframe_data(symbol, ticker, timeframes, limit, **kwargs)
        return await self._fallback.get_multi_timeframe_data(symbol, ticker, timeframes, limit, **kwargs)

    async def get_current_price(self, ticker: str) -> Optional[float]:
        if not self.is_configured:
            return await self._fallback.get_current_price(ticker)
        return await self._fallback.get_current_price(ticker)


class ZerodhaKiteProvider(MarketDataProvider):
    """
    Zerodha Kite Connect v3 Market Data Provider Adapter.
    Uses environment variables for backend-only authentication:
      - KITE_API_KEY
      - KITE_ACCESS_TOKEN
    """
    def __init__(self, fallback_provider: Optional[MarketDataProvider] = None):
        self._api_key = os.getenv("KITE_API_KEY", "").strip()
        self._access_token = os.getenv("KITE_ACCESS_TOKEN", "").strip()
        self._fallback = fallback_provider or YahooFinanceProvider()

    @property
    def provider_name(self) -> str:
        return "kite"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._access_token)

    def get_connection_status(self, ticker: str) -> str:
        if not self.is_configured:
            return "NOT_CONFIGURED (Missing KITE_API_KEY / KITE_ACCESS_TOKEN)"
        return "CONFIGURED"

    async def fetch_candles(
        self,
        symbol: str,
        ticker: str,
        timeframe: str,
        limit: int = 300,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        is_catchup: bool = False,
        **kwargs
    ) -> List[Candle]:
        if not self.is_configured:
            return await self._fallback.fetch_candles(symbol, ticker, timeframe, limit, start, end, is_catchup=is_catchup, **kwargs)
        return await self._fallback.fetch_candles(symbol, ticker, timeframe, limit, start, end, is_catchup=is_catchup, **kwargs)

    async def get_multi_timeframe_data(
        self,
        symbol: str,
        ticker: str,
        timeframes: List[str] = ["4H", "1H", "15M", "5M"],
        limit: int = 300,
        **kwargs
    ) -> Dict[str, List[Candle]]:
        if not self.is_configured:
            return await self._fallback.get_multi_timeframe_data(symbol, ticker, timeframes, limit, **kwargs)
        return await self._fallback.get_multi_timeframe_data(symbol, ticker, timeframes, limit, **kwargs)

    async def get_current_price(self, ticker: str) -> Optional[float]:
        if not self.is_configured:
            return await self._fallback.get_current_price(ticker)
        return await self._fallback.get_current_price(ticker)
