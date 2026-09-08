import pytest
import pandas as pd
from app.models.schemas import Candle, SwingPoint
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector


def test_w_genuine_bearish_preceding_structure_accepted():
    atr = 2.0
    candles = [
        Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=140 - i*2, high=142 - i*2, low=138 - i*2, close=139 - i*2, volume=1000)
        for i in range(10)
    ]
    candles[9] = Candle(timestamp='2026-08-25T10:45:00Z', open=105, high=106, low=100, close=101, volume=1000)
    for i in range(10, 30):
        candles.append(Candle(timestamp=f'2026-08-25T11:{i*2:02d}:00Z', open=110, high=115, low=105, close=110, volume=1000))
    candles[24] = Candle(timestamp='2026-08-25T11:48:00Z', open=117, high=121, low=116, close=119.5, volume=2500)

    swings = [
        SwingPoint(index=0, price=140.0, timestamp='2026-08-25T10:00:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=2, price=120.0, timestamp='2026-08-25T10:10:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=4, price=130.0, timestamp='2026-08-25T10:20:00Z', is_high=True, type='LH', strength=2.0, confirmed=True),
        SwingPoint(index=6, price=110.0, timestamp='2026-08-25T10:30:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=8, price=122.0, timestamp='2026-08-25T10:40:00Z', is_high=True, type='LH', strength=2.0, confirmed=True),
        SwingPoint(index=9, price=100.0, timestamp='2026-08-25T10:45:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=14, price=118.0, timestamp='2026-08-25T11:28:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=19, price=101.0, timestamp='2026-08-25T11:38:00Z', is_high=False, type='HL', strength=2.0, confirmed=True)
    ]
    df_ind = pd.DataFrame({'ema_20': [112.0] * len(candles), 'atr_14': [2.0] * len(candles)})

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=df_ind,
        symbol='GENERIC_SYM', timeframe='15M', atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].pattern_type == 'W'
    assert confirmed[0].breakout_status == 'CONFIRMED'
    assert confirmed[0].s1_price == 100.0


