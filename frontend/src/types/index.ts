export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema_20?: number | null;
  ema_50?: number | null;
  ema_200?: number | null;
  rsi_14?: number | null;
  atr_14?: number | null;
  vwap?: number | null;
}

export interface SwingPoint {
  index: number;
  timestamp: string;
  price: number;
  type: "HH" | "HL" | "LH" | "LL";
  is_high: boolean;
  confirmed: boolean;
  confirmation_index?: number | null;
}

export interface ProtectedSwing {
  price: number;
  index: number;
  timestamp: string;
  swing_type: "HL" | "LH";
  is_broken: boolean;
  notes: string;
}

export interface TrendlineTouchPoint {
  index: number;
  timestamp: string;
  price: number;
}

export interface Trendline {
  line_type: "ASCENDING_SUPPORT" | "DESCENDING_RESISTANCE";
  rank: "PRIMARY" | "SECONDARY" | "MINOR";
  strength: "MAJOR" | "INTERMEDIATE" | "MINOR";
  p1_index: number;
  p1_price: number;
  p1_time: string;
  p2_index: number;
  p2_price: number;
  p2_time: string;
  end_index: number;
  end_price: number;
  slope: number;
  intercept: number;
  touch_count: number;
  touch_points: TrendlineTouchPoint[];
  r_squared?: number | null;
  swing_structure?: string | null;
  structure_points?: string[];
  status: "ACTIVE" | "BROKEN" | "RETESTED";
  is_active: boolean;
  is_broken: boolean;
}

export interface StructureBreakEvent {
  id: string;
  symbol: string;
  timeframe: string;
  timestamp: string;
  event_type: string;
  direction: "BULLISH" | "BEARISH";
  broken_level: number;
  break_price: number;
  break_candle_index: number;
  volume_confirmed: boolean;
  atr_at_break: number;
  htf_alignment: "BULLISH" | "BEARISH" | "NEUTRAL" | "MIXED";
  evidence_score: number;
  notes: string;
  is_retested?: boolean;
  retest_price?: number | null;
  retest_status?: string | null;
}

export interface SupportResistanceLevel {
  price: number;
  level_type: "SUPPORT" | "RESISTANCE";
  strength: "MAJOR" | "MINOR";
  touch_count: number;
  timeframe: string;
  distance_pct: number;
  last_tested_timestamp?: string | null;
}

export interface SupportResistanceSummary {
  major_support: number | null;
  minor_support: number | null;
  current_price: number;
  minor_resistance: number | null;
  major_resistance: number | null;
  all_levels: SupportResistanceLevel[];
}

export interface TechnicalIndicators {
  ema_20: number | null;
  ema_50: number | null;
  ema_200: number | null;
  rsi_14: number | null;
  atr_14: number | null;
  volume_sma_20: number | null;
  relative_volume: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  vwap: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
}

export interface SingleTimeframeAnalysis {
  timeframe: string;
  trend: "STRONG BULLISH" | "BULLISH" | "NEUTRAL" | "BEARISH" | "STRONG BEARISH";
  structure_type: string;
  latest_event: StructureBreakEvent | null;
  important_level: number | null;
  protected_swing?: ProtectedSwing | null;
  swings: SwingPoint[];
  recent_events: StructureBreakEvent[];
  trendlines: Trendline[];
  indicators: TechnicalIndicators;
  support_resistance: SupportResistanceSummary;
  breakout_status: "NONE" | "POSSIBLE BREAK" | "CONFIRMED BREAKOUT" | "CONFIRMED BREAKDOWN" | "FAILED BREAKOUT" | "FAILED BREAKDOWN";
  predictive_scenarios?: any;
  wm_patterns?: WMPatternStructure[];
  active_wm_pattern?: WMPatternStructure | null;
  wm_debug_candidates?: WMPatternStructure[];
  candle_count: number;
  latest_candle_time: string;
}

export interface EvidenceScoreBreakdown {
  total_score: number;
  category: "Strong Evidence Alignment" | "Moderate-to-Strong Alignment" | "Mixed Evidence" | "Weak Alignment" | "Conflicting / Weak Evidence";
  structure_points: number;
  htf_alignment_points: number;
  momentum_points: number;
  volume_points: number;
  breakout_points: number;
  details: string[];
}

export interface WhatJustChanged {
  symbol: string;
  timeframe: string;
  previous_state: string;
  new_state: string;
  event_type: string;
  broken_level: number;
  break_price: number;
  volume_confirmed: boolean;
  structural_interpretation: string;
  timestamp: string;
}

export interface MarketSessionStatus {
  is_running: boolean;
  status: "OPEN" | "CLOSED" | "PRE-OPEN";
  session_name: string;
  message: string;
}

