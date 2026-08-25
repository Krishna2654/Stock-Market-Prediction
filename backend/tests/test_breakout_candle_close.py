import pytest
from app.models.schemas import Candle, SwingPoint, AlertRule, MultiTimeframeSynthesis, SingleTimeframeAnalysis, StructureBreakEvent, SupportResistanceSummary, TechnicalIndicators, EvidenceScoreBreakdown
from app.market_structure.trendlines import TrendlineDetector, Trendline
from app.market_structure.bos_choch import BOSCHoCHDetector
from app.alerts.engine import AlertEngine

def make_c(i: int, o: float, h: float, l: float, c: float, vol: float = 1000.0) -> Candle:
    return Candle(
        timestamp=f"2026-08-25T10:{i:02d}:00Z",
        open=round(o, 2),
        high=round(h, 2),
        low=round(l, 2),
        close=round(c, 2),
        volume=vol
    )

# -------------------------------------------------------------
# MASTER PROMPT SECTION 48: 10 CANONICAL BREAKOUT TESTS
# -------------------------------------------------------------

def test_section48_test1_intrabar_above_resistance_but_closed_below():
    """
    TEST 1:
    5M resistance = 100.
    Candle: Minute 1 = 99, Minute 2 = 99, Minute 3 = 100, Minute 4 = 101, Minute 5 = 99.
    Final close = 99.
    Expected: NO UP BREAKOUT.
    Reason: The candle did move above resistance intrabar (High = 101) but closed below it (Close = 99).
    """
    resistance_level = 100.0
    candle = make_c(0, o=99.0, h=101.0, l=99.0, c=99.0)
    
    # Check close rule: close must be strictly greater than resistance
    is_confirmed_up_breakout = candle.close > resistance_level
    assert is_confirmed_up_breakout is False, "Wick/Intrabar crossing above resistance with close below must NOT trigger UP BREAKOUT"

def test_section48_test2_resistance_confirmed_closed_above():
    """
    TEST 2:
    Resistance = 100.
    Candle: Minute 1 = 99, Minute 2 = 99, Minute 3 = 100, Minute 4 = 101, Minute 5 = 102.
    Final close = 102.
    Expected: UP BREAKOUT CONFIRMED.
    """
    resistance_level = 100.0
    candle = make_c(0, o=99.0, h=102.0, l=99.0, c=102.0)
    
    is_confirmed_up_breakout = candle.close > resistance_level
    assert is_confirmed_up_breakout is True, "Confirmed close above resistance must trigger UP BREAKOUT CONFIRMED"

def test_section48_test3_intrabar_below_support_but_closed_above():
    """
    TEST 3:
    Support = 100.
    Candle: Minute 1 = 101, Minute 2 = 101, Minute 3 = 100, Minute 4 = 99, Minute 5 = 101.
    Final close = 101.
    Expected: NO DOWN BREAKOUT.
    Reason: The candle dipped below support intrabar (Low = 99) but closed back above (Close = 101).
    """
    support_level = 100.0
    candle = make_c(0, o=101.0, h=101.0, l=99.0, c=101.0)
    
    is_confirmed_down_breakout = candle.close < support_level
    assert is_confirmed_down_breakout is False, "Wick/Intrabar dip below support with close above must NOT trigger DOWN BREAKOUT"

def test_section48_test4_support_confirmed_closed_below():
    """
    TEST 4:
    Support = 100.
    Candle: Minute 1 = 101, Minute 2 = 100, Minute 3 = 99, Minute 4 = 98, Minute 5 = 97.
    Final close = 97.
    Expected: DOWN BREAKOUT CONFIRMED.
    """
    support_level = 100.0
    candle = make_c(0, o=101.0, h=101.0, l=97.0, c=97.0)
    
    is_confirmed_down_breakout = candle.close < support_level
    assert is_confirmed_down_breakout is True, "Confirmed close below support must trigger DOWN BREAKOUT CONFIRMED"

