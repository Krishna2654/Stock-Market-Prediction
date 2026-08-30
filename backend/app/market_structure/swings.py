from typing import List, Dict, Tuple, Optional
import numpy as np
import pandas as pd
from app.models.schemas import Candle, SwingPoint, ProtectedSwing

class SwingDetector:
    """
    Identifies fractal market structure swing highs and swing lows (HH, HL, LH, LL)
    with configurable sensitivity (swing_length, confirmation window, ATR filtering)
    and tracks protected structural swings.
    """

    @staticmethod
    def _calculate_atr(candles: List[Candle], period: int = 14) -> float:
        if len(candles) < 2:
            return 1.0
        ranges = [
            max(c.high - c.low, abs(c.high - c.close), abs(c.low - c.close))
            for c in candles[-min(period, len(candles)):]
        ]
        return max(float(np.mean(ranges)), 0.0001)

    @classmethod
    def detect_swings(
        cls,
        candles: List[Candle],
        swing_length: int = 5,
        confirmation_candles: int = 2,
        min_atr_distance: float = 0.3,
        swing_left_bars: Optional[int] = None,
        swing_right_bars: Optional[int] = None
    ) -> Tuple[List[SwingPoint], Optional[ProtectedSwing]]:
        left_bars = swing_left_bars if swing_left_bars is not None else swing_length
        right_bars = swing_right_bars if swing_right_bars is not None else swing_length
        conf_candles = confirmation_candles

        if len(candles) < (left_bars + right_bars + 1):
            return [], None

        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])
        n = len(candles)
        atr = cls._calculate_atr(candles)
        
        raw_swings: List[Dict] = []

        # Fractal peak / trough detection
        for i in range(left_bars, n - right_bars):
            current_high = highs[i]
            current_low = lows[i]

            is_swing_high = (
                np.all(current_high >= highs[i - left_bars:i]) and
                np.all(current_high >= highs[i + 1:i + right_bars + 1])
            )
            
            is_swing_low = (
                np.all(current_low <= lows[i - left_bars:i]) and
                np.all(current_low <= lows[i + 1:i + right_bars + 1])
            )

            if is_swing_high:
                raw_swings.append({
                    "index": i,
                    "timestamp": candles[i].timestamp,
                    "price": current_high,
                    "is_high": True,
                    "confirmed": (i + right_bars + conf_candles) <= n,
                    "confirmation_index": i + right_bars
                })
            
            if is_swing_low:
                raw_swings.append({
                    "index": i,
                    "timestamp": candles[i].timestamp,
                    "price": current_low,
                    "is_high": False,
                    "confirmed": (i + right_bars + conf_candles) <= n,
                    "confirmation_index": i + right_bars
                })

        # Sort chronologically by candle index
        raw_swings.sort(key=lambda s: (s["index"], not s["is_high"]))

        # Classify as HH, HL, LH, LL
        classified_swings: List[SwingPoint] = []
        last_high_price: Optional[float] = None
        last_low_price: Optional[float] = None

        for s in raw_swings:
            if s["is_high"]:
                if last_high_price is None:
                    swing_type = "HH"
                elif s["price"] > last_high_price + (min_atr_distance * atr):
                    swing_type = "HH"
                else:
                    swing_type = "LH"
                last_high_price = s["price"]
            else:
                if last_low_price is None:
                    swing_type = "HL"
                elif s["price"] > last_low_price + (min_atr_distance * atr):
                    swing_type = "HL"
                else:
                    swing_type = "LL"
                last_low_price = s["price"]

            classified_swings.append(SwingPoint(
                index=s["index"],
                timestamp=s["timestamp"],
                price=round(float(s["price"]), 2),
                type=swing_type,
                is_high=s["is_high"],
                confirmed=s["confirmed"],
                confirmation_index=s.get("confirmation_index")
            ))

        # Determine Protected Structural Swing
        protected_swing: Optional[ProtectedSwing] = None
        current_close = candles[-1].close

        # Look at the most recent confirmed swings
        confirmed_swings = [s for s in classified_swings if s.confirmed]
        if confirmed_swings:
            recent_swings = confirmed_swings[-4:]
            hl_swings = [s for s in confirmed_swings if s.type == "HL"]
            lh_swings = [s for s in confirmed_swings if s.type == "LH"]

            # If recent structure is bullish, protected swing is the latest confirmed Higher Low
            if hl_swings and (not lh_swings or hl_swings[-1].index >= lh_swings[-1].index):
                latest_hl = hl_swings[-1]
                is_broken = current_close < latest_hl.price
                protected_swing = ProtectedSwing(
                    price=latest_hl.price,
                    index=latest_hl.index,
                    timestamp=latest_hl.timestamp,
                    swing_type="HL",
                    is_broken=is_broken,
                    notes="Protected Higher Low: Sustained break below this level triggers Bearish CHoCH."
                )
            elif lh_swings:
                latest_lh = lh_swings[-1]
                is_broken = current_close > latest_lh.price
                protected_swing = ProtectedSwing(
                    price=latest_lh.price,
                    index=latest_lh.index,
                    timestamp=latest_lh.timestamp,
                    swing_type="LH",
                    is_broken=is_broken,
                    notes="Protected Lower High: Sustained break above this level triggers Bullish CHoCH."
                )

        return classified_swings, protected_swing