def test_w_bullish_hh_hl_pullback_continuation_rejected():
    atr = 2.0
    candles = [
        Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=100 + i*3, high=102 + i*3, low=98 + i*3, close=101 + i*3, volume=1000)
        for i in range(30)
    ]
    swings = [
        SwingPoint(index=2, price=100.0, timestamp='2026-08-25T10:10:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=5, price=130.0, timestamp='2026-08-25T10:25:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=8, price=120.0, timestamp='2026-08-25T10:40:00Z', is_high=False, type='HL', strength=2.0, confirmed=True),
        SwingPoint(index=12, price=155.0, timestamp='2026-08-25T11:00:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=15, price=140.0, timestamp='2026-08-25T11:15:00Z', is_high=False, type='HL', strength=2.0, confirmed=True),
        SwingPoint(index=18, price=175.0, timestamp='2026-08-25T11:30:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=20, price=132.0, timestamp='2026-08-25T11:40:00Z', is_high=False, type='HL', strength=2.0, confirmed=True),
        SwingPoint(index=23, price=138.0, timestamp='2026-08-25T11:55:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=27, price=133.0, timestamp='2026-08-25T12:15:00Z', is_high=False, type='HL', strength=2.0, confirmed=True)
    ]
    candles[28] = Candle(timestamp='2026-08-25T12:20:00Z', open=135, high=140, low=134, close=139, volume=2500)

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol='GENERIC_SYM', timeframe='15M', atr_val=atr
    )
    assert len(confirmed) == 0, 'Bullish continuation W must not be confirmed'
    w_rejs = [c for c in debug_cands if c.pattern_type == 'W' and c.s1_index == 20]
    assert len(w_rejs) >= 1
    assert 'BULLISH_CONTINUATION_NOT_REVERSAL' in w_rejs[0].rejection_reason or 'bullish' in w_rejs[0].rejection_reason.lower()


def test_w_insufficient_preceding_bearish_structure_rejected():
    atr = 2.0
    swings = [
        SwingPoint(index=2, price=105.0, timestamp='2026-08-25T10:10:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp='2026-08-25T10:25:00Z', is_high=False, type='LL', strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=105, high=106, low=104, close=105, volume=1000) for i in range(10)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=swings[1], atr_val=atr, timeframe='15M'
    )
    assert regime == 'UNCLEAR'
    assert 'INSUFFICIENT_PREVIOUS_STRUCTURE_NOT_REVERSAL' in reason


def test_w_displacement_alone_without_bearish_structure_rejected():
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=100.0, timestamp='2026-08-25T10:05:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=3, price=130.0, timestamp='2026-08-25T10:15:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=5, price=120.0, timestamp='2026-08-25T10:25:00Z', is_high=False, type='HL', strength=2.0, confirmed=True),
        SwingPoint(index=7, price=150.0, timestamp='2026-08-25T10:35:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=10, price=122.0, timestamp='2026-08-25T10:50:00Z', is_high=False, type='HL', strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=130, high=135, low=125, close=130, volume=1000) for i in range(15)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=swings[4], atr_val=atr, timeframe='15M'
    )
    assert regime == 'BULLISH'
    is_valid, rej_reason = PrecisionBreakoutDetector._validate_reversal_context(
        candles=candles, swings=swings, point_1=swings[4], pattern_type='W', atr_val=atr, timeframe='15M'
    )
    assert not is_valid
    assert rej_reason == 'BULLISH_CONTINUATION_NOT_REVERSAL'


def test_m_genuine_bullish_preceding_structure_accepted():
    atr = 2.0
    candles = [
        Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=160 + i*2, high=162 + i*2, low=158 + i*2, close=161 + i*2, volume=1000)
        for i in range(10)
    ]
    candles[9] = Candle(timestamp='2026-08-25T10:45:00Z', open=195, high=200, low=194, close=199, volume=1000)
    for i in range(10, 30):
        candles.append(Candle(timestamp=f'2026-08-25T11:{i*2:02d}:00Z', open=190, high=195, low=185, close=190, volume=1000))
    candles[24] = Candle(timestamp='2026-08-25T11:48:00Z', open=183, high=184, low=179, close=180.5, volume=2500)

    swings = [
        SwingPoint(index=0, price=160.0, timestamp='2026-08-25T10:00:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=2, price=175.0, timestamp='2026-08-25T10:10:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=4, price=170.0, timestamp='2026-08-25T10:20:00Z', is_high=False, type='HL', strength=2.0, confirmed=True),
        SwingPoint(index=6, price=185.0, timestamp='2026-08-25T10:30:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=8, price=180.0, timestamp='2026-08-25T10:40:00Z', is_high=False, type='HL', strength=2.0, confirmed=True),
        SwingPoint(index=9, price=200.0, timestamp='2026-08-25T10:45:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=14, price=182.0, timestamp='2026-08-25T11:28:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=19, price=199.0, timestamp='2026-08-25T11:38:00Z', is_high=True, type='LH', strength=2.0, confirmed=True)
    ]
    df_ind = pd.DataFrame({'ema_20': [186.0] * len(candles), 'atr_14': [2.0] * len(candles)})

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=df_ind,
        symbol='GENERIC_SYM', timeframe='1H', atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].pattern_type == 'M'
    assert confirmed[0].breakout_status == 'CONFIRMED'
    assert confirmed[0].s1_price == 200.0


def test_m_bearish_ll_lh_relief_rally_continuation_rejected():
    atr = 2.0
    candles = [
        Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=200 - i*3, high=202 - i*3, low=198 - i*3, close=199 - i*3, volume=1000)
        for i in range(30)
    ]
    swings = [
        SwingPoint(index=2, price=200.0, timestamp='2026-08-25T10:10:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=5, price=170.0, timestamp='2026-08-25T10:25:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=8, price=180.0, timestamp='2026-08-25T10:40:00Z', is_high=True, type='LH', strength=2.0, confirmed=True),
        SwingPoint(index=12, price=145.0, timestamp='2026-08-25T11:00:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=15, price=155.0, timestamp='2026-08-25T11:15:00Z', is_high=True, type='LH', strength=2.0, confirmed=True),
        SwingPoint(index=18, price=105.0, timestamp='2026-08-25T11:30:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=20, price=115.0, timestamp='2026-08-25T11:40:00Z', is_high=True, type='LH', strength=2.0, confirmed=True),
        SwingPoint(index=23, price=108.0, timestamp='2026-08-25T11:55:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=27, price=114.0, timestamp='2026-08-25T12:15:00Z', is_high=True, type='LH', strength=2.0, confirmed=True)
    ]
    candles[28] = Candle(timestamp='2026-08-25T12:20:00Z', open=109, high=110, low=104, close=105, volume=2500)

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol='GENERIC_SYM', timeframe='1H', atr_val=atr
    )
    assert len(confirmed) == 0, 'Bearish continuation M must not be confirmed'
    m_rejs = [c for c in debug_cands if c.pattern_type == 'M' and c.s1_index == 20]
    assert len(m_rejs) >= 1
    assert 'BEARISH_CONTINUATION_NOT_REVERSAL' in m_rejs[0].rejection_reason or 'bearish' in m_rejs[0].rejection_reason.lower()


def test_m_insufficient_preceding_bullish_structure_rejected():
    atr = 2.0
    swings = [
        SwingPoint(index=2, price=195.0, timestamp='2026-08-25T10:10:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=5, price=200.0, timestamp='2026-08-25T10:25:00Z', is_high=True, type='HH', strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=195, high=196, low=194, close=195, volume=1000) for i in range(10)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=swings[1], atr_val=atr, timeframe='15M'
    )
    assert regime == 'UNCLEAR'
    assert 'INSUFFICIENT_PREVIOUS_STRUCTURE_NOT_REVERSAL' in reason


def test_m_displacement_alone_without_bullish_structure_rejected():
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=200.0, timestamp='2026-08-25T10:05:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=3, price=170.0, timestamp='2026-08-25T10:15:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=5, price=180.0, timestamp='2026-08-25T10:25:00Z', is_high=True, type='LH', strength=2.0, confirmed=True),
        SwingPoint(index=7, price=140.0, timestamp='2026-08-25T10:35:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=10, price=172.0, timestamp='2026-08-25T10:50:00Z', is_high=True, type='LH', strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=160, high=165, low=155, close=160, volume=1000) for i in range(15)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=swings[4], atr_val=atr, timeframe='15M'
    )
    assert regime == 'BEARISH'
    is_valid, rej_reason = PrecisionBreakoutDetector._validate_reversal_context(
        candles=candles, swings=swings, point_1=swings[4], pattern_type='M', atr_val=atr, timeframe='15M'
    )
    assert not is_valid
    assert rej_reason == 'BEARISH_CONTINUATION_NOT_REVERSAL'


def test_session_boundary_isolation_intraday():
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=100.0, timestamp='2026-08-24T14:00:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=3, price=120.0, timestamp='2026-08-24T14:30:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=5, price=125.0, timestamp='2026-08-25T09:20:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=7, price=115.0, timestamp='2026-08-25T09:35:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=9, price=120.0, timestamp='2026-08-25T09:50:00Z', is_high=True, type='LH', strength=2.0, confirmed=True),
        SwingPoint(index=11, price=105.0, timestamp='2026-08-25T10:05:00Z', is_high=False, type='LL', strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f'2026-08-25T09:{i*5:02d}:00Z', open=120, high=125, low=115, close=120, volume=1000) for i in range(15)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=swings[5], atr_val=atr, timeframe='5M'
    )
    assert regime == 'BEARISH'


