import pytest
import pandas as pd
from app.models.schemas import Candle, SwingPoint
from app.market_structure.trendlines import Trendline
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector

# -------------------------------------------------------------
# MASTER PROMPT: TESTS 1 TO 7 (TRENDLINE + 20 EMA + VOLUME)
# -------------------------------------------------------------

def test_pbreakout_test1_valid_up_breakout():
    """
    TEST 1:
    Valid descending resistance trendline.
    Candle closes above trendline.
    Candle closes above 20 EMA.
    Volume >= 1.20 average.
    Expected: TRENDLINE_EMA_VOLUME_UP_BREAKOUT
    """
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=110.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=100.0, p2_time="2026-08-25T11:15:00+05:30",
        slope=-2.0, intercept=110.0, end_index=10, end_price=90.0,
        rank="PRIMARY", strength="MAJOR"
    )
    # 10 baseline candles (below line, volume=1000)
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*15:02d}:00+05:30", open=110-2*i, high=111-2*i, low=108-2*i, close=109-2*i, volume=1000)
        for i in range(10)
    ]
    # Candle 10 at index 10 (trendline at index 10 is 90.0, 20 EMA is 91.0)
    # Breakout candle: close=96.0 > 90.0 (TL) and > 91.0 (EMA), volume=1500 (1.5x)
    breakout_c = Candle(timestamp="2026-08-25T12:30:00+05:30", open=89.0, high=97.0, low=89.0, close=96.0, volume=1500)
    candles.append(breakout_c)

    df_ind = pd.DataFrame({
        "ema_20": [91.0] * len(candles),
        "relative_volume": [1.0] * 10 + [1.50],
        "atr_14": [1.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_trendline_ema_volume_breakouts(
        candles=candles, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="15M", atr_val=1.0, good_volume_threshold=1.20
    )

    assert len(breaks) == 1
    assert breaks[0].event_type == "TRENDLINE_EMA_VOLUME_UP_BREAKOUT"
    assert breaks[0].direction == "BULLISH"
    assert breaks[0].break_price == 96.0
    assert breaks[0].broken_level == 90.0

def test_pbreakout_test2_tl_broken_ema_not_broken():
    """
    TEST 2:
    Trendline broken.
    EMA not broken.
    Expected: NO ALERT.
    """
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=110.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=100.0, p2_time="2026-08-25T11:15:00+05:30",
        slope=-2.0, intercept=110.0, end_index=10, end_price=90.0,
        rank="PRIMARY", strength="MAJOR"
    )
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*15:02d}:00+05:30", open=110-2*i, high=111-2*i, low=108-2*i, close=109-2*i, volume=1000)
        for i in range(10)
    ]
    # At index 10: TL is 90.0, EMA is 97.0
    # Candle closes at 93.0 (> 90.0 TL, but < 97.0 EMA)
    breakout_c = Candle(timestamp="2026-08-25T12:30:00+05:30", open=89.0, high=94.0, low=89.0, close=93.0, volume=1500)
    candles.append(breakout_c)

    df_ind = pd.DataFrame({
        "ema_20": [97.0] * len(candles),
        "relative_volume": [1.0] * 10 + [1.50],
        "atr_14": [1.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_trendline_ema_volume_breakouts(
        candles=candles, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="15M", atr_val=1.0, good_volume_threshold=1.20
    )
    assert len(breaks) == 0

def test_pbreakout_test3_ema_broken_tl_not_broken():
    """
    TEST 3:
    EMA broken.
    Trendline not broken.
    Expected: NO ALERT.
    """
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=110.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=100.0, p2_time="2026-08-25T11:15:00+05:30",
        slope=-2.0, intercept=110.0, end_index=10, end_price=90.0,
        rank="PRIMARY", strength="MAJOR"
    )
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*15:02d}:00+05:30", open=110-2*i, high=111-2*i, low=108-2*i, close=109-2*i, volume=1000)
        for i in range(10)
    ]
    # At index 10: TL is 90.0, EMA is 85.0
    # Candle closes at 88.0 (> 85.0 EMA, but < 90.0 TL)
    breakout_c = Candle(timestamp="2026-08-25T12:30:00+05:30", open=84.0, high=89.0, low=84.0, close=88.0, volume=1500)
    candles.append(breakout_c)

    df_ind = pd.DataFrame({
        "ema_20": [85.0] * len(candles),
        "relative_volume": [1.0] * 10 + [1.50],
        "atr_14": [1.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_trendline_ema_volume_breakouts(
        candles=candles, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="15M", atr_val=1.0, good_volume_threshold=1.20
    )
    assert len(breaks) == 0

def test_pbreakout_test4_both_broken_volume_weak():
    """
    TEST 4:
    Both broken.
    Volume < 1.20.
    Expected: NO ALERT.
    """
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=110.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=100.0, p2_time="2026-08-25T11:15:00+05:30",
        slope=-2.0, intercept=110.0, end_index=10, end_price=90.0,
        rank="PRIMARY", strength="MAJOR"
    )
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*15:02d}:00+05:30", open=110-2*i, high=111-2*i, low=108-2*i, close=109-2*i, volume=1000)
        for i in range(10)
    ]
    # Candle closes at 96.0 (both levels broken), but relative_volume is 0.95 (< 1.20)
    breakout_c = Candle(timestamp="2026-08-25T12:30:00+05:30", open=89.0, high=97.0, low=89.0, close=96.0, volume=950)
    candles.append(breakout_c)

    df_ind = pd.DataFrame({
        "ema_20": [91.0] * len(candles),
        "relative_volume": [1.0] * 10 + [0.95],
        "atr_14": [1.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_trendline_ema_volume_breakouts(
        candles=candles, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="15M", atr_val=1.0, good_volume_threshold=1.20
    )
    assert len(breaks) == 0

def test_pbreakout_test5_wick_breaks_both_close_returns_below():
    """
    TEST 5:
    Wick breaks both (High = 98.0 > TL 90 & EMA 91),
    but candle Close returns to 88.0 (< 90 & < 91).
    Expected: NO ALERT.
    """
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=110.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=100.0, p2_time="2026-08-25T11:15:00+05:30",
        slope=-2.0, intercept=110.0, end_index=10, end_price=90.0,
        rank="PRIMARY", strength="MAJOR"
    )
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*15:02d}:00+05:30", open=110-2*i, high=111-2*i, low=108-2*i, close=109-2*i, volume=1000)
        for i in range(10)
    ]
    # Candle pierced to High 98.0, but Closed at 88.0
    wick_c = Candle(timestamp="2026-08-25T12:30:00+05:30", open=89.0, high=98.0, low=87.0, close=88.0, volume=1800)
    candles.append(wick_c)

    df_ind = pd.DataFrame({
        "ema_20": [91.0] * len(candles),
        "relative_volume": [1.0] * 10 + [1.80],
        "atr_14": [1.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_trendline_ema_volume_breakouts(
        candles=candles, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="15M", atr_val=1.0, good_volume_threshold=1.20
    )
    assert len(breaks) == 0

def test_pbreakout_test6_intrabar_cross_final_close_below():
    """
    TEST 6:
    Price crossed both intrabar, but at final close price closed below.
    Expected: NO ALERT.
    """
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=110.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=100.0, p2_time="2026-08-25T11:15:00+05:30",
        slope=-2.0, intercept=110.0, end_index=10, end_price=90.0,
        rank="PRIMARY", strength="MAJOR"
    )
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*15:02d}:00+05:30", open=110-2*i, high=111-2*i, low=108-2*i, close=109-2*i, volume=1000)
        for i in range(10)
    ]
    # Intrabar crossed to 95.0, final close = 89.5
    intrabar_c = Candle(timestamp="2026-08-25T12:30:00+05:30", open=89.0, high=95.0, low=88.0, close=89.5, volume=1500)
    candles.append(intrabar_c)

    df_ind = pd.DataFrame({
        "ema_20": [91.0] * len(candles),
        "relative_volume": [1.0] * 10 + [1.50],
        "atr_14": [1.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_trendline_ema_volume_breakouts(
        candles=candles, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="15M", atr_val=1.0, good_volume_threshold=1.20
    )
    assert len(breaks) == 0

def test_pbreakout_test7_all_conditions_confirmed_same_candle():
    """
    TEST 7:
    All conditions confirmed by the same candle close.
    Expected: Exactly ONE alert.
    """
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=0, p1_price=100.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=110.0, p2_time="2026-08-25T11:15:00+05:30",
        slope=2.0, intercept=100.0, end_index=10, end_price=120.0,
        rank="PRIMARY", strength="MAJOR"
    )
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*15:02d}:00+05:30", open=100+2*i, high=101+2*i, low=99+2*i, close=100+2*i, volume=1000)
        for i in range(10)
    ]
    # At index 10: TL is 120.0, EMA is 118.0
    # Breakdown candle: close=112.0 < 120.0 & < 118.0, volume=1400 (1.4x)
    breakdown_c = Candle(timestamp="2026-08-25T12:30:00+05:30", open=119.0, high=119.5, low=111.0, close=112.0, volume=1400)
    candles.append(breakdown_c)

    df_ind = pd.DataFrame({
        "ema_20": [118.0] * len(candles),
        "relative_volume": [1.0] * 10 + [1.40],
        "atr_14": [1.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_trendline_ema_volume_breakouts(
        candles=candles, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="15M", atr_val=1.0, good_volume_threshold=1.20
    )
    assert len(breaks) == 1
    assert breaks[0].event_type == "TRENDLINE_EMA_VOLUME_DOWN_BREAKOUT"
    assert breaks[0].direction == "BEARISH"

# -------------------------------------------------------------
# MASTER PROMPT: TESTS 8 TO 11 (W PATTERN + TL + 20 EMA)
# -------------------------------------------------------------

def test_pbreakout_test8_valid_w_pattern_breakout():
    """
    TEST 8:
    Valid W pattern.
    Neckline broken.
    Trendline broken.
    20 EMA broken.
    Same candle closes above all.
    Expected: W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    # W Pattern: L1 at index 2 (90.0), Neckline Peak at index 5 (100.0), L2 at index 8 (91.0)
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmation_index=4, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmation_index=7, confirmed=True),
        SwingPoint(index=8, price=91.0, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmation_index=10, confirmed=True)
    ]
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=105.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=98.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=-1.4, intercept=105.0, end_index=14, end_price=85.0,
        rank="PRIMARY", strength="MAJOR"
    )
    # Candle 12 at index 12: Neckline is 100.0, TL is ~88.2, EMA is 96.0
    # Candle 12 closes at 100.5 > 100.0 (Neck) & > 88.2 (TL) & > 96.0 (EMA), RR = 9.5 / 9.8 = 0.97 >= 0.85
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=99.0, high=101.0, low=98.5, close=100.5, volume=2000)

    df_ind = pd.DataFrame({
        "ema_20": [96.0] * len(candles),
        "atr_14": [2.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 1
    assert breaks[0].event_type == "W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT"
    assert breaks[0].direction == "BULLISH"
    assert breaks[0].broken_level == 100.0

def test_pbreakout_test9_w_neckline_broken_ema_not_broken():
    """
    TEST 9:
    W neckline broken, but EMA not broken.
    Expected: NO ALERT.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmation_index=4, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmation_index=7, confirmed=True),
        SwingPoint(index=8, price=90.2, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmation_index=10, confirmed=True)
    ]
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=105.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=98.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=-1.4, intercept=105.0, end_index=14, end_price=85.0,
        rank="PRIMARY", strength="MAJOR"
    )
    # Candle closes at 102.0 > 100.0 (Neckline), but EMA is 106.0 (< 106.0 EMA)
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=97.0, high=103.0, low=97.0, close=102.0, volume=2000)

    df_ind = pd.DataFrame({
        "ema_20": [106.0] * len(candles),
        "atr_14": [2.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

def test_pbreakout_test10_w_neckline_broken_tl_not_broken():
    """
    TEST 10:
    W neckline broken, Trendline not broken.
    Expected: NO ALERT.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmation_index=4, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmation_index=7, confirmed=True),
        SwingPoint(index=8, price=90.2, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmation_index=10, confirmed=True)
    ]
    # Steep descending line above current price (TL price at index 12 is 115.0)
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=130.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=124.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=-1.2, intercept=130.0, end_index=14, end_price=113.0,
        rank="PRIMARY", strength="MAJOR"
    )
    # Candle closes at 104.0 > 100.0 (Neck), but < 115.6 (TL)
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=97.0, high=105.0, low=97.0, close=104.0, volume=2000)

    df_ind = pd.DataFrame({
        "ema_20": [96.0] * len(candles),
        "atr_14": [2.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

def test_pbreakout_test11_w_temporary_cross_close_returns_below():
    """
    TEST 11:
    W levels temporarily crossed (High = 106.0), but Final Close returns to 98.0 (< Neckline 100.0).
    Expected: NO ALERT.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmation_index=4, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmation_index=7, confirmed=True),
        SwingPoint(index=8, price=90.2, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmation_index=10, confirmed=True)
    ]
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=105.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=98.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=-1.4, intercept=105.0, end_index=14, end_price=85.0,
        rank="PRIMARY", strength="MAJOR"
    )
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=97.0, high=106.0, low=96.0, close=98.0, volume=2000)

    df_ind = pd.DataFrame({
        "ema_20": [96.0] * len(candles),
        "atr_14": [2.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

# -------------------------------------------------------------
# MASTER PROMPT: TESTS 12 TO 15 (M PATTERN + TL + 20 EMA)
# -------------------------------------------------------------

def test_pbreakout_test12_valid_m_pattern_breakout():
    """
    TEST 12:
    Valid M pattern.
    Neckline broken.
    Trendline broken.
    20 EMA broken.
    Same candle closes below all.
    Expected: M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    # M Pattern: H1 at index 2 (110.0), Neckline Trough at index 5 (100.0), H2 at index 8 (109.0)
    swings = [
        SwingPoint(index=2, price=110.0, timestamp="2026-08-25T10:10:00+05:30", is_high=True, type="HH", strength=2.0, confirmation_index=4, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=False, type="HL", strength=2.0, confirmation_index=7, confirmed=True),
        SwingPoint(index=8, price=109.0, timestamp="2026-08-25T10:40:00+05:30", is_high=True, type="LH", strength=2.0, confirmation_index=10, confirmed=True)
    ]
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=0, p1_price=95.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=101.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=1.2, intercept=95.0, end_index=14, end_price=111.0,
        rank="PRIMARY", strength="MAJOR"
    )
    # Candle 12 at index 12: Neckline is 100.0, TL is ~109.4, EMA is 104.0
    # Candle 12 closes at 99.5 < 100.0 (Neck) & < 109.4 (TL) & < 104.0 (EMA), RR = 9.5 / 9.8 = 0.97 >= 0.85
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=101.0, high=101.5, low=99.0, close=99.5, volume=2000)

    df_ind = pd.DataFrame({
        "ema_20": [104.0] * len(candles),
        "atr_14": [2.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 1
    assert breaks[0].event_type == "M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT"
    assert breaks[0].direction == "BEARISH"
    assert breaks[0].broken_level == 100.0

def test_pbreakout_test13_m_neckline_broken_ema_not_broken():
    """
    TEST 13:
    M neckline broken, but EMA not broken.
    Expected: NO ALERT.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=110.0, timestamp="2026-08-25T10:10:00+05:30", is_high=True, type="HH", strength=2.0, confirmation_index=4, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=False, type="HL", strength=2.0, confirmation_index=7, confirmed=True),
        SwingPoint(index=8, price=109.8, timestamp="2026-08-25T10:40:00+05:30", is_high=True, type="LH", strength=2.0, confirmation_index=10, confirmed=True)
    ]
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=0, p1_price=95.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=101.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=1.2, intercept=95.0, end_index=14, end_price=111.0,
        rank="PRIMARY", strength="MAJOR"
    )
    # Candle closes at 98.0 (< 100.0 Neckline), but EMA is 94.0 (> 94.0 EMA)
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=103.0, high=103.5, low=97.0, close=98.0, volume=2000)

    df_ind = pd.DataFrame({
        "ema_20": [94.0] * len(candles),
        "atr_14": [2.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

def test_pbreakout_test14_m_neckline_broken_tl_not_broken():
    """
    TEST 14:
    M neckline broken, Trendline not broken.
    Expected: NO ALERT.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=110.0, timestamp="2026-08-25T10:10:00+05:30", is_high=True, type="HH", strength=2.0, confirmation_index=4, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=False, type="HL", strength=2.0, confirmation_index=7, confirmed=True),
        SwingPoint(index=8, price=109.8, timestamp="2026-08-25T10:40:00+05:30", is_high=True, type="LH", strength=2.0, confirmation_index=10, confirmed=True)
    ]
    # Low ascending line (TL at index 12 is 85.0)
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=0, p1_price=70.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=76.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=1.2, intercept=70.0, end_index=14, end_price=87.0,
        rank="PRIMARY", strength="MAJOR"
    )
    # Candle closes at 96.0 < 100.0 (Neck), but > 84.4 (TL)
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=103.0, high=103.5, low=95.0, close=96.0, volume=2000)

    df_ind = pd.DataFrame({
        "ema_20": [104.0] * len(candles),
        "atr_14": [2.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

def test_pbreakout_test15_m_intrabar_cross_close_returns_above():
    """
    TEST 15:
    Intrabar broke below (Low = 94.0), but Final Close returned to 102.0 (> Neckline 100.0).
    Expected: NO ALERT.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=110.0, timestamp="2026-08-25T10:10:00+05:30", is_high=True, type="HH", strength=2.0, confirmation_index=4, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=False, type="HL", strength=2.0, confirmation_index=7, confirmed=True),
        SwingPoint(index=8, price=109.8, timestamp="2026-08-25T10:40:00+05:30", is_high=True, type="LH", strength=2.0, confirmation_index=10, confirmed=True)
    ]
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=0, p1_price=95.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=101.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=1.2, intercept=95.0, end_index=14, end_price=111.0,
        rank="PRIMARY", strength="MAJOR"
    )
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=103.0, high=104.0, low=94.0, close=102.0, volume=2000)

    df_ind = pd.DataFrame({
        "ema_20": [104.0] * len(candles),
        "atr_14": [2.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

# -------------------------------------------------------------
# MASTER SPECIFICATION SECTION 52: TESTS 1 TO 11
# -------------------------------------------------------------

from app.alerts.high_confluence_engine import HighConfluenceAlertEngine
from app.models.schemas import (
    MultiTimeframeSynthesis,
    SingleTimeframeAnalysis,
    StructureBreakEvent,
    SupportResistanceSummary,
    TechnicalIndicators,
    EvidenceScoreBreakdown
)

def make_test_wm_synthesis(events, score_val=85):
    score = EvidenceScoreBreakdown(
        total_score=score_val,
        category="Strong Evidence Alignment" if score_val >= 75 else "Mixed Evidence",
        structure_points=25,
        htf_alignment_points=25,
        momentum_points=15,
        volume_points=10,
        breakout_points=10,
        details=["W/M Breakout Analysis"]
    )
    analysis = SingleTimeframeAnalysis(
        timeframe="15M",
        trend="BULLISH" if score_val >= 75 else "NEUTRAL",
        structure_type="BULLISH",
        structure_description="Pattern Breakout",
        swings=[],
        recent_events=events,
        support_resistance=SupportResistanceSummary(
            all_levels=[],
            major_support=24000.0,
            minor_support=24100.0,
            minor_resistance=24300.0,
            major_resistance=24400.0,
            current_price=24250.0
        ),
        trendlines=[],
        indicators=TechnicalIndicators(
            rsi_14=60.0,
            ema_20=24180.0,
            relative_volume=1.45,
            atr_14=20.0
        ),
        breakout_status="CONFIRMED BREAKOUT",
        candle_count=50,
        latest_candle_time="2026-08-25T10:45:00+05:30"
    )
    return MultiTimeframeSynthesis(
        symbol="NIFTY 50",
        ticker="^NSEI",
        provider="yfinance",
        data_status="LIVE",
        last_updated="2026-08-25T10:45:00+05:30",
        is_stale=False,
        status_message="Live",
        current_price=24250.0,
        timeframes={"15M": analysis},
        overall_bias="BULLISH",
        current_state="FULL BULLISH ALIGNMENT",
        evidence_score=score,
        confirmation_state="HIGH",
        short_term_state="EXPANDING",
        key_supports=[24000.0, 24100.0],
        key_resistances=[24300.0, 24400.0],
        synthesis_rationale="W/M Analysis"
    )

def test_wm_section52_test1_valid_w_score_85():
    """TEST 1: Valid W, neckline, TL, EMA broken on same candle, Score=85 -> High-confluence alert emitted."""
    hc_engine = HighConfluenceAlertEngine()
    event = StructureBreakEvent(
        id="w_test1",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T10:45:00+05:30",
        event_type="W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=85,
        pattern_id="NIFTY50_15M_W_001",
        pattern_type="W",
        neckline_price=24200.0,
        trendline_level=24180.0,
        ema20_level=24170.0
    )
    synthesis = make_test_wm_synthesis([event], score_val=85)
    alerts = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)

    assert len(alerts) == 1
    assert alerts[0].alert_type == "W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT"
    assert alerts[0].direction == "UP"
    assert alerts[0].breakout_candle_timestamp == "2026-08-25T10:45:00+05:30"
    assert alerts[0].evidence_score == 85

def test_wm_section52_test2_valid_w_score_41_rejected():
    """TEST 2: Valid W, but Score=41 -> REJECTED (Score < 75 threshold)."""
    hc_engine = HighConfluenceAlertEngine()
    event = StructureBreakEvent(
        id="w_test2",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T10:45:00+05:30",
        event_type="W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=41
    )
    synthesis = make_test_wm_synthesis([event], score_val=41)
    alerts = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)
    assert len(alerts) == 0

def test_wm_section52_test7_valid_m_score_84():
    """TEST 7: Valid M, all 3 levels broken on same candle close, Score=84 -> M Alert emitted."""
    hc_engine = HighConfluenceAlertEngine()
    event = StructureBreakEvent(
        id="m_test7",
        symbol="BANK NIFTY",
        timeframe="1H",
        timestamp="2026-08-25T13:00:00+05:30",
        event_type="M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT",
        direction="BEARISH",
        broken_level=57435.0,
        break_price=57300.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=50.0,
        htf_alignment="BEARISH",
        evidence_score=84,
        pattern_id="BANKNIFTY_1H_M_001",
        pattern_type="M",
        neckline_price=57435.0,
        trendline_level=57435.30,
        ema20_level=57460.62
    )
    synthesis = make_test_wm_synthesis([event], score_val=84)
    synthesis.symbol = "BANK NIFTY"
    alerts = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)

    assert len(alerts) == 1
    assert alerts[0].alert_type == "M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT"
    assert alerts[0].direction == "DOWN"
    assert alerts[0].breakout_candle_timestamp == "2026-08-25T13:00:00+05:30"
    assert alerts[0].evidence_score == 84

