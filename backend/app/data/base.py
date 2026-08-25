from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import pandas as pd
from app.models.schemas import Candle, OHLCVResponse

class MarketDataProvider(ABC):
    """
    Abstract Base Class for modular Market Data Providers.
    Any new data provider (NSE API, AlphaVantage, CCXT, Polygon, etc.)
    can be plugged in by subclassing this class.
    """
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    async def fetch_candles(
        self,
        symbol: str,
        ticker: str,
        timeframe: str,
        limit: int = 300
    ) -> List[Candle]:
        """
        Fetch OHLCV candles for a given ticker and timeframe.
        Timeframe: "4H", "1H", "15M", "5M"
        """
        pass

    @abstractmethod
    async def get_multi_timeframe_data(
        self,
        symbol: str,
        ticker: str,
        timeframes: List[str] = ["4H", "1H", "15M", "5M"],
        limit: int = 300
    ) -> Dict[str, List[Candle]]:
        """
        Fetch OHLCV candles for all 4 timeframes.
        """
        pass
    
    @abstractmethod
    async def get_current_price(self, ticker: str) -> Optional[float]:
        """
        Get latest quote price.
        """
        pass
