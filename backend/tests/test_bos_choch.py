import pytest
from app.models.schemas import Candle, SwingPoint
from app.market_structure.bos_choch import BOSCHoCHDetector

def test_bos_detection():
    # Construct sequence:
    # 1. Swings establish a High at 100.0 (index 5)
    # 2. Price retraces then surges and closes at 105.0 (index 12)
    candles = []
    for i in range(20):
        price = 90.0 + (i * 1.5) if i <= 5 else (97.5 - (i - 5) * 1.0 if i <= 10 else 92.5 + (i - 10) * 2.5)
        candles.append(Candle(
            timestamp=f"2026-08-24T10:{i:02d}:00Z",
            open=price - 0.5,
            high=price + 1.0,
            low=price - 1.0,
            close=price,
            volume=5000.0
        ))
    
    # Swing High at index 5 with price 98.5
    swings = [
        SwingPoint(index=5, timestamp=candles[5].timestamp, price=98.5, type="HH", is_high=True, confirmed=True, confirmation_index=7),
        SwingPoint(index=10, timestamp=candles[10].timestamp, price=91.5, type="HL", is_high=False, confirmed=True, confirmation_index=11)
    ]
    
    breaks = BOSCHoCHDetector.detect_structure_breaks(
        candles=candles,
        swings=swings,
        symbol="TEST",
        timeframe="15M"
    )
    
    assert len(breaks) >= 1
    assert breaks[0].event_type in ["BULLISH_BOS", "BULLISH_CHOCH"]
    assert breaks[0].broken_level == 98.5
    assert breaks[0].break_price >= 98.5
