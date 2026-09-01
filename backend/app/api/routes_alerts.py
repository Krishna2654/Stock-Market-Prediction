import uuid
import asyncio
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timezone
from app.models.schemas import AlertRule, AlertNotification, HighConfluenceAlert, MWBreakoutAlert, TrendlineShortlistCandidate, WMPatternStructure, MultiTimeframeSynthesis
from app.alerts.engine import alert_engine
from app.alerts.high_confluence_engine import high_confluence_alert_engine
from app.alerts.mw_breakout_engine import mw_breakout_engine
from app.alerts.trendline_shortlist_engine import trendline_shortlist_engine
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.api.websocket import ws_manager
from app.api.deps import get_current_provider, configured_instruments

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

@router.get("/rules", response_model=List[AlertRule])
def get_alert_rules():
    return alert_engine.get_rules()

@router.post("/rules", response_model=AlertRule)
def create_alert_rule(rule: AlertRule):
    if not rule.id:
        rule.id = str(uuid.uuid4())[:8]
    if not rule.created_at:
        rule.created_at = datetime.now(timezone.utc).isoformat()
    return alert_engine.add_rule(rule)

@router.delete("/rules/{rule_id}")
def delete_alert_rule(rule_id: str):
    success = alert_engine.remove_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return {"message": f"Rule {rule_id} removed"}

@router.get("/notifications", response_model=List[AlertNotification])
def get_notifications(limit: int = 50):
    return alert_engine.get_notifications(limit=limit)

@router.post("/clear")
def clear_notifications():
    alert_engine.clear_notifications()
    return {"message": "Notifications cleared"}

@router.post("/test", response_model=AlertNotification)
async def trigger_test_alert():
    now_str = datetime.now(timezone.utc).isoformat()
    test_notif = AlertNotification(
        id=f"test_{str(uuid.uuid4())[:8]}",
        timestamp=now_str,
        symbol="NIFTY 50",
        timeframe="15M",
        event_type="RESISTANCE_BREAK",
        message="💥 [TEST ALERT] NIFTY 50 15M Resistance Breakout above ₹24,250.00 (Close: ₹24,285.00)",
        price=24285.0,
        level=24250.0,
        evidence_score=85,
        volume_confirmed=True,
        htf_alignment="BULLISH",
        read=False
    )
    alert_engine.notifications.append(test_notif)
    
    # Broadcast immediately to all connected WebSockets
    await ws_manager.broadcast({
        "type": "ALERT_TRIGGERED",
        "alert": test_notif.model_dump()
    })
    
    return test_notif

# -------------------------------------------------------------
# HIGH-CONFLUENCE BREAKOUT ALERTS (COMPLETELY SEPARATE ENDPOINTS)
# -------------------------------------------------------------

@router.get("/high-confluence", response_model=List[HighConfluenceAlert])
def get_high_confluence_alerts(
    symbol: Optional[str] = Query(None, description="Optional symbol filter"),
    limit: int = Query(30, description="Max number of alerts")
):
    return high_confluence_alert_engine.get_alerts(symbol=symbol, limit=limit)

@router.post("/high-confluence/clear")
def clear_high_confluence_alerts():
    high_confluence_alert_engine.clear_alerts()
    return {"message": "High-confluence breakout alerts cleared"}

