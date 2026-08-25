import React from 'react';
import { SingleTimeframeAnalysis } from '../types';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Layers,
  Zap
} from 'lucide-react';

interface MultiTimeframeCardsProps {
  timeframes: Record<string, SingleTimeframeAnalysis>;
}

export const MultiTimeframeCards: React.FC<MultiTimeframeCardsProps> = ({ timeframes }) => {
  const tfOrder = ['4H', '1H', '15M', '5M'] as const;
  const tfLabels: Record<string, { role: string; desc: string }> = {
    '4H': { role: 'Macro Structure', desc: 'Highest Priority Anchor' },
    '1H': { role: 'Intermediate Trend', desc: 'Core Trend Filter' },
    '15M': { role: 'Execution Structure', desc: 'BOS / CHoCH Setup Zone' },
    '5M': { role: 'Tactical Timing', desc: 'Immediate Momentum & Pullback' }
  };

  const getTrendStyle = (trend: string) => {
    if (trend.includes('BULLISH')) {
      return {
        badge: 'bg-emerald-50 text-emerald-700 border-emerald-300',
        text: 'text-emerald-700',
        icon: <TrendingUp className="h-3.5 w-3.5 text-emerald-600" />
      };
    } else if (trend.includes('BEARISH')) {
      return {
        badge: 'bg-rose-50 text-rose-700 border-rose-300',
        text: 'text-rose-700',
        icon: <TrendingDown className="h-3.5 w-3.5 text-rose-600" />
      };
    } else {
      return {
        badge: 'bg-amber-50 text-amber-700 border-amber-300',
        text: 'text-amber-700',
        icon: <Minus className="h-3.5 w-3.5 text-amber-600" />
      };
    }
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {tfOrder.map((tf) => {
        const data = timeframes[tf];
        const trend = data?.trend || 'NEUTRAL';
        const style = getTrendStyle(trend);
        const rsi = data?.indicators?.rsi_14 ?? 50;
        const relVol = data?.indicators?.relative_volume ?? 1.0;
        const latestEvent = data?.latest_event;

        return (
          <div
            key={tf}
            className="glass-card rounded-2xl p-4 flex flex-col justify-between gap-3 shadow-2xs hover:shadow-md transition-all bg-white border border-slate-200"
          >
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-extrabold text-lg text-slate-900 font-mono">{tf}</span>
                  <span className="text-[10px] text-blue-700 font-semibold px-2 py-0.5 rounded bg-blue-50 border border-blue-200">
                    {tfLabels[tf].role}
                  </span>
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">{tfLabels[tf].desc}</p>
              </div>
              <div className={`px-2 py-0.5 rounded-lg border text-xs font-bold flex items-center gap-1.5 ${style.badge}`}>
                {style.icon}
                <span>{trend}</span>
              </div>
            </div>

            {/* Structure & Latest Break */}
            <div className="bg-slate-50 rounded-xl p-3 border border-slate-200 flex flex-col gap-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500 flex items-center gap-1">
                  <Layers className="h-3 w-3 text-slate-400" /> Structure:
                </span>
                <span className="font-semibold text-slate-800">{data?.structure_type || 'Consolidation'}</span>
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500 flex items-center gap-1">
                  <Zap className="h-3 w-3 text-slate-400" /> Latest Break:
                </span>
                <span className={`font-semibold text-[11px] ${latestEvent ? (latestEvent.direction === 'BULLISH' ? 'text-emerald-600' : 'text-rose-600') : 'text-slate-500'}`}>
                  {latestEvent ? `${latestEvent.event_type.replace(/_/g, ' ')}` : 'None'}
                </span>
              </div>

              {latestEvent && (
                <div className="text-[10px] font-mono text-slate-600 bg-white px-2 py-1 rounded border border-slate-200">
                  Broken: {latestEvent.broken_level.toFixed(1)} | Break: {latestEvent.break_price.toFixed(1)}
                </div>
              )}

              <div className="flex items-center justify-between text-xs pt-1 border-t border-slate-200">
                <span className="text-slate-500">Important Level:</span>
                <span className="font-mono text-blue-600 font-bold">
                  {data?.important_level ? `${data.important_level.toFixed(1)}` : 'N/A'}
                </span>
              </div>
            </div>

            {/* Indicators: RSI, Volume */}
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              {/* RSI */}
              <div className="bg-slate-50 rounded-lg p-2 border border-slate-200 flex flex-col gap-1">
                <div className="flex items-center justify-between text-slate-500 text-[10px]">
                  <span>RSI (14)</span>
                  <span className={`font-bold ${rsi > 60 ? 'text-emerald-600' : rsi < 40 ? 'text-rose-600' : 'text-slate-700'}`}>
                    {rsi.toFixed(1)}
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      rsi > 60 ? 'bg-emerald-500' : rsi < 40 ? 'bg-rose-500' : 'bg-blue-500'
                    }`}
                    style={{ width: `${Math.min(100, Math.max(0, rsi))}%` }}
                  />
                </div>
              </div>

              {/* Volume Ratio */}
              <div className="bg-slate-50 rounded-lg p-2 border border-slate-200 flex flex-col gap-1">
                <div className="flex items-center justify-between text-slate-500 text-[10px]">
                  <span>Rel Vol</span>
                  <span className={`font-bold ${relVol >= 1.2 ? 'text-emerald-600' : 'text-slate-700'}`}>
                    {relVol.toFixed(2)}x
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      relVol >= 1.2 ? 'bg-emerald-500' : 'bg-indigo-500'
                    }`}
                    style={{ width: `${Math.min(100, (relVol / 2.0) * 100)}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
