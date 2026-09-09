"""
Generalized W/M Pattern Recognition Test Suite (16 Core Scenarios: A to P)
========================================================================
Validates that the W/M pattern recognition engine:
1. Accurately identifies structural double bottoms (W) and double tops (M).
2. Decouples market structure recognition from trade-quality/entry filtering.
3. Causal & completed candle confirmation with zero look-ahead.
4. Robust against volatility, asymmetry, noise, and liquidity sweeps.
5. Rejects non-reversal continuation (Pattern 2 W and Pattern 4 M) and multi-wave structures.
"""

import pytest
import pandas as pd
from app.models.schemas import Candle, SwingPoint
from app.market_structure.trendlines import Trendline
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.core.config import settings


def test_scenario_a_asymmetric_w_shallower_second_leg():
    """Scenario A: Asymmetric W (shallower second leg / higher Low 2)."""
    atr = 2.0
    # L1 at 100.0, Mid Peak at 120.0 (Height = 20), L2 at 102.0 (Diff = 2.0 = 1.0 ATR)
    swings = [
        SwingPoint(index=1, price=130.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=120.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=102.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=118, high=123, low=117, close=122, volume=2000)

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="NIFTY", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].pattern_type == "W"
    assert confirmed[0].breakout_status == "CONFIRMED"
    assert confirmed[0].s1_price == 100.0
    assert confirmed[0].s2_price == 102.0


def test_scenario_b_asymmetric_m_shallower_second_leg():
    """Scenario B: Asymmetric M (shallower second leg / lower High 2)."""
    atr = 2.0
    # H1 at 200.0, Mid Trough at 180.0 (Height = 20), H2 at 198.0 (Diff = 2.0 = 1.0 ATR)
    swings = [
        SwingPoint(index=1, price=170.0, timestamp="2026-08-25T10:05:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=200.0, timestamp="2026-08-25T10:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=180.0, timestamp="2026-08-25T10:50:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=198.0, timestamp="2026-08-25T11:15:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=190, high=195, low=185, close=190, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=182, high=183, low=176, close=178, volume=2000)

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="NIFTY", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].pattern_type == "M"
    assert confirmed[0].breakout_status == "CONFIRMED"
    assert confirmed[0].s1_price == 200.0
    assert confirmed[0].s2_price == 198.0


