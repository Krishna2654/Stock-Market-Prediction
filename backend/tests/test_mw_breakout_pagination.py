import pytest
from datetime import datetime, timedelta, timezone
from app.alerts.mw_breakout_engine import MWBreakoutAlertEngine
from app.models.schemas import MWBreakoutAlert, PaginatedMWBreakoutsResponse

def _generate_synthetic_alerts(count: int, start_time: datetime = None) -> list[MWBreakoutAlert]:
    if start_time is None:
        start_time = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    alerts = []
    for i in range(count):
        ts = (start_time - timedelta(minutes=15 * i)).isoformat()
        pt = "W" if i % 2 == 0 else "M"
        sym_num = str(i % 5).zfill(2)
        alert = MWBreakoutAlert(
            alert_id=f"alert_test_{str(i).zfill(4)}",
            alert_type="W_BREAKOUT_CONFIRMED" if pt == "W" else "M_BREAKDOWN_CONFIRMED",
            pattern_type=pt,
            direction="UP" if pt == "W" else "DOWN",
            symbol=f"SYM_{sym_num}",
            ticker=f"TICK_{sym_num}",
            timeframe="15M",
            pattern_id=f"pat_{str(i).zfill(4)}",
            s1_price=100.0 + i,
            s1_timestamp=ts,
            s2_price=100.5 + i,
            s2_timestamp=ts,
            neckline_price=105.0 + i,
            neckline_timestamp=ts,
            pattern_height=5.0,
            breakout_candle_timestamp=ts,
            breakout_open=104.0,
            breakout_high=106.0,
            breakout_low=103.5,
            breakout_close=105.8,
            trendline_price=105.0,
            ema20_price=104.5,
            volume=1500.0,
            relative_volume=1.4,
            measured_target=110.0 + i if pt == "W" else 100.0 - i,
            target_2=115.0 + i if pt == "W" else 95.0 - i,
            invalidation_level=99.0 + i if pt == "W" else 106.0 + i,
            quality_score=85,
            reversal_score=40,
            trendline_score=25,
            ema_score=20,
            status="TARGET OPEN",
            trade_quality="HIGH",
            entry_status="VALID",
            event_created_at=ts,
            read=False
        )
        alerts.append(alert)
    return alerts

@pytest.fixture
def fresh_engine(tmp_path, monkeypatch):
    test_store = tmp_path / "test_pagination_store.json"
    monkeypatch.setattr("app.alerts.mw_breakout_engine.STORAGE_FILE", test_store)
    engine = MWBreakoutAlertEngine()
    engine.alerts.clear()
    engine.seen_event_keys.clear()
    return engine

def test_1_create_more_than_200_alerts(fresh_engine):
    alerts_300 = _generate_synthetic_alerts(300)
    fresh_engine.alerts = list(alerts_300)
    fresh_engine.alerts.sort(key=lambda a: (a.breakout_candle_timestamp or "", a.alert_id or ""), reverse=True)
    fresh_engine._save_to_storage()
    assert len(fresh_engine.alerts) == 300
    assert len(fresh_engine.alerts) > 200

def test_2_create_1054_alerts_no_cap(fresh_engine):
    alerts_1054 = _generate_synthetic_alerts(1054)
    fresh_engine.alerts = list(alerts_1054)
    fresh_engine.alerts.sort(key=lambda a: (a.breakout_candle_timestamp or "", a.alert_id or ""), reverse=True)
    fresh_engine._save_to_storage()
    stats = fresh_engine.get_summary_stats()
    assert stats["total_count"] == 1054
    assert len(fresh_engine.alerts) == 1054

def test_3_page_1_limit_50(fresh_engine):
    fresh_engine.alerts = _generate_synthetic_alerts(1054)
    items, total, total_pages, has_next, has_prev = fresh_engine.get_paginated_alerts(page=1, limit=50)
    assert len(items) == 50
    assert total == 1054
    assert total_pages == 22
    assert has_next is True
    assert has_prev is False

def test_4_page_2_limit_50(fresh_engine):
    fresh_engine.alerts = _generate_synthetic_alerts(1054)
    items, total, total_pages, has_next, has_prev = fresh_engine.get_paginated_alerts(page=2, limit=50)
    assert len(items) == 50
    assert total == 1054
    assert has_next is True
    assert has_prev is True

def test_5_page_1_newer_than_page_2(fresh_engine):
    fresh_engine.alerts = _generate_synthetic_alerts(1054)
    p1_items, _, _, _, _ = fresh_engine.get_paginated_alerts(page=1, limit=50)
    p2_items, _, _, _, _ = fresh_engine.get_paginated_alerts(page=2, limit=50)
    p1_oldest = p1_items[-1].breakout_candle_timestamp
    p2_newest = p2_items[0].breakout_candle_timestamp
    assert p1_oldest >= p2_newest

