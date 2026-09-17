import pytest
import sqlite3
import threading
from pathlib import Path
from typing import List
from app.models.schemas import Candle, SwingPoint, MWBreakoutAlert
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.alerts.mw_breakout_engine import MWBreakoutAlertEngine
from app.core.config import settings

@pytest.fixture(autouse=True)
def isolate_store(tmp_path, monkeypatch):
    monkeypatch.setattr("app.alerts.mw_breakout_engine.STORAGE_FILE", tmp_path / "test_mw_store.json")

def create_test_db(db_path: Path):
    src_db = Path("backend/data/market_analyzer.db")
    if src_db.exists():
        with sqlite3.connect(str(src_db)) as s_conn:
            ddl = s_conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='mw_breakout_alerts'").fetchone()[0]
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(ddl)
            conn.commit()
    else:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mw_breakout_alerts (
                    alert_id VARCHAR PRIMARY KEY,
                    alert_type VARCHAR,
                    pattern_type VARCHAR,
                    direction VARCHAR,
                    symbol VARCHAR,
                    ticker VARCHAR,
                    timeframe VARCHAR,
                    pattern_id VARCHAR,
                    s1_price FLOAT,
                    s1_timestamp VARCHAR,
                    s2_price FLOAT,
                    s2_timestamp VARCHAR,
                    neckline_price FLOAT,
                    neckline_timestamp VARCHAR,
                    pattern_height FLOAT,
                    breakout_candle_timestamp VARCHAR,
                    breakout_open FLOAT,
                    breakout_high FLOAT,
                    breakout_low FLOAT,
                    breakout_close FLOAT,
                    trendline_price FLOAT,
                    ema20_price FLOAT,
                    volume FLOAT,
                    relative_volume FLOAT,
                    measured_target FLOAT,
                    target_2 FLOAT,
                    nearest_support FLOAT,
                    nearest_resistance FLOAT,
                    invalidation_level FLOAT,
                    quality_score INTEGER,
                    quality_breakdown JSON,
                    reversal_score INTEGER,
                    trendline_score INTEGER,
                    ema_score INTEGER,
                    reversal_points INTEGER,
                    trendline_points INTEGER,
                    ema_points INTEGER,
                    status VARCHAR,
                    trade_quality VARCHAR,
                    entry_status VARCHAR,
                    outcome_timestamp VARCHAR,
                    stop_loss FLOAT,
                    event_created_at VARCHAR,
                    read BOOLEAN,
                    CONSTRAINT uq_mw_breakout_identity UNIQUE (symbol, timeframe, pattern_type, breakout_candle_timestamp)
                )
            """)
            conn.commit()


def make_test_alert(
    symbol: str = "TEST",
    timeframe: str = "5M",
    pattern_type: str = "W",
    s1_time: str = "2026-09-10T10:40:00Z",
    neckline_time: str = "2026-09-10T10:50:00Z",
    breakout_time: str = "2026-09-10T11:05:00Z",
    breakout_close: float = 118.0,
    quality_score: int = 90
) -> MWBreakoutAlert:
    clean_sym = symbol.replace(" ", "_")
    pattern_id = f"{clean_sym}_{timeframe}_{pattern_type}_{s1_time}_{neckline_time}"
    clean_pat_id = pattern_id.replace(":", "-").replace(".", "-").replace("/", "_").replace(" ", "_")
    alert_id = f"mw_{clean_pat_id}"
    is_w = pattern_type == "W"
    return MWBreakoutAlert(
        alert_id=alert_id,
        alert_type="W_BREAKOUT_CONFIRMED" if is_w else "M_BREAKDOWN_CONFIRMED",
        pattern_type=pattern_type,
        direction="UP" if is_w else "DOWN",
        symbol=symbol,
        ticker=f"{clean_sym}.NS",
        timeframe=timeframe,
        pattern_id=pattern_id,
        s1_price=100.0 if is_w else 200.0,
        s1_timestamp=s1_time,
        s2_price=102.0 if is_w else 198.0,
        s2_timestamp="2026-09-10T11:00:00Z",
        neckline_price=115.0 if is_w else 185.0,
        neckline_timestamp=neckline_time,
        pattern_height=15.0,
        breakout_candle_timestamp=breakout_time,
        breakout_open=102.0 if is_w else 198.0,
        breakout_high=119.0 if is_w else 198.0,
        breakout_low=102.0 if is_w else 181.0,
        breakout_close=breakout_close,
        trendline_price=114.0 if is_w else 186.0,
        ema20_price=110.0 if is_w else 190.0,
        volume=2500.0,
        relative_volume=2.5,
        measured_target=130.0 if is_w else 170.0,
        target_2=139.27 if is_w else 160.73,
        invalidation_level=102.0 if is_w else 198.0,
        quality_score=quality_score,
        status="TARGET OPEN",
        event_created_at=breakout_time
    )


# ============================================================================
# 1. SINGLE W BREAKOUT: SUBSEQUENT CANDLES DO NOT CREATE EXTRA EVENTS
# ============================================================================
def test_1_w_breakout_single_event_subsequent_candles_ignored():
    """Single structural W pattern breaks at T_0. Later candles closing above neckline must NOT emit extra events."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-09-10T09:{i*5:02d}:00Z", open=200 - i*4, high=202 - i*4, low=198 - i*4, close=199 - i*4, volume=1000)
        for i in range(20)
    ]
    extra_candles = [
        Candle(timestamp="2026-09-10T10:40:00Z", open=105, high=107, low=99.5, close=100.0, volume=1500), # 20: L1
        Candle(timestamp="2026-09-10T10:45:00Z", open=100, high=110, low=100, close=108.0, volume=1200),   # 21
        Candle(timestamp="2026-09-10T10:50:00Z", open=108, high=115.5, low=107, close=115.0, volume=1400), # 22: Neckline
        Candle(timestamp="2026-09-10T10:55:00Z", open=115, high=115, low=105, close=106.0, volume=1100),   # 23
        Candle(timestamp="2026-09-10T11:00:00Z", open=106, high=108, low=101.5, close=102.0, volume=1300), # 24: L2
        Candle(timestamp="2026-09-10T11:05:00Z", open=102, high=119, low=102, close=118.0, volume=2500),   # 25: First Breakout
        Candle(timestamp="2026-09-10T11:10:00Z", open=118, high=123, low=117, close=122.0, volume=2200),   # 26: Subsequent
        Candle(timestamp="2026-09-10T11:15:00Z", open=122, high=126, low=121, close=125.0, volume=2000),   # 27: Subsequent
    ]
    candles.extend(extra_candles)

    swings = [
        SwingPoint(index=0, price=200.0, timestamp="2026-09-10T09:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=180.0, timestamp="2026-09-10T09:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=160.0, timestamp="2026-09-10T09:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=130.0, timestamp="2026-09-10T10:15:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=20, price=100.0, timestamp="2026-09-10T10:40:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=22, price=115.0, timestamp="2026-09-10T10:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=24, price=102.0, timestamp="2026-09-10T11:00:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )

    w_confirmed = [p for p in confirmed if p.pattern_type == "W"]
    assert len(w_confirmed) == 1, f"Expected exactly 1 confirmed W pattern, found {len(w_confirmed)}"
    assert w_confirmed[0].breakout_candle_time == "2026-09-10T11:05:00Z", "Breakout candle must be the first qualifying candle (11:05)"

    w_events = [e for e in events if e.pattern_type == "W"]
    assert len(w_events) == 1, f"Expected exactly 1 W break event, found {len(w_events)}"
    assert w_events[0].break_candle_index == 25, "Event must point to first breakout candle index 25"


# ============================================================================
# 2. SINGLE M BREAKDOWN: SUBSEQUENT CANDLES DO NOT CREATE EXTRA EVENTS
# ============================================================================
def test_2_m_breakdown_single_event_subsequent_candles_ignored():
    """Single structural M pattern breaks at T_0. Later candles closing below neckline must NOT emit extra events."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-09-10T09:{i*5:02d}:00Z", open=100 + i*4, high=102 + i*4, low=98 + i*4, close=101 + i*4, volume=1000)
        for i in range(20)
    ]
    extra_candles = [
        Candle(timestamp="2026-09-10T10:40:00Z", open=195, high=200.5, low=194, close=200.0, volume=1500), # 20: H1
        Candle(timestamp="2026-09-10T10:45:00Z", open=200, high=200, low=190, close=192.0, volume=1200),   # 21
        Candle(timestamp="2026-09-10T10:50:00Z", open=192, high=193, low=184.5, close=185.0, volume=1400), # 22: Neckline
        Candle(timestamp="2026-09-10T10:55:00Z", open=185, high=195, low=185, close=194.0, volume=1100),   # 23
        Candle(timestamp="2026-09-10T11:00:00Z", open=194, high=198.5, low=193, close=198.0, volume=1300), # 24: H2
        Candle(timestamp="2026-09-10T11:05:00Z", open=198, high=198, low=181, close=182.0, volume=2500),   # 25: First Breakdown
        Candle(timestamp="2026-09-10T11:10:00Z", open=182, high=183, low=177, close=178.0, volume=2200),   # 26: Subsequent
        Candle(timestamp="2026-09-10T11:15:00Z", open=178, high=179, low=174, close=175.0, volume=2000),   # 27: Subsequent
    ]
    candles.extend(extra_candles)

    swings = [
        SwingPoint(index=0, price=100.0, timestamp="2026-09-10T09:00:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=120.0, timestamp="2026-09-10T09:25:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=140.0, timestamp="2026-09-10T09:50:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=170.0, timestamp="2026-09-10T10:15:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=20, price=200.0, timestamp="2026-09-10T10:40:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=22, price=185.0, timestamp="2026-09-10T10:50:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=24, price=198.0, timestamp="2026-09-10T11:00:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="BANK NIFTY", timeframe="5M", atr_val=atr
    )

    m_confirmed = [p for p in confirmed if p.pattern_type == "M"]
    assert len(m_confirmed) == 1, f"Expected exactly 1 confirmed M pattern, found {len(m_confirmed)}"
    assert m_confirmed[0].breakout_candle_time == "2026-09-10T11:05:00Z", "Breakdown candle must be the first qualifying candle (11:05)"

    m_events = [e for e in events if e.pattern_type == "M"]
    assert len(m_events) == 1, f"Expected exactly 1 M break event, found {len(m_events)}"
    assert m_events[0].break_candle_index == 25, "Event must point to first breakdown candle index 25"


# ============================================================================
# 3. MULTI-PASS WORKER SIMULATION: INCREMENTAL CANDLE INGESTION
# ============================================================================
def test_3_multi_pass_worker_incremental_candles():
    """Worker passes across expanding candle windows must lock to the exact first breakout candle."""
    atr = 2.0
    base_candles = [
        Candle(timestamp=f"2026-09-10T09:{i*5:02d}:00Z", open=200 - i*4, high=202 - i*4, low=198 - i*4, close=199 - i*4, volume=1000)
        for i in range(20)
    ]
    swings = [
        SwingPoint(index=0, price=200.0, timestamp="2026-09-10T09:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=180.0, timestamp="2026-09-10T09:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=160.0, timestamp="2026-09-10T09:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=130.0, timestamp="2026-09-10T10:15:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=20, price=100.0, timestamp="2026-09-10T10:40:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=22, price=115.0, timestamp="2026-09-10T10:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=24, price=102.0, timestamp="2026-09-10T11:00:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
    ]
    extra_candles = [
        Candle(timestamp="2026-09-10T10:40:00Z", open=105, high=107, low=99.5, close=100.0, volume=1500), # 20: L1
        Candle(timestamp="2026-09-10T10:45:00Z", open=100, high=110, low=100, close=108.0, volume=1200),   # 21
        Candle(timestamp="2026-09-10T10:50:00Z", open=108, high=115.5, low=107, close=115.0, volume=1400), # 22: Neckline
        Candle(timestamp="2026-09-10T10:55:00Z", open=115, high=115, low=105, close=106.0, volume=1100),   # 23
        Candle(timestamp="2026-09-10T11:00:00Z", open=106, high=108, low=101.5, close=102.0, volume=1300), # 24: L2
        Candle(timestamp="2026-09-10T11:05:00Z", open=102, high=119, low=102, close=118.0, volume=2500),   # 25: First Breakout
        Candle(timestamp="2026-09-10T11:10:00Z", open=118, high=123, low=117, close=122.0, volume=2200),   # 26: Completed when 27 arrives
        Candle(timestamp="2026-09-10T11:15:00Z", open=122, high=126, low=121, close=125.0, volume=2000),   # 27: Completed when 28 arrives
        Candle(timestamp="2026-09-10T11:20:00Z", open=125, high=128, low=124, close=127.0, volume=1800),   # 28: Live candle
    ]

    # Pass 1: Candles up to index 26 (candle 25 completed, candle 26 forming)
    pass1_candles = base_candles + extra_candles[:7]
    _, conf1, _, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=pass1_candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )
    assert len(conf1) == 1
    assert conf1[0].breakout_candle_time == "2026-09-10T11:05:00Z"
    first_pat_id = conf1[0].pattern_id

    # Pass 2: Candles up to index 27 (candle 26 completed, candle 27 forming)
    pass2_candles = base_candles + extra_candles[:8]
    _, conf2, _, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=pass2_candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )
    assert len(conf2) == 1
    assert conf2[0].pattern_id == first_pat_id
    assert conf2[0].breakout_candle_time == "2026-09-10T11:05:00Z", "Pass 2 must not shift breakout candle to 11:10"

    # Pass 3: Candles up to index 28 (candle 27 completed, candle 28 forming)
    pass3_candles = base_candles + extra_candles
    _, conf3, _, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=pass3_candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )
    assert len(conf3) == 1
    assert conf3[0].pattern_id == first_pat_id
    assert conf3[0].breakout_candle_time == "2026-09-10T11:05:00Z", "Pass 3 must not shift breakout candle to 11:15"


# ============================================================================
# 4. DATABASE PERSISTENCE DEDUPLICATION (SQLITE TEST)
# ============================================================================
def test_4_database_persistence_deduplication(tmp_path, monkeypatch):
    """Database persistence must return SKIPPED when attempting to persist the same structural pattern."""
    db_path = tmp_path / "test_dedupe.db"
    create_test_db(db_path)
    monkeypatch.setattr("app.alerts.mw_breakout_engine.get_database_path", lambda: db_path)

    engine = MWBreakoutAlertEngine()
    alert1 = make_test_alert(symbol="TEST", breakout_time="2026-09-10T11:05:00Z", breakout_close=118.0)

    # First insert -> INSERTED
    res1 = engine._persist_alert_to_db_sync(alert1)
    assert res1 == "INSERTED"

    # Attempt second insert for the same structural pattern with subsequent timestamp 11:10
    alert2 = alert1.model_copy(update={
        "breakout_candle_timestamp": "2026-09-10T11:10:00Z",
        "breakout_close": 122.0
    })
    res2 = engine._persist_alert_to_db_sync(alert2)
    assert res2 == "SKIPPED", f"Expected SKIPPED for subsequent candle of same pattern, got {res2}"

    # Verify exactly 1 record in SQLite
    with sqlite3.connect(str(db_path)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM mw_breakout_alerts").fetchone()[0]
        assert count == 1


# ============================================================================
# 5. DISTINCT PATTERNS NOT DEDUPLICATED
# ============================================================================
def test_5_distinct_patterns_permitted(tmp_path, monkeypatch):
    """Different structural patterns on same or different symbols must be inserted independently."""
    db_path = tmp_path / "test_distinct.db"
    create_test_db(db_path)
    monkeypatch.setattr("app.alerts.mw_breakout_engine.get_database_path", lambda: db_path)

    engine = MWBreakoutAlertEngine()

    alert_w = make_test_alert(symbol="TEST", pattern_type="W", s1_time="2026-09-10T10:40:00Z", neckline_time="2026-09-10T10:50:00Z")
    alert_m = make_test_alert(symbol="TEST", pattern_type="M", s1_time="2026-09-10T13:40:00Z", neckline_time="2026-09-10T13:50:00Z")

    res_w = engine._persist_alert_to_db_sync(alert_w)
    res_m = engine._persist_alert_to_db_sync(alert_m)

    assert res_w == "INSERTED"
    assert res_m == "INSERTED"

    with sqlite3.connect(str(db_path)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM mw_breakout_alerts").fetchone()[0]
        assert count == 2


# ============================================================================
# 6. DIFFERENT ANCHORS NOT DEDUPLICATED
# ============================================================================
def test_6_different_anchors_not_deduplicated(tmp_path, monkeypatch):
    """Two W patterns with different S1/neckline anchor timestamps on different days/sessions are both preserved."""
    db_path = tmp_path / "test_anchors.db"
    create_test_db(db_path)
    monkeypatch.setattr("app.alerts.mw_breakout_engine.get_database_path", lambda: db_path)

    engine = MWBreakoutAlertEngine()

    alert_day1 = make_test_alert(symbol="TEST", s1_time="2026-09-08T10:00:00Z", neckline_time="2026-09-08T11:00:00Z", breakout_time="2026-09-08T12:00:00Z")
    alert_day2 = make_test_alert(symbol="TEST", s1_time="2026-09-09T10:00:00Z", neckline_time="2026-09-09T11:00:00Z", breakout_time="2026-09-09T12:00:00Z")

    res1 = engine._persist_alert_to_db_sync(alert_day1)
    res2 = engine._persist_alert_to_db_sync(alert_day2)

    assert res1 == "INSERTED"
    assert res2 == "INSERTED"

    with sqlite3.connect(str(db_path)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM mw_breakout_alerts").fetchone()[0]
        assert count == 2


# ============================================================================
# 7. FIRST QUALIFYING CANDLE WINS
# ============================================================================
def test_7_earliest_breakout_candle_preserved():
    """Earliest qualifying breakout candle index must be selected permanently."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-09-10T09:{i*5:02d}:00Z", open=200 - i*4, high=202 - i*4, low=198 - i*4, close=199 - i*4, volume=1000)
        for i in range(20)
    ]
    extra_candles = [
        Candle(timestamp="2026-09-10T10:40:00Z", open=105, high=107, low=99.5, close=100.0, volume=1500), # 20: L1
        Candle(timestamp="2026-09-10T10:45:00Z", open=100, high=110, low=100, close=108.0, volume=1200),   # 21
        Candle(timestamp="2026-09-10T10:50:00Z", open=108, high=115.5, low=107, close=115.0, volume=1400), # 22: Neckline
        Candle(timestamp="2026-09-10T10:55:00Z", open=115, high=115, low=105, close=106.0, volume=1100),   # 23
        Candle(timestamp="2026-09-10T11:00:00Z", open=106, high=108, low=101.5, close=102.0, volume=1300), # 24: L2
        Candle(timestamp="2026-09-10T11:05:00Z", open=102, high=116, low=102, close=115.5, volume=1800),   # 25: First Breakout Close (modest)
        Candle(timestamp="2026-09-10T11:10:00Z", open=115.5, high=125, low=115, close=124.0, volume=5000), # 26: Explosive candle
        Candle(timestamp="2026-09-10T11:15:00Z", open=124, high=126, low=123, close=125.0, volume=2000),   # 27: Forming/live candle
    ]
    candles.extend(extra_candles)

    swings = [
        SwingPoint(index=0, price=200.0, timestamp="2026-09-10T09:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=180.0, timestamp="2026-09-10T09:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=160.0, timestamp="2026-09-10T09:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=130.0, timestamp="2026-09-10T10:15:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=20, price=100.0, timestamp="2026-09-10T10:40:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=22, price=115.0, timestamp="2026-09-10T10:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=24, price=102.0, timestamp="2026-09-10T11:00:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
    ]

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )

    assert len(confirmed) == 1
    # Even though candle 26 has volume 5000 and close 124, candle 25 is the FIRST breakout candle
    assert confirmed[0].breakout_candle_time == "2026-09-10T11:05:00Z"
    assert confirmed[0].breakout_candle_index == 25


