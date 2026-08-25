import pytest
from datetime import datetime, timezone
import zoneinfo
from app.core.timezone import (
    KOLKATA_TZ,
    UTC_TZ,
    to_utc,
    to_market_tz,
    format_market_time,
    format_market_datetime,
    parse_iso_datetime,
    get_market_tz
)
from app.models.schemas import Candle, SwingPoint, StructureBreakEvent
from app.data.candle_builder import SessionAwareCandleBuilder
from app.market_structure.bos_choch import BOSCHoCHDetector
from app.market_structure.trendlines import TrendlineDetector, Trendline
from app.alerts.engine import AlertEngine

# -------------------------------------------------------------
# MASTER PROMPT SECTION 35: 10 CANONICAL TIMEZONE TESTS
# -------------------------------------------------------------

def test_section35_test1_known_utc_to_ist():
    """
    TEST 1:
    Known UTC timestamp: 2026-08-25T03:45:00Z
    Expected Indian time: 09:15 IST (since UTC+05:30: 03:45 + 05:30 = 09:15).
    """
    utc_str = "2026-08-25T03:45:00Z"
    dt_ist = to_market_tz(utc_str, KOLKATA_TZ)
    formatted = format_market_time(utc_str, KOLKATA_TZ)
    
    assert dt_ist.hour == 9
    assert dt_ist.minute == 15
    assert formatted == "09:15 IST"

def test_section35_test2_known_market_open():
    """
    TEST 2:
    Known market open timestamp for NSE.
    Expected: 09:15 IST.
    """
    market_open_ist_str = "2026-08-25T09:15:00+05:30"
    formatted = format_market_time(market_open_ist_str, KOLKATA_TZ)
    assert formatted == "09:15 IST"

def test_section35_test3_5m_candle_sequence():
    """
    TEST 3:
    5M candle sequence starting at market open.
    Expected: 09:15, 09:20, 09:25, 09:30...
    """
    base_times = [
        "2026-08-25T09:15:00+05:30",
        "2026-08-25T09:20:00+05:30",
        "2026-08-25T09:25:00+05:30",
        "2026-08-25T09:30:00+05:30",
        "2026-08-25T09:35:00+05:30"
    ]
    formatted_times = [format_market_time(ts, KOLKATA_TZ, include_suffix=False) for ts in base_times]
    assert formatted_times == ["09:15", "09:20", "09:25", "09:30", "09:35"]

def test_section35_test4_15m_candle_sequence():
    """
    TEST 4:
    15M sequence starting at market open.
    Expected: 09:15, 09:30, 09:45, 10:00...
    """
    base_times = [
        "2026-08-25T09:15:00+05:30",
        "2026-08-25T09:30:00+05:30",
        "2026-08-25T09:45:00+05:30",
        "2026-08-25T10:00:00+05:30"
    ]
    formatted_times = [format_market_time(ts, KOLKATA_TZ, include_suffix=False) for ts in base_times]
    assert formatted_times == ["09:15", "09:30", "09:45", "10:00"]

def test_section35_test5_frontend_receives_utc_converts_to_ist():
    """
    TEST 5:
    Backend sends UTC timestamp '2026-08-25T05:15:00Z'.
    Expected Indian time: '10:45 IST'.
    """
    utc_str = "2026-08-25T05:15:00Z"
    formatted_ist = format_market_time(utc_str, KOLKATA_TZ)
    assert formatted_ist == "10:45 IST"

def test_section35_test6_timezone_aware_no_double_conversion():
    """
    TEST 6:
    Input is already timezone-aware IST: '2026-08-25T10:45:00+05:30'.
    Converting to market timezone must NOT shift by another 5h30m.
    Expected: '10:45 IST'.
    """
    ist_str = "2026-08-25T10:45:00+05:30"
    dt = to_market_tz(ist_str, KOLKATA_TZ)
    formatted = format_market_time(dt, KOLKATA_TZ)
    assert formatted == "10:45 IST"
    assert dt.hour == 10
    assert dt.minute == 45