@router.post("/high-confluence/test", response_model=HighConfluenceAlert)
async def trigger_test_high_confluence_alert(
    alert_type: str = Query("TRENDLINE_EMA_VOLUME_UP_BREAKOUT", description="Alert type")
):
    now_str = datetime.now(timezone.utc).isoformat()
    if alert_type == "W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT":
        w_targets = PrecisionBreakoutDetector.calculate_pattern_targets(
            pattern_type="W",
            s1_price=24500.0,
            s2_price=24520.0,
            neckline_price=24850.0,
            breakout_close=24920.0,
            key_resistances=[25050.0, 25350.0],
            quality_score=88,
            quality_breakdown={"structure": 20, "swing_quality": 15, "depth": 15, "symmetry": 10, "separation": 10, "neckline_quality": 8, "trendline_confluence": 10, "ema_confluence": 5, "breakout_candle": 5}
        )
        test_alert = HighConfluenceAlert(
            id=f"hc_test_{str(uuid.uuid4())[:8]}",
            alert_category="HIGH_CONFLUENCE",
            alert_type="W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT",
            symbol="NIFTY 50",
            timeframe="15M",
            direction="UP",
            timestamp=now_str,
            breakout_candle_timestamp=now_str,
            breakout_candle_open=24850.0,
            breakout_candle_high=24930.0,
            breakout_candle_low=24840.0,
            breakout_candle_close=24920.0,
            trendline_level=24860.0,
            ema20_level=24875.0,
            volume_ratio=1.45,
            pattern_id="NIFTY50_15M_W_TEST_001",
            pattern_type="W",
            pattern_formed_time=now_str,
            first_swing_price=24500.0,
            first_swing_time=now_str,
            second_swing_price=24520.0,
            second_swing_time=now_str,
            neckline_price=24850.0,
            neckline_level=24850.0,
            neckline_time=now_str,
            trendline_confirmed=True,
            ema_confirmed=True,
            volume_confirmed=True,
            neckline_confirmed=True,
            candle_closed_confirmed=True,
            evidence_score=88,
            pattern_quality_score=88,
            target_analysis=w_targets,
            next_level=w_targets.measured_target,
            invalidation_level=w_targets.invalidation_level,
            event_created_at=now_str,
            message=f"🟢 W PATTERN + TRENDLINE + 20 EMA — UP BREAKOUT\nNIFTY 50 • 15M\nBreakout Candle Close: ₹24,920.00 | Neckline: ₹24,850.00 ✓\nTrendline: ₹24,860.00 ✓ | 20 EMA: ₹24,875.00 ✓\nMeasured Target: ₹{w_targets.measured_target:,.2f} | Nearest Resistance: ₹{w_targets.nearest_obstacle:,.2f}\nCandle: CONFIRMED CLOSED ✓ | Pattern Quality: 88/100"
        )
    elif alert_type == "M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT":
        m_targets = PrecisionBreakoutDetector.calculate_pattern_targets(
            pattern_type="M",
            s1_price=57500.0,
            s2_price=57480.0,
            neckline_price=57435.0,
            breakout_close=57300.0,
            key_supports=[57380.0, 57150.0],
            quality_score=86,
            quality_breakdown={"structure": 20, "swing_quality": 15, "depth": 15, "symmetry": 10, "separation": 10, "neckline_quality": 8, "trendline_confluence": 8, "ema_confluence": 5, "breakout_candle": 5}
        )
        test_alert = HighConfluenceAlert(
            id=f"hc_test_{str(uuid.uuid4())[:8]}",
            alert_category="HIGH_CONFLUENCE",
            alert_type="M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT",
            symbol="BANK NIFTY",
            timeframe="1H",
            direction="DOWN",
            timestamp=now_str,
            breakout_candle_timestamp=now_str,
            breakout_candle_open=57480.0,
            breakout_candle_high=57510.0,
            breakout_candle_low=57280.0,
            breakout_candle_close=57300.0,
            trendline_level=57435.30,
            ema20_level=57460.62,
            volume_ratio=1.55,
            pattern_id="BANKNIFTY_1H_M_TEST_002",
            pattern_type="M",
            pattern_formed_time=now_str,
            first_swing_price=57500.0,
            first_swing_time=now_str,
            second_swing_price=57480.0,
            second_swing_time=now_str,
            neckline_price=57435.0,
            neckline_level=57435.0,
            neckline_time=now_str,
            trendline_confirmed=True,
            ema_confirmed=True,
            volume_confirmed=True,
            neckline_confirmed=True,
            candle_closed_confirmed=True,
            evidence_score=86,
            pattern_quality_score=86,
            target_analysis=m_targets,
            next_level=m_targets.measured_target,
            invalidation_level=m_targets.invalidation_level,
            event_created_at=now_str,
            message=f"🔴 M PATTERN + TRENDLINE + 20 EMA — DOWN BREAKOUT\nBANK NIFTY • 1H\nBreakout Candle Close: ₹57,300.00 | Neckline: ₹57,435.00 ✓\nTrendline: ₹57,435.30 ✓ | 20 EMA: ₹57,460.62 ✓\nMeasured Target: ₹{m_targets.measured_target:,.2f} | Nearest Support: ₹{m_targets.nearest_obstacle:,.2f}\nCandle: CONFIRMED CLOSED ✓ | Pattern Quality: 86/100"
        )
    else:
        test_alert = HighConfluenceAlert(
            id=f"hc_test_{str(uuid.uuid4())[:8]}",
            alert_category="HIGH_CONFLUENCE",
            alert_type="TRENDLINE_EMA_VOLUME_UP_BREAKOUT",
            symbol="NIFTY 50",
            timeframe="15M",
            direction="UP",
            timestamp=now_str,
            breakout_candle_timestamp=now_str,
            breakout_candle_open=24840.0,
            breakout_candle_high=24925.0,
            breakout_candle_low=24830.0,
            breakout_candle_close=24910.0,
            trendline_level=24850.0,
            ema20_level=24870.0,
            volume_ratio=1.45,
            pattern_type=None,
            neckline_level=None,
            trendline_confirmed=True,
            ema_confirmed=True,
            volume_confirmed=True,
            neckline_confirmed=True,
            candle_closed_confirmed=True,
            evidence_score=85,
            next_level=25050.0,
            invalidation_level=24850.0,
            event_created_at=now_str,
            message="🟢 UP BREAKOUT — TRENDLINE + 20 EMA + VOLUME\nNIFTY 50 • 15M\nBreakout Candle Close: ₹24,910.00 | Trendline: ₹24,850.00 ✓\n20 EMA: ₹24,870.00 ✓ | Volume: 1.45× ✓\nCandle: CONFIRMED CLOSED ✓ | Evidence: 85/100"
        )
    
    high_confluence_alert_engine.alerts.append(test_alert)

    # Broadcast on separate WebSocket event type
    await ws_manager.broadcast({
        "type": "HIGH_CONFLUENCE_ALERT_TRIGGERED",
        "alert": test_alert.model_dump()
    })

    return test_alert