def test_wm_section52_test8_m_score_33_rejected():
    """TEST 8: M Score = 33 -> REJECTED (Score < 75)."""
    hc_engine = HighConfluenceAlertEngine()
    event = StructureBreakEvent(
        id="m_test8",
        symbol="BANK NIFTY",
        timeframe="1H",
        timestamp="2026-08-25T13:00:00+05:30",
        event_type="M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT",
        direction="BEARISH",
        broken_level=57435.0,
        break_price=57300.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=50.0,
        htf_alignment="BEARISH",
        evidence_score=33
    )
    synthesis = make_test_wm_synthesis([event], score_val=33)
    alerts = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)
    assert len(alerts) == 0

def test_wm_section52_test10_breakout_candle_timestamp_exact():
    """TEST 10: Breakout candle timestamp preserved accurately (NOT event created timestamp)."""
    hc_engine = HighConfluenceAlertEngine()
    candle_time = "2026-08-25T10:45:00+05:30"
    event = StructureBreakEvent(
        id="w_test10",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp=candle_time,
        event_type="W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=85
    )
    synthesis = make_test_wm_synthesis([event], score_val=85)
    alerts = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)

    assert len(alerts) == 1
    assert alerts[0].breakout_candle_timestamp == candle_time
    assert alerts[0].event_created_at is not None