def test_insufficient_historical_swings_boundary_rejected():
    atr = 2.0
    swings = [SwingPoint(index=0, price=100.0, timestamp='2026-08-25T10:00:00Z', is_high=False, type='LL', strength=2.0, confirmed=True)]
    candles = []

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=swings[0], atr_val=atr, timeframe='5M'
    )
    assert regime == 'UNCLEAR'
    assert 'INSUFFICIENT_PREVIOUS_STRUCTURE_NOT_REVERSAL' in reason


def test_equal_pivots_noisy_sideways_structure_rejected():
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=100.1, timestamp='2026-08-25T10:05:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=3, price=99.8, timestamp='2026-08-25T10:15:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.2, timestamp='2026-08-25T10:25:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=7, price=99.9, timestamp='2026-08-25T10:35:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=9, price=99.85, timestamp='2026-08-25T10:45:00Z', is_high=False, type='LL', strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=100, high=100.3, low=99.7, close=100, volume=1000) for i in range(12)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=swings[4], atr_val=atr, timeframe='5M'
    )
    assert regime == 'SIDEWAYS'
    is_valid, rej_reason = PrecisionBreakoutDetector._validate_reversal_context(
        candles=candles, swings=swings, point_1=swings[4], pattern_type='W', atr_val=atr, timeframe='5M'
    )
    assert not is_valid
    assert rej_reason == 'SIDEWAYS_NOT_REVERSAL'


