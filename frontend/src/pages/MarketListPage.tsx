import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  InstrumentConfig,
  MultiTimeframeSynthesis
} from '../types';
import {
  TrendingUp,
  Search,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Radio,
  Zap,
  Shield,
  Layers,
  ChevronRight,
  Sparkles,
  Activity
} from 'lucide-react';

interface MarketListPageProps {
  instruments: InstrumentConfig[];
  syntheses: Record<string, MultiTimeframeSynthesis>;
  isLoading: boolean;
  onRefresh: () => void;
  onOpenManageModal: () => void;
}

export const MarketListPage: React.FC<MarketListPageProps> = ({
  instruments,
  syntheses,
  isLoading,
  onRefresh,
  onOpenManageModal
}) => {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [assetFilter, setAssetFilter] = useState<'ALL' | 'INDEX' | 'EQUITY' | 'CRYPTO'>('ALL');
  const [biasFilter, setBiasFilter] = useState<'ALL' | 'BULLISH' | 'BEARISH' | 'NEUTRAL'>('ALL');

  // Set document title
  React.useEffect(() => {
    document.title = 'AI Market Analyzer — Markets';
  }, []);

  // Filtered market list
  const filteredInstruments = useMemo(() => {
    return instruments.filter((inst) => {
      const synth = syntheses[inst.symbol];
      const matchesSearch =
        inst.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
        inst.ticker.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesAsset =
        assetFilter === 'ALL' ||
        (assetFilter === 'CRYPTO' && (inst.asset_type === 'CRYPTO' || inst.symbol.includes('BTC') || inst.symbol.includes('USD'))) ||
        inst.asset_type === assetFilter;

      const matchesBias =
        biasFilter === 'ALL' ||
        (synth && synth.overall_bias === biasFilter);

      return matchesSearch && matchesAsset && matchesBias;
    });
  }, [instruments, syntheses, searchQuery, assetFilter, biasFilter]);

  // Aggregate Metrics
  const stats = useMemo(() => {
    const list = Object.values(syntheses);
    const bullishCount = list.filter((s) => s.overall_bias === 'BULLISH').length;
    const bearishCount = list.filter((s) => s.overall_bias === 'BEARISH').length;
    const neutralCount = list.length - bullishCount - bearishCount;
    return { total: instruments.length, bullishCount, bearishCount, neutralCount };
  }, [syntheses, instruments]);

  const handleSelectMarket = (symbol: string) => {
    navigate(`/markets/${encodeURIComponent(symbol)}`);
  };

  return (
    <div className="space-y-4 sm:space-y-6 pb-12 w-full max-w-full min-w-0">
      {/* Executive Header Banner */}
      <div className="bg-white rounded-3xl p-4 sm:p-8 border border-slate-200 shadow-xs relative overflow-hidden w-full min-w-0">
        <div className="absolute -top-24 -right-24 w-96 h-96 bg-blue-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4 sm:gap-6 min-w-0">
          <div className="min-w-0">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-50 border border-blue-200 text-blue-700 text-xs font-bold mb-2 sm:mb-3">
              <Sparkles className="h-3.5 w-3.5 text-blue-600" />
              <span>Multi-Timeframe Market Structure Intelligence</span>
            </div>
            <h1 className="text-xl sm:text-3xl font-black text-slate-900 tracking-tight truncate">
              Market Selection Dashboard
            </h1>
            <p className="text-xs sm:text-sm text-slate-600 mt-1 max-w-2xl">
              Select an instrument below to launch its focused, real-time quantitative analysis page with dynamic trendlines, confirmed candle-close breakouts, and scenario forecasting.
            </p>
          </div>

          {/* Quick Metrics Bar */}
          <div className="flex items-center gap-2 sm:gap-3 self-start md:self-auto flex-wrap min-w-0">
            <div className="bg-slate-50 px-3 sm:px-4 py-2 sm:py-2.5 rounded-2xl border border-slate-200 text-center">
              <span className="text-[9px] sm:text-[10px] text-slate-500 font-bold uppercase block">Tracked</span>
              <span className="text-lg sm:text-xl font-black text-slate-900 font-mono">{stats.total}</span>
            </div>
            <div className="bg-emerald-50 px-3 sm:px-4 py-2 sm:py-2.5 rounded-2xl border border-emerald-200 text-center">
              <span className="text-[9px] sm:text-[10px] text-emerald-700 font-bold uppercase block">Bullish</span>
              <span className="text-lg sm:text-xl font-black text-emerald-700 font-mono">{stats.bullishCount}</span>
            </div>
            <div className="bg-rose-50 px-3 sm:px-4 py-2 sm:py-2.5 rounded-2xl border border-rose-200 text-center">
              <span className="text-[9px] sm:text-[10px] text-rose-700 font-bold uppercase block">Bearish</span>
              <span className="text-lg sm:text-xl font-black text-rose-700 font-mono">{stats.bearishCount}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Search & Filter Controls */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-3 rounded-2xl border border-slate-200 shadow-xs w-full min-w-0">
        {/* Search Bar */}
        <div className="relative w-full sm:w-80 min-w-0">
          <Search className="h-4 w-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search market (e.g. NIFTY, BTC, RELIANCE)..."
            className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all font-medium"
          />
        </div>

        {/* Asset Type Filter Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto w-full sm:w-auto self-stretch sm:self-auto py-1 no-scrollbar min-w-0">
          {[
            { id: 'ALL', label: 'All Markets' },
            { id: 'INDEX', label: 'Indices' },
            { id: 'EQUITY', label: 'Equities' },
            { id: 'CRYPTO', label: 'Crypto (24/7)' }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setAssetFilter(tab.id as any)}
              className={`px-2.5 sm:px-3 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all ${
                assetFilter === tab.id
                  ? 'bg-blue-600 text-white shadow-2xs'
                  : 'bg-slate-50 text-slate-600 hover:bg-slate-100 hover:text-slate-900 border border-slate-200/60'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Bias Filter Pills */}
        <div className="flex items-center gap-1 overflow-x-auto w-full sm:w-auto no-scrollbar min-w-0">
          {[
            { id: 'ALL', label: 'All Biases' },
            { id: 'BULLISH', label: '🟢 Bullish' },
            { id: 'BEARISH', label: '🔴 Bearish' }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setBiasFilter(tab.id as any)}
              className={`px-2 sm:px-2.5 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all ${
                biasFilter === tab.id
                  ? 'bg-slate-900 text-white shadow-2xs'
                  : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200/60'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Market Cards Grid */}
      {filteredInstruments.length === 0 ? (
        <div className="bg-white rounded-3xl p-12 text-center border border-slate-200 shadow-xs">
          <Layers className="h-10 w-10 text-slate-400 mx-auto mb-3" />
          <h3 className="text-base font-bold text-slate-800">No matching markets found</h3>
          <p className="text-xs text-slate-500 mt-1">
            Try adjusting your search query or reset the filters.
          </p>
          <button
            onClick={() => {
              setSearchQuery('');
              setAssetFilter('ALL');
              setBiasFilter('ALL');
            }}
            className="mt-4 px-4 py-2 bg-blue-50 text-blue-700 rounded-xl text-xs font-bold border border-blue-200 hover:bg-blue-100 transition-all"
          >
            Reset Filters
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredInstruments.map((inst) => {
            const synth = syntheses[inst.symbol];
            const isCrypto = inst.symbol.includes('BTC') || inst.symbol.includes('USD') || inst.asset_type === 'CRYPTO';
            const currSym = isCrypto ? '$' : '₹';

            const price = synth?.current_price || 0;
            const bias = synth?.overall_bias || 'NEUTRAL';
            const score = synth?.evidence_score?.total_score ?? 50;
            const dataStatus = synth?.data_status || 'LIVE';
            const session = synth?.market_session;

            // Bias color schemes
            const isBull = bias === 'BULLISH';
            const isBear = bias === 'BEARISH';

            const latestEvent = synth?.latest_important_event;

            return (
              <div
                key={inst.symbol}
                onClick={() => handleSelectMarket(inst.symbol)}
                className="group relative bg-white rounded-3xl p-5 border border-slate-200 shadow-xs hover:shadow-xl hover:border-blue-500/60 transition-all duration-200 cursor-pointer flex flex-col justify-between overflow-hidden"
              >
                {/* Top Accent line on hover */}
                <div className={`absolute top-0 left-0 right-0 h-1.5 transition-colors ${
                  isBull ? 'bg-emerald-500' : isBear ? 'bg-rose-500' : 'bg-slate-300'
                }`} />

                <div>
                  {/* Card Header: Symbol & Badges */}
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-lg font-black text-slate-900 group-hover:text-blue-600 transition-colors tracking-tight">
                          {inst.symbol}
                        </h2>
                        <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                          {inst.ticker}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider block mt-0.5">
                        {inst.exchange} • {inst.asset_type}
                      </span>
                    </div>

                    <div className="flex flex-col items-end gap-1">
                      {/* Live Market Session Dot */}
                      {session && (
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border flex items-center gap-1 ${
                          session.is_running
                            ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                            : 'bg-slate-100 text-slate-600 border-slate-300'
                        }`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${session.is_running ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} />
                          {session.status}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Price & Trend Status */}
                  <div className="bg-slate-50/80 rounded-2xl p-3.5 border border-slate-100 mb-3 flex items-center justify-between">
                    <div>
                      <span className="text-[10px] text-slate-500 font-bold uppercase block">Current Price</span>
                      <span className="text-xl font-black font-mono text-slate-900 tracking-tight">
                        {price > 0
                          ? `${currSym}${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : 'Loading...'}
                      </span>
                    </div>

                    <div className="text-right">
                      <span className="text-[10px] text-slate-500 font-bold uppercase block">Overall Bias</span>
                      <span className={`inline-flex items-center gap-1 text-xs font-black px-2.5 py-1 rounded-xl border ${
                        isBull
                          ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
                          : isBear
                          ? 'bg-rose-100 text-rose-800 border-rose-300'
                          : 'bg-slate-200 text-slate-800 border-slate-300'
                      }`}>
                        {isBull ? <ArrowUpRight className="h-3.5 w-3.5" /> : isBear ? <ArrowDownRight className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
                        {bias}
                      </span>
                    </div>
                  </div>

                  {/* Multi-Timeframe Alignment Preview */}
                  {synth?.timeframes && (
                    <div className="grid grid-cols-4 gap-1.5 mb-3 text-center">
                      {(['4H', '1H', '15M', '5M'] as const).map((tf) => {
                        const tfData = synth.timeframes[tf];
                        const tfTrend = tfData?.trend || 'NEUTRAL';
                        const isTfBull = tfTrend.includes('BULL');
                        const isTfBear = tfTrend.includes('BEAR');
                        return (
                          <div
                            key={tf}
                            className={`py-1 px-1.5 rounded-lg border text-[10px] font-bold ${
                              isTfBull
                                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                : isTfBear
                                ? 'bg-rose-50 text-rose-700 border-rose-200'
                                : 'bg-slate-50 text-slate-600 border-slate-200'
                            }`}
                          >
                            <span className="text-slate-400 block text-[8px] font-mono">{tf}</span>
                            <span>{isTfBull ? 'BULL' : isTfBear ? 'BEAR' : 'NEUT'}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Latest Event Pill */}
                  <div className="text-[11px] text-slate-600 mb-3 flex items-center gap-1.5 truncate">
                    <Zap className="h-3.5 w-3.5 text-blue-600 shrink-0" />
                    <span className="truncate">
                      {latestEvent
                        ? `${latestEvent.timeframe} ${latestEvent.event_type.replace(/_/g, ' ')} (${currSym}${latestEvent.broken_level.toFixed(1)})`
                        : 'Holding confirmed structural levels'}
                    </span>
                  </div>
                </div>

                {/* Card Footer Action */}
                <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500">
                    <span className="font-bold text-blue-600">Score: {score}/100</span>
                  </div>

                  <span className="inline-flex items-center gap-1 text-xs font-bold text-blue-600 group-hover:translate-x-1 transition-transform">
                    Analyze Market <ChevronRight className="h-4 w-4" />
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