def test_wm_section52_test11_same_pattern_20_times_deduplicated():
    """TEST 11: Same pattern processed 20 times -> exactly ONE alert."""
    hc_engine = HighConfluenceAlertEngine()
    event = StructureBreakEvent(
        id="w_test11",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T10:45:00+05:30",
        event_type="W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=85
    )
    synthesis = make_test_wm_synthesis([event], score_val=85)

    total_emitted = 0
    for _ in range(20):
        emitted = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)
        total_emitted += len(emitted)

    assert total_emitted == 1
    assert len(hc_engine.get_alerts()) == 1

# -------------------------------------------------------------
# MASTER SPECIFICATION SECTION 55: TESTS 1 TO 20
# -------------------------------------------------------------

def test_wm_sec55_test1_two_random_lows_no_w():
    """TEST 1: Two random lows without confirmed swings -> No W."""
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=101, low=99, close=100, volume=1000)
        for i in range(15)
    ]
    # No swings passed
    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=[], trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

def test_wm_sec55_test2_two_random_highs_no_m():
    """TEST 2: Two random highs without confirmed swings -> No M."""
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=101, low=99, close=100, volume=1000)
        for i in range(15)
    ]
    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=[], trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

def test_wm_sec55_test3_insufficient_depth_no_alert():
    """TEST 3: Valid W shape but shallow depth (< 1.0 ATR) -> No alert."""
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    # L1: 99.5, Peak: 100.0, L2: 99.6 -> Depth = 0.4 (< 2.0 ATR when atr=2.0)
    swings = [
        SwingPoint(index=2, price=99.5, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=99.6, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=105.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=98.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=-1.4, intercept=105.0, end_index=14, end_price=85.0
    )
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=97.0, high=105.0, low=97.0, close=104.0, volume=2000)
    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0, min_depth_atr=1.5
    )
    assert len(breaks) == 0

