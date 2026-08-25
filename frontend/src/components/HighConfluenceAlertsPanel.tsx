import React, { useState } from 'react';
import { HighConfluenceAlert } from '../types';
import { formatMarketTime } from '../utils/time';
import { api } from '../services/api';
import { 
  Zap, 
  CheckCircle2, 
  Trash2, 
  ShieldAlert, 
  Flame, 
  TrendingUp, 
  TrendingDown, 
  Layers,
  Activity,
  Clock,
  Target,
  AlertTriangle,
  Info,
  Compass
} from 'lucide-react';

interface HighConfluenceAlertsPanelProps {
  alerts: HighConfluenceAlert[];
  currentSymbol: string;
  onClearAlerts?: () => void;
  onAlertTriggered?: (alert: HighConfluenceAlert) => void;
}

export const HighConfluenceAlertsPanel: React.FC<HighConfluenceAlertsPanelProps> = ({
  alerts,
  currentSymbol,
  onClearAlerts,
  onAlertTriggered
}) => {
  const [filterMode, setFilterMode] = useState<'ALL' | 'THIS_SYMBOL' | 'TL_EMA_VOL' | 'WM_PATTERN'>('ALL');
  const [isTriggeringTest, setIsTriggeringTest] = useState(false);

  const filteredAlerts = alerts.filter((a) => {
    if (filterMode === 'THIS_SYMBOL' && a.symbol.toUpperCase() !== currentSymbol.toUpperCase()) {
      return false;
    }
    if (filterMode === 'TL_EMA_VOL' && !a.alert_type.includes('EMA_VOLUME')) {
      return false;
    }
    if (filterMode === 'WM_PATTERN' && !a.alert_type.includes('PATTERN_TRENDLINE')) {
      return false;
    }
    return true;
  });

  const handleClear = async () => {
    try {
      await api.clearHighConfluenceAlerts();
      if (onClearAlerts) onClearAlerts();
    } catch (err) {
      console.error('Failed to clear high-confluence alerts', err);
    }
  };

  const handleTestAlert = async (type: 'TRENDLINE_EMA_VOLUME_UP_BREAKOUT' | 'W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT' | 'M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT') => {
    setIsTriggeringTest(true);
    try {
      const alert = await api.triggerTestHighConfluenceAlert(type);
      if (onAlertTriggered) onAlertTriggered(alert);
    } catch (err) {
      console.error('Failed to trigger test high-confluence alert', err);
    } finally {
      setIsTriggeringTest(false);
    }
  };

  const getCurrencySymbol = (symbol: string) => {
    return symbol.includes('BTC') || symbol.includes('USD') ? '$' : '₹';
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden transition-all w-full min-w-0">
      {/* Header Bar */}
      <div className="p-3.5 sm:px-5 sm:py-4 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-3 bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-950 text-white min-w-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2 sm:gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-rose-500/20 border border-rose-500/40 flex items-center justify-center text-rose-400 shrink-0">
              <ShieldAlert className="h-5 w-5 animate-pulse" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-sm sm:text-base font-black tracking-tight text-white flex items-center gap-1.5 truncate">
                  🚨 HIGH-CONFLUENCE BREAKOUT ALERTS
                </h2>
                {alerts.length > 0 && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-rose-500 text-white animate-pulse shrink-0">
                    {alerts.length} ACTIVE
                  </span>
                )}
              </div>
              <p className="text-[11px] sm:text-xs text-slate-300 font-medium truncate sm:whitespace-normal">
                Precision breakout alerts based on Trendline + 20 EMA + Volume or W/M + Trendline + 20 EMA.
              </p>
            </div>
          </div>
        </div>

        {/* Filter Pills and Actions */}
        <div className="flex flex-wrap items-center gap-2 text-xs min-w-0">
          <div className="flex items-center bg-slate-800/80 p-0.5 sm:p-1 rounded-lg border border-slate-700 overflow-x-auto max-w-full no-scrollbar">
            <button
              onClick={() => setFilterMode('ALL')}
              className={`px-2 sm:px-2.5 py-1 rounded-md font-semibold text-[10px] sm:text-[11px] whitespace-nowrap transition-all cursor-pointer ${
                filterMode === 'ALL'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              All ({alerts.length})
            </button>
            <button
              onClick={() => setFilterMode('THIS_SYMBOL')}
              className={`px-2 sm:px-2.5 py-1 rounded-md font-semibold text-[10px] sm:text-[11px] whitespace-nowrap transition-all cursor-pointer ${
                filterMode === 'THIS_SYMBOL'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {currentSymbol}
            </button>
            <button
              onClick={() => setFilterMode('TL_EMA_VOL')}
              className={`px-2 sm:px-2.5 py-1 rounded-md font-semibold text-[10px] sm:text-[11px] whitespace-nowrap transition-all cursor-pointer ${
                filterMode === 'TL_EMA_VOL'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              TL+EMA+Vol
            </button>
            <button
              onClick={() => setFilterMode('WM_PATTERN')}
              className={`px-2 sm:px-2.5 py-1 rounded-md font-semibold text-[10px] sm:text-[11px] whitespace-nowrap transition-all cursor-pointer ${
                filterMode === 'WM_PATTERN'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              W/M Pattern
            </button>
          </div>

          <div className="flex items-center gap-1.5 flex-wrap">
            <button
              onClick={() => handleTestAlert('TRENDLINE_EMA_VOLUME_UP_BREAKOUT')}
              disabled={isTriggeringTest}
              className="px-2 sm:px-2.5 py-1 sm:py-1.5 bg-emerald-600/80 hover:bg-emerald-600 text-white rounded-lg font-bold text-[10px] sm:text-[11px] transition-all flex items-center gap-1 border border-emerald-500/50 cursor-pointer disabled:opacity-50 min-h-[30px]"
              title="Trigger simulated Type 1 Precision Breakout"
            >
              <Zap className="h-3.5 w-3.5" />
              + Test TL+EMA
            </button>

            <button
              onClick={() => handleTestAlert('W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT')}
              disabled={isTriggeringTest}
              className="px-2 sm:px-2.5 py-1 sm:py-1.5 bg-purple-600/80 hover:bg-purple-600 text-white rounded-lg font-bold text-[10px] sm:text-[11px] transition-all flex items-center gap-1 border border-purple-500/50 cursor-pointer disabled:opacity-50 min-h-[30px]"
              title="Trigger simulated Type 2 W Pattern Breakout"
            >
              <Layers className="h-3.5 w-3.5" />
              + Test W-Pat
            </button>

            <button
              onClick={() => handleTestAlert('M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT')}
              disabled={isTriggeringTest}
              className="px-2 sm:px-2.5 py-1 sm:py-1.5 bg-rose-600/80 hover:bg-rose-600 text-white rounded-lg font-bold text-[10px] sm:text-[11px] transition-all flex items-center gap-1 border border-rose-500/50 cursor-pointer disabled:opacity-50 min-h-[30px]"
              title="Trigger simulated Type 2 M Pattern Breakout"
            >
              <Layers className="h-3.5 w-3.5" />
              + Test M-Pat
            </button>

            {alerts.length > 0 && (
              <button
                onClick={handleClear}
                className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-rose-400 rounded-lg transition-all border border-slate-700 cursor-pointer min-h-[30px] min-w-[30px] flex items-center justify-center"
                title="Clear High-Confluence Alerts"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Alert Cards Container */}
      <div className="p-3 sm:p-4 bg-slate-50/50 min-w-0">
        {filteredAlerts.length === 0 ? (
          <div className="py-12 px-4 text-center rounded-xl bg-white border border-dashed border-slate-200 flex flex-col items-center justify-center">
            <div className="h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-3">
              <Activity className="h-6 w-6 text-slate-400" />
            </div>
            <h3 className="text-sm font-bold text-slate-700">
              No confirmed high-confluence breakouts yet.
            </h3>
            <p className="text-xs text-slate-500 mt-1 max-w-md text-center leading-relaxed">
              Waiting for high-probability market structure confirmations:
              <br />
              <span className="font-semibold text-slate-600">• Trendline + 20 EMA + Volume Breakout</span>
              <br />
              <span className="font-semibold text-slate-600">• W/M Pattern + Trendline + 20 EMA Breakout</span>
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 min-w-0">
            {filteredAlerts.map((alert) => {
              const isBull = alert.direction === 'UP';
              const isWM = alert.alert_type.includes('PATTERN_TRENDLINE');
              const currSym = getCurrencySymbol(alert.symbol);
              const breakTimestamp = alert.breakout_candle_timestamp || alert.timestamp;
              const targetAnalysis = alert.target_analysis;
              const qualityScore = alert.pattern_quality_score || alert.evidence_score;

              return (
                <div
                  key={alert.id}
                  className={`rounded-2xl border p-3.5 sm:p-4 shadow-2xs transition-all relative overflow-hidden flex flex-col justify-between min-w-0 ${
                    isWM
                      ? isBull
                        ? 'bg-gradient-to-br from-purple-50/70 via-white to-purple-50/30 border-purple-200/90 ring-1 ring-purple-100'
                        : 'bg-gradient-to-br from-rose-50/70 via-white to-rose-50/30 border-rose-200/90 ring-1 ring-rose-100'
                      : isBull
                      ? 'bg-gradient-to-br from-emerald-50/70 via-white to-emerald-50/30 border-emerald-200/90 ring-1 ring-emerald-100'
                      : 'bg-gradient-to-br from-rose-50/70 via-white to-rose-50/30 border-rose-200/90 ring-1 ring-rose-100'
                  }`}
                >
                  <div>
                    {/* Header: Direction Badge + Exact Breakout Time in IST */}
                    <div className="flex flex-wrap items-center justify-between gap-1.5 sm:gap-2 mb-2">
                      <span
                        className={`px-2 sm:px-2.5 py-1 rounded-lg text-[10px] sm:text-[11px] font-black uppercase tracking-wide flex items-center gap-1 sm:gap-1.5 shadow-2xs ${
                          isBull
                            ? 'bg-emerald-600 text-white'
                            : 'bg-rose-600 text-white'
                        }`}
                      >
                        {isBull ? (
                          <TrendingUp className="h-3.5 w-3.5" />
                        ) : (
                          <TrendingDown className="h-3.5 w-3.5" />
                        )}
                        {isWM
                          ? isBull
                            ? '🟢 W PATTERN + TL + EMA'
                            : '🔴 M PATTERN + TL + EMA'
                          : isBull
                          ? '🟢 TRENDLINE + EMA + VOL'
                          : '🔴 TRENDLINE + EMA + VOL'}
                      </span>

                      <div className="flex items-center gap-1 text-[10px] sm:text-[11px] font-mono font-bold text-slate-700 bg-white/90 px-1.5 sm:px-2 py-0.5 rounded-md border border-slate-200 shrink-0">
                        <Clock className="h-3 w-3 text-slate-400" />
                        {formatMarketTime(breakTimestamp, alert.symbol)}
                      </div>
                    </div>

                    {/* Symbol & Timeframe Banner */}
                    <div className="flex items-center justify-between py-1 border-b border-slate-200/60 mb-2.5">
                      <span className="text-xs font-black text-slate-900 tracking-tight">
                        {alert.symbol}
                      </span>
                      <span className="text-[10px] font-extrabold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-100">
                        {alert.timeframe} TIMEFRAME
                      </span>
                    </div>

                    {/* Structure Details (for W/M Patterns) */}
                    {isWM && alert.first_swing_price && alert.second_swing_price && (
                      <div className="mb-2.5 p-2 bg-slate-100/70 rounded-lg text-[10px] font-mono border border-slate-200/50 space-y-1 text-slate-600">
                        <div className="flex items-center justify-between">
                          <span>{isBull ? '1st Swing Low:' : '1st Swing High:'}</span>
                          <span className="font-bold text-slate-800">
                            {currSym}{alert.first_swing_price.toFixed(2)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span>Neckline Pivot:</span>
                          <span className="font-bold text-purple-700">
                            {currSym}{(alert.neckline_price || alert.neckline_level || 0).toFixed(2)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span>{isBull ? '2nd Swing Low:' : '2nd Swing High:'}</span>
                          <span className="font-bold text-slate-800">
                            {currSym}{alert.second_swing_price.toFixed(2)}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Breakout Confluence Checklist */}
                    <div className="bg-white/95 rounded-xl p-3 border border-slate-200/80 space-y-1.5 text-xs font-mono shadow-2xs">
                      <div className="flex items-center justify-between font-bold text-slate-900 pb-1.5 border-b border-slate-100">
                        <span className="font-sans text-[11px] text-slate-500 font-normal">
                          Breakout Candle Close:
                        </span>
                        <span className="text-[13px] font-black text-slate-900">
                          {currSym}{(alert.breakout_candle_close || alert.breakout_close || 0).toFixed(2)}
                        </span>
                      </div>

                      {isWM && (alert.neckline_price || alert.neckline_level) && (
                        <div className="flex items-center justify-between text-slate-700">
                          <span className="font-sans text-[11px] text-slate-500">
                            Neckline:
                          </span>
                          <span className="flex items-center gap-1 font-bold text-purple-800">
                            {currSym}{(alert.neckline_price || alert.neckline_level || 0).toFixed(2)}
                            <CheckCircle2 className="h-3.5 w-3.5 text-purple-600 inline" />
                          </span>
                        </div>
                      )}

                      <div className="flex items-center justify-between text-slate-700">
                        <span className="font-sans text-[11px] text-slate-500">
                          Trendline Level:
                        </span>
                        <span className="flex items-center gap-1 font-bold text-slate-800">
                          {currSym}{alert.trendline_level.toFixed(2)}
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 inline" />
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-slate-700">
                        <span className="font-sans text-[11px] text-slate-500">
                          20 EMA Level:
                        </span>
                        <span className="flex items-center gap-1 font-bold text-slate-800">
                          {currSym}{alert.ema20_level.toFixed(2)}
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 inline" />
                        </span>
                      </div>

                      {!isWM && alert.volume_ratio && (
                        <div className="flex items-center justify-between text-slate-700">
                          <span className="font-sans text-[11px] text-slate-500">
                            Rel. Volume:
                          </span>
                          <span className="flex items-center gap-1 font-bold text-emerald-700">
                            {alert.volume_ratio.toFixed(2)}×
                            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 inline" />
                          </span>
                        </div>
                      )}

                      <div className="flex items-center justify-between text-slate-700 pt-1 border-t border-slate-100">
                        <span className="font-sans text-[11px] text-slate-500">
                          Candle State:
                        </span>
                        <span className="text-[10px] font-black text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded flex items-center gap-1 border border-emerald-200">
                          CONFIRMED CLOSED ✓
                        </span>
                      </div>
                    </div>

                    {/* TARGET ANALYSIS SECTION */}
                    {targetAnalysis ? (
                      <div className="mt-2.5 bg-slate-900 text-white p-2.5 rounded-xl text-[10px] font-mono space-y-1.5 border border-slate-800">
                        <div className="flex items-center justify-between pb-1 border-b border-slate-800">
                          <span className="font-sans text-[10px] font-bold text-rose-400 flex items-center gap-1">
                            <Compass className="h-3 w-3 text-rose-400" />
                            TARGET ANALYSIS (PROJECTION)
                          </span>
                          <span className="text-[9px] bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded">
                            Pattern Height: {currSym}{targetAnalysis.pattern_height.toFixed(2)}
                          </span>
                        </div>

                        <div className="flex items-center justify-between">
                          <span className="text-slate-400">Target 1 (Measured):</span>
                          <span className="font-bold text-emerald-400">
                            {currSym}{targetAnalysis.measured_target.toFixed(2)}
                          </span>
                        </div>

                        {targetAnalysis.nearest_obstacle && (
                          <div className="flex items-center justify-between text-amber-300">
                            <span className="text-slate-400 flex items-center gap-1">
                              <AlertTriangle className="h-2.5 w-2.5 text-amber-400" />
                              Nearest Obstacle:
                            </span>
                            <span className="font-bold">
                              {currSym}{targetAnalysis.nearest_obstacle.toFixed(2)}
                            </span>
                          </div>
                        )}

                        {targetAnalysis.target_2 && (
                          <div className="flex items-center justify-between">
                            <span className="text-slate-400">Target 2 (Major S/R):</span>
                            <span className="font-bold text-cyan-400">
                              {currSym}{targetAnalysis.target_2.toFixed(2)}
                            </span>
                          </div>
                        )}

                        <div className="flex items-center justify-between pt-1 border-t border-slate-800 text-slate-400">
                          <span className="text-rose-400">Invalidation:</span>
                          <span className="font-bold text-rose-400">
                            Close beyond {currSym}{targetAnalysis.invalidation_level.toFixed(2)}
                          </span>
                        </div>

                        {targetAnalysis.interpretation && (
                          <p className="text-[9px] font-sans text-slate-300 pt-1 border-t border-slate-800 leading-snug">
                            {targetAnalysis.interpretation}
                          </p>
                        )}
                      </div>
                    ) : (
                      (alert.next_level || alert.invalidation_level) && (
                        <div className="mt-2.5 grid grid-cols-2 gap-2 text-[10px] font-mono">
                          {alert.next_level && (
                            <div className="bg-slate-50 p-1.5 rounded-lg border border-slate-200">
                              <span className="text-slate-400 block font-sans text-[9px] flex items-center gap-1">
                                <Target className="h-2.5 w-2.5 text-emerald-600" />
                                Next Target:
                              </span>
                              <span className="font-bold text-slate-800">
                                {currSym}{alert.next_level.toFixed(2)}
                              </span>
                            </div>
                          )}
                          {alert.invalidation_level && (
                            <div className="bg-slate-50 p-1.5 rounded-lg border border-slate-200">
                              <span className="text-slate-400 block font-sans text-[9px] flex items-center gap-1">
                                <AlertTriangle className="h-2.5 w-2.5 text-rose-500" />
                                Invalidation:
                              </span>
                              <span className="font-bold text-rose-700">
                                {currSym}{alert.invalidation_level.toFixed(2)}
                              </span>
                            </div>
                          )}
                        </div>
                      )
                    )}
                  </div>

                  {/* Bottom Footer: Quality Score */}
                  <div className="mt-3 pt-2.5 border-t border-slate-200/70 flex items-center justify-between text-xs">
                    <span className="text-slate-500 font-medium flex items-center gap-1 text-[11px]">
                      <Flame className="h-3.5 w-3.5 text-orange-500" /> Pattern Quality
                    </span>
                    <span className="font-black px-2.5 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 text-[11px]">
                      Score: {qualityScore}/100
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
