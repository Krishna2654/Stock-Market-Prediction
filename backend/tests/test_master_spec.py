import pytest
import numpy as np
from datetime import datetime, timezone
from app.models.schemas import Candle, SwingPoint
from app.market_structure.trendlines import TrendlineDetector, Trendline
from app.market_structure.swings import SwingDetector
from app.market_structure.bos_choch import BOSCHoCHDetector
from app.data.candle_builder import CandleValidator, SessionAwareCandleBuilder
from app.multi_timeframe.evidence_score import EvidenceScoreEngine

def make_candle(index: int, open_p: float, high_p: float, low_p: float, close_p: float, vol: float = 1000.0) -> Candle:
    return Candle(
        timestamp=f"2026-08-24T10:{index:02d}:00Z",
        open=round(open_p, 2),
        high=round(high_p, 2),
        low=round(low_p, 2),
        close=round(close_p, 2),
        volume=vol
    )

# -------------------------------------------------------------
# MASTER PROMPT SECTION 63: 11 TRENDLINE TEST CASES
# -------------------------------------------------------------

def test_case_1_clear_uptrend():
    """CASE 1 — CLEAR UPTREND: Ascending support line connects swing lows."""
    prices = [100, 105, 103, 110, 107, 115, 112, 120, 118, 125, 122, 130, 128, 135]
    candles = [make_candle(i, p-0.5, p+1.0, p-1.0, p) for i, p in enumerate(prices)]
    swings, _ = SwingDetector.detect_swings(candles, swing_length=1, confirmation_candles=1)
    
    trendlines = TrendlineDetector.fit_trendlines(candles, swings, max_lines_per_direction=5)
    support_lines = [t for t in trendlines if t.line_type == "ASCENDING_SUPPORT"]
    
    assert len(support_lines) >= 1
    assert support_lines[0].slope > 0
    assert support_lines[0].rank in ["PRIMARY", "SECONDARY"]

def test_case_2_clear_downtrend():
    """CASE 2 — CLEAR DOWNTREND: Descending resistance line connects swing highs."""
    prices = [150, 145, 147, 140, 143, 135, 138, 130, 133, 125, 128, 120, 122, 115]
    candles = [make_candle(i, p+0.5, p+1.0, p-1.0, p) for i, p in enumerate(prices)]
    swings, _ = SwingDetector.detect_swings(candles, swing_length=1, confirmation_candles=1)
    
    trendlines = TrendlineDetector.fit_trendlines(candles, swings, max_lines_per_direction=5)
    res_lines = [t for t in trendlines if t.line_type == "DESCENDING_RESISTANCE"]
    
    assert len(res_lines) >= 1
    assert res_lines[0].slope < 0
    assert res_lines[0].rank in ["PRIMARY", "SECONDARY"]

def test_case_3_multiple_uptrend_lines():
    """CASE 3 — MULTIPLE UPTREND LINES: Returns distinct primary & secondary support lines."""
    prices = [
        100, 105, 102, 110, 106, 118, 112, 125, 120, 130, 126, 138, 132, 145, 140, 150,
        146, 158, 152, 165, 160, 172, 168, 180
    ]
    candles = [make_candle(i, p-0.5, p+1.0, p-1.0, p) for i, p in enumerate(prices)]
    swings, _ = SwingDetector.detect_swings(candles, swing_length=1, confirmation_candles=1)
    
    trendlines = TrendlineDetector.fit_trendlines(candles, swings, max_lines_per_direction=5)
    support_lines = [t for t in trendlines if t.line_type == "ASCENDING_SUPPORT"]
    
    assert len(support_lines) >= 1
    assert any(t.rank == "PRIMARY" for t in support_lines)

def test_case_4_multiple_downtrend_lines():
    """CASE 4 — MULTIPLE DOWNTREND LINES: Returns distinct resistance lines."""
    prices = [
        200, 190, 195, 182, 188, 175, 180, 168, 172, 160, 165, 150, 155, 142, 147, 135,
        140, 128, 132, 120
    ]
    candles = [make_candle(i, p+0.5, p+1.0, p-1.0, p) for i, p in enumerate(prices)]
    swings, _ = SwingDetector.detect_swings(candles, swing_length=1, confirmation_candles=1)
    
    trendlines = TrendlineDetector.fit_trendlines(candles, swings, max_lines_per_direction=5)
    res_lines = [t for t in trendlines if t.line_type == "DESCENDING_RESISTANCE"]
    
    assert len(res_lines) >= 1

def test_case_5_noisy_market():
    """CASE 5 — NOISY MARKET: In choppy consolidation, no major long-spanning trendline dominates."""
    np.random.seed(42)
    noise = np.random.normal(100, 0.5, 30)
    candles = [make_candle(i, p, p+0.5, p-0.5, p) for i, p in enumerate(noise)]
    swings, _ = SwingDetector.detect_swings(candles, swing_length=3, confirmation_candles=1)
    
    trendlines = TrendlineDetector.fit_trendlines(candles, swings, max_lines_per_direction=5)
    major_lines = [t for t in trendlines if t.strength == "MAJOR"]
    assert len(major_lines) == 0

