import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.alerts.mw_breakout_engine import mw_breakout_engine, MWBreakoutAlertEngine
from app.models.schemas import MWBreakoutAlert, MultiTimeframeSynthesis, EvidenceScoreBreakdown, SwingPoint, Candle, WMPatternStructure, PatternTargetAnalysis
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_engine(tmp_path, monkeypatch):
    test_store = tmp_path / "test_mw_store.json"
    monkeypatch.setattr("app.alerts.mw_breakout_engine.STORAGE_FILE", test_store)
    orig_alerts = list(mw_breakout_engine.alerts)
    orig_seen = set(mw_breakout_engine.seen_event_keys)
    mw_breakout_engine.clear_alerts()
    yield
    mw_breakout_engine.alerts = orig_alerts
    mw_breakout_engine.seen_event_keys = orig_seen

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
    assert w_alert["target_2"] == 25416.3
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
    assert m_alert["target_2"] == 57329.83
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
    assert alert["target_2"] == 25416.3

def test_2_w_breakout_reaches_target_1():
    """TEST 2: W breakout price reaches Target 1: Status = TARGET 1 HIT."""
    # W alert: neckline=24850, T1=25200, T2=25416.3, SL=24480
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

    # Step 2: Hit T2 (25416.3)
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 25420.0))
    assert w_alert.status == "TARGET 2 HIT"

    # Step 3: Verify TARGET 2 HIT is never downgraded or overwritten
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 24000.0))
    assert w_alert.status == "TARGET 2 HIT"

    # Verify API reflects TARGET 2 HIT
    api_alert = client.get(f"/api/alerts/mw-breakouts/{w_alert.alert_id}").json()
    assert api_alert["status"] == "TARGET 2 HIT"

def test_4_w_breakout_reaches_sl_before_target_1():
    """TEST 4: W breakout price reaches SL before Target 1: Status = SL HIT."""
    # W alert: neckline=24850, Invalidation SL=24480 (previous swing low below W structure)
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    w_alert = mw_breakout_engine.get_alerts()[0]
    assert w_alert.status == "TARGET OPEN"
    assert w_alert.invalidation_level < w_alert.neckline_price

    # Retest of neckline (24800) does NOT hit SL because SL is 24480!
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 24800.0))
    assert w_alert.status == "TARGET OPEN"

    # Price falls to 24450 (below SL 24480) before hitting target -> SL HIT
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 24450.0))
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
    # M alert: neckline=57435, Invalidation SL=57530 (previous swing high above M structure)
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=M")
    assert res.status_code == 200
    m_alert = mw_breakout_engine.get_alerts()[0]
    assert m_alert.status == "TARGET OPEN"
    assert m_alert.invalidation_level > m_alert.neckline_price

    # Retest of neckline (57450) does NOT hit SL because SL is 57530!
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(m_alert.symbol, 57450.0))
    assert m_alert.status == "TARGET OPEN"

    # Price rises to 57550 (above SL 57530) before hitting targets -> SL HIT
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(m_alert.symbol, 57550.0))
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
    assert reloaded_alert.target_2 == 25416.3

def test_9_refresh_page_after_target_2_hit():
    """TEST 9: Refresh page after TARGET 2 HIT: Status must remain TARGET 2 HIT."""
    res = client.post("/api/alerts/mw-breakouts/test?pattern_type=W")
    assert res.status_code == 200
    w_alert = mw_breakout_engine.get_alerts()[0]
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 25420.0))
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
    assert data["target_2"] == 25416.3
    assert data["invalidation_level"] == 24480.0
    assert data["invalidation_level"] != data["neckline_price"]
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
    assert data["target_2"] == 57329.83
    assert data["invalidation_level"] == 57530.0
    assert data["invalidation_level"] != data["neckline_price"]
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

    # Price jumps straight past Target 2 (25416.3) to 25450.0
    mw_breakout_engine._update_existing_alert_statuses(_make_synth(w_alert.symbol, 25450.0))
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

def test_16_w_pattern_stop_loss_below_structure_and_not_neckline():
    """TEST 16: W breakout Stop Loss is below W structure (never equals neckline) and retests do not trigger SL HIT."""
    target_res = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="W",
        s1_price=100.0,
        s2_price=101.0,
        neckline_price=110.0,
        breakout_close=112.0,
        prev_swing_sl=98.0
    )
    # Stop loss must be previous swing low (98.0)
    assert target_res.invalidation_level == 98.0
    assert target_res.invalidation_level < target_res.retest_level
    assert target_res.retest_level == 110.0

    # Test lifecycle: neckline retest (e.g. 109.5) does NOT trigger SL HIT
    alert = MWBreakoutAlert(
        alert_id="mw_test_w_sl_independence",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="TEST",
        ticker="TEST",
        timeframe="15M",
        pattern_id="W_TEST_IND",
        s1_price=100.0,
        s1_timestamp="2026-08-30T10:00:00Z",
        s2_price=101.0,
        s2_timestamp="2026-08-30T10:30:00Z",
        neckline_price=110.0,
        neckline_timestamp="2026-08-30T10:15:00Z",
        pattern_height=10.0,
        breakout_candle_timestamp="2026-08-30T10:45:00Z",
        breakout_open=109.0,
        breakout_high=112.5,
        breakout_low=108.8,
        breakout_close=112.0,
        trendline_price=110.0,
        ema20_price=108.0,
        measured_target=120.0,
        target_2=130.0,
        invalidation_level=98.0,
        quality_score=90,
        status="TARGET OPEN",
        event_created_at="2026-08-30T10:45:00Z"
    )

    # Retest dipping below neckline to 109.0 with close at 110.5
    mw_breakout_engine._evaluate_single_alert_status(alert, [
        Candle(timestamp="2026-08-30T11:00:00Z", open=112.0, high=112.2, low=109.0, close=110.5, volume=5000)
    ])
    assert alert.status == "TARGET OPEN", "Neckline retest must NOT trigger SL HIT"

    # Deep drop reaching swing SL (97.5 <= 98.0)
    mw_breakout_engine._evaluate_single_alert_status(alert, [
        Candle(timestamp="2026-08-30T11:15:00Z", open=109.5, high=109.5, low=97.5, close=97.8, volume=5000)
    ])
    assert alert.status == "SL HIT", "Breach of swing SL must trigger SL HIT"

