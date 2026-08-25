import React from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import {
  TrendingUp,
  Bell,
  RefreshCw,
  Settings,
  Database,
  Layers,
  Sparkles
} from 'lucide-react';

interface NavbarProps {
  currentProvider: string;
  availableProviders: string[];
  onSelectProvider: (provider: string) => void;
  onRefreshAll: () => void;
  isLoading: boolean;
  unreadAlertCount: number;
  mwBreakoutCount?: number;
  mwUnreadCount?: number;
  onOpenAlerts: () => void;
  onOpenBacktest: () => void;
  onOpenSettings: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentProvider,
  availableProviders,
  onSelectProvider,
  onRefreshAll,
  isLoading,
  unreadAlertCount,
  mwBreakoutCount = 0,
  mwUnreadCount = 0,
  onOpenAlerts,
  onOpenBacktest,
  onOpenSettings
}) => {
  const navigate = useNavigate();
  const location = useLocation();

  const isChartActive = location.pathname === '/' || (location.pathname.startsWith('/markets/') && location.pathname !== '/markets');
  const isMarketListActive = location.pathname === '/markets';
  const isMWActive = location.pathname.startsWith('/mw-breakouts');
  const isEventsActive = location.pathname === '/events';
  const isBacktestActive = location.pathname === '/backtest';

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white/95 backdrop-blur-md shadow-xs">
      <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 py-2 sm:py-0 sm:h-16 flex items-center justify-between gap-2 min-w-0">
        {/* Brand & App Title Link */}
        <Link to="/" className="flex items-center gap-2 sm:gap-3 group min-w-0 flex-1 sm:flex-initial">
          <div className="h-9 w-9 sm:h-10 sm:w-10 shrink-0 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-500 to-cyan-500 p-0.5 shadow-md shadow-blue-500/10 flex items-center justify-center group-hover:scale-105 transition-transform">
            <div className="h-full w-full bg-white rounded-[10px] flex items-center justify-center">
              <TrendingUp className="h-4 w-4 sm:h-5 sm:w-5 text-blue-600" />
            </div>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="font-extrabold text-sm sm:text-lg tracking-tight text-slate-900 group-hover:text-blue-600 transition-colors truncate">
                AI Market Analyzer
              </span>
              <span className="text-[9px] sm:text-[10px] font-mono font-bold uppercase px-1.5 sm:px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1 shrink-0">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" /> LIVE
              </span>
            </div>
            <p className="text-[10px] sm:text-[11px] text-slate-500 font-medium hidden sm:block truncate">
              Multi-Timeframe BOS & CHoCH • S/R Liquidity Bands • Target Predictions
            </p>
          </div>
        </Link>

        {/* Desktop View Navigation Tabs */}
        <div className="hidden md:flex items-center gap-1 bg-slate-100 p-1 rounded-xl border border-slate-200 shadow-inner shrink-0">
          <Link
            to="/"
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
              isChartActive
                ? 'bg-blue-600 text-white shadow-xs font-bold'
                : 'text-slate-600 hover:text-slate-900 hover:bg-white'
            }`}
          >
            📈 Live Chart
          </Link>

          <Link
            to="/markets"
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
              isMarketListActive
                ? 'bg-blue-600 text-white shadow-xs font-bold'
                : 'text-slate-600 hover:text-slate-900 hover:bg-white'
            }`}
          >
            🗂️ Markets
          </Link>

          {/* DEDICATED M/W BREAKOUTS TAB */}
          <Link
            to="/mw-breakouts"
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
              isMWActive
                ? 'bg-purple-600 text-white shadow-xs font-bold'
                : 'text-purple-700 hover:text-purple-900 hover:bg-white'
            }`}
          >
            <span>📊 M/W Breakouts</span>
            {mwUnreadCount > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-rose-500 text-white text-[10px] font-mono font-bold animate-pulse shadow-2xs">
                {mwUnreadCount}
              </span>
            )}
          </Link>

          <Link
            to="/events"
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
              isEventsActive
                ? 'bg-blue-600 text-white shadow-xs font-bold'
                : 'text-slate-600 hover:text-slate-900 hover:bg-white'
            }`}
          >
            Structure Log
          </Link>
          <Link
            to="/backtest"
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
              isBacktestActive
                ? 'bg-blue-600 text-white shadow-xs font-bold'
                : 'text-slate-600 hover:text-slate-900 hover:bg-white'
            }`}
          >
            Backtester
          </Link>
        </div>

        {/* Controls & Feed Selector */}
        <div className="flex items-center gap-1.5 sm:gap-2.5 shrink-0">
          {/* Data Feed Selector */}
          <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-xl px-2 py-1 sm:px-2.5 sm:py-1.5 text-[11px] sm:text-xs text-slate-700 shadow-2xs max-w-[115px] sm:max-w-none">
            <Database className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-blue-600 shrink-0" />
            <select
              value={currentProvider}
              onChange={(e) => onSelectProvider(e.target.value)}
              className="bg-transparent text-slate-800 font-medium focus:outline-none cursor-pointer truncate text-[11px] sm:text-xs"
            >
              {availableProviders.map((p) => (
                <option key={p} value={p} className="bg-white text-slate-800">
                  {p === 'yfinance' ? 'Yahoo Live' : p === 'simulated' ? 'Simulated' : p}
                </option>
              ))}
            </select>
          </div>

          {/* Refresh Analysis */}
          <button
            onClick={onRefreshAll}
            disabled={isLoading}
            className="p-1.5 sm:p-2 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 hover:text-slate-900 transition-all disabled:opacity-50 shadow-2xs cursor-pointer min-h-[34px] min-w-[34px] flex items-center justify-center"
            title="Refresh Market Prediction"
          >
            <RefreshCw className={`h-3.5 w-3.5 sm:h-4 sm:w-4 ${isLoading ? 'animate-spin text-blue-600' : ''}`} />
          </button>

          {/* Alerts Notification Button */}
          <button
            onClick={onOpenAlerts}
            className="relative p-1.5 sm:p-2 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 hover:text-slate-900 transition-all shadow-2xs cursor-pointer min-h-[34px] min-w-[34px] flex items-center justify-center"
            title="Breakout Notifications"
          >
            <Bell className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            {unreadAlertCount > 0 && (
              <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-rose-500 text-[9px] font-mono font-bold text-white flex items-center justify-center animate-pulse shadow-xs">
                {unreadAlertCount > 9 ? '9+' : unreadAlertCount}
              </span>
            )}
          </button>

          {/* Settings */}
          <button
            onClick={onOpenSettings}
            className="p-1.5 sm:p-2 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 hover:text-slate-900 transition-all shadow-2xs cursor-pointer min-h-[34px] min-w-[34px] flex items-center justify-center"
            title="Configuration"
          >
            <Settings className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          </button>
        </div>
      </div>

      {/* Mobile Scrollable Navigation Tabs */}
      <div className="flex md:hidden items-center gap-1.5 overflow-x-auto px-3 py-1.5 border-t border-slate-100 bg-slate-50/90 no-scrollbar">
        <Link
          to="/"
          className={`px-3 py-1 rounded-lg text-xs font-bold whitespace-nowrap transition-all ${
            isChartActive
              ? 'bg-blue-600 text-white shadow-2xs'
              : 'text-slate-600 hover:text-slate-900 bg-white border border-slate-200/80'
          }`}
        >
          📈 Live Chart
        </Link>
        <Link
          to="/markets"
          className={`px-3 py-1 rounded-lg text-xs font-bold whitespace-nowrap transition-all ${
            isMarketListActive
              ? 'bg-blue-600 text-white shadow-2xs'
              : 'text-slate-600 hover:text-slate-900 bg-white border border-slate-200/80'
          }`}
        >
          🗂️ Markets
        </Link>
        <Link
          to="/mw-breakouts"
          className={`px-3 py-1 rounded-lg text-xs font-bold whitespace-nowrap transition-all flex items-center gap-1 ${
            isMWActive
              ? 'bg-purple-600 text-white shadow-2xs'
              : 'text-purple-700 hover:text-purple-900 bg-purple-50 border border-purple-200'
          }`}
        >
          <span>📊 M/W Breakouts</span>
          {mwUnreadCount > 0 && (
            <span className="px-1.5 py-0.2 rounded-full bg-rose-500 text-white text-[9px] font-mono font-bold animate-pulse">
              {mwUnreadCount}
            </span>
          )}
        </Link>
        <Link
          to="/events"
          className={`px-3 py-1 rounded-lg text-xs font-bold whitespace-nowrap transition-all ${
            isEventsActive
              ? 'bg-blue-600 text-white shadow-2xs'
              : 'text-slate-600 hover:text-slate-900 bg-white border border-slate-200/80'
          }`}
        >
          Structure Log
        </Link>
        <Link
          to="/backtest"
          className={`px-3 py-1 rounded-lg text-xs font-bold whitespace-nowrap transition-all ${
            isBacktestActive
              ? 'bg-blue-600 text-white shadow-2xs'
              : 'text-slate-600 hover:text-slate-900 bg-white border border-slate-200/80'
          }`}
        >
          Backtester
        </Link>
      </div>
    </header>
  );
};