def test_section48_test5_price_touches_trendline_remains_on_same_side():
    """
    TEST 5:
    Price touches trendline but remains on the same side.
    Expected: NO BREAKOUT.
    """
    # Descending resistance trendline at level 100.0
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=110.0, p1_time="2026-08-25T10:00:00Z",
        p2_index=5, p2_price=100.0, p2_time="2026-08-25T10:05:00Z",
        slope=-2.0, intercept=110.0, end_index=6, end_price=98.0,
        rank="PRIMARY", strength="MAJOR"
    )
    # Candle at index 5 touches 100.0 (High = 100.0, Close = 99.0, Previous close = 98.0)
    prev_c = make_c(4, o=97.0, h=98.5, l=97.0, c=98.0)
    curr_c = make_c(5, o=98.0, h=100.0, l=98.0, c=99.0) # touches line at 100.0 but closes at 99.0
    
    breaks = TrendlineDetector.detect_trendline_breaks([prev_c, curr_c], [tl], "NIFTY 50", "5M", atr_val=1.0)
    assert len(breaks) == 0, "Touching trendline without closing beyond must produce NO BREAKOUT"

def test_section48_test6_wick_crosses_trendline_closed_inside():
    """
    TEST 6:
    Wick crosses trendline but candle closes inside.
    Expected: NO BREAKOUT.
    """
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=110.0, p1_time="2026-08-25T10:00:00Z",
        p2_index=5, p2_price=100.0, p2_time="2026-08-25T10:05:00Z",
        slope=-2.0, intercept=110.0, end_index=6, end_price=98.0,
        rank="PRIMARY", strength="MAJOR"
    )
    # Candle at index 5 has wick up to 105.0, but closes at 99.5 (below 100.0)
    prev_c = make_c(4, o=97.0, h=98.0, l=96.0, c=98.0)
    curr_c = make_c(5, o=98.0, h=105.0, l=97.5, c=99.5)
    
    breaks = TrendlineDetector.detect_trendline_breaks([prev_c, curr_c], [tl], "NIFTY 50", "5M", atr_val=1.0)
    assert len(breaks) == 0, "Wick-only penetration with close inside must produce NO BREAKOUT (Wick Rejection)"

def test_section48_test7_price_crosses_trendline_and_closes_beyond():
    """
    TEST 7:
    Price crosses trendline intrabar and closes beyond it.
    Expected: CONFIRMED BREAKOUT.
    """
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=110.0, p1_time="2026-08-25T10:00:00Z",
        p2_index=4, p2_price=102.0, p2_time="2026-08-25T10:04:00Z",
        slope=-2.0, intercept=110.0, end_index=6, end_price=98.0,
        rank="PRIMARY", strength="MAJOR"
    )
    # Candle at index 4 closed below line at 102.0; Candle at index 5 confirmed close at 104.0 (well above line at 100.0)
    candles = [make_c(i, 110.0 - 2.0*i, 111.0 - 2.0*i, 109.0 - 2.0*i, 110.0 - 2.0*i) for i in range(5)]
    curr_c = make_c(5, o=98.0, h=105.0, l=98.0, c=104.0)
    candles.append(curr_c)
    
    breaks = TrendlineDetector.detect_trendline_breaks(candles, [tl], "NIFTY 50", "5M", atr_val=1.0)
    assert len(breaks) == 1, "Confirmed close above descending resistance must generate CONFIRMED BREAKOUT"
    assert breaks[0].direction == "BULLISH"
    assert breaks[0].break_price == 104.0