def test_multi_instrument_invariant_scaling():
    btc_swings = [
        SwingPoint(index=1, price=62000.0, timestamp='2026-08-25T10:05:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=3, price=60500.0, timestamp='2026-08-25T10:15:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=5, price=61500.0, timestamp='2026-08-25T10:25:00Z', is_high=True, type='LH', strength=2.0, confirmed=True),
        SwingPoint(index=7, price=59800.0, timestamp='2026-08-25T10:35:00Z', is_high=False, type='LL', strength=2.0, confirmed=True)
    ]
    btc_candles = [Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=61000, high=61500, low=60500, close=61000, volume=1000) for i in range(10)]
    regime_btc, _ = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=btc_candles, swings=btc_swings, point_1=btc_swings[3], atr_val=500.0, timeframe='1H'
    )
    assert regime_btc == 'BEARISH'

    stock_swings = [
        SwingPoint(index=1, price=55.0, timestamp='2026-08-25T10:05:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=3, price=52.0, timestamp='2026-08-25T10:15:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=5, price=53.5, timestamp='2026-08-25T10:25:00Z', is_high=True, type='LH', strength=2.0, confirmed=True),
        SwingPoint(index=7, price=50.0, timestamp='2026-08-25T10:35:00Z', is_high=False, type='LL', strength=2.0, confirmed=True)
    ]
    stock_candles = [Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=53, high=54, low=52, close=53, volume=1000) for i in range(10)]
    regime_stock, _ = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=stock_candles, swings=stock_swings, point_1=stock_swings[3], atr_val=0.8, timeframe='15M'
    )
    assert regime_stock == 'BEARISH'


def test_fast_path_and_macro_path_reversal_enforcement():
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=100.0, timestamp='2026-08-25T10:05:00Z', is_high=False, type='LL', strength=2.0, confirmed=True),
        SwingPoint(index=3, price=120.0, timestamp='2026-08-25T10:15:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=5, price=110.0, timestamp='2026-08-25T10:25:00Z', is_high=False, type='HL', strength=2.0, confirmed=True),
        SwingPoint(index=7, price=130.0, timestamp='2026-08-25T10:35:00Z', is_high=True, type='HH', strength=2.0, confirmed=True),
        SwingPoint(index=9, price=115.0, timestamp='2026-08-25T10:45:00Z', is_high=False, type='HL', strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f'2026-08-25T10:{i*5:02d}:00Z', open=120, high=125, low=114, close=120, volume=1000) for i in range(20)]

    is_valid_macro, reason_macro = PrecisionBreakoutDetector._validate_reversal_context(
        candles=candles, swings=swings, point_1=swings[4], pattern_type='W', atr_val=atr, timeframe='5M'
    )
    assert not is_valid_macro
    assert reason_macro == 'BULLISH_CONTINUATION_NOT_REVERSAL'

    is_valid_fast, reason_fast = PrecisionBreakoutDetector._validate_reversal_context(
        candles=candles, swings=swings, point_1=swings[4], pattern_type='W', atr_val=atr, timeframe='5M'
    )
    assert not is_valid_fast
    assert reason_fast == 'BULLISH_CONTINUATION_NOT_REVERSAL'


