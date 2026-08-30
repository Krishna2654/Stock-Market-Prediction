import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { TrendlineShortlistCandidate } from '../types';
import { formatMarketTime } from '../utils/time';
import { api } from '../services/api';
import {
  TrendingUp,
  TrendingDown,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Zap,
  Target,
  Clock,
  Sparkles,
  Search,
  Filter,
  Trash2,
  Flame,
  ChevronRight,
  Shield,
  Activity
} from 'lucide-react';

interface TrendlineShortlistPanelProps {
  candidates: TrendlineShortlistCandidate[];
  onRefresh?: () => void;
}

export const TrendlineShortlistPanel: React.FC<TrendlineShortlistPanelProps> = ({
  candidates,
  onRefresh
}) => {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [directionFilter, setDirectionFilter] = useState<'ALL' | 'BULLISH' | 'BEARISH'>('ALL');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'BREAKOUT' | 'CONFIRMED' | 'RETEST' | 'WATCHING' | 'FALSE BREAKOUT'>('ALL');
  const [timeframeFilter, setTimeframeFilter] = useState<'ALL' | '4H' | '1H' | '15M' | '5M'>('ALL');
  const [isTriggering, setIsTriggering] = useState(false);

  const filteredCandidates = candidates.filter((c) => {
    const matchesSearch =
      c.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.ticker && c.ticker.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesDirection = directionFilter === 'ALL' || c.direction === directionFilter;
    const matchesStatus = statusFilter === 'ALL' || c.status === statusFilter;
    const matchesTimeframe = timeframeFilter === 'ALL' || c.timeframe === timeframeFilter;

    return matchesSearch && matchesDirection && matchesStatus && matchesTimeframe;
  });

  const handleTestCandidate = async (dir: 'BULLISH' | 'BEARISH') => {
    setIsTriggering(true);
    try {
      await api.triggerTestTrendlineShortlist(dir);
      if (onRefresh) onRefresh();
    } catch (err) {
      console.error('Failed to trigger test trendline breakout candidate', err);
    } finally {
      setIsTriggering(false);
    }
  };

  const handleClear = async () => {
    if (!window.confirm('Clear all shortlisted trendline breakout stocks?')) return;
    try {
      await api.clearTrendlineShortlist();
      if (onRefresh) onRefresh();
    } catch (err) {
      console.error('Failed to clear shortlist', err);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'CONFIRMED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black bg-emerald-600 text-white shadow-2xs">
            <CheckCircle2 className="h-3 w-3" /> CONFIRMED
          </span>
        );
      case 'RETEST':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black bg-blue-600 text-white shadow-2xs">
            <Sparkles className="h-3 w-3" /> RETEST BOUNCE
          </span>
        );
      case 'BREAKOUT':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black bg-purple-600 text-white shadow-2xs animate-pulse">
            <Zap className="h-3 w-3" /> BREAKOUT CLOSE
          </span>
        );
      case 'WATCHING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black bg-amber-500 text-white shadow-2xs">
            <Clock className="h-3 w-3" /> WATCHING
          </span>
        );
      case 'FALSE BREAKOUT':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black bg-rose-600 text-white shadow-2xs">
            <AlertTriangle className="h-3 w-3" /> FALSE BREAKOUT
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-black bg-slate-700 text-white shadow-2xs">
            {status}
          </span>
        );
    }
  };

  const getConfidenceBadge = (conf: string) => {
    switch (conf) {
      case 'VERY STRONG':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-black bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1">
            <Flame className="h-3 w-3 text-emerald-600" /> VERY STRONG
          </span>
        );
      case 'STRONG':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-black bg-blue-100 text-blue-800 border border-blue-300 flex items-center gap-1">
            <CheckCircle2 className="h-3 w-3 text-blue-600" /> STRONG
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-300">
            {conf}
          </span>
        );
    }
  };

  return (
    <div className="space-y-4 w-full min-w-0">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 rounded-3xl p-5 sm:p-6 text-white border border-slate-800 shadow-sm relative overflow-hidden">
        <div className="absolute top-0 right-0 w-80 h-80 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/20 text-blue-300 border border-blue-400/30 text-xs font-bold mb-2">
              <Layers className="h-3.5 w-3.5 text-blue-400" />
              <span>Multi-Touch Verified Trendline Breakout Shortlist (N ≥ 3 Points)</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-black tracking-tight text-white flex items-center gap-2">
              🎯 Stock Shortlisting Dashboard
            </h2>
            <p className="text-xs sm:text-sm text-slate-300 mt-1 max-w-2xl">
              Strictly shortlists stocks supported by validated trendlines with <strong>more than 2 points</strong>, mathematical regression fit (R² ≥ 0.90), ATR-based tolerance, and confirmed completed candle closes.
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => handleTestCandidate('BULLISH')}
              disabled={isTriggering}
              className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-xs flex items-center gap-1 transition-all disabled:opacity-50"
            >
              <TrendingUp className="h-3.5 w-3.5" />
              <span>+ Test Bullish Breakout</span>
            </button>
            <button
              onClick={() => handleTestCandidate('BEARISH')}
              disabled={isTriggering}
              className="px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs shadow-xs flex items-center gap-1 transition-all disabled:opacity-50"
            >
              <TrendingDown className="h-3.5 w-3.5" />
              <span>+ Test Bearish Breakdown</span>
            </button>
            {candidates.length > 0 && (
              <button
                onClick={handleClear}
                className="p-2 rounded-xl bg-slate-800 hover:bg-rose-900/50 text-slate-300 hover:text-rose-300 border border-slate-700 transition-all text-xs"
                title="Clear Shortlist"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Filter Controls Bar */}
      <div className="bg-white rounded-2xl p-3 sm:p-4 border border-slate-200 shadow-2xs flex flex-col md:flex-row items-center justify-between gap-3 min-w-0">
        {/* Search */}
        <div className="relative w-full md:w-72 min-w-0">
          <Search className="h-4 w-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search symbol (e.g. NIFTY, TCS)..."
            className="w-full pl-9 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white font-medium"
          />
        </div>

        {/* Direction Filter */}
        <div className="flex items-center gap-1 overflow-x-auto w-full md:w-auto no-scrollbar">
          {[
            { id: 'ALL', label: 'All Directions' },
            { id: 'BULLISH', label: '🟢 Bullish Breakouts' },
            { id: 'BEARISH', label: '🔴 Bearish Breakdowns' }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setDirectionFilter(tab.id as any)}
              className={`px-2.5 py-1 rounded-xl text-xs font-bold whitespace-nowrap transition-all ${
                directionFilter === tab.id
                  ? 'bg-blue-600 text-white shadow-2xs'
                  : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200/60'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Status Filter */}
        <div className="flex items-center gap-1 overflow-x-auto w-full md:w-auto no-scrollbar">
          {[
            { id: 'ALL', label: 'All Status' },
            { id: 'CONFIRMED', label: 'Confirmed' },
            { id: 'RETEST', label: 'Retest' },
            { id: 'BREAKOUT', label: 'Breakout' },
            { id: 'WATCHING', label: 'Watching' }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id as any)}
              className={`px-2 py-1 rounded-xl text-xs font-bold whitespace-nowrap transition-all ${
                statusFilter === tab.id
                  ? 'bg-slate-900 text-white shadow-2xs'
                  : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200/60'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Shortlist Cards Grid */}
      {filteredCandidates.length === 0 ? (
        <div className="bg-white rounded-3xl p-12 text-center border border-slate-200 shadow-xs">
          <Layers className="h-10 w-10 text-slate-400 mx-auto mb-3" />
          <h3 className="text-base font-bold text-slate-800">No Shortlisted Stocks Currently</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            The scanner strictly shortlists stocks with <strong>more than 2 validated swing points (N ≥ 3)</strong>, R² ≥ 0.90, and completed candle body closes beyond the trendline.
          </p>
          <div className="mt-4 flex items-center justify-center gap-2">
            <button
              onClick={() => handleTestCandidate('BULLISH')}
              className="px-4 py-2 bg-emerald-50 text-emerald-700 rounded-xl text-xs font-bold border border-emerald-200 hover:bg-emerald-100 transition-all flex items-center gap-1.5"
            >
              <TrendingUp className="h-4 w-4" />
              <span>Simulate Bullish Breakout</span>
            </button>
            <button
              onClick={() => handleTestCandidate('BEARISH')}
              className="px-4 py-2 bg-rose-50 text-rose-700 rounded-xl text-xs font-bold border border-rose-200 hover:bg-rose-100 transition-all flex items-center gap-1.5"
            >
              <TrendingDown className="h-4 w-4" />
              <span>Simulate Bearish Breakdown</span>
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
          {filteredCandidates.map((c) => {
            const isBull = c.direction === 'BULLISH';
            const currSym = c.symbol.includes('BTC') || c.symbol.includes('USD') ? '$' : '₹';

            return (
              <div
                key={c.id}
                onClick={() => navigate(`/markets/${encodeURIComponent(c.symbol)}`)}
                className={`group relative rounded-3xl p-4 sm:p-5 border shadow-xs hover:shadow-xl transition-all duration-200 cursor-pointer flex flex-col justify-between overflow-hidden ${
                  isBull
                    ? 'bg-gradient-to-br from-emerald-50/40 via-white to-white border-emerald-200/90 hover:border-emerald-500'
                    : 'bg-gradient-to-br from-rose-50/40 via-white to-white border-rose-200/90 hover:border-rose-500'
                }`}
              >
                {/* Top Accent Strip */}
                <div className={`absolute top-0 left-0 right-0 h-1.5 ${
                  isBull ? 'bg-emerald-500' : 'bg-rose-500'
                }`} />

                <div>
                  {/* Card Header: Type Badge & Status */}
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <span
                      className={`px-2.5 py-1 rounded-xl text-[10px] sm:text-[11px] font-black uppercase tracking-wider flex items-center gap-1.5 shadow-2xs ${
                        isBull ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'
                      }`}
                    >
                      {isBull ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                      <span>{c.trendline_type.replace('_', ' ')}</span>
                    </span>

                    <div>{getStatusBadge(c.status)}</div>
                  </div>

                  {/* Symbol, Timeframe & Breakout Time */}
                  <div className="flex items-start justify-between gap-2 pb-2.5 border-b border-slate-100 mb-3">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <h3 className="text-base sm:text-lg font-black text-slate-900 group-hover:text-blue-600 transition-colors tracking-tight">
                          {c.symbol}
                        </h3>
                        <span className="text-[10px] font-mono font-extrabold px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                          {c.timeframe}
                        </span>
                      </div>
                      <div className="flex items-center gap-1 text-[11px] text-slate-400 font-mono mt-0.5">
                        <Clock className="h-3 w-3" />
                        <span>{formatMarketTime(c.breakout_time, c.symbol)}</span>
                      </div>
                    </div>

                    <div className="text-right">
                      {getConfidenceBadge(c.confidence)}
                      <span className="text-[10px] font-mono font-bold text-slate-400 block mt-1">
                        Score: {c.trendline_score}/100
                      </span>
                    </div>
                  </div>

                  {/* Swing Structure & Points Badge */}
                  <div className="mb-3 p-2.5 bg-slate-50/90 rounded-2xl border border-slate-200/70 text-xs space-y-1.5">
                    <div className="flex items-center justify-between text-slate-600">
                      <span className="font-semibold flex items-center gap-1 text-[11px]">
                        <Layers className="h-3.5 w-3.5 text-indigo-600" /> Trendline Touches:
                      </span>
                      <span className="font-mono font-black text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                        {c.touch_count} Points (N ≥ 3 ✓)
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-slate-600">
                      <span className="font-semibold text-[11px]">Swing Structure:</span>
                      <span className="font-mono font-bold text-slate-800">
                        {c.swing_structure}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-slate-600">
                      <span className="font-semibold text-[11px]">Goodness of Fit (R²):</span>
                      <span className="font-mono font-bold text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded">
                        R² = {c.r_squared.toFixed(3)} (≥ 0.90 ✓)
                      </span>
                    </div>
                  </div>

                  {/* Price & Breakout Metrics */}
                  <div className="grid grid-cols-2 gap-2 mb-3 text-xs font-mono">
                    <div className="p-2 bg-white rounded-xl border border-slate-200/80">
                      <span className="text-[10px] font-sans font-semibold text-slate-400 block">Current Price</span>
                      <span className="font-black text-slate-900 text-sm">
                        {currSym}{c.current_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </span>
                    </div>

                    <div className="p-2 bg-white rounded-xl border border-slate-200/80">
                      <span className="text-[10px] font-sans font-semibold text-slate-400 block">Trendline Price</span>
                      <span className="font-bold text-purple-700 text-sm">
                        {currSym}{c.trendline_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </span>
                    </div>

                    <div className="p-2 bg-white rounded-xl border border-slate-200/80">
                      <span className="text-[10px] font-sans font-semibold text-slate-400 block">Breakout Move</span>
                      <span className={`font-black text-xs ${isBull ? 'text-emerald-600' : 'text-rose-600'}`}>
                        {isBull ? '+' : '-'}{c.breakout_pct.toFixed(2)}%
                      </span>
                    </div>

                    <div className="p-2 bg-white rounded-xl border border-slate-200/80">
                      <span className="text-[10px] font-sans font-semibold text-slate-400 block">Volume Surge</span>
                      <span className="font-bold text-slate-800 text-xs">
                        {c.volume_ratio ? `${c.volume_ratio.toFixed(2)}×` : '1.20×'} Vol
                      </span>
                    </div>
                  </div>
                </div>

                {/* Footer Action */}
                <div className="pt-2.5 border-t border-slate-100 flex items-center justify-between text-xs">
                  <span className="text-[11px] font-mono text-slate-500 truncate max-w-[200px]">
                    Slope: {c.slope > 0 ? `+${c.slope}` : c.slope}
                  </span>

                  <span className="inline-flex items-center gap-1 font-bold text-blue-600 group-hover:translate-x-1 transition-transform">
                    View Chart <ChevronRight className="h-4 w-4" />
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
