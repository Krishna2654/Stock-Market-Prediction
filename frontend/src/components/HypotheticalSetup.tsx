import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { HypotheticalSetup as SetupType } from '../types';
import { Calculator, ShieldAlert } from 'lucide-react';

interface HypotheticalSetupProps {
  symbol: string;
}

export const HypotheticalSetup: React.FC<HypotheticalSetupProps> = ({ symbol }) => {
  const [accountSize, setAccountSize] = useState<number>(100000);
  const [riskPct, setRiskPct] = useState<number>(1.0);
  const [setup, setSetup] = useState<SetupType | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const isCryptoOrUsd = symbol.includes('BTC') || symbol.includes('USD');
  const currSym = isCryptoOrUsd ? '$' : '₹';

  const fetchSetup = async () => {
    setIsLoading(true);
    try {
      const data = await api.getHypotheticalSetup(symbol, accountSize, riskPct);
      setSetup(data);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSetup();
  }, [symbol, accountSize, riskPct]);

  return (
    <div className="glass-panel rounded-2xl p-5 shadow-xs flex flex-col justify-between gap-4 bg-white border border-slate-200">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2">
          <Calculator className="h-5 w-5 text-blue-600" />
          <h3 className="font-bold text-sm text-slate-900">
            Educational Decision-Support Calculator
          </h3>
        </div>
        <span className="text-[10px] font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
          Hypothetical Only
        </span>
      </div>

      {/* Account Parameters */}
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <label className="text-slate-600 font-medium block mb-1">Simulated Capital ({currSym})</label>
          <input
            type="number"
            value={accountSize}
            onChange={(e) => setAccountSize(Number(e.target.value))}
            step={10000}
            className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-slate-900 font-mono focus:border-blue-500 focus:bg-white focus:outline-none"
          />
        </div>
        <div>
          <label className="text-slate-600 font-medium block mb-1">Risk Capital Per Setup (%)</label>
          <input
            type="number"
            value={riskPct}
            onChange={(e) => setRiskPct(Number(e.target.value))}
            step={0.5}
            min={0.1}
            max={5.0}
            className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-slate-900 font-mono focus:border-blue-500 focus:bg-white focus:outline-none"
          />
        </div>
      </div>

      {/* Calculated Setup Box */}
      {setup && setup.status === 'HYPOTHETICAL_SETUP_AVAILABLE' ? (
        <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 flex flex-col gap-3 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-800">
              Hypothetical Setup ({setup.direction})
            </span>
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
              setup.direction === 'LONG'
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-300'
                : 'bg-rose-50 text-rose-700 border border-rose-300'
            }`}>
              {setup.direction}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            <div className="bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs">
              <span className="text-[10px] text-slate-500 block font-medium">Hypothetical Entry</span>
              <span className="font-bold font-mono text-slate-900">{currSym}{setup.entry_price}</span>
            </div>
            <div className="bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs">
              <span className="text-[10px] text-slate-500 block font-medium">Invalidation (SL)</span>
              <span className="font-bold font-mono text-rose-600">{currSym}{setup.stop_loss}</span>
            </div>
            <div className="bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs">
              <span className="text-[10px] text-slate-500 block font-medium">Target 1 (1:2 R:R)</span>
              <span className="font-bold font-mono text-emerald-600">{currSym}{setup.target_1_rr2}</span>
            </div>
            <div className="bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs">
              <span className="text-[10px] text-slate-500 block font-medium">Target 2 (1:3 R:R)</span>
              <span className="font-bold font-mono text-blue-600">{currSym}{setup.target_2_rr3}</span>
            </div>
          </div>

          <div className="flex items-center justify-between text-[11px] bg-white px-3 py-2 rounded-lg border border-slate-200 text-slate-700 shadow-2xs">
            <span>Hypothetical Qty: <strong className="text-slate-900 font-mono">{setup.hypothetical_quantity} units</strong></span>
            <span>Capital at Risk: <strong className="text-amber-700 font-mono">{currSym}{setup.capital_at_risk} ({riskPct}%)</strong></span>
          </div>
        </div>
      ) : (
        <div className="bg-slate-50 rounded-xl p-4 text-center text-xs text-slate-500 border border-slate-200">
          {setup?.message || 'Market structure is consolidating or conflicting. Awaiting confirmed BOS setup.'}
        </div>
      )}

      {/* Strict Disclaimer */}
      <div className="flex items-center gap-2 text-[10px] text-slate-500 bg-slate-50 p-2.5 rounded-lg border border-slate-200">
        <ShieldAlert className="h-4 w-4 text-amber-600 shrink-0" />
        <span>
          Mathematical risk simulation for educational and risk-management planning only. The tool never executes live orders.
        </span>
      </div>
    </div>
  );
};
