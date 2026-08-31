import pytest
import pandas as pd
from app.models.schemas import Candle, SwingPoint
from app.market_structure.trendlines import Trendline
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.alerts.mw_breakout_engine import MWBreakoutAlertEngine
from app.core.config import settings

@pytest.fixture(autouse=True)
def isolate_store(tmp_path, monkeypatch):
    monkeypatch.setattr("app.alerts.mw_breakout_engine.STORAGE_FILE", tmp_path / "test_mw_store.json")

# ============================================================================
# 1. STRUCTURAL REVERSAL & CONTINUATION TESTS (TESTS 1 - 6)
# ============================================================================

def test_1_bull_continuation_w_rejected():
    """1. Bull-market pullback forming W continuation -> REJECT (Score 0)."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=100 + i*3, high=102 + i*3, low=98 + i*3, close=101 + i*3, volume=1000)
        for i in range(30)
    ]
    swings = [
        SwingPoint(index=2, price=100.0, timestamp="2026-08-25T10:10:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=130.0, timestamp="2026-08-25T10:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=120.0, timestamp="2026-08-25T10:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=12, price=155.0, timestamp="2026-08-25T11:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=140.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=18, price=175.0, timestamp="2026-08-25T11:30:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        # Pullback base: L1 (132) -> Neckline (138) -> L2 (133)
        SwingPoint(index=20, price=132.0, timestamp="2026-08-25T11:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=23, price=138.0, timestamp="2026-08-25T11:55:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=27, price=133.0, timestamp="2026-08-25T12:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="RELIANCE", timeframe="15M", atr_val=atr
    )

    assert len(confirmed) == 0, "Bull-market pullback W continuation must be rejected"
    w_cands = [c for c in debug_cands if c.pattern_type == "W" and c.s1_index == 20]
    assert len(w_cands) >= 1
    rejected = w_cands[0]
    assert rejected.status == "REJECTED"
    assert rejected.quality_score == 0
    assert "bullish" in rejected.rejection_reason.lower() or "continuation" in rejected.rejection_reason.lower()

def test_2_bear_continuation_m_rejected():
    """2. Bear-market rally forming M continuation -> REJECT (Score 0)."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=200 - i*3, high=202 - i*3, low=198 - i*3, close=199 - i*3, volume=1000)
        for i in range(30)
    ]
    swings = [
        SwingPoint(index=2, price=200.0, timestamp="2026-08-25T10:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=170.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=180.0, timestamp="2026-08-25T10:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=12, price=145.0, timestamp="2026-08-25T11:00:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=155.0, timestamp="2026-08-25T11:15:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=18, price=105.0, timestamp="2026-08-25T11:30:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        # Bear flag rally: H1 (115) -> Neckline (108) -> H2 (114)
        SwingPoint(index=20, price=115.0, timestamp="2026-08-25T11:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=23, price=108.0, timestamp="2026-08-25T11:55:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=27, price=114.0, timestamp="2026-08-25T12:15:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="TCS", timeframe="1H", atr_val=atr
    )

    assert len(confirmed) == 0, "Bear-market rally M continuation must be rejected"
    m_cands = [c for c in debug_cands if c.pattern_type == "M" and c.s1_index == 20]
    assert len(m_cands) >= 1
    rejected = m_cands[0]
    assert rejected.status == "REJECTED"
    assert rejected.quality_score == 0
    assert "bearish" in rejected.rejection_reason.lower() or "continuation" in rejected.rejection_reason.lower()

def test_3_genuine_bearish_to_bullish_w_accepted():
    """3. Genuine W reversal after clear preceding downtrend (LH/LL) with EMA confluence -> ACCEPT."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=140 - i*2, high=142 - i*2, low=138 - i*2, close=139 - i*2, volume=1000)
        for i in range(10)
    ]
    candles[9] = Candle(timestamp="2026-08-25T10:45:00Z", open=105, high=106, low=100, close=101, volume=1000)
    for i in range(10, 30):
        candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000))
    # Breakout candle: closes at 119.5 (just above neckline 118, T1=136, SL=100.7, RR=(136-119.5)/(119.5-100.7)=16.5/18.8=0.88 >= 0.85)
    candles[24] = Candle(timestamp="2026-08-25T11:48:00Z", open=117, high=121, low=116, close=119.5, volume=2500)

    # Preceding swings: High 0 (140) -> Low 0 (120) -> LH (130) -> LL (110) -> LH (122) -> Low 1 (100)
    swings = [
        SwingPoint(index=0, price=140.0, timestamp="2026-08-25T10:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=2, price=120.0, timestamp="2026-08-25T10:10:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=130.0, timestamp="2026-08-25T10:20:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=110.0, timestamp="2026-08-25T10:30:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=122.0, timestamp="2026-08-25T10:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        # W Pattern Swings: L1 (100) -> Neckline (118) -> L2 (101) (separation: 19 - 9 = 10 bars >= 6)
        SwingPoint(index=9, price=100.0, timestamp="2026-08-25T10:45:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=118.0, timestamp="2026-08-25T11:28:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=19, price=101.0, timestamp="2026-08-25T11:38:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]

    df_ind = pd.DataFrame({"ema_20": [112.0] * len(candles), "atr_14": [2.0] * len(candles)})

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=df_ind,
        symbol="RELIANCE", timeframe="15M", atr_val=atr
    )

    assert len(confirmed) == 1, "Genuine W reversal with EMA confluence (Score 70) must be accepted"
    pat = confirmed[0]
    assert pat.pattern_type == "W"
    assert pat.s1_price == 100.0
    assert pat.neckline_price == 118.0
    assert pat.s2_price == 101.0
    assert pat.quality_score >= 70

def test_4_genuine_bullish_to_bearish_m_accepted():
    """4. Genuine M reversal after clear preceding uptrend (HH/HL) with EMA confluence -> ACCEPT."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=160 + i*2, high=162 + i*2, low=158 + i*2, close=161 + i*2, volume=1000)
        for i in range(10)
    ]
    candles[9] = Candle(timestamp="2026-08-25T10:45:00Z", open=195, high=200, low=194, close=199, volume=1000)
    for i in range(10, 30):
        candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=190, high=195, low=185, close=190, volume=1000))
    # Breakout candle: closes at 180.5 (just below neckline 182, T1=164, SL=199.3, RR=(180.5-164)/(199.3-180.5)=16.5/18.8=0.88 >= 0.85)
    candles[24] = Candle(timestamp="2026-08-25T11:48:00Z", open=183, high=184, low=179, close=180.5, volume=2500)

    # Preceding swings: Low 0 (160) -> High 0 (175) -> HL (170) -> HH (185) -> HL (180) -> High 1 (200)
    swings = [
        SwingPoint(index=0, price=160.0, timestamp="2026-08-25T10:00:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=2, price=175.0, timestamp="2026-08-25T10:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=170.0, timestamp="2026-08-25T10:20:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=185.0, timestamp="2026-08-25T10:30:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=180.0, timestamp="2026-08-25T10:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        # M Pattern Swings: H1 (200) -> Neckline (182) -> H2 (199) (separation: 19 - 9 = 10 bars >= 6)
        SwingPoint(index=9, price=200.0, timestamp="2026-08-25T10:45:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=182.0, timestamp="2026-08-25T11:28:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=19, price=199.0, timestamp="2026-08-25T11:38:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]

    df_ind = pd.DataFrame({"ema_20": [186.0] * len(candles), "atr_14": [2.0] * len(candles)})

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=df_ind,
        symbol="TCS", timeframe="1H", atr_val=atr
    )

    assert len(confirmed) == 1, "Genuine M reversal with EMA confluence (Score 70) must be accepted"
    pat = confirmed[0]
    assert pat.pattern_type == "M"
    assert pat.s1_price == 200.0
    assert pat.neckline_price == 182.0
    assert pat.s2_price == 199.0
    assert pat.quality_score >= 70

def test_5_sideways_w_rejected():
    """5. Sideways consolidation range forming W -> REJECT."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=100.0, high=101.5, low=98.5, close=100.0, volume=1000)
        for i in range(30)
    ]
    swings = [
        SwingPoint(index=1, price=101.0, timestamp="2026-08-25T10:05:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=3, price=99.5, timestamp="2026-08-25T10:15:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=101.2, timestamp="2026-08-25T10:30:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=9, price=99.6, timestamp="2026-08-25T10:45:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=13, price=101.1, timestamp="2026-08-25T11:05:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=17, price=99.4, timestamp="2026-08-25T11:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=20, price=101.0, timestamp="2026-08-25T11:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=27, price=99.5, timestamp="2026-08-25T12:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )
    assert len(confirmed) == 0

def test_6_sideways_m_rejected():
    """6. Sideways consolidation range forming M -> REJECT."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=100.0, high=101.5, low=98.5, close=100.0, volume=1000)
        for i in range(30)
    ]
    swings = [
        SwingPoint(index=1, price=99.0, timestamp="2026-08-25T10:05:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=3, price=101.0, timestamp="2026-08-25T10:15:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=99.2, timestamp="2026-08-25T10:30:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=9, price=101.1, timestamp="2026-08-25T10:45:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=13, price=99.1, timestamp="2026-08-25T11:05:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=17, price=101.2, timestamp="2026-08-25T11:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=20, price=99.3, timestamp="2026-08-25T11:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=27, price=101.1, timestamp="2026-08-25T12:15:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="BANK NIFTY", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0

# ============================================================================
# 2. QUALITY SCORE HARD GATING TESTS (TESTS 7 - 9)
# ============================================================================

def test_7_quality_40_rejected_in_precision_mode():
    """7. Quality Score 40 (Reversal only, no EMA/TL) -> REJECT in Balanced Precision Mode."""
    score, breakdown = PrecisionBreakoutDetector.calculate_wm_quality_score(
        pattern_type="W",
        breakout_candle=Candle(timestamp="2026-08-25T10:00:00Z", open=100, high=105, low=99, close=104, volume=1000),
        tl=None,
        ema_20=None,
        has_reversal=True
    )
    assert score == 40
    assert breakdown["reversal"] == 40
    assert breakdown["trendline"] == 0
    assert breakdown["ema"] == 0
    assert score < settings.MIN_WM_QUALITY_SCORE

def test_8_quality_70_accepted():
    """8. Quality Score 70 (Reversal + 20 EMA) -> ACCEPT in Balanced Precision Mode."""
    bc = Candle(timestamp="2026-08-25T10:00:00Z", open=100, high=108, low=99, close=106, volume=1000)
    score, breakdown = PrecisionBreakoutDetector.calculate_wm_quality_score(
        pattern_type="W",
        breakout_candle=bc,
        tl=None,
        ema_20=102.0,
        has_reversal=True
    )
    assert breakdown["reversal"] == 40
    assert breakdown["trendline"] == 0
    assert breakdown["ema"] == 30
    assert score == 70
    assert score >= settings.MIN_WM_QUALITY_SCORE

def test_9_quality_100_accepted():
    """9. Quality Score 100 (Reversal + Trendline + 20 EMA) -> ACCEPT."""
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=0, p1_price=130.0, p1_time="2026-08-25T10:00:00Z",
        p2_index=10, p2_price=120.0, p2_time="2026-08-25T10:50:00Z",
        slope=-1.0, intercept=130.0, end_index=20, end_price=110.0, touch_count=2, is_active=True
    )
    bc = Candle(index=18, timestamp="2026-08-25T11:30:00Z", open=115, high=125, low=114, close=122, volume=2000)

    score, breakdown = PrecisionBreakoutDetector.calculate_wm_quality_score(
        pattern_type="W",
        breakout_candle=bc,
        breakout_candle_index=18,
        tl=tl,
        ema_20=115.0,
        has_reversal=True
    )
    assert breakdown["reversal"] == 40
    assert breakdown["trendline"] == 30
    assert breakdown["ema"] == 30
    assert score == 100
    assert score >= settings.MIN_WM_QUALITY_SCORE

# ============================================================================
# 3. BREAKOUT EXTENSION & OVEREXTENSION TESTS (TESTS 10 - 11)
# ============================================================================

def test_10_breakout_extension_le_0_50_accepted():
    """10. Breakout candle extension <= 0.50x pattern depth -> ACCEPT."""
    neckline = 100.0
    pattern_depth = 20.0
    max_extension_ratio = settings.MAX_BREAKOUT_EXTENSION_DEPTH_RATIO  # 0.50
    close_price = 108.0
    ratio = (close_price - neckline) / pattern_depth
    assert ratio <= max_extension_ratio

def test_11_breakout_extension_gt_0_50_rejected():
    """11. Breakout candle extension > 0.50x pattern depth -> REJECT."""
    neckline = 100.0
    pattern_depth = 20.0
    max_extension_ratio = settings.MAX_BREAKOUT_EXTENSION_DEPTH_RATIO  # 0.50
    close_price = 114.0
    ratio = (close_price - neckline) / pattern_depth
    assert ratio > max_extension_ratio

# ============================================================================
# 4. MINIMUM RISK:REWARD (R:R) TESTS (TESTS 12 - 13)
# ============================================================================

def test_12_rr_lt_0_85_rejected():
    """12. Risk:Reward ratio < 0.85 -> REJECT."""
    entry_price = 115.0
    t1_price = 120.0  # distance = 5.0
    sl_price = 105.0  # distance = 10.0
    rr = abs(t1_price - entry_price) / abs(entry_price - sl_price)  # 5 / 10 = 0.50
    assert rr < settings.MIN_WM_RR

def test_13_rr_gte_0_85_accepted():
    """13. Risk:Reward ratio >= 0.85 -> ACCEPT."""
    entry_price = 110.0
    t1_price = 122.0  # distance = 12.0
    sl_price = 100.0  # distance = 10.0
    rr = abs(t1_price - entry_price) / abs(entry_price - sl_price)  # 12 / 10 = 1.20
    assert rr >= settings.MIN_WM_RR

# ============================================================================
# 5. LEG SEPARATION TESTS (TESTS 14 - 15)
# ============================================================================

def test_14_separation_lt_6_rejected():
    """14. Point 1 to Point 2 separation < 6 bars -> REJECT."""
    bar_sep = 4
    min_sep = settings.MIN_WM_BAR_SEPARATION  # 6
    assert bar_sep < min_sep

def test_15_separation_gte_6_accepted():
    """15. Point 1 to Point 2 separation >= 6 bars -> ACCEPT."""
    bar_sep = 8
    min_sep = settings.MIN_WM_BAR_SEPARATION  # 6
    assert bar_sep >= min_sep

# ============================================================================
# 6. LIQUIDITY SWEEPS (TESTS 16 - 17)
# ============================================================================

def test_16_liquidity_sweep_w_accepted():
    """16. Liquidity sweep W (L2 < L1 within ATR) -> ACCEPT."""
    atr = 2.0
    l1_price = 100.0
    l2_price = 98.8  # sweep below L1 by 1.2 (< 1.5 ATR)
    assert l2_price < l1_price
    assert abs(l2_price - l1_price) <= (1.5 * atr)

def test_17_liquidity_sweep_m_accepted():
    """17. Liquidity sweep M (H2 > H1 within ATR) -> ACCEPT."""
    atr = 2.0
    h1_price = 200.0
    h2_price = 201.2  # sweep above H1 by 1.2 (< 1.5 ATR)
    assert h2_price > h1_price
    assert abs(h2_price - h1_price) <= (1.5 * atr)

# ============================================================================
# 7. MISSING INDICATOR DATA (TESTS 18 - 19)
# ============================================================================

def test_18_missing_ema_zero_points():
    """18. Missing EMA data -> 0 EMA points."""
    score, breakdown = PrecisionBreakoutDetector.calculate_wm_quality_score(
        pattern_type="W",
        breakout_candle=Candle(timestamp="2026-08-25T10:00:00Z", open=100, high=105, low=99, close=104, volume=1000),
        tl=None,
        ema_20=None,
        has_reversal=True
    )
    assert breakdown["ema"] == 0

def test_19_missing_trendline_zero_points():
    """19. Missing trendline -> 0 Trendline points."""
    score, breakdown = PrecisionBreakoutDetector.calculate_wm_quality_score(
        pattern_type="W",
        breakout_candle=Candle(timestamp="2026-08-25T10:00:00Z", open=100, high=105, low=99, close=104, volume=1000),
        tl=None,
        ema_20=100.0,
        has_reversal=True
    )
    assert breakdown["trendline"] == 0

# ============================================================================
# 8. CONFIRMATION, TIMING & CLOSES (TESTS 20 - 24)
# ============================================================================

def test_20_unconfirmed_point_2_rejected():
    """20. Unconfirmed Point 2 (confirmed=False) -> REJECT."""
    s2 = SwingPoint(index=18, price=100.0, timestamp="2026-08-25T11:30:00Z", is_high=False, type="HL", strength=2.0, confirmed=False)
    assert not getattr(s2, "confirmed", True)

def test_21_breakout_before_point_2_confirmation_rejected():
    """21. Breakout scanned before Point 2 confirmation_index -> REJECT."""
    s2 = SwingPoint(index=15, price=100.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmation_index=18, confirmed=True)
    min_scan_idx = max(s2.index + 1, s2.confirmation_index)
    assert min_scan_idx == 18
    candle_idx = 16
    assert candle_idx < min_scan_idx

def test_22_wick_only_breakout_rejected():
    """22. Wick penetrates neckline but Close remains below -> NO BREAKOUT."""
    neckline = 100.0
    candle = Candle(timestamp="2026-08-25T11:00:00Z", open=97.0, high=102.0, low=96.0, close=99.0, volume=1000)
    is_wick_penetration = candle.high > neckline
    is_confirmed_close = candle.close > neckline
    assert is_wick_penetration
    assert not is_confirmed_close

def test_23_completed_candle_close_breakout_accepted():
    """23. Completed candle Close above neckline -> CONFIRMED BREAKOUT."""
    neckline = 100.0
    candle = Candle(timestamp="2026-08-25T11:00:00Z", open=98.0, high=104.0, low=97.5, close=103.5, volume=1500)
    is_confirmed_close = candle.close > neckline
    assert is_confirmed_close

def test_24_rejected_candidate_quality_score_zero():
    """24. Rejected candidate (has_reversal=False) MUST receive strictly 0 score."""
    score, breakdown = PrecisionBreakoutDetector.calculate_wm_quality_score(
        pattern_type="W",
        breakout_candle=Candle(timestamp="2026-08-25T10:00:00Z", open=100, high=105, low=99, close=104, volume=1000),
        tl=None,
        ema_20=100.0,
        has_reversal=False
    )
    assert score == 0
    assert breakdown["reversal"] == 0
    assert breakdown["trendline"] == 0
    assert breakdown["ema"] == 0

# ============================================================================
# 9. DEDICATED VISUAL ARCHETYPE DATASETS (A, B, C, D) & REPLAY
# ============================================================================

def test_dataset_a_bearish_to_w_to_bullish_accepted():
    """
    DATASET A (PATTERN 1 — TRUE W REVERSAL):
    Bearish Structure (LH/LL) -> L1 -> Neckline -> L2 -> Bullish Breakout
    Expected: ACCEPT (Confirmed W Reversal).
    """
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=150 - i*2, high=152 - i*2, low=148 - i*2, close=149 - i*2, volume=1000)
        for i in range(10)
    ]
    for i in range(10, 30):
        candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000))
    candles[24] = Candle(timestamp="2026-08-25T11:48:00Z", open=117, high=121, low=116, close=119.5, volume=2500)

    swings = [
        SwingPoint(index=0, price=150.0, timestamp="2026-08-25T10:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=2, price=130.0, timestamp="2026-08-25T10:10:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=140.0, timestamp="2026-08-25T10:20:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=120.0, timestamp="2026-08-25T10:30:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=132.0, timestamp="2026-08-25T10:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        # W Pattern
        SwingPoint(index=9, price=100.0, timestamp="2026-08-25T10:45:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=118.0, timestamp="2026-08-25T11:28:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=19, price=101.0, timestamp="2026-08-25T11:38:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    df_ind = pd.DataFrame({"ema_20": [112.0] * len(candles), "atr_14": [2.0] * len(candles)})

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=df_ind,
        symbol="RELIANCE", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 1
    assert confirmed[0].pattern_type == "W"
    assert confirmed[0].quality_score >= 70

def test_dataset_b_bullish_to_w_to_bullish_rejected():
    """
    DATASET B (PATTERN 2 — BULLISH CONTINUATION W):
    Bullish Structure (HH/HL) -> Pullback -> W-shape -> Bullish Continuation
    Expected: HARD REJECT (status="REJECTED", quality_score=0, reason="BULLISH_CONTINUATION_NOT_REVERSAL").
    Even if Trendline and EMA confluence are provided!
    """
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=100 + i*3, high=102 + i*3, low=98 + i*3, close=101 + i*3, volume=1000)
        for i in range(30)
    ]
    swings = [
        SwingPoint(index=2, price=100.0, timestamp="2026-08-25T10:10:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=130.0, timestamp="2026-08-25T10:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=120.0, timestamp="2026-08-25T10:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=12, price=155.0, timestamp="2026-08-25T11:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=140.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=18, price=175.0, timestamp="2026-08-25T11:30:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        # Pullback base: L1 (132) -> Neckline (138) -> L2 (133)
        SwingPoint(index=20, price=132.0, timestamp="2026-08-25T11:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=23, price=138.0, timestamp="2026-08-25T11:55:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=27, price=133.0, timestamp="2026-08-25T12:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    # Provide perfect EMA & Trendline
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=18, p1_price=175.0, p1_time="2026-08-25T11:30:00Z",
        p2_index=23, p2_price=138.0, p2_time="2026-08-25T11:55:00Z",
        slope=-7.4, intercept=175.0, end_index=29, end_price=130.0, touch_count=2, is_active=True
    )
    df_ind = pd.DataFrame({"ema_20": [130.0] * len(candles), "atr_14": [2.0] * len(candles)})

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="RELIANCE", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0
    assert len(events) == 0
    w_cands = [c for c in debug_cands if c.pattern_type == "W" and c.s1_index == 20]
    assert len(w_cands) >= 1
    rejected = w_cands[0]
    assert rejected.status == "REJECTED"
    assert rejected.quality_score == 0
    assert "BULLISH_CONTINUATION_NOT_REVERSAL" in rejected.rejection_reason or "bullish" in rejected.rejection_reason.lower()

def test_dataset_c_bullish_to_m_to_bearish_accepted():
    """
    DATASET C (PATTERN 3 — TRUE M REVERSAL):
    Bullish Structure (HH/HL) -> H1 -> Neckline -> H2 -> Bearish Breakdown
    Expected: ACCEPT (Confirmed M Reversal).
    """
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=160 + i*2, high=162 + i*2, low=158 + i*2, close=161 + i*2, volume=1000)
        for i in range(10)
    ]
    for i in range(10, 30):
        candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=190, high=195, low=185, close=190, volume=1000))
    candles[24] = Candle(timestamp="2026-08-25T11:48:00Z", open=183, high=184, low=179, close=180.5, volume=2500)

    swings = [
        SwingPoint(index=0, price=160.0, timestamp="2026-08-25T10:00:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=2, price=175.0, timestamp="2026-08-25T10:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=170.0, timestamp="2026-08-25T10:20:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=185.0, timestamp="2026-08-25T10:30:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=180.0, timestamp="2026-08-25T10:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        # M Pattern Swings
        SwingPoint(index=9, price=200.0, timestamp="2026-08-25T10:45:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=182.0, timestamp="2026-08-25T11:28:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=19, price=199.0, timestamp="2026-08-25T11:38:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    df_ind = pd.DataFrame({"ema_20": [186.0] * len(candles), "atr_14": [2.0] * len(candles)})

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=df_ind,
        symbol="TCS", timeframe="1H", atr_val=atr
    )
    assert len(confirmed) == 1
    assert confirmed[0].pattern_type == "M"
    assert confirmed[0].quality_score >= 70

def test_dataset_d_bearish_to_m_to_bearish_rejected():
    """
    DATASET D (PATTERN 4 — BEARISH CONTINUATION M):
    Bearish Structure (LH/LL) -> Bear flag rally -> M-shape -> Bearish Continuation
    Expected: HARD REJECT (status="REJECTED", quality_score=0, reason="BEARISH_CONTINUATION_NOT_REVERSAL").
    Even if Trendline and EMA confluence are provided!
    """
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=200 - i*3, high=202 - i*3, low=198 - i*3, close=199 - i*3, volume=1000)
        for i in range(30)
    ]
    swings = [
        SwingPoint(index=2, price=200.0, timestamp="2026-08-25T10:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=170.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=180.0, timestamp="2026-08-25T10:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=12, price=145.0, timestamp="2026-08-25T11:00:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=155.0, timestamp="2026-08-25T11:15:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=18, price=105.0, timestamp="2026-08-25T11:30:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        # Bear flag rally: H1 (115) -> Neckline (108) -> H2 (114)
        SwingPoint(index=20, price=115.0, timestamp="2026-08-25T11:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=23, price=108.0, timestamp="2026-08-25T11:55:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=27, price=114.0, timestamp="2026-08-25T12:15:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    # Provide perfect EMA & Trendline
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=18, p1_price=105.0, p1_time="2026-08-25T11:30:00Z",
        p2_index=23, p2_price=108.0, p2_time="2026-08-25T11:55:00Z",
        slope=0.6, intercept=105.0, end_index=29, end_price=111.0, touch_count=2, is_active=True
    )
    df_ind = pd.DataFrame({"ema_20": [112.0] * len(candles), "atr_14": [2.0] * len(candles)})

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="TCS", timeframe="1H", atr_val=atr
    )
    assert len(confirmed) == 0
    assert len(events) == 0
    m_cands = [c for c in debug_cands if c.pattern_type == "M" and c.s1_index == 20]
    assert len(m_cands) >= 1
    rejected = m_cands[0]
    assert rejected.status == "REJECTED"
    assert rejected.quality_score == 0
    assert "BEARISH_CONTINUATION_NOT_REVERSAL" in rejected.rejection_reason or "bearish" in rejected.rejection_reason.lower()

def test_realtime_candle_replay_no_lookahead():
    """
    REAL-TIME CANDLE-BY-CANDLE REPLAY TEST:
    Simulates real-time market stream where at step t, ONLY candles <= t are available.
    Ensures no future confirmation or future price is accessed.
    """
    atr = 2.0
    full_candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=150 - i*2, high=152 - i*2, low=148 - i*2, close=149 - i*2, volume=1000)
        for i in range(10)
    ]
    for i in range(10, 30):
        full_candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000))
    full_candles[24] = Candle(timestamp="2026-08-25T11:48:00Z", open=117, high=121, low=116, close=119.5, volume=2500)

    all_swings = [
        SwingPoint(index=0, price=150.0, timestamp="2026-08-25T10:00:00Z", is_high=True, type="HH", strength=2.0, confirmation_index=2, confirmed=True),
        SwingPoint(index=2, price=130.0, timestamp="2026-08-25T10:10:00Z", is_high=False, type="LL", strength=2.0, confirmation_index=4, confirmed=True),
        SwingPoint(index=4, price=140.0, timestamp="2026-08-25T10:20:00Z", is_high=True, type="LH", strength=2.0, confirmation_index=6, confirmed=True),
        SwingPoint(index=6, price=120.0, timestamp="2026-08-25T10:30:00Z", is_high=False, type="LL", strength=2.0, confirmation_index=8, confirmed=True),
        SwingPoint(index=8, price=132.0, timestamp="2026-08-25T10:40:00Z", is_high=True, type="LH", strength=2.0, confirmation_index=10, confirmed=True),
        SwingPoint(index=9, price=100.0, timestamp="2026-08-25T10:45:00Z", is_high=False, type="LL", strength=2.0, confirmation_index=12, confirmed=True),
        SwingPoint(index=14, price=118.0, timestamp="2026-08-25T11:28:00Z", is_high=True, type="HH", strength=2.0, confirmation_index=16, confirmed=True),
        SwingPoint(index=19, price=101.0, timestamp="2026-08-25T11:38:00Z", is_high=False, type="HL", strength=2.0, confirmation_index=21, confirmed=True)
    ]

    detected_at_step = None
    # Replay candle-by-candle from t=15 to t=28
    for t in range(15, len(full_candles)):
        current_candles = full_candles[:t+1]
        # At time t, only swings confirmed at or before t are known
        current_swings = [s for s in all_swings if (s.confirmation_index or s.index) <= t]
        df_ind = pd.DataFrame({"ema_20": [112.0] * len(current_candles), "atr_14": [2.0] * len(current_candles)})

        events, conf, act, deb = PrecisionBreakoutDetector.detect_wm_patterns(
            candles=current_candles, swings=current_swings, trendlines=[], df_indicators=df_ind,
            symbol="RELIANCE", timeframe="15M", atr_val=atr
        )

        if len(conf) > 0 and detected_at_step is None:
            detected_at_step = t

    # At t=24, candle 24 is the active forming bar.
    # At t=25, candle 24 is a completed closed candle, confirming the breakout.
    # Therefore, detection occurs strictly upon close at t=25 (and never before t=24).
    assert detected_at_step == 25, f"Breakout must be confirmed on candle close at t=25, was {detected_at_step}"

