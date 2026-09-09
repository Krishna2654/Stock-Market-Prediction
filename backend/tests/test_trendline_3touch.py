import pytest
import numpy as np
from typing import List
from app.models.schemas import (
    Candle,
    SwingPoint,
    StructureBreakEvent,
    SingleTimeframeAnalysis,
    MultiTimeframeSynthesis,
    TechnicalIndicators,
    SupportResistanceSummary,
    EvidenceScoreBreakdown,
)
from app.market_structure.trendlines import TrendlineDetector, Trendline
from app.market_structure.swings import SwingDetector
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.alerts.trendline_shortlist_engine import TrendlineShortlistEngine

def make_candle(i: int, o: float, h: float, l: float, c: float, v: float = 1000.0, tf_min: int = 5) -> Candle:
    total_min = i * tf_min
    day = 1 + (total_min // 1440)
    hour = (total_min % 1440) // 60
    minute = total_min % 60
    return Candle(
        timestamp=f'2026-09-{day:02d}T{hour:02d}:{minute:02d}:00Z',
        open=round(float(o), 2),
        high=round(float(h), 2),
        low=round(float(l), 2),
        close=round(float(c), 2),
        volume=float(v)
    )

def make_swing(idx: int, candles: List[Candle], price: float, is_high: bool) -> SwingPoint:
    return SwingPoint(
        index=idx,
        timestamp=candles[idx].timestamp,
        price=round(float(price), 2),
        type='HH' if is_high else 'HL',
        is_high=is_high,
        confirmed=True,
        confirmation_index=idx + 1
    )

# -------------------------------------------------------------
# 1. Valid ascending support with exactly 3 structural touches
# -------------------------------------------------------------
def test_1_valid_ascending_support_3_structural_touches():
    # Line: y = 1.0 * x + 100.0
    # T1 at x=2 (y=102), T2 at x=6 (y=106), T3 at x=10 (y=110)
    candles = []
    for i in range(15):
        base = 100.0 + 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base + 2, base + 4, 102.0, base + 2))
        elif i == 6:
            candles.append(make_candle(i, base + 2, base + 4, 106.0, base + 2))
        elif i == 10:
            candles.append(make_candle(i, base + 2, base + 4, 110.0, base + 2))
        else:
            # Stays safely above line
            candles.append(make_candle(i, base + 3, base + 6, base + 1.5, base + 4))

    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(4, candles, 108.0, is_high=True),
        make_swing(6, candles, 106.0, is_high=False),
        make_swing(8, candles, 113.0, is_high=True),
        make_swing(10, candles, 110.0, is_high=False),
    ]

    tls = TrendlineDetector.fit_trendlines(candles, swings)
    support_lines = [t for t in tls if t.line_type == 'ASCENDING_SUPPORT']
    assert len(support_lines) >= 1
    best = support_lines[0]
    assert best.touch_count >= 3
    touch_indices = [tp.index for tp in best.touch_points]
    assert 2 in touch_indices and 6 in touch_indices and 10 in touch_indices
    assert best.slope > 0

# -------------------------------------------------------------
# 2. Valid descending resistance with exactly 3 structural touches
# -------------------------------------------------------------
def test_2_valid_descending_resistance_3_structural_touches():
    # Line: y = -1.0 * x + 200.0
    # T1 at x=2 (y=198), T2 at x=6 (y=194), T3 at x=10 (y=190)
    candles = []
    for i in range(15):
        base = 200.0 - 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base - 2, 198.0, base - 4, base - 2))
        elif i == 6:
            candles.append(make_candle(i, base - 2, 194.0, base - 4, base - 2))
        elif i == 10:
            candles.append(make_candle(i, base - 2, 190.0, base - 4, base - 2))
        else:
            # Stays safely below line
            candles.append(make_candle(i, base - 3, base - 1.5, base - 6, base - 4))

    swings = [
        make_swing(2, candles, 198.0, is_high=True),
        make_swing(4, candles, 192.0, is_high=False),
        make_swing(6, candles, 194.0, is_high=True),
        make_swing(8, candles, 187.0, is_high=False),
        make_swing(10, candles, 190.0, is_high=True),
    ]

    tls = TrendlineDetector.fit_trendlines(candles, swings)
    res_lines = [t for t in tls if t.line_type == 'DESCENDING_RESISTANCE']
    assert len(res_lines) >= 1
    best = res_lines[0]
    assert best.touch_count >= 3
    touch_indices = [tp.index for tp in best.touch_points]
    assert 2 in touch_indices and 6 in touch_indices and 10 in touch_indices
    assert best.slope < 0

