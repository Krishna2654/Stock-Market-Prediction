from typing import List, Dict, Optional, Literal, Tuple
import pandas as pd
from app.models.schemas import (
    Candle,
    SingleTimeframeAnalysis,
    StructureBreakEvent,
    SwingPoint,
    ProtectedSwing,
    TechnicalIndicators
)
from app.indicators.technical import TechnicalIndicatorEngine
from app.market_structure.swings import SwingDetector
from app.market_structure.bos_choch import BOSCHoCHDetector
from app.market_structure.support_resistance import SupportResistanceDetector
from app.market_structure.breakouts import BreakoutValidator
from app.market_structure.trendlines import TrendlineDetector
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.market_structure.predictive_scenarios import PredictiveScenarioEngine
from app.core.config import settings

class SingleTimeframeAnalyzer:
    """
    Analyzes an independent timeframe (4H, 1H, 15M, or 5M)
    and computes market structure, indicators, swings, breaks, trend state,
    and predictive If-Then scenario targets with buyer/seller zones.
    """

    @classmethod
    def analyze_timeframe(
        cls,
        candles: List[Candle],
        symbol: str,
        timeframe: str,
        swing_length: int = 5,
        confirmation_candles: int = 2
    ) -> SingleTimeframeAnalysis:
        if not candles:
            return SingleTimeframeAnalysis(
                timeframe=timeframe,
                trend="NEUTRAL",
                structure_type="No Data",
                indicators=TechnicalIndicators(),
                support_resistance=SupportResistanceDetector.detect_levels([], [], timeframe),
                breakout_status="NONE",
                predictive_scenarios={},
                candle_count=0,
                latest_candle_time=""
            )

        # 1. Compute Technical Indicators
        df_indicators, indicators = TechnicalIndicatorEngine.compute_all_indicators(
            candles,
            ema_fast_p=settings.EMA_FAST,
            ema_mid_p=settings.EMA_MID,
            ema_slow_p=settings.EMA_SLOW,
            rsi_p=settings.RSI_PERIOD,
            atr_p=settings.ATR_PERIOD
        )

        # 2. Detect Fractal Swings & Protected Swings
        swings, protected_swing = SwingDetector.detect_swings(
            candles,
            swing_length=swing_length,
            confirmation_candles=confirmation_candles
        )

        # 3. Detect BOS and CHoCH Events
        breaks = BOSCHoCHDetector.detect_structure_breaks(
            candles=candles,
            swings=swings,
            symbol=symbol,
            timeframe=timeframe,
            df_indicators=df_indicators,
            min_break_pct=settings.DEFAULT_MIN_BREAK_PCT,
            min_break_atr_mult=settings.DEFAULT_MIN_BREAK_ATR_MULTIPLE
        )

        # 4. Support and Resistance Levels
        sr_summary = SupportResistanceDetector.detect_levels(candles, swings, timeframe)

        # 5. Breakout Validation
        breakout_status = BreakoutValidator.validate_breakout(candles, sr_summary, indicators)

        # 6. Trendline Detection & Trendline Breaks
        trendlines = TrendlineDetector.fit_trendlines(candles, swings, max_lines_per_direction=settings.MAX_TRENDLINES_PER_DIRECTION)
        atr_val = indicators.atr_14 or (candles[-1].close * 0.005)
        trendline_breaks = TrendlineDetector.detect_trendline_breaks(
            candles, trendlines, symbol, timeframe, atr_val=atr_val
        )
        
        for tb in trendline_breaks:
            breaks.append(tb)

        # 6b. Precision High-Confluence Breakouts (Notification 1 & Notification 2)
        tl_ema_vol_breaks = PrecisionBreakoutDetector.detect_trendline_ema_volume_breakouts(
            candles=candles,
            trendlines=trendlines,
            df_indicators=df_indicators,
            symbol=symbol,
            timeframe=timeframe,
            atr_val=atr_val,
            good_volume_threshold=settings.GOOD_VOLUME_THRESHOLD
        )
        for pb in tl_ema_vol_breaks:
            breaks.append(pb)

        key_sups = [lvl.price for lvl in sr_summary.all_levels if lvl.level_type == "SUPPORT"]
        key_res = [lvl.price for lvl in sr_summary.all_levels if lvl.level_type == "RESISTANCE"]
        if sr_summary.minor_support and sr_summary.minor_support not in key_sups:
            key_sups.append(sr_summary.minor_support)
        if sr_summary.major_support and sr_summary.major_support not in key_sups:
            key_sups.append(sr_summary.major_support)
        if sr_summary.minor_resistance and sr_summary.minor_resistance not in key_res:
            key_res.append(sr_summary.minor_resistance)
        if sr_summary.major_resistance and sr_summary.major_resistance not in key_res:
            key_res.append(sr_summary.major_resistance)

        wm_breaks, confirmed_wm_patterns, active_wm_pattern, _ = PrecisionBreakoutDetector.detect_wm_patterns(
            candles=candles,
            swings=swings,
            trendlines=trendlines,
            df_indicators=df_indicators,
            symbol=symbol,
            timeframe=timeframe,
            atr_val=atr_val,
            price_tolerance_atr=settings.W_M_SWING_TOLERANCE_ATR,
            min_depth_atr=settings.MIN_PATTERN_DEPTH_ATR,
            min_bar_spacing=settings.MIN_W_M_SWING_SEPARATION,
            min_breakout_dist_atr=settings.MIN_BREAKOUT_DISTANCE_ATR,
            key_supports=key_sups,
            key_resistances=key_res
        )
        for wb in wm_breaks:
            breaks.append(wb)

        # If confirmed breakout / breakdown, register explicit SUPPORT_BREAK / RESISTANCE_BREAK with deterministic IDs
        last_candle = candles[-1]
        curr_sym = "$" if "BTC" in symbol or "USD" in symbol else "₹"
        if breakout_status == "CONFIRMED BREAKOUT" and sr_summary.minor_resistance:
            event_id = f"{symbol}_{timeframe}_RES_BREAK_{last_candle.timestamp}_{round(sr_summary.minor_resistance, 1)}"
            breaks.append(StructureBreakEvent(
                id=event_id,
                symbol=symbol,
                timeframe=timeframe,
                timestamp=last_candle.timestamp,
                event_type="RESISTANCE_BREAK",
                direction="BULLISH",
                broken_level=round(sr_summary.minor_resistance, 2),
                break_price=round(last_candle.close, 2),
                break_candle_index=len(candles) - 1,
                volume_confirmed=True,
                atr_at_break=round(atr_val, 2),
                htf_alignment="BULLISH",
                evidence_score=80,
                breakout_candle_open=round(last_candle.open, 2),
                breakout_candle_high=round(last_candle.high, 2),
                breakout_candle_low=round(last_candle.low, 2),
                breakout_candle_close=round(last_candle.close, 2),
                notes=f"Confirmed candle-close resistance breakout above {curr_sym}{sr_summary.minor_resistance:,.2f}"
            ))
        elif breakout_status == "CONFIRMED BREAKDOWN" and sr_summary.minor_support:
            event_id = f"{symbol}_{timeframe}_SUP_BREAK_{last_candle.timestamp}_{round(sr_summary.minor_support, 1)}"
            breaks.append(StructureBreakEvent(
                id=event_id,
                symbol=symbol,
                timeframe=timeframe,
                timestamp=last_candle.timestamp,
                event_type="SUPPORT_BREAK",
                direction="BEARISH",
                broken_level=round(sr_summary.minor_support, 2),
                break_price=round(last_candle.close, 2),
                break_candle_index=len(candles) - 1,
                volume_confirmed=True,
                atr_at_break=round(atr_val, 2),
                htf_alignment="BEARISH",
                evidence_score=80,
                breakout_candle_open=round(last_candle.open, 2),
                breakout_candle_high=round(last_candle.high, 2),
                breakout_candle_low=round(last_candle.low, 2),
                breakout_candle_close=round(last_candle.close, 2),
                notes=f"Confirmed candle-close support breakdown below {curr_sym}{sr_summary.minor_support:,.2f}"
            ))

        # 7. Predictive Scenarios
        predictive_scenarios = PredictiveScenarioEngine.compute_scenarios(
            candles=candles,
            swings=swings,
            sr_summary=sr_summary,
            recent_events=breaks,
            timeframe=timeframe,
            symbol=symbol
        )

        # 8. Trend Classification
        trend, structure_desc, important_level = cls.classify_trend(candles, swings, indicators, breaks)

        latest_event = breaks[-1] if breaks else None

        return SingleTimeframeAnalysis(
            timeframe=timeframe,
            trend=trend,
            structure_type=structure_desc,
            latest_event=latest_event,
            important_level=important_level,
            protected_swing=protected_swing,
            swings=swings[-12:],
            recent_events=breaks[-10:],
            trendlines=[t.to_dict() for t in trendlines],
            indicators=indicators,
            support_resistance=sr_summary,
            breakout_status=breakout_status,
            predictive_scenarios=predictive_scenarios,
            wm_patterns=confirmed_wm_patterns,
            active_wm_pattern=active_wm_pattern,
            candle_count=len(candles),
            latest_candle_time=candles[-1].timestamp
        )

    @classmethod
    def classify_trend(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        indicators: TechnicalIndicators,
        breaks: List[StructureBreakEvent]
    ) -> Tuple[
        Literal["STRONG BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "STRONG BEARISH"],
        str,
        Optional[float]
    ]:
        if not candles:
            return "NEUTRAL", "Consolidation", None

        current_price = candles[-1].close
        bullish_points = 0
        bearish_points = 0

        recent_swings = swings[-4:] if len(swings) >= 4 else swings
        hh_count = sum(1 for s in recent_swings if s.type == "HH")
        hl_count = sum(1 for s in recent_swings if s.type == "HL")
        lh_count = sum(1 for s in recent_swings if s.type == "LH")
        ll_count = sum(1 for s in recent_swings if s.type == "LL")

        if (hh_count + hl_count) > (lh_count + ll_count):
            bullish_points += 3
            structure_desc = "HH/HL Structure"
        elif (lh_count + ll_count) > (hh_count + hl_count):
            bearish_points += 3
            structure_desc = "LH/LL Structure"
        else:
            structure_desc = "Consolidation / Mixed"

        # EMA Alignment
        ema20 = indicators.ema_20
        ema50 = indicators.ema_50
        ema200 = indicators.ema_200

        if ema20 and ema50:
            if current_price > ema20 > ema50:
                bullish_points += 3
                if ema200 and ema50 > ema200:
                    bullish_points += 2
            elif current_price < ema20 < ema50:
                bearish_points += 3
                if ema200 and ema50 < ema200:
                    bearish_points += 2
            elif current_price > ema20:
                bullish_points += 1
            elif current_price < ema20:
                bearish_points += 1

        # RSI
        rsi = indicators.rsi_14
        if rsi is not None:
            if rsi >= 60:
                bullish_points += 2
            elif rsi <= 40:
                bearish_points += 2

        # Breaks
        if breaks:
            latest_break = breaks[-1]
            if latest_break.direction == "BULLISH":
                bullish_points += 3
            else:
                bearish_points += 3

        net_score = bullish_points - bearish_points
        if net_score >= 6:
            trend = "STRONG BULLISH"
        elif net_score >= 2:
            trend = "BULLISH"
        elif net_score <= -6:
            trend = "STRONG BEARISH"
        elif net_score <= -2:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"

        important_level = recent_swings[-1].price if recent_swings else ema50

        return trend, structure_desc, important_level