export interface MultiTimeframeSynthesis {
  symbol: string;
  ticker: string;
  provider: string;
  data_status?: "LIVE" | "RECONNECTING" | "TEMPORARILY DISCONNECTED" | "RESTORING DATA" | "LAST VALID ANALYSIS";
  market_session?: MarketSessionStatus | null;
  last_updated: string;
  is_stale: boolean;
  status_message: string;
  current_price: number;
  timeframes: Record<string, SingleTimeframeAnalysis>;
  overall_bias: "BULLISH" | "BEARISH" | "NEUTRAL" | "MIXED";
  current_state:
    | "FULL BULLISH ALIGNMENT"
    | "FULL BEARISH ALIGNMENT"
    | "BULLISH WITH SHORT-TERM PULLBACK"
    | "BEARISH WITH SHORT-TERM BOUNCE"
    | "CONSOLIDATION"
    | "POSSIBLE REVERSAL"
    | "MIXED"
    | "NO CLEAR STRUCTURE";
  evidence_score: EvidenceScoreBreakdown;
  latest_important_event: StructureBreakEvent | null;
  what_just_changed?: WhatJustChanged | null;
  confirmation_state: string;
  short_term_state: string;
  invalidation_level: number | null;
  key_supports: number[];
  key_resistances: number[];
  predictive_scenarios?: any;
  synthesis_rationale: string;
}

export interface AIAnalysisSummary {
  symbol: string;
  generated_at: string;
  model_used: string;
  overall_bias: string;
  evidence_alignment_score: number;
  summary_markdown: string;
  raw_synthesis: MultiTimeframeSynthesis;
}

export interface InstrumentConfig {
  symbol: string;
  ticker: string;
  exchange: string;
  asset_type: string;
  is_active: boolean;
}

export interface AlertRule {
  id: string;
  symbol: string;
  timeframes: string[];
  event_types: string[];
  min_evidence_score: number;
  is_enabled: boolean;
  created_at: string;
}

export interface AlertNotification {
  id: string;
  timestamp: string;
  symbol: string;
  timeframe: string;
  event_type: string;
  message: string;
  price: number;
  level: number;
  evidence_score: number;
  volume_confirmed: boolean;
  htf_alignment: string;
  read: boolean;
}

export interface PatternTargetAnalysis {
  pattern_height: number;
  measured_target: number;
  nearest_obstacle?: number | null;
  target_2?: number | null;
  target_zone?: string | null;
  invalidation_level: number;
  retest_level: number;
  retest_status: string;
  pattern_status: string;
  pattern_quality_score: number;
  quality_breakdown?: Record<string, number>;
  interpretation: string;
}

export interface WMPatternStructure {
  pattern_id: string;
  pattern_type: "W" | "M";
  status:
    | "FORMING"
    | "ACTIVE"
    | "CONFIRMED"
    | "BREAKOUT_FORMING"
    | "BREAKDOWN_FORMING"
    | "STRUCTURAL_BREAKOUT_CONFIRMED"
    | "STRUCTURAL_BREAKDOWN_CONFIRMED"
    | "BREAKOUT_CONFIRMED"
    | "HIGH_CONFLUENCE_CONFIRMED"
    | "TARGET_1_HIT"
    | "TARGET_2_HIT"
    | "SL_HIT"
    | "INVALIDATED"
    | "REJECTED";
  s1_index: number;
  s1_price: number;
  s1_time: string;
  neckline_index: number;
  neckline_price: number;
  neckline_time: string;
  s2_index: number;
  s2_price: number;
  s2_time: string;
  pattern_height: number;
  depth_atr: number;
  symmetry_atr: number;
  bar_separation: number;
  quality_score: number;
  breakout_candle_index?: number | null;
  breakout_candle_time?: string | null;
  breakout_close?: number | null;
  target_analysis?: PatternTargetAnalysis | null;
  is_active: boolean;
  rejection_reason?: string | null;
  prev_swing_sl_price?: number | null;
  prev_swing_sl_time?: string | null;
  symbol?: string | null;
  timeframe?: string | null;
  target_1?: number | null;
  target_2?: number | null;
  stop_loss?: number | null;
}

export interface HighConfluenceAlert {
  id: string;
  alert_category: "HIGH_CONFLUENCE";
  alert_type:
    | "TRENDLINE_EMA_VOLUME_UP_BREAKOUT"
    | "TRENDLINE_EMA_VOLUME_DOWN_BREAKOUT"
    | "W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT"
    | "M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT";
  symbol: string;
  timeframe: string;
  direction: "UP" | "DOWN";
  timestamp: string;
  breakout_candle_timestamp: string;
  breakout_candle_time_range?: string | null;
  breakout_candle_open?: number | null;
  breakout_candle_high?: number | null;
  breakout_candle_low?: number | null;
  breakout_candle_close: number;
  breakout_close?: number;
  trendline_level: number;
  ema20_level: number;
  volume_ratio?: number | null;
  pattern_id?: string | null;
  pattern_type?: "W" | "M" | null;
  pattern_formed_time?: string | null;
  first_swing_price?: number | null;
  first_swing_time?: string | null;
  second_swing_price?: number | null;
  second_swing_time?: string | null;
  neckline_price?: number | null;
  neckline_level?: number | null;
  neckline_time?: string | null;
  trendline_confirmed: boolean;
  ema_confirmed: boolean;
  volume_confirmed: boolean;
  neckline_confirmed: boolean;
  candle_closed_confirmed: boolean;
  evidence_score: number;
  pattern_quality_score?: number | null;
  target_analysis?: PatternTargetAnalysis | null;
  next_level?: number | null;
  invalidation_level?: number | null;
  event_created_at: string;
  message: string;
}