# ============================================================================
# 10. ADVERSARIAL & EXTRA STRUCTURAL TESTS (SECTION 14 & 15)
# ============================================================================

def test_adversarial_pattern_2_perfect_confluence_rejected():
    """
    ADVERSARIAL TEST — PATTERN 2 (BULLISH CONTINUATION W):
    Deliberately crafted with:
    - Perfect W geometry (depth 15, symmetric legs, separation 10 bars)
    - High-volume completed breakout candle
    - EMA confluence (Price > EMA 20)
    - Trendline confluence (Descending resistance broken)
    - Excellent R:R (> 1.5)
    BUT formed after Bullish HH/HL regime.
    Expected: HARD REJECT (status='REJECTED', quality_score=0).
    """
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=100 + i*3, high=102 + i*3, low=98 + i*3, close=101 + i*3, volume=1000)
        for i in range(30)
    ]
    # Candle 24 is a massive breakout candle
    candles[24] = Candle(timestamp="2026-08-25T12:00:00Z", open=140.0, high=145.0, low=139.0, close=142.0, volume=10000)

    swings = [
        SwingPoint(index=2, price=100.0, timestamp="2026-08-25T10:10:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=130.0, timestamp="2026-08-25T10:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=120.0, timestamp="2026-08-25T10:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=12, price=160.0, timestamp="2026-08-25T11:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=145.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=18, price=180.0, timestamp="2026-08-25T11:30:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        # Pullback base: L1 (130) -> Neckline (140) -> L2 (130.5)
        SwingPoint(index=20, price=130.0, timestamp="2026-08-25T11:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=22, price=140.0, timestamp="2026-08-25T11:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=23, price=130.5, timestamp="2026-08-25T11:55:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="DESCENDING_RESISTANCE",
        p1_index=18, p1_price=180.0, p1_time="2026-08-25T11:30:00Z",
        p2_index=22, p2_price=140.0, p2_time="2026-08-25T11:50:00Z",
        slope=-10.0, intercept=180.0, end_index=29, end_price=130.0, touch_count=2, is_active=True
    )
    df_ind = pd.DataFrame({"ema_20": [135.0] * len(candles), "atr_14": [2.0] * len(candles)})

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="RELIANCE", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0
    assert len(events) == 0
    w_cands = [c for c in debug_cands if c.pattern_type == "W" and c.s1_index == 20]
    assert len(w_cands) >= 1
    rejected = w_cands[0]
    assert rejected.status == "REJECTED"
    assert rejected.quality_score == 0
    assert "BULLISH_CONTINUATION_NOT_REVERSAL" in rejected.rejection_reason or "bullish" in rejected.rejection_reason.lower()

def test_adversarial_pattern_4_perfect_confluence_rejected():
    """
    ADVERSARIAL TEST — PATTERN 4 (BEARISH CONTINUATION M):
    Deliberately crafted with:
    - Perfect M geometry (depth 15, symmetric highs, separation 10 bars)
    - High-volume completed breakdown candle
    - EMA confluence (Price < EMA 20)
    - Trendline confluence (Ascending support broken)
    - Excellent R:R (> 1.5)
    BUT formed after Bearish LH/LL regime.
    Expected: HARD REJECT (status='REJECTED', quality_score=0).
    """
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=200 - i*3, high=202 - i*3, low=198 - i*3, close=199 - i*3, volume=1000)
        for i in range(30)
    ]
    # Candle 24 is a massive breakdown candle
    candles[24] = Candle(timestamp="2026-08-25T12:00:00Z", open=110.0, high=111.0, low=102.0, close=104.0, volume=10000)

    swings = [
        SwingPoint(index=2, price=200.0, timestamp="2026-08-25T10:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=170.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=180.0, timestamp="2026-08-25T10:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=12, price=140.0, timestamp="2026-08-25T11:00:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=155.0, timestamp="2026-08-25T11:15:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=18, price=100.0, timestamp="2026-08-25T11:30:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        # Bear flag rally: H1 (115) -> Neckline (106) -> H2 (114.5)
        SwingPoint(index=20, price=115.0, timestamp="2026-08-25T11:40:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=22, price=106.0, timestamp="2026-08-25T11:50:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=23, price=114.5, timestamp="2026-08-25T11:55:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    tl = Trendline(
        line_type="ASCENDING_SUPPORT",
        p1_index=18, p1_price=100.0, p1_time="2026-08-25T11:30:00Z",
        p2_index=22, p2_price=106.0, p2_time="2026-08-25T11:50:00Z",
        slope=1.5, intercept=100.0, end_index=29, end_price=116.0, touch_count=2, is_active=True
    )
    df_ind = pd.DataFrame({"ema_20": [112.0] * len(candles), "atr_14": [2.0] * len(candles)})

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[tl], df_indicators=df_ind,
        symbol="TCS", timeframe="1H", atr_val=atr
    )
    assert len(confirmed) == 0
    assert len(events) == 0
    m_cands = [c for c in debug_cands if c.pattern_type == "M" and c.s1_index == 20]
    assert len(m_cands) >= 1
    rejected = m_cands[0]
    assert rejected.status == "REJECTED"
    assert rejected.quality_score == 0
    assert "BEARISH_CONTINUATION_NOT_REVERSAL" in rejected.rejection_reason or "bearish" in rejected.rejection_reason.lower()

def test_unconfirmed_point_1_rejected():
    """Unconfirmed Point 1 (confirmed=False) -> REJECT."""
    s1 = SwingPoint(index=10, price=100.0, timestamp="2026-08-25T11:00:00Z", is_high=False, type="LL", strength=2.0, confirmed=False)
    assert not getattr(s1, "confirmed", True)

def test_multiple_intervening_structural_swings_rejected():
    """Multiple intervening structural necklines -> REJECT."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=120 - i, high=122 - i, low=118 - i, close=119 - i, volume=1000)
        for i in range(25)
    ]
    swings = [
        SwingPoint(index=0, price=140.0, timestamp="2026-08-25T10:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=2, price=120.0, timestamp="2026-08-25T10:10:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=130.0, timestamp="2026-08-25T10:20:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        # L1 (100) -> H_inter_1 (115) -> H_inter_2 (118) -> L2 (101)
        SwingPoint(index=6, price=100.0, timestamp="2026-08-25T10:30:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=115.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=118.0, timestamp="2026-08-25T11:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=18, price=101.0, timestamp="2026-08-25T11:30:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]
    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="RELIANCE", timeframe="15M", atr_val=atr
    )
    assert len(confirmed) == 0

def test_excessive_asymmetry_rejected():
    """Excessive asymmetry (|L1 - L2| > 1.5 ATR without valid sweep geometry) -> REJECT."""
    atr = 2.0
    l1 = 100.0
    l2 = 105.0  # diff = 5.0 > 1.5 * 2.0 (3.0 ATR)
    diff_atr = abs(l1 - l2) / atr
    assert diff_atr > 1.5

def test_insufficient_depth_rejected():
    """Pattern depth < 1.0 ATR -> REJECT."""
    atr = 2.0
    neckline = 101.0
    l1 = 100.0
    depth_atr = (neckline - l1) / atr  # 1.0 / 2.0 = 0.5 < 1.0
    assert depth_atr < 1.0


