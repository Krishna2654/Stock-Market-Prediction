from typing import List, Dict, Optional, Tuple
import numpy as np
import pandas as pd
from app.models.schemas import Candle, TechnicalIndicators
from app.data.normalizer import DataNormalizer

class TechnicalIndicatorEngine:
    """
    High-performance, vectorized technical indicator calculation engine.
    Calculates EMA (20, 50, 200), RSI (14), ATR (14), Volume Metrics,
    MACD, Bollinger Bands, and VWAP.
    """
    
    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        # Wilder's Smoothing
        avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        
        # Handle zero loss (pure upward trend) and zero gain (pure downward trend)
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        # If avg_loss is 0 and avg_gain > 0, RSI is 100.0
        rsi = rsi.where(avg_loss != 0, 100.0)
        # If both are 0, RSI is 50.0
        rsi = rsi.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
        return rsi.fillna(50.0)

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        return atr.fillna(tr.mean() if not tr.empty else 1.0)

    @staticmethod
    def calculate_macd(
        series: pd.Series,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Dict[str, pd.Series]:
        ema_fast = series.ewm(span=fast_period, adjust=False).mean()
        ema_slow = series.ewm(span=slow_period, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=signal_period, adjust=False).mean()
        hist = macd - signal
        return {"macd": macd, "signal": signal, "hist": hist}

    @staticmethod
    def calculate_bollinger_bands(
        series: pd.Series,
        period: int = 20,
        num_std: float = 2.0
    ) -> Dict[str, pd.Series]:
        sma = series.rolling(window=period, min_periods=1).mean()
        std = series.rolling(window=period, min_periods=1).std().fillna(0)
        upper = sma + (std * num_std)
        lower = sma - (std * num_std)
        return {"upper": upper, "middle": sma, "lower": lower}

    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> pd.Series:
        # Typical price * Volume / Cumulative Volume
        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        pv = typical_price * df["volume"]
        cum_pv = pv.cumsum()
        cum_vol = df["volume"].cumsum().replace(0, np.nan)
        vwap = (cum_pv / cum_vol).fillna(typical_price)
        return vwap

    @classmethod
    def compute_all_indicators(
        cls,
        candles: List[Candle],
        ema_fast_p: int = 20,
        ema_mid_p: int = 50,
        ema_slow_p: int = 200,
        rsi_p: int = 14,
        atr_p: int = 14
    ) -> Tuple[pd.DataFrame, TechnicalIndicators]:
        """
        Computes all indicators and attaches them as DataFrame columns.
        Returns: (augmented_df, latest_indicator_values)
        """
        df = DataNormalizer.candles_to_dataframe(candles)
        if df.empty:
            return df, TechnicalIndicators()

        # EMAs
        df["ema_20"] = cls.calculate_ema(df["close"], ema_fast_p)
        df["ema_50"] = cls.calculate_ema(df["close"], ema_mid_p)
        df["ema_200"] = cls.calculate_ema(df["close"], ema_slow_p)
        
        # RSI & ATR
        df["rsi_14"] = cls.calculate_rsi(df["close"], rsi_p)
        df["atr_14"] = cls.calculate_atr(df, atr_p)
        
        # Volume Metrics
        df["volume_sma_20"] = df["volume"].rolling(window=20, min_periods=1).mean()
        df["relative_volume"] = (df["volume"] / df["volume_sma_20"].replace(0, np.nan)).fillna(1.0)
        
        # MACD
        macd_dict = cls.calculate_macd(df["close"])
        df["macd"] = macd_dict["macd"]
        df["macd_signal"] = macd_dict["signal"]
        df["macd_hist"] = macd_dict["hist"]
        
        # Bollinger Bands
        bb_dict = cls.calculate_bollinger_bands(df["close"])
        df["bb_upper"] = bb_dict["upper"]
        df["bb_lower"] = bb_dict["lower"]
        
        # VWAP
        df["vwap"] = cls.calculate_vwap(df)

        # Extract latest row as TechnicalIndicators model
        last_row = df.iloc[-1]
        
        latest = TechnicalIndicators(
            ema_20=round(float(last_row["ema_20"]), 2) if not pd.isna(last_row["ema_20"]) else None,
            ema_50=round(float(last_row["ema_50"]), 2) if not pd.isna(last_row["ema_50"]) else None,
            ema_200=round(float(last_row["ema_200"]), 2) if not pd.isna(last_row["ema_200"]) else None,
            rsi_14=round(float(last_row["rsi_14"]), 1) if not pd.isna(last_row["rsi_14"]) else None,
            atr_14=round(float(last_row["atr_14"]), 2) if not pd.isna(last_row["atr_14"]) else None,
            volume_sma_20=round(float(last_row["volume_sma_20"]), 0) if not pd.isna(last_row["volume_sma_20"]) else None,
            relative_volume=round(float(last_row["relative_volume"]), 2) if not pd.isna(last_row["relative_volume"]) else None,
            macd=round(float(last_row["macd"]), 2) if not pd.isna(last_row["macd"]) else None,
            macd_signal=round(float(last_row["macd_signal"]), 2) if not pd.isna(last_row["macd_signal"]) else None,
            macd_hist=round(float(last_row["macd_hist"]), 2) if not pd.isna(last_row["macd_hist"]) else None,
            vwap=round(float(last_row["vwap"]), 2) if not pd.isna(last_row["vwap"]) else None,
            bb_upper=round(float(last_row["bb_upper"]), 2) if not pd.isna(last_row["bb_upper"]) else None,
            bb_lower=round(float(last_row["bb_lower"]), 2) if not pd.isna(last_row["bb_lower"]) else None
        )
        
        return df, latest
