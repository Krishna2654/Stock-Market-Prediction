import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.alerts.trendline_shortlist_engine import trendline_shortlist_engine, TrendlineShortlistEngine
from app.models.schemas import Candle, SwingPoint, MultiTimeframeSynthesis, SingleTimeframeAnalysis, TechnicalIndicators, SupportResistanceSummary, EvidenceScoreBreakdown

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_engine():
    trendline_shortlist_engine.clear_shortlist()
    yield
    trendline_shortlist_engine.clear_shortlist()

def test_trendline_shortlist_empty_state():
    """Verify endpoint returns empty list when no stocks are shortlisted."""
    res = client.get("/api/alerts/trendline-shortlist")
    assert res.status_code == 200
    assert res.json() == []

def test_reject_trendline_with_only_2_points():
    """Verify that candidate trendlines with only 2 points are strictly rejected."""
    # Synthetic synthesis with a trendline having only 2 touch points
    c1 = Candle(timestamp="2026-08-30T09:15:00Z", open=100.0, high=105.0, low=99.0, close=102.0, volume=1000)
    c2 = Candle(timestamp="2026-08-30T09:30:00Z", open=102.0, high=103.0, low=98.0, close=99.0, volume=1200)
    c3 = Candle(timestamp="2026-08-30T09:45:00Z", open=99.0, high=101.0, low=97.0, close=98.0, volume=1500)
    c4 = Candle(timestamp="2026-08-30T10:00:00Z", open=98.0, high=102.0, low=97.5, close=101.5, volume=2500)
    candles = [c1, c2, c3, c4] * 3  # 12 candles

    two_point_tl = {
        "line_type": "DESCENDING_RESISTANCE",
        "p1_index": 0,
        "p2_index": 4,
        "slope": -0.5,
        "intercept": 105.0,
        "touch_count": 2,  # Only 2 points!
        "touch_points": [
            {"index": 0, "timestamp": "2026-08-30T09:15:00Z", "price": 105.0},
            {"index": 4, "timestamp": "2026-08-30T09:30:00Z", "price": 103.0}
        ]
    }

    tf_analysis = SingleTimeframeAnalysis(
        timeframe="15M",
        trend="BULLISH",
        structure_type="Test",
        indicators=TechnicalIndicators(atr_14=2.0, relative_volume=1.5),
        support_resistance=SupportResistanceSummary(major_support=90.0, minor_support=95.0, current_price=101.5, minor_resistance=105.0, major_resistance=110.0, all_levels=[]),
        breakout_status="NONE",
        trendlines=[two_point_tl],
        candle_count=len(candles),
        latest_candle_time=candles[-1].timestamp
    )

    synth = MultiTimeframeSynthesis(
        symbol="RELIANCE",
        ticker="RELIANCE.NS",
        provider="yfinance",
        current_price=101.5,
        last_updated="2026-08-30T10:00:00Z",
        timeframes={"15M": tf_analysis},
        overall_bias="BULLISH",
        current_state="FULL BULLISH ALIGNMENT",
        evidence_score=EvidenceScoreBreakdown(total_score=80, category="Strong Evidence Alignment", structure_points=20, htf_alignment_points=20, momentum_points=15, volume_points=15, breakout_points=10, details=[]),
        confirmation_state="CONFIRMED",
        short_term_state="BULLISH",
        status_message="OK",
        is_stale=False,
        synthesis_rationale="Test rationale"
    )

    shortlisted = trendline_shortlist_engine.process_synthesis(synth, mtf_candles={"15M": candles})
    assert len(shortlisted) == 0, "Trendline with only 2 points must be strictly rejected from shortlisting"