def test_wm_sec55_test4_insufficient_separation_no_alert():
    """TEST 4: Valid W but L1 and L2 only 2 bars apart (< 5 bars) -> No alert."""
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=3, price=100.0, timestamp="2026-08-25T10:15:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=90.2, timestamp="2026-08-25T10:20:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=105.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=3, p2_price=98.0, p2_time="2026-08-25T10:15:00+05:30",
        slope=-1.4, intercept=105.0, end_index=14, end_price=85.0
    )
    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0, min_bar_spacing=5
    )
    assert len(breaks) == 0

def test_wm_sec55_test5_neckline_unclear_no_alert():
    """TEST 5: Two lows but no intermediate reaction peak high -> No alert."""
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=90.2, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

def test_wm_sec55_test6_neckline_broken_intrabar_close_below_no_alert():
    """TEST 6: Intrabar wick breaks neckline (High=105), but candle closes below (Close=98) -> No alert."""
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=90.2, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=105.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=98.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=-1.4, intercept=105.0, end_index=14, end_price=85.0
    )
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=97.0, high=105.0, low=96.0, close=98.0, volume=2000)
    df_ind = pd.DataFrame({"ema_20": [95.0] * len(candles), "atr_14": [2.0] * len(candles)})
    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

def test_wm_sec55_test7_close_above_neckline_below_ema_no_alert():
    """TEST 7: Candle closes above neckline (102 > 100), but below 20 EMA (102 < 106) -> No alert."""
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=90.2, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=105.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=98.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=-1.4, intercept=105.0, end_index=14, end_price=85.0
    )
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=97.0, high=103.0, low=97.0, close=102.0, volume=2000)
    df_ind = pd.DataFrame({"ema_20": [106.0] * len(candles), "atr_14": [2.0] * len(candles)})
    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

