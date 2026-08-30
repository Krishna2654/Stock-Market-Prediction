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
# CRITICAL TEST CASES 1 THROUGH 13 AS SPECIFIED:
# =========================================================================

def _make_synth(symbol: str, price: float, candles: list = None) -> MultiTimeframeSynthesis:
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

def test_1_new_w_breakout_status_target_open():
    """TEST 1: New W breakout: Status = TARGET OPEN."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    alert = res.json()
    assert alert["status"] == "TARGET OPEN"
    assert alert["measured_target"] == 25200.0
    assert alert["target_2"] == 25350.0

def test_2_w_breakout_reaches_target_1():
    """TEST 2: W breakout price reaches Target 1: Status = TARGET 1 HIT."""
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

def test_3_w_breakout_reaches_target_2():
    """TEST 3: W breakout price reaches Target 2: Status = TARGET 2 HIT."""
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

def test_4_w_breakout_reaches_sl_before_target_1():
    """TEST 4: W breakout price reaches SL before Target 1: Status = SL HIT."""
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

def test_5_m_breakdown_reaches_target_1():
    """TEST 5: M breakdown reaches Target 1: Status = TARGET 1 HIT."""
    # M alert: neckline=57435, T1=57370, T2=57150, SL=57435
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=M")
    assert res.status_code == 200
    m_alert = mw_breakout_engine.get_alerts()[0]
    assert m_alert.status == "TARGET OPEN"

    # Price drops to 57360 (below T1=57370, above T2=57150) -> TARGET 1 HIT
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(m_alert.symbol, 57360.0))
    assert m_alert.status == "TARGET 1 HIT"

    # Verify API reflects TARGET 1 HIT
    api_alert = client.get(f"/api/alerts/mw-breakouts/{m_alert.alert_id}").json()
    assert api_alert["status"] == "TARGET 1 HIT"

def test_6_m_breakdown_reaches_target_2():
    """TEST 6: M breakdown reaches Target 2: Status = TARGET 2 HIT."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=M")
    assert res.status_code == 200
    m_alert = mw_breakout_engine.get_alerts()[0]

    # Step 1: Hit T1
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(m_alert.symbol, 57360.0))
    assert m_alert.status == "TARGET 1 HIT"

    # Step 2: Hit T2 (57150)
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(m_alert.symbol, 57140.0))
    assert m_alert.status == "TARGET 2 HIT"

    # Terminal state check: bounce above invalidation level does NOT overwrite TARGET 2 HIT
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(m_alert.symbol, 58000.0))
    assert m_alert.status == "TARGET 2 HIT"

def test_7_m_breakdown_reaches_sl_before_target():
    """TEST 7: M breakdown reaches SL before target: Status = SL HIT."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=M")
    assert res.status_code == 200
    m_alert = mw_breakout_engine.get_alerts()[0]
    assert m_alert.status == "TARGET OPEN"

    # Price rises to 57450 (above invalidation SL 57435) before hitting targets
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(m_alert.symbol, 57450.0))
    assert m_alert.status == "SL HIT"

    # Verify SL HIT cannot be overwritten by later drop
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(m_alert.symbol, 56000.0))
    assert m_alert.status == "SL HIT"

def test_8_refresh_page_after_target_1_hit():
    """TEST 8: Refresh page after TARGET 1 HIT: Status must remain TARGET 1 HIT."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    w_alert = mw_breakout_engine.get_alerts()[0]
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 25220.0))
    assert w_alert.status == "TARGET 1 HIT"
    target_alert_id = w_alert.alert_id

    # Simulate fresh page request or server restart
    engine2 = MWBreakoutAlertEngine()
    reloaded_alert = engine2.get_alert_by_id(target_alert_id)
    assert reloaded_alert is not None
    assert reloaded_alert.status == "TARGET 1 HIT"
    assert reloaded_alert.measured_target == 25200.0
    assert reloaded_alert.target_2 == 25350.0

