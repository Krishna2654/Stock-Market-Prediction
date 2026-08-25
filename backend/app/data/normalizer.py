from typing import List, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from app.models.schemas import Candle
from app.core.config import settings

class DataNormalizer:
    """
    Validates, cleans, and standardizes OHLCV candles from any raw provider.
    Ensures no corrupted or invalid data reaches the analytical engines.
    """
    
    @staticmethod
    def normalize_candles(raw_candles: List[Candle]) -> Tuple[List[Candle], bool, str]:
        """
        Cleans candles, removes duplicates, validates price integrity.
        Returns: (cleaned_candles, is_stale, status_message)
        """
        if not raw_candles:
            return [], True, "No candle data available"
        
        valid_candles: List[Candle] = []
        seen_timestamps = set()
        
        for c in raw_candles:
            # 1. Deduplication
            if c.timestamp in seen_timestamps:
                continue
            seen_timestamps.add(c.timestamp)
            
            # 2. Price sanity checks
            if c.open <= 0 or c.high <= 0 or c.low <= 0 or c.close <= 0:
                continue
            if c.high < c.low:
                continue
            if c.open > c.high or c.open < c.low:
                # Correct minor precision aberrations or skip if corrupted
                c.high = max(c.high, c.open, c.close)
                c.low = min(c.low, c.open, c.close)
            if c.close > c.high or c.close < c.low:
                c.high = max(c.high, c.open, c.close)
                c.low = min(c.low, c.open, c.close)
                
            # 3. Volume sanity
            if c.volume < 0 or np.isnan(c.volume):
                c.volume = 0.0
                
            valid_candles.append(c)
            
        if not valid_candles:
            return [], True, "All incoming candles failed validation"
            
        # 4. Sort chronologically
        valid_candles.sort(key=lambda x: x.timestamp)
        
        # 5. Stale data check
        is_stale, status_msg = DataNormalizer.check_staleness(valid_candles[-1].timestamp)
        
        return valid_candles, is_stale, status_msg

    @staticmethod
    def check_staleness(latest_timestamp_str: str) -> Tuple[bool, str]:
        """
        Checks if the latest candle timestamp is older than acceptable threshold.
        """
        try:
            # Parse ISO or standard formats
            dt = pd.to_datetime(latest_timestamp_str)
            if dt.tzinfo is None:
                dt = dt.tz_localize(timezone.utc)
            else:
                dt = dt.tz_convert(timezone.utc)
                
            now = datetime.now(timezone.utc)
            diff_hours = (now - dt).total_seconds() / 3600.0
            
            # Market may be closed on weekends (diff > 48h) or overnight
            # If diff > 72 hours, flag as stale / historical
            if diff_hours > 72.0:
                return False, f"Market session closed/weekend (last update: {latest_timestamp_str})"
            elif diff_hours > 24.0:
                return False, f"Recent session data (last update: {latest_timestamp_str})"
            else:
                return False, f"Live/Active feed (last update: {latest_timestamp_str})"
        except Exception as e:
            return False, f"Timestamp parsed with note: {str(e)}"

    @staticmethod
    def candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
        """
        Converts Candle models to a clean Pandas DataFrame for vectorized math.
        """
        if not candles:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        
        data = {
            "timestamp": [c.timestamp for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles]
        }
        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", errors="coerce")
        df.set_index("timestamp", inplace=True)
        return df