def test_6_last_page_contains_remaining_records(fresh_engine):
    fresh_engine.alerts = _generate_synthetic_alerts(1054)
    items, total, total_pages, has_next, has_prev = fresh_engine.get_paginated_alerts(page=22, limit=50)
    assert len(items) == 4
    assert total_pages == 22
    assert has_next is False
    assert has_prev is True

def test_7_w_pattern_filtering(fresh_engine):
    fresh_engine.alerts = _generate_synthetic_alerts(1054)
    w_items, w_total, total_pages, _, _ = fresh_engine.get_paginated_alerts(pattern_type="W", page=1, limit=50)
    assert len(w_items) == 50
    assert all(a.pattern_type == "W" for a in w_items)
    assert w_total == 527

def test_8_m_pattern_filtering(fresh_engine):
    fresh_engine.alerts = _generate_synthetic_alerts(1054)
    m_items, m_total, total_pages, _, _ = fresh_engine.get_paginated_alerts(pattern_type="M", page=1, limit=50)
    assert len(m_items) == 50
    assert all(a.pattern_type == "M" for a in m_items)
    assert m_total == 527

def test_9_duplicate_update_records_deduplicated_across_pages(fresh_engine):
    alerts = _generate_synthetic_alerts(100)
    duplicate_alert = alerts[0].model_copy()
    duplicate_alert.alert_id = "dup_copy_id"
    alerts.insert(10, duplicate_alert)
    fresh_engine.alerts = alerts
    p1_items, total, _, _, _ = fresh_engine.get_paginated_alerts(page=1, limit=50)
    p2_items, _, _, _, _ = fresh_engine.get_paginated_alerts(page=2, limit=50)
    all_seen_pat_ids = [a.pattern_id for a in p1_items + p2_items]
    assert len(all_seen_pat_ids) == len(set(all_seen_pat_ids))
    assert total == 100

def test_10_new_live_breakout_prepended_no_truncation(fresh_engine):
    fresh_engine.alerts = _generate_synthetic_alerts(1054)
    new_breakout = MWBreakoutAlert(
        alert_id="live_breakout_1055",
        alert_type="W_BREAKOUT_CONFIRMED",
        pattern_type="W",
        direction="UP",
        symbol="LIVE_SYM",
        timeframe="15M",
        pattern_id="live_pat_1055",
        s1_price=200.0,
        s1_timestamp="2026-09-02T13:00:00Z",
        s2_price=200.5,
        s2_timestamp="2026-09-02T13:00:00Z",
        neckline_price=210.0,
        neckline_timestamp="2026-09-02T13:00:00Z",
        pattern_height=10.0,
        breakout_candle_timestamp="2026-09-02T13:00:00Z",
        breakout_open=209.0,
        breakout_high=212.0,
        breakout_low=208.5,
        breakout_close=211.5,
        trendline_price=210.0,
        ema20_price=209.0,
        measured_target=220.0,
        invalidation_level=199.0,
        quality_score=90,
        event_created_at="2026-09-02T13:00:00Z"
    )
    fresh_engine.alerts.insert(0, new_breakout)
    fresh_engine.alerts.sort(key=lambda a: (a.breakout_candle_timestamp or "", a.alert_id or ""), reverse=True)
    assert len(fresh_engine.alerts) == 1055
    p1_items, total, _, _, _ = fresh_engine.get_paginated_alerts(page=1, limit=50)
    assert total == 1055
    assert p1_items[0].alert_id == "live_breakout_1055"

def test_11_summary_stats_independent_of_page(fresh_engine):
    fresh_engine.alerts = _generate_synthetic_alerts(1054)
    p1_items, _, _, _, _ = fresh_engine.get_paginated_alerts(page=1, limit=50)
    assert len(p1_items) == 50
    stats = fresh_engine.get_summary_stats()
    assert stats["total_count"] == 1054
    assert stats["w_breakouts"] == 527
    assert stats["m_breakdowns"] == 527

def test_12_historical_pattern_chart_references_preserved(fresh_engine):
    alerts = _generate_synthetic_alerts(300)
    old_alert = alerts[-1]
    old_alert.nearest_support = 95.0
    old_alert.nearest_resistance = 115.0
    fresh_engine.alerts = alerts
    retrieved = fresh_engine.get_alert_by_id(old_alert.alert_id)
    assert retrieved is not None
    assert retrieved.pattern_id == old_alert.pattern_id
    assert retrieved.s1_price == old_alert.s1_price
    assert retrieved.neckline_price == old_alert.neckline_price
    assert retrieved.measured_target == old_alert.measured_target
