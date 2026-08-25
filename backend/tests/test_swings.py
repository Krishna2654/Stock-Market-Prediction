import pytest
from app.models.schemas import Candle
from app.market_structure.swings import SwingDetector

def create_sample_candles():
    candles = []
    prices = [
        100, 101, 103, 105, 107, 108, 109, 115, 108, 106, 104, 101, 98, 95, 88, 93, 96, 99, 102, 105, 108, 110, 112, 114, 116
    ]
    for i, p in enumerate(prices):
        candles.append(Candle(
            timestamp=f"2026-08-24T10:{i:02d}:00Z",
            open=p - 0.5,
            high=p + 1.0,
            low=p - 1.0,
            close=p,
            volume=1000.0
        ))
    return candles

def test_swing_detection():
    candles = create_sample_candles()
    swings, protected_swing = SwingDetector.detect_swings(candles, swing_length=3, confirmation_candles=1)
    
    assert len(swings) >= 2
    high_swings = [s for s in swings if s.is_high]
    low_swings = [s for s in swings if not s.is_high]
    
    assert len(high_swings) > 0
    assert len(low_swings) > 0
    assert high_swings[0].price == pytest.approx(116.0, 0.1)
    assert low_swings[0].price == pytest.approx(87.0, 0.1)
    assert protected_swing is not None