# ============================================================================
# 8. UNCLOSED / IN-PROGRESS CANDLES BLOCKED
# ============================================================================
def test_8_unclosed_wick_only_not_breakout():
    """Wick piercing above neckline but candle closing below neckline does NOT trigger a breakout."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-09-10T09:{i*5:02d}:00Z", open=200 - i*4, high=202 - i*4, low=198 - i*4, close=199 - i*4, volume=1000)
        for i in range(20)
    ]
    extra_candles = [
        Candle(timestamp="2026-09-10T10:40:00Z", open=105, high=107, low=99.5, close=100.0, volume=1500), # 20: L1
        Candle(timestamp="2026-09-10T10:45:00Z", open=100, high=110, low=100, close=108.0, volume=1200),   # 21
        Candle(timestamp="2026-09-10T10:50:00Z", open=108, high=115.5, low=107, close=115.0, volume=1400), # 22: Neckline at 115
        Candle(timestamp="2026-09-10T10:55:00Z", open=115, high=115, low=105, close=106.0, volume=1100),   # 23
        Candle(timestamp="2026-09-10T11:00:00Z", open=106, high=108, low=101.5, close=102.0, volume=1300), # 24: L2
        Candle(timestamp="2026-09-10T11:05:00Z", open=102, high=118, low=102, close=114.5, volume=2500),   # 25: False break (wick only)
        Candle(timestamp="2026-09-10T11:10:00Z", open=114.5, high=115, low=113, close=113.5, volume=1000), # 26: Forming
    ]
    candles.extend(extra_candles)

    swings = [
        SwingPoint(index=0, price=200.0, timestamp="2026-09-10T09:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=180.0, timestamp="2026-09-10T09:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=160.0, timestamp="2026-09-10T09:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=130.0, timestamp="2026-09-10T10:15:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=20, price=100.0, timestamp="2026-09-10T10:40:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=22, price=115.0, timestamp="2026-09-10T10:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=24, price=102.0, timestamp="2026-09-10T11:00:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
    ]

    events, confirmed, active, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )

    w_conf = [p for p in confirmed if p.pattern_type == "W"]
    assert len(w_conf) == 0, "Candle closing below neckline must NOT confirm a breakout"


# ============================================================================
# 9. REVERSAL VALIDATION INTACT (CONTINUATIONS REJECTED)
# ============================================================================
def test_9_reversal_context_validation():
    """W pattern without a prior downtrend (bull continuation) must be rejected."""
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
        SwingPoint(index=20, price=132.0, timestamp="2026-08-25T11:40:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
        SwingPoint(index=23, price=138.0, timestamp="2026-08-25T11:55:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=27, price=133.0, timestamp="2026-08-25T12:15:00Z", is_high=False, type="HL", strength=2.0, confirmed=True)
    ]

    events, confirmed, active, debug_cands = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="RELIANCE", timeframe="15M", atr_val=atr
    )

    assert len(confirmed) == 0, "Bull-market pullback W continuation must be rejected"


# ============================================================================
# 10. TARGET & SL MATH INTACT
# ============================================================================
def test_10_target_sl_mathematics():
    """Target 1, Target 2 (1.618x), and Invalidation Level math remains exact."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-09-10T09:{i*5:02d}:00Z", open=200 - i*4, high=202 - i*4, low=198 - i*4, close=199 - i*4, volume=1000)
        for i in range(20)
    ]
    extra_candles = [
        Candle(timestamp="2026-09-10T10:40:00Z", open=105, high=107, low=99.5, close=100.0, volume=1500), # 20: L1 = 100.0
        Candle(timestamp="2026-09-10T10:45:00Z", open=100, high=110, low=100, close=108.0, volume=1200),   # 21
        Candle(timestamp="2026-09-10T10:50:00Z", open=108, high=115.0, low=107, close=115.0, volume=1400), # 22: Neckline = 115.0
        Candle(timestamp="2026-09-10T10:55:00Z", open=115, high=115, low=105, close=106.0, volume=1100),   # 23
        Candle(timestamp="2026-09-10T11:00:00Z", open=106, high=108, low=102.0, close=102.0, volume=1300), # 24: L2 = 102.0
        Candle(timestamp="2026-09-10T11:05:00Z", open=102, high=119, low=102, close=118.0, volume=2500),   # 25: Breakout
        Candle(timestamp="2026-09-10T11:10:00Z", open=118, high=120, low=117, close=119.0, volume=1500),   # 26: Forming
    ]
    candles.extend(extra_candles)

    swings = [
        SwingPoint(index=0, price=200.0, timestamp="2026-09-10T09:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=180.0, timestamp="2026-09-10T09:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=160.0, timestamp="2026-09-10T09:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=130.0, timestamp="2026-09-10T10:15:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=20, price=100.0, timestamp="2026-09-10T10:40:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=22, price=115.0, timestamp="2026-09-10T10:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=24, price=102.0, timestamp="2026-09-10T11:00:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
    ]

    _, confirmed, _, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )

    assert len(confirmed) == 1
    pat = confirmed[0]
    expected_height = 115.0 - 100.0       # 15.0
    expected_t1 = 200.0                    # Structural Reversal Origin (prior swing high)
    expected_t2 = 115.0 + (15.0 * 1.618)  # 139.27
    expected_inval = 102.0 - (0.15 * 2.0) # 101.7 (S2 low - buffer_atr * atr)

    assert abs(pat.pattern_height - expected_height) < 1e-2
    assert pat.target_analysis is not None
    assert abs(pat.target_analysis.measured_target - expected_t1) < 1e-2
    assert abs(pat.target_analysis.target_2 - expected_t2) < 1e-2
    assert abs(pat.target_analysis.invalidation_level - expected_inval) < 1e-2