# -------------------------------------------------------------
# DEDICATED M/W BREAKOUT PAGE ENDPOINTS (ZERO FAKE DATA PIPELINE)
# -------------------------------------------------------------

@router.get("/mw-breakouts", response_model=List[MWBreakoutAlert])
def get_mw_breakout_alerts(
    symbol: Optional[str] = Query(None, description="Symbol filter or search query"),
    timeframe: Optional[str] = Query(None, description="Timeframe filter (4H, 1H, 15M, 5M, or All)"),
    pattern_type: Optional[str] = Query(None, description="Pattern type (W, M, or All)"),
    status: Optional[str] = Query(None, description="Status filter (ACTIVE, COMPLETED, INVALIDATED, or All)"),
    date_filter: Optional[str] = Query(None, description="Date filter (latest, today, 24h, 7d, all)"),
    limit: int = Query(200, description="Max results")
):
    return mw_breakout_engine.get_alerts(
        symbol=symbol,
        timeframe=timeframe,
        pattern_type=pattern_type,
        status=status,
        date_filter=date_filter,
        limit=limit
    )

@router.get("/mw-breakouts-candidates", response_model=List[WMPatternStructure])
async def get_mw_breakout_candidates(
    symbol: Optional[str] = Query(None, description="Symbol filter"),
    timeframe: Optional[str] = Query("15M", description="Timeframe")
):
    """
    Exposes evaluated candidate formations (both confirmed and rejected, with rejection_reason)
    for transparent debugging of W/M structural decisions.
    """
    from app.api.routes_analysis import get_chart_data
    sym = symbol or "BTC/USD"
    tf = timeframe or "15M"
    try:
        data = await get_chart_data(symbol=sym, timeframe=tf)
        return data.get("wm_debug_candidates", [])
    except Exception:
        return []

@router.get("/mw-breakouts/stats")
def get_mw_breakout_stats():
    return mw_breakout_engine.get_summary_stats()

