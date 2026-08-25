import React from 'react';
import { Target, TrendingUp, TrendingDown, Layers } from 'lucide-react';

interface PredictiveScenarioBoxProps {
  scenarios: any;
  symbol: string;
}

export const PredictiveScenarioBox: React.FC<PredictiveScenarioBoxProps> = ({
  scenarios,
  symbol
}) => {
  if (!scenarios || (!scenarios.bullish_path && !scenarios.bearish_path)) {
    return null;
  }

  const isCryptoOrUsd = symbol.includes('BTC') || symbol.includes('USD');
  const currSym = isCryptoOrUsd ? '$' : '₹';

  const impulse = scenarios.recent_impulse || {};
  const buyerZone = scenarios.buyer_zone;
  const sellerZone = scenarios.seller_zone;
  const bullPath = scenarios.bullish_path;
  const bearPath = scenarios.bearish_path;

  return (
    <div className="w-full glass-panel rounded-2xl p-5 shadow-xs flex flex-col gap-4 bg-white border border-slate-200">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-blue-50 text-blue-600 border border-blue-200">
            <Target className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-bold text-sm text-slate-900 flex items-center gap-1.5">
              Predictive Target Roadmaps & Order Blocks
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                CHoCH & S/R Driven
              </span>
            </h3>
            <p className="text-xs text-slate-500">
              Structural If-Then Breakout Triggers, Demand/Supply Order Blocks, and Multi-Target Projections
            </p>
          </div>
        </div>

        {impulse.direction && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200 text-xs">
            <span className="text-slate-500">Impulse Wave:</span>
            {impulse.direction === 'UP' ? (
              <span className="font-bold text-emerald-700 flex items-center gap-1">
                <TrendingUp className="h-3.5 w-3.5" /> Recent Low ➔ High ({currSym}{impulse.from_price?.toLocaleString()} ➔ {currSym}{impulse.to_price?.toLocaleString()})
              </span>
            ) : (
              <span className="font-bold text-rose-700 flex items-center gap-1">
                <TrendingDown className="h-3.5 w-3.5" /> Recent High ➔ Low ({currSym}{impulse.from_price?.toLocaleString()} ➔ {currSym}{impulse.to_price?.toLocaleString()})
              </span>
            )}
          </div>
        )}
      </div>

      {/* Buyer (Demand) and Seller (Supply) Zones */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {buyerZone && (
          <div className="p-3.5 rounded-xl bg-emerald-50/60 border border-emerald-200 flex items-start gap-3">
            <div className="p-1.5 rounded-lg bg-emerald-100 text-emerald-700 mt-0.5">
              <Layers className="h-4 w-4" />
            </div>
            <div className="text-xs">
              <span className="font-bold text-emerald-800 uppercase tracking-wider text-[11px] block">
                Buyer Demand Zone (Support Base)
              </span>
              <p className="font-mono text-sm text-slate-900 font-bold mt-0.5">
                {currSym}{buyerZone.bottom_price?.toLocaleString()} — {currSym}{buyerZone.top_price?.toLocaleString()}
              </p>
              <span className="text-[10px] text-slate-500">
                Institutional accumulation base prior to bullish impulse
              </span>
            </div>
          </div>
        )}

        {sellerZone && (
          <div className="p-3.5 rounded-xl bg-rose-50/60 border border-rose-200 flex items-start gap-3">
            <div className="p-1.5 rounded-lg bg-rose-100 text-rose-700 mt-0.5">
              <Layers className="h-4 w-4" />
            </div>
            <div className="text-xs">
              <span className="font-bold text-rose-800 uppercase tracking-wider text-[11px] block">
                Seller Supply Zone (Resistance Base)
              </span>
              <p className="font-mono text-sm text-slate-900 font-bold mt-0.5">
                {currSym}{sellerZone.bottom_price?.toLocaleString()} — {currSym}{sellerZone.top_price?.toLocaleString()}
              </p>
              <span className="text-[10px] text-slate-500">
                Institutional distribution area prior to bearish expansion
              </span>
            </div>
          </div>
        )}
      </div>

      {/* If-Then Predictive Scenario Paths */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
        {/* Bullish Breakout Path */}
        {bullPath && (
          <div className="p-4 rounded-xl bg-slate-50/70 border border-emerald-200 flex flex-col justify-between gap-3 shadow-2xs">
            <div>
              <div className="flex items-center justify-between border-b border-slate-200 pb-2 mb-2">
                <span className="font-bold text-emerald-700 text-xs flex items-center gap-1.5 uppercase tracking-wide">
                  <TrendingUp className="h-4 w-4" /> Bullish Breakout Roadmap
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold border border-emerald-200">
                  R:R 1:{bullPath.risk_reward_ratio}
                </span>
              </div>

              <div className="text-xs space-y-2">
                <div className="p-2.5 rounded-lg bg-white border border-slate-200 font-mono text-[11px] shadow-2xs">
                  <span className="text-slate-500 block text-[10px] font-sans">Trigger Condition:</span>
                  <span className="text-slate-900 font-semibold">{bullPath.trigger_condition}</span>
                </div>

                <div className="grid grid-cols-2 gap-2 pt-1 font-mono text-xs">
                  <div className="p-2.5 rounded-lg bg-emerald-50 border border-emerald-200">
                    <span className="text-[10px] text-emerald-700 block font-sans font-medium">Target 1 (Major S/R)</span>
                    <span className="font-bold text-slate-900">{currSym}{bullPath.target_1?.toLocaleString()}</span>
                    <span className="text-[10px] text-emerald-600 block mt-0.5 font-bold">+{bullPath.target_1_distance_pct}%</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-emerald-50 border border-emerald-200">
                    <span className="text-[10px] text-emerald-700 block font-sans font-medium">Target 2 (Extension)</span>
                    <span className="font-bold text-slate-900">{currSym}{bullPath.target_2?.toLocaleString()}</span>
                    <span className="text-[10px] text-emerald-600 block mt-0.5 font-bold">+{bullPath.target_2_distance_pct}%</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between text-[10px] text-slate-500 pt-2 border-t border-slate-200 font-mono">
              <span>Invalidation SL: <strong className="text-rose-600">{currSym}{bullPath.invalidation_sl?.toLocaleString()}</strong></span>
              <span className="text-slate-400">Exit on CHoCH failure</span>
            </div>
          </div>
        )}

        {/* Bearish Breakdown Path */}
        {bearPath && (
          <div className="p-4 rounded-xl bg-slate-50/70 border border-rose-200 flex flex-col justify-between gap-3 shadow-2xs">
            <div>
              <div className="flex items-center justify-between border-b border-slate-200 pb-2 mb-2">
                <span className="font-bold text-rose-700 text-xs flex items-center gap-1.5 uppercase tracking-wide">
                  <TrendingDown className="h-4 w-4" /> Bearish Breakdown Roadmap
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-100 text-rose-800 font-bold border border-rose-200">
                  R:R 1:{bearPath.risk_reward_ratio}
                </span>
              </div>

              <div className="text-xs space-y-2">
                <div className="p-2.5 rounded-lg bg-white border border-slate-200 font-mono text-[11px] shadow-2xs">
                  <span className="text-slate-500 block text-[10px] font-sans">Trigger Condition:</span>
                  <span className="text-slate-900 font-semibold">{bearPath.trigger_condition}</span>
                </div>

                <div className="grid grid-cols-2 gap-2 pt-1 font-mono text-xs">
                  <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200">
                    <span className="text-[10px] text-rose-700 block font-sans font-medium">Downside Target 1</span>
                    <span className="font-bold text-slate-900">{currSym}{bearPath.target_1?.toLocaleString()}</span>
                    <span className="text-[10px] text-rose-600 block mt-0.5 font-bold">{bearPath.target_1_distance_pct}%</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200">
                    <span className="text-[10px] text-rose-700 block font-sans font-medium">Downside Target 2</span>
                    <span className="font-bold text-slate-900">{currSym}{bearPath.target_2?.toLocaleString()}</span>
                    <span className="text-[10px] text-rose-600 block mt-0.5 font-bold">{bearPath.target_2_distance_pct}%</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between text-[10px] text-slate-500 pt-2 border-t border-slate-200 font-mono">
              <span>Invalidation SL: <strong className="text-rose-600">{currSym}{bearPath.invalidation_sl?.toLocaleString()}</strong></span>
              <span className="text-slate-400">Exit on CHoCH failure</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