# ============================================================================
# 11. CANONICAL 700 RECORDS PRESERVED
# ============================================================================
def test_11_canonical_700_records_intact():
    """Verify that the production SQLite database contains exactly 700 canonical records untouched."""
    db_path = Path("backend/data/market_analyzer.db")
    if not db_path.exists():
        pytest.skip("Production database file not found")

    with sqlite3.connect(str(db_path)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM mw_breakout_alerts").fetchone()[0]
        assert count == 700, f"Canonical records count must remain exactly 700, found {count}"


# ============================================================================
# 12. MULTI-INSTRUMENT AND MULTI-TIMEFRAME SUPPORT
# ============================================================================
def test_12_multi_symbol_timeframe_isolation():
    """Verify that deduplication respects exact (symbol, timeframe) boundaries."""
    atr = 2.0
    candles = [
        Candle(timestamp=f"2026-09-10T09:{i*5:02d}:00Z", open=200 - i*4, high=202 - i*4, low=198 - i*4, close=199 - i*4, volume=1000)
        for i in range(20)
    ]
    extra_candles = [
        Candle(timestamp="2026-09-10T10:40:00Z", open=105, high=107, low=99.5, close=100.0, volume=1500),
        Candle(timestamp="2026-09-10T10:45:00Z", open=100, high=110, low=100, close=108.0, volume=1200),
        Candle(timestamp="2026-09-10T10:50:00Z", open=108, high=115.5, low=107, close=115.0, volume=1400),
        Candle(timestamp="2026-09-10T10:55:00Z", open=115, high=115, low=105, close=106.0, volume=1100),
        Candle(timestamp="2026-09-10T11:00:00Z", open=106, high=108, low=101.5, close=102.0, volume=1300),
        Candle(timestamp="2026-09-10T11:05:00Z", open=102, high=119, low=102, close=118.0, volume=2500),
        Candle(timestamp="2026-09-10T11:10:00Z", open=118, high=120, low=117, close=119.0, volume=1500), # Forming candle
    ]
    candles.extend(extra_candles)
    swings = [
        SwingPoint(index=0, price=200.0, timestamp="2026-09-10T09:00:00Z", is_high=True, type="HH", strength=2.0, confirmed=True),
        SwingPoint(index=5, price=180.0, timestamp="2026-09-10T09:25:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=10, price=160.0, timestamp="2026-09-10T09:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=15, price=130.0, timestamp="2026-09-10T10:15:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=20, price=100.0, timestamp="2026-09-10T10:40:00Z", is_high=False, type="LL", strength=2.0, confirmed=True),
        SwingPoint(index=22, price=115.0, timestamp="2026-09-10T10:50:00Z", is_high=True, type="LH", strength=2.0, confirmed=True),
        SwingPoint(index=24, price=102.0, timestamp="2026-09-10T11:00:00Z", is_high=False, type="HL", strength=2.0, confirmed=True),
    ]

    _, conf_nifty, _, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="NIFTY 50", timeframe="5M", atr_val=atr
    )
    _, conf_bank, _, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles, swings=swings, trendlines=[], df_indicators=None,
        symbol="BANK NIFTY", timeframe="5M", atr_val=atr
    )

    assert len(conf_nifty) == 1
    assert len(conf_bank) == 1
    assert conf_nifty[0].symbol == "NIFTY 50"
    assert conf_bank[0].symbol == "BANK NIFTY"