def test_section35_test7_notification_timestamp_equals_candle_timestamp():
    """
    TEST 7:
    Notification timestamp matches the confirmed break candle's timestamp.
    """
    candle_ts = "2026-08-25T10:45:00+05:30"
    event = StructureBreakEvent(
        id="NIFTY_15M_TL_BULL_2026-08-25T10:45:00+05:30_5",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp=candle_ts,
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
    assert event.timestamp == candle_ts
    assert format_market_time(event.timestamp, KOLKATA_TZ) == "10:45 IST"

def test_section35_test8_bos_timestamp_equals_confirmed_candle_timestamp():
    """
    TEST 8:
    BOS timestamp equals the confirmed closed candle timestamp.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100+i, high=102+i, low=99+i, close=101+i, volume=1000)
        for i in range(12)
    ]
    # Swings with at least 1 high and 1 low
    swings = [
        SwingPoint(index=1, price=99.0, timestamp="2026-08-25T10:05:00+05:30", is_high=False, type="LL", strength=2.0, confirmation_index=3, confirmed=True),
        SwingPoint(index=2, price=102.0, timestamp="2026-08-25T10:10:00+05:30", is_high=True, type="HH", strength=2.0, confirmation_index=4, confirmed=True)
    ]
    events = BOSCHoCHDetector.detect_structure_breaks(candles, swings, "NIFTY 50", "5M")
    assert len(events) >= 1
    # Event timestamp must match the break candle index timestamp
    break_evt = events[0]
    expected_ts = candles[break_evt.break_candle_index].timestamp
    assert break_evt.timestamp == expected_ts

def test_section35_test9_up_breakout_timestamp_equals_confirmed_breakout_candle():
    """
    TEST 9:
    UP BREAKOUT timestamp matches confirmed breakout candle.
    """
    candle_break_ts = "2026-08-25T11:15:00+05:30"
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=110.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=4, p2_price=102.0, p2_time="2026-08-25T11:00:00+05:30",
        slope=-2.0, intercept=110.0, end_index=6, end_price=98.0,
        rank="PRIMARY", strength="MAJOR"
    )
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*15:02d}:00+05:30", open=110-2*i, high=111-2*i, low=109-2*i, close=110-2*i, volume=1000)
        for i in range(5)
    ]
    # Candle 5 at 11:15 breaks above line
    curr_c = Candle(timestamp=candle_break_ts, open=98.0, high=106.0, low=98.0, close=105.0, volume=2000)
    candles.append(curr_c)

    breaks = TrendlineDetector.detect_trendline_breaks(candles, [tl], "NIFTY 50", "15M", atr_val=1.0)
    assert len(breaks) == 1
    assert breaks[0].timestamp == candle_break_ts
    assert format_market_time(breaks[0].timestamp, KOLKATA_TZ) == "11:15 IST"

def test_section35_test10_down_breakout_timestamp_equals_confirmed_breakout_candle():
    """
    TEST 10:
    DOWN BREAKOUT timestamp matches confirmed breakdown candle.
    """
    candle_break_ts = "2026-08-25T11:30:00+05:30"
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=0, p1_price=100.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=4, p2_price=108.0, p2_time="2026-08-25T11:00:00+05:30",
        slope=2.0, intercept=100.0, end_index=6, end_price=112.0,
        rank="PRIMARY", strength="MAJOR"
    )
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*15:02d}:00+05:30", open=100+2*i, high=101+2*i, low=99+2*i, close=100+2*i, volume=1000)
        for i in range(5)
    ]
    # Candle 5 at 11:30 breaks below line (line at index 5 is 110.0, close is 104.0)
    curr_c = Candle(timestamp=candle_break_ts, open=109.0, high=109.5, low=103.0, close=104.0, volume=2000)
    candles.append(curr_c)

    breaks = TrendlineDetector.detect_trendline_breaks(candles, [tl], "NIFTY 50", "15M", atr_val=1.0)
    assert len(breaks) == 1
    assert breaks[0].timestamp == candle_break_ts
    assert breaks[0].direction == "BEARISH"
    assert format_market_time(breaks[0].timestamp, KOLKATA_TZ) == "11:30 IST"
