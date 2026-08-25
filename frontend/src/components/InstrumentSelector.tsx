import React from 'react';
import { InstrumentConfig, MultiTimeframeSynthesis } from '../types';
import { Plus } from 'lucide-react';

interface InstrumentSelectorProps {
  instruments: InstrumentConfig[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  syntheses: Record<string, MultiTimeframeSynthesis>;
  onOpenManageModal: () => void;
}

export const InstrumentSelector: React.FC<InstrumentSelectorProps> = ({
  instruments,
  selectedSymbol,
  onSelectSymbol,
  syntheses,
  onOpenManageModal
}) => {
  return (
    <div className="w-full flex items-center justify-between gap-3 overflow-x-auto py-2 px-1 scrollbar-thin">
      <div className="flex items-center gap-2">
        {instruments.map((inst) => {
          const synthesis = syntheses[inst.symbol];
          const isSelected = inst.symbol.toUpperCase() === selectedSymbol.toUpperCase();
          const bias = synthesis?.overall_bias || 'NEUTRAL';
          const score = synthesis?.evidence_score?.total_score ?? '--';
          const currentPrice = synthesis?.current_price;
          const isCrypto = inst.symbol.includes('BTC') || inst.symbol.includes('USD');
          const currSym = isCrypto ? '$' : '₹';
          const isMarketRunning = synthesis?.market_session?.is_running ?? true;

          let dotColor = isMarketRunning ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400';
          let borderHighlight = 'border-slate-200';

          if (bias === 'BULLISH') {
            borderHighlight = isSelected ? 'border-emerald-500 bg-emerald-50 text-emerald-900 shadow-xs' : 'hover:border-emerald-300';
          } else if (bias === 'BEARISH') {
            borderHighlight = isSelected ? 'border-rose-500 bg-rose-50 text-rose-900 shadow-xs' : 'hover:border-rose-300';
          } else {
            borderHighlight = isSelected ? 'border-amber-500 bg-amber-50 text-amber-900 shadow-xs' : 'hover:border-amber-300';
          }

          return (
            <button
              key={inst.symbol}
              onClick={() => onSelectSymbol(inst.symbol)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-semibold whitespace-nowrap transition-all ${
                isSelected
                  ? `font-bold ${borderHighlight}`
                  : `bg-white text-slate-700 border-slate-200 hover:bg-slate-50 hover:text-slate-900 shadow-2xs`
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${dotColor}`} />
              <span>{inst.symbol}</span>
              {currentPrice !== undefined && (
                <span className="font-mono text-slate-900 font-extrabold text-[11px]">
                  {currSym}{currentPrice.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 })}
                </span>
              )}
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-bold">
                {score}
              </span>
            </button>
          );
        })}
      </div>

      {/* Add / Manage Button */}
      <button
        onClick={onOpenManageModal}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-xs font-semibold text-blue-600 hover:text-blue-700 transition-all shrink-0 shadow-2xs"
      >
        <Plus className="h-3.5 w-3.5" />
        <span>Manage (Max 10)</span>
      </button>
    </div>
  );
};
