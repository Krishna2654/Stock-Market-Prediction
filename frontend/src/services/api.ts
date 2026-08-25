import {
  MultiTimeframeSynthesis,
  AIAnalysisSummary,
  InstrumentConfig,
  AlertRule,
  AlertNotification,
  HighConfluenceAlert,
  MWBreakoutAlert,
  MWBreakoutStats,
  BacktestRequest,
  BacktestResult,
  HypotheticalSetup,
  PaperOrder
} from '../types';

const API_BASE = '/api';

export const api = {
  // Instruments
  getInstruments: async (): Promise<InstrumentConfig[]> => {
    const res = await fetch(`${API_BASE}/instruments/`);
    if (!res.ok) throw new Error('Failed to fetch instruments');
    return res.json();
  },

  addInstrument: async (inst: Partial<InstrumentConfig>): Promise<InstrumentConfig> => {
    const res = await fetch(`${API_BASE}/instruments/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(inst)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to add instrument');
    }
    return res.json();
  },

  deleteInstrument: async (symbol: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/instruments/${encodeURIComponent(symbol)}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to delete instrument');
  },

  getProviderStatus: async (): Promise<{ current_provider: string; available_providers: string[] }> => {
    const res = await fetch(`${API_BASE}/instruments/provider`);
    if (!res.ok) throw new Error('Failed to fetch provider status');
    return res.json();
  },

  setProvider: async (providerName: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/instruments/provider/${encodeURIComponent(providerName)}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to switch provider');
  },

  // Analysis
  getOverview: async (): Promise<MultiTimeframeSynthesis[]> => {
    const res = await fetch(`${API_BASE}/analysis/overview`);
    if (!res.ok) throw new Error('Failed to fetch market overview');
    return res.json();
  },

  getInstrumentDetail: async (symbol: string): Promise<MultiTimeframeSynthesis> => {
    const res = await fetch(`${API_BASE}/analysis/detail/${encodeURIComponent(symbol)}`);
    if (!res.ok) throw new Error(`Failed to fetch analysis for ${symbol}`);
    return res.json();
  },

  getChartData: async (symbol: string, timeframe: string = '15M', limit: number = 250): Promise<any> => {
    const res = await fetch(`${API_BASE}/analysis/chart/${encodeURIComponent(symbol)}?timeframe=${timeframe}&limit=${limit}`);
    if (!res.ok) throw new Error(`Failed to fetch chart data for ${symbol} on ${timeframe}`);
    return res.json();
  },

  // AI Summary
  generateAISummary: async (symbol: string, apiKey?: string): Promise<AIAnalysisSummary> => {
    const res = await fetch(`${API_BASE}/ai/summary/${encodeURIComponent(symbol)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey || '' })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to generate AI summary');
    }
    return res.json();
  },

  // Alerts
  getAlertRules: async (): Promise<AlertRule[]> => {
    const res = await fetch(`${API_BASE}/alerts/rules`);
    if (!res.ok) throw new Error('Failed to fetch alert rules');
    return res.json();
  },

  createAlertRule: async (rule: Partial<AlertRule>): Promise<AlertRule> => {
    const res = await fetch(`${API_BASE}/alerts/rules`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(rule)
    });
    if (!res.ok) throw new Error('Failed to create alert rule');
    return res.json();
  },

  deleteAlertRule: async (ruleId: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/alerts/rules/${ruleId}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to delete alert rule');
  },

  getNotifications: async (limit: number = 50): Promise<AlertNotification[]> => {
    const res = await fetch(`${API_BASE}/alerts/notifications?limit=${limit}`);
    if (!res.ok) throw new Error('Failed to fetch notifications');
    return res.json();
  },

  clearNotifications: async (): Promise<void> => {
    const res = await fetch(`${API_BASE}/alerts/clear`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to clear notifications');
  },

  triggerTestAlert: async (): Promise<AlertNotification> => {
    const res = await fetch(`${API_BASE}/alerts/test`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to trigger test alert');
    return res.json();
  },

  // High-Confluence Breakout Alerts (Separate API)
  getHighConfluenceAlerts: async (symbol?: string, limit: number = 30): Promise<HighConfluenceAlert[]> => {
    const query = new URLSearchParams();
    if (symbol) query.append('symbol', symbol);
    if (limit) query.append('limit', limit.toString());
    const res = await fetch(`${API_BASE}/alerts/high-confluence?${query.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch high-confluence alerts');
    return res.json();
  },

  clearHighConfluenceAlerts: async (): Promise<void> => {
    const res = await fetch(`${API_BASE}/alerts/high-confluence/clear`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to clear high-confluence alerts');
  },

  triggerTestHighConfluenceAlert: async (alertType: string = 'TRENDLINE_EMA_VOLUME_UP_BREAKOUT'): Promise<HighConfluenceAlert> => {
    const res = await fetch(`${API_BASE}/alerts/high-confluence/test?alert_type=${alertType}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to trigger test high-confluence alert');
    return res.json();
  },

  // Dedicated M/W Breakout Page APIs
  getMWBreakouts: async (filters?: {
    symbol?: string;
    timeframe?: string;
    pattern_type?: string;
    status?: string;
    date_filter?: string;
    limit?: number;
  }): Promise<MWBreakoutAlert[]> => {
    const query = new URLSearchParams();
    if (filters?.symbol) query.append('symbol', filters.symbol);
    if (filters?.timeframe) query.append('timeframe', filters.timeframe);
    if (filters?.pattern_type) query.append('pattern_type', filters.pattern_type);
    if (filters?.status) query.append('status', filters.status);
    if (filters?.date_filter) query.append('date_filter', filters.date_filter);
    if (filters?.limit) query.append('limit', filters.limit.toString());
    const res = await fetch(`${API_BASE}/alerts/mw-breakouts?${query.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch M/W breakouts');
    return res.json();
  },

  getMWBreakoutStats: async (): Promise<MWBreakoutStats> => {
    const res = await fetch(`${API_BASE}/alerts/mw-breakouts/stats`);
    if (!res.ok) throw new Error('Failed to fetch M/W breakout stats');
    return res.json();
  },

  getMWBreakoutDetail: async (alertId: string): Promise<MWBreakoutAlert> => {
    const res = await fetch(`${API_BASE}/alerts/mw-breakouts/${encodeURIComponent(alertId)}`);
    if (!res.ok) throw new Error('Failed to fetch M/W breakout detail');
    return res.json();
  },

  markAllMWBreakoutsRead: async (): Promise<void> => {
    const res = await fetch(`${API_BASE}/alerts/mw-breakouts/read-all`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to mark M/W breakouts read');
  },

  clearMWBreakouts: async (): Promise<void> => {
    const res = await fetch(`${API_BASE}/alerts/mw-breakouts/clear`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to clear M/W breakouts');
  },

  triggerTestMWBreakout: async (patternType: 'W' | 'M' = 'W'): Promise<MWBreakoutAlert> => {
    const res = await fetch(`${API_BASE}/alerts/mw-breakouts/test?pattern_type=${patternType}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to trigger test M/W breakout');
    return res.json();
  },

  // Backtest
  runBacktest: async (req: BacktestRequest): Promise<BacktestResult> => {
    const res = await fetch(`${API_BASE}/backtest/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Backtest failed');
    }
    return res.json();
  },

  // Paper Trading
  getHypotheticalSetup: async (symbol: string, accountSize: number = 100000, riskPct: number = 1.0): Promise<HypotheticalSetup> => {
    const res = await fetch(`${API_BASE}/paper/setup/${encodeURIComponent(symbol)}?account_size=${accountSize}&risk_pct=${riskPct}`);
    if (!res.ok) throw new Error('Failed to get hypothetical setup');
    return res.json();
  },

  getPaperOrders: async (): Promise<PaperOrder[]> => {
    const res = await fetch(`${API_BASE}/paper/orders`);
    if (!res.ok) throw new Error('Failed to fetch paper orders');
    return res.json();
  },

  placePaperOrder: async (order: {
    symbol: string;
    direction: string;
    entry_price: number;
    stop_loss: number;
    target: number;
    quantity: number;
    notes?: string;
  }): Promise<PaperOrder> => {
    const res = await fetch(`${API_BASE}/paper/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(order)
    });
    if (!res.ok) throw new Error('Failed to place paper order');
    return res.json();
  }
};
