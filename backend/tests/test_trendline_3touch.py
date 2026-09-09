import pytest
from datetime import datetime, timezone, timedelta
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
    AlertNotification,
)
from app.market_structure.trendlines import TrendlineDetector, Trendline
from app.market_structure.swings import SwingDetector
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.alerts.trendline_shortlist_engine import TrendlineShortlistEngine
from app.alerts.engine import AlertEngine
from app.core.timezone import is_candle_closed, KOLKATA_TZ, UTC_TZ

def make_candle(i: int, o: float, h: float, l: float, c: float, v: float = 1000.0, tf_min: int = 5) -> Candle:
    total_min = i * tf_min
    day = 1 + (total_min // 1440)
    hour = (total_min % 1440) // 60
    minute = total_min % 60
    return Candle(
        timestamp=f"2026-09-{day:02d}T{hour:02d}:{minute:02d}:00Z",
        open=round(float(o), 2),
        high=round(float(h), 2),
        low=round(float(l), 2),
        close=round(float(c), 2),
        volume=float(v)
    )

def make_swing(idx: int, candles: List[Candle], price: float, is_high: bool, confirmed: bool = True) -> SwingPoint:
    return SwingPoint(
        index=idx,
        timestamp=candles[idx].timestamp,
        price=round(float(price), 2),
        type="HH" if is_high else "HL",
        is_high=is_high,
        confirmed=confirmed,
        confirmation_index=idx + 1 if confirmed else None
    )

# -------------------------------------------------------------
# 1. 2-touch trendline can be established (Ascending & Descending)
# -------------------------------------------------------------
def test_1_2touch_trendline_can_be_established():
    candles = [make_candle(i, 100.0 + i, 105.0 + i, 99.0 + i, 101.0 + i) for i in range(12)]
    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(6, candles, 106.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    support_lines = [t for t in tls if t.line_type == "ASCENDING_SUPPORT"]
    assert len(support_lines) >= 1
    best_up = support_lines[0]
    assert best_up.touch_count == 2
    assert len(best_up.touch_points) == 2
    assert best_up.slope > 0

    candles_down = [make_candle(i, 200.0 - i, 205.0 - i, 195.0 - i, 199.0 - i) for i in range(12)]
    swings_down = [
        make_swing(2, candles_down, 198.0, is_high=True),
        make_swing(6, candles_down, 194.0, is_high=True),
    ]
    tls_down = TrendlineDetector.fit_trendlines(candles_down, swings_down)
    resistance_lines = [t for t in tls_down if t.line_type == "DESCENDING_RESISTANCE"]
    assert len(resistance_lines) >= 1
    best_down = resistance_lines[0]
    assert best_down.touch_count == 2
    assert len(best_down.touch_points) == 2
    assert best_down.slope < 0

# -------------------------------------------------------------
# 2. 2-touch breakout can generate a valid signal
# -------------------------------------------------------------
def test_2_2touch_breakout_generates_valid_signal():
    candles = []
    for i in range(10):
        base = 100.0 + 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base + 2, base + 4, 102.0, base + 2))
        elif i == 6:
            candles.append(make_candle(i, base + 2, base + 4, 106.0, base + 2))
        elif i == 8:
            candles.append(make_candle(i, 108.0, 108.5, 103.5, 104.0))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2.0, base + 4))

    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(6, candles, 106.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    assert len(tls) >= 1
    assert tls[0].touch_count == 2

    breaks = TrendlineDetector.detect_trendline_breaks(candles, tls, "TEST", "5M", atr_val=1.0)
    assert len(breaks) == 1
    b = breaks[0]
    assert b.direction == "BEARISH"
    assert b.break_candle_index == 8
    assert "2-TOUCH TRENDLINE BREAK" in b.notes

# -------------------------------------------------------------
# 3. 3-touch breakout can generate a valid signal
# -------------------------------------------------------------
def test_3_3touch_breakout_generates_valid_signal():
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
    assert len(tls) >= 1
    assert tls[0].touch_count >= 3

    breaks = TrendlineDetector.detect_trendline_breaks(candles, tls, "TEST", "5M", atr_val=1.0)
    assert len(breaks) == 1
    b = breaks[0]
    assert b.direction == "BEARISH"
    assert b.break_candle_index == 12
    assert "3-TOUCH TRENDLINE BREAK" in b.notes
    assert b.evidence_score == 90

# -------------------------------------------------------------
# 4. 3-touch is classified separately from 2-touch
# -------------------------------------------------------------
def test_4_3touch_classified_separately_from_2touch():
    c_2t = [make_candle(i, 100+i, 105+i, 99+i, 101+i) for i in range(10)]
    c_2t[2] = make_candle(2, 102, 104, 102, 103)
    c_2t[6] = make_candle(6, 106, 108, 106, 107)
    c_2t[8] = make_candle(8, 108, 108.5, 103.5, 104)
    sw_2t = [make_swing(2, c_2t, 102.0, is_high=False), make_swing(6, c_2t, 106.0, is_high=False)]
    tl_2t = TrendlineDetector.fit_trendlines(c_2t, sw_2t)
    breaks_2t = TrendlineDetector.detect_trendline_breaks(c_2t, tl_2t, "TEST", "5M")
    assert "2-TOUCH TRENDLINE BREAK" in breaks_2t[0].notes
    assert breaks_2t[0].evidence_score == 75

    c_3t = [make_candle(i, 100+i, 105+i, 99+i, 101+i) for i in range(14)]
    c_3t[2] = make_candle(2, 102, 104, 102, 103)
    c_3t[6] = make_candle(6, 106, 108, 106, 107)
    c_3t[10] = make_candle(10, 110, 112, 110, 111)
    c_3t[12] = make_candle(12, 112, 112.5, 107.5, 108)
    sw_3t = [
        make_swing(2, c_3t, 102.0, is_high=False),
        make_swing(4, c_3t, 109.0, is_high=True),
        make_swing(6, c_3t, 106.0, is_high=False),
        make_swing(8, c_3t, 114.0, is_high=True),
        make_swing(10, c_3t, 110.0, is_high=False),
    ]
    tl_3t = TrendlineDetector.fit_trendlines(c_3t, sw_3t)
    breaks_3t = TrendlineDetector.detect_trendline_breaks(c_3t, tl_3t, "TEST", "5M")
    assert "3-TOUCH TRENDLINE BREAK" in breaks_3t[0].notes
    assert breaks_3t[0].evidence_score == 90

    engine = AlertEngine()
    synthesis_2t = MultiTimeframeSynthesis(
        symbol="NIFTY",
        ticker="^NSEI",
        provider="TEST",
        last_updated="2026-09-01T00:45:00Z",
        is_stale=False,
        status_message="OK",
        current_price=104.0,
        overall_bias="BEARISH",
        current_state="FULL BEARISH ALIGNMENT",
        confirmation_state="CONFIRMED",
        short_term_state="BEARISH",
        synthesis_rationale="Test",
        evidence_score=EvidenceScoreBreakdown(
            total_score=85,
            category="Strong Evidence Alignment",
            structure_points=25,
            htf_alignment_points=25,
            momentum_points=15,
            volume_points=10,
            breakout_points=10,
            details=[]
        ),
        timeframes={"5M": SingleTimeframeAnalysis(
            timeframe="5M",
            trend="BEARISH",
            structure_type="BEARISH",
            breakout_status="CONFIRMED BREAKDOWN",
            candle_count=10,
            latest_candle_time="2026-09-01T00:45:00Z",
            indicators=TechnicalIndicators(),
            support_resistance=SupportResistanceSummary(current_price=104.0),
            recent_events=breaks_2t
        )}
    )
    alerts_2t = engine.process_synthesis_for_alerts(synthesis_2t)
    assert len(alerts_2t) >= 1
    assert "2-TOUCH TRENDLINE BREAK — BEARISH" in alerts_2t[0].message

    engine_3t = AlertEngine()
    synthesis_3t = MultiTimeframeSynthesis(
        symbol="NIFTY",
        ticker="^NSEI",
        provider="TEST",
        last_updated="2026-09-01T00:45:00Z",
        is_stale=False,
        status_message="OK",
        current_price=108.0,
        overall_bias="BEARISH",
        current_state="FULL BEARISH ALIGNMENT",
        confirmation_state="CONFIRMED",
        short_term_state="BEARISH",
        synthesis_rationale="Test",
        evidence_score=EvidenceScoreBreakdown(
            total_score=90,
            category="Strong Evidence Alignment",
            structure_points=25,
            htf_alignment_points=25,
            momentum_points=15,
            volume_points=15,
            breakout_points=10,
            details=[]
        ),
        timeframes={"5M": SingleTimeframeAnalysis(
            timeframe="5M",
            trend="BEARISH",
            structure_type="BEARISH",
            breakout_status="CONFIRMED BREAKDOWN",
            candle_count=14,
            latest_candle_time="2026-09-01T00:45:00Z",
            indicators=TechnicalIndicators(),
            support_resistance=SupportResistanceSummary(current_price=108.0),
            recent_events=breaks_3t
        )}
    )
    alerts_3t = engine_3t.process_synthesis_for_alerts(synthesis_3t)
    assert len(alerts_3t) >= 1
    assert "3-TOUCH TRENDLINE BREAK — BEARISH" in alerts_3t[0].message

# -------------------------------------------------------------
# 5. 1-touch cannot create a trendline
# -------------------------------------------------------------
def test_5_1touch_cannot_create_trendline():
    candles = [make_candle(i, 100 + i, 105 + i, 99 + i, 101 + i) for i in range(12)]
    swings = [
        make_swing(2, candles, 101.0, is_high=False),
        make_swing(6, candles, 108.0, is_high=True),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    support_lines = [t for t in tls if t.line_type == "ASCENDING_SUPPORT"]
    assert len(support_lines) == 0

# -------------------------------------------------------------
# 6. Artificial swings cannot create touches
# -------------------------------------------------------------
def test_6_artificial_swings_cannot_create_touches():
    candles = [make_candle(i, 100 + i, 105 + i, 99 + i, 101 + i) for i in range(12)]
    swings = [
        make_swing(2, candles, 101.0, is_high=False, confirmed=False),
        make_swing(6, candles, 105.0, is_high=False, confirmed=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    assert len(tls) == 0

# -------------------------------------------------------------
# 7. Wick-only break does not trigger
# -------------------------------------------------------------
def test_7_wick_only_break_does_not_trigger():
    candles = []
    for i in range(10):
        base = 100.0 + 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base + 2, base + 4, 102.0, base + 2))
        elif i == 6:
            candles.append(make_candle(i, base + 2, base + 4, 106.0, base + 2))
        elif i == 8:
            candles.append(make_candle(i, 109.0, 110.0, 104.0, 109.0))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2.0, base + 4))

    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(6, candles, 106.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    breaks = TrendlineDetector.detect_trendline_breaks(candles, tls, "TEST", "5M", atr_val=1.0)
    assert len(breaks) == 0

# -------------------------------------------------------------
# 8. Unfinished candle does not trigger
# -------------------------------------------------------------
def test_8_unfinished_candle_does_not_trigger():
    candles = []
    for i in range(10):
        base = 100.0 + 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base + 2, base + 4, 102.0, base + 2))
        elif i == 6:
            candles.append(make_candle(i, base + 2, base + 4, 106.0, base + 2))
        elif i == 8:
            candles.append(make_candle(i, 108.0, 108.5, 103.5, 104.0))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2.0, base + 4))

    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(6, candles, 106.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)

    now_during_candle = datetime(2026, 9, 1, 0, 42, 0, tzinfo=timezone.utc)
    breaks_unfinished = TrendlineDetector.detect_trendline_breaks(
        candles, tls, "TEST", "5M", atr_val=1.0, now=now_during_candle
    )
    assert len(breaks_unfinished) == 0

