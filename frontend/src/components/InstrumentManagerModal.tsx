import React, { useState } from 'react';
import { InstrumentConfig } from '../types';
import { api } from '../services/api';
import { Plus, Trash2, X, Check, ShieldAlert } from 'lucide-react';

interface InstrumentManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  instruments: InstrumentConfig[];
  onRefresh: () => void;
}

export const InstrumentManagerModal: React.FC<InstrumentManagerModalProps> = ({
  isOpen,
  onClose,
  instruments,
  onRefresh
}) => {
  const [symbol, setSymbol] = useState('');
  const [ticker, setTicker] = useState('');
  const [exchange, setExchange] = useState('NSE');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol || !ticker) return;

    if (instruments.length >= 10) {
      setErrorMsg('Maximum 10 instruments limit reached. Remove one first.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      await api.addInstrument({
        symbol: symbol.toUpperCase(),
        ticker: ticker.trim(),
        exchange: exchange.toUpperCase(),
        asset_type: 'EQUITY',
        is_active: true
      });
      setSymbol('');
      setTicker('');
      onRefresh();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to add instrument');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (sym: string) => {
    try {
      await api.deleteInstrument(sym);
      onRefresh();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to delete');
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h3 className="font-bold text-base text-slate-100">
              Configure Watchlist ({instruments.length}/10 Instruments)
            </h3>
            <p className="text-xs text-slate-400">
              Manage Indian & Global equities, indices, and forex pairs
            </p>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg bg-slate-800 text-slate-400 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Add Form */}
        <form onSubmit={handleAdd} className="bg-slate-950/80 p-4 rounded-xl border border-slate-800 space-y-3">
          <span className="text-xs font-bold text-slate-200 block">Add New Instrument</span>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div>
              <label className="text-slate-400 text-[10px] block mb-1">Display Symbol</label>
              <input
                type="text"
                placeholder="e.g. INFY"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-500 uppercase"
              />
            </div>
            <div>
              <label className="text-slate-400 text-[10px] block mb-1">Yahoo Ticker</label>
              <input
                type="text"
                placeholder="e.g. INFY.NS"
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <label className="text-slate-400 text-[10px] block mb-1">Exchange</label>
              <input
                type="text"
                value={exchange}
                onChange={(e) => setExchange(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-500 uppercase"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting || instruments.length >= 10}
            className="w-full py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold text-xs flex items-center justify-center gap-1.5 transition-all disabled:opacity-50"
          >
            <Plus className="h-4 w-4" />
            <span>Add Instrument ({instruments.length}/10)</span>
          </button>
        </form>

        {errorMsg && (
          <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-xs">
            {errorMsg}
          </div>
        )}

        {/* Current List */}
        <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">
            Currently Monitored Instruments
          </span>
          {instruments.map((inst) => (
            <div
              key={inst.symbol}
              className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/50 border border-slate-800 text-xs"
            >
              <div className="flex items-center gap-2">
                <span className="font-bold text-slate-100">{inst.symbol}</span>
                <span className="font-mono text-[11px] text-slate-400">({inst.ticker})</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-cyan-400 font-semibold">
                  {inst.exchange}
                </span>
              </div>
              <button
                onClick={() => handleDelete(inst.symbol)}
                className="p-1 text-slate-500 hover:text-rose-400 transition-all"
                title="Remove instrument"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