def test_17_m_pattern_stop_loss_above_structure_and_not_neckline():
    """TEST 17: M breakdown Stop Loss is above M structure (never equals neckline) and retests do not trigger SL HIT."""
    target_res = PrecisionBreakoutDetector.calculate_pattern_targets(
        pattern_type="M",
        s1_price=200.0,
        s2_price=199.0,
        neckline_price=190.0,
        breakout_close=188.0,
        prev_swing_sl=203.0
    )
    # Stop loss must be previous swing high (203.0)
    assert target_res.invalidation_level == 203.0
    assert target_res.invalidation_level > target_res.retest_level
    assert target_res.retest_level == 190.0

    # Test lifecycle: neckline retest (e.g. 191.0) does NOT trigger SL HIT
    alert = MWBreakoutAlert(
        alert_id="mw_test_m_sl_independence",
        alert_type="M_BREAKDOWN_CONFIRMED",
        pattern_type="M",
        direction="DOWN",
        symbol="TEST",
        ticker="TEST",
        timeframe="15M",
        pattern_id="M_TEST_IND",
        s1_price=200.0,
        s1_timestamp="2026-08-30T10:00:00Z",
        s2_price=199.0,
        s2_timestamp="2026-08-30T10:30:00Z",
        neckline_price=190.0,
        neckline_timestamp="2026-08-30T10:15:00Z",
        pattern_height=10.0,
        breakout_candle_timestamp="2026-08-30T10:45:00Z",
        breakout_open=191.0,
        breakout_high=191.2,
        breakout_low=187.5,
        breakout_close=188.0,
        trendline_price=190.0,
        ema20_price=192.0,
        measured_target=180.0,
        target_2=170.0,
        invalidation_level=203.0,
        quality_score=90,
        status="TARGET OPEN",
        event_created_at="2026-08-30T10:45:00Z"
    )

    # Retest bouncing above neckline to 191.0 with close at 189.5
    mw_breakout_engine._evaluate_single_alert_status(alert, [
        Candle(timestamp="2026-08-30T11:00:00Z", open=188.0, high=191.0, low=187.8, close=189.5, volume=5000)
    ])
    assert alert.status == "TARGET OPEN", "Neckline retest must NOT trigger SL HIT"

    # Rally reaching swing SL (203.5 >= 203.0)
    mw_breakout_engine._evaluate_single_alert_status(alert, [
        Candle(timestamp="2026-08-30T11:15:00Z", open=190.5, high=203.5, low=190.5, close=202.0, volume=5000)
    ])
    assert alert.status == "SL HIT", "Breach of swing SL must trigger SL HIT"

def test_18_late_stage_5th_wave_pattern_rejected():
    """TEST 18: Pattern forming after extended 5-wave trending sequence is rejected."""
    # 3 consecutive higher highs leading into H1:
    swings = [
        SwingPoint(index=2, price=100.0, timestamp="2026-08-25T10:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=4, price=95.0, timestamp="2026-08-25T10:20:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=6, price=105.0, timestamp="2026-08-25T10:30:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=8, price=101.0, timestamp="2026-08-25T10:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=110.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=12, price=106.0, timestamp="2026-08-25T11:00:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        # H1
        SwingPoint(index=14, price=115.0, timestamp="2026-08-25T11:10:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        # Mid Trough
        SwingPoint(index=18, price=111.0, timestamp="2026-08-25T11:30:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        # H2
        SwingPoint(index=22, price=114.9, timestamp="2026-08-25T11:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    ]
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=100, high=116, low=94, close=105, volume=1000)
        for i in range(35)
    ]

    events, confirmed, active, candidates = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles,
        swings=swings,
        symbol="TEST",
        timeframe="15M",
        trendlines=[],
        df_indicators=None,
        atr_val=2.0
    )

    rejected_5w = [c for c in candidates if c.status == "REJECTED" and "extended 5-wave" in (c.rejection_reason or "")]
    assert len(rejected_5w) > 0, "Expected pattern to be rejected due to extended 5-wave movement"

def test_19_valid_w_breakout_structural_geometry():
    """TEST 19: Valid W pattern with Low 2 Stop Loss, candle-close confirmation, Target 1 and Target 2."""
    l1 = SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True)
    mid_peak = SwingPoint(index=10, price=120.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True)
    l2 = SwingPoint(index=15, price=101.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    swings = [l1, mid_peak, l2]

    # 25 candles. Candle at index 18 closes above neckline (120.0) at 122.0
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000)
        for i in range(25)
    ]
    candles[17] = Candle(timestamp="2026-08-25T10:85:00Z", open=115, high=119, low=114, close=118, volume=1200)
    candles[18] = Candle(timestamp="2026-08-25T10:90:00Z", open=118, high=124, low=117, close=122, volume=2000)
    for i in range(19, 25):
        candles[i] = Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=122, high=126, low=121, close=124, volume=1500)

    events, confirmed, active, candidates = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles,
        swings=swings,
        symbol="RELIANCE",
        timeframe="15M",
        trendlines=[],
        df_indicators=None,
        atr_val=2.0
    )

    assert len(confirmed) > 0, "Valid W breakout should be confirmed"
    pat = confirmed[0]
    assert pat.pattern_type == "W"
    assert pat.status in ["BREAKOUT_CONFIRMED", "HIGH_CONFLUENCE_CONFIRMED"]
    assert pat.s1_price == 100.0
    assert pat.neckline_price == 120.0
    assert pat.s2_price == 101.0
    assert pat.breakout_candle_index == 18
    assert pat.breakout_candle_index > pat.s2_index, "Breakout must occur after Point 2 (Low 2)"

    # Height = 120 - 100 = 20.0
    assert pat.pattern_height == 20.0
    # Target 1 = 120 + 20 = 140.0
    assert pat.target_analysis.measured_target == 140.0
    # Target 2 = 120 + 20 * 1.618 = 152.36
    assert pat.target_analysis.target_2 == 152.36
    # Stop Loss = Low 2 - (0.15 * ATR) = 101.0 - (0.15 * 2.0) = 100.70
    assert pat.target_analysis.invalidation_level == 100.70
    assert pat.target_analysis.invalidation_level < pat.neckline_price, "W Stop Loss must be strictly below neckline"
    assert pat.target_analysis.invalidation_level <= pat.s2_price, "W Stop Loss must be below Low 2"