def test_wm_sec55_test8_close_above_neckline_and_ema_below_tl_no_alert():
    """TEST 8: Candle closes above neckline and EMA, but below Trendline -> No alert."""
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=90.2, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=130.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=124.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=-1.2, intercept=130.0, end_index=14, end_price=113.0
    )
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=97.0, high=105.0, low=97.0, close=104.0, volume=2000)
    df_ind = pd.DataFrame({"ema_20": [96.0] * len(candles), "atr_14": [2.0] * len(candles)})
    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 0

def test_wm_sec55_test9_same_candle_closes_above_all_three_w_breakout():
    """TEST 9: Same candle closes above Neckline, Trendline, and 20 EMA -> W Breakout."""
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=91.0, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=105.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=98.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=-1.4, intercept=105.0, end_index=14, end_price=85.0
    )
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=99.0, high=101.0, low=98.5, close=100.5, volume=2000)
    df_ind = pd.DataFrame({"ema_20": [96.0] * len(candles), "atr_14": [2.0] * len(candles)})
    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 1
    assert breaks[0].event_type == "W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT"

def test_wm_sec55_test10_w_quality_score_60_no_alert():
    """TEST 10: W breakout with quality score 60 (< 75 threshold) -> No high-confluence alert."""
    hc_engine = HighConfluenceAlertEngine()
    event = StructureBreakEvent(
        id="w_sec55_10",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T10:45:00+05:30",
        event_type="W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=60,
        pattern_quality_score=60
    )
    synthesis = make_test_wm_synthesis([event], score_val=60)
    alerts = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)
    assert len(alerts) == 0

def test_wm_sec55_test11_w_quality_score_85_emits_alert():
    """TEST 11: W breakout with quality score 85 (>= 75) -> High-confluence alert emitted."""
    hc_engine = HighConfluenceAlertEngine()
    event = StructureBreakEvent(
        id="w_sec55_11",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T10:45:00+05:30",
        event_type="W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=85,
        pattern_quality_score=85
    )
    synthesis = make_test_wm_synthesis([event], score_val=85)
    alerts = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)
    assert len(alerts) == 1
    assert alerts[0].pattern_quality_score == 85

