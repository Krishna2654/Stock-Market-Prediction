from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime

class Candle(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

class OHLCVResponse(BaseModel):
    symbol: str
    ticker: str
    timeframe: str
    provider: str
    status: str
    is_stale: bool
    last_updated: str
    candles: List[Candle]

class SwingPoint(BaseModel):
    index: int
    timestamp: str
    price: float
    type: Literal["HH", "HL", "LH", "LL"]
    is_high: bool
    confirmed: bool
    confirmation_index: Optional[int] = None

class ProtectedSwing(BaseModel):
    price: float
    index: int
    timestamp: str
    swing_type: Literal["HL", "LH"]
    is_broken: bool = False
    notes: str = ""

class PatternTargetAnalysis(BaseModel):
    pattern_height: float
    measured_target: float
    nearest_obstacle: Optional[float] = None
    target_2: Optional[float] = None
    target_zone: Optional[str] = None
    invalidation_level: float
    retest_level: float
    retest_status: str = "PENDING_RETEST"  # "HOLDING", "FAILED_RETEST", "PENDING_RETEST"
    pattern_status: str = "CONFIRMED_BREAKOUT"  # "FORMING", "CONFIRMED_BREAKOUT", "TARGET_ACTIVE", "TARGET_HIT", "INVALIDATED"
    pattern_quality_score: int = 85
    quality_breakdown: Dict[str, int] = {}
    interpretation: str = ""

class WMPatternStructure(BaseModel):
    pattern_id: str
    pattern_type: Literal["W", "M"]
    status: Literal[
        "FORMING", "ACTIVE", "CONFIRMED", "BREAKOUT_FORMING", "BREAKDOWN_FORMING",
        "STRUCTURAL_BREAKOUT_CONFIRMED", "STRUCTURAL_BREAKDOWN_CONFIRMED",
        "BREAKOUT_CONFIRMED", "HIGH_CONFLUENCE_CONFIRMED", "TARGET_1_HIT",
        "TARGET_2_HIT", "SL_HIT", "INVALIDATED", "REJECTED"
    ]
    s1_index: int
    s1_price: float
    s1_time: str
    neckline_index: int
    neckline_price: float
    neckline_time: str
    s2_index: int
    s2_price: float
    s2_time: str
    pattern_height: float
    depth_atr: float
    symmetry_atr: float
    bar_separation: int
    quality_score: int
    breakout_candle_index: Optional[int] = None
    breakout_candle_time: Optional[str] = None
    breakout_close: Optional[float] = None
    target_analysis: Optional[PatternTargetAnalysis] = None
    is_active: bool = False
    rejection_reason: Optional[str] = None
    prev_swing_sl_price: Optional[float] = None
    prev_swing_sl_time: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    stop_loss: Optional[float] = None

class StructureBreakEvent(BaseModel):
    id: str
    symbol: str
    timeframe: str
    timestamp: str
    event_type: str  # e.g., "BULLISH_BOS", "BEARISH_BOS", "BULLISH_CHOCH", "BEARISH_CHOCH", "SUPPORT_BREAK", "RESISTANCE_BREAK", "TREND_LINE_BREAK"
    direction: Literal["BULLISH", "BEARISH"]
    broken_level: float
    break_price: float
    break_candle_index: int
    volume_confirmed: bool
    atr_at_break: float
    htf_alignment: Literal["BULLISH", "BEARISH", "NEUTRAL", "MIXED"]
    evidence_score: int
    notes: str = ""
    is_retested: bool = False
    retest_price: Optional[float] = None
    retest_status: Optional[str] = None
    pattern_id: Optional[str] = None
    pattern_type: Optional[str] = None
    pattern_formed_time: Optional[str] = None
    first_swing_price: Optional[float] = None
    first_swing_time: Optional[str] = None
    second_swing_price: Optional[float] = None
    second_swing_time: Optional[str] = None
    neckline_price: Optional[float] = None
    neckline_time: Optional[str] = None
    breakout_candle_open: Optional[float] = None
    breakout_candle_high: Optional[float] = None
    breakout_candle_low: Optional[float] = None
    breakout_candle_close: Optional[float] = None
    trendline_level: Optional[float] = None
    ema20_level: Optional[float] = None
    volume_ratio: Optional[float] = None
    pattern_quality_score: Optional[int] = None
    target_analysis: Optional[PatternTargetAnalysis] = None

class SupportResistanceLevel(BaseModel):
    price: float
    level_type: Literal["SUPPORT", "RESISTANCE"]
    strength: Literal["MAJOR", "MINOR"]
    touch_count: int
    timeframe: str
    distance_pct: float
    last_tested_timestamp: Optional[str] = None

class SupportResistanceSummary(BaseModel):
    major_support: Optional[float] = None
    minor_support: Optional[float] = None
    current_price: float
    minor_resistance: Optional[float] = None
    major_resistance: Optional[float] = None
    all_levels: List[SupportResistanceLevel] = []

class TechnicalIndicators(BaseModel):
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    ema_200: Optional[float] = None
    rsi_14: Optional[float] = None
    atr_14: Optional[float] = None
    volume_sma_20: Optional[float] = None
    relative_volume: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    vwap: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None

class TrendlineTouchPoint(BaseModel):
    index: int
    timestamp: str
    price: float

class TrendlineSchema(BaseModel):
    line_type: Literal["ASCENDING_SUPPORT", "DESCENDING_RESISTANCE"]
    rank: Literal["PRIMARY", "SECONDARY", "MINOR"] = "PRIMARY"
    strength: Literal["MAJOR", "INTERMEDIATE", "MINOR"] = "INTERMEDIATE"
    p1_index: int
    p1_price: float
    p1_time: str
    p2_index: int
    p2_price: float
    p2_time: str
    end_index: int
    end_price: float
    slope: float
    intercept: float
    touch_count: int
    touch_points: List[TrendlineTouchPoint] = []
    r_squared: Optional[float] = None
    swing_structure: Optional[str] = None
    structure_points: Optional[List[str]] = None
    status: Literal["ACTIVE", "BROKEN", "RETESTED"] = "ACTIVE"
    is_active: bool = True
    is_broken: bool = False

class SingleTimeframeAnalysis(BaseModel):
    timeframe: str
    trend: Literal["STRONG BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "STRONG BEARISH"]
    structure_type: str
    latest_event: Optional[StructureBreakEvent] = None
    important_level: Optional[float] = None
    protected_swing: Optional[ProtectedSwing] = None
    swings: List[SwingPoint] = []
    recent_events: List[StructureBreakEvent] = []
    trendlines: List[Dict[str, Any]] = []
    indicators: TechnicalIndicators
    support_resistance: SupportResistanceSummary
    breakout_status: Literal["NONE", "POSSIBLE BREAK", "CONFIRMED BREAKOUT", "CONFIRMED BREAKDOWN", "FAILED BREAKOUT", "FAILED BREAKDOWN"]
    predictive_scenarios: Dict[str, Any] = {}
    wm_patterns: List[WMPatternStructure] = []
    active_wm_pattern: Optional[WMPatternStructure] = None
    candle_count: int
    latest_candle_time: str

class EvidenceScoreBreakdown(BaseModel):
    total_score: int
    category: Literal["Strong Evidence Alignment", "Moderate-to-Strong Alignment", "Mixed Evidence", "Weak Alignment", "Conflicting / Weak Evidence"]
    structure_points: int
    htf_alignment_points: int
    momentum_points: int
    volume_points: int
    breakout_points: int
    details: List[str] = []

class WhatJustChanged(BaseModel):
    symbol: str
    timeframe: str
    previous_state: str
    new_state: str
    event_type: str
    broken_level: float
    break_price: float
    volume_confirmed: bool
    structural_interpretation: str
    timestamp: str

class MarketSessionStatus(BaseModel):
    is_running: bool
    status: Literal["OPEN", "CLOSED", "PRE-OPEN"]
    session_name: str
    message: str

class MultiTimeframeSynthesis(BaseModel):
    symbol: str
    ticker: str
    provider: str
    data_status: Literal["LIVE", "RECONNECTING", "TEMPORARILY DISCONNECTED", "RESTORING DATA", "LAST VALID ANALYSIS"] = "LIVE"
    market_session: Optional[MarketSessionStatus] = None
    last_updated: str
    is_stale: bool
    status_message: str
    current_price: float
    timeframes: Dict[str, SingleTimeframeAnalysis]
    mtf_candles: Optional[Dict[str, List[Candle]]] = Field(default=None, exclude=True)
    overall_bias: Literal["BULLISH", "BEARISH", "NEUTRAL", "MIXED"]
    current_state: Literal[
        "FULL BULLISH ALIGNMENT",
        "FULL BEARISH ALIGNMENT",
        "BULLISH WITH SHORT-TERM PULLBACK",
        "BEARISH WITH SHORT-TERM BOUNCE",
        "CONSOLIDATION",
        "POSSIBLE REVERSAL",
        "MIXED",
        "NO CLEAR STRUCTURE"
    ]
    evidence_score: EvidenceScoreBreakdown
    latest_important_event: Optional[StructureBreakEvent] = None
    what_just_changed: Optional[WhatJustChanged] = None
    confirmation_state: str
    short_term_state: str
    invalidation_level: Optional[float] = None
    key_supports: List[float] = []
    key_resistances: List[float] = []
    predictive_scenarios: Dict[str, Any] = {}
    synthesis_rationale: str

class AIAnalysisSummary(BaseModel):
    symbol: str
    generated_at: str
    model_used: str
    overall_bias: str
    evidence_alignment_score: int
    summary_markdown: str
    raw_synthesis: MultiTimeframeSynthesis

class InstrumentConfig(BaseModel):
    symbol: str
    ticker: str
    exchange: str = "NSE"
    asset_type: str = "EQUITY"
    is_active: bool = True

class AlertRule(BaseModel):
    id: str
    symbol: str
    timeframes: List[str]
    event_types: List[str]
    min_evidence_score: int = 50
    is_enabled: bool = True
    created_at: str

class AlertNotification(BaseModel):
    id: str
    timestamp: str
    symbol: str
    timeframe: str
    event_type: str
    message: str
    price: float
    level: float
    evidence_score: int
    volume_confirmed: bool
    htf_alignment: str
    read: bool = False

class HighConfluenceAlert(BaseModel):
    id: str
    alert_category: Literal["HIGH_CONFLUENCE"] = "HIGH_CONFLUENCE"
    alert_type: Literal[
        "TRENDLINE_EMA_VOLUME_UP_BREAKOUT",
        "TRENDLINE_EMA_VOLUME_DOWN_BREAKOUT",
        "W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT",
        "M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT"
    ]
    symbol: str
    timeframe: str
    direction: Literal["UP", "DOWN"]
    timestamp: str  # Kept for compatibility (= breakout_candle_timestamp)
    breakout_candle_timestamp: str
    breakout_candle_time_range: Optional[str] = None
    breakout_candle_open: Optional[float] = None
    breakout_candle_high: Optional[float] = None
    breakout_candle_low: Optional[float] = None
    breakout_candle_close: float
    trendline_level: float
    ema20_level: float
    volume_ratio: Optional[float] = None
    pattern_id: Optional[str] = None
    pattern_type: Optional[Literal["W", "M"]] = None
    pattern_formed_time: Optional[str] = None
    first_swing_price: Optional[float] = None
    first_swing_time: Optional[str] = None
    second_swing_price: Optional[float] = None
    second_swing_time: Optional[str] = None
    neckline_price: Optional[float] = None
    neckline_level: Optional[float] = None
    neckline_time: Optional[str] = None
    trendline_confirmed: bool = True
    ema_confirmed: bool = True
    volume_confirmed: bool = True
    neckline_confirmed: bool = True
    candle_closed_confirmed: bool = True
    evidence_score: int = 85
    pattern_quality_score: Optional[int] = None
    target_analysis: Optional[PatternTargetAnalysis] = None
    next_level: Optional[float] = None
    invalidation_level: Optional[float] = None
    event_created_at: str
    message: str

class MWBreakoutAlert(BaseModel):
    alert_id: str
    alert_type: Literal["W_BREAKOUT_CONFIRMED", "M_BREAKDOWN_CONFIRMED"]
    pattern_type: Literal["W", "M"]
    direction: Literal["UP", "DOWN"]
    symbol: str
    ticker: Optional[str] = None
    timeframe: str
    pattern_id: str

    # Pattern geometry
    s1_price: float
    s1_timestamp: str
    s2_price: float
    s2_timestamp: str
    neckline_price: float
    neckline_timestamp: str
    pattern_height: float

    # Breakout candle exact metrics
    breakout_candle_timestamp: str
    breakout_open: float
    breakout_high: float
    breakout_low: float
    breakout_close: float

    # Confluence metrics
    trendline_price: float
    ema20_price: float
    volume: float = 0.0
    relative_volume: float = 1.0

    # Projections & Target Analysis
    measured_target: float
    target_2: Optional[float] = None
    nearest_support: Optional[float] = None
    nearest_resistance: Optional[float] = None
    invalidation_level: float
    quality_score: int
    quality_breakdown: Dict[str, int] = {}

    # Lifecycle & status tracking
    status: Literal["TARGET OPEN", "TARGET 1 HIT", "TARGET 2 HIT", "SL HIT", "ACTIVE", "TARGET_1_HIT", "TARGET_2_HIT", "INVALIDATED", "EXPIRED"] = "TARGET OPEN"
    stop_loss: Optional[float] = None
    event_created_at: str
    read: bool = False

class BacktestRequest(BaseModel):
    symbol: str
    ticker: str
    timeframe: str = "15M"
    strategy: Literal["BOS_CONTINUATION", "CHOCH_REVERSAL", "TRENDLINE_BREAKOUT", "MULTI_TF_ALIGNMENT"] = "BOS_CONTINUATION"
    risk_reward_ratio: float = 2.0
    stop_loss_atr_multiple: float = 1.5
    slippage_bps: float = 2.0
    fee_bps: float = 3.0
    start_period: str = "60d"

class BacktestTrade(BaseModel):
    trade_id: int
    entry_time: str
    exit_time: str
    direction: Literal["LONG", "SHORT"]
    entry_price: float
    exit_price: float
    stop_loss: float
    target: float
    pnl_pct: float
    pnl_amount: float
    exit_reason: Literal["TARGET", "STOP_LOSS", "TIME_EXIT", "CHOCH_EXIT", "TL_EXIT"]
    mae_pct: float
    mfe_pct: float
    bars_held: int

class BacktestResult(BaseModel):
    symbol: str
    timeframe: str
    strategy: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    loss_rate_pct: float
    profit_factor: float
    total_return_pct: float
    max_drawdown_pct: float
    avg_trade_pnl_pct: float
    avg_favorable_excursion_pct: float
    avg_adverse_excursion_pct: float
    trades: List[BacktestTrade]
    equity_curve: List[Dict[str, Any]]

class PaperOrder(BaseModel):
    id: str
    symbol: str
    direction: Literal["LONG", "SHORT"]
    entry_price: float
    stop_loss: float
    target: float
    quantity: float
    status: Literal["PENDING", "OPEN", "CLOSED", "CANCELLED"]
    created_at: str
    closed_at: Optional[str] = None
    realized_pnl: Optional[float] = None
    notes: str = ""

class TrendlineShortlistCandidate(BaseModel):
    id: str
    symbol: str
    ticker: Optional[str] = None
    timeframe: str
    current_price: float
    trendline_type: Literal["RESISTANCE_BREAKOUT", "SUPPORT_BREAKDOWN"]
    direction: Literal["BULLISH", "BEARISH"]
    touch_count: int
    swing_structure: str  # e.g. "Lower High × 4" or "Higher Low × 3"
    structure_sequence: List[str] = []  # e.g. ["LH", "LH", "LH", "LH"]
    slope: float
    intercept: float
    trendline_price: float
    breakout_pct: float
    r_squared: float
    volume_ratio: Optional[float] = 1.0
    trendline_score: int  # 0 to 100
    confidence: Literal["VERY STRONG", "STRONG", "VALID", "NOT SHORTLISTED"] = "VALID"
    breakout_time: str
    status: Literal["WATCHING", "BREAKOUT", "CONFIRMED", "RETEST", "FALSE BREAKOUT"] = "BREAKOUT"
    invalidation_level: Optional[float] = None
    target_price: Optional[float] = None
    htf_alignment: Optional[str] = None
    notes: Optional[str] = None
    score_breakdown: Dict[str, int] = {}
    created_at: Optional[str] = None