def test_20_valid_m_breakdown_structural_geometry():
    """TEST 20: Valid M pattern with High 2 Stop Loss, candle-close confirmation, Target 1 and Target 2."""
    h1 = SwingPoint(index=5, price=200.0, timestamp="2026-08-25T10:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True)
    mid_trough = SwingPoint(index=10, price=180.0, timestamp="2026-08-25T10:50:00Z", is_high=False, type="LL", strength=2.0, confirmed=True)
    h2 = SwingPoint(index=15, price=199.0, timestamp="2026-08-25T11:15:00Z", is_high=True, type="LH", strength=2.0, confirmed=True)
    swings = [h1, mid_trough, h2]

    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=190, high=195, low=185, close=190, volume=1000)
        for i in range(25)
    ]
    candles[17] = Candle(timestamp="2026-08-25T10:85:00Z", open=185, high=186, low=181, close=182, volume=1200)
    candles[18] = Candle(timestamp="2026-08-25T10:90:00Z", open=182, high=183, low=176, close=178, volume=2000)
    for i in range(19, 25):
        candles[i] = Candle(timestamp=f"2026-08-25T11:{i*2:02d}:00Z", open=178, high=179, low=174, close=176, volume=1500)

    events, confirmed, active, candidates = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles,
        swings=swings,
        symbol="TCS",
        timeframe="1H",
        trendlines=[],
        df_indicators=None,
        atr_val=2.0
    )

    assert len(confirmed) > 0, "Valid M breakdown should be confirmed"
    pat = confirmed[0]
    assert pat.pattern_type == "M"
    assert pat.status in ["BREAKOUT_CONFIRMED", "HIGH_CONFLUENCE_CONFIRMED"]
    assert pat.s1_price == 200.0
    assert pat.neckline_price == 180.0
    assert pat.s2_price == 199.0
    assert pat.breakout_candle_index == 18
    assert pat.breakout_candle_index > pat.s2_index, "Breakout must occur after Point 2 (High 2)"

    # Height = 200 - 180 = 20.0
    assert pat.pattern_height == 20.0
    # Target 1 = 180 - 20 = 160.0
    assert pat.target_analysis.measured_target == 160.0
    # Target 2 = 180 - 20 * 1.618 = 147.64
    assert pat.target_analysis.target_2 == 147.64
    # Stop Loss = High 2 + (0.15 * ATR) = 199.0 + (0.15 * 2.0) = 199.30
    assert pat.target_analysis.invalidation_level == 199.30
    assert pat.target_analysis.invalidation_level > pat.neckline_price, "M Stop Loss must be strictly above neckline"
    assert pat.target_analysis.invalidation_level >= pat.s2_price, "M Stop Loss must be above High 2"

def test_21_wick_only_penetration_does_not_trigger_breakout():
    """TEST 21: A candle whose wick pierces the neckline but whose close remains inside must NOT trigger a breakout."""
    l1 = SwingPoint(index=5, price=100.0, timestamp="2026-08-25T10:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True)
    mid_peak = SwingPoint(index=10, price=120.0, timestamp="2026-08-25T10:50:00Z", is_high=True, type="HH", strength=2.0, confirmed=True)
    l2 = SwingPoint(index=15, price=101.0, timestamp="2026-08-25T11:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    swings = [l1, mid_peak, l2]

    # Candle 18 has high=125 (wick above 120), but close=119 (below neckline 120)
    candles = [
        Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=110, high=115, low=105, close=110, volume=1000)
        for i in range(25)
    ]
    candles[18] = Candle(timestamp="2026-08-25T10:90:00Z", open=118, high=125, low=116, close=119, volume=2000)

    events, confirmed, active, candidates = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles,
        swings=swings,
        symbol="INFY",
        timeframe="15M",
        trendlines=[],
        df_indicators=None,
        atr_val=2.0
    )

    # Must NOT have confirmed breakout because close was below neckline!
    assert len(confirmed) == 0 or confirmed[0].status != "BREAKOUT_CONFIRMED", "Wick-only penetration must not trigger breakout"
    assert len(events) == 0, "No breakout events should be emitted on wick-only crosses"