def test_wm_sec55_test12_valid_m_all_conditions_m_breakdown():
    """TEST 12: Valid M with all conditions -> M Breakdown."""
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=110.0, timestamp="2026-08-25T10:10:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=109.0, timestamp="2026-08-25T10:40:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=0, p1_price=95.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=101.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=1.2, intercept=95.0, end_index=14, end_price=111.0
    )
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=101.0, high=101.5, low=99.0, close=99.5, volume=2000)
    df_ind = pd.DataFrame({"ema_20": [104.0] * len(candles), "atr_14": [2.0] * len(candles)})
    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 1
    assert breaks[0].event_type == "M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT"
    assert breaks[0].direction == "BEARISH"

def test_wm_sec55_test13_m_breakout_score_40_no_alert():
    """TEST 13: M breakout score 40 -> Rejected from High-Confluence Alerts."""
    hc_engine = HighConfluenceAlertEngine()
    event = StructureBreakEvent(
        id="m_sec55_13",
        symbol="BANK NIFTY",
        timeframe="1H",
        timestamp="2026-08-25T13:00:00+05:30",
        event_type="M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT",
        direction="BEARISH",
        broken_level=57435.0,
        break_price=57300.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=50.0,
        htf_alignment="BEARISH",
        evidence_score=40,
        pattern_quality_score=40
    )
    synthesis = make_test_wm_synthesis([event], score_val=40)
    alerts = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)
    assert len(alerts) == 0

def test_wm_sec55_test14_valid_w_measured_target_calculated():
    """TEST 14: Valid W breakout -> Measured target = Neckline + Height."""
    target_res = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="W",
        s1_price=24500.0,
        s2_price=24520.0,
        neckline_price=24850.0,
        breakout_close=24910.0
    )
    # Height = 24850 - 24500 = 350.0
    # Measured Target = 24850 + 350 = 25200.0
    assert target_res.pattern_height == 350.0
    # Stop Loss = Low 2 - (0.15 * ATR) = 24520 - 0.15 = 24519.85 (strictly below neckline)
    assert target_res.invalidation_level == round(24520.0 - 0.15 * 1.0, 2)
    assert target_res.invalidation_level < target_res.retest_level

def test_wm_sec55_test15_valid_m_measured_target_calculated():
    """TEST 15: Valid M breakout -> Measured target = Neckline - Height."""
    target_res = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="M",
        s1_price=57500.0,
        s2_price=57480.0,
        neckline_price=57435.0,
        breakout_close=57300.0
    )
    # Height = 57500 - 57435 = 65.0
    # Measured Target = 57435 - 65 = 57370.0
    assert target_res.pattern_height == 65.0
    assert target_res.measured_target == 57370.0
    # Stop Loss = High 2 + (0.15 * ATR) = 57480 + 0.15 = 57480.15 (strictly above neckline)
    assert target_res.invalidation_level == round(57480.0 + 0.15 * 1.0, 2)
    assert target_res.invalidation_level > target_res.retest_level

def test_wm_sec55_test16_major_resistance_before_w_target_detected():
    """TEST 16: Major resistance between neckline (24850) and target (25200) -> Detected as nearest obstacle."""
    target_res = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="W",
        s1_price=24500.0,
        s2_price=24520.0,
        neckline_price=24850.0,
        breakout_close=24910.0,
        key_resistances=[25050.0, 25350.0]
    )
    assert target_res.measured_target == 25200.0
    assert target_res.nearest_obstacle == 25050.0
    # Pure measured move: Neckline (24850) + 1.618 * 350 = 25416.3
    assert target_res.target_2 == 25416.3

def test_wm_sec55_test17_major_support_before_m_target_detected():
    """TEST 17: Major support between neckline (57435) and target (57100) -> Detected as nearest obstacle."""
    target_res = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="M",
        s1_price=57770.0,
        s2_price=57750.0,
        neckline_price=57435.0,
        breakout_close=57300.0,
        key_supports=[57250.0, 56900.0]
    )
    # Height = 57770 - 57435 = 335. Target 1 = 57100.
    assert target_res.measured_target == 57100.0
    assert target_res.nearest_obstacle == 57250.0
    # Pure measured move: Neckline (57435) - 1.618 * 335 = 56892.97
    assert target_res.target_2 == 56892.97

def test_wm_sec55_test18_repeated_processing_exactly_one_alert():
    """TEST 18: Breakout event processed repeatedly -> exactly ONE alert emitted."""
    hc_engine = HighConfluenceAlertEngine()
    event = StructureBreakEvent(
        id="sec55_18",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T10:45:00+05:30",
        event_type="W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=85
    )
    synthesis = make_test_wm_synthesis([event], score_val=85)
    for _ in range(50):
        hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)
    assert len(hc_engine.get_alerts()) == 1

def test_wm_sec55_test19_historical_backtest_no_future_leakage():
    """TEST 19: Breakout timestamp strictly matches the breakout candle timestamp (no future lookahead)."""
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=91.0, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=105.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=98.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=-1.4, intercept=105.0, end_index=14, end_price=85.0
    )
    breakout_timestamp = "2026-08-25T11:00:00+05:30"
    candles[12] = Candle(timestamp=breakout_timestamp, open=99.0, high=101.0, low=98.5, close=100.5, volume=2000)
    df_ind = pd.DataFrame({"ema_20": [96.0] * len(candles), "atr_14": [2.0] * len(candles)})

    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(breaks) == 1
    assert breaks[0].timestamp == breakout_timestamp

def test_wm_sec55_test20_pattern_invalidation_handling():
    """TEST 20: Invalidation level is accurately established at previous swing low below structure (never neckline)."""
    target_res = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="W",
        s1_price=24500.0,
        s2_price=24520.0,
        neckline_price=24850.0,
        breakout_close=24910.0
    )
    assert target_res.invalidation_level == round(24520.0 - 0.15 * 1.0, 2)
    assert target_res.invalidation_level < target_res.retest_level
    assert target_res.pattern_status == "CONFIRMED_BREAKOUT"