export interface MWBreakoutAlert {
  alert_id: string;
  alert_type: "W_BREAKOUT_CONFIRMED" | "M_BREAKDOWN_CONFIRMED";
  pattern_type: "W" | "M";
  direction: "UP" | "DOWN";
  symbol: string;
  ticker?: string | null;
  timeframe: string;
  pattern_id: string;

  // Pattern geometry
  s1_price: number;
  s1_timestamp: string;
  s2_price: number;
  s2_timestamp: string;
  neckline_price: number;
  neckline_timestamp: string;
  pattern_height: number;

  // Breakout candle exact metrics
  breakout_candle_timestamp: string;
  breakout_open: number;
  breakout_high: number;
  breakout_low: number;
  breakout_close: number;

  // Confluence metrics
  trendline_price: number;
  ema20_price: number;
  volume: number;
  relative_volume: number;

  // Projections & Target Analysis
  measured_target: number;
  target_2?: number | null;
  nearest_support?: number | null;
  nearest_resistance?: number | null;
  invalidation_level: number;
  stop_loss?: number | null;
  quality_score: number;
  quality_breakdown?: Record<string, number>;

  // Lifecycle & status tracking
  status: "TARGET OPEN" | "TARGET 1 HIT" | "TARGET 2 HIT" | "SL HIT" | "ACTIVE" | "TARGET_1_HIT" | "TARGET_2_HIT" | "INVALIDATED" | "EXPIRED";
  event_created_at: string;
  read: boolean;
}

export interface MWBreakoutStats {
  w_breakouts: number;
  m_breakdowns: number;
  active_count: number;
  target_hit_count: number;
  invalidated_count: number;
  unread_count: number;
  total_count: number;
}

export interface BacktestRequest {
  symbol: string;
  ticker: string;
  timeframe: string;
  strategy: "BOS_CONTINUATION" | "CHOCH_REVERSAL" | "TRENDLINE_BREAKOUT" | "MULTI_TF_ALIGNMENT";
  risk_reward_ratio: number;
  stop_loss_atr_multiple: number;
  slippage_bps: number;
  fee_bps: number;
  start_period?: string;
}

export interface BacktestTrade {
  trade_id: number;
  entry_time: string;
  exit_time: string;
  direction: "LONG" | "SHORT";
  entry_price: number;
  exit_price: number;
  stop_loss: number;
  target: number;
  pnl_pct: number;
  pnl_amount: number;
  exit_reason: "TARGET" | "STOP_LOSS" | "TIME_EXIT" | "CHOCH_EXIT" | "TL_EXIT";
  mae_pct: number;
  mfe_pct: number;
  bars_held: number;
}

export interface BacktestResult {
  symbol: string;
  timeframe: string;
  strategy: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  loss_rate_pct: number;
  profit_factor: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  avg_trade_pnl_pct: number;
  avg_favorable_excursion_pct: number;
  avg_adverse_excursion_pct: number;
  trades: BacktestTrade[];
  equity_curve: { time: string; equity: number }[];
}

export interface HypotheticalSetup {
  status: string;
  symbol?: string;
  direction?: "LONG" | "SHORT";
  entry_price?: number;
  stop_loss?: number;
  target_1_rr2?: number;
  target_2_rr3?: number;
  risk_per_unit?: number;
  risk_reward_ratio?: string;
  hypothetical_quantity?: number;
  capital_at_risk?: number;
  disclaimer?: string;
  message?: string;
}

export interface PaperOrder {
  id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  entry_price: number;
  stop_loss: number;
  target: number;
  quantity: number;
  status: "PENDING" | "OPEN" | "CLOSED" | "CANCELLED";
  created_at: string;
  closed_at?: string | null;
  realized_pnl?: number | null;
  notes: string;
}

export interface TrendlineShortlistCandidate {
  id: string;
  symbol: string;
  ticker?: string | null;
  timeframe: string;
  current_price: number;
  trendline_type: "RESISTANCE_BREAKOUT" | "SUPPORT_BREAKDOWN";
  direction: "BULLISH" | "BEARISH";
  touch_count: number;
  swing_structure: string;
  structure_sequence?: string[];
  slope: number;
  intercept: number;
  trendline_price: number;
  breakout_pct: number;
  r_squared: number;
  volume_ratio?: number | null;
  trendline_score: number;
  confidence: "VERY STRONG" | "STRONG" | "VALID" | "NOT SHORTLISTED";
  breakout_time: string;
  status: "WATCHING" | "BREAKOUT" | "CONFIRMED" | "RETEST" | "FALSE BREAKOUT";
  invalidation_level?: number | null;
  target_price?: number | null;
  htf_alignment?: string | null;
  notes?: string | null;
  score_breakdown?: Record<string, number>;
  created_at?: string | null;
}