def test_22_no_false_breakout_confirmed_stays_active():
    """
    TEST 22: Confirmed W and M breakouts remain active and do NOT transition to FALSE BREAKOUT.
    W: Confirmed close above neckline remains confirmed/active even if later candle closes back below neckline.
    M: Confirmed close below neckline remains confirmed/active even if later candle closes back above neckline.
    """
    # 1. Test W Pattern: confirmed breakout remains TARGET OPEN when candle closes back below neckline
    w_alert = MWBreakoutAlert(
        alert_id="mw_test_no_false_breakout_w",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="NIFTY 50",
        timeframe="15M",
        pattern_id="test_pat_w",
        s1_price=24000.0,
        s1_timestamp="2026-08-25T10:00:00Z",
        s2_price=24020.0,
        s2_timestamp="2026-08-25T11:00:00Z",
        neckline_price=24200.0,
        neckline_timestamp="2026-08-25T10:30:00Z",
        pattern_height=200.0,
        breakout_candle_timestamp="2026-08-25T11:15:00Z",
        breakout_open=24190.0,
        breakout_high=24220.0,
        breakout_low=24180.0,
        breakout_close=24210.0,
        trendline_price=24200.0,
        ema20_price=24180.0,
        measured_target=24400.0,
        target_2=24600.0,
        invalidation_level=24000.0,
        quality_score=85,
        status="TARGET OPEN",
        event_created_at="2026-08-25T11:15:00Z"
    )

    # Subsequent candle closes at 24150 (back below neckline 24200) without hitting SL (24000) or T1 (24400)
    w_subsequent_candles = [
        Candle(timestamp="2026-08-25T11:15:00Z", open=24190, high=24220, low=24180, close=24210, volume=1000),
        Candle(timestamp="2026-08-25T11:30:00Z", open=24210, high=24215, low=24140, close=24150, volume=1500)
    ]

    mw_breakout_engine._evaluate_single_alert_status(w_alert, w_subsequent_candles)
    assert w_alert.status == "TARGET OPEN", f"W breakout closing back below neckline must remain TARGET OPEN, got: {w_alert.status}"
    assert w_alert.status != "FALSE BREAKOUT", "W breakout must never transition to FALSE BREAKOUT"

    # 2. Test M Pattern: confirmed breakdown remains TARGET OPEN when candle closes back above neckline
    m_alert = MWBreakoutAlert(
        alert_id="mw_test_no_false_breakout_m",
        alert_type="M_BREAKDOWN_CONFIRMED",
        pattern_type="M",
        direction="DOWN",
        symbol="BTC/USD",
        timeframe="15M",
        pattern_id="test_pat_m",
        s1_price=65000.0,
        s1_timestamp="2026-08-25T10:00:00Z",
        s2_price=64980.0,
        s2_timestamp="2026-08-25T11:00:00Z",
        neckline_price=64500.0,
        neckline_timestamp="2026-08-25T10:30:00Z",
        pattern_height=500.0,
        breakout_candle_timestamp="2026-08-25T11:15:00Z",
        breakout_open=64520.0,
        breakout_high=64530.0,
        breakout_low=64460.0,
        breakout_close=64470.0,
        trendline_price=64500.0,
        ema20_price=64510.0,
        measured_target=64000.0,
        target_2=63500.0,
        invalidation_level=65000.0,
        quality_score=85,
        status="TARGET OPEN",
        event_created_at="2026-08-25T11:15:00Z"
    )

    # Subsequent candle closes at 64550 (back above neckline 64500) without hitting SL (65000) or T1 (64000)
    m_subsequent_candles = [
        Candle(timestamp="2026-08-25T11:15:00Z", open=64520, high=64530, low=64460, close=64470, volume=1000),
        Candle(timestamp="2026-08-25T11:30:00Z", open=64470, high=64560, low=64460, close=64550, volume=1500)
    ]

    mw_breakout_engine._evaluate_single_alert_status(m_alert, m_subsequent_candles)
    assert m_alert.status == "TARGET OPEN", f"M breakdown closing back above neckline must remain TARGET OPEN, got: {m_alert.status}"
    assert m_alert.status != "FALSE BREAKOUT", "M breakdown must never transition to FALSE BREAKOUT"

def test_23_multi_symbol_and_deduplication():
    """TEST 23: Confirmed alerts across multiple symbols (BTC/USD, RELIANCE, NIFTY) and prevent duplicates."""
    mw_breakout_engine.clear_alerts()

    # Create pattern on RELIANCE
    pat1 = WMPatternStructure(
        pattern_id="RELIANCE_15M_W_2026-08-25T10:00:00Z_2026-08-25T11:00:00Z",
        pattern_type="W",
        status="BREAKOUT_CONFIRMED",
        s1_index=5, s1_price=2800.0, s1_time="2026-08-25T10:00:00Z",
        neckline_index=10, neckline_price=2900.0, neckline_time="2026-08-25T10:30:00Z",
        s2_index=15, s2_price=2810.0, s2_time="2026-08-25T11:00:00Z",
        pattern_height=100.0, depth_atr=2.0, symmetry_atr=0.2, bar_separation=10, quality_score=85,
        breakout_candle_index=18, breakout_candle_time="2026-08-25T11:30:00Z", breakout_close=2915.0,
        target_analysis=PatternTargetAnalysis(
            pattern_height=100.0, measured_target=3000.0, target_2=3061.8,
            invalidation_level=2805.0, retest_level=2900.0, retest_status="PENDING",
            pattern_status="CONFIRMED_BREAKOUT", pattern_quality_score=85, quality_breakdown={}, interpretation=""
        )
    )

    candles = [Candle(timestamp=f"2026-08-25T10:{i*5:02d}:00Z", open=2800, high=2920, low=2790, close=2915, volume=1000) for i in range(25)]

    # Sync once
    mw_breakout_engine.sync_chart_patterns("RELIANCE", "15M", [pat1], pat1, candles)
    assert len(mw_breakout_engine.alerts) == 1
    assert mw_breakout_engine.alerts[0].symbol == "RELIANCE"

    # Sync again with same pattern -> should NOT duplicate!
    mw_breakout_engine.sync_chart_patterns("RELIANCE", "15M", [pat1], pat1, candles)
    assert len(mw_breakout_engine.alerts) == 1, "Duplicate pattern sync must update in-place without adding duplicate cards"