# -------------------------------------------------------------
# 9. Completed candle does trigger
# -------------------------------------------------------------
def test_9_completed_candle_triggers():
    candles = []
    for i in range(10):
        base = 100.0 + 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base + 2, base + 4, 102.0, base + 2))
        elif i == 6:
            candles.append(make_candle(i, base + 2, base + 4, 106.0, base + 2))
        elif i == 8:
            candles.append(make_candle(i, 108.0, 108.5, 103.5, 104.0))
        else:
            candles.append(make_candle(i, base + 3, base + 6, base + 2.0, base + 4))

    swings = [
        make_swing(2, candles, 102.0, is_high=False),
        make_swing(6, candles, 106.0, is_high=False),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)

    now_after_close = datetime(2026, 9, 1, 0, 45, 1, tzinfo=timezone.utc)
    breaks_completed = TrendlineDetector.detect_trendline_breaks(
        candles, tls, "TEST", "5M", atr_val=1.0, now=now_after_close
    )
    assert len(breaks_completed) == 1
    assert breaks_completed[0].break_candle_index == 8

# -------------------------------------------------------------
# 10. Ascending Action Line break = bearish/short
# -------------------------------------------------------------
def test_10_ascending_action_line_break_is_bearish():
    candles = [make_candle(i, 100+i, 105+i, 99+i, 101+i) for i in range(10)]
    candles[2] = make_candle(2, 102, 104, 102, 103)
    candles[6] = make_candle(6, 106, 108, 106, 107)
    candles[8] = make_candle(8, 108, 108.5, 103.5, 104)
    swings = [make_swing(2, candles, 102.0, is_high=False), make_swing(6, candles, 106.0, is_high=False)]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    breaks = TrendlineDetector.detect_trendline_breaks(candles, tls, "TEST", "5M")
    assert len(breaks) == 1
    assert breaks[0].direction == "BEARISH"
    assert breaks[0].htf_alignment == "BEARISH"
    assert "BEARISH" in breaks[0].notes

