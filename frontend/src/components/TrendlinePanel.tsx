import React from 'react';
import { Trendline } from '../types';
import { TrendingUp, TrendingDown, Layers, CheckCircle, AlertTriangle, Shield } from 'lucide-react';

interface TrendlinePanelProps {
  trendlines: Trendline[];
  timeframe: string;
}

export const TrendlinePanel: React.FC<TrendlinePanelProps> = ({
  trendlines,
  timeframe
}) => {
  const ascendingLines = trendlines.filter((t) => t.line_type === 'ASCENDING_SUPPORT');
  const descendingLines = trendlines.filter((t) => t.line_type === 'DESCENDING_RESISTANCE');

  const getRankBadge = (rank: string) => {
    switch (rank) {
      case 'PRIMARY':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
            PRIMARY
          </span>
        );
      case 'SECONDARY':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            SECONDARY
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-50 text-slate-500 border border-slate-200">
            MINOR
          </span>
        );
    }
  };

  const getStatusBadge = (status: string, isActive: boolean) => {
    if (isActive) {
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-700">
          <CheckCircle className="h-3 w-3 text-emerald-600" /> Active
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-rose-700">
          <AlertTriangle className="h-3 w-3 text-rose-600" /> Broken
        </span>
      );
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-5 shadow-xs flex flex-col justify-between gap-4 bg-white border border-slate-200">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2">
          <Layers className="h-5 w-5 text-blue-600" />
          <div>
            <h3 className="font-bold text-sm text-slate-900 flex items-center gap-1.5">
              <span>Structural Trendlines Matrix</span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                {timeframe} Timeframe ({trendlines.length} lines)
              </span>
            </h3>
            <p className="text-xs text-slate-500">
              Pivot tangent non-penetrating multi-line geometry (Primary, Secondary, Minor)
            </p>
          </div>
        </div>
      </div>

      {/* Grid of Support & Resistance Trendlines */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        {/* Ascending Support Lines */}
        <div className="flex flex-col gap-2.5 bg-emerald-50/40 p-3.5 rounded-xl border border-emerald-200">
          <div className="flex items-center justify-between">
            <span className="font-bold text-xs text-emerald-800 uppercase tracking-wider flex items-center gap-1.5">
              <TrendingUp className="h-4 w-4 text-emerald-600" /> Ascending Support Lines ({ascendingLines.length})
            </span>
          </div>

          {ascendingLines.length === 0 ? (
            <p className="text-[11px] text-slate-400 py-3 text-center italic">
              No active ascending support lines in current structure.
            </p>
          ) : (
            <div className="space-y-2">
              {ascendingLines.map((tl, idx) => (
                <div
                  key={idx}
                  className="p-2.5 rounded-lg bg-white border border-slate-200 shadow-2xs flex flex-col gap-1.5"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      {getRankBadge(tl.rank)}
                      <span className="font-semibold text-slate-800 text-[11px]">
                        {tl.strength} Support
                      </span>
                    </div>
                    {getStatusBadge(tl.status, tl.is_active)}
                  </div>

                  <div className="grid grid-cols-3 gap-1 text-[10px] font-mono text-slate-600 bg-slate-50 p-1.5 rounded border border-slate-100">
                    <div>
                      <span className="text-slate-400 block">Touches:</span>
                      <strong className="text-slate-900">{tl.touch_count} pivots</strong>
                    </div>
                    <div>
                      <span className="text-slate-400 block">Anchor P1:</span>
                      <strong className="text-slate-900">{tl.p1_price.toFixed(2)}</strong>
                    </div>
                    <div>
                      <span className="text-slate-400 block">Current End:</span>
                      <strong className="text-emerald-700">{tl.end_price.toFixed(2)}</strong>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Descending Resistance Lines */}
        <div className="flex flex-col gap-2.5 bg-rose-50/40 p-3.5 rounded-xl border border-rose-200">
          <div className="flex items-center justify-between">
            <span className="font-bold text-xs text-rose-800 uppercase tracking-wider flex items-center gap-1.5">
              <TrendingDown className="h-4 w-4 text-rose-600" /> Descending Resistance Lines ({descendingLines.length})
            </span>
          </div>

          {descendingLines.length === 0 ? (
            <p className="text-[11px] text-slate-400 py-3 text-center italic">
              No active descending resistance lines in current structure.
            </p>
          ) : (
            <div className="space-y-2">
              {descendingLines.map((tl, idx) => (
                <div
                  key={idx}
                  className="p-2.5 rounded-lg bg-white border border-slate-200 shadow-2xs flex flex-col gap-1.5"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      {getRankBadge(tl.rank)}
                      <span className="font-semibold text-slate-800 text-[11px]">
                        {tl.strength} Resistance
                      </span>
                    </div>
                    {getStatusBadge(tl.status, tl.is_active)}
                  </div>

                  <div className="grid grid-cols-3 gap-1 text-[10px] font-mono text-slate-600 bg-slate-50 p-1.5 rounded border border-slate-100">
                    <div>
                      <span className="text-slate-400 block">Touches:</span>
                      <strong className="text-slate-900">{tl.touch_count} pivots</strong>
                    </div>
                    <div>
                      <span className="text-slate-400 block">Anchor P1:</span>
                      <strong className="text-slate-900">{tl.p1_price.toFixed(2)}</strong>
                    </div>
                    <div>
                      <span className="text-slate-400 block">Current End:</span>
                      <strong className="text-rose-700">{tl.end_price.toFixed(2)}</strong>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