def test_accept_strong_trendline_with_4_validated_points_and_r2():
    """Verify acceptance of a 4-point descending resistance breakout with R2 >= 0.95 and high score."""
    # Construct 15 candles
    candles = []
    base_price = 100.0
    for idx in range(15):
        # descending slope -0.5
        tl_val = 110.0 - 0.5 * idx
        if idx == 14:
            # Breakout candle: closes strongly above line
            c = Candle(timestamp=f"2026-08-30T{10+idx//4:02d}:{(idx%4)*15:02d}:00Z", open=tl_val - 0.2, high=tl_val + 2.0, low=tl_val - 0.5, close=tl_val + 1.8, volume=3500)
        else:
            c = Candle(timestamp=f"2026-08-30T{10+idx//4:02d}:{(idx%4)*15:02d}:00Z", open=tl_val - 0.8, high=tl_val, low=tl_val - 1.5, close=tl_val - 0.4, volume=1200)
        candles.append(c)

    # 4 clean touch points with perfect R2
    four_point_tl = {
        "line_type": "DESCENDING_RESISTANCE",
        "p1_index": 1,
        "p2_index": 10,
        "slope": -0.5,
        "intercept": 110.0,
        "touch_count": 4,
        "touch_points": [
            {"index": 1, "timestamp": candles[1].timestamp, "price": 109.5},
            {"index": 4, "timestamp": candles[4].timestamp, "price": 108.0},
            {"index": 7, "timestamp": candles[7].timestamp, "price": 106.5},
            {"index": 10, "timestamp": candles[10].timestamp, "price": 105.0}
        ]
    }

    tf_analysis = SingleTimeframeAnalysis(
        timeframe="15M",
        trend="BULLISH",
        structure_type="Descending Channel Breakout",
        indicators=TechnicalIndicators(atr_14=1.5, relative_volume=2.2),
        support_resistance=SupportResistanceSummary(major_support=95.0, minor_support=100.0, current_price=104.5, minor_resistance=110.0, major_resistance=115.0, all_levels=[]),
        breakout_status="CONFIRMED BREAKOUT",
        trendlines=[four_point_tl],
        candle_count=len(candles),
        latest_candle_time=candles[-1].timestamp
    )

    synth = MultiTimeframeSynthesis(
        symbol="TCS",
        ticker="TCS.NS",
        provider="yfinance",
        current_price=104.5,
        last_updated="2026-08-30T13:30:00Z",
        timeframes={"15M": tf_analysis},
        overall_bias="BULLISH",
        current_state="FULL BULLISH ALIGNMENT",
        evidence_score=EvidenceScoreBreakdown(total_score=85, category="Strong Evidence Alignment", structure_points=20, htf_alignment_points=20, momentum_points=15, volume_points=15, breakout_points=15, details=[]),
        confirmation_state="CONFIRMED",
        short_term_state="BULLISH",
        status_message="OK",
        is_stale=False,
        synthesis_rationale="Test rationale"
    )

    shortlisted = trendline_shortlist_engine.process_synthesis(synth, mtf_candles={"15M": candles})
    assert len(shortlisted) == 1
    cand = shortlisted[0]

    assert cand.symbol == "TCS"
    assert cand.direction == "BULLISH"
    assert cand.trendline_type == "RESISTANCE_BREAKOUT"
    assert cand.touch_count == 4
    assert cand.swing_structure == "Lower High × 4"
    assert cand.r_squared >= 0.95
    assert cand.trendline_score >= 80
    assert cand.confidence in ["STRONG", "VERY STRONG"]
    assert cand.status == "BREAKOUT"
    assert cand.breakout_pct > 0.20

def test_trigger_test_shortlist_endpoints():
    """Verify test triggers for both Bullish Resistance Breakout and Bearish Support Breakdown."""
    # Trigger Bullish
    res_bull = client.post("/api/alerts/trendline-shortlist/test?direction=BULLISH")
    assert res_bull.status_code == 200
    bull_data = res_bull.json()
    assert bull_data["symbol"] == "NIFTY 50"
    assert bull_data["direction"] == "BULLISH"
    assert bull_data["trendline_type"] == "RESISTANCE_BREAKOUT"
    assert bull_data["touch_count"] == 4
    assert bull_data["swing_structure"] == "Lower High × 4"
    assert bull_data["r_squared"] > 0.95
    assert bull_data["trendline_score"] >= 80

    # Trigger Bearish
    res_bear = client.post("/api/alerts/trendline-shortlist/test?direction=BEARISH")
    assert res_bear.status_code == 200
    bear_data = res_bear.json()
    assert bear_data["symbol"] == "BANK NIFTY"
    assert bear_data["direction"] == "BEARISH"
    assert bear_data["trendline_type"] == "SUPPORT_BREAKDOWN"
    assert bear_data["touch_count"] == 3
    assert bear_data["swing_structure"] == "Higher Low × 3"
    assert bear_data["r_squared"] > 0.90

    # Query shortlist
    list_res = client.get("/api/alerts/trendline-shortlist")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 2

    # Filter by Direction
    bull_res = client.get("/api/alerts/trendline-shortlist?direction=BULLISH")
    assert len(bull_res.json()) == 1
    assert bull_res.json()[0]["direction"] == "BULLISH"

    bear_res = client.get("/api/alerts/trendline-shortlist?direction=BEARISH")
    assert len(bear_res.json()) == 1
    assert bear_res.json()[0]["direction"] == "BEARISH"

    # Detail query by ID
    det_res = client.get(f"/api/alerts/trendline-shortlist/{bull_data['id']}")
    assert det_res.status_code == 200
    assert det_res.json()["id"] == bull_data["id"]

    # Clear shortlist
    clear_res = client.post("/api/alerts/trendline-shortlist/clear")
    assert clear_res.status_code == 200
    assert client.get("/api/alerts/trendline-shortlist").json() == []
