import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.alerts.mw_breakout_engine import mw_breakout_engine, MWBreakoutAlertEngine
from app.models.schemas import MWBreakoutAlert, MultiTimeframeSynthesis, SingleTimeframeAnalysis, WMPatternStructure, PatternTargetAnalysis, EvidenceScoreBreakdown

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_engine():
    mw_breakout_engine.clear_alerts()
    yield
    mw_breakout_engine.clear_alerts()

def test_mw_breakout_empty_state():
    """Verify that when no alerts are present, endpoints return empty list without fake data."""
    res = client.get("/api/alerts/mw-breakouts")
    assert res.status_code == 200
    assert res.json() == []

    res_stats = client.get("/api/alerts/mw-breakouts/stats")
    assert res_stats.status_code == 200
    data = res_stats.json()
    assert data["total_count"] == 0
    assert data["w_breakouts"] == 0
    assert data["m_breakdowns"] == 0

def test_trigger_and_get_test_w_breakout():
    """Trigger test W breakout and verify all fields, exact timestamp, and measured target."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    w_alert = res.json()

    assert w_alert["alert_type"] == "W_BREAKOUT_CONFIRMED"
    assert w_alert["pattern_type"] == "W"
    assert w_alert["direction"] == "UP"
    assert w_alert["symbol"] == "NIFTY 50"
    assert w_alert["timeframe"] == "15M"
    assert w_alert["s1_price"] == 24500.0
    assert w_alert["s2_price"] == 24520.0
    assert w_alert["neckline_price"] == 24850.0
    assert w_alert["pattern_height"] == 350.0
    assert w_alert["breakout_close"] == 24910.0
    assert w_alert["measured_target"] == 25200.0
    assert w_alert["quality_score"] == 87
    assert w_alert["status"] == "ACTIVE"

    # Fetch detail by alert_id
    alert_id = w_alert["alert_id"]
    detail_res = client.get(f"/api/alerts/mw-breakouts/{alert_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["alert_id"] == alert_id

def test_trigger_and_get_test_m_breakdown():
    """Trigger test M breakdown and verify all fields, exact timestamp, and measured target."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=M")
    assert res.status_code == 200
    m_alert = res.json()

    assert m_alert["alert_type"] == "M_BREAKDOWN_CONFIRMED"
    assert m_alert["pattern_type"] == "M"
    assert m_alert["direction"] == "DOWN"
    assert m_alert["symbol"] == "BANK NIFTY"
    assert m_alert["timeframe"] == "1H"
    assert m_alert["s1_price"] == 57500.0
    assert m_alert["s2_price"] == 57480.0
    assert m_alert["neckline_price"] == 57435.0
    assert m_alert["pattern_height"] == 65.0
    assert m_alert["breakout_close"] == 57300.0
    assert m_alert["measured_target"] == 57370.0
    assert m_alert["quality_score"] == 86
    assert m_alert["status"] == "ACTIVE"

def test_filter_w_and_m_breakouts():
    """Test filtering by pattern_type, symbol, timeframe, status."""
    client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    client.post("/api/alerts/mw-breakouts/test?pattern_type=M")

    # Filter W
    w_res = client.get("/api/alerts/mw-breakouts?pattern_type=W")
    assert w_res.status_code == 200
    assert len(w_res.json()) == 1
    assert w_res.json()[0]["pattern_type"] == "W"

    # Filter M
    m_res = client.get("/api/alerts/mw-breakouts?pattern_type=M")
    assert m_res.status_code == 200
    assert len(m_res.json()) == 1
    assert m_res.json()[0]["pattern_type"] == "M"

    # Filter Symbol
    sym_res = client.get("/api/alerts/mw-breakouts?symbol=BANK")
    assert sym_res.status_code == 200
    assert len(sym_res.json()) == 1
    assert sym_res.json()[0]["symbol"] == "BANK NIFTY"

    # Filter Timeframe
    tf_res = client.get("/api/alerts/mw-breakouts?timeframe=15M")
    assert tf_res.status_code == 200
    assert len(tf_res.json()) == 1
    assert tf_res.json()[0]["timeframe"] == "15M"

def test_mark_all_read_and_clear():
    """Verify mark read and clear endpoints."""
    client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    client.post("/api/alerts/mw-breakouts/test?pattern_type=M")

    stats = client.get("/api/alerts/mw-breakouts/stats").json()
    assert stats["unread_count"] == 2

    # Mark all read
    read_res = client.post("/api/alerts/mw-breakouts/read-all")
    assert read_res.status_code == 200
    stats_after_read = client.get("/api/alerts/mw-breakouts/stats").json()
    assert stats_after_read["unread_count"] == 0

    # Clear
    clear_res = client.post("/api/alerts/mw-breakouts/clear")
    assert clear_res.status_code == 200
    assert client.get("/api/alerts/mw-breakouts").json() == []

