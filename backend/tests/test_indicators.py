import pytest
from datetime import datetime, timedelta, timezone
from app.models.schemas import Candle
from app.indicators.technical import TechnicalIndicatorEngine

def test_indicators():
    base_time = datetime(2026, 8, 24, 9, 15, tzinfo=timezone.utc)
    candles = [
        Candle(
            timestamp=(base_time + timedelta(minutes=5 * i)).isoformat(),
            open=100.0 + i,
            high=102.0 + i,
            low=99.0 + i,
            close=101.0 + i,
            volume=1000.0 + (i * 50)
        )
        for i in range(40)
    ]
    
    df, indicators = TechnicalIndicatorEngine.compute_all_indicators(candles)
    
    assert not df.empty
    assert "ema_20" in df.columns
    assert "rsi_14" in df.columns
    assert "atr_14" in df.columns
    assert indicators.ema_20 is not None
    assert indicators.rsi_14 is not None
    assert indicators.rsi_14 > 50  # Steady uptrend should yield RSI > 50
    assert indicators.atr_14 is not None
