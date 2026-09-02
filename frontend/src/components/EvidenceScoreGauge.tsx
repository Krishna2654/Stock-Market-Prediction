import React from 'react';
import { EvidenceScoreBreakdown } from '../types';
import { ShieldCheck } from 'lucide-react';

interface EvidenceScoreGaugeProps {
  scoreData: EvidenceScoreBreakdown;
}

export const EvidenceScoreGauge: React.FC<EvidenceScoreGaugeProps> = ({ scoreData }) => {
  const safeData = scoreData || {
    total_score: 50,
    category: 'Mixed Evidence',
    structure_points: 10,
    htf_alignment_points: 10,
    momentum_points: 10,
    volume_points: 10,
    breakout_points: 10,
    details: []
  };
  const score = safeData.total_score ?? 50;

  let circleColor = '#d97706';
  let badgeStyle = 'bg-amber-50 text-amber-700 border-amber-300';

  if (score >= 80) {
    circleColor = '#16a34a';
    badgeStyle = 'bg-emerald-50 text-emerald-700 border-emerald-300';
  } else if (score >= 65) {
    circleColor = '#2563eb';
    badgeStyle = 'bg-blue-50 text-blue-700 border-blue-300';
  } else if (score >= 50) {
    circleColor = '#d97706';
    badgeStyle = 'bg-amber-50 text-amber-700 border-amber-300';
  } else {
    circleColor = '#dc2626';
    badgeStyle = 'bg-rose-50 text-rose-700 border-rose-300';
  }

  // Factors
  const factors = [
    { label: 'Market Structure', pts: safeData.structure_points ?? 10, max: 25, color: 'bg-emerald-500' },
    { label: 'HTF Trend Alignment', pts: safeData.htf_alignment_points ?? 10, max: 25, color: 'bg-blue-500' },
    { label: 'Momentum (RSI/EMA)', pts: safeData.momentum_points ?? 10, max: 20, color: 'bg-indigo-500' },
    { label: 'Volume Expansion', pts: safeData.volume_points ?? 10, max: 15, color: 'bg-amber-500' },
    { label: 'Breakout Confirmation', pts: safeData.breakout_points ?? 10, max: 15, color: 'bg-purple-500' }
  ];

  return (
    <div className="glass-panel rounded-2xl p-4 sm:p-5 shadow-xs flex flex-col justify-between gap-4 bg-white border border-slate-200 w-full min-w-0">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between border-b border-slate-200 pb-3 gap-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <ShieldCheck className="h-5 w-5 text-blue-600 shrink-0" />
          <h3 className="font-bold text-sm text-slate-900 truncate">Evidence Alignment Score</h3>
        </div>
        <span className={`px-2.5 py-1 rounded-lg border text-xs font-bold ${badgeStyle} shrink-0`}>
          {scoreData.category}
        </span>
      </div>

      {/* Main Score Display */}
      <div className="flex flex-col sm:flex-row items-center sm:items-start gap-4 sm:gap-6 min-w-0">
        {/* Score Number Gauge */}
        <div className="relative flex items-center justify-center h-20 w-20 sm:h-24 sm:w-24 shrink-0 rounded-2xl bg-slate-50 border border-slate-200 shadow-inner">
          <div className="text-center">
            <span className="text-2xl sm:text-3xl font-extrabold font-mono tracking-tight" style={{ color: circleColor }}>
              {score}
            </span>
            <span className="text-[10px] block text-slate-500 font-mono font-bold">/ 100 PTS</span>
          </div>
        </div>

        {/* Description */}
        <div className="flex flex-col gap-1 text-xs text-slate-600">
          <p className="font-semibold text-slate-800">
            Multi-factor quantitative evidence confluence across 4H, 1H, 15M, and 5M.
          </p>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Higher score reflects multi-timeframe alignment, confirmed structural breaks, and volume expansion.
          </p>
        </div>
      </div>

      {/* Factor Breakdown Bars */}
      <div className="flex flex-col gap-2.5 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
        <span className="text-[11px] font-bold text-slate-600 uppercase tracking-wider">
          Contributing Evidence Factors
        </span>

        {factors.map((f) => (
          <div key={f.label} className="flex flex-col gap-1 text-xs">
            <div className="flex items-center justify-between text-slate-700">
              <span className="text-[11px] font-medium">{f.label}</span>
              <span className="font-mono font-bold text-[11px] text-slate-900">
                +{f.pts} / {f.max} pts
              </span>
            </div>
            <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
              <div
                className={`h-full rounded-full ${f.color}`}
                style={{ width: `${(f.pts / f.max) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
