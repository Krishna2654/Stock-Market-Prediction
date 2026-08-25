import React from 'react';
import { SupportResistanceSummary } from '../types';
import { Anchor, ArrowUp, ArrowDown } from 'lucide-react';

interface SupportResistanceBoxProps {
  sr: SupportResistanceSummary;
  invalidationLevel?: number | null;
}

export const SupportResistanceBox: React.FC<SupportResistanceBoxProps> = ({
  sr,
  invalidationLevel
}) => {
  const currentPrice = sr.current_price || 0;

  const calculateDistance = (level: number | null) => {
    if (!level || currentPrice === 0) return '--';
    const diff = ((level - currentPrice) / currentPrice) * 100;
    return `${diff > 0 ? '+' : ''}${diff.toFixed(2)}%`;
  };

  return (
    <div className="glass-panel rounded-2xl p-5 shadow-xs flex flex-col justify-between gap-4 bg-white border border-slate-200">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2">
          <Anchor className="h-5 w-5 text-blue-600" />
          <h3 className="font-bold text-sm text-slate-900">Key Support & Resistance Zones</h3>
        </div>
        <span className="text-[11px] font-mono text-blue-700 font-bold bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
          CMP: {currentPrice.toLocaleString()}
        </span>
      </div>

      {/* Levels Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
        {/* Resistances */}
        <div className="bg-rose-50/60 rounded-xl p-3.5 border border-rose-200 flex flex-col gap-2">
          <span className="font-bold text-[11px] text-rose-700 uppercase tracking-wider flex items-center gap-1">
            <ArrowUp className="h-3.5 w-3.5" /> Resistance Zones
          </span>

          <div className="flex items-center justify-between bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs">
            <div>
              <span className="text-[10px] text-slate-500 block font-medium">Major Resistance</span>
              <span className="font-bold font-mono text-rose-700 text-sm">
                {sr.major_resistance ? `${sr.major_resistance.toFixed(2)}` : 'None'}
              </span>
            </div>
            <span className="font-mono text-[10px] text-slate-500 font-semibold">
              {calculateDistance(sr.major_resistance)}
            </span>
          </div>

          <div className="flex items-center justify-between bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs">
            <div>
              <span className="text-[10px] text-slate-500 block font-medium">Minor Resistance</span>
              <span className="font-bold font-mono text-rose-700 text-sm">
                {sr.minor_resistance ? `${sr.minor_resistance.toFixed(2)}` : 'None'}
              </span>
            </div>
            <span className="font-mono text-[10px] text-slate-500 font-semibold">
              {calculateDistance(sr.minor_resistance)}
            </span>
          </div>
        </div>

        {/* Supports */}
        <div className="bg-emerald-50/60 rounded-xl p-3.5 border border-emerald-200 flex flex-col gap-2">
          <span className="font-bold text-[11px] text-emerald-700 uppercase tracking-wider flex items-center gap-1">
            <ArrowDown className="h-3.5 w-3.5" /> Support Zones
          </span>

          <div className="flex items-center justify-between bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs">
            <div>
              <span className="text-[10px] text-slate-500 block font-medium">Minor Support</span>
              <span className="font-bold font-mono text-emerald-700 text-sm">
                {sr.minor_support ? `${sr.minor_support.toFixed(2)}` : 'None'}
              </span>
            </div>
            <span className="font-mono text-[10px] text-slate-500 font-semibold">
              {calculateDistance(sr.minor_support)}
            </span>
          </div>

          <div className="flex items-center justify-between bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs">
            <div>
              <span className="text-[10px] text-slate-500 block font-medium">Major Support</span>
              <span className="font-bold font-mono text-emerald-700 text-sm">
                {sr.major_support ? `${sr.major_support.toFixed(2)}` : 'None'}
              </span>
            </div>
            <span className="font-mono text-[10px] text-slate-500 font-semibold">
              {calculateDistance(sr.major_support)}
            </span>
          </div>
        </div>
      </div>

      {/* Structural Invalidation Level Banner */}
      {invalidationLevel && (
        <div className="flex items-center justify-between bg-amber-50 p-3 rounded-xl border border-amber-200 text-xs">
          <div>
            <span className="font-bold text-amber-800 block">Structural Invalidation Level</span>
            <span className="text-[11px] text-slate-500">
              Setup invalidated if price confirms close beyond this level
            </span>
          </div>
          <span className="font-mono font-extrabold text-amber-800 text-sm bg-white px-2.5 py-1 rounded-lg border border-amber-300 shadow-2xs">
            {invalidationLevel.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
};