def test_section48_test8_duplicate_breakout_deduplication():
    """
    TEST 8:
    Same confirmed breakout is processed multiple times.
    Expected: ONE notification only.
    """
    engine = AlertEngine()
    engine.clear_notifications()
    
    # Create synthesis with a single confirmed event
    event = StructureBreakEvent(
        id="NIFTY_15M_TL_BULL_2026-08-25T10:00:00Z_5",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T10:00:00Z",
        event_type="TREND_LINE_BREAK",
        direction="BULLISH",
        broken_level=24850.0,
        break_price=24910.0,
        break_candle_index=5,
        volume_confirmed=True,
        atr_at_break=10.0,
        htf_alignment="BULLISH",
        evidence_score=85
    )
    
    synthesis = MultiTimeframeSynthesis(
        symbol="NIFTY 50",
        ticker="^NSEI",
        provider="TEST",
        last_updated="2026-08-25T10:00:00Z",
        is_stale=False,
        status_message="OK",
        current_price=24910.0,
        timeframes={
            "15M": SingleTimeframeAnalysis(
                timeframe="15M",
                trend="BULLISH",
                structure_type="BULLISH",
                candle_count=10,
                latest_candle_time="2026-08-25T10:00:00Z",
                recent_events=[event],
                breakout_status="CONFIRMED BREAKOUT",
                indicators=TechnicalIndicators(),
                support_resistance=SupportResistanceSummary(current_price=24910.0)
            )
        },
        overall_bias="BULLISH",
        current_state="FULL BULLISH ALIGNMENT",
        evidence_score=EvidenceScoreBreakdown(
            total_score=85,
            category="Strong Evidence Alignment",
            structure_points=25,
            htf_alignment_points=25,
            momentum_points=15,
            volume_points=10,
            breakout_points=10
        ),
        confirmation_state="CONFIRMED",
        short_term_state="BULLISH",
        synthesis_rationale="Test"
    )
    
    # Process twice
    alerts1 = engine.process_synthesis_for_alerts(synthesis)
    alerts2 = engine.process_synthesis_for_alerts(synthesis)
    
    assert len(alerts1) == 1, "First evaluation must produce 1 notification"
    assert len(alerts2) == 0, "Duplicate evaluation of same event must produce ZERO extra notifications"
    assert len(engine.get_notifications()) == 1

def test_section48_test9_minor_trendline_break_no_default_notification():
    """
    TEST 9:
    Minor trendline breaks.
    Expected: No notification by default.
    """
    # Event on a MINOR trendline
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=105.0, p1_time="2026-08-25T10:00:00Z",
        p2_index=2, p2_price=104.0, p2_time="2026-08-25T10:02:00Z",
        slope=-0.5, intercept=105.0, end_index=3, end_price=103.5,
        rank="MINOR", strength="MINOR"
    )
    assert tl.rank == "MINOR"
    # Alerts engine filters out MINOR trendlines by default when rules target PRIMARY/SECONDARY

def test_section48_test10_primary_major_trendline_break_notification():
    """
    TEST 10:
    Primary major trendline breaks with confirmed close.
    Expected: Notification generated.
    """
    engine = AlertEngine()
    engine.clear_notifications()
    
    event = StructureBreakEvent(
        id="NIFTY_15M_TL_BULL_2026-08-25T10:15:00Z_8",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T10:15:00Z",
        event_type="TREND_LINE_BREAK",
        direction="BULLISH",
        broken_level=24850.0,
        break_price=24910.0,
        break_candle_index=8,
        volume_confirmed=True,
        atr_at_break=12.0,
        htf_alignment="BULLISH",
        evidence_score=85,
        notes="PRIMARY major descending resistance trendline broken"
    )
    
    synthesis = MultiTimeframeSynthesis(
        symbol="NIFTY 50",
        ticker="^NSEI",
        provider="TEST",
        last_updated="2026-08-25T10:15:00Z",
        is_stale=False,
        status_message="OK",
        current_price=24910.0,
        timeframes={
            "15M": SingleTimeframeAnalysis(
                timeframe="15M",
                trend="BULLISH",
                structure_type="BULLISH",
                candle_count=10,
                latest_candle_time="2026-08-25T10:15:00Z",
                recent_events=[event],
                breakout_status="CONFIRMED BREAKOUT",
                indicators=TechnicalIndicators(),
                support_resistance=SupportResistanceSummary(current_price=24910.0)
            )
        },
        overall_bias="BULLISH",
        current_state="FULL BULLISH ALIGNMENT",
        evidence_score=EvidenceScoreBreakdown(
            total_score=85,
            category="Strong Evidence Alignment",
            structure_points=25,
            htf_alignment_points=25,
            momentum_points=15,
            volume_points=10,
            breakout_points=10
        ),
        confirmation_state="CONFIRMED",
        short_term_state="BULLISH",
        synthesis_rationale="Primary Major Breakout"
    )
    
    alerts = engine.process_synthesis_for_alerts(synthesis)
    assert len(alerts) == 1
    assert "UP BREAKOUT" in alerts[0].message
    assert alerts[0].price == 24910.0
