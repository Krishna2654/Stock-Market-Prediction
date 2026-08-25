import React from 'react';
import { WhatJustChanged, StructureBreakEvent } from '../types';
import { Activity, ArrowRight, Zap, CheckCircle2, AlertCircle } from 'lucide-react';

interface WhatJustChangedPanelProps {
  whatJustChanged?: WhatJustChanged | null;
  latestEvent?: StructureBreakEvent | null;
  currentSymbol: string;
}

export const WhatJustChangedPanel: React.FC<WhatJustChangedPanelProps> = ({
  whatJustChanged,
  latestEvent,
  currentSymbol
}) => {
  if (!whatJustChanged && !latestEvent) {
    return (
      <div className="glass-panel rounded-2xl p-4 bg-white border border-slate-200 shadow-xs flex items-center justify-between text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-blue-500 animate-pulse" />
          <span className="font-semibold text-slate-700">What Just Changed?</span>
        </div>
        <span className="text-slate-400">Monitoring real-time structure delta for {currentSymbol}...</span>
      </div>
    );
  }

  const isBullish = whatJustChanged?.event_type.includes('BULL') || latestEvent?.direction === 'BULLISH';
  const badgeStyle = isBullish
    ? 'bg-emerald-50 text-emerald-700 border-emerald-300'
    : 'bg-rose-50 text-rose-700 border-rose-300';

  const isCrypto = currentSymbol.includes('BTC') || currentSymbol.includes('USD');
  const currSym = isCrypto ? '$' : '₹';

  const eventType = whatJustChanged?.event_type || latestEvent?.event_type || 'STRUCTURE_UPDATE';
  const timeframe = whatJustChanged?.timeframe || latestEvent?.timeframe || '15M';
  const brokenLevel = whatJustChanged?.broken_level ?? latestEvent?.broken_level ?? 0;
  const breakPrice = whatJustChanged?.break_price ?? latestEvent?.break_price ?? 0;
  const volConfirmed = whatJustChanged?.volume_confirmed ?? latestEvent?.volume_confirmed ?? true;
  const interpretation = whatJustChanged?.structural_interpretation || latestEvent?.notes || 'Structural state updated.';

  return (
    <div className="glass-panel rounded-2xl p-3.5 sm:p-4 bg-white border border-slate-200 shadow-xs flex flex-col gap-3 w-full min-w-0">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1.5 rounded-lg bg-blue-50 text-blue-600 border border-blue-200 shrink-0">
            <Activity className="h-4 w-4 animate-pulse" />
          </div>
          <div className="min-w-0">
            <h3 className="font-bold text-xs text-slate-900 flex items-center gap-1.5 flex-wrap">
              <span>What Just Changed?</span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 truncate">
                {currentSymbol} • {timeframe}
              </span>
            </h3>
          </div>
        </div>

        <span className={`px-2 py-0.5 rounded-lg border text-[10px] sm:text-[11px] font-bold ${badgeStyle} flex items-center gap-1 shrink-0`}>
          <Zap className="h-3 w-3" />
          {eventType.replace(/_/g, ' ')}
        </span>
      </div>

      {/* Delta Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 text-xs min-w-0">
        {/* State Transition */}
        <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-col justify-between">
          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
            State Transition
          </span>
          <div className="flex items-center gap-2 font-bold text-slate-800 text-xs mt-1">
            <span className="text-slate-500">{whatJustChanged?.previous_state || 'Previous Structure'}</span>
            <ArrowRight className="h-3.5 w-3.5 text-blue-600 shrink-0" />
            <span className={isBullish ? 'text-emerald-700' : 'text-rose-700'}>
              {whatJustChanged?.new_state || (isBullish ? 'BULLISH BIAS' : 'BEARISH BIAS')}
            </span>
          </div>
        </div>

        {/* Level & Price */}
        <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-col justify-between">
          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
            Broken Level / Trigger
          </span>
          <div className="flex items-center justify-between mt-1">
            <span className="font-mono font-bold text-slate-800 text-xs">
              {currSym}{brokenLevel.toLocaleString()}
            </span>
            <span className="text-[10px] font-mono text-slate-500">
              Close: {currSym}{breakPrice.toLocaleString()}
            </span>
          </div>
        </div>

        {/* Volume & Validation */}
        <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-col justify-between">
          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
            Volume & Confirmation
          </span>
          <div className="flex items-center gap-1.5 mt-1">
            {volConfirmed ? (
              <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> Confirmed with Volume
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700">
                <AlertCircle className="h-3.5 w-3.5 text-amber-600" /> Normal Volume
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Structural Interpretation */}
      <div className="p-2.5 rounded-xl bg-blue-50/50 border border-blue-100 text-[11px] text-slate-700 leading-relaxed">
        <strong className="text-blue-900 font-semibold">Structural Interpretation: </strong>
        {interpretation}
      </div>
    </div>
  );
};