def test_24_detector_no_false_breakout_for_wm_patterns():
    """
    TEST 24: Verify PrecisionBreakoutDetector.detect_wm_patterns does NOT classify
    patterns as FALSE_BREAKOUT when a subsequent candle closes back across the neckline.
    """
    from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
    from app.market_structure.swings import SwingDetector

    # 1. Test W Pattern with subsequent candle closing back below neckline
    # L1 at 0 (100), Mid peak at 5 (120), L2 at 10 (101), Breakout at 12 (123 > 120), subsequent candle at 13 (close 118 < 120)
    w_candles = []
    # 0: L1
    w_candles.append(Candle(timestamp="2026-08-30T09:15:00Z", open=105, high=106, low=100, close=102, volume=1000))
    # 1-4: rise to mid peak
    for i in range(1, 5):
        w_candles.append(Candle(timestamp=f"2026-08-30T09:{15+i*5:02d}:00Z", open=102+i*3, high=105+i*3, low=101+i*3, close=104+i*3, volume=1000))
    # 5: mid peak (neckline = 120)
    w_candles.append(Candle(timestamp="2026-08-30T09:40:00Z", open=116, high=120, low=115, close=119, volume=1200))
    # 6-9: fall to L2
    for i in range(6, 10):
        w_candles.append(Candle(timestamp=f"2026-08-30T09:{15+i*5:02d}:00Z", open=118-(i-5)*4, high=119-(i-5)*4, low=114-(i-5)*4, close=115-(i-5)*4, volume=1000))
    # 10: L2 (101)
    w_candles.append(Candle(timestamp="2026-08-30T10:05:00Z", open=103, high=104, low=101, close=103, volume=1100))
    # 11: rally toward neckline
    w_candles.append(Candle(timestamp="2026-08-30T10:10:00Z", open=104, high=118, low=103, close=117, volume=1200))
    # 12: breakout candle (closes at 123 > 120)
    w_candles.append(Candle(timestamp="2026-08-30T10:15:00Z", open=118, high=124, low=117, close=123, volume=2000))
    # 13: subsequent candle closing below neckline (closes at 118 < 120), without hitting SL (101)
    w_candles.append(Candle(timestamp="2026-08-30T10:20:00Z", open=122, high=123, low=117, close=118, volume=1500))
    # 14: active candle
    w_candles.append(Candle(timestamp="2026-08-30T10:25:00Z", open=118, high=119, low=116, close=117, volume=1000))

    swings, _ = SwingDetector.detect_swings(w_candles, swing_length=2, confirmation_candles=1)
    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=w_candles,
        swings=swings,
        trendlines=[],
        df_indicators=None,
        symbol="NIFTY 50",
        timeframe="15M",
        atr_val=2.0
    )

    for p in confirmed:
        assert p.status != "FALSE_BREAKOUT", "W pattern status must never be FALSE_BREAKOUT"
        assert p.status != "FALSE BREAKOUT", "W pattern status must never be FALSE BREAKOUT"
        if p.breakout_candle_index == 12:
            assert p.status in ["BREAKOUT_CONFIRMED", "HIGH_CONFLUENCE_CONFIRMED"], f"Confirmed W breakout must stay confirmed, got: {p.status}"


# =========================================================================
# GENERIC MULTI-SYMBOL & MULTI-TIMEFRAME HISTORICAL OUTCOME LIFECYCLE TESTS
# Note: RELIANCE 1H is a reproduction case, not the scope of the fix.
# The scope is the complete W/M historical outcome lifecycle across all
# configured symbols and all supported timeframes.
# =========================================================================

def test_25_generic_w_t1_winner_protected_against_subsequent_crash():
    """
    GENERIC TEST: Any symbol (e.g. BTC/USD 15M) W breakout reaches Target 1,
    then subsequent candles crash far below the stop loss.
    Outcome must remain TARGET 1 HIT and NEVER become SL HIT.
    """
    mw_breakout_engine.clear_alerts()
    alert = MWBreakoutAlert(
        alert_id="mw_test_btc_15m_w",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="BTC/USD",
        ticker="BTC-USD",
        timeframe="15M",
        pattern_id="btc_w_1",
        s1_price=60000.0,
        s1_timestamp="2026-08-20T10:00:00Z",
        s2_price=60100.0,
        s2_timestamp="2026-08-20T11:00:00Z",
        neckline_price=61000.0,
        neckline_timestamp="2026-08-20T10:30:00Z",
        pattern_height=1000.0,
        breakout_candle_timestamp="2026-08-20T11:15:00Z",
        breakout_open=60950.0,
        breakout_high=61100.0,
        breakout_low=60900.0,
        breakout_close=61050.0,
        trendline_price=61000.0,
        ema20_price=60950.0,
        measured_target=62000.0,      # T1
        target_2=63000.0,             # T2
        invalidation_level=59900.0,   # SL
        quality_score=85,
        status="TARGET OPEN",
        event_created_at="2026-08-20T11:15:00Z"
    )
    mw_breakout_engine.alerts.append(alert)

    # Subsequent candles:
    # 1. Touches 62100 (T1 hit!)
    # 2. Reverses and crashes to 58000 (below SL 59900)
    subsequent_candles = [
        Candle(timestamp="2026-08-20T11:30:00Z", open=61100, high=62200, low=61050, close=62150, volume=100),
        Candle(timestamp="2026-08-20T11:45:00Z", open=62150, high=62200, low=58000, close=58500, volume=200)
    ]

    mw_breakout_engine.replay_alert_lifecycle(alert, subsequent_candles)
    assert alert.status == "TARGET 1 HIT", f"W breakout hitting T1 must remain TARGET 1 HIT forever even after crash, got: {alert.status}"


def test_26_generic_w_t2_terminal_winner_is_immutable():
    """
    GENERIC TEST: Any symbol (e.g. NIFTY 50 1H) W breakout reaches Target 2.
    Outcome must become TARGET 2 HIT and cannot be changed by any later action.
    """
    mw_breakout_engine.clear_alerts()
    alert = MWBreakoutAlert(
        alert_id="mw_test_nifty_1h_w",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="NIFTY 50",
        ticker="^NSEI",
        timeframe="1H",
        pattern_id="nifty_w_1",
        s1_price=24000.0,
        s1_timestamp="2026-08-21T09:15:00Z",
        s2_price=24020.0,
        s2_timestamp="2026-08-21T11:15:00Z",
        neckline_price=24300.0,
        neckline_timestamp="2026-08-21T10:15:00Z",
        pattern_height=300.0,
        breakout_candle_timestamp="2026-08-21T12:15:00Z",
        breakout_open=24280.0,
        breakout_high=24350.0,
        breakout_low=24270.0,
        breakout_close=24320.0,
        trendline_price=24300.0,
        ema20_price=24250.0,
        measured_target=24600.0,      # T1 = 24300 + 300 = 24600
        target_2=24900.0,             # T2 = 24300 + 600 = 24900
        invalidation_level=23950.0,   # SL
        quality_score=88,
        status="TARGET OPEN",
        event_created_at="2026-08-21T12:15:00Z"
    )
    mw_breakout_engine.alerts.append(alert)

    # Candle 1 hits T1 (24650)
    # Candle 2 hits T2 (24950)
    # Candle 3 crashes to 23000
    candles = [
        Candle(timestamp="2026-08-21T13:15:00Z", open=24330, high=24650, low=24320, close=24620, volume=5000),
        Candle(timestamp="2026-08-21T14:15:00Z", open=24620, high=24950, low=24600, close=24920, volume=7000),
        Candle(timestamp="2026-08-21T15:15:00Z", open=24900, high=24900, low=23000, close=23500, volume=9000),
    ]

    mw_breakout_engine.replay_alert_lifecycle(alert, candles)
    assert alert.status == "TARGET 2 HIT", f"W breakout hitting T2 must be TARGET 2 HIT, got: {alert.status}"


