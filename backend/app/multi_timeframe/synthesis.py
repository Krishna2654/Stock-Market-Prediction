from typing import Dict, List, Optional
from datetime import datetime, timezone
from app.models.schemas import (
    Candle,
    MultiTimeframeSynthesis,
    SingleTimeframeAnalysis,
    StructureBreakEvent,
    WhatJustChanged,
    MarketSessionStatus
)
from app.multi_timeframe.analyzer import SingleTimeframeAnalyzer
from app.multi_timeframe.evidence_score import EvidenceScoreEngine

class MultiTimeframeAnalyzer:
    """
    Synthesizes independent analyses of 4H, 1H, 15M, and 5M timeframes.
    Enforces hierarchical dominance: 4H > 1H > 15M > 5M.
    Tracks state transitions and generates 'What Just Changed?' deltas.
    """

    @classmethod
    def synthesize(
        cls,
        symbol: str,
        ticker: str,
        provider_name: str,
        mtf_candles: Dict[str, List[Candle]],
        is_stale: bool = False,
        status_message: str = "Active Feed",
        data_status: str = "LIVE"
    ) -> MultiTimeframeSynthesis:
        # 1. Analyze each timeframe independently
        analyses: Dict[str, SingleTimeframeAnalysis] = {}
        for tf in ["4H", "1H", "15M", "5M"]:
            candles = mtf_candles.get(tf, [])
            analyses[tf] = SingleTimeframeAnalyzer.analyze_timeframe(candles, symbol, tf)

        # Get current price from lowest timeframe or any available
        current_price = 0.0
        for tf in ["5M", "15M", "1H", "4H"]:
            candles = mtf_candles.get(tf, [])
            if candles:
                current_price = candles[-1].close
                break

        # 2. Hierarchical Bias Determination
        tf_4h = analyses.get("4H")
        tf_1h = analyses.get("1H")
        tf_15m = analyses.get("15M")
        tf_5m = analyses.get("5M")

        h4_trend = tf_4h.trend if tf_4h else "NEUTRAL"
        h1_trend = tf_1h.trend if tf_1h else "NEUTRAL"
        m15_trend = tf_15m.trend if tf_15m else "NEUTRAL"
        m5_trend = tf_5m.trend if tf_5m else "NEUTRAL"

        # Calculate weighted bias points (4H: 40%, 1H: 30%, 15M: 20%, 5M: 10%)
        weights = {"4H": 4.0, "1H": 3.0, "15M": 2.0, "5M": 1.0}
        trend_score_map = {
            "STRONG BULLISH": 2.0,
            "BULLISH": 1.0,
            "NEUTRAL": 0.0,
            "BEARISH": -1.0,
            "STRONG BEARISH": -2.0
        }

        weighted_score = (
            weights["4H"] * trend_score_map.get(h4_trend, 0) +
            weights["1H"] * trend_score_map.get(h1_trend, 0) +
            weights["15M"] * trend_score_map.get(m15_trend, 0) +
            weights["5M"] * trend_score_map.get(m5_trend, 0)
        ) / 10.0

        if weighted_score >= 0.75:
            overall_bias = "BULLISH"
        elif weighted_score <= -0.75:
            overall_bias = "BEARISH"
        elif ("BULLISH" in h4_trend and "BEARISH" in h1_trend) or ("BEARISH" in h4_trend and "BULLISH" in h1_trend):
            overall_bias = "MIXED"
        else:
            overall_bias = "NEUTRAL" if abs(weighted_score) < 0.3 else ("BULLISH" if weighted_score > 0 else "BEARISH")

        # 3. Determine Current Market State
        current_state = "NO CLEAR STRUCTURE"
        confirmation_state = "Waiting for structural confirmation"
        short_term_state = "Consolidation"
        
        # Check alignment states
        if "BULLISH" in h4_trend and "BULLISH" in h1_trend and "BULLISH" in m15_trend and "BULLISH" in m5_trend:
            current_state = "FULL BULLISH ALIGNMENT"
            short_term_state = "All 4 timeframes aligned bullish"
            confirmation_state = "4H + 1H + 15M + 5M in unison"
        elif "BEARISH" in h4_trend and "BEARISH" in h1_trend and "BEARISH" in m15_trend and "BEARISH" in m5_trend:
            current_state = "FULL BEARISH ALIGNMENT"
            short_term_state = "All 4 timeframes aligned bearish"
            confirmation_state = "4H + 1H + 15M + 5M in unison"
        elif overall_bias == "BULLISH":
            if "BEARISH" in m5_trend or "BEARISH" in m15_trend:
                current_state = "BULLISH WITH SHORT-TERM PULLBACK"
                short_term_state = "5M/15M Pullback within 4H/1H Bullish Trend"
                confirmation_state = "Watch for 5M/15M Bullish CHoCH to signal continuation"
            else:
                current_state = "FULL BULLISH ALIGNMENT"
                short_term_state = "Short-term timeframes aligned with HTF trend"
                confirmation_state = "4H + 1H + 15M aligned"
        elif overall_bias == "BEARISH":
            if "BULLISH" in m5_trend or "BULLISH" in m15_trend:
                current_state = "BEARISH WITH SHORT-TERM BOUNCE"
                short_term_state = "5M/15M Rally / Retracement within 4H/1H Bearish Trend"
                confirmation_state = "Watch for 5M/15M Bearish CHoCH to signal continuation"
            else:
                current_state = "FULL BEARISH ALIGNMENT"
                short_term_state = "Short-term timeframes aligned with HTF bear trend"
                confirmation_state = "4H + 1H + 15M aligned"
        elif overall_bias == "MIXED":
            current_state = "MIXED"
            short_term_state = "HTF and LTF in structural divergence"
            confirmation_state = "Awaiting 1H alignment with 4H"
        else:
            current_state = "CONSOLIDATION"
            short_term_state = "Range-bound sideways market"
            confirmation_state = "Waiting for decisive BOS on 1H/15M"

        # 4. Latest important structure event
        all_breaks: List[StructureBreakEvent] = []
        for tf_key in ["15M", "1H", "4H", "5M"]:
            tf_obj = analyses.get(tf_key)
            if tf_obj and tf_obj.recent_events:
                all_breaks.extend(tf_obj.recent_events)
        
        all_breaks.sort(key=lambda x: x.timestamp, reverse=True)
        latest_important_event = all_breaks[0] if all_breaks else None

        # 5. Invalidation Level & Key S/R
        invalidation_level = None
        key_supports: List[float] = []
        key_resistances: List[float] = []

        for tf_key in ["4H", "1H", "15M"]:
            tf_obj = analyses.get(tf_key)
            if tf_obj:
                sr = tf_obj.support_resistance
                if sr.major_support and sr.major_support not in key_supports:
                    key_supports.append(sr.major_support)
                if sr.minor_support and sr.minor_support not in key_supports:
                    key_supports.append(sr.minor_support)
                if sr.major_resistance and sr.major_resistance not in key_resistances:
                    key_resistances.append(sr.major_resistance)
                if sr.minor_resistance and sr.minor_resistance not in key_resistances:
                    key_resistances.append(sr.minor_resistance)

        key_supports = sorted(key_supports, reverse=True)[:4]
        key_resistances = sorted(key_resistances)[:4]

        if overall_bias == "BULLISH":
            invalidation_level = key_supports[0] if key_supports else (current_price * 0.985)
        elif overall_bias == "BEARISH":
            invalidation_level = key_resistances[0] if key_resistances else (current_price * 1.015)

        # 6. Evidence Score Calculation
        evidence_score = EvidenceScoreEngine.calculate_score(analyses, overall_bias)

        # 7. What Just Changed Delta
        what_just_changed: Optional[WhatJustChanged] = None
        if latest_important_event:
            what_just_changed = WhatJustChanged(
                symbol=symbol,
                timeframe=latest_important_event.timeframe,
                previous_state="Consolidation" if "CHOCH" in latest_important_event.event_type else "Trend Active",
                new_state=f"{latest_important_event.direction} ({latest_important_event.event_type.replace('_', ' ')})",
                event_type=latest_important_event.event_type,
                broken_level=latest_important_event.broken_level,
                break_price=latest_important_event.break_price,
                volume_confirmed=latest_important_event.volume_confirmed,
                structural_interpretation=(
                    f"Confirmed {latest_important_event.timeframe} {latest_important_event.event_type.replace('_', ' ')} "
                    f"at {latest_important_event.broken_level:.2f}. "
                    f"Higher timeframe bias remains {overall_bias}."
                ),
                timestamp=latest_important_event.timestamp
            )

        # 8. Synthesis Rationale
        rationale = (
            f"4H is {h4_trend} ({analyses['4H'].structure_type if tf_4h else 'N/A'}), "
            f"1H is {h1_trend}, 15M is {m15_trend}, and 5M is {m5_trend}. "
            f"Overall bias is {overall_bias} with {evidence_score.total_score}/100 evidence alignment. "
            f"Current state is {current_state}."
        )

        from app.data.candle_builder import SessionAwareCandleBuilder
        session_info = SessionAwareCandleBuilder.get_market_session_status(ticker)
        market_session_obj = MarketSessionStatus(**session_info)

        return MultiTimeframeSynthesis(
            symbol=symbol,
            ticker=ticker,
            provider=provider_name,
            data_status=data_status if not is_stale else "LAST VALID ANALYSIS",
            market_session=market_session_obj,
            last_updated=datetime.now(timezone.utc).isoformat(),
            is_stale=is_stale,
            status_message=status_message,
            current_price=round(current_price, 2),
            timeframes=analyses,
            mtf_candles=mtf_candles,
            overall_bias=overall_bias,
            current_state=current_state,
            evidence_score=evidence_score,
            latest_important_event=latest_important_event,
            what_just_changed=what_just_changed,
            confirmation_state=confirmation_state,
            short_term_state=short_term_state,
            invalidation_level=round(invalidation_level, 2) if invalidation_level else None,
            key_supports=[round(p, 2) for p in key_supports],
            key_resistances=[round(p, 2) for p in key_resistances],
            predictive_scenarios=analyses["15M"].predictive_scenarios if "15M" in analyses else (analyses["1H"].predictive_scenarios if "1H" in analyses else {}),
            synthesis_rationale=rationale
        )
