import numpy as np
import pandas as pd
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from app.models.schemas import Candle
from app.data.base import MarketDataProvider
from app.data.normalizer import DataNormalizer

class SimulatedMarketDataProvider(MarketDataProvider):
    """
    Dynamic Synthetic Market Data Engine.
    Evolves live trending waves and produces authentic Trendline & Resistance breaks
    for live simulation and testing across Equities, Indices, and Crypto.
    """
    
    def __init__(self, base_prices: Optional[Dict[str, float]] = None):
        self.base_prices = base_prices or {
            "BTC-USD": 79380.0,
            "BTC/USD": 79380.0,
            "^NSEI": 24220.0,
            "NIFTY 50": 24220.0,
            "^NSEBANK": 57520.0,
            "BANK NIFTY": 57520.0,
            "RELIANCE.NS": 1310.0,
            "RELIANCE": 1310.0,
            "HDFCBANK.NS": 729.0,
            "HDFCBANK": 729.0,
            "ICICIBANK.NS": 1415.0,
            "ICICIBANK": 1415.0,
            "TCS.NS": 2284.0,
            "TCS": 2284.0,
            "INFY.NS": 1130.0,
            "INFY": 1130.0,
            "SBIN.NS": 1040.0,
            "SBIN": 1040.0,
            "BHARTIARTL.NS": 1935.0,
            "BHARTI AIRTEL": 1935.0,
            "LT.NS": 4090.0,
            "MARUTI.NS": 13620.0,
        }
        self.start_epoch = time.time()

    @property
    def provider_name(self) -> str:
        return "Simulated Data Engine"

    def _get_base_price(self, symbol: str, ticker: str) -> float:
        return self.base_prices.get(ticker, self.base_prices.get(symbol, 1000.0))

    def _generate_synthetic_series(
        self,
        base_price: float,
        timeframe: str,
        limit: int = 250
    ) -> List[Candle]:
        tf_minutes = {
            "5M": 5,
            "15M": 15,
            "1H": 60,
            "4H": 240
        }.get(timeframe, 15)
        
        volatility_pct = {
            "5M": 0.0012,
            "15M": 0.0025,
            "1H": 0.0055,
            "4H": 0.012
        }.get(timeframe, 0.003)
        
        elapsed_blocks = int((time.time() - self.start_epoch) / 30)
        custom_seed = int((base_price * 100) % 10000) + tf_minutes + (elapsed_blocks % 50)
        rng = np.random.default_rng(custom_seed)
        
        end_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        end_time -= timedelta(minutes=end_time.minute % 5)
        
        start_time = end_time - timedelta(minutes=tf_minutes * limit)
        
        t = np.linspace(0, 4 * np.pi, limit)
        trend_drift = np.linspace(0, 0.045, limit)
        macro_wave = 0.02 * np.sin(t)
        micro_wave = 0.008 * np.sin(3 * t)
        noise = rng.normal(0, volatility_pct, limit)
        
        breakout_pulse = np.zeros(limit)
        if elapsed_blocks % 2 == 1:
            breakout_pulse[-3:] = [0.004, 0.008, 0.014]
        
        cum_returns = trend_drift + macro_wave + micro_wave + noise + breakout_pulse
        price_path = base_price * (1.0 + cum_returns)
        
        candles: List[Candle] = []
        current_time = start_time
        
        for i in range(limit):
            close_p = price_path[i]
            prev_close = price_path[i - 1] if i > 0 else close_p * (1 - rng.uniform(0.0005, 0.001))
            
            open_p = prev_close
            candle_volatility = close_p * volatility_pct * rng.uniform(0.8, 1.6)
            
            high_p = max(open_p, close_p) + abs(rng.normal(0, candle_volatility * 0.7))
            low_p = min(open_p, close_p) - abs(rng.normal(0, candle_volatility * 0.7))
            
            price_change = abs(close_p - open_p) / open_p
            base_vol = (base_price * 150.0) / (base_price ** 0.5)
            vol = base_vol * (1.0 + price_change * 50.0) * rng.uniform(0.7, 1.4)
            
            ts_str = current_time.isoformat()
            
            candles.append(Candle(
                timestamp=ts_str,
                open=round(float(open_p), 2),
                high=round(float(high_p), 2),
                low=round(float(low_p), 2),
                close=round(float(close_p), 2),
                volume=round(float(vol), 0)
            ))
            
            current_time += timedelta(minutes=tf_minutes)
            
        normalized, _, _ = DataNormalizer.normalize_candles(candles)
        return normalized

    async def fetch_candles(
        self,
        symbol: str,
        ticker: str,
        timeframe: str,
        limit: int = 300
    ) -> List[Candle]:
        base_price = self._get_base_price(symbol, ticker)
        return self._generate_synthetic_series(base_price, timeframe, limit)

    async def get_multi_timeframe_data(
        self,
        symbol: str,
        ticker: str,
        timeframes: List[str] = ["4H", "1H", "15M", "5M"],
        limit: int = 300
    ) -> Dict[str, List[Candle]]:
        base_price = self._get_base_price(symbol, ticker)
        return {
            tf: self._generate_synthetic_series(base_price, tf, limit)
            for tf in timeframes
        }

    async def get_current_price(self, ticker: str) -> Optional[float]:
        return self.base_prices.get(ticker, 1000.0)