@router.post("/mw-breakouts/refresh")
async def refresh_mw_breakouts():
    """
    Triggers a live multi-timeframe precision scan across all configured active instruments,
    updates mw_breakout_engine with newly confirmed precision W/M alerts,
    and returns the latest summary statistics and alerts.
    """
    provider = get_current_provider()
    result = await mw_breakout_engine.rescan_all_instruments(provider, configured_instruments)
    return {
        "message": "M/W breakout alerts refreshed successfully",
        "result": result,
        "stats": mw_breakout_engine.get_summary_stats()
    }

@router.get("/mw-breakouts/{alert_id:path}", response_model=MWBreakoutAlert)
def get_mw_breakout_detail(alert_id: str):
    alert = mw_breakout_engine.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="M/W Breakout Alert not found")
    return alert

@router.post("/mw-breakouts/read-all")
def mark_mw_breakouts_read():
    mw_breakout_engine.mark_all_read()
    return {"message": "All M/W breakout alerts marked as read"}

@router.post("/mw-breakouts/clear")
def clear_mw_breakouts():
    mw_breakout_engine.clear_alerts()
    return {"message": "M/W breakout alerts cleared"}

@router.post("/mw-breakouts/test", response_model=MWBreakoutAlert)
async def trigger_test_mw_breakout(
    pattern_type: str = Query("W", description="Pattern type W or M")
):
    now_str = datetime.now(timezone.utc).isoformat()
    if pattern_type.upper() == "W":
        w_targets = PrecisionBreakoutDetector.calculate_pattern_targets(
            pattern_type="W",
            s1_price=24500.0,
            s2_price=24520.0,
            neckline_price=24850.0,
            breakout_close=24910.0,
            prev_swing_sl=24480.0,
            key_resistances=[25050.0, 25350.0],
            quality_score=87,
            quality_breakdown={"structure": 20, "swing_quality": 15, "depth": 15, "symmetry": 10, "separation": 10, "neckline_quality": 10, "trendline_confluence": 10, "ema_confluence": 5, "breakout_candle": 5}
        )
        test_alert = MWBreakoutAlert(
            alert_id=f"mw_test_NIFTY_50_15M_W_{str(uuid.uuid4())[:8]}",
            alert_type="W_BREAKOUT_CONFIRMED",
            pattern_type="W",
            direction="UP",
            symbol="NIFTY 50",
            ticker="^NSEI",
            timeframe="15M",
            pattern_id="NIFTY50_15M_W_TEST_001",
            s1_price=24500.0,
            s1_timestamp=now_str,
            s2_price=24520.0,
            s2_timestamp=now_str,
            neckline_price=24850.0,
            neckline_timestamp=now_str,
            pattern_height=350.0,
            breakout_candle_timestamp=now_str,
            breakout_open=24840.0,
            breakout_high=24925.0,
            breakout_low=24830.0,
            breakout_close=24910.0,
            trendline_price=24820.0,
            ema20_price=24800.0,
            volume=250000.0,
            relative_volume=1.45,
            measured_target=w_targets.measured_target,
            target_2=w_targets.target_2 or 25550.0,
            nearest_resistance=25050.0,
            invalidation_level=w_targets.invalidation_level,
            quality_score=87,
            quality_breakdown={"structure": 20, "swing_quality": 15, "depth": 15, "symmetry": 10, "separation": 10, "neckline_quality": 10, "trendline_confluence": 10, "ema_confluence": 5, "breakout_candle": 5},
            reversal_score=40,
            trendline_score=30,
            ema_score=30,
            reversal_points=40,
            trendline_points=30,
            ema_points=30,
            status="TARGET OPEN",
            event_created_at=now_str,
            read=False
        )
    else:
        m_targets = PrecisionBreakoutDetector.calculate_pattern_targets(
            pattern_type="M",
            s1_price=57500.0,
            s2_price=57480.0,
            neckline_price=57435.0,
            breakout_close=57300.0,
            prev_swing_sl=57530.0,
            key_supports=[57380.0, 57150.0],
            quality_score=86,
            quality_breakdown={"structure": 20, "swing_quality": 15, "depth": 15, "symmetry": 10, "separation": 10, "neckline_quality": 8, "trendline_confluence": 8, "ema_confluence": 5, "breakout_candle": 5}
        )
        test_alert = MWBreakoutAlert(
            alert_id=f"mw_test_BANK_NIFTY_1H_M_{str(uuid.uuid4())[:8]}",
            alert_type="M_BREAKDOWN_CONFIRMED",
            pattern_type="M",
            direction="DOWN",
            symbol="BANK NIFTY",
            ticker="^NSEBANK",
            timeframe="1H",
            pattern_id="BANKNIFTY_1H_M_TEST_002",
            s1_price=57500.0,
            s1_timestamp=now_str,
            s2_price=57480.0,
            s2_timestamp=now_str,
            neckline_price=57435.0,
            neckline_timestamp=now_str,
            pattern_height=65.0,
            breakout_candle_timestamp=now_str,
            breakout_open=57480.0,
            breakout_high=57510.0,
            breakout_low=57280.0,
            breakout_close=57300.0,
            trendline_price=57435.30,
            ema20_price=57460.62,
            volume=180000.0,
            relative_volume=1.38,
            measured_target=m_targets.measured_target,
            target_2=m_targets.target_2 or 57305.0,
            nearest_support=57380.0,
            invalidation_level=m_targets.invalidation_level,
            quality_score=86,
            quality_breakdown={"structure": 20, "swing_quality": 15, "depth": 15, "symmetry": 10, "separation": 10, "neckline_quality": 8, "trendline_confluence": 8, "ema_confluence": 5, "breakout_candle": 5},
            reversal_score=40,
            trendline_score=30,
            ema_score=30,
            reversal_points=40,
            trendline_points=30,
            ema_points=30,
            status="TARGET OPEN",
            event_created_at=now_str,
            read=False
        )

    mw_breakout_engine.alerts.insert(0, test_alert)
    mw_breakout_engine._save_to_storage()
    await ws_manager.broadcast({
        "type": "MW_BREAKOUT_TRIGGERED",
        "alert": test_alert.model_dump()
    })
    return test_alert