def test_27_generic_w_sl_hit_before_target():
    """
    GENERIC TEST: Any symbol (e.g. BANK NIFTY 5M) W breakout hits SL before any target.
    Must be marked SL HIT and cannot be revived by subsequent rally.
    """
    mw_breakout_engine.clear_alerts()
    alert = MWBreakoutAlert(
        alert_id="mw_test_bnf_5m_w",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="BANK NIFTY",
        ticker="^NSEBANK",
        timeframe="5M",
        pattern_id="bnf_w_1",
        s1_price=51000.0,
        s1_timestamp="2026-08-22T09:15:00Z",
        s2_price=51020.0,
        s2_timestamp="2026-08-22T09:45:00Z",
        neckline_price=51300.0,
        neckline_timestamp="2026-08-22T09:30:00Z",
        pattern_height=300.0,
        breakout_candle_timestamp="2026-08-22T09:55:00Z",
        breakout_open=51280.0,
        breakout_high=51350.0,
        breakout_low=51270.0,
        breakout_close=51320.0,
        trendline_price=51300.0,
        ema20_price=51250.0,
        measured_target=51600.0,
        target_2=51900.0,
        invalidation_level=50950.0,
        quality_score=80,
        status="TARGET OPEN",
        event_created_at="2026-08-22T09:55:00Z"
    )
    mw_breakout_engine.alerts.append(alert)

    # Candle 1 drops straight below SL to 50900
    # Candle 2 rallies to 52000
    candles = [
        Candle(timestamp="2026-08-22T10:00:00Z", open=51300, high=51310, low=50900, close=50920, volume=1000),
        Candle(timestamp="2026-08-22T10:05:00Z", open=50950, high=52000, low=50950, close=51980, volume=2000),
    ]

    mw_breakout_engine.replay_alert_lifecycle(alert, candles)
    assert alert.status == "SL HIT", f"W breakout hitting SL first must remain SL HIT, got: {alert.status}"


def test_28_generic_m_t1_winner_protected_against_subsequent_rally():
    """
    GENERIC TEST: Any symbol (e.g. TCS 4H) M breakdown hits Target 1,
    then subsequent candles rally far above SL.
    Outcome must remain TARGET 1 HIT and NEVER become SL HIT.
    """
    mw_breakout_engine.clear_alerts()
    alert = MWBreakoutAlert(
        alert_id="mw_test_tcs_4h_m",
        alert_type="M_BREAKDOWN_CONFIRMED",
        pattern_type="M",
        direction="DOWN",
        symbol="TCS",
        ticker="TCS.NS",
        timeframe="4H",
        pattern_id="tcs_m_1",
        s1_price=4500.0,
        s1_timestamp="2026-08-10T09:15:00Z",
        s2_price=4490.0,
        s2_timestamp="2026-08-12T09:15:00Z",
        neckline_price=4400.0,
        neckline_timestamp="2026-08-11T09:15:00Z",
        pattern_height=100.0,
        breakout_candle_timestamp="2026-08-13T09:15:00Z",
        breakout_open=4410.0,
        breakout_high=4415.0,
        breakout_low=4380.0,
        breakout_close=4385.0,
        trendline_price=4400.0,
        ema20_price=4420.0,
        measured_target=4300.0,      # T1 = 4400 - 100 = 4300
        target_2=4200.0,             # T2 = 4400 - 200 = 4200
        invalidation_level=4520.0,   # SL
        quality_score=85,
        status="TARGET OPEN",
        event_created_at="2026-08-13T09:15:00Z"
    )
    mw_breakout_engine.alerts.append(alert)

    # Subsequent candles:
    # 1. Touches 4290 (T1 hit!)
    # 2. Reverses and rallies to 4600 (above SL 4520)
    subsequent_candles = [
        Candle(timestamp="2026-08-14T09:15:00Z", open=4380, high=4385, low=4280, close=4295, volume=1000),
        Candle(timestamp="2026-08-15T09:15:00Z", open=4300, high=4650, low=4290, close=4620, volume=2000)
    ]

    mw_breakout_engine.replay_alert_lifecycle(alert, subsequent_candles)
    assert alert.status == "TARGET 1 HIT", f"M breakdown hitting T1 must remain TARGET 1 HIT forever even after rally, got: {alert.status}"