def test_scenario_c_lower_second_bottom_w_liquidity_sweep():
    """Scenario C: Lower second bottom W (marginal liquidity sweep within bounded ATR)."""
    atr = 2.0
    # L1 at 100.0, Mid Peak at 120.0, L2 at 98.6 (Overshoot = 1.4 <= min(1.0*ATR, 0.25*Height = 2.0))
    swings = [
        SwingPoint(index=1, price=130.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=120.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=98.6, timestamp="2026-08-25T11:15:00Z", is_high=False, type="LL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=118, high=123, low=117, close=122, volume=2000)

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="INFY", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].pattern_type == "W"
    assert confirmed[0].s2_price == 98.6


def test_scenario_d_higher_second_top_m_liquidity_sweep():
    """Scenario D: Higher second top M (marginal liquidity sweep within bounded ATR)."""
    atr = 2.0
    # H1 at 200.0, Mid Trough at 180.0, H2 at 201.4 (Overshoot = 1.4 <= 2.0 ATR)
    swings = [
        SwingPoint(index=1, price=170.0, timestamp="2026-08-25T10:05:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=200.0, timestamp="2026-08-25T10:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=180.0, timestamp="2026-08-25T10:50:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=201.4, timestamp="2026-08-25T11:15:00Z", is_high=True, type="HH", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=190, high=195, low=185, close=190, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=182, high=183, low=176, close=178, volume=2000)

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="RELIANCE", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].pattern_type == "M"
    assert confirmed[0].s2_price == 201.4


def test_scenario_e_shallow_second_leg_retest():
    """Scenario E: Shallow second leg retest is recognized when depth >= 0.70 ATR."""
    atr = 2.0
    # Depth = 1.8 ATR (3.6 pts), Retest leg = 1.8 pts >= 0.35*ATR
    swings = [
        SwingPoint(index=1, price=110.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=103.6, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=100.5, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=102, high=103, low=101, close=102, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=103, high=105, low=102.5, close=104.2, volume=2000)

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TCS", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].pattern_type == "W"


def test_scenario_f_noisy_reaction_zone_clustered():
    """Scenario F: Noisy reaction zone with micro-fluctuations clustered into true reaction neckline."""
    atr = 2.0
    # H1 at 1900, two reaction lows at 1880.0 (idx 8) and 1880.3 (idx 10), H2 at 1899.0 (idx 15)
    swings = [
        SwingPoint(index=1, price=1860.0, timestamp="2026-08-25T10:05:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=1900.0, timestamp="2026-08-25T10:20:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=1880.0, timestamp="2026-08-25T10:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=1880.3, timestamp="2026-08-25T10:50:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=1899.0, timestamp="2026-08-25T11:15:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=1885, high=1890, low=1880, close=1885, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=1882, high=1883, low=1876, close=1878, volume=2500)

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="BHARTIARTL", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 1
    assert confirmed[0].pattern_type == "M"
    assert confirmed[0].neckline_price == 1880.0


def test_scenario_g_genuine_multi_wave_structure_rejected():
    """Scenario G: Genuine multi-wave structure with independent deep intervening wave is rejected."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=100.0, timestamp="2026-08-25T10:05:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=130.0, timestamp="2026-08-25T10:20:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),  # H1
        SwingPoint(index=8, price=110.0, timestamp="2026-08-25T10:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),  # Mid trough
        SwingPoint(index=12, price=128.0, timestamp="2026-08-25T11:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True), # Deep inter high (90% retracement)
        SwingPoint(index=16, price=112.0, timestamp="2026-08-25T11:20:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=20, price=129.0, timestamp="2026-08-25T11:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)  # H2
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=120, high=125, low=115, close=120, volume=1000) for i in range(25)]
    candles[23] = Candle(timestamp="2026-08-25T11:55:00Z", open=115, high=116, low=108, close=109, volume=2000)

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TEST", timeframe="15M", atr_val=atr
    )
    # The H1(130) -> H2(129) pair with intervening peak at 128 must be rejected as multi-wave
    macro_cand = next((c for c in debug_cands if c.s1_price == 130.0 and c.s2_price == 129.0), None)
    assert macro_cand is not None
    assert macro_cand.status == "REJECTED"
    assert "multi-wave" in macro_cand.rejection_reason


def test_scenario_h_strong_breakout_candle_overextended():
    """Scenario H: Strong breakout candle confirmed, marked with entry_status = OVEREXTENDED."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=130.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=110.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=101.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    # Height = 10.0. Breakout candle closes at 119.0 (> 110 + 0.75 * 10 = 117.5) -> Overextended
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=105, high=108, low=103, close=105, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=109, high=120, low=108, close=119, volume=3000)

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="NIFTY", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].breakout_status == "CONFIRMED"
    assert confirmed[0].entry_status == "OVEREXTENDED"


def test_scenario_i_poor_risk_reward_decoupled():
    """Scenario I: Poor R:R (< 0.85) confirmed as valid market structure, marked entry_status = POOR_RR."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=120.5, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=110.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=99.5, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    # Neckline = 110, Structural T1 = 120.5, SL = 99.5 - 0.3 = 99.2.
    # Breakout candle closes at 114.0 -> Reward = 120.5 - 114.0 = 6.5, Risk = 114.0 - 99.2 = 14.8 -> R:R = 0.44 < 0.85
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=105, high=108, low=103, close=105, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=109, high=115, low=108, close=114.0, volume=2000)

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="NIFTY", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].breakout_status == "CONFIRMED"
    assert confirmed[0].entry_status == "POOR_RR"


def test_scenario_j_weak_ema_trendline_quality_classified():
    """Scenario J: Weak EMA / trendline confluence confirmed with trade_quality = LOW / MEDIUM."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=130.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=120.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=101.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=118, high=123, low=117, close=122, volume=2000)
    # EMA is above breakout price (126.0 > 122.0) -> Reversal only (Quality = 40)
    df_ind = pd.DataFrame({"ema_20": [126.0] * len(candles), "atr_14": [2.0] * len(candles)})

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=df_ind, symbol="NIFTY", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].breakout_status == "CONFIRMED"
    assert confirmed[0].trade_quality == "LOW"


def test_scenario_k_mixed_bearish_reversal_context_accepted():
    """Scenario K: Directional downward displacement leading into Low 1 accepted as BEARISH regime."""
    atr = 2.0
    swings = [
        SwingPoint(index=2, price=125.0, timestamp="2026-08-25T10:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=120.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=101.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=118, high=123, low=117, close=122, volume=2000)

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=swings[1], atr_val=atr, timeframe="15M"
    )
    assert regime == "BEARISH"


def test_scenario_l_mixed_bullish_reversal_context_accepted():
    """Scenario L: Directional upward displacement leading into High 1 accepted as BULLISH regime."""
    atr = 2.0
    swings = [
        SwingPoint(index=2, price=175.0, timestamp="2026-08-25T10:10:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=200.0, timestamp="2026-08-25T10:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=180.0, timestamp="2026-08-25T10:50:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=199.0, timestamp="2026-08-25T11:15:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=190, high=195, low=185, close=190, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=182, high=183, low=176, close=178, volume=2000)

    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=candles, swings=swings, point_1=swings[1], atr_val=atr, timeframe="15M"
    )
    assert regime == "BULLISH"


def test_scenario_m_bullish_continuation_w_rejected():
    """Scenario M: Bullish continuation W (higher low in bull trend) strictly rejected as reversal."""
    atr = 2.0
    swings = [
        SwingPoint(index=0, price=80.0, timestamp="2026-08-25T10:00:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=2, price=95.0, timestamp="2026-08-25T10:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=85.0, timestamp="2026-08-25T10:20:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=105.0, timestamp="2026-08-25T10:30:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        # L1 at 98.0 (Higher low relative to 85.0 -> Bullish continuation)
        SwingPoint(index=8, price=98.0, timestamp="2026-08-25T10:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=12, price=112.0, timestamp="2026-08-25T11:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=16, price=99.0, timestamp="2026-08-25T11:20:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=100, high=105, low=95, close=100, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=110, high=115, low=109, close=114, volume=2000)

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="NIFTY", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0


def test_scenario_n_bearish_continuation_m_rejected():
    """Scenario N: Bearish continuation M (lower high in bear trend) strictly rejected as reversal."""
    atr = 2.0
    swings = [
        SwingPoint(index=0, price=150.0, timestamp="2026-08-25T10:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=2, price=130.0, timestamp="2026-08-25T10:10:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=140.0, timestamp="2026-08-25T10:20:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=120.0, timestamp="2026-08-25T10:30:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        # H1 at 125.0 (Lower high relative to 140.0 -> Bearish continuation)
        SwingPoint(index=8, price=125.0, timestamp="2026-08-25T10:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=12, price=110.0, timestamp="2026-08-25T11:00:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=16, price=124.0, timestamp="2026-08-25T11:20:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=120, high=125, low=115, close=120, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=112, high=113, low=107, close=108, volume=2000)

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="NIFTY", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0


def test_scenario_o_long_duration_formation():
    """Scenario O: Long duration formation (40 bars spacing) confirmed within expanded candidate search."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=130.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=25, price=120.0, timestamp="2026-08-25T12:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=45, price=101.0, timestamp="2026-08-25T13:45:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000) for i in range(60)]
    candles[50] = Candle(timestamp="2026-08-25T14:10:00Z", open=118, high=123, low=117, close=122, volume=2000)

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="NIFTY", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].bar_separation == 40
    assert confirmed[0].breakout_status == "CONFIRMED"


def test_scenario_p_multi_volatility_regime_robustness():
    """Scenario P: Multi-volatility robustness across low ATR (0.5) and high ATR (15.0)."""
    # Low ATR = 0.5 (e.g. low-beta equity)
    atr_low = 0.5
    swings_low = [
        SwingPoint(index=1, price=30.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=20.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=25.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=20.3, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles_low = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=22, high=23, low=21, close=22, volume=1000) for i in range(25)]
    candles_low[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=24, high=26, low=23.5, close=25.6, volume=2000)

    _, conf_low, _, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles_low, swings=swings_low, trendlines=[], df_indicators=None, symbol="LOW_VOL", timeframe="15M", atr_val=atr_low
    )
    assert len(conf_low) >= 1
    assert conf_low[0].pattern_type == "W"

    # High ATR = 15.0 (e.g. crypto/index futures)
    atr_high = 15.0
    swings_high = [
        SwingPoint(index=1, price=3000.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=2500.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=2750.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=2512.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles_high = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=2600, high=2650, low=2550, close=2600, volume=1000) for i in range(25)]
    candles_high[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=2740, high=2780, low=2730, close=2765, volume=2000)

    _, conf_high, _, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles_high, swings=swings_high, trendlines=[], df_indicators=None, symbol="HIGH_VOL", timeframe="15M", atr_val=atr_high
    )
    assert len(conf_high) >= 1
    assert conf_high[0].pattern_type == "W"


# ============================================================================
# NEGATIVE TEST SUITE: STRUCTURALLY INVALID PATTERN REJECTIONS
# ============================================================================

def test_negative_1_two_similar_lows_no_meaningful_reaction():
    """Negative 1: Two similar lows with no meaningful reaction high between them -> REJECT."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=130.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=100.2, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000) for i in range(25)]

    _, confirmed, _, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TEST", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0
    rejected_cand = next((c for c in debug_cands if c.s1_price == 100.0 and c.s2_price == 100.2), None)
    assert rejected_cand is not None
    assert rejected_cand.status == "REJECTED"
    assert "No confirmed structural reaction high" in rejected_cand.rejection_reason


def test_negative_2_two_similar_highs_no_meaningful_reaction():
    """Negative 2: Two similar highs with no meaningful reaction low between them -> REJECT."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=170.0, timestamp="2026-08-25T10:05:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=200.0, timestamp="2026-08-25T10:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=199.8, timestamp="2026-08-25T11:15:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=190, high=195, low=185, close=190, volume=1000) for i in range(25)]

    _, confirmed, _, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TEST", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0
    rejected_cand = next((c for c in debug_cands if c.s1_price == 200.0 and c.s2_price == 199.8), None)
    assert rejected_cand is not None
    assert rejected_cand.status == "REJECTED"
    assert "No confirmed structural reaction low" in rejected_cand.rejection_reason


def test_negative_3_tiny_retest_noise_insufficient_amplitude():
    """Negative 3: Tiny retest leg (noise fluctuation < max(0.30 ATR, 0.20 Hpat)) -> REJECT."""
    atr = 2.0
    # Height = 10 (Neckline 110, L1 100). L2 = 109.8 -> Retest leg = 0.20 pts < max(0.60, 2.0) = 2.0 pts
    swings = [
        SwingPoint(index=1, price=130.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=110.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=109.8, timestamp="2026-08-25T11:10:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=105, high=108, low=103, close=105, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=110, high=115, low=109, close=114, volume=2000)

    _, confirmed, _, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TEST", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0


def test_negative_4_unrelated_pivots_exceeding_max_spacing():
    """Negative 4: Unrelated pivots paired across excessive horizontal range (> 60 bars) -> REJECT."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=130.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=40, price=120.0, timestamp="2026-08-25T13:20:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=75, price=101.0, timestamp="2026-08-25T16:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000) for i in range(85)]

    _, confirmed, _, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TEST", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0


def test_negative_5_deep_s2_continuation_beyond_sweep():
    """Negative 5: Deep S2 continuation (8 pts below S1 > 1.0 ATR) -> REJECT."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=130.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=110.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        # L2 at 92.0 (8.0 below 100.0) -> Exceeds allowed sweep tolerance of min(1.0*ATR, ...)
        SwingPoint(index=15, price=92.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="LL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=105, high=108, low=103, close=105, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=110, high=115, low=109, close=114, volume=2000)

    _, confirmed, _, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TEST", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0
    rejected_cand = next((c for c in debug_cands if c.s1_price == 100.0 and c.s2_price == 92.0), None)
    assert rejected_cand is not None
    assert rejected_cand.status == "REJECTED"


def test_negative_6_deep_h2_continuation_beyond_sweep():
    """Negative 6: Deep H2 continuation (8 pts above H1 > 1.0 ATR) -> REJECT."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=170.0, timestamp="2026-08-25T10:05:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=200.0, timestamp="2026-08-25T10:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=180.0, timestamp="2026-08-25T10:50:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        # H2 at 208.0 (8.0 above 200.0) -> Exceeds allowed sweep tolerance
        SwingPoint(index=15, price=208.0, timestamp="2026-08-25T11:15:00Z", is_high=True, type="HH", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=190, high=195, low=185, close=190, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=182, high=183, low=176, close=178, volume=2000)

    _, confirmed, _, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TEST", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0
    rejected_cand = next((c for c in debug_cands if c.s1_price == 200.0 and c.s2_price == 208.0), None)
    assert rejected_cand is not None
    assert rejected_cand.status == "REJECTED"


def test_negative_7_isolated_competing_necklines_unclustered():
    """Negative 7: Multiple unclustered competing necklines between S1 and S2 -> REJECT."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=130.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=100.0, timestamp="2026-08-25T10:20:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=112.0, timestamp="2026-08-25T10:40:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),  # High 1
        SwingPoint(index=14, price=124.0, timestamp="2026-08-25T11:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True), # High 2 (far, unclustered)
        SwingPoint(index=18, price=101.0, timestamp="2026-08-25T11:30:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000) for i in range(25)]

    _, confirmed, _, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TEST", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0


def test_negative_8_bullish_continuation_pullback_rejected_as_w():
    """Negative 8: Bullish continuation pullback falsely classified as W reversal -> STRICTLY REJECT."""
    atr = 2.0
    swings = [
        SwingPoint(index=0, price=80.0, timestamp="2026-08-25T10:00:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=3, price=95.0, timestamp="2026-08-25T10:15:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        # L1 is a higher low (88.0 > 80.0) -> Bullish continuation
        SwingPoint(index=6, price=88.0, timestamp="2026-08-25T10:30:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=100.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=89.0, timestamp="2026-08-25T11:10:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=95, high=102, low=94, close=98, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=99, high=104, low=98, close=103, volume=2000)

    _, confirmed, _, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TEST", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0


def test_negative_9_bearish_continuation_pullback_rejected_as_m():
    """Negative 9: Bearish continuation pullback falsely classified as M reversal -> STRICTLY REJECT."""
    atr = 2.0
    swings = [
        SwingPoint(index=0, price=150.0, timestamp="2026-08-25T10:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=3, price=130.0, timestamp="2026-08-25T10:15:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        # H1 is a lower high (140.0 < 150.0) -> Bearish continuation
        SwingPoint(index=6, price=140.0, timestamp="2026-08-25T10:30:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=120.0, timestamp="2026-08-25T10:50:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=139.0, timestamp="2026-08-25T11:10:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=130, high=135, low=125, close=130, volume=1000) for i in range(25)]
    candles[18] = Candle(timestamp="2026-08-25T11:30:00Z", open=122, high=123, low=117, close=118, volume=2000)

    _, confirmed, _, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TEST", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0


def test_negative_10_macro_multi_wave_competing_structure():
    """Negative 10: Multi-wave competing structure with deep intervening retracement -> REJECT."""
    atr = 2.0
    swings = [
        SwingPoint(index=1, price=100.0, timestamp="2026-08-25T10:05:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=130.0, timestamp="2026-08-25T10:20:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),  # H1
        SwingPoint(index=8, price=110.0, timestamp="2026-08-25T10:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),  # Mid trough
        SwingPoint(index=12, price=128.0, timestamp="2026-08-25T11:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True), # Deep inter high (90% retracement)
        SwingPoint(index=16, price=112.0, timestamp="2026-08-25T11:20:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=20, price=129.0, timestamp="2026-08-25T11:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)  # H2
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=120, high=125, low=115, close=120, volume=1000) for i in range(25)]
    candles[23] = Candle(timestamp="2026-08-25T11:55:00Z", open=115, high=116, low=108, close=109, volume=2000)

    _, confirmed, _, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None, symbol="TEST", timeframe="15M", atr_val=atr
    )
    macro_cand = next((c for c in debug_cands if c.s1_price == 130.0 and c.s2_price == 129.0), None)
    assert macro_cand is not None
    assert macro_cand.status == "REJECTED"
    assert "multi-wave" in macro_cand.rejection_reason