def test_w_asymmetric_2hh_1l_deep_pullback_rejected():
    """W Asymmetric: 2 HH + 1 prior low + deep pullback below prior low MUST NOT be accepted as BEARISH."""
    atr = 2.0
    swings = [
        SwingPoint(index=0, price=100.0, timestamp='2026-08-25T10:00:00Z', is_high=True, type='HH', confirmed=True),
        SwingPoint(index=5, price=95.0, timestamp='2026-08-25T10:05:00Z', is_high=False, type='HL', confirmed=True),
        SwingPoint(index=10, price=110.0, timestamp='2026-08-25T10:10:00Z', is_high=True, type='HH', confirmed=True),
    ]
    p1 = SwingPoint(index=15, price=90.0, timestamp='2026-08-25T10:15:00Z', is_high=False, type='LL', confirmed=True)
    candles = [Candle(timestamp=f'2026-08-25T10:{i:02d}:00Z', open=100, high=101, low=99, close=100, volume=1000) for i in range(25)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=p1, atr_val=atr, timeframe='15M'
    )
    assert regime != 'BEARISH', f'Deep pullback in 2-HH uptrend must not be BEARISH: {reason}'
    is_valid, v_reason = PrecisionBreakoutDetector._validate_reversal_context(
        candles=candles, swings=swings, point_1=p1, pattern_type='W', atr_val=atr, timeframe='15M'
    )
    assert not is_valid, 'Deep pullback in 2-HH uptrend must not pass W reversal validation'


def test_w_asymmetric_2hh_1l_normal_pullback_rejected():
    """W Asymmetric: 2 HH + 1 prior low + normal bullish pullback MUST reject as continuation."""
    atr = 2.0
    swings = [
        SwingPoint(index=0, price=100.0, timestamp='2026-08-25T10:00:00Z', is_high=True, type='HH', confirmed=True),
        SwingPoint(index=5, price=95.0, timestamp='2026-08-25T10:05:00Z', is_high=False, type='HL', confirmed=True),
        SwingPoint(index=10, price=110.0, timestamp='2026-08-25T10:10:00Z', is_high=True, type='HH', confirmed=True),
    ]
    p1 = SwingPoint(index=15, price=98.0, timestamp='2026-08-25T10:15:00Z', is_high=False, type='HL', confirmed=True)
    candles = [Candle(timestamp=f'2026-08-25T10:{i:02d}:00Z', open=100, high=101, low=99, close=100, volume=1000) for i in range(25)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=p1, atr_val=atr, timeframe='15M'
    )
    assert regime == 'BULLISH'
    is_valid, v_reason = PrecisionBreakoutDetector._validate_reversal_context(
        candles=candles, swings=swings, point_1=p1, pattern_type='W', atr_val=atr, timeframe='15M'
    )
    assert not is_valid
    assert v_reason == 'BULLISH_CONTINUATION_NOT_REVERSAL'


def test_w_asymmetric_1h_2ll_genuine_reversal_accepted():
    """W Asymmetric: 1 High + 2 Lows making Lower Lows should be accepted as genuine bearish reversal."""
    atr = 2.0
    swings = [
        SwingPoint(index=0, price=120.0, timestamp='2026-08-25T10:00:00Z', is_high=False, type='LL', confirmed=True),
        SwingPoint(index=5, price=125.0, timestamp='2026-08-25T10:05:00Z', is_high=True, type='HH', confirmed=True),
        SwingPoint(index=10, price=110.0, timestamp='2026-08-25T10:10:00Z', is_high=False, type='LL', confirmed=True),
    ]
    p1 = SwingPoint(index=15, price=100.0, timestamp='2026-08-25T10:15:00Z', is_high=False, type='LL', confirmed=True)
    candles = [Candle(timestamp=f'2026-08-25T10:{i:02d}:00Z', open=100, high=101, low=99, close=100, volume=1000) for i in range(25)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=p1, atr_val=atr, timeframe='15M'
    )
    assert regime == 'BEARISH'
    is_valid, v_reason = PrecisionBreakoutDetector._validate_reversal_context(
        candles=candles, swings=swings, point_1=p1, pattern_type='W', atr_val=atr, timeframe='15M'
    )
    assert is_valid
    assert v_reason == 'OK'