# -------------------------------------------------------------
# 11. Descending Action Line break = bullish/long
# -------------------------------------------------------------
def test_11_descending_action_line_break_is_bullish():
    candles = []
    for i in range(10):
        base = 200.0 - 1.0 * i
        if i == 2:
            candles.append(make_candle(i, base - 2, 198.0, base - 4, base - 2))
        elif i == 6:
            candles.append(make_candle(i, base - 2, 194.0, base - 4, base - 2))
        elif i == 8:
            candles.append(make_candle(i, 192.0, 196.5, 191.5, 196.0))
        else:
            candles.append(make_candle(i, base - 3, base - 1.5, base - 6, base - 4))

    swings = [
        make_swing(2, candles, 198.0, is_high=True),
        make_swing(6, candles, 194.0, is_high=True),
    ]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    breaks = TrendlineDetector.detect_trendline_breaks(candles, tls, "TEST", "5M", atr_val=1.0)
    assert len(breaks) == 1
    assert breaks[0].direction == "BULLISH"
    assert breaks[0].htf_alignment == "BULLISH"
    assert "BULLISH" in breaks[0].notes

# -------------------------------------------------------------
# 12. Opposing Safety Line is required when configured
# -------------------------------------------------------------
def test_12_opposing_safety_line_required():
    action_tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=2, p1_price=102.0, p1_time="2026-09-01T00:10:00Z",
        p2_index=6, p2_price=106.0, p2_time="2026-09-01T00:30:00Z",
        slope=1.0, intercept=100.0, end_index=8, end_price=108.0,
        rank="PRIMARY", strength="INTERMEDIATE"
    )
    candles = [make_candle(i, 100+i, 105+i, 99+i, 101+i) for i in range(10)]
    candles[8] = make_candle(8, 108.0, 108.5, 103.5, 104.0)

    breaks_no_safety = TrendlineDetector.detect_trendline_breaks(
        candles, [action_tl], "TEST", "5M", atr_val=1.0, require_safety_line=True
    )
    assert len(breaks_no_safety) == 0

    safety_tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=1, p1_price=112.0, p1_time="2026-09-01T00:05:00Z",
        p2_index=5, p2_price=110.0, p2_time="2026-09-01T00:25:00Z",
        slope=-0.5, intercept=112.5, end_index=8, end_price=108.5,
        rank="PRIMARY", strength="INTERMEDIATE"
    )
    breaks_with_safety = TrendlineDetector.detect_trendline_breaks(
        candles, [action_tl, safety_tl], "TEST", "5M", atr_val=1.0, require_safety_line=True
    )
    assert len(breaks_with_safety) == 1
    assert "Safety Line" in breaks_with_safety[0].notes

    far_safety_tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=1, p1_price=200.0, p1_time="2026-09-01T00:05:00Z",
        p2_index=5, p2_price=195.0, p2_time="2026-09-01T00:25:00Z",
        slope=-1.25, intercept=201.25, end_index=8, end_price=191.25,
        rank="PRIMARY", strength="INTERMEDIATE"
    )
    breaks_far_safety = TrendlineDetector.detect_trendline_breaks(
        candles, [action_tl, far_safety_tl], "TEST", "5M", atr_val=1.0, require_safety_line=True
    )
    assert len(breaks_far_safety) == 0

