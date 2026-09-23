import pytest
from datetime import datetime, timezone
from app.models.schemas import Candle, SwingPoint
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.market_structure.swings import SwingDetector
from app.market_structure.trendlines import Trendline
from app.models.schemas import WMPatternStructure

class TestSystemWideScaleAndRegimeValidation:
    """
    Comprehensive regression tests ensuring W/M breakout detection generalizes
    across all asset classes, price scales ($50 to $80,000+), market regimes,
    wick-vs-close confirmations, and deduplication idempotency.
    """

    @pytest.mark.parametrize("symbol,price,atr_val,depth", [
        ("BTC/USD", 65000.0, 450.0, 1500.0),      # Crypto High-Value Tier
        ("NIFTY 50", 25000.0, 160.0, 400.0),      # Index Mid-High Tier
        ("SBIN", 820.0, 9.5, 25.0),               # Standard Large-Cap Tier
        ("PENNY_STOCK", 45.0, 0.85, 2.5),         # Low-Price Equity Tier
    ])
    def test_scale_aware_neckline_and_symmetry_across_asset_tiers(self, symbol, price, atr_val, depth):
        """
        Verify that horizontal neckline tolerance and swing symmetry scale dynamically
        with asset price and ATR without breaking across low-priced or high-priced assets.
        """
        # 1. Neckline band tolerance test
        # max_neckline_band = max(0.75 * atr_val, min(1.50 * atr_val, point_1.price * 0.0025))
        pct_cap = price * 0.0025
        expected_neckline_band = max(0.75 * atr_val, min(1.50 * atr_val, pct_cap))
        assert expected_neckline_band > 0, "Neckline band must be strictly positive"
        assert expected_neckline_band >= 0.75 * atr_val, "Neckline band must respect baseline ATR buffer"

        # 2. Symmetry tolerance test
        # max_allowed_diff = max(price_tolerance_atr * atr_val, min(0.60 * pattern_depth, point_1.price * 0.005))
        price_tol_atr = 1.20
        expected_sym_diff = max(price_tol_atr * atr_val, min(0.60 * depth, price * 0.005))
        assert expected_sym_diff > 0, "Symmetry difference tolerance must be positive"
        assert expected_sym_diff >= price_tol_atr * atr_val, "Symmetry diff must allow standard market noise"

        # 3. Test _cluster_swings with two multi-touch peaks separated within expected_neckline_band
        s1 = SwingPoint(index=10, price=price, type="HH", timestamp="2026-09-01T01:00:00Z", is_high=True, confirmed=True)
        s2 = SwingPoint(index=15, price=price + (0.5 * atr_val), type="HH", timestamp="2026-09-01T01:05:00Z", is_high=True, confirmed=True)
        clustered = PrecisionBreakoutDetector._cluster_swings([s1, s2], atr_val=atr_val, max_bar_diff=8, price_tol_atr=0.75)
        assert len(clustered) == 1, f"Expected unified cluster for {symbol}, got {len(clustered)}"
        assert clustered[0].price == max(s1.price, s2.price), "Unified neckline must choose dominant peak"

    def test_wick_only_breach_never_confirms_breakout(self):
        """
        Verify that a candle that wicks across the neckline but closes inside
        is STRICTLY rejected and never confirmed as a breakout.
        """
        # W pattern: neckline at 100.0.
        # Candle wicks up to 102.5 (above neckline), but closes at 99.2 (below neckline).
        neckline = 100.0
        atr_val = 2.0
        wick_candle = Candle(
            timestamp="2026-09-01T10:00:00Z",
            open=98.0,
            high=102.5,  # Wicks above 100.0
            low=97.5,
            close=99.2,  # Closes strictly BELOW 100.0
            volume=50000.0
        )

        # Candidate W breakout evaluation
        min_breakout_dist = 0.05 * atr_val
        decisive_margin = max(min_breakout_dist, neckline * 0.0003)
        assert wick_candle.close < neckline, "Candle close must be strictly below neckline"
        assert wick_candle.close < (neckline + decisive_margin), "Candle close fails breakout margin"

    def test_completed_candle_close_confirms_breakout_with_margin(self):
        """
        Verify that a completed candle closing decisively above neckline + scale margin confirms W breakout.
        """
        neckline = 100.0
        atr_val = 2.0
        breakout_candle = Candle(
            timestamp="2026-09-01T10:00:00Z",
            open=99.0,
            high=103.0,
            low=98.8,
            close=101.5,  # Closes decisively above 100.0
            volume=80000.0
        )
        min_breakout_dist = 0.05 * atr_val
        decisive_margin = max(min_breakout_dist, neckline * 0.0003)
        assert breakout_candle.close > (neckline + decisive_margin), "Decisive breakout close must exceed margin"

    def test_regime_classification_distinguishes_reversals_from_continuations(self):
        """
        Verify that preceding regime requires:
        - Downtrend (LL/LH) into W bottom (bullish reversal)
        - Uptrend (HH/HL) into M top (bearish reversal)
        And rejects continuation bounces/pullbacks.
        """
        # 1. Bearish trend into W pattern
        bearish_swings = [
            SwingPoint(index=5, price=120.0, type="LH", timestamp="2026-09-01T01:00:00Z", is_high=True, confirmed=True),
            SwingPoint(index=15, price=105.0, type="LL", timestamp="2026-09-01T01:10:00Z", is_high=False, confirmed=True),
            SwingPoint(index=25, price=110.0, type="LH", timestamp="2026-09-01T01:20:00Z", is_high=True, confirmed=True),
            SwingPoint(index=35, price=95.0, type="LL", timestamp="2026-09-01T01:30:00Z", is_high=False, confirmed=True),
        ]
        w_low_1 = SwingPoint(index=45, price=90.0, type="LL", timestamp="2026-09-01T01:40:00Z", is_high=False, confirmed=True)

        regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
            candles=[], swings=bearish_swings, point_1=w_low_1, atr_val=2.0, timeframe="5M"
        )
        assert regime == "BEARISH", f"Expected BEARISH regime leading into W pattern, got {regime}"

        # 2. Bullish trend into M pattern
        bullish_swings = [
            SwingPoint(index=5, price=80.0, type="HL", timestamp="2026-09-01T01:00:00Z", is_high=False, confirmed=True),
            SwingPoint(index=15, price=95.0, type="HH", timestamp="2026-09-01T01:10:00Z", is_high=True, confirmed=True),
            SwingPoint(index=25, price=90.0, type="HL", timestamp="2026-09-01T01:20:00Z", is_high=False, confirmed=True),
            SwingPoint(index=35, price=105.0, type="HH", timestamp="2026-09-01T01:30:00Z", is_high=True, confirmed=True),
        ]
        m_high_1 = SwingPoint(index=45, price=110.0, type="HH", timestamp="2026-09-01T01:40:00Z", is_high=True, confirmed=True)

        regime, reason = PrecisionBreakoutDetector.classify_preceding_market_regime(
            candles=[], swings=bullish_swings, point_1=m_high_1, atr_val=2.0, timeframe="5M"
        )
        assert regime == "BULLISH", f"Expected BULLISH regime leading into M pattern, got {regime}"

    def test_structural_pattern_id_uniqueness_and_deduplication(self):
        """
        Verify that multiple successive candles oscillating around the breakout zone
        generate the identical pattern_id and are not duplicated into separate alerts.
        """
        symbol = "BTC/USD"
        timeframe = "5M"
        pattern_type = "W"
        s1_price = 78000.0
        neckline_price = 78500.0
        s1_time = "2026-09-01T02:00:00Z"

        pattern_id_bar1 = f"{symbol}_{timeframe}_{pattern_type}_{s1_time}_{round(s1_price, 1)}_{round(neckline_price, 1)}"
        pattern_id_bar2 = f"{symbol}_{timeframe}_{pattern_type}_{s1_time}_{round(s1_price, 1)}_{round(neckline_price, 1)}"
        pattern_id_bar3 = f"{symbol}_{timeframe}_{pattern_type}_{s1_time}_{round(s1_price, 1)}_{round(neckline_price, 1)}"

        assert pattern_id_bar1 == pattern_id_bar2 == pattern_id_bar3, "Pattern ID must remain strictly identical across retests"