def test_one_pattern_one_breakout_no_repeating_across_continuous_downtrend():
    """
    CRITICAL TEST:
    A continuous downward movement with 10 candles below neckline + TL + EMA
    MUST produce exactly ONE M breakout event for that pattern, NOT 10 events.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(25)
    ]
    swings = [
        SwingPoint(index=2, price=110.0, timestamp="2026-08-25T10:10:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=109.0, timestamp="2026-08-25T10:40:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=0, p1_price=95.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=5, p2_price=101.0, p2_time="2026-08-25T10:25:00+05:30",
        slope=1.2, intercept=95.0, end_index=24, end_price=123.0
    )
    # First breakdown candle at index 10 closes just below neckline (99.5)
    candles[10] = Candle(
        timestamp="2026-08-25T10:50:00+05:30",
        open=101.0, high=101.5, low=99.0, close=99.5, volume=2000
    )
    # Candles 11 to 20 continue downwards
    for k in range(11, 20):
        candles[k] = Candle(
            timestamp=f"2026-08-25T10:{k*5:02d}:00+05:30",
            open=98.0 - (k - 10),
            high=98.5 - (k - 10),
            low=93.0 - (k - 10),
            close=94.0 - (k - 10),
            volume=2000
        )

    df_ind = pd.DataFrame({
        "ema_20": [104.0] * len(candles),
        "atr_14": [2.0] * len(candles)
    })

    breaks = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )

    assert len(breaks) == 1
    assert breaks[0].event_type == "M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT"
    assert breaks[0].break_candle_index == 10

def test_detect_wm_patterns_asymmetric_highs_detected():
    """
    TEST: Real-world M pattern with asymmetric highs (80,000 vs 79,700 with ATR=300 -> diff 1.0 ATR <= 1.5 ATR).
    Must be successfully detected by the structural engine.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=79500, high=79600, low=79400, close=79500, volume=1000)
        for i in range(25)
    ]
    candles[0] = Candle(timestamp="2026-08-25T10:00:00+05:30", open=78800, high=78900, low=78800, close=78850, volume=1000)
    swings = [
        SwingPoint(index=2, price=80000.0, timestamp="2026-08-25T10:10:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=7, price=79200.0, timestamp="2026-08-25T10:35:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=79880.0, timestamp="2026-08-25T11:10:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=0, p1_price=78800.0, p1_time="2026-08-25T10:00:00+05:30",
        p2_index=7, p2_price=79200.0, p2_time="2026-08-25T10:35:00+05:30",
        slope=57.1, intercept=78800.0, end_index=24, end_price=80200.0
    )
    # Breakout candle at index 18 and subsequent candles below neckline
    for idx in range(18, 25):
        candles[idx] = Candle(
            timestamp=f"2026-08-25T11:{30+(idx-18)*5:02d}:00+05:30",
            open=79180.0, high=79200.0, low=79050.0, close=79120.0, volume=2500
        )
    df_ind = pd.DataFrame({
        "ema_20": [79450.0] * len(candles),
        "atr_14": [300.0] * len(candles)
    })

    events, confirmed, active_pat, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=300.0, price_tolerance_atr=1.50
    )

    assert len(events) == 1
    assert len(confirmed) == 1
    assert active_pat is not None
    assert active_pat.pattern_type == "M"
    assert active_pat.status in ["BREAKOUT_CONFIRMED", "HIGH_CONFLUENCE_CONFIRMED"]
    assert active_pat.s1_price == 80000.0
    assert active_pat.s2_price == 79880.0
    assert active_pat.neckline_price == 79200.0
    assert active_pat.target_analysis is not None
    # Structural Reversal Target 1 = Preceding Trend-Origin Swing Low (78800.0 at index 0)
    assert active_pat.target_analysis.measured_target == 78800.0

def test_detect_wm_patterns_debug_diagnostics_records_rejections():
    """
    TEST: When an M candidate has shallow neckline depth (< 0.80 ATR),
    debug diagnostics records the candidate with an explicit rejection reason.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=100, high=102, low=98, close=100, volume=1000)
        for i in range(20)
    ]
    candles[0] = Candle(timestamp="2026-08-25T10:00:00+05:30", open=95, high=96, low=95, close=96, volume=1000)
    swings = [
        SwingPoint(index=2, price=100.5, timestamp="2026-08-25T10:10:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=100.4, timestamp="2026-08-25T10:40:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    # Depth = 0.4 < 1.6 (0.80 * 2.0 ATR)
    events, confirmed, active_pat, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0, min_depth_atr=0.80
    )

    assert len(confirmed) == 0
    assert active_pat is None
    assert len(debug_cands) >= 1
    assert debug_cands[0].status == "REJECTED"
    assert "Insufficient neckline depth" in (debug_cands[0].rejection_reason or "")


# -------------------------------------------------------------
# SPECIFICATION CRITERIA TESTS (SECTIONS 37 - 40)
# -------------------------------------------------------------

def test_wm_breakout_engine_section37_w_structural_breakout():
    """
    SECTION 37 TEST CASE — W:
    Create a test with LOW1, LOW2, NECKLINE.
    Then create a candle whose close > neckline.
    Expected:
    - W STRUCTURAL BREAKOUT = TRUE.
    - Chart marker: W BREAKOUT ↑ (or W + TL + EMA + VOL ↑).
    - Expected target: neckline + pattern height.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=95, high=97, low=93, close=95, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=90.2, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    # Candle 11 closes above neckline (102.5 > 100.0)
    candles[11] = Candle(timestamp="2026-08-25T10:55:00+05:30", open=98.0, high=103.0, low=97.5, close=102.5, volume=2000)
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=102.5, high=104.0, low=102.0, close=103.0, volume=2000)
    candles[13] = Candle(timestamp="2026-08-25T11:05:00+05:30", open=103.0, high=105.0, low=102.5, close=104.0, volume=2000)

    events, confirmed, active_pat, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0, enforce_precision=False
    )

    assert len(confirmed) == 1
    assert active_pat is not None
    assert active_pat.pattern_type == "W"
    assert active_pat.status in ["BREAKOUT_CONFIRMED", "HIGH_CONFLUENCE_CONFIRMED", "STRUCTURAL_BREAKOUT_CONFIRMED"]
    assert active_pat.breakout_candle_index == 11
    assert active_pat.breakout_close == 102.5
    # Height = Neckline - min(Low1, Low2) = 100.0 - 90.0 = 10.0
    # Target = Neckline + Height = 100.0 + 10.0 = 110.0
    assert active_pat.target_analysis is not None
    assert active_pat.target_analysis.measured_target == 110.0
    assert len(events) >= 1
    assert events[0].event_type in ["W_PATTERN_BREAKOUT", "W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT"]


