import React from 'react';
import { useNavigate } from 'react-router-dom';
import { MWBreakoutAlert } from '../types';
import { formatMarketTime, formatCandleDate, formatMarketDateTime } from '../utils/time';
import {
  TrendingUp,
  TrendingDown,
  Target,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  ArrowRight,
  Activity,
  AlertTriangle
} from 'lucide-react';

interface MWBreakoutCardProps {
  alert: MWBreakoutAlert;
  isHero?: boolean;
}

export const MWBreakoutCard: React.FC<MWBreakoutCardProps> = ({ alert, isHero = false }) => {
  const navigate = useNavigate();
  const isW = alert.pattern_type === 'W';
  const currSym = alert.symbol.includes('BTC') || alert.symbol.includes('ETH') ? '$' : '₹';

  const getNormalizedStatus = (): 'TARGET OPEN' | 'TARGET 1 HIT' | 'TARGET 2 HIT' | 'SL HIT' => {
    switch (alert.status) {
      case 'TARGET 2 HIT':
      case 'TARGET_2_HIT':
        return 'TARGET 2 HIT';
      case 'TARGET 1 HIT':
      case 'TARGET_1_HIT':
        return 'TARGET 1 HIT';
      case 'SL HIT':
      case 'INVALIDATED':
        return 'SL HIT';
      case 'TARGET OPEN':
      case 'ACTIVE':
      default:
        return 'TARGET OPEN';
    }
  };

  const normStatus = getNormalizedStatus();
  const target2Val = alert.target_2 != null ? alert.target_2 : (
    isW ? alert.neckline_price + 2.0 * alert.pattern_height : alert.neckline_price - 2.0 * alert.pattern_height
  );

  const getStatusBadge = () => {
    switch (normStatus) {
      case 'TARGET 1 HIT':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-600 border border-emerald-500/30">
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span>TARGET 1 HIT</span>
          </span>
        );
      case 'TARGET 2 HIT':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-600/15 text-emerald-700 border border-emerald-500/40">
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span>TARGET 2 HIT</span>
          </span>
        );
      case 'SL HIT':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-rose-500/10 text-rose-600 border border-rose-500/30">
            <XCircle className="h-3.5 w-3.5" />
            <span>SL HIT</span>
          </span>
        );
      case 'TARGET OPEN':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-blue-500/10 text-blue-600 border border-blue-500/30">
            <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
            <span>TARGET OPEN</span>
          </span>
        );
    }
  };

  return (
    <div
      className={`rounded-2xl border transition-all shadow-xs hover:shadow-md flex flex-col justify-between ${
        isW
          ? 'bg-gradient-to-b from-white to-emerald-50/20 border-emerald-200/80 hover:border-emerald-300'
          : 'bg-gradient-to-b from-white to-rose-50/20 border-rose-200/80 hover:border-rose-300'
      } ${isHero ? 'p-5 sm:p-6 ring-2 ring-blue-500/20 shadow-md' : 'p-4 sm:p-5'}`}
    >
      <div>
        {/* Card Header: Pattern Badge, Timeframe & Status */}
        <div className="flex flex-wrap items-start justify-between gap-2 border-b pb-3 border-slate-100 min-w-0">
          <div className="space-y-1 min-w-0">
            <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap min-w-0">
              <span
                className={`inline-flex items-center gap-1 sm:gap-1.5 px-2 sm:px-2.5 py-0.5 rounded-lg text-[10px] sm:text-xs font-black tracking-wide ${
                  isW
                    ? 'bg-emerald-600 text-white shadow-xs'
                    : 'bg-rose-600 text-white shadow-xs'
                }`}
              >
                {isW ? <TrendingUp className="h-3 sm:h-3.5 w-3 sm:w-3.5" /> : <TrendingDown className="h-3 sm:h-3.5 w-3 sm:w-3.5" />}
                <span>{isW ? '🟢 W BREAKOUT' : '🔴 M BREAKDOWN'}</span>
              </span>

              <span
                className={`text-[10px] sm:text-[11px] font-extrabold uppercase px-1.5 sm:px-2 py-0.5 rounded-md border ${
                  isW
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : 'bg-rose-50 text-rose-700 border-rose-200'
                }`}
              >
                {isW ? 'UP' : 'DOWN'}
              </span>
            </div>

            <div className="flex items-center gap-2 pt-1">
              <span className="font-extrabold text-base sm:text-lg text-slate-900 truncate">
                {alert.symbol}
              </span>
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-bold text-xs font-mono border border-slate-200 shrink-0">
                {alert.timeframe}
              </span>
            </div>
          </div>

          <div className="shrink-0">{getStatusBadge()}</div>
        </div>

        {/* Breakout Timestamp in Asia/Kolkata (IST) */}
        <div className="py-2 sm:py-2.5 flex flex-wrap items-center justify-between gap-1 text-[11px] sm:text-xs bg-slate-50/80 px-2.5 sm:px-3 rounded-xl my-2.5 sm:my-3 border border-slate-100">
          <div className="flex items-center gap-1.5 text-slate-600">
            <Clock className="h-3.5 w-3.5 text-blue-600 shrink-0" />
            <span>Breakout Confirmed:</span>
          </div>
          <div className="text-right font-mono font-bold text-blue-600">
            {formatMarketDateTime(alert.breakout_candle_timestamp, alert.symbol)}
          </div>
        </div>

        {/* Structural Metrics Grid */}
        <div className="grid grid-cols-2 gap-2 text-xs py-1">
          {/* Pattern Column */}
          <div className="p-2.5 rounded-xl bg-slate-50/60 border border-slate-100 space-y-1.5">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
              Pattern Geometry
            </div>
            <div>
              <div className="flex justify-between text-slate-700">
                <span>{isW ? 'Low 1 (Pt 1):' : 'High 1 (Pt 1):'}</span>
                <span className="font-mono font-bold">{currSym}{alert.s1_price.toLocaleString()}</span>
              </div>
              {alert.s1_timestamp && (
                <div className="text-[10px] font-mono text-slate-400 text-right">
                  {formatMarketDateTime(alert.s1_timestamp, alert.symbol)}
                </div>
              )}
            </div>
            <div>
              <div className="flex justify-between text-slate-700">
                <span>Neckline:</span>
                <span className="font-mono font-bold text-purple-700">{currSym}{alert.neckline_price.toLocaleString()}</span>
              </div>
              {alert.neckline_timestamp && (
                <div className="text-[10px] font-mono text-purple-600/70 text-right">
                  {formatMarketDateTime(alert.neckline_timestamp, alert.symbol)}
                </div>
              )}
            </div>
            <div>
              <div className="flex justify-between text-slate-700">
                <span>{isW ? 'Low 2 (Pt 2):' : 'High 2 (Pt 2):'}</span>
                <span className="font-mono font-bold">{currSym}{alert.s2_price.toLocaleString()}</span>
              </div>
              {alert.s2_timestamp && (
                <div className="text-[10px] font-mono text-slate-400 text-right">
                  {formatMarketDateTime(alert.s2_timestamp, alert.symbol)}
                </div>
              )}
            </div>
            <div className="flex justify-between text-slate-500 text-[11px] pt-0.5 border-t border-slate-200/60">
              <span>Height:</span>
              <span className="font-mono font-semibold">{currSym}{alert.pattern_height.toFixed(2)}</span>
            </div>
          </div>

          {/* Breakout Confirmation Column */}
          <div className="p-2.5 rounded-xl bg-slate-50/60 border border-slate-100 space-y-1">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
              Confirmation
            </div>
            <div className="flex justify-between text-slate-700">
              <span>Close:</span>
              <span className={`font-mono font-bold ${isW ? 'text-emerald-700' : 'text-rose-700'}`}>
                {currSym}{alert.breakout_close.toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between text-slate-700">
              <span>Trendline:</span>
              <span className="font-mono text-slate-600">{currSym}{alert.trendline_price.toLocaleString()} ✓</span>
            </div>
            <div className="flex justify-between text-slate-700">
              <span>20 EMA:</span>
              <span className="font-mono text-slate-600">{currSym}{alert.ema20_price.toLocaleString()} ✓</span>
            </div>
            <div className="flex justify-between text-slate-700 text-[11px] pt-0.5 border-t border-slate-200/60">
              <span>Volume:</span>
              <span className="font-mono font-bold text-blue-600">{alert.relative_volume}× ✓</span>
            </div>
          </div>
        </div>

        {/* Target & Invalidation Summary */}
        <div className="mt-2.5 p-3 rounded-xl border border-slate-200 bg-white shadow-2xs space-y-2">
          {/* Target 1 */}
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-1.5 font-bold text-slate-700">
              <Target className="h-3.5 w-3.5 text-emerald-600" />
              <span>Target 1:</span>
            </div>
            <span className="font-mono font-extrabold text-emerald-600">
              {currSym}{alert.measured_target.toLocaleString()}
            </span>
          </div>

          {/* Target 2 */}
          <div className="flex items-center justify-between text-xs pt-1 border-t border-slate-100">
            <div className="flex items-center gap-1.5 font-bold text-slate-700">
              <Target className="h-3.5 w-3.5 text-emerald-700" />
              <span>Target 2:</span>
            </div>
            <span className="font-mono font-extrabold text-emerald-700">
              {currSym}{target2Val.toLocaleString()}
            </span>
          </div>

          {/* Invalidation Close / SL */}
          <div className="flex items-center justify-between text-xs text-slate-600 pt-1 border-t border-slate-100">
            <div className="flex items-center gap-1">
              <ShieldAlert className="h-3.5 w-3.5 text-rose-500" />
              <span>Invalidation Close / SL:</span>
            </div>
            <span className="font-mono font-bold text-rose-600">
              {currSym}{alert.invalidation_level.toLocaleString()}
            </span>
          </div>

          {/* Trade Outcome Status */}
          <div className="flex flex-col gap-1 pt-1.5 border-t border-slate-100">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[11px] font-bold uppercase text-slate-500">Status:</span>
              <span
                className={`px-2 py-0.5 rounded-md font-mono text-[11px] font-black tracking-wide ${
                  normStatus === 'TARGET 2 HIT'
                    ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                    : normStatus === 'TARGET 1 HIT'
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : normStatus === 'SL HIT'
                    ? 'bg-rose-50 text-rose-700 border border-rose-200'
                    : 'bg-blue-50 text-blue-700 border border-blue-200'
                }`}
              >
                {normStatus}
              </span>
            </div>
            {alert.outcome_timestamp && (
              <div className="text-[10px] font-mono text-slate-500 text-right">
                Hit at: <span className="font-semibold text-slate-700">{formatMarketDateTime(alert.outcome_timestamp, alert.symbol)}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Card Footer: Quality Score & Action Button */}
      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5 text-slate-400" />
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-mono font-bold ${
                alert.quality_score >= 85
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-blue-100 text-blue-800'
              }`}
            >
              VALUE: {alert.quality_score}/100
            </span>
          </div>
          <span className="text-[10px] text-slate-500 font-medium">
            Reversal {alert.reversal_score ?? 40} • Trendline {alert.trendline_score ?? 0} • EMA {alert.ema_score ?? 0}
          </span>
        </div>

        <button
          onClick={() => navigate(`/mw-breakouts/${encodeURIComponent(alert.alert_id)}`)}
          className="min-h-[44px] min-w-[120px] px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 bg-slate-900 hover:bg-blue-600 text-white shadow-xs cursor-pointer active:scale-98"
        >
          <span>View Details</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
};