def test_case_6_trendline_break():
    """CASE 6 — TRENDLINE BREAK: Confirmed break event generated."""
    prices = [100, 108, 104, 115, 110, 122, 116, 130, 124, 135, 128, 140, 110, 105]
    candles = [make_candle(i, p-0.5, p+1.0, p-1.0, p) for i, p in enumerate(prices)]
    swings, _ = SwingDetector.detect_swings(candles, swing_length=1, confirmation_candles=1)
    
    trendlines = TrendlineDetector.fit_trendlines(candles, swings)
    breaks = TrendlineDetector.detect_trendline_breaks(candles, trendlines, "TEST", "15M", atr_val=1.0)
    
    assert len(breaks) >= 1
    assert any(b.event_type == "TREND_LINE_BREAK" and b.direction == "BEARISH" for b in breaks)

def test_case_7_wick_break():
    """CASE 7 — WICK BREAK: Wick penetrates line but candle close stays inside line -> no confirmed break."""
    candles = [
        make_candle(0, 100, 102, 99, 101),
        make_candle(1, 101, 106, 100, 105),
        make_candle(2, 105, 107, 103, 104),
        make_candle(3, 104, 110, 103, 109),
        make_candle(4, 109, 113, 107, 108),
    ]
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=0, p1_price=100.0, p1_time=candles[0].timestamp,
        p2_index=2, p2_price=104.0, p2_time=candles[2].timestamp,
        end_index=4, end_price=108.0,
        slope=2.0, intercept=100.0,
        touch_count=2, status="ACTIVE", is_active=True, is_broken=False
    )
    breaks = TrendlineDetector.detect_trendline_breaks(candles, [tl], "TEST", "15M", atr_val=1.0)
    assert len(breaks) == 0

def test_case_8_body_close_through_line():
    """CASE 8 — BODY CLOSE THROUGH LINE: Confirmed break when close penetrates line by ATR tolerance."""
    candles = [
        make_candle(0, 100, 102, 99, 100),
        make_candle(1, 100, 106, 100, 105),
        make_candle(2, 105, 107, 104, 104),
        make_candle(3, 104, 106, 102, 101), # close at 101, line at 106
    ]
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=0, p1_price=100.0, p1_time=candles[0].timestamp,
        p2_index=2, p2_price=104.0, p2_time=candles[2].timestamp,
        end_index=3, end_price=106.0,
        slope=2.0, intercept=100.0,
        touch_count=2, status="ACTIVE", is_active=True, is_broken=False
    )
    breaks = TrendlineDetector.detect_trendline_breaks(candles, [tl], "TEST", "15M", atr_val=1.0)
    assert len(breaks) >= 1
    assert breaks[0].event_type == "TREND_LINE_BREAK"

def test_case_9_duplicate_lines_clustered():
    """CASE 9 — DUPLICATE LINES: Nearly identical candidate lines are clustered."""
    prices = [100, 105, 103, 103.2, 110, 107, 107.1, 115, 120]
    candles = [make_candle(i, p-0.5, p+1.0, p-1.0, p) for i, p in enumerate(prices)]
    swings, _ = SwingDetector.detect_swings(candles, swing_length=1, confirmation_candles=1)
    
    trendlines = TrendlineDetector.fit_trendlines(candles, swings, max_lines_per_direction=5)
    support_lines = [t for t in trendlines if t.line_type == "ASCENDING_SUPPORT"]
    
    for i in range(len(support_lines)):
        for j in range(i + 1, len(support_lines)):
            diff_p = abs(support_lines[i].end_price - support_lines[j].end_price)
            assert diff_p > 0.01

def test_case_10_active_line_extension():
    """CASE 10 — ACTIVE LINE: Line extends to the latest candle index."""
    prices = [100, 105, 103, 110, 107, 115, 112, 120, 118, 125]
    candles = [make_candle(i, p-0.5, p+1.0, p-1.0, p) for i, p in enumerate(prices)]
    swings, _ = SwingDetector.detect_swings(candles, swing_length=1, confirmation_candles=1)
    
    trendlines = TrendlineDetector.fit_trendlines(candles, swings)
    active_lines = [t for t in trendlines if t.is_active]
    
    for line in active_lines:
        assert line.end_index == len(candles) - 1
        assert line.status == "ACTIVE"

def test_case_11_broken_line_stops():
    """CASE 11 — BROKEN LINE: Broken line stops at break candle index."""
    prices = [100, 105, 103, 110, 107, 115, 112, 120, 95, 90, 88]
    candles = [make_candle(i, p-0.5, p+1.0, p-1.0, p) for i, p in enumerate(prices)]
    swings, _ = SwingDetector.detect_swings(candles, swing_length=1, confirmation_candles=1)
    
    trendlines = TrendlineDetector.fit_trendlines(candles, swings)
    broken_lines = [t for t in trendlines if t.is_broken]
    
    for line in broken_lines:
        assert line.end_index < len(candles) - 1
        assert line.status == "BROKEN"

# -------------------------------------------------------------
# CANDLE VALIDATOR & SESSION BUILDER TESTS
# -------------------------------------------------------------

def test_candle_validation():
    valid_c = make_candle(1, 100, 105, 98, 102, 500)
    assert CandleValidator.validate_candle(valid_c) is True
    
    invalid_c1 = make_candle(2, -100, 105, 98, 102, 500)
    assert CandleValidator.validate_candle(invalid_c1) is False
    
    invalid_c2 = make_candle(3, 100, 95, 98, 102, 500)
    assert CandleValidator.validate_candle(invalid_c2) is False
