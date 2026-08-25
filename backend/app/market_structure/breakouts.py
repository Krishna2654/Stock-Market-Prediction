from typing import List, Literal, Optional
from app.models.schemas import Candle, SupportResistanceSummary, TechnicalIndicators

class BreakoutValidator:
    """
    Validates level crossings into:
    - CONFIRMED BREAKOUT / BREAKDOWN
    - FAILED BREAKOUT / BREAKDOWN (Fakeouts)
    - POSSIBLE BREAK
    - NONE
    """

    @classmethod
    def validate_breakout(
        cls,
        candles: List[Candle],
        sr_summary: SupportResistanceSummary,
        indicators: TechnicalIndicators
    ) -> Literal["NONE", "POSSIBLE BREAK", "CONFIRMED BREAKOUT", "CONFIRMED BREAKDOWN", "FAILED BREAKOUT", "FAILED BREAKDOWN"]:
        if len(candles) < 3:
            return "NONE"

        current_candle = candles[-1]
        prev_candle = candles[-2]
        
        c_close = current_candle.close
        c_high = current_candle.high
        c_low = current_candle.low
        
        atr = indicators.atr_14 or (c_close * 0.005)
        rel_vol = indicators.relative_volume or 1.0

        # Check Resistance interactions
        res_level = sr_summary.minor_resistance or sr_summary.major_resistance
        if res_level is not None:
            # Did price cross resistance?
            if c_close > res_level:
                if rel_vol >= 1.15 and (c_close - res_level) >= (0.1 * atr):
                    return "CONFIRMED BREAKOUT"
                else:
                    return "POSSIBLE BREAK"
            elif c_high > res_level and c_close <= res_level:
                # Pierced high but closed below -> Fakeout / Failed Breakout
                if (c_high - res_level) > (0.15 * atr):
                    return "FAILED BREAKOUT"

        # Check Support interactions
        sup_level = sr_summary.minor_support or sr_summary.major_support
        if sup_level is not None:
            if c_close < sup_level:
                if rel_vol >= 1.15 and (sup_level - c_close) >= (0.1 * atr):
                    return "CONFIRMED BREAKDOWN"
                else:
                    return "POSSIBLE BREAK"
            elif c_low < sup_level and c_close >= sup_level:
                # Pierced low but closed above -> Fakeout / Failed Breakdown
                if (sup_level - c_low) > (0.15 * atr):
                    return "FAILED BREAKDOWN"

        return "NONE"