# ============================================================================
# 13. CONCURRENCY PROTECTION: SIMULTANEOUS INSERTS
# ============================================================================
def test_13_concurrency_protection(tmp_path, monkeypatch):
    """Simultaneous insertion attempts for the same structural alert are serialized safely."""
    db_path = tmp_path / "test_concurrency.db"
    create_test_db(db_path)
    monkeypatch.setattr("app.alerts.mw_breakout_engine.get_database_path", lambda: db_path)

    engine = MWBreakoutAlertEngine()
    alert = make_test_alert(symbol="CONCUR")

    results = []

    def insert_worker():
        res = engine._persist_alert_to_db_sync(alert)
        results.append(res)

    threads = [threading.Thread(target=insert_worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("INSERTED") == 1, f"Expected exactly 1 INSERTED, got {results}"
    assert results.count("SKIPPED") == 4, f"Expected 4 SKIPPED, got {results}"

    with sqlite3.connect(str(db_path)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM mw_breakout_alerts WHERE symbol = 'CONCUR'").fetchone()[0]
        assert count == 1


# ============================================================================
# 14. ZERO TRADING OR ORDER CODE IN CODEBASE
# ============================================================================
def test_14_zero_trading_or_order_execution():
    """Verify that no order execution, broker integration, or trade routing exists."""
    forbidden_terms = [
        "place_order", "create_order", "submit_order",
        "buy_market", "sell_market", "zerodha_client", "broker_session"
    ]
    repo_root = Path(__file__).resolve().parent.parent
    py_files = list(repo_root.glob("app/**/*.py"))
    for f in py_files:
        content = f.read_text(encoding="utf-8", errors="ignore")
        for term in forbidden_terms:
            assert term not in content, f"Forbidden trading term '{term}' found in {f}"