def test_9_refresh_page_after_target_2_hit():
    """TEST 9: Refresh page after TARGET 2 HIT: Status must remain TARGET 2 HIT."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    w_alert = mw_breakout_engine.get_alerts()[0]
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 25360.0))
    assert w_alert.status == "TARGET 2 HIT"
    target_alert_id = w_alert.alert_id

    # Simulate fresh page request or server restart
    engine2 = MWBreakoutAlertEngine()
    reloaded_alert = engine2.get_alert_by_id(target_alert_id)
    assert reloaded_alert is not None
    assert reloaded_alert.status == "TARGET 2 HIT"

def test_10_view_details_on_old_w_breakout():
    """TEST 10: Click View Details on an old W breakout: Full historical details must appear."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    alert = res.json()
    alert_id = alert["alert_id"]

    detail_res = client.get(f"/api/alerts/mw-breakouts/{alert_id}")
    assert detail_res.status_code == 200
    data = detail_res.json()

    # Complete historical information must be present
    assert data["alert_id"] == alert_id
    assert data["symbol"] == "NIFTY 50"
    assert data["pattern_type"] == "W"
    assert data["direction"] == "UP"
    assert data["timeframe"] == "15M"
    assert data["s1_price"] == 24500.0
    assert data["s2_price"] == 24520.0
    assert data["neckline_price"] == 24850.0
    assert data["pattern_height"] == 350.0
    assert data["breakout_close"] == 24910.0
    assert data["measured_target"] == 25200.0
    assert data["target_2"] == 25350.0
    assert data["invalidation_level"] == 24850.0
    assert data["quality_score"] == 87
    assert data["status"] in ["TARGET OPEN", "TARGET 1 HIT", "TARGET 2 HIT", "SL HIT"]

