from typing import List, Dict, Optional, Tuple, Any, Literal
import numpy as np
from app.models.schemas import (
    Candle,
    SwingPoint,
    SupportResistanceSummary,
    StructureBreakEvent
)

class PredictiveScenarioEngine:
    """
    Quantitative Predictive Scenario & Supply/Demand Order Block Engine.
    1. Identifies Recent Major Impulse Ray (Low-to-High for Uptrend, High-to-Low for Downtrend).
    2. Identifies Buyer Zones (Demand Order Blocks) and Seller Zones (Supply Order Blocks).
    3. Formulates precise 'If Break X -> Next Target Y' roadmaps using S/R liquidity levels.
    """

    @classmethod
    def compute_scenarios(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        sr_summary: SupportResistanceSummary,
        recent_events: List[StructureBreakEvent],
        timeframe: str,
        symbol: str
    ) -> Dict[str, Any]:
        if not candles:
            return {}

        current_price = candles[-1].close
        n = len(candles)
        atr_window = candles[-min(20, n):]
        atr = max(0.5, float(np.mean([c.high - c.low for c in atr_window])))
        curr_sym = "$" if "BTC" in symbol or "USD" in symbol else "₹"

        # -------------------------------------------------------------
        # 1. Recent Impulse Swing Ray (High-to-Low / Low-to-High)
        # -------------------------------------------------------------
        high_swings = [s for s in swings if s.is_high]
        low_swings = [s for s in swings if not s.is_high]

        last_high = high_swings[-1] if high_swings else None
        last_low = low_swings[-1] if low_swings else None

        impulse_data = {}
        if last_high and last_low:
            if last_high.index > last_low.index:
                # Uptrend Impulse: Low to High
                impulse_data = {
                    "direction": "UP",
                    "type": "RECENT_LOW_TO_HIGH",
                    "from_index": last_low.index,
                    "from_price": round(last_low.price, 2),
                    "from_time": last_low.timestamp,
                    "to_index": last_high.index,
                    "to_price": round(last_high.price, 2),
                    "to_time": last_high.timestamp,
                    "retrace_50": round((last_low.price + last_high.price) / 2.0, 2),
                    "retrace_618": round(last_high.price - 0.618 * (last_high.price - last_low.price), 2)
                }
            else:
                # Downtrend Impulse: High to Low
                impulse_data = {
                    "direction": "DOWN",
                    "type": "RECENT_HIGH_TO_LOW",
                    "from_index": last_high.index,
                    "from_price": round(last_high.price, 2),
                    "from_time": last_high.timestamp,
                    "to_index": last_low.index,
                    "to_price": round(last_low.price, 2),
                    "to_time": last_low.timestamp,
                    "retrace_50": round((last_high.price + last_low.price) / 2.0, 2),
                    "retrace_618": round(last_low.price + 0.618 * (last_high.price - last_low.price), 2)
                }

        # -------------------------------------------------------------
        # 2. Buyer (Demand) & Seller (Supply) Zones
        # -------------------------------------------------------------
        buyer_zone = None
        seller_zone = None

        # Buyer Zone: Base before strong bullish expansion
        if last_low:
            zone_bottom = last_low.price
            zone_top = last_low.price + (0.5 * atr)
            buyer_zone = {
                "zone_type": "BUYER_DEMAND",
                "top_price": round(zone_top, 2),
                "bottom_price": round(zone_bottom, 2),
                "mid_price": round((zone_top + zone_bottom) / 2.0, 2),
                "start_time": last_low.timestamp,
                "label": f"Buyer Demand Zone ({curr_sym}{zone_bottom:,.1f} - {curr_sym}{zone_top:,.1f})"
            }

        # Seller Zone: Base before strong bearish impulse
        if last_high:
            zone_top = last_high.price
            zone_bottom = last_high.price - (0.5 * atr)
            seller_zone = {
                "zone_type": "SELLER_SUPPLY",
                "top_price": round(zone_top, 2),
                "bottom_price": round(zone_bottom, 2),
                "mid_price": round((zone_top + zone_bottom) / 2.0, 2),
                "start_time": last_high.timestamp,
                "label": f"Seller Supply Zone ({curr_sym}{zone_bottom:,.1f} - {curr_sym}{zone_top:,.1f})"
            }

        # -------------------------------------------------------------
        # 3. 'If-Then' Target Projections via S/R and CHoCH
        # -------------------------------------------------------------
        # Bullish Path: If price breaks Resistance / Swing High / CHoCH -> Next Target
        res_trigger = sr_summary.minor_resistance or (current_price * 1.008)
        if last_high and last_high.price > current_price:
            res_trigger = last_high.price

        bullish_target_1 = sr_summary.major_resistance or (res_trigger + 1.5 * atr)
        if bullish_target_1 <= res_trigger:
            bullish_target_1 = round(res_trigger + 1.8 * atr, 2)
        bullish_target_2 = round(bullish_target_1 + 2.0 * atr, 2)

        bullish_sl = sr_summary.minor_support or (current_price - 1.2 * atr)
        bull_risk = max(0.01, res_trigger - bullish_sl)
        bull_reward = max(0.01, bullish_target_1 - res_trigger)
        bull_rr = round(bull_reward / bull_risk, 2)

        bullish_path = {
            "scenario": "BULLISH_BREAKOUT",
            "trigger_level": round(res_trigger, 2),
            "trigger_condition": f"Confirmed candle close above {curr_sym}{res_trigger:,.2f} (Resistance / CHoCH Pivot)",
            "target_1": round(bullish_target_1, 2),
            "target_1_distance_pct": round(((bullish_target_1 - current_price) / current_price) * 100.0, 2),
            "target_2": round(bullish_target_2, 2),
            "target_2_distance_pct": round(((bullish_target_2 - current_price) / current_price) * 100.0, 2),
            "invalidation_sl": round(bullish_sl, 2),
            "risk_reward_ratio": bull_rr,
            "prediction_statement": f"IF price confirms close above {curr_sym}{res_trigger:,.2f} ➔ NEXT TARGET 1 is {curr_sym}{bullish_target_1:,.2f}, TARGET 2 is {curr_sym}{bullish_target_2:,.2f} (Invalidation: {curr_sym}{bullish_sl:,.2f})"
        }

        # Bearish Path: If price breaks Support / Swing Low / CHoCH -> Next Downside Target
        sup_trigger = sr_summary.minor_support or (current_price * 0.992)
        if last_low and last_low.price < current_price:
            sup_trigger = last_low.price

        bearish_target_1 = sr_summary.major_support or (sup_trigger - 1.5 * atr)
        if bearish_target_1 >= sup_trigger:
            bearish_target_1 = round(sup_trigger - 1.8 * atr, 2)
        bearish_target_2 = round(bearish_target_1 - 2.0 * atr, 2)

        bearish_sl = sr_summary.minor_resistance or (current_price + 1.2 * atr)
        bear_risk = max(0.01, bearish_sl - sup_trigger)
        bear_reward = max(0.01, sup_trigger - bearish_target_1)
        bear_rr = round(bear_reward / bear_risk, 2)

        bearish_path = {
            "scenario": "BEARISH_BREAKDOWN",
            "trigger_level": round(sup_trigger, 2),
            "trigger_condition": f"Confirmed candle close below {curr_sym}{sup_trigger:,.2f} (Support / CHoCH Pivot)",
            "target_1": round(bearish_target_1, 2),
            "target_1_distance_pct": round(((bearish_target_1 - current_price) / current_price) * 100.0, 2),
            "target_2": round(bearish_target_2, 2),
            "target_2_distance_pct": round(((bearish_target_2 - current_price) / current_price) * 100.0, 2),
            "invalidation_sl": round(bearish_sl, 2),
            "risk_reward_ratio": bear_rr,
            "prediction_statement": f"IF price confirms breakdown below {curr_sym}{sup_trigger:,.2f} ➔ NEXT DOWNSIDE TARGET 1 is {curr_sym}{bearish_target_1:,.2f}, TARGET 2 is {curr_sym}{bearish_target_2:,.2f} (Invalidation: {curr_sym}{bearish_sl:,.2f})"
        }

        return {
            "current_price": round(current_price, 2),
            "recent_impulse": impulse_data,
            "buyer_zone": buyer_zone,
            "seller_zone": seller_zone,
            "bullish_path": bullish_path,
            "bearish_path": bearish_path
        }
