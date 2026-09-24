import pytest
import pandas as pd
from app.models.schemas import Candle, SwingPoint
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector


def test_w_structural_reversal_target_equals_trend_origin_high():
    """
    Scenario 1: W structural reversal target equals the actual preceding bearish trend-origin swing high.
    Preceding structure:
      H_origin (25,200) -> LH1 (24,800) -> LH2 (24,400) -> L1 (24,000) -> Neck (24,300) -> L2 (24,050) -> Breakout (24,350)
    Target 1 must be 25,200, NOT 24,400 and NOT measured move (24,600).
    """
    atr = 50.0
    swings = [
        SwingPoint(index=2, price=25200.0, timestamp="2026-08-25T09:25:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=24600.0, timestamp="2026-08-25T09:40:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=24800.0, timestamp="2026-08-25T09:55:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=11, price=24200.0, timestamp="2026-08-25T10:10:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=24400.0, timestamp="2026-08-25T10:25:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=17, price=24000.0, timestamp="2026-08-25T10:40:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),  # L1
        SwingPoint(index=21, price=24300.0, timestamp="2026-08-25T11:00:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),   # Neckline
        SwingPoint(index=25, price=24050.0, timestamp="2026-08-25T11:20:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True),  # L2
    ]

    candles = [
        Candle(timestamp=f"2026-08-25T{9 + i // 12:02d}:{(i % 12) * 5:02d}:00+05:30", open=24300, high=24350, low=24250, close=24300, volume=1000)
        for i in range(32)
    ]
    # Breakout candle closing above neckline (24,300)
    candles[28] = Candle(timestamp="2026-08-25T11:35:00+05:30", open=24290, high=24380, low=24280, close=24350.0, volume=3500)
    df_ind = pd.DataFrame({"ema_20": [24200.0] * len(candles), "atr_14": [atr] * len(candles)})

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )

    assert len(confirmed) >= 1
    w_pat = confirmed[0]
    assert w_pat.pattern_type == "W"
    assert w_pat.s1_price == 24000.0
    assert w_pat.neckline_price == 24300.0
    assert w_pat.s2_price == 24050.0
    # Target 1 is the trend origin 25,200
    assert w_pat.target_1 == 25200.0
    assert w_pat.target_analysis.measured_target == 25200.0


def test_m_structural_reversal_target_equals_trend_origin_low():
    """
    Scenario 2: M structural reversal target equals the actual preceding bullish trend-origin swing low.
    Preceding structure:
      L_origin (24,000) -> HL1 (24,200) -> HL2 (24,400) -> H1 (25,000) -> Neck (24,700) -> H2 (24,950) -> Breakdown (24,650)
    Target 1 must be 24,000, NOT 24,400 and NOT measured move (24,400).
    """
    atr = 50.0
    swings = [
        SwingPoint(index=2, price=24000.0, timestamp="2026-08-25T09:25:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=24300.0, timestamp="2026-08-25T09:40:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=24200.0, timestamp="2026-08-25T09:55:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=11, price=24500.0, timestamp="2026-08-25T10:10:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=24400.0, timestamp="2026-08-25T10:25:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=17, price=25000.0, timestamp="2026-08-25T10:40:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),  # H1
        SwingPoint(index=21, price=24700.0, timestamp="2026-08-25T11:00:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),  # Neckline
        SwingPoint(index=25, price=24950.0, timestamp="2026-08-25T11:20:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),   # H2
    ]

    candles = [
        Candle(timestamp=f"2026-08-25T{9 + i // 12:02d}:{(i % 12) * 5:02d}:00+05:30", open=24700, high=24750, low=24650, close=24700, volume=1000)
        for i in range(32)
    ]
    # Breakdown candle closing below neckline (24,700)
    candles[28] = Candle(timestamp="2026-08-25T11:35:00+05:30", open=24710, high=24720, low=24620, close=24650.0, volume=3500)
    df_ind = pd.DataFrame({"ema_20": [24800.0] * len(candles), "atr_14": [atr] * len(candles)})

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=df_ind,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )

    assert len(confirmed) >= 1
    m_pat = confirmed[0]
    assert m_pat.pattern_type == "M"
    assert m_pat.s1_price == 25000.0
    assert m_pat.neckline_price == 24700.0
    assert m_pat.s2_price == 24950.0
    # Target 1 is the trend origin 24,000
    assert m_pat.target_1 == 24000.0
    assert m_pat.target_analysis.measured_target == 24000.0


def test_w_multi_swing_sequence_picks_origin_high():
    """
    Scenario 3: W multi-swing sequence: 25,200 -> 24,800 -> 24,400 -> W selects 25,200.
    """
    p1 = SwingPoint(index=12, price=24000.0, timestamp="2026-08-25T10:30:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True)
    swings = [
        SwingPoint(index=2, price=25200.0, timestamp="2026-08-25T09:30:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=24700.0, timestamp="2026-08-25T09:45:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=24800.0, timestamp="2026-08-25T10:00:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=24300.0, timestamp="2026-08-25T10:15:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=24400.0, timestamp="2026-08-25T10:20:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        p1
    ]
    origin_price, origin_time = PrecisionBreakoutDetector.extract_preceding_trend_origin(
        candles=[], swings=swings, point_1=p1, pattern_type="W", timeframe="5M"
    )
    assert origin_price == 25200.0
    assert origin_time == "2026-08-25T09:30:00+05:30"


def test_m_multi_swing_sequence_picks_origin_low():
    """
    Scenario 4: M multi-swing sequence: 24,000 -> 24,200 -> 24,400 -> M selects 24,000.
    """
    p1 = SwingPoint(index=12, price=25000.0, timestamp="2026-08-25T10:30:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True)
    swings = [
        SwingPoint(index=2, price=24000.0, timestamp="2026-08-25T09:30:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=24300.0, timestamp="2026-08-25T09:45:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=24200.0, timestamp="2026-08-25T10:00:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=24500.0, timestamp="2026-08-25T10:15:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=24400.0, timestamp="2026-08-25T10:20:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True),
        p1
    ]
    origin_price, origin_time = PrecisionBreakoutDetector.extract_preceding_trend_origin(
        candles=[], swings=swings, point_1=p1, pattern_type="M", timeframe="5M"
    )
    assert origin_price == 24000.0
    assert origin_time == "2026-08-25T09:30:00+05:30"


def test_valid_origin_outside_arbitrary_lookbacks_detected():
    """
    Scenario 5: A valid origin outside an arbitrary five-swing or twenty-candle window is correctly detected.
    15 prior swings, 45 prior candles.
    """
    swings = []
    for i in range(8):
        swings.append(SwingPoint(
            index=i * 5 + 1, price=26000.0 - (i * 100),
            timestamp=f"2026-08-25T{9 + i // 6:02d}:{(i % 6) * 10:02d}:00+05:30",
            is_high=True, type="LH" if i > 0 else "HH", strength=2.0, confirmed=True
        ))
        swings.append(SwingPoint(
            index=i * 5 + 3, price=25800.0 - (i * 100),
            timestamp=f"2026-08-25T{9 + i // 6:02d}:{(i % 6) * 10 + 5:02d}:00+05:30",
            is_high=False, type="LL", strength=2.0, confirmed=True
        ))

    p1 = SwingPoint(index=45, price=25000.0, timestamp="2026-08-25T12:30:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True)
    swings.append(p1)

    origin_price, _ = PrecisionBreakoutDetector.extract_preceding_trend_origin(
        candles=[], swings=swings, point_1=p1, pattern_type="W", timeframe="5M"
    )
    assert origin_price == 26000.0


def test_w_target_1_must_be_strictly_above_neckline():
    """
    Scenario 6: W Target 1 must be strictly > neckline.
    If reversal_target <= neckline, calculate_pattern_targets falls back to neckline + height.
    """
    res = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="W",
        s1_price=24000.0,
        s2_price=24050.0,
        neckline_price=24300.0,
        breakout_close=24350.0,
        reversal_target=24200.0  # Under neckline!
    )
    # Height = 24300 - 24000 = 300 -> Measured move = 24300 + 300 = 24600.0
    assert res.measured_target == 24600.0


def test_m_target_1_must_be_strictly_below_neckline():
    """
    Scenario 7: M Target 1 must be strictly < neckline.
    If reversal_target >= neckline, calculate_pattern_targets falls back to neckline - height.
    """
    res = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="M",
        s1_price=25000.0,
        s2_price=24950.0,
        neckline_price=24700.0,
        breakout_close=24650.0,
        reversal_target=24800.0  # Above neckline!
    )
    # Height = 25000 - 24700 = 300 -> Measured move = 24700 - 300 = 24400.0
    assert res.measured_target == 24400.0


def test_missing_or_invalid_structural_origin_safe_fallback():
    """
    Scenario 8: Missing/invalid structural origin safely uses the existing fallback without crashing.
    """
    res_w = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="W",
        s1_price=100.0,
        s2_price=102.0,
        neckline_price=120.0,
        breakout_close=122.0,
        reversal_target=None
    )
    assert res_w.measured_target == 140.0

    res_m = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="M",
        s1_price=200.0,
        s2_price=198.0,
        neckline_price=180.0,
        breakout_close=178.0,
        reversal_target=None
    )
    assert res_m.measured_target == 160.0


def test_rr_uses_new_structural_target_1():
    """
    Scenario 9: R:R calculation strictly uses the structural Target 1.
    Reward = abs(Target 1 - Entry), Risk = abs(Entry - SL), R:R = Reward / Risk.
    """
    res = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="W",
        s1_price=24000.0,
        s2_price=24050.0,
        neckline_price=24300.0,
        breakout_close=24350.0,
        prev_swing_sl=24000.0,
        reversal_target=25200.0
    )
    assert res.measured_target == 25200.0
    expected_rr = round((25200.0 - 24350.0) / (24350.0 - res.invalidation_level), 2)
    assert res.risk_reward_ratio == expected_rr


def test_macro_w_and_macro_m_integration():
    """
    Scenarios 10 & 11: Macro W and Macro M detection pipelines use the structural reversal target.
    """
    atr = 10.0
    # Macro W
    w_swings = [
        SwingPoint(index=1, price=150.0, timestamp="2026-08-25T09:20:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),  # Origin High
        SwingPoint(index=4, price=110.0, timestamp="2026-08-25T09:35:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=7, price=130.0, timestamp="2026-08-25T09:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=100.0, timestamp="2026-08-25T10:05:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),  # L1
        SwingPoint(index=14, price=120.0, timestamp="2026-08-25T10:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),   # Neckline
        SwingPoint(index=18, price=102.0, timestamp="2026-08-25T10:45:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)   # L2
    ]
    candles = [Candle(timestamp=f"2026-08-25T10:{i*2:02d}:00Z", open=115, high=118, low=112, close=115, volume=1000) for i in range(25)]
    candles[21] = Candle(timestamp="2026-08-25T10:50:00Z", open=119, high=125, low=118, close=123.0, volume=3000)
    df_ind = pd.DataFrame({"ema_20": [115.0] * len(candles), "atr_14": [atr] * len(candles)})

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=w_swings, trendlines=[], df_indicators=df_ind,
        symbol="SYM_W", timeframe="1H", atr_val=atr
    )
    assert len(confirmed) >= 1
    assert confirmed[0].target_1 == 150.0

    # Macro M
    m_swings = [
        SwingPoint(index=1, price=50.0, timestamp="2026-08-25T09:20:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),  # Origin Low
        SwingPoint(index=4, price=90.0, timestamp="2026-08-25T09:35:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=7, price=70.0, timestamp="2026-08-25T09:50:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=100.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),  # H1
        SwingPoint(index=14, price=80.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),  # Neckline
        SwingPoint(index=18, price=98.0, timestamp="2026-08-25T10:45:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)   # H2
    ]
    candles_m = [Candle(timestamp=f"2026-08-25T10:{i*2:02d}:00Z", open=85, high=88, low=82, close=85, volume=1000) for i in range(25)]
    candles_m[21] = Candle(timestamp="2026-08-25T10:50:00Z", open=81, high=82, low=75, close=77.0, volume=3000)
    df_ind_m = pd.DataFrame({"ema_20": [85.0] * len(candles_m), "atr_14": [atr] * len(candles_m)})

    events_m, confirmed_m, active_m, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles_m, swings=m_swings, trendlines=[], df_indicators=df_ind_m,
        symbol="SYM_M", timeframe="1H", atr_val=atr
    )
    assert len(confirmed_m) >= 1
    assert confirmed_m[0].target_1 == 50.0


def test_target_2_and_sl_preserved():
    """
    Scenario 14: Target 2 formula is preserved (neckline ± 1.618 * pattern_height)
    and SL formula is preserved (Point-2 based with ATR buffer).
    """
    atr = 10.0
    res_w = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="W",
        s1_price=100.0,
        s2_price=102.0,
        neckline_price=120.0,
        breakout_close=122.0,
        prev_swing_sl=100.5,
        atr_val=atr,
        sl_atr_buffer=1.5,
        reversal_target=145.0
    )
    # Target 1 = 145.0 (structural reversal target)
    assert res_w.measured_target == 145.0
    # Height = 120.0 - 100.0 = 20.0
    # Target 2 = 120.0 + 1.618 * 20.0 = 152.36
    assert res_w.target_2 == 152.36
    # SL = 100.5 (prev_swing_sl passed in)
    assert res_w.invalidation_level == 100.5


def test_highest_prior_swing_not_origin_rule_respected():
    """
    Scenario 15: Critical check proving naive max(prior_highs) or min(prior_lows) is NOT used.
    When a prior cycle had a lower peak followed by an even lower peak, but earlier had a higher peak:
    Sequence of highs:
    H0 = 25,500
    H1 = 25,000  (Origin of this leg)
    H2 = 25,200  (Higher than H1, breaking the monotonic descent from H1, so H2 was a new high)
    H3 = 24,800  (Lower than H2)
    H4 = 24,400  (Lower than H3)
    p1 = 24,000  (L1)
    Walking backwards from p1 through descending highs:
    H4 (24,400) -> H3 (24,800) -> H2 (25,200).
    At H2, preceding high H1 is 25,000 <= 25,200 (descent stopped at H2).
    True trend origin is H2 (25,200), NOT max(prior_highs) which is H0 (25,500).
    """
    p1 = SwingPoint(index=20, price=24000.0, timestamp="2026-08-25T11:00:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True)
    swings = [
        # Older historical peak
        SwingPoint(index=2, price=25500.0, timestamp="2026-08-25T09:30:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=24200.0, timestamp="2026-08-25T09:40:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=25000.0, timestamp="2026-08-25T09:50:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=24500.0, timestamp="2026-08-25T10:00:00+05:30", is_high=False, type="HL", strength=2.0, confirmed=True),
        # Initiation of current validated downtrend
        SwingPoint(index=10, price=25200.0, timestamp="2026-08-25T10:15:00+05:30", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=12, price=24600.0, timestamp="2026-08-25T10:25:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=24800.0, timestamp="2026-08-25T10:35:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=16, price=24200.0, timestamp="2026-08-25T10:45:00+05:30", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=18, price=24400.0, timestamp="2026-08-25T10:55:00+05:30", is_high=True, type="LH", strength=2.0, confirmed=True),
        p1
    ]

    origin_price, origin_time = PrecisionBreakoutDetector.extract_preceding_trend_origin(
        candles=[], swings=swings, point_1=p1, pattern_type="W", timeframe="5M"
    )
    # Must pick 25,200 (origin of the uninterrupted descending high sequence), NOT max(all_highs)=25,500
    assert origin_price == 25200.0
    assert origin_time == "2026-08-25T10:15:00+05:30"


def test_fast_5m_w_uses_structural_target():
    """
    Scenario 12: Fast 5M W path computes and applies the preceding trend-origin swing high.
    """
    atr = 15.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=24050, high=24060, low=24040, close=24050, volume=1000)
        for i in range(20)
    ]
    candles[4] = Candle(timestamp="2026-08-25T10:20:00Z", open=24030, high=24035, low=24010, close=24015, volume=1000)
    candles[7] = Candle(timestamp="2026-08-25T10:35:00Z", open=24045, high=24065, low=24040, close=24060, volume=1000)
    candles[9] = Candle(timestamp="2026-08-25T10:45:00Z", open=24040, high=24045, low=24015, close=24020, volume=1000)
    candles[11] = Candle(timestamp="2026-08-25T10:55:00Z", open=24055, high=24080, low=24050, close=24075, volume=3000)

    prior_h = SwingPoint(index=1, price=24100.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True)
    l1 = SwingPoint(index=4, price=24010.0, timestamp="2026-08-25T10:20:00Z", is_high=False, type="LL", strength=2.0, confirmed=True)
    neckline = SwingPoint(index=7, price=24065.0, timestamp="2026-08-25T10:35:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    l2 = SwingPoint(index=9, price=24015.0, timestamp="2026-08-25T10:45:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=[prior_h, l1, neckline, l2], trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )
    assert len(confirmed) >= 1
    w_fast = confirmed[0]
    assert w_fast.pattern_type == "W"
    # Target 1 is the preceding trend origin swing high 24,100
    assert w_fast.target_1 == 24100.0
    assert w_fast.target_analysis.measured_target == 24100.0


def test_fast_5m_m_uses_structural_target():
    """
    Scenario 13: Fast 5M M path computes and applies the preceding trend-origin swing low.
    """
    atr = 15.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=24050, high=24060, low=24040, close=24050, volume=1000)
        for i in range(20)
    ]
    # H1 at index 4 (high 24090), Neckline candle at index 7 (low 24035), H2 candle at index 9 (high 24085), Breakdown at index 11 (close 24025)
    candles[4] = Candle(timestamp="2026-08-25T10:20:00Z", open=24070, high=24090, low=24065, close=24085, volume=1000)
    candles[7] = Candle(timestamp="2026-08-25T10:35:00Z", open=24055, high=24060, low=24035, close=24040, volume=1000)
    candles[9] = Candle(timestamp="2026-08-25T10:45:00Z", open=24060, high=24085, low=24055, close=24080, volume=1000)
    candles[11] = Candle(timestamp="2026-08-25T10:55:00Z", open=24045, high=24050, low=24020, close=24025, volume=3000)

    prior_l = SwingPoint(index=1, price=24000.0, timestamp="2026-08-25T10:05:00Z", is_high=False, type="LL", strength=2.0, confirmed=True)
    h1 = SwingPoint(index=4, price=24090.0, timestamp="2026-08-25T10:20:00Z", is_high=True, type="HH", strength=2.0, confirmed=True)
    neckline = SwingPoint(index=7, price=24035.0, timestamp="2026-08-25T10:35:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    h2 = SwingPoint(index=9, price=24085.0, timestamp="2026-08-25T10:45:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=[prior_l, h1, neckline, h2], trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )
    assert len(confirmed) >= 1
    m_fast = confirmed[0]
    assert m_fast.pattern_type == "M"
    # Target 1 is the preceding trend origin swing low 24,000
    assert m_fast.target_1 == 24000.0
    assert m_fast.target_analysis.measured_target == 24000.0