def test_wm_breakout_engine_section38_m_structural_breakdown():
    """
    SECTION 38 TEST CASE — M:
    Create HIGH1, HIGH2, NECKLINE.
    Then create a candle whose close < neckline.
    Expected:
    - M STRUCTURAL BREAKDOWN = TRUE.
    - Chart marker: M BREAKDOWN ↓ (or M + TL + EMA + VOL ↓).
    - Expected target: neckline - pattern height.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=105, high=107, low=103, close=105, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=110.0, timestamp="2026-08-25T10:10:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=109.8, timestamp="2026-08-25T10:40:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    # Candle 11 closes below neckline (97.5 < 100.0)
    candles[11] = Candle(timestamp="2026-08-25T10:55:00+05:30", open=102.0, high=102.5, low=97.0, close=97.5, volume=2000)
    candles[12] = Candle(timestamp="2026-08-25T11:00:00+05:30", open=97.5, high=98.0, low=96.0, close=97.0, volume=2000)
    candles[13] = Candle(timestamp="2026-08-25T11:05:00+05:30", open=97.0, high=97.5, low=95.5, close=96.0, volume=2000)

    events, confirmed, active_pat, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0, enforce_precision=False
    )

    assert len(confirmed) == 1
    assert active_pat is not None
    assert active_pat.pattern_type == "M"
    assert active_pat.status in ["BREAKOUT_CONFIRMED", "HIGH_CONFLUENCE_CONFIRMED", "STRUCTURAL_BREAKDOWN_CONFIRMED"]
    assert active_pat.breakout_candle_index == 11
    assert active_pat.breakout_close == 97.5
    # Height = max(High1, High2) - Neckline = 110.0 - 100.0 = 10.0
    # Target = Neckline - Height = 100.0 - 10.0 = 90.0
    assert active_pat.target_analysis is not None
    assert active_pat.target_analysis.measured_target == 90.0
    assert len(events) >= 1
    assert events[0].event_type in ["M_PATTERN_BREAKDOWN", "M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT"]


def test_wm_breakout_engine_section39_intrabar_forming_no_confirmed_breakout():
    """
    SECTION 39 TEST CASE — INTRABAR:
    Price moves above W neckline on active open candle (last candle).
    Expected:
    - NO CONFIRMED BREAKOUT.
    - Pattern status: BREAKOUT_FORMING.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=95, high=97, low=93, close=95, volume=1000)
        for i in range(12)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=90.2, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    # Candle 9 and 10 remain below neckline (97.0 < 100.0)
    candles[9] = Candle(timestamp="2026-08-25T10:45:00+05:30", open=91.0, high=96.0, low=91.0, close=95.0, volume=1000)
    candles[10] = Candle(timestamp="2026-08-25T10:50:00+05:30", open=95.0, high=98.0, low=94.5, close=97.0, volume=1000)
    # Candle 11 (the LAST/active candle) is currently spiking above neckline to 103.0
    candles[11] = Candle(timestamp="2026-08-25T10:55:00+05:30", open=97.0, high=103.0, low=97.0, close=102.5, volume=2000)

    events, confirmed, active_pat, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0, enforce_precision=False
    )

    assert active_pat is not None
    assert active_pat.status == "BREAKOUT_FORMING"
    assert active_pat.breakout_candle_index is None
    # No confirmed breakout events while bar is still unclosed/open
    assert len(events) == 0


def test_wm_breakout_engine_section40_structural_only_not_hidden():
    """
    SECTION 40 TEST CASE — STRUCTURAL ONLY NOT HIDDEN:
    Price closes above W neckline (102 > 100).
    EMA condition fails (EMA = 106.0 > 102.0).
    Expected:
    - W STRUCTURAL BREAKOUT is confirmed and event is created.
    - Not high-confluence alert (filtered from high-confluence wrapper).
    - Chart still receives W BREAKOUT event.
    """
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00+05:30", open=95, high=97, low=93, close=95, volume=1000)
        for i in range(15)
    ]
    swings = [
        SwingPoint(index=2, price=90.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=90.2, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    # Candles 11-14 close above neckline
    for idx in range(11, 15):
        candles[idx] = Candle(
            timestamp=f"2026-08-25T11:{(idx-11)*5:02d}:00+05:30",
            open=101.0, high=103.0, low=100.5, close=102.0, volume=2000
        )

    # EMA is above price (106.0)
    df_ind = pd.DataFrame({
        "ema_20": [106.0] * len(candles),
        "atr_14": [2.0] * len(candles)
    })

    events, confirmed, active_pat, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0, enforce_precision=False
    )

    # Structural breakout is created!
    assert len(confirmed) == 1
    assert active_pat is not None
    assert active_pat.status == "BREAKOUT_CONFIRMED"
    assert active_pat.breakout_candle_index == 11
    assert active_pat.target_analysis is not None
    assert active_pat.target_analysis.measured_target == 110.0
    assert len(events) == 1
    assert events[0].event_type == "W_PATTERN_BREAKOUT"

    # High-confluence alert wrapper filters it out
    high_conf_events = PrecisionBreakoutDetector.detect_wm_pattern_trendline_ema_breakouts(
        candles=candles, swings=swings, trendlines=[], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=2.0
    )
    assert len(high_conf_events) == 0



