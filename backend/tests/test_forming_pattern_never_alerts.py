import pytest
from app.models.schemas import Candle, WMPatternStructure, PatternTargetAnalysis
from app.alerts.mw_breakout_engine import MWBreakoutAlertEngine


@pytest.fixture
def fresh_engine(tmp_path, monkeypatch):
    """Provides a fresh isolated MWBreakoutAlertEngine for each test."""
    temp_store = tmp_path / "test_store.json"
    temp_db = tmp_path / "test_alerts.db"
    monkeypatch.setattr("app.alerts.mw_breakout_engine.STORAGE_FILE", temp_store)
    monkeypatch.setattr("app.alerts.mw_breakout_engine.get_database_path", lambda: temp_db)
    
    # Initialize schema in temp DB
    from app.db.database import get_sync_sqlite_connection
    with get_sync_sqlite_connection(temp_db) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_breakout_alerts (
                alert_id TEXT PRIMARY KEY,
                alert_type TEXT NOT NULL,
                pattern_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                symbol TEXT NOT NULL,
                ticker TEXT,
                timeframe TEXT NOT NULL,
                pattern_id TEXT NOT NULL,
                s1_price REAL NOT NULL,
                s1_timestamp TEXT NOT NULL,
                s2_price REAL NOT NULL,
                s2_timestamp TEXT NOT NULL,
                neckline_price REAL NOT NULL,
                neckline_timestamp TEXT NOT NULL,
                pattern_height REAL NOT NULL,
                breakout_candle_timestamp TEXT NOT NULL,
                breakout_open REAL NOT NULL,
                breakout_high REAL NOT NULL,
                breakout_low REAL NOT NULL,
                breakout_close REAL NOT NULL,
                trendline_price REAL NOT NULL,
                ema20_price REAL NOT NULL,
                volume REAL DEFAULT 0.0,
                relative_volume REAL DEFAULT 1.0,
                measured_target REAL NOT NULL,
                target_2 REAL,
                nearest_support REAL,
                nearest_resistance REAL,
                invalidation_level REAL NOT NULL,
                quality_score INTEGER NOT NULL,
                quality_breakdown TEXT DEFAULT '{}',
                reversal_score INTEGER DEFAULT 40,
                trendline_score INTEGER DEFAULT 0,
                ema_score INTEGER DEFAULT 0,
                reversal_points INTEGER DEFAULT 40,
                trendline_points INTEGER DEFAULT 0,
                ema_points INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                trade_quality TEXT DEFAULT 'MEDIUM',
                entry_status TEXT DEFAULT 'VALID',
                outcome_timestamp TEXT,
                stop_loss REAL,
                event_created_at TEXT NOT NULL,
                read INTEGER DEFAULT 0
            )
        """)
        conn.commit()

    engine = MWBreakoutAlertEngine()
    engine.alerts = []
    engine.seen_event_keys = set()
    return engine


def test_01_forming_w_without_breakout_never_creates_alert(fresh_engine):
    """1. FORMING W with breakout_candle_time=None -> MUST NOT create alert."""
    engine = fresh_engine
    pat = WMPatternStructure(
        pattern_id="SBIN_1H_W_2026-09-18T09:15:00Z_2026-09-22T13:15:00Z",
        pattern_type="W",
        status="FORMING",
        s1_index=5, s1_price=985.4, s1_time="2026-09-18T09:15:00Z",
        neckline_index=10, neckline_price=999.2, neckline_time="2026-09-22T09:15:00Z",
        s2_index=15, s2_price=981.3, s2_time="2026-09-22T13:15:00Z",
        pattern_height=17.9, depth_atr=1.5, symmetry_atr=0.2, bar_separation=5, quality_score=40,
        breakout_candle_index=None,
        breakout_candle_time=None,
        breakout_close=None,
        target_analysis=PatternTargetAnalysis(
            pattern_height=17.9, measured_target=1060.0, target_2=1028.16,
            invalidation_level=980.68, retest_level=999.2, retest_status="PENDING",
            pattern_status="FORMING", pattern_quality_score=40, quality_breakdown={}, interpretation=""
        )
    )
    candles = [Candle(timestamp=f"2026-09-22T{10+i}:00:00Z", open=985, high=990, low=980, close=987.6, volume=100) for i in range(16)]

    result = engine.sync_chart_patterns("SBIN", "1H", [pat], pat, candles)
    assert result is None, "Sync must return None for forming pattern without breakout"
    assert len(engine.alerts) == 0, "No alert must be created for forming W pattern"
    assert len(engine.seen_event_keys) == 0, "No event keys must be recorded"


def test_02_forming_m_without_breakout_never_creates_alert(fresh_engine):
    """2. FORMING M with breakout_candle_time=None -> MUST NOT create alert."""
    engine = fresh_engine
    pat = WMPatternStructure(
        pattern_id="NIFTY_5M_M_2026-09-24T11:20:00Z_2026-09-24T12:05:00Z",
        pattern_type="M",
        status="FORMING",
        s1_index=5, s1_price=23244.7, s1_time="2026-09-24T11:20:00Z",
        neckline_index=10, neckline_price=23190.4, neckline_time="2026-09-24T11:55:00Z",
        s2_index=15, s2_price=23212.95, s2_time="2026-09-24T12:05:00Z",
        pattern_height=54.3, depth_atr=1.5, symmetry_atr=0.2, bar_separation=5, quality_score=40,
        breakout_candle_index=None,
        breakout_candle_time=None,
        breakout_close=None,
        target_analysis=PatternTargetAnalysis(
            pattern_height=54.3, measured_target=23136.1, target_2=23102.54,
            invalidation_level=23215.31, retest_level=23190.4, retest_status="PENDING",
            pattern_status="FORMING", pattern_quality_score=40, quality_breakdown={}, interpretation=""
        )
    )
    candles = [Candle(timestamp=f"2026-09-24T12:{i*5:02d}:00Z", open=23200, high=23220, low=23195, close=23205, volume=100) for i in range(16)]

    result = engine.sync_chart_patterns("NIFTY 50", "5M", [pat], pat, candles)
    assert result is None, "Sync must return None for forming pattern without breakdown"
    assert len(engine.alerts) == 0, "No alert must be created for forming M pattern"


def test_03_w_where_s2_candle_close_below_neckline_never_creates_alert(fresh_engine):
    """3. W where S2 candle exists but close is below neckline -> MUST NOT create alert."""
    engine = fresh_engine
    pat = WMPatternStructure(
        pattern_id="SBIN_1H_W_2026-09-18T09:15:00Z_2026-09-22T13:15:00Z",
        pattern_type="W",
        status="CONFIRMED",
        s1_index=5, s1_price=985.4, s1_time="2026-09-18T09:15:00Z",
        neckline_index=10, neckline_price=999.2, neckline_time="2026-09-22T09:15:00Z",
        s2_index=15, s2_price=981.3, s2_time="2026-09-22T13:15:00Z",
        pattern_height=17.9, depth_atr=1.5, symmetry_atr=0.2, bar_separation=5, quality_score=40,
        breakout_candle_index=15,
        breakout_candle_time="2026-09-22T13:15:00Z",  # S2 candle timestamp
        breakout_close=987.6,  # Close is below neckline 999.2!
        target_analysis=PatternTargetAnalysis(
            pattern_height=17.9, measured_target=1060.0, target_2=1028.16,
            invalidation_level=980.68, retest_level=999.2, retest_status="PENDING",
            pattern_status="CONFIRMED", pattern_quality_score=40, quality_breakdown={}, interpretation=""
        )
    )
    candles = [Candle(timestamp=f"2026-09-22T{10+i}:00:00Z", open=985, high=990, low=980, close=987.6, volume=100) for i in range(16)]

    result = engine.sync_chart_patterns("SBIN", "1H", [pat], pat, candles)
    assert result is None, "Must not create alert when close is below neckline"
    assert len(engine.alerts) == 0, "Engine alerts must remain empty"


def test_04_m_where_s2_candle_close_above_neckline_never_creates_alert(fresh_engine):
    """4. M where S2 candle exists but close is above neckline -> MUST NOT create alert."""
    engine = fresh_engine
    pat = WMPatternStructure(
        pattern_id="ICICIBANK_15M_M_2026-09-17T09:30:00Z_2026-09-17T12:30:00Z",
        pattern_type="M",
        status="CONFIRMED",
        s1_index=5, s1_price=1363.0, s1_time="2026-09-17T09:30:00Z",
        neckline_index=10, neckline_price=1350.0, neckline_time="2026-09-17T11:00:00Z",
        s2_index=15, s2_price=1358.9, s2_time="2026-09-17T12:30:00Z",
        pattern_height=13.0, depth_atr=1.5, symmetry_atr=0.2, bar_separation=5, quality_score=40,
        breakout_candle_index=15,
        breakout_candle_time="2026-09-17T12:30:00Z",  # S2 candle timestamp
        breakout_close=1355.0,  # Close is above neckline 1350.0!
        target_analysis=PatternTargetAnalysis(
            pattern_height=13.0, measured_target=1337.0, target_2=1328.97,
            invalidation_level=1359.71, retest_level=1350.0, retest_status="PENDING",
            pattern_status="CONFIRMED", pattern_quality_score=40, quality_breakdown={}, interpretation=""
        )
    )
    candles = [Candle(timestamp=f"2026-09-17T{10+i}:00:00Z", open=1356, high=1360, low=1352, close=1355.0, volume=100) for i in range(16)]

    result = engine.sync_chart_patterns("ICICIBANK", "15M", [pat], pat, candles)
    assert result is None, "Must not create alert when M candle close is above neckline"
    assert len(engine.alerts) == 0


def test_05_w_later_completed_candle_closes_above_neckline_creates_alert(fresh_engine):
    """5. W where a later completed candle closes above neckline -> MUST create exactly one valid alert."""
    engine = fresh_engine
    t_s1 = "2026-09-24T10:00:00Z"
    t_neck = "2026-09-24T10:30:00Z"
    t_s2 = "2026-09-24T11:00:00Z"
    t_breakout = "2026-09-24T11:30:00Z"

    pat = WMPatternStructure(
        pattern_id="INFY_5M_W_2026-09-24T10:00:00Z_2026-09-24T11:00:00Z",
        pattern_type="W",
        status="BREAKOUT_CONFIRMED",
        s1_index=5, s1_price=1010.0, s1_time=t_s1,
        neckline_index=10, neckline_price=1015.0, neckline_time=t_neck,
        s2_index=15, s2_price=1011.0, s2_time=t_s2,
        pattern_height=5.0, depth_atr=1.5, symmetry_atr=0.2, bar_separation=5, quality_score=75,
        breakout_candle_index=18,
        breakout_candle_time=t_breakout,
        breakout_close=1017.5,  # 1017.5 > neckline 1015.0!
        target_analysis=PatternTargetAnalysis(
            pattern_height=5.0, measured_target=1020.0, target_2=1023.09,
            invalidation_level=1010.5, retest_level=1015.0, retest_status="PENDING",
            pattern_status="CONFIRMED_BREAKOUT", pattern_quality_score=75, quality_breakdown={}, interpretation=""
        )
    )
    candles = [
        Candle(timestamp=f"2026-09-24T10:{i*5:02d}:00Z", open=1012, high=1016, low=1009, close=1012, volume=100)
        for i in range(18)
    ]
    candles.append(Candle(timestamp=t_breakout, open=1014.0, high=1018.0, low=1013.5, close=1017.5, volume=250))

    result = engine.sync_chart_patterns("INFY", "5M", [pat], pat, candles)
    assert result is not None, "Genuine breakout must return valid alert"
    assert len(engine.alerts) == 1, "Exactly one alert must be created"
    alert = engine.alerts[0]
    assert alert.pattern_type == "W"
    assert alert.symbol == "INFY"
    assert alert.breakout_candle_timestamp == t_breakout
    assert alert.breakout_close == 1017.5
    assert alert.breakout_close > alert.neckline_price
    assert alert.status == "TARGET OPEN"


def test_06_m_later_completed_candle_closes_below_neckline_creates_alert(fresh_engine):
    """6. M where a later completed candle closes below neckline -> MUST create exactly one valid alert."""
    engine = fresh_engine
    t_s1 = "2026-09-24T11:20:00Z"
    t_neck = "2026-09-24T11:55:00Z"
    t_s2 = "2026-09-24T12:05:00Z"
    t_breakdown = "2026-09-24T12:30:00Z"

    pat = WMPatternStructure(
        pattern_id="NIFTY_5M_M_2026-09-24T11:20:00Z_2026-09-24T12:05:00Z",
        pattern_type="M",
        status="BREAKOUT_CONFIRMED",
        s1_index=5, s1_price=23244.7, s1_time=t_s1,
        neckline_index=10, neckline_price=23190.4, neckline_time=t_neck,
        s2_index=15, s2_price=23212.95, s2_time=t_s2,
        pattern_height=54.3, depth_atr=1.5, symmetry_atr=0.2, bar_separation=5, quality_score=85,
        breakout_candle_index=18,
        breakout_candle_time=t_breakdown,
        breakout_close=23175.45,  # 23175.45 < neckline 23190.4!
        target_analysis=PatternTargetAnalysis(
            pattern_height=54.3, measured_target=23136.1, target_2=23102.54,
            invalidation_level=23215.31, retest_level=23190.4, retest_status="PENDING",
            pattern_status="CONFIRMED_BREAKOUT", pattern_quality_score=85, quality_breakdown={}, interpretation=""
        )
    )
    candles = [
        Candle(timestamp=f"2026-09-24T11:{20+i*3:02d}:00Z", open=23200, high=23250, low=23190, close=23200, volume=100)
        for i in range(18)
    ]
    candles.append(Candle(timestamp=t_breakdown, open=23187.95, high=23192.2, low=23173.1, close=23175.45, volume=300))

    result = engine.sync_chart_patterns("NIFTY 50", "5M", [pat], pat, candles)
    assert result is not None, "Genuine breakdown must return valid alert"
    assert len(engine.alerts) == 1, "Exactly one alert must be created"
    alert = engine.alerts[0]
    assert alert.pattern_type == "M"
    assert alert.symbol == "NIFTY 50"
    assert alert.breakout_candle_timestamp == t_breakdown
    assert alert.breakout_close == 23175.45
    assert alert.breakout_close < alert.neckline_price


def test_07_verify_s2_timestamp_never_used_as_breakout_candle_timestamp(fresh_engine):
    """7. Verify S2 timestamp is NEVER used as breakout_candle_timestamp."""
    engine = fresh_engine
    t_s2 = "2026-09-22T13:15:00Z"
    pat = WMPatternStructure(
        pattern_id="SBIN_1H_W_2026-09-18T09:15:00Z_2026-09-22T13:15:00Z",
        pattern_type="W",
        status="CONFIRMED",
        s1_index=5, s1_price=985.4, s1_time="2026-09-18T09:15:00Z",
        neckline_index=10, neckline_price=999.2, neckline_time="2026-09-22T09:15:00Z",
        s2_index=15, s2_price=981.3, s2_time=t_s2,
        pattern_height=17.9, depth_atr=1.5, symmetry_atr=0.2, bar_separation=5, quality_score=40,
        breakout_candle_index=15,
        breakout_candle_time=t_s2,  # Exactly S2 timestamp
        breakout_close=1005.0,  # Even if close claimed to be high
        target_analysis=PatternTargetAnalysis(
            pattern_height=17.9, measured_target=1060.0, target_2=1028.16,
            invalidation_level=980.68, retest_level=999.2, retest_status="PENDING",
            pattern_status="CONFIRMED", pattern_quality_score=40, quality_breakdown={}, interpretation=""
        )
    )
    candles = [Candle(timestamp=f"2026-09-22T{10+i}:00:00Z", open=985, high=1005, low=980, close=1005.0, volume=100) for i in range(16)]

    result = engine.sync_chart_patterns("SBIN", "1H", [pat], pat, candles)
    assert result is None, "Must never accept S2 timestamp as breakout timestamp"
    assert len(engine.alerts) == 0, "Zero alerts must be created"


def test_08_verify_candle_close_taken_from_actual_breakout_candle_not_latest(fresh_engine):
    """8. Verify candle close is taken from actual breakout candle, not candles[-1] merely because it is latest."""
    engine = fresh_engine
    t_breakout = "2026-09-24T11:00:00Z"
    t_latest = "2026-09-24T12:00:00Z"

    pat = WMPatternStructure(
        pattern_id="RELIANCE_15M_W_2026-09-24T10:00:00Z_2026-09-24T10:45:00Z",
        pattern_type="W",
        status="BREAKOUT_CONFIRMED",
        s1_index=2, s1_price=1240.0, s1_time="2026-09-24T10:00:00Z",
        neckline_index=5, neckline_price=1250.0, neckline_time="2026-09-24T10:30:00Z",
        s2_index=8, s2_price=1242.0, s2_time="2026-09-24T10:45:00Z",
        pattern_height=10.0, depth_atr=1.5, symmetry_atr=0.2, bar_separation=3, quality_score=80,
        breakout_candle_index=10,  # Breakout happened at index 10
        breakout_candle_time=t_breakout,
        breakout_close=1253.5,  # Actual breakout candle closed at 1253.5
        target_analysis=PatternTargetAnalysis(
            pattern_height=10.0, measured_target=1260.0, target_2=1266.18,
            invalidation_level=1241.0, retest_level=1250.0, retest_status="PENDING",
            pattern_status="CONFIRMED_BREAKOUT", pattern_quality_score=80, quality_breakdown={}, interpretation=""
        )
    )
    candles = [
        Candle(timestamp=f"2026-09-24T10:{i*5:02d}:00Z", open=1245, high=1249, low=1241, close=1245, volume=100)
        for i in range(10)
    ]
    # Index 10: Actual breakout candle (close 1253.5)
    candles.append(Candle(timestamp=t_breakout, open=1249.0, high=1255.0, low=1248.0, close=1253.5, volume=200))
    # Index 11-15: Subsequent candles running higher, candles[-1] close is 1290.0
    for i in range(1, 5):
        candles.append(Candle(timestamp=f"2026-09-24T11:{i*15:02d}:00Z", open=1255+i*5, high=1265+i*5, low=1254+i*5, close=1260+i*5, volume=100))
    candles.append(Candle(timestamp=t_latest, open=1285.0, high=1295.0, low=1280.0, close=1290.0, volume=300))

    result = engine.sync_chart_patterns("RELIANCE", "15M", [pat], pat, candles)
    assert result is not None
    assert len(engine.alerts) == 1
    alert = engine.alerts[0]
    # CRITICAL: breakout_close must match breakout candle (1253.5), NOT candles[-1] (1290.0)
    assert alert.breakout_close == 1253.5, f"Expected 1253.5 from breakout candle, got {alert.breakout_close}"
    assert alert.breakout_candle_timestamp == t_breakout


def test_09_repeated_sync_calls_while_forming_zero_alerts(fresh_engine):
    """9. Repeated sync calls while pattern remains FORMING -> zero alerts."""
    engine = fresh_engine
    pat = WMPatternStructure(
        pattern_id="SBIN_5M_W_2026-09-24T09:45:00Z_2026-09-24T10:25:00Z",
        pattern_type="W",
        status="FORMING",
        s1_index=5, s1_price=984.2, s1_time="2026-09-24T09:45:00Z",
        neckline_index=10, neckline_price=986.8, neckline_time="2026-09-24T10:10:00Z",
        s2_index=15, s2_price=985.3, s2_time="2026-09-24T10:25:00Z",
        pattern_height=2.6, depth_atr=1.5, symmetry_atr=0.2, bar_separation=5, quality_score=40,
        breakout_candle_index=None,
        breakout_candle_time=None,
        breakout_close=None,
        target_analysis=PatternTargetAnalysis(
            pattern_height=2.6, measured_target=993.4, target_2=991.01,
            invalidation_level=985.11, retest_level=986.8, retest_status="PENDING",
            pattern_status="FORMING", pattern_quality_score=40, quality_breakdown={}, interpretation=""
        )
    )

    candles = [Candle(timestamp=f"2026-09-24T10:{i*5:02d}:00Z", open=985, high=986, low=984, close=985.5, volume=100) for i in range(16)]

    # Call sync 10 times in a row as new candles arrive
    for step in range(10):
        candles.append(Candle(timestamp=f"2026-09-24T11:{step*5:02d}:00Z", open=985, high=986.5, low=984.8, close=985.8, volume=100))
        res = engine.sync_chart_patterns("SBIN", "5M", [pat], pat, candles)
        assert res is None, f"Sync step {step} returned an alert for forming pattern"
        assert len(engine.alerts) == 0, f"Sync step {step} created alerts: {len(engine.alerts)}"


def test_10_repeated_sync_calls_after_genuine_breakout_exactly_one_alert(fresh_engine):
    """10. Repeated sync calls after genuine breakout -> exactly one structural alert."""
    engine = fresh_engine
    t_breakout = "2026-09-24T10:45:00Z"
    pat = WMPatternStructure(
        pattern_id="SBIN_5M_W_2026-09-24T09:45:00Z_2026-09-24T10:25:00Z",
        pattern_type="W",
        status="BREAKOUT_CONFIRMED",
        s1_index=5, s1_price=984.2, s1_time="2026-09-24T09:45:00Z",
        neckline_index=10, neckline_price=986.8, neckline_time="2026-09-24T10:10:00Z",
        s2_index=15, s2_price=985.3, s2_time="2026-09-24T10:25:00Z",
        pattern_height=2.6, depth_atr=1.5, symmetry_atr=0.2, bar_separation=5, quality_score=75,
        breakout_candle_index=18,
        breakout_candle_time=t_breakout,
        breakout_close=987.4,  # 987.4 > 986.8
        target_analysis=PatternTargetAnalysis(
            pattern_height=2.6, measured_target=993.4, target_2=991.01,
            invalidation_level=985.11, retest_level=986.8, retest_status="PENDING",
            pattern_status="CONFIRMED_BREAKOUT", pattern_quality_score=75, quality_breakdown={}, interpretation=""
        )
    )

    candles = [Candle(timestamp=f"2026-09-24T10:{i*5:02d}:00Z", open=985, high=986, low=984, close=985.5, volume=100) for i in range(18)]
    candles.append(Candle(timestamp=t_breakout, open=986.0, high=987.5, low=986.0, close=987.4, volume=200))

    # Initial sync
    res1 = engine.sync_chart_patterns("SBIN", "5M", [pat], pat, candles)
    assert res1 is not None
    assert len(engine.alerts) == 1
    initial_alert_id = engine.alerts[0].alert_id

    # 10 subsequent sync calls as price moves
    for step in range(10):
        candles.append(Candle(timestamp=f"2026-09-24T11:{step*5:02d}:00Z", open=987, high=989, low=986.5, close=988.0, volume=100))
        res_sub = engine.sync_chart_patterns("SBIN", "5M", [pat], pat, candles)
        assert len(engine.alerts) == 1, f"Step {step} created duplicate alert: count={len(engine.alerts)}"
        assert engine.alerts[0].alert_id == initial_alert_id, "Alert ID must remain identical"
        assert engine.alerts[0].breakout_candle_timestamp == t_breakout
        assert engine.alerts[0].breakout_close == 987.4