def test_11_view_details_on_old_m_breakdown():
    """TEST 11: Click View Details on an old M breakdown: Full historical details must appear."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=M")
    assert res.status_code == 200
    alert = res.json()
    alert_id = alert["alert_id"]

    detail_res = client.get(f"/api/alerts/mw-breakouts/{alert_id}")
    assert detail_res.status_code == 200
    data = detail_res.json()

    # Complete historical information must be present
    assert data["alert_id"] == alert_id
    assert data["symbol"] == "BANK NIFTY"
    assert data["pattern_type"] == "M"
    assert data["direction"] == "DOWN"
    assert data["timeframe"] == "1H"
    assert data["s1_price"] == 57500.0
    assert data["s2_price"] == 57480.0
    assert data["neckline_price"] == 57435.0
    assert data["pattern_height"] == 65.0
    assert data["breakout_close"] == 57300.0
    assert data["measured_target"] == 57370.0
    assert data["target_2"] == 57150.0
    assert data["invalidation_level"] == 57435.0
    assert data["quality_score"] == 86

def test_12_current_market_no_longer_detects_old_pattern_view_details_still_works():
    """TEST 12: Current market no longer detects the old pattern: View Details must STILL work."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    alert_id = res.json()["alert_id"]

    # Even if market scan has zero active patterns, View Details returns the historical record
    detail_res = client.get(f"/api/alerts/mw-breakouts/{alert_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["alert_id"] == alert_id

    # Test symbol with slash (e.g. BTC/USD) and URL-encoded slash
    btc_alert = MWBreakoutAlert(
        alert_id="mw_BTC_USD_15M_W_test1234",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="BTC/USD",
        ticker="BTC-USD",
        timeframe="15M",
        pattern_id="pat_btc_1",
        s1_price=77500.0,
        s1_timestamp="2026-08-30T09:00:00Z",
        s2_price=77520.0,
        s2_timestamp="2026-08-30T09:30:00Z",
        neckline_price=77752.5,
        neckline_timestamp="2026-08-30T09:15:00Z",
        pattern_height=252.5,
        breakout_candle_timestamp="2026-08-30T09:45:00Z",
        breakout_open=77750.0,
        breakout_high=77800.0,
        breakout_low=77740.0,
        breakout_close=77780.0,
        trendline_price=77750.0,
        ema20_price=77745.0,
        volume=500.0,
        relative_volume=1.8,
        measured_target=78005.0,
        target_2=78257.5,
        invalidation_level=77752.5,
        quality_score=88,
        quality_breakdown={},
        status="TARGET OPEN",
        event_created_at="2026-08-30T09:45:00Z",
        read=False
    )
    mw_breakout_engine.alerts.insert(0, btc_alert)

    # Can fetch with exact alert_id
    res_btc = client.get(f"/api/alerts/mw-breakouts/{btc_alert.alert_id}")
    assert res_btc.status_code == 200
    assert res_btc.json()["symbol"] == "BTC/USD"

def test_13_price_jumps_directly_past_target_2():
    """TEST 13: If price jumps directly past Target 2: Status = TARGET 2 HIT."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    w_alert = mw_breakout_engine.get_alerts()[0]
    assert w_alert.status == "TARGET OPEN"

    # Price jumps straight past Target 2 (25350) to 25400
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 25400.0))
    assert w_alert.status == "TARGET 2 HIT"

def test_14_chart_and_mw_breakout_card_data_consistency():
    """TEST 14: Single Source of Truth - Chart, Card, List, and Detail use exact identical pattern data."""
    res_chart = client.get("/api/analysis/chart/BTC-USD?timeframe=15M&limit=250")
    assert res_chart.status_code == 200
    chart_data = res_chart.json()
    active_pat = chart_data.get("active_wm_pattern")
    active_alert = chart_data.get("active_wm_alert")

    assert active_pat is not None, "Expected active W/M pattern on BTC-USD 15M chart"
    assert active_alert is not None, "Expected active W/M alert on BTC-USD 15M chart"

    # 1. Verify Card Alert matches Chart Pattern 100%
    assert active_alert["pattern_type"] == active_pat["pattern_type"]
    assert active_alert["s1_price"] == active_pat["s1_price"]
    assert active_alert["neckline_price"] == active_pat["neckline_price"]
    assert active_alert["s2_price"] == active_pat["s2_price"]
    assert active_alert["pattern_height"] == active_pat["pattern_height"]
    assert active_alert["measured_target"] == active_pat["target_analysis"]["measured_target"]
    assert active_alert["target_2"] == active_pat["target_analysis"]["target_2"]
    assert active_alert["invalidation_level"] == active_pat["target_analysis"]["invalidation_level"]
    assert active_alert["quality_score"] == active_pat["quality_score"]

    # 2. Verify Alerts List endpoint returns this exact alert as #1
    res_alerts = client.get("/api/alerts/mw-breakouts?symbol=BTC/USD&timeframe=15M")
    assert res_alerts.status_code == 200
    alerts = res_alerts.json()
    assert len(alerts) > 0
    first_alert = alerts[0]
    assert first_alert["s1_price"] == active_pat["s1_price"]
    assert first_alert["neckline_price"] == active_pat["neckline_price"]
    assert first_alert["s2_price"] == active_pat["s2_price"]
    assert first_alert["pattern_height"] == active_pat["pattern_height"]
    assert first_alert["measured_target"] == active_pat["target_analysis"]["measured_target"]
    assert first_alert["target_2"] == active_pat["target_analysis"]["target_2"]
    assert first_alert["invalidation_level"] == active_pat["target_analysis"]["invalidation_level"]

    # 3. Verify View Details endpoint matches identically
    detail_res = client.get(f"/api/alerts/mw-breakouts/{first_alert['alert_id']}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["s1_price"] == active_pat["s1_price"]
    assert detail["neckline_price"] == active_pat["neckline_price"]
    assert detail["s2_price"] == active_pat["s2_price"]
    assert detail["measured_target"] == active_pat["target_analysis"]["measured_target"]
    assert detail["target_2"] == active_pat["target_analysis"]["target_2"]
    assert detail["invalidation_level"] == active_pat["target_analysis"]["invalidation_level"]

def test_15_chart_sync_deduplication():
    """TEST 15: Repeated chart queries do not generate duplicate breakout cards."""
    # Fetch chart once
    client.get("/api/analysis/chart/BTC-USD?timeframe=15M&limit=250")
    count_1 = len(client.get("/api/alerts/mw-breakouts?symbol=BTC/USD&timeframe=15M").json())

    # Fetch chart multiple times
    client.get("/api/analysis/chart/BTC-USD?timeframe=15M&limit=250")
    client.get("/api/analysis/chart/BTC-USD?timeframe=15M&limit=250")
    count_2 = len(client.get("/api/alerts/mw-breakouts?symbol=BTC/USD&timeframe=15M").json())

    assert count_1 == count_2, f"Duplicate cards generated: count_1={count_1}, count_2={count_2}"