# -------------------------------------------------------------
# 13. Same symbol/timeframe/candle cannot produce both directions
# -------------------------------------------------------------
def test_13_same_candle_cannot_produce_both_directions():
    tl_up = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=2, p1_price=99.8, p1_time="2026-09-01T00:10:00Z",
        p2_index=6, p2_price=103.8, p2_time="2026-09-01T00:30:00Z",
        slope=1.0, intercept=97.8, end_index=8, end_price=105.8,
        rank="PRIMARY", strength="INTERMEDIATE"
    )
    tl_down = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=2, p1_price=110.2, p1_time="2026-09-01T00:10:00Z",
        p2_index=6, p2_price=106.2, p2_time="2026-09-01T00:30:00Z",
        slope=-1.0, intercept=112.2, end_index=8, end_price=104.2,
        rank="SECONDARY", strength="INTERMEDIATE"
    )
    candles = [make_candle(i, 105.0, 106.0, 104.0, 105.0) for i in range(10)]

    breaks = TrendlineDetector.detect_trendline_breaks(candles, [tl_up, tl_down], "TEST", "5M", atr_val=1.0)
    assert len(breaks) == 1
    assert breaks[0].direction == "BEARISH"

# -------------------------------------------------------------
# 14. 1H candle is not marked closed before its actual close
# -------------------------------------------------------------
def test_14_1h_candle_not_marked_closed_before_actual_close():
    candle_ts = "2026-09-09T10:00:00Z"
    tf = "1H"

    now_mid = datetime(2026, 9, 9, 10, 45, 0, tzinfo=timezone.utc)
    assert is_candle_closed(candle_ts, tf, now=now_mid) is False

    now_almost = datetime(2026, 9, 9, 10, 59, 59, tzinfo=timezone.utc)
    assert is_candle_closed(candle_ts, tf, now=now_almost) is False

    now_exact = datetime(2026, 9, 9, 11, 0, 0, tzinfo=timezone.utc)
    assert is_candle_closed(candle_ts, tf, now=now_exact) is True

    now_after = datetime(2026, 9, 9, 11, 5, 0, tzinfo=timezone.utc)
    assert is_candle_closed(candle_ts, tf, now=now_after) is True