def test_m_asymmetric_2ll_1h_strong_rally_rejected():
    """M Asymmetric: 2 LL + 1 prior high + strong rally above prior high MUST NOT be accepted as BULLISH."""
    atr = 2.0
    swings = [
        SwingPoint(index=0, price=100.0, timestamp='2026-08-25T10:00:00Z', is_high=False, type='LL', confirmed=True),
        SwingPoint(index=5, price=105.0, timestamp='2026-08-25T10:05:00Z', is_high=True, type='LH', confirmed=True),
        SwingPoint(index=10, price=90.0, timestamp='2026-08-25T10:10:00Z', is_high=False, type='LL', confirmed=True),
    ]
    p1 = SwingPoint(index=15, price=110.0, timestamp='2026-08-25T10:15:00Z', is_high=True, type='HH', confirmed=True)
    candles = [Candle(timestamp=f'2026-08-25T10:{i:02d}:00Z', open=100, high=101, low=99, close=100, volume=1000) for i in range(25)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=p1, atr_val=atr, timeframe='15M'
    )
    assert regime != 'BULLISH', f'Strong rally in 2-LL downtrend must not be BULLISH: {reason}'
    is_valid, v_reason = PrecisionBreakoutDetector._validate_reversal_context(
        candles=candles, swings=swings, point_1=p1, pattern_type='M', atr_val=atr, timeframe='15M'
    )
    assert not is_valid, 'Strong rally in 2-LL downtrend must not pass M reversal validation'


def test_m_asymmetric_2ll_1h_normal_relief_rally_rejected():
    """M Asymmetric: 2 LL + 1 prior high + normal relief rally MUST reject as continuation."""
    atr = 2.0
    swings = [
        SwingPoint(index=0, price=100.0, timestamp='2026-08-25T10:00:00Z', is_high=False, type='LL', confirmed=True),
        SwingPoint(index=5, price=105.0, timestamp='2026-08-25T10:05:00Z', is_high=True, type='LH', confirmed=True),
        SwingPoint(index=10, price=90.0, timestamp='2026-08-25T10:10:00Z', is_high=False, type='LL', confirmed=True),
    ]
    p1 = SwingPoint(index=15, price=98.0, timestamp='2026-08-25T10:15:00Z', is_high=True, type='LH', confirmed=True)
    candles = [Candle(timestamp=f'2026-08-25T10:{i:02d}:00Z', open=100, high=101, low=99, close=100, volume=1000) for i in range(25)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=p1, atr_val=atr, timeframe='15M'
    )
    assert regime == 'BEARISH'
    is_valid, v_reason = PrecisionBreakoutDetector._validate_reversal_context(
        candles=candles, swings=swings, point_1=p1, pattern_type='M', atr_val=atr, timeframe='15M'
    )
    assert not is_valid
    assert v_reason == 'BEARISH_CONTINUATION_NOT_REVERSAL'


def test_m_asymmetric_1l_2hh_genuine_reversal_accepted():
    """M Asymmetric: 1 Low + 2 Highs making Higher Highs should be accepted as genuine bullish reversal."""
    atr = 2.0
    swings = [
        SwingPoint(index=0, price=80.0, timestamp='2026-08-25T10:00:00Z', is_high=True, type='HH', confirmed=True),
        SwingPoint(index=5, price=75.0, timestamp='2026-08-25T10:05:00Z', is_high=False, type='LL', confirmed=True),
        SwingPoint(index=10, price=90.0, timestamp='2026-08-25T10:10:00Z', is_high=True, type='HH', confirmed=True),
    ]
    p1 = SwingPoint(index=15, price=100.0, timestamp='2026-08-25T10:15:00Z', is_high=True, type='HH', confirmed=True)
    candles = [Candle(timestamp=f'2026-08-25T10:{i:02d}:00Z', open=100, high=101, low=99, close=100, volume=1000) for i in range(25)]

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=p1, atr_val=atr, timeframe='15M'
    )
    assert regime == 'BULLISH'
    is_valid, v_reason = PrecisionBreakoutDetector._validate_reversal_context(
        candles=candles, swings=swings, point_1=p1, pattern_type='M', atr_val=atr, timeframe='15M'
    )
    assert is_valid
    assert v_reason == 'OK'

