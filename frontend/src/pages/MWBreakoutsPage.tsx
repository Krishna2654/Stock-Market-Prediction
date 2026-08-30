import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { MWBreakoutAlert, MWBreakoutStats } from '../types';
import { api } from '../services/api';
import { MWBreakoutCard } from '../components/MWBreakoutCard';
import {
  ArrowLeft,
  Filter,
  Search,
  RefreshCw,
  Volume2,
  VolumeX,
  TrendingUp,
  TrendingDown,
  Target,
  ShieldAlert,
  CheckCircle2,
  Sparkles,
  Layers,
  Clock,
  Activity,
  AlertCircle
} from 'lucide-react';

interface MWBreakoutsPageProps {
  alerts: MWBreakoutAlert[];
  soundEnabled: boolean;
  onToggleSound: () => void;
  onRefresh: () => void;
}

export const MWBreakoutsPage: React.FC<MWBreakoutsPageProps> = ({
  alerts,
  soundEnabled,
  onToggleSound,
  onRefresh
}) => {
  const navigate = useNavigate();

  // Filters State
  const [patternTypeFilter, setPatternTypeFilter] = useState<'ALL' | 'W' | 'M'>('ALL');
  const [timeframeFilter, setTimeframeFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [dateFilter, setDateFilter] = useState<'latest' | 'today' | '24h' | '7d' | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [stats, setStats] = useState<MWBreakoutStats | null>(null);

  // Dynamic Browser Page Title
  useEffect(() => {
    document.title = 'M/W Breakouts — Quantitative Pattern Confluence';
  }, []);

  // Fetch Summary Statistics
  const loadStats = async () => {
    try {
      const data = await api.getMWBreakoutStats();
      setStats(data);
    } catch (err) {
      console.warn('Failed to load M/W stats:', err);
    }
  };

  useEffect(() => {
    loadStats();
  }, [alerts]);

  // Filtered & Sorted Alerts
  const filteredAlerts = useMemo(() => {
    let result = [...alerts];

    // 1. Pattern Type Filter (W / M / ALL)
    if (patternTypeFilter !== 'ALL') {
      result = result.filter((a) => a.pattern_type === patternTypeFilter);
    }

    // 2. Timeframe Filter
    if (timeframeFilter !== 'ALL') {
      result = result.filter((a) => a.timeframe.toUpperCase() === timeframeFilter.toUpperCase());
    }

    // 3. Status Filter (TARGET OPEN / TARGET 1 HIT / TARGET 2 HIT / SL HIT / ALL)
    if (statusFilter !== 'ALL') {
      if (statusFilter === 'COMPLETED') {
        result = result.filter((a) => a.status === 'TARGET 1 HIT' || a.status === 'TARGET 2 HIT' || a.status === 'TARGET_1_HIT' || a.status === 'TARGET_2_HIT');
      } else if (statusFilter === 'TARGET OPEN' || statusFilter === 'ACTIVE') {
        result = result.filter((a) => a.status === 'TARGET OPEN' || a.status === 'ACTIVE');
      } else if (statusFilter === 'SL HIT' || statusFilter === 'INVALIDATED') {
        result = result.filter((a) => a.status === 'SL HIT' || a.status === 'INVALIDATED');
      } else if (statusFilter === 'TARGET 1 HIT') {
        result = result.filter((a) => a.status === 'TARGET 1 HIT' || a.status === 'TARGET_1_HIT');
      } else if (statusFilter === 'TARGET 2 HIT') {
        result = result.filter((a) => a.status === 'TARGET 2 HIT' || a.status === 'TARGET_2_HIT');
      } else if (statusFilter === 'FALSE BREAKOUT') {
        result = result.filter((a) => a.status === 'FALSE BREAKOUT' || (a.status as any) === 'FALSE_BREAKOUT');
      } else {
        result = result.filter((a) => a.status === statusFilter);
      }
    }

    // 4. Search Filter
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toUpperCase().replace(/[/_\-\s]/g, '');
      result = result.filter(
        (a) =>
          a.symbol.toUpperCase().replace(/[/_\-\s]/g, '').includes(q) ||
          (a.ticker && a.ticker.toUpperCase().replace(/[/_\-\s]/g, '').includes(q))
      );
    }

    // 5. Date Filter
    if (dateFilter !== 'all') {
      const now = new Date();
      if (dateFilter === 'today') {
        const todayStr = now.toISOString().slice(0, 10);
        result = result.filter((a) => a.breakout_candle_timestamp.startsWith(todayStr));
      } else if (dateFilter === '24h') {
        const cutoff = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        result = result.filter((a) => new Date(a.breakout_candle_timestamp) >= cutoff);
      } else if (dateFilter === '7d') {
        const cutoff = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        result = result.filter((a) => new Date(a.breakout_candle_timestamp) >= cutoff);
      } else if (dateFilter === 'latest') {
        result = result.slice(0, 5);
      }
    }

    // Deduplicate alerts by pattern_id or composite key
    const seen = new Set<string>();
    const deduplicated: MWBreakoutAlert[] = [];
    for (const a of result) {
      const key = a.pattern_id || `${a.symbol}_${a.timeframe}_${a.pattern_type}_${a.breakout_candle_timestamp}`;
      if (!seen.has(key) && !seen.has(a.alert_id)) {
        seen.add(key);
        seen.add(a.alert_id);
        deduplicated.push(a);
      }
    }
    result = deduplicated;

    // Sort newest first by breakout_candle_timestamp
    result.sort(
      (a, b) => new Date(b.breakout_candle_timestamp).getTime() - new Date(a.breakout_candle_timestamp).getTime()
    );

    return result;
  }, [alerts, patternTypeFilter, timeframeFilter, statusFilter, dateFilter, searchQuery]);

  const latestHeroAlert = filteredAlerts.length > 0 ? filteredAlerts[0] : null;
  const historyAlerts = filteredAlerts.length > 1 ? filteredAlerts.slice(1) : [];

  // Handle Trigger Test Breakouts
  const handleTestTrigger = async (type: 'W' | 'M') => {
    setIsLoading(true);
    try {
      await api.triggerTestMWBreakout(type);
      onRefresh();
      loadStats();
    } catch (err) {
      console.error('Test breakout error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-7xl mx-auto space-y-4 sm:space-y-6 min-w-0">
      {/* Navigation Top Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3 sm:pb-4 min-w-0">
        <div>
          <button
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1.5 sm:gap-2 min-h-[38px] sm:min-h-[44px] px-3 sm:px-3.5 py-1.5 sm:py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-bold text-xs shadow-2xs transition-all cursor-pointer"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to Market Analysis</span>
          </button>
        </div>

        {/* Action Buttons: Sound, Refresh, Developer Test */}
        <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap min-w-0">
          <button
            onClick={onToggleSound}
            className={`min-h-[36px] sm:min-h-[44px] px-2.5 sm:px-3.5 py-1.5 sm:py-2 rounded-xl border text-xs font-bold transition-all flex items-center gap-1 sm:gap-1.5 shadow-2xs cursor-pointer ${
              soundEnabled
                ? 'bg-emerald-50 text-emerald-700 border-emerald-300'
                : 'bg-slate-50 text-slate-500 border-slate-200'
            }`}
            title="Toggle M/W Breakout Audio Alert"
          >
            {soundEnabled ? <Volume2 className="h-3.5 w-3.5 sm:h-4 sm:w-4" /> : <VolumeX className="h-3.5 w-3.5 sm:h-4 sm:w-4" />}
            <span>Sound: {soundEnabled ? 'ON' : 'OFF'}</span>
          </button>

          <button
            onClick={() => {
              onRefresh();
              loadStats();
            }}
            disabled={isLoading}
            className="min-h-[36px] sm:min-h-[44px] px-2.5 sm:px-3.5 py-1.5 sm:py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold transition-all flex items-center gap-1 sm:gap-1.5 shadow-2xs cursor-pointer disabled:opacity-50"
            title="Refresh M/W Signals"
          >
            <RefreshCw className={`h-3.5 w-3.5 sm:h-4 sm:w-4 ${isLoading ? 'animate-spin text-blue-600' : ''}`} />
            <span>Refresh</span>
          </button>

          {/* Test Signal Triggers */}
          <button
            onClick={() => handleTestTrigger('W')}
            disabled={isLoading}
            className="min-h-[36px] sm:min-h-[44px] px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-xl border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-[10px] sm:text-[11px] font-bold transition-all cursor-pointer"
            title="Simulate Confirmed W Breakout Signal"
          >
            + Test W Signal
          </button>
          <button
            onClick={() => handleTestTrigger('M')}
            disabled={isLoading}
            className="min-h-[36px] sm:min-h-[44px] px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-xl border border-rose-300 bg-rose-50 hover:bg-rose-100 text-rose-800 text-[10px] sm:text-[11px] font-bold transition-all cursor-pointer"
            title="Simulate Confirmed M Breakdown Signal"
          >
            + Test M Signal
          </button>
        </div>
      </div>

      {/* Page Title & Subtitle Header */}
      <div className="space-y-1">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-purple-100 text-purple-700 border border-purple-200 shadow-xs">
            <Target className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-900">
              M/W BREAKOUTS
            </h1>
            <p className="text-xs sm:text-sm text-slate-600 font-medium">
              Confirmed W and M pattern breakout signals with strict structural swing confluence
            </p>
          </div>
        </div>
      </div>

      {/* Summary Statistics Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
        <div className="p-3.5 rounded-2xl bg-white border border-slate-200 shadow-2xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
            <TrendingUp className="h-3.5 w-3.5 text-emerald-600" />
            <span>W Breakouts</span>
          </div>
          <div className="text-xl font-black text-emerald-700 mt-1">
            {stats?.w_breakouts ?? alerts.filter((a) => a.pattern_type === 'W').length}
          </div>
        </div>

        <div className="p-3.5 rounded-2xl bg-white border border-slate-200 shadow-2xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
            <TrendingDown className="h-3.5 w-3.5 text-rose-600" />
            <span>M Breakdowns</span>
          </div>
          <div className="text-xl font-black text-rose-700 mt-1">
            {stats?.m_breakdowns ?? alerts.filter((a) => a.pattern_type === 'M').length}
          </div>
        </div>

        <div className="p-3.5 rounded-2xl bg-white border border-slate-200 shadow-2xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
            <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
            <span>Target Open</span>
          </div>
          <div className="text-xl font-black text-blue-600 mt-1">
            {stats?.active_count ?? alerts.filter((a) => a.status === 'TARGET OPEN' || a.status === 'ACTIVE').length}
          </div>
        </div>

        <div className="p-3.5 rounded-2xl bg-white border border-slate-200 shadow-2xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
            <span>Target Hit</span>
          </div>
          <div className="text-xl font-black text-emerald-600 mt-1">
            {stats?.target_hit_count ?? alerts.filter((a) => a.status === 'TARGET 1 HIT' || a.status === 'TARGET 2 HIT' || a.status === 'TARGET_1_HIT' || a.status === 'TARGET_2_HIT').length}
          </div>
        </div>

        <div className="p-3.5 rounded-2xl bg-white border border-slate-200 shadow-2xs col-span-2 sm:col-span-1">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
            <ShieldAlert className="h-3.5 w-3.5 text-rose-500" />
            <span>SL Hit</span>
          </div>
          <div className="text-xl font-black text-rose-600 mt-1">
            {stats?.invalidated_count ?? alerts.filter((a) => a.status === 'SL HIT' || a.status === 'INVALIDATED').length}
          </div>
        </div>
      </div>

      {/* Filter Control Bar (Horizontally scrollable on small mobile) */}
      <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          {/* Pattern Type Toggle: [ ALL ] [ W ] [ M ] */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl border border-slate-200">
            <button
              onClick={() => setPatternTypeFilter('ALL')}
              className={`min-h-[38px] px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                patternTypeFilter === 'ALL'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              ALL
            </button>
            <button
              onClick={() => setPatternTypeFilter('W')}
              className={`min-h-[38px] px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                patternTypeFilter === 'W'
                  ? 'bg-emerald-600 text-white shadow-xs'
                  : 'text-emerald-700 hover:bg-emerald-50'
              }`}
            >
              🟢 W BREAKOUTS
            </button>
            <button
              onClick={() => setPatternTypeFilter('M')}
              className={`min-h-[38px] px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                patternTypeFilter === 'M'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'text-rose-700 hover:bg-rose-50'
              }`}
            >
              🔴 M BREAKDOWNS
            </button>
          </div>

          {/* Timeframe Filter Dropdown */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-bold text-slate-600">Timeframe:</label>
            <select
              value={timeframeFilter}
              onChange={(e) => setTimeframeFilter(e.target.value)}
              className="min-h-[40px] px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 text-xs font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/20 cursor-pointer"
            >
              <option value="ALL">All Timeframes</option>
              <option value="4H">4H Timeframe</option>
              <option value="1H">1H Timeframe</option>
              <option value="15M">15M Timeframe</option>
              <option value="5M">5M Timeframe</option>
            </select>
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl border border-slate-200 flex-wrap">
            {[
              { id: 'ALL', label: 'ALL' },
              { id: 'TARGET OPEN', label: 'OPEN' },
              { id: 'TARGET 1 HIT', label: 'T1 HIT' },
              { id: 'TARGET 2 HIT', label: 'T2 HIT' },
              { id: 'SL HIT', label: 'SL HIT' },
              { id: 'FALSE BREAKOUT', label: 'FALSE' }
            ].map((st) => (
              <button
                key={st.id}
                onClick={() => setStatusFilter(st.id)}
                className={`min-h-[38px] px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  statusFilter === st.id
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {st.label}
              </button>
            ))}
          </div>
        </div>

        {/* Date Filter & Search Row */}
        <div className="flex items-center justify-between gap-3 pt-2 border-t border-slate-100 flex-wrap">
          {/* Date Filter Pills */}
          <div className="flex items-center gap-1.5 overflow-x-auto py-1 max-w-full">
            <span className="text-xs font-bold text-slate-500 whitespace-nowrap mr-1">Period:</span>
            {[
              { key: 'all', label: 'All History' },
              { key: 'latest', label: 'Latest 5' },
              { key: 'today', label: 'Today' },
              { key: '24h', label: 'Last 24h' },
              { key: '7d', label: 'Last 7d' }
            ].map((p) => (
              <button
                key={p.key}
                onClick={() => setDateFilter(p.key as any)}
                className={`min-h-[36px] px-3 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  dateFilter === p.key
                    ? 'bg-blue-600 text-white shadow-2xs font-bold'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Symbol Search Bar */}
          <div className="relative min-w-[220px] flex-1 sm:flex-none">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search symbol (e.g. NIFTY, BANK NIFTY)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full min-h-[40px] pl-9 pr-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {filteredAlerts.length === 0 ? (
        /* Empty State (Zero Fake Data) */
        <div className="p-8 sm:p-12 rounded-3xl bg-white border border-slate-200 shadow-sm text-center space-y-4 max-w-2xl mx-auto my-8">
          <div className="h-16 w-16 rounded-2xl bg-purple-50 text-purple-600 border border-purple-200 flex items-center justify-center mx-auto shadow-xs">
            <Target className="h-8 w-8" />
          </div>
          <div className="space-y-1">
            <h3 className="text-lg sm:text-xl font-extrabold text-slate-900">
              NO CONFIRMED M/W BREAKOUTS
            </h3>
            <p className="text-xs sm:text-sm text-slate-500 max-w-md mx-auto">
              Waiting for a valid pattern and confirmed candle close from the live market data stream.
            </p>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 text-left text-xs text-slate-700 space-y-2 max-w-md mx-auto">
            <div className="font-bold text-slate-900 border-b border-slate-200 pb-1 flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4 text-purple-600" />
              <span>Strict Confluence Criteria Required:</span>
            </div>
            <ul className="space-y-1.5 text-[11px] text-slate-600">
              <li className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-purple-500" />
                <span>Structural Swing Point Sequence (H1-L-H2 or L1-H-L2)</span>
              </li>
              <li className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-purple-500" />
                <span>Pattern Depth ≥ 0.80× ATR & Separation (5 to 60 bars)</span>
              </li>
              <li className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-purple-500" />
                <span>Completed Candle Close beyond Neckline</span>
              </li>
              <li className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-purple-500" />
                <span>Trendline & 20 EMA Confluence on the same breakout candle</span>
              </li>
            </ul>
          </div>
        </div>
      ) : (
        <div className="space-y-8">
          {/* LATEST CONFIRMED BREAKOUT (Hero Section) */}
          {latestHeroAlert && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-900 uppercase tracking-wider">
                <Sparkles className="h-4 w-4 text-amber-500" />
                <span>LATEST CONFIRMED BREAKOUT</span>
              </div>
              <MWBreakoutCard alert={latestHeroAlert} isHero={true} />
            </div>
          )}

          {/* BREAKOUT HISTORY GRID */}
          {historyAlerts.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-bold text-slate-900 uppercase tracking-wider">
                  <Clock className="h-4 w-4 text-blue-600" />
                  <span>BREAKOUT HISTORY ({historyAlerts.length})</span>
                </div>
              </div>

              {/* 3 columns on Desktop, 2 on Tablet, 1 on Mobile */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {historyAlerts.map((alert) => (
                  <MWBreakoutCard key={alert.alert_id} alert={alert} isHero={false} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
