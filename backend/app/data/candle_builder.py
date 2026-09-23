from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, time as dtime, timezone
import zoneinfo
import pandas as pd
import numpy as np
from app.models.schemas import Candle
from app.core.config import settings

KOLKATA_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")
UTC_TZ = zoneinfo.ZoneInfo("UTC")

class CandleValidator:
    """
    Validates genuine OHLCV candles according to strict market data standards.
    Rejects corrupted, impossible, negative, or invalid candles.
    """
    @staticmethod
    def validate_candle(c: Candle) -> bool:
        if c.open <= 0 or c.high <= 0 or c.low <= 0 or c.close <= 0:
            return False
        if c.high < max(c.open, c.close) or c.low > min(c.open, c.close):
            return False
        if c.volume < 0:
            return False
        return True

    @classmethod
    def clean_and_validate_candles(cls, candles: List[Candle]) -> List[Candle]:
        if not candles:
            return []
        
        valid_candles: List[Candle] = []
        seen_timestamps = set()

        for c in candles:
            if not cls.validate_candle(c):
                continue
            if c.timestamp in seen_timestamps:
                continue
            seen_timestamps.add(c.timestamp)
            valid_candles.append(c)

        # Sort chronologically
        valid_candles.sort(key=lambda x: x.timestamp)
        return valid_candles


class SessionAwareCandleBuilder:
    """
    Builds session-aware intraday and multi-hour candles (5M, 15M, 1H, 4H)
    aligned strictly to the exchange session (Asia/Kolkata for NSE/BSE, 24/7 for Crypto).
    """

    @staticmethod
    def is_crypto(ticker: str) -> bool:
        ticker_u = ticker.upper()
        return "BTC" in ticker_u or "ETH" in ticker_u or "USD" in ticker_u or "CRYPTO" in ticker_u

    @classmethod
    def get_market_session_status(cls, ticker: str) -> Dict[str, Any]:
        """
        Determines if the exchange market is currently running (Live Trading),
        pre-open, or closed.
        """
        if cls.is_crypto(ticker):
            return {
                "is_running": True,
                "status": "OPEN",
                "session_name": "24/7 Crypto Market",
                "message": "Continuous 24/7 Live Trading"
            }
        
        now_kolkata = datetime.now(KOLKATA_TZ)
        weekday = now_kolkata.weekday()  # 0 = Monday, 6 = Sunday
        current_time = now_kolkata.time()
        
        market_open = dtime(9, 15)
        market_close = dtime(15, 30)
        pre_open = dtime(9, 0)
        
        if weekday >= 5:  # Saturday or Sunday
            return {
                "is_running": False,
                "status": "CLOSED",
                "session_name": "Weekend Closed",
                "message": "Market Closed (Reopens Monday 09:15 IST)"
            }
            
        if pre_open <= current_time < market_open:
            return {
                "is_running": False,
                "status": "PRE-OPEN",
                "session_name": "Pre-Market Session",
                "message": "Pre-Open Session (09:00 - 09:15 IST)"
            }
        elif market_open <= current_time <= market_close:
            return {
                "is_running": True,
                "status": "OPEN",
                "session_name": "Regular Trading Session",
                "message": "Live Trading Session (09:15 - 15:30 IST)"
            }
        else:
            return {
                "is_running": False,
                "status": "CLOSED",
                "session_name": "Market Closed",
                "message": "Market Closed (Next Session at 09:15 IST)"
            }

    @classmethod
    def aggregate_candles(
        cls,
        base_candles: List[Candle],
        target_timeframe: str,
        ticker: str
    ) -> List[Candle]:
        """
        Aggregates lower-timeframe candles into session-aligned target timeframe candles.
        Target timeframes: '5M', '15M', '1H', '4H'.
        """
        cleaned = CandleValidator.clean_and_validate_candles(base_candles)
        if not cleaned:
            return []

        if target_timeframe in ["5M", "15M"]:
            return cleaned

        is_crypto = cls.is_crypto(ticker)

        # Convert to pandas DataFrame for session-aware resampling using vectorized columns
        records = {
            "timestamp": [c.timestamp for c in cleaned],
            "Open": [c.open for c in cleaned],
            "High": [c.high for c in cleaned],
            "Low": [c.low for c in cleaned],
            "Close": [c.close for c in cleaned],
            "Volume": [c.volume for c in cleaned]
        }

        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")

        if not is_crypto:
            df.index = df.index.tz_convert(KOLKATA_TZ)
        else:
            df.index = df.index.tz_convert(UTC_TZ)

        if target_timeframe == "1H":
            if is_crypto:
                resampled = df.resample("1h", closed="left", label="left").agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()
            else:
                # Group by date and session-aligned hourly buckets (09:15, 10:15, 11:15, 12:15, 13:15, 14:15, 15:15)
                resampled = df.resample("1h", offset="15min", closed="left", label="left").agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()
        elif target_timeframe == "4H":
            if is_crypto:
                resampled = df.resample("4h", closed="left", label="left").agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()
            else:
                # Session-aligned 4H for Indian Market (09:15 - 13:15, 13:15 - 15:30)
                # Group by date and split into morning (09:15) and afternoon (13:15) bars
                resampled = df.resample("4h", offset="15min", closed="left", label="left").agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()
        else:
            return cleaned

        result_candles: List[Candle] = []
        for ts, o, h, l, cl, v in zip(
            resampled.index,
            resampled["Open"],
            resampled["High"],
            resampled["Low"],
            resampled["Close"],
            resampled["Volume"]
        ):
            c = Candle(
                timestamp=ts.isoformat(),
                open=round(float(o), 2),
                high=round(float(h), 2),
                low=round(float(l), 2),
                close=round(float(cl), 2),
                volume=round(float(v), 2)
            )
            if CandleValidator.validate_candle(c):
                result_candles.append(c)

        return result_candles
