import React, { useState } from 'react';
import { BacktestRequest, BacktestResult, InstrumentConfig } from '../types';
import { api } from '../services/api';
import { formatMarketDateTime } from '../utils/time';
import {
  Play,
  TrendingUp,
  BarChart2,
  Percent,
  X,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  ShieldCheck,
  AlertCircle
} from 'lucide-react';

interface BacktestModalProps {
  instruments: InstrumentConfig[];
  selectedSymbol: string;
  onClose?: () => void;
}

export const BacktestModal: React.FC<BacktestModalProps> = ({
  instruments,
  selectedSymbol,
  onClose
}) => {
  const [symbol, setSymbol] = useState<string>(selectedSymbol || 'NIFTY 50');
  const [timeframe, setTimeframe] = useState<string>('15M');
  const [strategy, setStrategy] = useState<'BOS_CONTINUATION' | 'CHOCH_REVERSAL' | 'MULTI_TF_ALIGNMENT'>('BOS_CONTINUATION');
  const [rrRatio, setRrRatio] = useState<number>(2.0);
  const [slAtrMult, setSlAtrMult] = useState<number>(1.5);
  const [slippageBps, setSlippageBps] = useState<number>(2.0);
  const [feeBps, setFeeBps] = useState<number>(3.0);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleRunBacktest = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMsg(null);

    const targetInst = instruments.find((i) => i.symbol.toUpperCase() === symbol.toUpperCase());
    const ticker = targetInst?.ticker || symbol;

    try {
      const res = await api.runBacktest({
        symbol,
        ticker,
        timeframe,
        strategy,
        risk_reward_ratio: Number(rrRatio),
        stop_loss_atr_multiple: Number(slAtrMult),
        slippage_bps: Number(slippageBps),
        fee_bps: Number(feeBps)
      });
      setResult(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'Backtest failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full space-y-6">
      {/* Configuration Form Panel */}
      <div className="glass-panel rounded-2xl p-6 shadow-xl border border-slate-800">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-500/20 text-blue-400 border border-blue-500/30">
              <BarChart2 className="h-5 w-5" />
            </div>
            <div>
              <h2 className="font-bold text-base text-slate-100">
                Market Structure Strategy Backtester
              </h2>
              <p className="text-xs text-slate-400">
                Validate BOS & CHoCH historical performance with realistic slippage and no look-ahead bias
              </p>
            </div>
          </div>
          {onClose && (
            <button onClick={onClose} className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-white">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        <form onSubmit={handleRunBacktest} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          {/* Symbol */}
          <div>
            <label className="text-slate-400 font-semibold block mb-1">Instrument</label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500"
            >
              {instruments.map((i) => (
                <option key={i.symbol} value={i.symbol}>
                  {i.symbol} ({i.ticker})
                </option>
              ))}
            </select>
          </div>

          {/* Timeframe */}
          <div>
            <label className="text-slate-400 font-semibold block mb-1">Timeframe</label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
            >
              <option value="4H">4H</option>
              <option value="1H">1H</option>
              <option value="15M">15M</option>
              <option value="5M">5M</option>
            </select>
          </div>

          {/* Strategy */}
          <div>
            <label className="text-slate-400 font-semibold block mb-1">Strategy Rule</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as any)}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500"
            >
              <option value="BOS_CONTINUATION">BOS Trend Continuation</option>
              <option value="CHOCH_REVERSAL">CHoCH Trend Reversal</option>
              <option value="MULTI_TF_ALIGNMENT">Multi-TF Volume Alignment</option>
            </select>
          </div>

          {/* R:R Ratio */}
          <div>
            <label className="text-slate-400 font-semibold block mb-1">Risk : Reward Ratio</label>
            <input
              type="number"
              step={0.5}
              min={1.0}
              max={5.0}
              value={rrRatio}
              onChange={(e) => setRrRatio(Number(e.target.value))}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
            />
          </div>

          {/* Stop Loss ATR Multiplier */}
          <div>
            <label className="text-slate-400 font-semibold block mb-1">Stop Loss (ATR Multiple)</label>
            <input
              type="number"
              step={0.1}
              min={0.5}
              max={4.0}
              value={slAtrMult}
              onChange={(e) => setSlAtrMult(Number(e.target.value))}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
            />
          </div>

          {/* Slippage */}
          <div>
            <label className="text-slate-400 font-semibold block mb-1">Slippage (bps)</label>
            <input
              type="number"
              step={0.5}
              value={slippageBps}
              onChange={(e) => setSlippageBps(Number(e.target.value))}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
            />
          </div>

          {/* Fee */}
          <div>
            <label className="text-slate-400 font-semibold block mb-1">Round-trip Fee (bps)</label>
            <input
              type="number"
              step={0.5}
              value={feeBps}
              onChange={(e) => setFeeBps(Number(e.target.value))}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
            />
          </div>

          {/* Submit Button */}
          <div className="flex items-end">
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-blue-500/20 transition-all disabled:opacity-50"
            >
              <Play className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
              <span>{isLoading ? 'Simulating Strategy...' : 'Run Backtest'}</span>
            </button>
          </div>
        </form>

        {errorMsg && (
          <div className="mt-4 p-3 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}
      </div>

      {/* Results View */}
      {result && (
        <div className="space-y-6">
          {/* KPI Summary Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            <div className="glass-card rounded-xl p-3.5 border border-slate-800 text-center">
              <span className="text-[11px] text-slate-400 block font-medium">Total Signals</span>
              <span className="text-xl font-extrabold font-mono text-slate-100">{result.total_trades}</span>
            </div>

            <div className="glass-card rounded-xl p-3.5 border border-slate-800 text-center">
              <span className="text-[11px] text-slate-400 block font-medium">Win Rate</span>
              <span className={`text-xl font-extrabold font-mono ${result.win_rate_pct >= 50 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {result.win_rate_pct}%
              </span>
            </div>

            <div className="glass-card rounded-xl p-3.5 border border-slate-800 text-center">
              <span className="text-[11px] text-slate-400 block font-medium">Profit Factor</span>
              <span className={`text-xl font-extrabold font-mono ${result.profit_factor >= 1.5 ? 'text-emerald-400' : 'text-slate-200'}`}>
                {result.profit_factor}x
              </span>
            </div>

            <div className="glass-card rounded-xl p-3.5 border border-slate-800 text-center">
              <span className="text-[11px] text-slate-400 block font-medium">Net Return</span>
              <span className={`text-xl font-extrabold font-mono ${result.total_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {result.total_return_pct >= 0 ? '+' : ''}{result.total_return_pct}%
              </span>
            </div>

            <div className="glass-card rounded-xl p-3.5 border border-slate-800 text-center">
              <span className="text-[11px] text-slate-400 block font-medium">Max Drawdown</span>
              <span className="text-xl font-extrabold font-mono text-rose-400">
                -{result.max_drawdown_pct}%
              </span>
            </div>

            <div className="glass-card rounded-xl p-3.5 border border-slate-800 text-center">
              <span className="text-[11px] text-slate-400 block font-medium">Avg Excursion (MFE)</span>
              <span className="text-xl font-extrabold font-mono text-cyan-400">
                +{result.avg_favorable_excursion_pct}%
              </span>
            </div>
          </div>

          {/* Trade History Table */}
          <div className="glass-panel rounded-2xl p-5 shadow-xl">
            <h3 className="font-bold text-sm text-slate-100 mb-3">
              Historical Trade Executions ({result.trades.length})
            </h3>

            <div className="overflow-x-auto rounded-xl border border-slate-800">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="bg-slate-900 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                    <th className="py-2.5 px-3">#</th>
                    <th className="py-2.5 px-3">Entry Time</th>
                    <th className="py-2.5 px-3">Type</th>
                    <th className="py-2.5 px-3 font-mono">Entry</th>
                    <th className="py-2.5 px-3 font-mono">Exit</th>
                    <th className="py-2.5 px-3 font-mono">PnL %</th>
                    <th className="py-2.5 px-3">Reason</th>
                    <th className="py-2.5 px-3 font-mono">MFE / MAE</th>
                    <th className="py-2.5 px-3 text-center">Bars</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-sans">
                  {result.trades.map((t) => (
                    <tr key={t.trade_id} className="hover:bg-slate-900/40">
                      <td className="py-2 px-3 text-slate-500 font-mono">{t.trade_id}</td>
                      <td className="py-2 px-3 text-slate-300 font-mono text-[11px]">
                        {formatMarketDateTime(t.entry_time, selectedSymbol)}
                      </td>
                      <td className="py-2 px-3 font-bold">
                        <span className={`px-2 py-0.5 rounded text-[10px] ${
                          t.direction === 'LONG'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-rose-500/20 text-rose-400'
                        }`}>
                          {t.direction}
                        </span>
                      </td>
                      <td className="py-2 px-3 font-mono text-slate-300">₹{t.entry_price}</td>
                      <td className="py-2 px-3 font-mono text-slate-300">₹{t.exit_price}</td>
                      <td className={`py-2 px-3 font-mono font-bold ${t.pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct}%
                      </td>
                      <td className="py-2 px-3 text-slate-400 text-[11px]">{t.exit_reason}</td>
                      <td className="py-2 px-3 font-mono text-[11px] text-slate-400">
                        <span className="text-emerald-400">+{t.mfe_pct}%</span> / <span className="text-rose-400">-{t.mae_pct}%</span>
                      </td>
                      <td className="py-2 px-3 text-center text-slate-400 font-mono">{t.bars_held}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