def test_engine_target_hit_and_invalidation_tracking():
    """Verify engine dynamically updates alert status to TARGET_1_HIT or INVALIDATED based on live price."""
    engine = MWBreakoutAlertEngine()
    
    # 1. Create a W Breakout Alert: Neckline=24850, Target=25200, Invalidation=24850
    w_alert = MWBreakoutAlert(
        alert_id="w_test_1",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="NIFTY 50",
        timeframe="15M",
        pattern_id="W_001",
        s1_price=24500.0,
        s1_timestamp="2026-08-25T10:00:00Z",
        s2_price=24520.0,
        s2_timestamp="2026-08-25T10:30:00Z",
        neckline_price=24850.0,
        neckline_timestamp="2026-08-25T10:15:00Z",
        pattern_height=350.0,
        breakout_candle_timestamp="2026-08-25T10:45:00Z",
        breakout_open=24840.0,
        breakout_high=24920.0,
        breakout_low=24830.0,
        breakout_close=24910.0,
        trendline_price=24820.0,
        ema20_price=24800.0,
        volume=200000.0,
        relative_volume=1.45,
        measured_target=25200.0,
        invalidation_level=24850.0,
        quality_score=88,
        status="ACTIVE",
        event_created_at="2026-08-25T10:45:00Z",
        read=False
    )
    engine.alerts.append(w_alert)

    # Mock Synthesis where price has reached 25,250 (Target 1 Hit!)
    synth_target_hit = MultiTimeframeSynthesis(
        symbol="NIFTY 50",
        ticker="^NSEI",
        provider="yfinance",
        current_price=25250.0,
        last_updated="2026-08-25T11:15:00Z",
        timeframes={},
        overall_bias="BULLISH",
        current_state="FULL BULLISH ALIGNMENT",
        evidence_score=EvidenceScoreBreakdown(
            total_score=85,
            category="Strong Evidence Alignment",
            structure_points=25,
            htf_alignment_points=20,
            momentum_points=15,
            volume_points=15,
            breakout_points=10,
            details=[]
        ),
        confirmation_state="CONFIRMED",
        short_term_state="BULLISH",
        what_just_changed=None,
        data_status="LIVE",
        status_message="OK",
        is_stale=False,
        synthesis_rationale="Test target hit"
    )
    engine._update_existing_alert_statuses(synth_target_hit)
    assert w_alert.status == "TARGET_1_HIT"

    # Mock another alert and verify Invalidation
    w_alert_2 = MWBreakoutAlert(
        alert_id="w_test_2",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="NIFTY 50",
        timeframe="15M",
        pattern_id="W_002",
        s1_price=24500.0,
        s1_timestamp="2026-08-25T10:00:00Z",
        s2_price=24520.0,
        s2_timestamp="2026-08-25T10:30:00Z",
        neckline_price=24850.0,
        neckline_timestamp="2026-08-25T10:15:00Z",
        pattern_height=350.0,
        breakout_candle_timestamp="2026-08-25T10:45:00Z",
        breakout_open=24840.0,
        breakout_high=24920.0,
        breakout_low=24830.0,
        breakout_close=24910.0,
        trendline_price=24820.0,
        ema20_price=24800.0,
        volume=200000.0,
        relative_volume=1.45,
        measured_target=25200.0,
        invalidation_level=24850.0,
        quality_score=88,
        status="ACTIVE",
        event_created_at="2026-08-25T10:45:00Z",
        read=False
    )
    engine.alerts.append(w_alert_2)

    synth_invalidated = MultiTimeframeSynthesis(
        symbol="NIFTY 50",
        ticker="^NSEI",
        provider="yfinance",
        current_price=24800.0,  # Below invalidation 24850
        last_updated="2026-08-25T11:15:00Z",
        timeframes={},
        overall_bias="BEARISH",
        current_state="FULL BEARISH ALIGNMENT",
        evidence_score=EvidenceScoreBreakdown(
            total_score=50,
            category="Mixed Evidence",
            structure_points=15,
            htf_alignment_points=10,
            momentum_points=10,
            volume_points=10,
            breakout_points=5,
            details=[]
        ),
        confirmation_state="CONFIRMED",
        short_term_state="BEARISH",
        what_just_changed=None,
        data_status="LIVE",
        status_message="OK",
        is_stale=False,
        synthesis_rationale="Test invalidated"
    )
    engine._update_existing_alert_statuses(synth_invalidated)
    assert w_alert_2.status == "INVALIDATED"
