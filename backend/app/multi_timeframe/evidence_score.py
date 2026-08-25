from typing import Dict, List, Literal
from app.models.schemas import (
    SingleTimeframeAnalysis,
    EvidenceScoreBreakdown
)

class EvidenceScoreEngine:
    """
    Deterministic Evidence Alignment Score Engine (0 to 100).
    Calculates quantitative confluence across Structure, HTF Alignment,
    Momentum, Volume, and Breakout Confirmation.
    """

    @classmethod
    def calculate_score(
        cls,
        tf_analyses: Dict[str, SingleTimeframeAnalysis],
        overall_bias: Literal["BULLISH", "BEARISH", "NEUTRAL", "MIXED"]
    ) -> EvidenceScoreBreakdown:
        details: List[str] = []
        
        structure_pts = 0
        htf_pts = 0
        momentum_pts = 0
        volume_pts = 0
        breakout_pts = 0

        tf_4h = tf_analyses.get("4H")
        tf_1h = tf_analyses.get("1H")
        tf_15m = tf_analyses.get("15M")
        tf_5m = tf_analyses.get("5M")

        is_bullish_bias = (overall_bias == "BULLISH")
        is_bearish_bias = (overall_bias == "BEARISH")

        # 1. Structure Points (Max 25)
        # Check swing structure alignment across 4H, 1H, 15M
        bullish_structs = sum(1 for tf in [tf_4h, tf_1h, tf_15m, tf_5m] if tf and "HH" in tf.structure_type)
        bearish_structs = sum(1 for tf in [tf_4h, tf_1h, tf_15m, tf_5m] if tf and "LL" in tf.structure_type)

        if is_bullish_bias and bullish_structs >= 3:
            structure_pts = 25
            details.append("Structure (+25): Strong multi-timeframe HH/HL structure")
        elif is_bearish_bias and bearish_structs >= 3:
            structure_pts = 25
            details.append("Structure (+25): Strong multi-timeframe LH/LL structure")
        elif (is_bullish_bias and bullish_structs >= 2) or (is_bearish_bias and bearish_structs >= 2):
            structure_pts = 18
            details.append(f"Structure (+18): Moderate structure agreement ({max(bullish_structs, bearish_structs)} timeframes)")
        else:
            structure_pts = 8
            details.append("Structure (+8): Fragmented or consolidating swing structure")

        # 2. HTF Alignment Points (Max 25)
        # Priority: 4H + 1H alignment
        if tf_4h and tf_1h:
            h4_bull = "BULLISH" in tf_4h.trend
            h4_bear = "BEARISH" in tf_4h.trend
            h1_bull = "BULLISH" in tf_1h.trend
            h1_bear = "BEARISH" in tf_1h.trend

            if (is_bullish_bias and h4_bull and h1_bull) or (is_bearish_bias and h4_bear and h1_bear):
                htf_pts = 25
                details.append("HTF Alignment (+25): 4H macro and 1H intermediate trends are fully aligned")
            elif (is_bullish_bias and h4_bull) or (is_bearish_bias and h4_bear):
                htf_pts = 16
                details.append("HTF Alignment (+16): 4H macro trend aligned, 1H in retrace/neutral")
            elif (is_bullish_bias and h1_bull) or (is_bearish_bias and h1_bear):
                htf_pts = 12
                details.append("HTF Alignment (+12): 1H aligned but 4H macro is neutral")
            else:
                htf_pts = 4
                details.append("HTF Alignment (+4): HTF timeframes in conflict")
        else:
            htf_pts = 10

        # 3. Momentum Points (Max 20)
        # RSI and EMA stacking across 1H and 15M
        rsi_pts = 0
        ema_pts = 0
        
        for tf in [tf_1h, tf_15m]:
            if tf and tf.indicators.rsi_14 is not None:
                rsi = tf.indicators.rsi_14
                if is_bullish_bias and 50 <= rsi <= 72:
                    rsi_pts += 5
                elif is_bearish_bias and 28 <= rsi <= 50:
                    rsi_pts += 5
                elif 45 <= rsi <= 55:
                    rsi_pts += 2
                    
            if tf and tf.indicators.ema_20 and tf.indicators.ema_50:
                if is_bullish_bias and tf.indicators.ema_20 > tf.indicators.ema_50:
                    ema_pts += 5
                elif is_bearish_bias and tf.indicators.ema_20 < tf.indicators.ema_50:
                    ema_pts += 5

        momentum_pts = min(20, rsi_pts + ema_pts)
        details.append(f"Momentum (+{momentum_pts}): RSI and EMA momentum alignment across 1H/15M")

        # 4. Volume Points (Max 15)
        vol_score = 0
        for tf in [tf_1h, tf_15m, tf_5m]:
            if tf and tf.indicators.relative_volume and tf.indicators.relative_volume >= 1.15:
                vol_score += 5
        volume_pts = min(15, vol_score if vol_score > 0 else 5)
        details.append(f"Volume (+{volume_pts}): Volume expansion & relative participation")

        # 5. Breakout / Break Confirmation Points (Max 15)
        breakout_score = 0
        for tf in [tf_1h, tf_15m]:
            if tf:
                if tf.breakout_status in ["CONFIRMED BREAKOUT", "CONFIRMED BREAKDOWN"]:
                    breakout_score += 8
                elif tf.latest_event and tf.latest_event.volume_confirmed:
                    breakout_score += 7
                elif tf.breakout_status == "POSSIBLE BREAK":
                    breakout_score += 4
        breakout_pts = min(15, breakout_score if breakout_score > 0 else 5)
        details.append(f"Breakout Confirmation (+{breakout_pts}): Validated structural break confirmation")

        total = structure_pts + htf_pts + momentum_pts + volume_pts + breakout_pts
        total = max(0, min(100, total))

        if total >= 80:
            category = "Strong Evidence Alignment"
        elif total >= 65:
            category = "Moderate-to-Strong Alignment"
        elif total >= 50:
            category = "Mixed Evidence"
        elif total >= 35:
            category = "Weak Alignment"
        else:
            category = "Conflicting / Weak Evidence"

        return EvidenceScoreBreakdown(
            total_score=total,
            category=category,
            structure_points=structure_pts,
            htf_alignment_points=htf_pts,
            momentum_points=momentum_pts,
            volume_points=volume_pts,
            breakout_points=breakout_pts,
            details=details
        )
