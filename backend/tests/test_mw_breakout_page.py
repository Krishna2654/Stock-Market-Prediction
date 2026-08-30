import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.alerts.mw_breakout_engine import mw_breakout_engine, MWBreakoutAlertEngine
from app.models.schemas import MWBreakoutAlert, MultiTimeframeSynthesis, EvidenceScoreBreakdown

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
    """Trigger test W breakout and verify all fields, exact timestamp, Target 1, Target 2, and initial TARGET OPEN status."""
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
    assert w_alert["target_2"] == 25350.0
    assert w_alert["quality_score"] == 87
    assert w_alert["status"] == "TARGET OPEN"

    # Fetch detail by alert_id
    alert_id = w_alert["alert_id"]
    detail_res = client.get(f"/api/alerts/mw-breakouts/{alert_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["alert_id"] == alert_id
    assert detail_res.json()["status"] == "TARGET OPEN"

def test_trigger_and_get_test_m_breakdown():
    """Trigger test M breakdown and verify all fields, Target 1, Target 2, and initial TARGET OPEN status."""
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
    assert m_alert["target_2"] == 57150.0
    assert m_alert["quality_score"] == 86
    assert m_alert["status"] == "TARGET OPEN"

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

    # Filter Status: TARGET OPEN
    st_res = client.get("/api/alerts/mw-breakouts?status=TARGET%20OPEN")
    assert st_res.status_code == 200
    assert len(st_res.json()) == 2

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

# =========================================================================
# COMPREHENSIVE OUTCOME TESTS REQUIRED BY SPEC:
# a) Newly confirmed breakout -> TARGET OPEN
# b) Target 1 reached -> TARGET 1 HIT
# c) Target 2 reached -> TARGET 2 HIT
# d) SL/invalidation reached before target -> SL HIT
# e) Page refresh / engine reload -> status remains unchanged
# f) Price moves directly beyond Target 2 -> TARGET 2 HIT
# =========================================================================

def _make_synth(symbol: str, price: float) -> MultiTimeframeSynthesis:
    return MultiTimeframeSynthesis(
        symbol=symbol,
        ticker="^TEST",
        provider="yfinance",
        current_price=price,
        last_updated="2026-08-30T10:00:00Z",
        timeframes={},
        overall_bias="BULLISH",
        current_state="FULL BULLISH ALIGNMENT",
        evidence_score=EvidenceScoreBreakdown(
            total_score=80,
            category="Strong Evidence Alignment",
            structure_points=20,
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
        synthesis_rationale="Test"
    )

def test_case_a_newly_confirmed_breakout_target_open():
    """Case a: Newly confirmed breakout has status TARGET OPEN."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    alert = res.json()
    assert alert["status"] == "TARGET OPEN"
    assert alert["measured_target"] == 25200.0
    assert alert["target_2"] == 25350.0

def test_case_b_target_1_reached():
    """Case b: Price reaches Target 1 -> status becomes TARGET 1 HIT."""
    # W alert: neckline=24850, T1=25200, T2=25350, SL=24850
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    w_alert = mw_breakout_engine.get_alerts()[0]
    assert w_alert.status == "TARGET OPEN"

    # Price reaches 25210 (Target 1 reached, below Target 2)
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 25210.0))
    assert w_alert.status == "TARGET 1 HIT"

    # Verify API reflects TARGET 1 HIT
    api_alert = client.get(f"/api/alerts/mw-breakouts/{w_alert.alert_id}").json()
    assert api_alert["status"] == "TARGET 1 HIT"

def test_case_c_target_2_subsequently_reached():
    """Case c: Price reaches Target 1 then subsequently reaches Target 2 -> status becomes TARGET 2 HIT."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    w_alert = mw_breakout_engine.get_alerts()[0]

    # Step 1: Hit T1
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 25210.0))
    assert w_alert.status == "TARGET 1 HIT"

    # Step 2: Hit T2 (25350)
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 25360.0))
    assert w_alert.status == "TARGET 2 HIT"

    # Step 3: Verify TARGET 2 HIT is never downgraded or overwritten
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 24000.0))
    assert w_alert.status == "TARGET 2 HIT"

    # Verify API reflects TARGET 2 HIT
    api_alert = client.get(f"/api/alerts/mw-breakouts/{w_alert.alert_id}").json()
    assert api_alert["status"] == "TARGET 2 HIT"

def test_case_d_sl_reached_before_target():
    """Case d: SL/invalidation reached before target -> status becomes SL HIT."""
    # W alert: neckline=24850, Invalidation SL=24850
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    w_alert = mw_breakout_engine.get_alerts()[0]
    assert w_alert.status == "TARGET OPEN"

    # Price falls to 24800 (below SL) before hitting target
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 24800.0))
    assert w_alert.status == "SL HIT"

    # Verify SL HIT is never overwritten by a later bounce
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 26000.0))
    assert w_alert.status == "SL HIT"

    # Verify API reflects SL HIT
    api_alert = client.get(f"/api/alerts/mw-breakouts/{w_alert.alert_id}").json()
    assert api_alert["status"] == "SL HIT"

def test_case_e_persistence_status_unchanged_on_reload():
    """Case e: Page refresh / engine reload -> status remains unchanged from persistent store."""
    # Create alert and progress it to TARGET 1 HIT
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    w_alert = mw_breakout_engine.get_alerts()[0]
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 25220.0))
    assert w_alert.status == "TARGET 1 HIT"
    target_alert_id = w_alert.alert_id

    # Create a fresh new engine instance (simulating server restart or new request cycle)
    engine2 = MWBreakoutAlertEngine()
    reloaded_alert = engine2.get_alert_by_id(target_alert_id)
    assert reloaded_alert is not None
    assert reloaded_alert.status == "TARGET 1 HIT"
    assert reloaded_alert.measured_target == 25200.0
    assert reloaded_alert.target_2 == 25350.0

def test_case_f_price_moves_directly_beyond_target_2():
    """Case f: Price moves directly beyond Target 2 -> status becomes TARGET 2 HIT directly."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    w_alert = mw_breakout_engine.get_alerts()[0]
    assert w_alert.status == "TARGET OPEN"

    # Price jumps straight past Target 2 (25350) to 25400
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 25400.0))
    assert w_alert.status == "TARGET 2 HIT"

def test_m_pattern_bearish_outcomes():
    """Verify bearish M Breakdown: T1, T2, SL logic works with inverted price directions."""
    # M alert: neckline=57435, T1=57370, T2=57150, SL=57435
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=M")
    assert res.status_code == 200
    m_alert = mw_breakout_engine.get_alerts()[0]
    assert m_alert.status == "TARGET OPEN"

    # Price drops to 57360 (below T1=57370, above T2=57150) -> TARGET 1 HIT
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(m_alert.symbol, 57360.0))
    assert m_alert.status == "TARGET 1 HIT"

    # Price drops further to 57140 (below T2=57150) -> TARGET 2 HIT
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(m_alert.symbol, 57140.0))
    assert m_alert.status == "TARGET 2 HIT"

    # Verify SL (if price moves above invalidation) does not overwrite TARGET 2 HIT
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(m_alert.symbol, 58000.0))
    assert m_alert.status == "TARGET 2 HIT"
