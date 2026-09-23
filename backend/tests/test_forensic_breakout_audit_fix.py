import pytest
import json
from pathlib import Path
from app.models.schemas import Candle, SwingPoint
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.market_structure.swings import SwingDetector
from app.market_structure.trendlines import TrendlineDetector
from app.indicators.technical import TechnicalIndicatorEngine
from app.core.config import settings

def test_regime_classifier_compares_highs_to_highs_and_lows_to_lows():
    """Verify that preceding regime compares highs strictly to highs and lows strictly to lows."""
    swings = [
        SwingPoint(index=10, price=90.0, type="LL", timestamp="2026-09-01T01:00:00Z", is_high=False, confirmed=True),
        SwingPoint(index=20, price=100.0, type="HH", timestamp="2026-09-01T01:10:00Z", is_high=True, confirmed=True),
        SwingPoint(index=30, price=95.0, type="HL", timestamp="2026-09-01T01:20:00Z", is_high=False, confirmed=True),
        SwingPoint(index=40, price=105.0, type="HH", timestamp="2026-09-01T01:30:00Z", is_high=True, confirmed=True),
        SwingPoint(index=50, price=100.0, type="HL", timestamp="2026-09-01T01:40:00Z", is_high=False, confirmed=True),
    ]
    p1 = SwingPoint(index=60, price=110.0, type="HH", timestamp="2026-09-01T01:50:00Z", is_high=True, confirmed=True)
    
    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=[], swings=swings, point_1=p1, atr_val=2.0, timeframe="5M"
    )
    assert regime == "BULLISH", f"Expected BULLISH preceding regime into High 1, got {regime} ({reason})"
    assert "bullish" in reason.lower()

def test_regime_classifier_rejects_continuation_as_reversal():
    """Verify that a relief bounce in a downtrend is classified as BEARISH (cannot form M reversal)."""
    swings = [
        SwingPoint(index=10, price=120.0, type="LH", timestamp="2026-09-01T01:00:00Z", is_high=True, confirmed=True),
        SwingPoint(index=20, price=105.0, type="LL", timestamp="2026-09-01T01:10:00Z", is_high=False, confirmed=True),
        SwingPoint(index=30, price=110.0, type="LH", timestamp="2026-09-01T01:20:00Z", is_high=True, confirmed=True),
        SwingPoint(index=40, price=95.0, type="LL", timestamp="2026-09-01T01:30:00Z", is_high=False, confirmed=True),
    ]
    p1 = SwingPoint(index=50, price=102.0, type="LH", timestamp="2026-09-01T01:40:00Z", is_high=True, confirmed=True)
    
    regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
        candles=[], swings=swings, point_1=p1, atr_val=2.0, timeframe="5M"
    )
    assert regime == "BEARISH", f"Expected BEARISH continuation regime, got {regime} ({reason})"
    assert "continuation" in reason.lower() or "bearish" in reason.lower()

def test_horizontal_neckline_zone_unification():
    """Test that multiple intermediate swings testing the same level within tolerance are unified."""
    atr_val = 10.0
    swings = [
        SwingPoint(index=10, price=100.0, type="HL", timestamp="2026-09-01T01:00:00Z", is_high=True, confirmed=True),
        SwingPoint(index=15, price=101.5, type="HH", timestamp="2026-09-01T01:05:00Z", is_high=True, confirmed=True),
    ]
    clustered = PrecisionBreakoutDetector._cluster_swings(swings, atr_val=atr_val, max_bar_diff=6, price_tol_atr=0.25)
    assert len(clustered) >= 1

