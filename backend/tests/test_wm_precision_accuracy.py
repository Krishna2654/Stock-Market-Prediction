import pytest
import pandas as pd
from app.models.schemas import Candle, SwingPoint
from app.market_structure.trendlines import Trendline
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.alerts.mw_breakout_engine import MWBreakoutAlertEngine

@pytest.fixture(autouse=True)
def isolate_store(tmp_path, monkeypatch):
    monkeypatch.setattr("app.alerts.mw_breakout_engine.STORAGE_FILE", tmp_path / "test_mw_store.json")

def test_w_structural_breakout_complete():
    """1. W structural test: Preceding down move -> Low 1 -> Neckline -> Low 2 -> confirmed close above neckline."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=120 - i*2, high=122 - i*2, low=118 - i*2, close=119 - i*2, volume=1000)
        for i in range(5)
    ]
    # Candle 0 has high=122, down into Low 1 at index 4 (price=100.0) -> disp = 22.0 >= max(4.0, 1.2)
    candles[4] = Candle(timestamp="2026-08-25T10:20:00Z", open=105, high=106, low=100, close=101, volume=1000)
    for i in range(5, 25):
        candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000))
    # Neckline at index 10 (price=118.0), Low 2 at index 15 (price=101.0)
    # Breakout candle at index 18 (close=121.0 > 118.0)
    candles[18] = Candle(timestamp="2026-08-25T11:36:00Z", open=117, high=123, low=116, close=121, volume=2500)

    swings = [
        SwingPoint(index=4, price=100.0, timestamp="2026-08-25T10:20:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=118.0, timestamp="2026-08-25T11:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=101.0, timestamp="2026-08-25T11:20:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="RELIANCE", timeframe="15M", atr_val=atr
    )

    assert len(confirmed) == 1
    pat = confirmed[0]
    assert pat.pattern_type == "W"
    assert pat.s1_price == 100.0
    assert pat.neckline_price == 118.0
    assert pat.s2_price == 101.0
    assert pat.breakout_candle_index == 18
    assert pat.breakout_candle_index > pat.s2_index, "Breakout candle must strictly occur AFTER Point 2"
    # Target 1 & 2
    assert pat.target_analysis.measured_target == 118.0 + 18.0  # 136.0
    assert pat.target_analysis.target_2 == round(118.0 + 1.618 * 18.0, 2)  # 147.12
    # Stop Loss strictly below Low 2
    assert pat.target_analysis.invalidation_level < pat.s2_price
    assert pat.target_analysis.invalidation_level < pat.neckline_price

def test_m_structural_breakdown_complete():
    """2. M structural test: Preceding up move -> High 1 -> Neckline -> High 2 -> confirmed close below neckline."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=180 + i*2, high=182 + i*2, low=178 + i*2, close=181 + i*2, volume=1000)
        for i in range(5)
    ]
    candles[4] = Candle(timestamp="2026-08-25T10:20:00Z", open=195, high=200, low=194, close=199, volume=1000)
    for i in range(5, 25):
        candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=190, high=195, low=185, close=190, volume=1000))
    candles[18] = Candle(timestamp="2026-08-25T11:36:00Z", open=183, high=184, low=176, close=178, volume=2500)

    swings = [
        SwingPoint(index=4, price=200.0, timestamp="2026-08-25T10:20:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=182.0, timestamp="2026-08-25T11:10:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=199.0, timestamp="2026-08-25T11:20:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="TCS", timeframe="1H", atr_val=atr
    )

    assert len(confirmed) == 1
    pat = confirmed[0]
    assert pat.pattern_type == "M"
    assert pat.s1_price == 200.0
    assert pat.neckline_price == 182.0
    assert pat.s2_price == 199.0
    assert pat.breakout_candle_index == 18
    assert pat.breakout_candle_index > pat.s2_index
    # Target 1 & 2
    assert pat.target_analysis.measured_target == 182.0 - 18.0  # 164.0
    assert pat.target_analysis.target_2 == round(182.0 - 1.618 * 18.0, 2)  # 152.88
    # Stop Loss strictly above High 2
    assert pat.target_analysis.invalidation_level > pat.s2_price
    assert pat.target_analysis.invalidation_level > pat.neckline_price

def test_sideways_and_preceding_trend_rejection():
    """3 & 5. Reject sideways consolidation and patterns lacking meaningful preceding trend."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=100.5, high=101.5, low=99.8, close=100.5, volume=1000)
        for i in range(25)
    ]
    swings = [
        SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=101.5, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=100.1, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="INFY", timeframe="5M", atr_val=atr
    )

    assert len(confirmed) == 0, "Sideways noise must be rejected"
    assert len(debug_cands) >= 1
    assert debug_cands[0].status == "REJECTED"

def test_small_swing_rejection():
    """4. Reject tiny swings where leg amplitude is smaller than required minimum."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=120 - i*3, high=122 - i*3, low=118 - i*3, close=119 - i*3, volume=1000)
        for i in range(5)
    ]
    for i in range(5, 25):
        candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=100, high=101, low=99.5, close=100, volume=1000))

    swings = [
        SwingPoint(index=4, price=100.0, timestamp="2026-08-25T10:20:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=100.5, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=100.1, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="SBIN", timeframe="5M", atr_val=atr
    )

    assert len(confirmed) == 0, "Tiny swings must be rejected"
    assert len(debug_cands) >= 1
    assert debug_cands[0].status == "REJECTED"

def test_wick_only_breakout_rejection():
    """7. Wick-only penetration beyond neckline is NOT a breakout."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=120 - i*2, high=122 - i*2, low=118 - i*2, close=119 - i*2, volume=1000)
        for i in range(5)
    ]
    candles[4] = Candle(timestamp="2026-08-25T10:20:00Z", open=105, high=106, low=100, close=101, volume=1000)
    for i in range(5, 25):
        candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000))
    candles[18] = Candle(timestamp="2026-08-25T11:36:00Z", open=115, high=124, low=114, close=117, volume=2500)

    swings = [
        SwingPoint(index=4, price=100.0, timestamp="2026-08-25T10:20:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=118.0, timestamp="2026-08-25T11:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=101.0, timestamp="2026-08-25T11:20:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="ICICIBANK", timeframe="15M", atr_val=atr
    )

    assert len(events) == 0, "Wick-only penetration must not emit a breakout event"
    assert len(confirmed) > 0
    pat = confirmed[0]
    assert pat.breakout_candle_index is None, "Wick-only penetration must not have a breakout candle"
    assert pat.status not in ["BREAKOUT_CONFIRMED", "HIGH_CONFLUENCE_CONFIRMED"], "Wick-only cannot be BREAKOUT_CONFIRMED"

def test_multi_symbol_configured_reachability():
    """13. Multi-symbol coverage: Verify configured symbols reach scanner with all 4 timeframes."""
    from app.core.config import settings
    expected_symbols = [
        "BTC/USD", "NIFTY 50", "BANK NIFTY", "RELIANCE",
        "HDFCBANK", "ICICIBANK", "TCS", "INFY", "SBIN", "BHARTI AIRTEL"
    ]
    configured_syms = [inst["symbol"] if isinstance(inst, dict) else inst.symbol for inst in settings.DEFAULT_INSTRUMENTS]
    for s in expected_symbols:
        assert s in configured_syms, f"Symbol {s} must be in DEFAULT_INSTRUMENTS"

    expected_tfs = ["5M", "15M", "1H", "4H"]
    for tf in expected_tfs:
        assert tf in settings.TIMEFRAMES, f"Timeframe {tf} must be in configured TIMEFRAMES"

def test_duplicate_prevention_on_repeated_synthesis():
    """14. Duplicate prevention: Repeated chart/synthesis syncs of the same breakout event emit exactly ONE alert."""
    from app.models.schemas import WMPatternStructure, PatternTargetAnalysis
    engine = MWBreakoutAlertEngine()
    engine.clear_alerts()

    pat = WMPatternStructure(
        pattern_id="test_dup_1",
        pattern_type="W",
        status="BREAKOUT_CONFIRMED",
        s1_index=5, s1_price=100.0, s1_time="2026-08-25T10:25:00Z",
        neckline_index=10, neckline_price=115.0, neckline_time="2026-08-25T10:50:00Z",
        s2_index=15, s2_price=101.0, s2_time="2026-08-25T11:15:00Z",
        pattern_height=15.0, depth_atr=7.5, symmetry_atr=0.5, bar_separation=10,
        quality_score=85,
        breakout_candle_index=18,
        breakout_candle_time="2026-08-25T11:30:00Z",
        breakout_close=116.0,
        target_analysis=PatternTargetAnalysis(
            pattern_height=15.0, measured_target=130.0, target_2=139.27, invalidation_level=100.7,
            retest_level=115.0, retest_status="PENDING", pattern_status="BREAKOUT_CONFIRMED",
            pattern_quality_score=85, quality_breakdown={}, interpretation="Test"
        ),
        symbol="BHARTI AIRTEL", timeframe="15M"
    )

    alert_1 = engine.sync_chart_patterns(
        symbol="BHARTI AIRTEL", timeframe="15M", confirmed_patterns=[pat], active_pattern=pat, candles=[]
    )
    assert alert_1 is not None, "First ingestion should create an alert"
    assert len(engine.get_alerts(symbol="BHARTI AIRTEL")) == 1

    # Second sync of exact same pattern
    alert_2 = engine.sync_chart_patterns(
        symbol="BHARTI AIRTEL", timeframe="15M", confirmed_patterns=[pat], active_pattern=pat, candles=[]
    )
    assert len(engine.get_alerts(symbol="BHARTI AIRTEL")) == 1

def test_single_source_of_truth_consistency():
    """15. Single Source of Truth: Canonical pattern object matches alert fields 100%."""
    from app.models.schemas import WMPatternStructure, PatternTargetAnalysis
    engine = MWBreakoutAlertEngine()
    engine.clear_alerts()

    pat = WMPatternStructure(
        pattern_id="test_truth_1",
        pattern_type="W",
        status="BREAKOUT_CONFIRMED",
        s1_index=5, s1_price=2400.0, s1_time="2026-08-25T10:25:00Z",
        neckline_index=10, neckline_price=2500.0, neckline_time="2026-08-25T10:50:00Z",
        s2_index=15, s2_price=2405.0, s2_time="2026-08-25T11:15:00Z",
        pattern_height=100.0, depth_atr=5.0, symmetry_atr=0.25, bar_separation=10,
        quality_score=88,
        breakout_candle_index=18,
        breakout_candle_time="2026-08-25T11:30:00Z",
        breakout_close=2510.0,
        target_analysis=PatternTargetAnalysis(
            pattern_height=100.0, measured_target=2600.0, target_2=2661.8, invalidation_level=2402.0,
            retest_level=2500.0, retest_status="PENDING", pattern_status="BREAKOUT_CONFIRMED",
            pattern_quality_score=88, quality_breakdown={}, interpretation="Truth Test"
        ),
        symbol="RELIANCE", timeframe="1H"
    )

    alert = engine.sync_chart_patterns(
        symbol="RELIANCE", timeframe="1H", confirmed_patterns=[pat], active_pattern=pat, candles=[]
    )
    assert alert is not None

    assert alert.s1_price == pat.s1_price
    assert alert.neckline_price == pat.neckline_price
    assert alert.s2_price == pat.s2_price
    assert alert.pattern_height == pat.pattern_height
    assert alert.measured_target == pat.target_analysis.measured_target
    assert alert.target_2 == pat.target_analysis.target_2
    assert alert.invalidation_level == pat.target_analysis.invalidation_level
    assert alert.quality_score == pat.quality_score

def test_reject_w_with_intervening_swing_low_between_l1_and_l2():
    """3 & 5. Reject W with an additional meaningful swing low between Low 1 and Low 2 (multi-wave structure)."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=120 - i*2, high=122 - i*2, low=118 - i*2, close=119 - i*2, volume=1000)
        for i in range(5)
    ]
    candles[4] = Candle(timestamp="2026-08-25T10:20:00Z", open=105, high=106, low=100, close=101, volume=1000)
    for i in range(5, 30):
        candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000))

    # Low 1 at index 4, Intermediate High at index 10, Intervening Low at index 14, High at 18, Low 2 at 22
    swings = [
        SwingPoint(index=4, price=100.0, timestamp="2026-08-25T10:20:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=118.0, timestamp="2026-08-25T11:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=105.0, timestamp="2026-08-25T11:18:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=18, price=117.0, timestamp="2026-08-25T11:26:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=22, price=101.0, timestamp="2026-08-25T11:34:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="15M", atr_val=atr
    )

    # Low 1 (idx 4) to Low 2 (idx 22) MUST NOT be paired because idx 14 is an intervening swing low!
    spanning_pats = [p for p in confirmed if p.s1_index == 4 and p.s2_index == 22]
    assert len(spanning_pats) == 0, "Spanning multi-wave W must be rejected"

    rejected_spanning = [c for c in debug_cands if c.s1_index == 4 and c.s2_index == 22]
    assert len(rejected_spanning) >= 1
    assert "Intervening structural swing low" in rejected_spanning[0].rejection_reason

def test_reject_m_with_intervening_swing_high_between_h1_and_h2():
    """4 & 6. Reject M with an additional meaningful swing high between High 1 and High 2 (multi-wave structure)."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=180 + i*2, high=182 + i*2, low=178 + i*2, close=181 + i*2, volume=1000)
        for i in range(5)
    ]
    candles[4] = Candle(timestamp="2026-08-25T10:20:00Z", open=195, high=200, low=194, close=199, volume=1000)
    for i in range(5, 30):
        candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=190, high=195, low=185, close=190, volume=1000))

    # High 1 at index 4, Intermediate Low at index 10, Intervening High at index 14, Low at 18, High 2 at 22
    swings = [
        SwingPoint(index=4, price=200.0, timestamp="2026-08-25T10:20:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=182.0, timestamp="2026-08-25T11:10:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=14, price=195.0, timestamp="2026-08-25T11:18:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=18, price=183.0, timestamp="2026-08-25T11:26:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=22, price=199.0, timestamp="2026-08-25T11:34:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="BANK NIFTY", timeframe="1H", atr_val=atr
    )

    # High 1 (idx 4) to High 2 (idx 22) MUST NOT be paired because idx 14 is an intervening swing high!
    spanning_pats = [p for p in confirmed if p.s1_index == 4 and p.s2_index == 22]
    assert len(spanning_pats) == 0, "Spanning multi-wave M must be rejected"

    rejected_spanning = [c for c in debug_cands if c.s1_index == 4 and c.s2_index == 22]
    assert len(rejected_spanning) >= 1
    assert "Intervening structural swing high" in rejected_spanning[0].rejection_reason

def test_reject_w_with_multiple_competing_necklines():
    """Reject W with multiple intermediate highs creating competing necklines."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=120 - i*2, high=122 - i*2, low=118 - i*2, close=119 - i*2, volume=1000)
        for i in range(5)
    ]
    candles[4] = Candle(timestamp="2026-08-25T10:20:00Z", open=105, high=106, low=100, close=101, volume=1000)
    for i in range(5, 25):
        candles.append(Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000))

    # Low 1 at index 4, High 1 at 10, High 2 at 13 (no swing low between them), Low 2 at 18
    swings = [
        SwingPoint(index=4, price=100.0, timestamp="2026-08-25T10:20:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=118.0, timestamp="2026-08-25T11:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=13, price=117.5, timestamp="2026-08-25T11:16:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=18, price=101.0, timestamp="2026-08-25T11:26:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="BTC/USD", timeframe="15M", atr_val=atr
    )

    assert len(confirmed) == 0, "Multiple intermediate necklines must be rejected"
    assert len(debug_cands) >= 1
    assert "Multiple intermediate structural highs" in debug_cands[0].rejection_reason


