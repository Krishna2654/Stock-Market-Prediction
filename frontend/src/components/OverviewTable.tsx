import React from 'react';
import { MultiTimeframeSynthesis } from '../types';
import { ArrowUpRight, ArrowDownRight, Minus, Eye, Sparkles, Radio } from 'lucide-react';

interface OverviewTableProps {
  syntheses: MultiTimeframeSynthesis[];
  selectedSymbol: string;
  onSelectInstrument: (symbol: string) => void;
  onGenerateAI: (symbol: string) => void;
}

export const OverviewTable: React.FC<OverviewTableProps> = ({
  syntheses,
  selectedSymbol,
  onSelectInstrument,
  onGenerateAI
}) => {
  const getTrendBadge = (trend?: string) => {
    if (!trend) return <span className="text-slate-400">--</span>;

    if (trend.includes('BULLISH')) {
      const isStrong = trend.includes('STRONG');
      return (
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold ${
            isStrong
              ? 'bg-emerald-50 text-emerald-700 border border-emerald-300'
              : 'bg-emerald-50/60 text-emerald-700 border border-emerald-200'
          }`}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-600" />
          {isStrong ? 'Strong Bull' : 'Bullish'}
        </span>
      );
    } else if (trend.includes('BEARISH')) {
      const isStrong = trend.includes('STRONG');
      return (
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold ${
            isStrong
              ? 'bg-rose-50 text-rose-700 border border-rose-300'
              : 'bg-rose-50/60 text-rose-700 border border-rose-200'
          }`}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-rose-600" />
          {isStrong ? 'Strong Bear' : 'Bearish'}
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
          Neutral
        </span>
      );
    }
  };

  const getBiasPill = (bias: string) => {
    switch (bias) {
      case 'BULLISH':
        return (
          <span className="px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-300 font-bold text-xs flex items-center gap-1">
            <ArrowUpRight className="h-3.5 w-3.5" />
            BULLISH
          </span>
        );
      case 'BEARISH':
        return (
          <span className="px-2.5 py-1 rounded-lg bg-rose-50 text-rose-700 border border-rose-300 font-bold text-xs flex items-center gap-1">
            <ArrowDownRight className="h-3.5 w-3.5" />
            BEARISH
          </span>
        );
      case 'MIXED':
        return (
          <span className="px-2.5 py-1 rounded-lg bg-purple-50 text-purple-700 border border-purple-300 font-bold text-xs flex items-center gap-1">
            <Minus className="h-3.5 w-3.5" />
            MIXED
          </span>
        );
      default:
        return (
          <span className="px-2.5 py-1 rounded-lg bg-amber-50 text-amber-700 border border-amber-300 font-bold text-xs flex items-center gap-1">
            <Minus className="h-3.5 w-3.5" />
            NEUTRAL
          </span>
        );
    }
  };

  return (
    <div className="w-full glass-panel rounded-2xl overflow-hidden shadow-xs bg-white border border-slate-200">
      <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <span>Multi-Timeframe Structure Matrix</span>
            <span className="text-xs font-normal text-slate-500">
              (Live alignment across 4H, 1H, 15M, 5M)
            </span>
          </h2>
        </div>
        <div className="text-xs text-slate-500 flex items-center gap-2">
          <span>Priority:</span>
          <span className="font-semibold text-blue-600">4H &gt; 1H &gt; 15M &gt; 5M</span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-slate-50 text-slate-600 uppercase tracking-wider font-semibold border-b border-slate-200">
              <th className="py-3 px-4">Instrument & Live Price</th>
              <th className="py-3 px-3 text-center">4H</th>
              <th className="py-3 px-3 text-center">1H</th>
              <th className="py-3 px-3 text-center">15M</th>
              <th className="py-3 px-3 text-center">5M</th>
              <th className="py-3 px-4 text-center">Overall Bias</th>
              <th className="py-3 px-4 text-center">Evidence Score</th>
              <th className="py-3 px-4">State & Latest Event</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {syntheses.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-8 text-center text-slate-400">
                  Loading multi-timeframe market structure...
                </td>
              </tr>
            ) : (
              syntheses.map((s) => {
                const isSelected = s.symbol.toUpperCase() === selectedSymbol.toUpperCase();
                const score = s.evidence_score.total_score;
                const isCrypto = s.symbol.includes('BTC') || s.symbol.includes('USD');
                const currSym = isCrypto ? '$' : '₹';
                const isMarketRunning = s.market_session?.is_running ?? true;

                const scoreColor =
                  score >= 80
                    ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                    : score >= 65
                    ? 'text-blue-700 bg-blue-50 border-blue-200'
                    : score >= 50
                    ? 'text-amber-700 bg-amber-50 border-amber-200'
                    : 'text-rose-700 bg-rose-50 border-rose-200';

                return (
                  <tr
                    key={s.symbol}
                    onClick={() => onSelectInstrument(s.symbol)}
                    className={`cursor-pointer transition-colors ${
                      isSelected
                        ? 'bg-blue-50/50 hover:bg-blue-50/70'
                        : 'hover:bg-slate-50'
                    }`}
                  >
                    {/* Instrument & Live Price */}
                    <td className="py-3.5 px-4 font-semibold text-slate-900 whitespace-nowrap">
                      <div className="flex items-center gap-2.5">
                        <span
                          className={`h-2.5 w-2.5 rounded-full shrink-0 ${
                            isMarketRunning ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'
                          }`}
                          title={s.market_session?.message || (isMarketRunning ? 'Market Live' : 'Market Closed')}
                        />
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="font-bold text-sm text-slate-900">{s.symbol}</span>
                            <span className="text-[10px] font-mono px-1 py-0.2 rounded bg-slate-100 text-slate-600 font-bold border border-slate-200">
                              {s.ticker}
                            </span>
                          </div>
                          <div className="text-xs font-mono font-extrabold text-blue-700 mt-0.5">
                            {currSym}{s.current_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* 4H */}
                    <td className="py-3.5 px-3 text-center whitespace-nowrap">
                      {getTrendBadge(s.timeframes['4H']?.trend)}
                    </td>

                    {/* 1H */}
                    <td className="py-3.5 px-3 text-center whitespace-nowrap">
                      {getTrendBadge(s.timeframes['1H']?.trend)}
                    </td>

                    {/* 15M */}
                    <td className="py-3.5 px-3 text-center whitespace-nowrap">
                      {getTrendBadge(s.timeframes['15M']?.trend)}
                    </td>

                    {/* 5M */}
                    <td className="py-3.5 px-3 text-center whitespace-nowrap">
                      {getTrendBadge(s.timeframes['5M']?.trend)}
                    </td>

                    {/* Overall Bias */}
                    <td className="py-3.5 px-4 text-center whitespace-nowrap">
                      <div className="inline-block">{getBiasPill(s.overall_bias)}</div>
                    </td>

                    {/* Evidence Score */}
                    <td className="py-3.5 px-4 text-center whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        <span className={`px-2 py-0.5 rounded font-mono font-bold text-xs border ${scoreColor}`}>
                          {score}/100
                        </span>
                      </div>
                    </td>

                    {/* State & Latest Event */}
                    <td className="py-3.5 px-4 text-slate-700">
                      <div className="font-semibold text-[11px] text-slate-900">
                        {s.current_state}
                      </div>
                      <div className="text-[10px] text-slate-500 truncate max-w-xs">
                        {s.latest_important_event
                          ? `${s.latest_important_event.timeframe} ${s.latest_important_event.event_type.replace(/_/g, ' ')}`
                          : s.short_term_state}
                      </div>
                    </td>

                    {/* Actions */}
                    <td className="py-3.5 px-4 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => onGenerateAI(s.symbol)}
                          className="px-2.5 py-1 rounded-lg bg-blue-50 hover:bg-blue-100 border border-blue-200 text-blue-700 text-xs font-semibold flex items-center gap-1 transition-all shadow-2xs"
                          title="Generate AI Prediction Summary"
                        >
                          <Sparkles className="h-3 w-3 text-blue-600" />
                          <span>AI Summary</span>
                        </button>
                        <button
                          onClick={() => onSelectInstrument(s.symbol)}
                          className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-all shadow-2xs"
                          title="Inspect Chart & Structure"
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