def test_29_generic_m_t2_terminal_winner():
    """
    GENERIC TEST: Any symbol (e.g. INFY 15M) M breakdown reaches Target 2.
    Outcome must be TARGET 2 HIT.
    """
    mw_breakout_engine.clear_alerts()
    alert = MWBreakoutAlert(
        alert_id="mw_test_infy_15m_m",
        alert_type="M_BREAKDOWN_CONFIRMED",
        pattern_type="M",
        direction="DOWN",
        symbol="INFY",
        ticker="INFY.NS",
        timeframe="15M",
        pattern_id="infy_m_1",
        s1_price=1800.0,
        s1_timestamp="2026-08-20T10:00:00Z",
        s2_price=1798.0,
        s2_timestamp="2026-08-20T11:00:00Z",
        neckline_price=1760.0,
        neckline_timestamp="2026-08-20T10:30:00Z",
        pattern_height=40.0,
        breakout_candle_timestamp="2026-08-20T11:15:00Z",
        breakout_open=1762.0,
        breakout_high=1764.0,
        breakout_low=1752.0,
        breakout_close=1754.0,
        trendline_price=1760.0,
        ema20_price=1765.0,
        measured_target=1720.0,
        target_2=1680.0,
        invalidation_level=1810.0,
        quality_score=84,
        status="TARGET OPEN",
        event_created_at="2026-08-20T11:15:00Z"
    )
    mw_breakout_engine.alerts.append(alert)

    candles = [
        Candle(timestamp="2026-08-20T11:30:00Z", open=1754, high=1755, low=1715, close=1718, volume=500),
        Candle(timestamp="2026-08-20T11:45:00Z", open=1718, high=1720, low=1675, close=1678, volume=800),
    ]

    mw_breakout_engine.replay_alert_lifecycle(alert, candles)
    assert alert.status == "TARGET 2 HIT", f"M breakdown reaching T2 must be TARGET 2 HIT, got: {alert.status}"


def test_30_generic_m_sl_hit_before_target():
    """
    GENERIC TEST: Any symbol (e.g. ICICIBANK 1H) M breakdown hits SL before any target.
    Must be marked SL HIT and cannot be revived.
    """
    mw_breakout_engine.clear_alerts()
    alert = MWBreakoutAlert(
        alert_id="mw_test_icici_1h_m",
        alert_type="M_BREAKDOWN_CONFIRMED",
        pattern_type="M",
        direction="DOWN",
        symbol="ICICIBANK",
        ticker="ICICIBANK.NS",
        timeframe="1H",
        pattern_id="icici_m_1",
        s1_price=1200.0,
        s1_timestamp="2026-08-22T09:15:00Z",
        s2_price=1198.0,
        s2_timestamp="2026-08-22T11:15:00Z",
        neckline_price=1170.0,
        neckline_timestamp="2026-08-22T10:15:00Z",
        pattern_height=30.0,
        breakout_candle_timestamp="2026-08-22T12:15:00Z",
        breakout_open=1172.0,
        breakout_high=1173.0,
        breakout_low=1162.0,
        breakout_close=1164.0,
        trendline_price=1170.0,
        ema20_price=1175.0,
        measured_target=1140.0,
        target_2=1110.0,
        invalidation_level=1205.0,
        quality_score=82,
        status="TARGET OPEN",
        event_created_at="2026-08-22T12:15:00Z"
    )
    mw_breakout_engine.alerts.append(alert)

    # Immediately spikes to 1210 (above SL 1205)
    candles = [
        Candle(timestamp="2026-08-22T13:15:00Z", open=1165, high=1215, low=1160, close=1210, volume=3000),
    ]

    mw_breakout_engine.replay_alert_lifecycle(alert, candles)
    assert alert.status == "SL HIT", f"M breakdown hitting SL first must be SL HIT, got: {alert.status}"


def test_31_repeated_scans_preserve_terminal_and_winner_states():
    """
    GENERIC TEST: Repeated scans and chart syncs across cycles must never alter
    or reset terminal states (TARGET 2 HIT, SL HIT) or locked winning states (TARGET 1 HIT).
    """
    mw_breakout_engine.clear_alerts()
    alert_t1 = MWBreakoutAlert(
        alert_id="mw_test_hparam_t1",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="HDFCBANK",
        ticker="HDFCBANK.NS",
        timeframe="15M",
        pattern_id="hdfc_w_1",
        s1_price=1600.0,
        s1_timestamp="2026-08-20T10:00:00Z",
        s2_price=1605.0,
        s2_timestamp="2026-08-20T11:00:00Z",
        neckline_price=1640.0,
        neckline_timestamp="2026-08-20T10:30:00Z",
        pattern_height=40.0,
        breakout_candle_timestamp="2026-08-20T11:15:00Z",
        breakout_open=1638.0,
        breakout_high=1645.0,
        breakout_low=1635.0,
        breakout_close=1642.0,
        trendline_price=1640.0,
        ema20_price=1630.0,
        measured_target=1680.0,
        target_2=1720.0,
        invalidation_level=1590.0,
        quality_score=85,
        status="TARGET 1 HIT",
        event_created_at="2026-08-20T11:15:00Z"
    )
    mw_breakout_engine.alerts.append(alert_t1)

    # Synthesis run with price collapsing to 1400 (far below SL)
    synth = _make_synth("HDFCBANK", price=1400.0)
    mw_breakout_engine._update_existing_alert_statuses(synth)

    # Must stay TARGET 1 HIT!
    assert alert_t1.status == "TARGET 1 HIT", "TARGET 1 HIT must be preserved across scan cycles"


def test_32_strict_timeframe_isolation():
    """
    GENERIC TEST: Timeframe fidelity. A 1H alert must only be evaluated against 1H candles.
    If only 5M or 15M candles are provided, 1H alert status must remain unchanged.
    """
    mw_breakout_engine.clear_alerts()
    alert_1h = MWBreakoutAlert(
        alert_id="mw_test_sbin_1h",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="SBIN",
        ticker="SBIN.NS",
        timeframe="1H",
        pattern_id="sbin_1h_w",
        s1_price=800.0,
        s1_timestamp="2026-08-20T10:00:00Z",
        s2_price=802.0,
        s2_timestamp="2026-08-20T12:00:00Z",
        neckline_price=820.0,
        neckline_timestamp="2026-08-20T11:00:00Z",
        pattern_height=20.0,
        breakout_candle_timestamp="2026-08-20T13:00:00Z",
        breakout_open=818.0,
        breakout_high=824.0,
        breakout_low=817.0,
        breakout_close=822.0,
        trendline_price=820.0,
        ema20_price=815.0,
        measured_target=840.0,
        target_2=860.0,
        invalidation_level=795.0,
        quality_score=85,
        status="TARGET OPEN",
        event_created_at="2026-08-20T13:00:00Z"
    )
    mw_breakout_engine.alerts.append(alert_1h)

    # Provide only 5M candles that touch 790 (which would be SL breach if cross-timeframe were allowed)
    m5_candles = [
        Candle(timestamp="2026-08-20T13:05:00Z", open=820, high=821, low=790, close=792, volume=100)
    ]
    synth = _make_synth("SBIN", price=820.0)

    # Call _update_existing_alert_statuses with only 5M candles in mtf_candles
    mw_breakout_engine._update_existing_alert_statuses(synth, mtf_candles={"5M": m5_candles})

    # The 1H alert must NOT have evaluated against 5M candles and must remain TARGET OPEN
    assert alert_1h.status == "TARGET OPEN", "1H alert must not be evaluated against 5M candles"


