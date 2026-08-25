import pytest
import pandas as pd
from datetime import datetime, timezone
from app.models.schemas import (
    MultiTimeframeSynthesis,
    SingleTimeframeAnalysis,
    StructureBreakEvent,
    EvidenceScoreBreakdown,
    TechnicalIndicators,
    SupportResistanceSummary
)
from app.alerts.engine import AlertEngine
from app.alerts.high_confluence_engine import HighConfluenceAlertEngine

def make_test_synthesis(events_15m):
    score = EvidenceScoreBreakdown(
        total_score=85,
        category="Strong Evidence Alignment",
        structure_points=25,
        htf_alignment_points=25,
        momentum_points=15,
        volume_points=10,
        breakout_points=10,
        details=["Strong Trendline Break", "High relative volume"]
    )
    analysis_15m = SingleTimeframeAnalysis(
        timeframe="15M",
        trend="BULLISH",
        structure_type="BULLISH",
        structure_description="Bullish expansion",
        swings=[],
        recent_events=events_15m,
        support_resistance=SupportResistanceSummary(
            all_levels=[],
            major_support=24000.0,
            minor_support=24100.0,
            minor_resistance=24300.0,
            major_resistance=24400.0,
            current_price=24250.0
        ),
        trendlines=[],
        indicators=TechnicalIndicators(
            rsi_14=62.0,
            ema_20=24180.0,
            relative_volume=1.45,
            atr_14=20.0
        ),
        breakout_status="CONFIRMED BREAKOUT",
        candle_count=50,
        latest_candle_time="2026-08-25T11:00:00+05:30"
    )
    return MultiTimeframeSynthesis(
        symbol="NIFTY 50",
        ticker="^NSEI",
        provider="yfinance",
        data_status="LIVE",
        last_updated=datetime.now(timezone.utc).isoformat(),
        is_stale=False,
        status_message="Live feed",
        current_price=24250.0,
        timeframes={"15M": analysis_15m},
        overall_bias="BULLISH",
        current_state="FULL BULLISH ALIGNMENT",
        evidence_score=score,
        confirmation_state="HIGH",
        short_term_state="EXPANDING",
        key_supports=[24000.0, 24100.0],
        key_resistances=[24300.0, 24400.0],
        synthesis_rationale="Bullish breakout"
    )

def test_alert_engine_separation():
    """
    Verify:
    1. Standard AlertEngine handles ONLY standard breakout events.
    2. HighConfluenceAlertEngine handles ONLY high-confluence breakout events.
    3. Both engines work completely independently.
    """
    normal_engine = AlertEngine()
    hc_engine = HighConfluenceAlertEngine()

    std_event = StructureBreakEvent(
        id="std_res_1",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T11:00:00+05:30",
        event_type="RESISTANCE_BREAK",
        direction="BULLISH",
        broken_level=24200.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=85,
        notes="Standard Resistance Break"
    )

    hc_event = StructureBreakEvent(
        id="hc_tl_ema_vol_1",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T11:00:00+05:30",
        event_type="TRENDLINE_EMA_VOLUME_UP_BREAKOUT",
        direction="BULLISH",
        broken_level=24150.0,
        break_price=24250.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=85,
        notes="Trendline + 20 EMA + Volume Breakout"
    )

    # Synthesis with both standard and high-confluence events
    synthesis = make_test_synthesis([std_event, hc_event])

    normal_alerts = normal_engine.process_synthesis_for_alerts(synthesis)
    hc_alerts = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)

    # Standard engine should receive ONLY the standard alert
    assert len(normal_alerts) == 1
    assert normal_alerts[0].event_type == "RESISTANCE_BREAK"
    assert "TRENDLINE_EMA_VOLUME" not in normal_alerts[0].event_type

    # High-confluence engine should receive ONLY the high-confluence alert
    assert len(hc_alerts) == 1
    assert hc_alerts[0].alert_type == "TRENDLINE_EMA_VOLUME_UP_BREAKOUT"
    assert hc_alerts[0].alert_category == "HIGH_CONFLUENCE"
    assert hc_alerts[0].direction == "UP"
    assert hc_alerts[0].trendline_level == 24150.0

def test_hc_engine_deduplication():
    """
    Verify high-confluence alert engine prevents duplicate alerts for the same event ID.
    """
    hc_engine = HighConfluenceAlertEngine()
    hc_event = StructureBreakEvent(
        id="hc_w_pat_1",
        symbol="NIFTY 50",
        timeframe="15M",
        timestamp="2026-08-25T11:00:00+05:30",
        event_type="W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT",
        direction="BULLISH",
        broken_level=24190.0,
        break_price=24260.0,
        break_candle_index=48,
        volume_confirmed=True,
        atr_at_break=20.0,
        htf_alignment="BULLISH",
        evidence_score=88,
        notes="W Pattern + Trendline + 20 EMA Breakout"
    )
    synthesis = make_test_synthesis([hc_event])

    first_pass = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)
    assert len(first_pass) == 1

    second_pass = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)
    assert len(second_pass) == 0  # No duplicate
    assert len(hc_engine.get_alerts()) == 1

def test_hc_engine_empty_when_no_breakout():
    """
    Verify high-confluence alert engine produces zero alerts when no precision events exist.
    """
    hc_engine = HighConfluenceAlertEngine()
    synthesis = make_test_synthesis([])
    alerts = hc_engine.process_synthesis_for_high_confluence_alerts(synthesis)
    assert len(alerts) == 0
    assert len(hc_engine.get_alerts()) == 0