# -------------------------------------------------------------
# TRENDLINE BREAKOUT STOCK SHORTLISTING ENDPOINTS
# -------------------------------------------------------------

@router.get("/trendline-shortlist", response_model=List[TrendlineShortlistCandidate])
def get_trendline_shortlist(
    symbol: Optional[str] = Query(None, description="Symbol filter or search query"),
    timeframe: Optional[str] = Query(None, description="Timeframe filter (4H, 1H, 15M, 5M, or All)"),
    direction: Optional[str] = Query(None, description="Direction filter (BULLISH, BEARISH, or All)"),
    status: Optional[str] = Query(None, description="Status filter (WATCHING, BREAKOUT, CONFIRMED, RETEST, FALSE BREAKOUT, or All)"),
    min_score: int = Query(70, description="Minimum trendline score"),
    limit: int = Query(50, description="Max results")
):
    try:
        from app.api.routes_analysis import _synthesis_cache
        for _, (_, synth) in list(_synthesis_cache.items()):
            trendline_shortlist_engine.process_synthesis(synth)
    except Exception:
        pass

    return trendline_shortlist_engine.get_shortlist(
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        status=status,
        min_score=min_score,
        limit=limit
    )

@router.get("/trendline-shortlist/{candidate_id:path}", response_model=TrendlineShortlistCandidate)
def get_trendline_shortlist_detail(candidate_id: str):
    candidate = trendline_shortlist_engine.get_candidate_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Trendline shortlist candidate not found")
    return candidate

@router.post("/trendline-shortlist/clear")
def clear_trendline_shortlist():
    trendline_shortlist_engine.clear_shortlist()
    return {"message": "Trendline shortlist cleared successfully"}

@router.post("/trendline-shortlist/test", response_model=TrendlineShortlistCandidate)
async def trigger_test_trendline_shortlist(
    direction: str = Query("BULLISH", description="Direction (BULLISH or BEARISH)")
):
    candidate = trendline_shortlist_engine.trigger_test_candidate(direction=direction)
    await ws_manager.broadcast({
        "type": "TRENDLINE_SHORTLIST_UPDATED",
        "candidate": candidate.model_dump()
    })
    return candidate