def test_33_zero_overwrite_by_today_market_price():
    """
    GENERIC TEST: Completed historical trades cannot be overwritten by today's live market price.
    """
    mw_breakout_engine.clear_alerts()
    alert_t1 = MWBreakoutAlert(
        alert_id="mw_test_airtel_4h",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="BHARTI AIRTEL",
        ticker="BHARTIARTL.NS",
        timeframe="4H",
        pattern_id="airtel_4h_w",
        s1_price=1400.0,
        s1_timestamp="2026-07-15T09:15:00Z",
        s2_price=1405.0,
        s2_timestamp="2026-07-20T09:15:00Z",
        neckline_price=1460.0,
        neckline_timestamp="2026-07-18T09:15:00Z",
        pattern_height=60.0,
        breakout_candle_timestamp="2026-07-22T09:15:00Z",
        breakout_open=1455.0,
        breakout_high=1468.0,
        breakout_low=1452.0,
        breakout_close=1465.0,
        trendline_price=1460.0,
        ema20_price=1440.0,
        measured_target=1520.0,
        target_2=1580.0,
        invalidation_level=1390.0,
        quality_score=87,
        status="TARGET 1 HIT",
        event_created_at="2026-07-22T09:15:00Z"
    )
    mw_breakout_engine.alerts.append(alert_t1)

    # Today's price in live market is 1350 (far below invalidation_level 1390)
    synth = _make_synth("BHARTI AIRTEL", price=1350.0)
    mw_breakout_engine.process_synthesis_with_updates(synth)

    assert alert_t1.status == "TARGET 1 HIT", "Historical trade with TARGET 1 HIT must never be overwritten to SL HIT by today's price"


def test_34_regression_case_reliance_1h_w_breakout():
    """
    REPRODUCTION / REGRESSION TEST:
    Verifies that the historical RELIANCE 1H W breakout from 2026-07-30T11:15:00+05:30
    evaluates correctly to TARGET 1 HIT on historical replay.
    Geometry:
    - S1 (2026-07-23 10:15): ₹1,268.05
    - Mid Peak Neckline (2026-07-27 10:15): ₹1,296.12
    - S2 (2026-07-29 11:15): ₹1,269.80
    - Pattern Height: ₹28.07
    - Breakout Candle (2026-07-30 11:15): Close ₹1,299.13 > Neckline ₹1,296.12
    - Target 1: ₹1,324.19 (measured target)
    - Invalidation SL: ₹1,265.14
    - Candle on 2026-08-07 09:15 touched High ₹1,331.50 >= ₹1,324.19
    - Lowest low between breakout and Aug 7 was ₹1,271.10 (SL of ₹1,265.14 was never touched).
    Outcome: TARGET 1 HIT.
    """
    mw_breakout_engine.clear_alerts()
    rel_alert = MWBreakoutAlert(
        alert_id="mw_RELIANCE_1H_W_2026-07-30T11-15-00-05-30",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="RELIANCE",
        ticker="RELIANCE.NS",
        timeframe="1H",
        pattern_id="RELIANCE_1H_W_HISTORICAL",
        s1_price=1268.05,
        s1_timestamp="2026-07-23T10:15:00+05:30",
        s2_price=1269.80,
        s2_timestamp="2026-07-29T11:15:00+05:30",
        neckline_price=1296.12,
        neckline_timestamp="2026-07-27T10:15:00+05:30",
        pattern_height=28.07,
        breakout_candle_timestamp="2026-07-30T11:15:00+05:30",
        breakout_open=1294.0,
        breakout_high=1301.0,
        breakout_low=1293.0,
        breakout_close=1299.13,
        trendline_price=1296.12,
        ema20_price=1285.0,
        measured_target=1324.19,
        target_2=1352.26,
        invalidation_level=1265.14,
        quality_score=86,
        status="TARGET OPEN",
        event_created_at="2026-07-30T11:15:00+05:30"
    )
    mw_breakout_engine.alerts.append(rel_alert)

    # Replay subsequent candles chronologically
    subsequent_candles = [
        # Candle 1: Retest consolidation (Low 1275, High 1305)
        Candle(timestamp="2026-07-30T12:15:00+05:30", open=1299.0, high=1305.0, low=1275.0, close=1285.0, volume=50000),
        # Candle 2: Consolidation (Low 1271.10 - lowest low before rally, above SL 1265.14)
        Candle(timestamp="2026-08-01T09:15:00+05:30", open=1285.0, high=1290.0, low=1271.10, close=1288.0, volume=60000),
        # Candle 3: Rally starts
        Candle(timestamp="2026-08-05T09:15:00+05:30", open=1290.0, high=1315.0, low=1288.0, close=1312.0, volume=80000),
        # Candle 4: Touches High 1331.50 (exceeds T1 1324.19)
        Candle(timestamp="2026-08-07T09:15:00+05:30", open=1315.0, high=1331.50, low=1310.0, close=1328.0, volume=120000),
        # Candle 5: Days later market drops to 1250 (below SL)
        Candle(timestamp="2026-08-20T09:15:00+05:30", open=1300.0, high=1302.0, low=1250.0, close=1255.0, volume=90000),
    ]

    mw_breakout_engine.replay_alert_lifecycle(rel_alert, subsequent_candles)
    assert rel_alert.status == "TARGET 1 HIT", f"RELIANCE 1H W breakout must be TARGET 1 HIT, got: {rel_alert.status}"