# -------------------------------------------------------------
# 15. 5M, 15M, 1H, 4H close timing works across UTC & IST
# -------------------------------------------------------------
def test_15_various_timeframes_close_timing():
    ts_5m = "2026-09-09T10:00:00Z"
    assert is_candle_closed(ts_5m, "5M", now=datetime(2026, 9, 9, 10, 4, 59, tzinfo=timezone.utc)) is False
    assert is_candle_closed(ts_5m, "5M", now=datetime(2026, 9, 9, 10, 5, 0, tzinfo=timezone.utc)) is True

    ts_15m = "2026-09-09T10:00:00Z"
    assert is_candle_closed(ts_15m, "15M", now=datetime(2026, 9, 9, 10, 14, 59, tzinfo=timezone.utc)) is False
    assert is_candle_closed(ts_15m, "15M", now=datetime(2026, 9, 9, 10, 15, 0, tzinfo=timezone.utc)) is True

    ts_4h = "2026-09-09T08:00:00Z"
    assert is_candle_closed(ts_4h, "4H", now=datetime(2026, 9, 9, 11, 59, 59, tzinfo=timezone.utc)) is False
    assert is_candle_closed(ts_4h, "4H", now=datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)) is True

    ts_ist_last = "2026-09-09T15:15:00+05:30"
    now_ist_before = datetime(2026, 9, 9, 15, 29, 0, tzinfo=KOLKATA_TZ)
    now_ist_after = datetime(2026, 9, 9, 15, 30, 0, tzinfo=KOLKATA_TZ)
    assert is_candle_closed(ts_ist_last, "15M", now=now_ist_before) is False
    assert is_candle_closed(ts_ist_last, "15M", now=now_ist_after) is True

# -------------------------------------------------------------
# 16. API serialization and UI compatibility preserved
# -------------------------------------------------------------
def test_16_api_serialization_and_ui_compatibility():
    candles = [make_candle(i, 100+i, 105+i, 99+i, 101+i) for i in range(12)]
    swings = [make_swing(2, candles, 102.0, is_high=False), make_swing(6, candles, 106.0, is_high=False)]
    tls = TrendlineDetector.fit_trendlines(candles, swings)
    assert len(tls) >= 1
    d = tls[0].to_dict()
    required_keys = [
        "line_type", "rank", "strength", "p1_index", "p1_price", "p1_time",
        "p2_index", "p2_price", "p2_time", "end_index", "end_price", "slope",
        "intercept", "touch_count", "touch_points", "r_squared", "status",
        "is_active", "is_broken"
    ]
    for k in required_keys:
        assert k in d, f"Missing key {k} in trendline dict"
    assert d["touch_count"] == 2
    assert len(d["touch_points"]) == 2