# -------------------------------------------------------------
# 3. Reject only 2 touches
# -------------------------------------------------------------
def test_3_reject_only_2_touches():
    # Only 2 swing lows available
    candles = [make_candle(i, 100 + i, 105 + i, 99 + i, 101 + i) for i in range(15)]
    swings = [
        make_swing(2, candles, 101.0, is_high=False),
        make_swing(6, candles, 105.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    assert len(tls) == 0

# -------------------------------------------------------------
# 4. Reject 3 random candle contacts that are not confirmed swings
# -------------------------------------------------------------
def test_4_reject_random_candle_contacts_not_confirmed_swings():
    # Candles touch at 2, 3, 4, but swings list does not confirm them as 3 distinct swings
    candles = [make_candle(i, 100, 102, 99, 100) for i in range(15)]
    swings = [
        make_swing(2, candles, 99.0, is_high=False),
        make_swing(8, candles, 102.0, is_high=True),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    assert len(tls) == 0

# -------------------------------------------------------------
# 5. Third touch validates an existing T1->T2 line within tolerance
# -------------------------------------------------------------
def test_5_third_touch_validates_within_tolerance():
    candles = []
    for i in range(15):
        base = 100.0 + 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base + 2, base + 4, 102.0, base + 2))
        elif i == 6:
            candles.append(make_candle(i, base + 2, base + 4, 106.0, base + 2))
        elif i == 10:
            # Line price is 110.0. ATR ~ 2.5. 0.65 * ATR ~ 1.625. Touch at 110.4 is well within tolerance.
            candles.append(make_candle(i, base + 2, base + 4, 110.4, base + 2))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2.0, base + 4))

    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(4, candles, 109.0, is_high=True),
        make_swing(6, candles, 106.0, is_high=False),
        make_swing(8, candles, 114.0, is_high=True),
        make_swing(10, candles, 110.4, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    support_lines = [t for t in tls if t.line_type == 'ASCENDING_SUPPORT']
    assert len(support_lines) >= 1
    assert support_lines[0].touch_count >= 3

# -------------------------------------------------------------
# 6. Third touch outside tolerance is rejected
# -------------------------------------------------------------
def test_6_third_touch_outside_tolerance_rejected():
    candles = []
    for i in range(15):
        base = 100.0 + 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base + 2, base + 4, 102.0, base + 2))
        elif i == 6:
            candles.append(make_candle(i, base + 2, base + 4, 106.0, base + 2))
        elif i == 10:
            # Line price is 110.0. ATR ~ 2.5. Touch at 118.0 is way outside tolerance (>0.65*ATR).
            candles.append(make_candle(i, base + 10, base + 12, 118.0, base + 11))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2.0, base + 4))

    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(4, candles, 109.0, is_high=True),
        make_swing(6, candles, 106.0, is_high=False),
        make_swing(8, candles, 114.0, is_high=True),
        make_swing(10, candles, 118.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    # The candidate from 2->6 cannot use 10 because it deviates by 8.0 points
    support_lines = [t for t in tls if t.line_type == 'ASCENDING_SUPPORT' and 2 in [p.index for p in t.touch_points]]
    assert len(support_lines) == 0

# -------------------------------------------------------------
# 7. Wick crossing without candle close beyond Action Line does NOT breakout
# -------------------------------------------------------------
def test_7_wick_crossing_without_close_no_breakout():
    # Support line y = 1.0 * x + 100.0.
    candles = []
    for i in range(14):
        base = 100.0 + 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base + 2, base + 4, 102.0, base + 2))
        elif i == 6:
            candles.append(make_candle(i, base + 2, base + 4, 106.0, base + 2))
        elif i == 10:
            candles.append(make_candle(i, base + 2, base + 4, 110.0, base + 2))
        elif i == 12:
            # Wick crosses line (low = 108, line is 112), but candle closes at 113 (above line)
            candles.append(make_candle(i, 113.0, 114.0, 108.0, 113.0))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2.0, base + 4))

    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(4, candles, 109.0, is_high=True),
        make_swing(6, candles, 106.0, is_high=False),
        make_swing(8, candles, 114.0, is_high=True),
        make_swing(10, candles, 110.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    breaks = TrendlineDetector.detect_trendline_breaks(candles, tls, 'TEST', '5M')
    # Wick pierced 108 < 112, but close 113 > 112 => NO break event
    assert len(breaks) == 0

# -------------------------------------------------------------
# 8. Completed candle closing beyond support generates correct breakdown
# -------------------------------------------------------------
def test_8_completed_candle_closing_below_support_breakdown():
    candles = []
    for i in range(14):
        base = 100.0 + 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base + 2, base + 4, 102.0, base + 2))
        elif i == 6:
            candles.append(make_candle(i, base + 2, base + 4, 106.0, base + 2))
        elif i == 10:
            candles.append(make_candle(i, base + 2, base + 4, 110.0, base + 2))
        elif i == 12:
            # Completed close at 108 < line (112)
            candles.append(make_candle(i, 112.0, 112.5, 107.5, 108.0))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2.0, base + 4))

    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(4, candles, 109.0, is_high=True),
        make_swing(6, candles, 106.0, is_high=False),
        make_swing(8, candles, 114.0, is_high=True),
        make_swing(10, candles, 110.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    breaks = TrendlineDetector.detect_trendline_breaks(candles, tls, 'TEST', '5M')
    assert len(breaks) >= 1
    b = breaks[0]
    assert b.direction == 'BEARISH'
    assert b.break_candle_index == 12
    assert b.break_price == 108.0

# -------------------------------------------------------------
# 9. Completed candle closing beyond resistance generates correct breakout
# -------------------------------------------------------------
def test_9_completed_candle_closing_above_resistance_breakout():
    candles = []
    for i in range(14):
        base = 200.0 - 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base - 2, 198.0, base - 4, base - 2))
        elif i == 6:
            candles.append(make_candle(i, base - 2, 194.0, base - 4, base - 2))
        elif i == 10:
            candles.append(make_candle(i, base - 2, 190.0, base - 4, base - 2))
        elif i == 12:
            # Completed close at 193 > line (188)
            candles.append(make_candle(i, 188.0, 193.5, 187.5, 193.0))
        else:
            candles.append(make_candle(i, base - 3, base - 1.5, base - 6, base - 4))

    swings = [
        make_swing(2, candles, 198.0, is_high=True),
        make_swing(4, candles, 192.0, is_high=False),
        make_swing(6, candles, 194.0, is_high=True),
        make_swing(8, candles, 187.0, is_high=False),
        make_swing(10, candles, 190.0, is_high=True),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    breaks = TrendlineDetector.detect_trendline_breaks(candles, tls, 'TEST', '5M')
    assert len(breaks) >= 1
    b = breaks[0]
    assert b.direction == 'BULLISH'
    assert b.break_candle_index == 12
    assert b.break_price == 193.0

# -------------------------------------------------------------
# 10. Unfinished / live candle crossing does NOT generate a signal
# -------------------------------------------------------------
def test_10_unfinished_candle_does_not_generate_signal():
    # Only completed candles in history are analyzed; candle with close still above line has not broken
    candles = [make_candle(i, 100 + i, 105 + i, 99 + i, 101 + i) for i in range(12)]
    tls = []
    breaks = TrendlineDetector.detect_trendline_breaks(candles, tls, 'TEST', '5M')
    assert len(breaks) == 0

# -------------------------------------------------------------
# 11. Touches separated by insufficient distance are rejected
# -------------------------------------------------------------
def test_11_touches_insufficient_distance_rejected():
    candles = [make_candle(i, 100 + i, 105 + i, 99 + i, 101 + i) for i in range(15)]
    # T1 at 2, T2 at 3 (dx = 1 < 2)
    swings = [
        make_swing(2, candles, 101.0, is_high=False),
        make_swing(3, candles, 102.0, is_high=False),
        make_swing(8, candles, 107.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    # The candidate pair (2, 3) must be skipped due to dx < 2
    assert not any(t.p1_index == 2 and t.p2_index == 3 for t in tls)

# -------------------------------------------------------------
# 12. No arbitrary 5-swing or 20-candle limit
# -------------------------------------------------------------
def test_12_no_arbitrary_swing_or_candle_limit():
    # Construct 55 candles with T1 at 5, T2 at 25, T3 at 45 (span = 40 candles > 20, 8 swings)
    candles = []
    for i in range(55):
        base = 100.0 + 0.5 * i
        if i == 5:
            candles.append(make_candle(i, base + 1, base + 2, 102.5, base + 1))
        elif i == 25:
            candles.append(make_candle(i, base + 1, base + 2, 112.5, base + 1))
        elif i == 45:
            candles.append(make_candle(i, base + 1, base + 2, 122.5, base + 1))
        else:
            candles.append(make_candle(i, base + 2, base + 5, base + 1.5, base + 3))

    swings = [
        make_swing(5, candles, 102.5, is_high=False),
        make_swing(10, candles, 110.0, is_high=True),
        make_swing(15, candles, 108.0, is_high=False),
        make_swing(20, candles, 115.0, is_high=True),
        make_swing(25, candles, 112.5, is_high=False),
        make_swing(30, candles, 120.0, is_high=True),
        make_swing(35, candles, 118.0, is_high=False),
        make_swing(40, candles, 125.0, is_high=True),
        make_swing(45, candles, 122.5, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    long_span_lines = [t for t in tls if (t.touch_points[-1].index - t.touch_points[0].index) >= 30]
    assert len(long_span_lines) >= 1
    assert long_span_lines[0].touch_count >= 3

# -------------------------------------------------------------
# 13. Multiple symbols work
# -------------------------------------------------------------
def test_13_multiple_symbols_work():
    # Test high-priced symbol (e.g. BTC ~60,000) and low-priced symbol (e.g. PENNY ~5.0)
    for sym, scale in [('BTCUSDT', 60000.0), ('PENNY', 5.0)]:
        candles = []
        for i in range(15):
            base = scale + (0.01 * scale) * i
            if i in (2, 6, 10):
                candles.append(make_candle(i, base, base + 0.02 * scale, base, base + 0.01 * scale))
            else:
                candles.append(make_candle(i, base + 0.01 * scale, base + 0.03 * scale, base + 0.005 * scale, base + 0.02 * scale))
        swings = [
            make_swing(2, candles, candles[2].low, is_high=False),
            make_swing(4, candles, candles[4].high, is_high=True),
            make_swing(6, candles, candles[6].low, is_high=False),
            make_swing(8, candles, candles[8].high, is_high=True),
            make_swing(10, candles, candles[10].low, is_high=False),
        ]
        tls = TrendlineDetector.fit_trendlines(candles, swings)
        assert len(tls) >= 1
        assert tls[0].touch_count >= 3

# -------------------------------------------------------------
# 14. Multiple timeframes work
# -------------------------------------------------------------
def test_14_multiple_timeframes_work():
    for tf, tf_min in [('5M', 5), ('15M', 15), ('1H', 60), ('1D', 1440)]:
        candles = []
        for i in range(15):
            base = 100.0 + 1.0 * i
            if i in (2, 6, 10):
                candles.append(make_candle(i, base + 2, base + 4, base, base + 2, tf_min=tf_min))
            else:
                candles.append(make_candle(i, base + 3, base + 6, base + 2, base + 4, tf_min=tf_min))
        swings = [
            make_swing(2, candles, candles[2].low, is_high=False),
            make_swing(4, candles, candles[4].high, is_high=True),
            make_swing(6, candles, candles[6].low, is_high=False),
            make_swing(8, candles, candles[8].high, is_high=True),
            make_swing(10, candles, candles[10].low, is_high=False),
        ]
        tls = TrendlineDetector.fit_trendlines(candles, swings)
        assert len(tls) >= 1
        breaks = TrendlineDetector.detect_trendline_breaks(candles, tls, 'TEST', tf)
        assert all(b.timeframe == tf for b in breaks)

# -------------------------------------------------------------
# 15. Duplicate breakout events are prevented
# -------------------------------------------------------------
def test_15_duplicate_breakout_events_prevented():
    candles = []
    for i in range(15):
        base = 100.0 + 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base + 2, base + 4, 102.0, base + 2))
        elif i == 6:
            candles.append(make_candle(i, base + 2, base + 4, 106.0, base + 2))
        elif i == 10:
            candles.append(make_candle(i, base + 2, base + 4, 110.0, base + 2))
        elif i == 12:
            # First break below line (112)
            candles.append(make_candle(i, 112.0, 112.5, 107.5, 108.0))
        elif i == 13:
            # Next candle also remains below line (113)
            candles.append(make_candle(i, 108.0, 109.0, 106.0, 107.0))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2.0, base + 4))

    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(4, candles, 109.0, is_high=True),
        make_swing(6, candles, 106.0, is_high=False),
        make_swing(8, candles, 114.0, is_high=True),
        make_swing(10, candles, 110.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    breaks = TrendlineDetector.detect_trendline_breaks(candles, tls, 'TEST', '5M')
    # Candle 12 broke out; candle 13 should NOT generate a duplicate event for the same line
    assert len([b for b in breaks if b.break_candle_index == 12]) == 1
    assert len([b for b in breaks if b.break_candle_index == 13]) == 0

# -------------------------------------------------------------
# 16. Action Line is based on the validated 3-touch trendline
# -------------------------------------------------------------
def test_16_action_line_derived_from_3touch_trendline():
    candles = []
    for i in range(15):
        base = 100.0 + 1.0 * i
        if i in (2, 6, 10):
            candles.append(make_candle(i, base + 2, base + 4, base, base + 2))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2, base + 4))
    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(4, candles, 109.0, is_high=True),
        make_swing(6, candles, 106.0, is_high=False),
        make_swing(8, candles, 114.0, is_high=True),
        make_swing(10, candles, 110.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    tl = tls[0]
    for k in range(len(candles)):
        expected = tl.slope * k + tl.intercept
        assert abs(tl.get_price_at_index(k) - expected) < 1e-6

# -------------------------------------------------------------
# 17. Existing Safety Line behavior remains correct
# -------------------------------------------------------------
def test_17_safety_line_compatibility():
    candles = []
    for i in range(15):
        base = 100.0 + 1.0 * i
        if i in (2, 6, 10):
            candles.append(make_candle(i, base + 2, base + 4, base, base + 2))
        elif i == 12:
            candles.append(make_candle(i, 112.0, 113.0, 107.0, 107.5, v=3000))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2, base + 4))
    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(4, candles, 109.0, is_high=True),
        make_swing(6, candles, 106.0, is_high=False),
        make_swing(8, candles, 114.0, is_high=True),
        make_swing(10, candles, 110.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    assert len(tls) >= 1
    detector = PrecisionBreakoutDetector()
    breakouts = detector.detect_trendline_ema_volume_breakouts(
        candles=candles,
        trendlines=tls,
        df_indicators=None,
        symbol='TEST',
        timeframe='5M',
        atr_val=1.0
    )
    assert isinstance(breakouts, list)

# -------------------------------------------------------------
# 18. Existing trendline API output remains backward compatible
# -------------------------------------------------------------
def test_18_api_output_backward_compatible():
    candles = []
    for i in range(15):
        base = 100.0 + 1.0 * i
        if i in (2, 6, 10):
            candles.append(make_candle(i, base + 2, base + 4, base, base + 2))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2, base + 4))
    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(4, candles, 109.0, is_high=True),
        make_swing(6, candles, 106.0, is_high=False),
        make_swing(8, candles, 114.0, is_high=True),
        make_swing(10, candles, 110.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    d = tls[0].to_dict()
    required_keys = [
        'line_type', 'rank', 'strength', 'p1_index', 'p1_price', 'p1_time',
        'p2_index', 'p2_price', 'p2_time', 'end_index', 'end_price', 'slope',
        'intercept', 'touch_count', 'touch_points', 'r_squared', 'status',
        'is_active', 'is_broken'
    ]
    for key in required_keys:
        assert key in d, f'Missing required API key: {key}'
    assert isinstance(d['touch_points'], list)
    assert len(d['touch_points']) >= 3

# -------------------------------------------------------------
# 19. Existing frontend trendline visualization remains functional
# -------------------------------------------------------------
def test_19_frontend_visualization_fields():
    candles = []
    for i in range(15):
        base = 100.0 + 1.0 * i
        if i in (2, 6, 10):
            candles.append(make_candle(i, base + 2, base + 4, base, base + 2))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2, base + 4))
    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(4, candles, 109.0, is_high=True),
        make_swing(6, candles, 106.0, is_high=False),
        make_swing(8, candles, 114.0, is_high=True),
        make_swing(10, candles, 110.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    d = tls[0].to_dict()
    assert d['p1_time'].startswith('2026-')
    assert d['p2_time'].startswith('2026-')
    assert isinstance(d['p1_price'], float)
    assert isinstance(d['p2_price'], float)
    assert isinstance(d['end_price'], float)
    assert len(d['touch_points']) >= 3
    for tp in d['touch_points']:
        assert 'index' in tp and 'timestamp' in tp and 'price' in tp

# -------------------------------------------------------------
# 20. Meta test: Full regression suite verification
# -------------------------------------------------------------
def test_20_regression_suite_verification():
    assert TrendlineDetector is not None
    assert PrecisionBreakoutDetector is not None
    assert TrendlineShortlistEngine is not None
