import React, { useState } from 'react';
import { AlertNotification, AlertRule } from '../types';
import { api } from '../services/api';
import { formatMarketTime, formatMarketDateTime } from '../utils/time';
import {
  Bell,
  Volume2,
  VolumeX,
  X,
  Trash2,
  Plus,
  Radio,
  Zap,
  Check,
  Filter
} from 'lucide-react';

interface AlertsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  notifications: AlertNotification[];
  rules: AlertRule[];
  onRefreshRules: () => void;
  onClearNotifications: () => void;
  soundEnabled: boolean;
  onToggleSound: () => void;
  onTestAlertTriggered?: (notif: AlertNotification) => void;
}

export const AlertsDrawer: React.FC<AlertsDrawerProps> = ({
  isOpen,
  onClose,
  notifications,
  rules,
  onRefreshRules,
  onClearNotifications,
  soundEnabled,
  onToggleSound,
  onTestAlertTriggered
}) => {
  const [activeTab, setActiveTab] = useState<'notifications' | 'rules'>('notifications');
  const [newSymbol, setNewSymbol] = useState('ALL');
  const [minScore, setMinScore] = useState(80);
  const [filterScore, setFilterScore] = useState<number>(0);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([
    'TREND_LINE_BREAK',
    'RESISTANCE_BREAK',
    'SUPPORT_BREAK'
  ]);
  const [isTriggeringTest, setIsTriggeringTest] = useState(false);

  if (!isOpen) return null;

  const toggleEventType = (type: string) => {
    if (selectedTypes.includes(type)) {
      if (selectedTypes.length > 1) {
        setSelectedTypes(selectedTypes.filter((t) => t !== type));
      }
    } else {
      setSelectedTypes([...selectedTypes, type]);
    }
  };

  const handleTriggerTest = async () => {
    setIsTriggeringTest(true);
    try {
      const testNotif = await api.triggerTestAlert();
      if (testNotif) {
        onRefreshRules();
        onTestAlertTriggered?.(testNotif);
      }
    } catch (e) {
      console.error('Trigger test error:', e);
    } finally {
      setIsTriggeringTest(false);
    }
  };

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createAlertRule({
        symbol: newSymbol.toUpperCase(),
        timeframes: ['4H', '1H', '15M', '5M'],
        event_types: selectedTypes,
        min_evidence_score: minScore,
        is_enabled: true
      });
      onRefreshRules();
      setNewSymbol('ALL');
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteRule = async (id: string) => {
    try {
      await api.deleteAlertRule(id);
      onRefreshRules();
    } catch (e) {
      console.error(e);
    }
  };

  const displayedNotifications = notifications.filter(
    (n) => n.evidence_score >= filterScore
  );

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-xs" onClick={onClose} />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-white border-l border-slate-200 shadow-2xl flex flex-col justify-between">
          {/* Header */}
          <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bell className="h-5 w-5 text-blue-600" />
              <div>
                <h2 className="font-bold text-sm text-slate-900">Breakout & Structure Alerts</h2>
                <p className="text-[10px] text-slate-500">Filtered by Evidence Score & Confirmed Breaks</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={onToggleSound}
                className={`p-1.5 rounded-lg border transition-all ${
                  soundEnabled
                    ? 'bg-blue-50 text-blue-700 border-blue-300'
                    : 'bg-slate-50 text-slate-400 border-slate-200'
                }`}
                title={soundEnabled ? 'Audio Chime Enabled' : 'Audio Chime Muted'}
              >
                {soundEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
              </button>

              <button
                onClick={onClose}
                className="p-1.5 rounded-lg bg-slate-100 text-slate-500 hover:text-slate-900 transition-all"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Tab navigation */}
          <div className="flex border-b border-slate-200 px-5 pt-2">
            <button
              onClick={() => setActiveTab('notifications')}
              className={`pb-2 px-3 text-xs font-semibold border-b-2 transition-all ${
                activeTab === 'notifications'
                  ? 'border-blue-600 text-blue-600 font-bold'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              Alert Feed ({displayedNotifications.length})
            </button>
            <button
              onClick={() => setActiveTab('rules')}
              className={`pb-2 px-3 text-xs font-semibold border-b-2 transition-all ${
                activeTab === 'rules'
                  ? 'border-blue-600 text-blue-600 font-bold'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              Filter Rules ({rules.length})
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-3">
            {activeTab === 'notifications' ? (
              <div className="space-y-3">
                {/* Score Filter Pills */}
                <div className="flex items-center justify-between bg-slate-50 p-2 rounded-xl border border-slate-200 text-xs">
                  <span className="flex items-center gap-1 text-[11px] font-semibold text-slate-600">
                    <Filter className="h-3.5 w-3.5 text-blue-600" /> Filter:
                  </span>
                  <div className="flex gap-1">
                    {[
                      { label: 'All', val: 0 },
                      { label: '≥ 70', val: 70 },
                      { label: '≥ 80 (Strict)', val: 80 },
                      { label: '≥ 90', val: 90 }
                    ].map((f) => (
                      <button
                        key={f.val}
                        onClick={() => setFilterScore(f.val)}
                        className={`px-2 py-0.5 rounded-lg text-[10px] font-bold transition-all ${
                          filterScore === f.val
                            ? 'bg-blue-600 text-white shadow-2xs'
                            : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
                        }`}
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                </div>

                {displayedNotifications.length === 0 ? (
                  <div className="py-16 text-center text-xs text-slate-400 flex flex-col items-center">
                    <Radio className="h-8 w-8 text-blue-500 mb-2 animate-pulse" />
                    <p className="font-semibold text-slate-700">
                      {filterScore > 0
                        ? `No breakout alerts with Score ≥ ${filterScore} yet`
                        : 'Monitoring for Trendline & Resistance Breaks...'}
                    </p>
                    <p className="text-[11px] text-slate-500 mt-1 max-w-xs">
                      Alerts will chime and appear when price confirms a breakout above dynamic trendlines or key levels with evidence score meeting your threshold.
                    </p>
                  </div>
                ) : (
                  displayedNotifications.map((n) => (
                    <div
                      key={n.id}
                      className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col gap-1 text-xs shadow-2xs"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-900 flex items-center gap-1.5">
                          <Zap className="h-3.5 w-3.5 text-blue-600" />
                          {n.symbol}
                        </span>
                        <span className="text-[10px] font-mono text-slate-500">
                          {formatMarketDateTime(n.timestamp, n.symbol)}
                        </span>
                      </div>
                      <p className="text-slate-800 text-[11px] font-semibold leading-relaxed mt-0.5">
                        {n.message}
                      </p>
                      <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-200 font-mono">
                        <span>Break Price: {n.price.toFixed(2)}</span>
                        <span
                          className={`font-bold px-1.5 py-0.5 rounded ${
                            n.evidence_score >= 80
                              ? 'bg-emerald-100 text-emerald-800'
                              : 'bg-blue-100 text-blue-800'
                          }`}
                        >
                          Score: {n.evidence_score}/100
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            ) : (
              <div className="space-y-4">
                {/* Rule Form */}
                <form onSubmit={handleCreateRule} className="bg-slate-50 p-3.5 rounded-xl border border-slate-200 space-y-3">
                  <span className="text-xs font-bold text-slate-800 block">Set Breakout Notification Filters</span>

                  {/* Filter Checklist */}
                  <div className="space-y-1.5">
                    <label className="text-slate-500 text-[10px] block font-semibold">Enabled Notification Events</label>
                    <div className="grid grid-cols-1 gap-1.5">
                      {[
                        { id: 'TREND_LINE_BREAK', label: '🚀 Trendline Breakouts' },
                        { id: 'RESISTANCE_BREAK', label: '💥 Resistance Breakouts' },
                        { id: 'SUPPORT_BREAK', label: '📉 Support Breakdowns' }
                      ].map((item) => {
                        const isChecked = selectedTypes.includes(item.id);
                        return (
                          <button
                            type="button"
                            key={item.id}
                            onClick={() => toggleEventType(item.id)}
                            className={`flex items-center justify-between px-3 py-2 rounded-lg border text-xs text-left transition-all ${
                              isChecked
                                ? 'bg-blue-50 border-blue-300 text-blue-700 font-semibold'
                                : 'bg-white border-slate-200 text-slate-600'
                            }`}
                          >
                            <span>{item.label}</span>
                            {isChecked && <Check className="h-4 w-4 text-blue-600" />}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                    <div>
                      <label className="text-slate-500 text-[10px] block mb-1 font-semibold">Symbol</label>
                      <input
                        type="text"
                        value={newSymbol}
                        onChange={(e) => setNewSymbol(e.target.value)}
                        className="w-full bg-white border border-slate-300 rounded px-2 py-1.5 text-slate-800 text-xs uppercase font-mono"
                        placeholder="ALL or NIFTY 50"
                      />
                    </div>
                    <div>
                      <label className="text-slate-500 text-[10px] block mb-1 font-semibold">Min Evidence Score (e.g. 80)</label>
                      <input
                        type="number"
                        value={minScore}
                        onChange={(e) => setMinScore(Number(e.target.value))}
                        min={0}
                        max={100}
                        className="w-full bg-white border border-slate-300 rounded px-2 py-1.5 text-slate-800 text-xs font-mono font-bold text-blue-600"
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs rounded-xl transition-all flex items-center justify-center gap-1 shadow-2xs"
                  >
                    <Plus className="h-3.5 w-3.5" /> Save / Update Filter Rule
                  </button>
                </form>

                {/* Existing Rules */}
                <div className="space-y-2">
                  <span className="text-[11px] font-bold text-slate-600 uppercase tracking-wider block">
                    Active Breakout Filter Rules ({rules.length})
                  </span>
                  {rules.map((r) => (
                    <div
                      key={r.id}
                      className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-900">{r.symbol}</span>
                          <span className="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5 rounded-full">
                            Score ≥ {r.min_evidence_score}
                          </span>
                        </div>
                        <div className="text-[10px] text-slate-500">
                          Events: {r.event_types.map((t) => t.replace('_BREAK', '')).join(', ')}
                        </div>
                      </div>
                      <button
                        onClick={() => handleDeleteRule(r.id)}
                        className="p-1.5 text-slate-400 hover:text-rose-600 rounded-lg hover:bg-rose-50 transition-all"
                        title="Delete Rule"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between gap-3">
            <button
              onClick={handleTriggerTest}
              disabled={isTriggeringTest}
              className="px-3 py-1.5 rounded-lg bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 text-xs font-semibold transition-all shadow-2xs flex items-center gap-1.5"
            >
              <Zap className="h-3.5 w-3.5 text-blue-600" />
              {isTriggeringTest ? 'Triggering...' : 'Trigger Test Breakout Alert (Score 85)'}
            </button>
            <button
              onClick={onClearNotifications}
              className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-rose-600 text-xs font-medium transition-all"
            >
              Clear Log
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