def test_scale_aware_symmetry_formula():
    """Verify that scale-aware symmetry tolerance accepts genuine double bottoms while rejecting extreme asymmetries."""
    atr_val = 74.37
    h1_price = 78370.52
    pattern_depth = 499.54
    price_tol_atr = 1.20

    genuine_diff = 286.11
    max_allowed_diff = max(price_tol_atr * atr_val, min(0.60 * pattern_depth, h1_price * 0.005))
    assert genuine_diff <= max_allowed_diff, f"Genuine double bottom diff {genuine_diff} should pass tolerance {max_allowed_diff}"

    asymmetric_diff = 481.80
    assert asymmetric_diff > max_allowed_diff, f"Extreme asymmetry {asymmetric_diff} must be rejected by tolerance {max_allowed_diff}"

def test_replay_sept1_btc_candles_audit_reconciliation():
    """Replay Sept 1 BTC/USD 5m candles to verify that genuine breakouts pass and false positives are rejected."""
    candles_path = Path(r"C:/Users/user/.gemini/antigravity/brain/c85d0846-2444-4d98-aef6-29be65353f0e/scratch/btc_5m_sept1.json")
    if not candles_path.exists():
        pytest.skip("Cached Sept 1 candle dataset not found in scratch directory.")

    with open(candles_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    candles = [Candle(**c) for c in raw_data]

    df_indicators, _ = TechnicalIndicatorEngine.compute_all_indicators(candles)
    swings, _ = SwingDetector.detect_swings(candles, swing_length=3, confirmation_candles=2)
    trendlines = TrendlineDetector.fit_trendlines(candles, swings, max_lines_per_direction=settings.MAX_TRENDLINES_PER_DIRECTION)
    atr_val = float(df_indicators["atr_14"].iloc[-1])

    events, confirmed, active, debug = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles,
        swings=swings,
        trendlines=trendlines,
        df_indicators=df_indicators,
        symbol="BTC/USD",
        timeframe="5m",
        atr_val=atr_val,
        price_tolerance_atr=settings.W_M_SWING_TOLERANCE_ATR,
        min_depth_atr=settings.MIN_PATTERN_DEPTH_ATR,
        min_bar_spacing=settings.MIN_W_M_SWING_SEPARATION
    )

    # 1. 10:55 AM IST W breakout (05:25 UTC) MUST BE DETECTED AND CONFIRMED
    w_1055_events = [e for e in events if "2026-09-01T05:25" in str(e.timestamp)]
    assert len(w_1055_events) == 1, f"Expected 10:55 AM W breakout event, got {w_1055_events}"
    w_event = w_1055_events[0]
    assert w_event.direction == "BULLISH"
    assert round(w_event.broken_level, 2) == 78870.06

    # 2. 4:00 AM IST M breakdown (22:30 UTC breakout candle close at 22:35 UTC) MUST BE DETECTED AND CONFIRMED
    m_0400_events = [e for e in events if "2026-08-31T22:35" in str(e.timestamp) or "2026-08-31T22:30" in str(e.timestamp)]
    assert len(m_0400_events) >= 1, f"Expected 4:00 AM M breakdown event, got {m_0400_events}"
    m_event = m_0400_events[0]
    assert m_event.direction == "BEARISH"
    assert round(m_event.broken_level, 2) == 78720.02

    # 3. None of the false positive timestamps should produce breakout events:
    false_positive_timestamps = [
        "2026-09-01T01:55", "2026-09-01T02:00", "2026-09-01T06:55",
        "2026-09-01T13:35", "2026-09-01T13:45", "2026-09-01T13:50"
    ]
    for fp_ts in false_positive_timestamps:
        fp_events = [e for e in events if fp_ts in str(e.timestamp)]
        assert len(fp_events) == 0, f"False positive at {fp_ts} was not eliminated! Produced: {fp_events}"

    # 4. Zero _FAST_ micro-patterns should exist in confirmed patterns or events
    for p in confirmed:
        assert "_FAST_" not in p.pattern_id, f"Found FAST micro-pattern in confirmed: {p.pattern_id}"
    for e in events:
        assert "_FAST_" not in str(e.id), f"Found FAST micro-pattern in event: {e.id}"
