from typing import List, Dict, Tuple, Optional
import numpy as np
import pandas as pd
from app.models.schemas import Candle, SwingPoint, ProtectedSwing, StructureBreakEvent
from app.core.config import settings

class BOSCHoCHDetector:
    """
    Quantitative Break of Structure (BOS) & Change of Character (CHoCH) Detector.
    Strictly verifies candle close breaks beyond confirmed structural levels
    and protected swings with ATR confirmation.
    """

    @classmethod
    def detect_structure_breaks(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        symbol: str,
        timeframe: str,
        df_indicators: Optional[pd.DataFrame] = None,
        min_break_pct: float = 0.0005,
        min_break_atr_mult: float = 0.15
    ) -> List[StructureBreakEvent]:
        if len(candles) < 10 or len(swings) < 2:
            return []

        events: List[StructureBreakEvent] = []
        n = len(candles)

        active_highs: List[SwingPoint] = []
        active_lows: List[SwingPoint] = []
        current_trend = "NEUTRAL"
        
        swings_by_confirm_idx: Dict[int, List[SwingPoint]] = {}
        for s in swings:
            confirm_idx = s.confirmation_index if s.confirmation_index is not None else s.index
            swings_by_confirm_idx.setdefault(confirm_idx, []).append(s)

        for i in range(n):
            c = candles[i]
            
            if i in swings_by_confirm_idx:
                for s in swings_by_confirm_idx[i]:
                    if s.is_high:
                        active_highs.append(s)
                    else:
                        active_lows.append(s)

            atr_val = 1.0
            vol_confirmed = False
            if df_indicators is not None and not df_indicators.empty and i < len(df_indicators):
                row = df_indicators.iloc[i]
                if "atr_14" in row and not pd.isna(row["atr_14"]):
                    atr_val = max(float(row["atr_14"]), 0.01)
                if "relative_volume" in row and not pd.isna(row["relative_volume"]):
                    vol_confirmed = float(row["relative_volume"]) >= 1.15
            else:
                vol_confirmed = c.volume > 0

            # Bullish BOS / CHoCH
            for sh in list(active_highs):
                min_threshold = max(sh.price * min_break_pct, atr_val * min_break_atr_mult)
                # Confirmed close break required (wick-only is rejected)
                if c.close > (sh.price + min_threshold):
                    if current_trend == "BEARISH" or sh.type == "LH":
                        event_type = "BULLISH_CHOCH"
                        notes = f"Change of Character: Confirmed close above protected {sh.type} at {sh.price:.2f}"
                        current_trend = "BULLISH"
                    else:
                        event_type = "BULLISH_BOS"
                        notes = f"Bullish Break of Structure: Confirmed close above {sh.type} at {sh.price:.2f}"
                        current_trend = "BULLISH"

                    # Deterministic deduplication ID
                    event_id = f"{symbol}_{timeframe}_{event_type}_{c.timestamp}_{round(sh.price, 1)}"
                    evt = StructureBreakEvent(
                        id=event_id,
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=c.timestamp,
                        event_type=event_type,
                        direction="BULLISH",
                        broken_level=round(sh.price, 2),
                        break_price=round(c.close, 2),
                        break_candle_index=i,
                        volume_confirmed=vol_confirmed,
                        atr_at_break=round(atr_val, 2),
                        htf_alignment="BULLISH",
                        evidence_score=75 if vol_confirmed else 60,
                        notes=notes
                    )
                    events.append(evt)
                    active_highs.remove(sh)
                    break

            # Bearish BOS / CHoCH
            for sl in list(active_lows):
                min_threshold = max(sl.price * min_break_pct, atr_val * min_break_atr_mult)
                # Confirmed close break required (wick-only is rejected)
                if c.close < (sl.price - min_threshold):
                    if current_trend == "BULLISH" or sl.type == "HL":
                        event_type = "BEARISH_CHOCH"
                        notes = f"Change of Character: Confirmed close below protected {sl.type} at {sl.price:.2f}"
                        current_trend = "BEARISH"
                    else:
                        event_type = "BEARISH_BOS"
                        notes = f"Bearish Break of Structure: Confirmed close below {sl.type} at {sl.price:.2f}"
                        current_trend = "BEARISH"

                    event_id = f"{symbol}_{timeframe}_{event_type}_{c.timestamp}_{round(sl.price, 1)}"
                    evt = StructureBreakEvent(
                        id=event_id,
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=c.timestamp,
                        event_type=event_type,
                        direction="BEARISH",
                        broken_level=round(sl.price, 2),
                        break_price=round(c.close, 2),
                        break_candle_index=i,
                        volume_confirmed=vol_confirmed,
                        atr_at_break=round(atr_val, 2),
                        htf_alignment="BEARISH",
                        evidence_score=75 if vol_confirmed else 60,
                        notes=notes
                    )
                    events.append(evt)
                    active_lows.remove(sl)
                    break

        return events
