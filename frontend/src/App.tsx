import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import {
  InstrumentConfig,
  MultiTimeframeSynthesis,
  AlertNotification,
  AlertRule,
  HighConfluenceAlert,
  MWBreakoutAlert
} from './types';
import { api } from './services/api';
import { wsClient } from './services/websocket';
import { Navbar } from './components/Navbar';
import { MarketListPage } from './pages/MarketListPage';
import { MarketAnalysisPage } from './pages/MarketAnalysisPage';
import { MWBreakoutsPage } from './pages/MWBreakoutsPage';
import { MWBreakoutDetailPage } from './pages/MWBreakoutDetailPage';
import { EventHistoryTable } from './components/EventHistoryTable';
import { BacktestModal } from './components/BacktestModal';
import { AlertsDrawer } from './components/AlertsDrawer';
import { InstrumentManagerModal } from './components/InstrumentManagerModal';
import { SettingsModal } from './components/SettingsModal';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Bell } from 'lucide-react';

const AppContent: React.FC = () => {
  const navigate = useNavigate();

  // Core Data State
  const [instruments, setInstruments] = useState<InstrumentConfig[]>([]);
  const [syntheses, setSyntheses] = useState<Record<string, MultiTimeframeSynthesis>>({});
  const [currentProvider, setCurrentProvider] = useState<string>('yfinance');
  const [availableProviders, setAvailableProviders] = useState<string[]>(['yfinance']);

  // Existing Standard Notifications & Rules
  const [notifications, setNotifications] = useState<AlertNotification[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [soundEnabled, setSoundEnabled] = useState<boolean>(true);
  const [latestToast, setLatestToast] = useState<AlertNotification | null>(null);

  // COMPLETELY SEPARATE: High-Confluence Breakout Alerts
  const [highConfluenceAlerts, setHighConfluenceAlerts] = useState<HighConfluenceAlert[]>([]);

  // COMPLETELY SEPARATE: Dedicated M/W Breakout Page Alerts Stream
  const [mwBreakoutAlerts, setMwBreakoutAlerts] = useState<MWBreakoutAlert[]>([]);
  const [mwUnreadCount, setMwUnreadCount] = useState<number>(0);

  // Modals
  const [isAlertsOpen, setIsAlertsOpen] = useState<boolean>(false);
  const [isManageOpen, setIsManageOpen] = useState<boolean>(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Audio Chime synthesizer for alerts
  const playAlertSound = useCallback(() => {
    if (!soundEnabled) return;
    try {
      const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtxClass) return;
      const audioCtx = new AudioCtxClass();
      if (audioCtx.state === 'suspended') {
        audioCtx.resume();
      }
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(659.25, audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.12);
      gain.gain.setValueAtTime(0.25, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.35);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.35);
    } catch (e) {
      console.warn('Audio chime warning:', e);
    }
  }, [soundEnabled]);

  // Load initial instrument configuration, rules, standard notifications, and high-confluence alerts
  const loadInitialData = async () => {
    try {
      const [instList, provStatus, rulesList, notifs, hcAlerts] = await Promise.all([
        api.getInstruments(),
        api.getProviderStatus(),
        api.getAlertRules(),
        api.getNotifications(),
        api.getHighConfluenceAlerts()
      ]);
      setInstruments(instList);
      setCurrentProvider(provStatus.current_provider);
      setAvailableProviders(provStatus.available_providers);
      setRules(rulesList);
      setNotifications(notifs);
      setHighConfluenceAlerts(hcAlerts);
    } catch (err) {
      console.error('Core initialization error:', err);
    }

    // Fast initial price fetch to immediately populate market cards in 10ms (never stuck on Loading)
    api.getFastOverview().then((fastList) => {
      if (fastList && fastList.length > 0) {
        setSyntheses((prev) => {
          const next = { ...prev };
          fastList.forEach((item: any) => {
            if (!next[item.symbol]) {
              next[item.symbol] = {
                symbol: item.symbol,
                ticker: item.ticker,
                provider: 'yfinance',
                data_status: item.data_status || 'LIVE',
                market_session: item.market_session,
                last_updated: item.last_updated,
                is_stale: false,
                status_message: 'Live Market Data',
                current_price: item.current_price,
                timeframes: {},
                overall_bias: item.overall_bias,
                current_state: 'NO CLEAR STRUCTURE',
                evidence_score: {
                  total_score: item.evidence_score,
                  price_action: 20,
                  trend_structure: 20,
                  momentum: 15,
                  volatility: 15,
                  volume: 10,
                  pattern_confluence: 10,
                  interpretation: 'Fast Feed'
                },
                confirmation_state: 'Active'
              } as any;
            } else if (item.current_price > 0 && next[item.symbol].current_price === 0) {
              next[item.symbol] = {
                ...next[item.symbol],
                current_price: item.current_price,
                overall_bias: item.overall_bias || next[item.symbol].overall_bias,
                evidence_score: {
                  ...next[item.symbol].evidence_score,
                  total_score: item.evidence_score || next[item.symbol].evidence_score.total_score
                }
              };
            }
          });
          return next;
        });
      }
    }).catch((e) => console.warn('Fast overview initial load:', e));

    // Independent background fetch for M/W Breakouts without blocking the main dashboard & chart
    api.getMWBreakouts().then((mwAlerts) => {
      setMwBreakoutAlerts(mwAlerts);
    }).catch((e) => console.warn('M/W initial load:', e));

    api.getMWBreakoutStats().then((stats) => {
      if (stats) setMwUnreadCount(stats.unread_count || 0);
    }).catch((e) => console.warn('M/W stats initial load:', e));
  };

  const loadMWBreakouts = async () => {
    try {
      const mwAlerts = await api.getMWBreakouts();
      setMwBreakoutAlerts(mwAlerts);
      const stats = await api.getMWBreakoutStats();
      setMwUnreadCount(stats.unread_count || 0);
    } catch (err) {
      console.warn('Failed to reload M/W breakouts:', err);
    }
  };

  // Refresh analysis overview for all instruments
  const refreshAllAnalysis = async () => {
    setIsLoading(true);
    try {
      const overviewList = await api.getOverview();
      const synthMap: Record<string, MultiTimeframeSynthesis> = {};
      overviewList.forEach((s) => {
        synthMap[s.symbol] = s;
      });
      setSyntheses(synthMap);
    } catch (err) {
      console.error('Failed to load overview:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Initial mount & real-time WebSocket connection
  useEffect(() => {
    loadInitialData();
    refreshAllAnalysis();

    // Connect WebSocket for real-time live events and prices
    wsClient.connect();
    const unsubscribe = wsClient.subscribe((data) => {
      // 1. DEDICATED M/W BREAKOUT ALERTS STREAM (Separate Channel)
      if (data.type === 'MW_BREAKOUT_TRIGGERED' && data.alert) {
        const mwAlert: MWBreakoutAlert = data.alert;
        playAlertSound();
        setMwUnreadCount((c) => c + 1);
        setMwBreakoutAlerts((prev) => {
          if (prev.some((a) => a.alert_id === mwAlert.alert_id)) return prev;
          return [mwAlert, ...prev];
        });
      }
      // 1b. DEDICATED M/W BREAKOUT STATUS UPDATED EVENT
      else if (data.type === 'MW_BREAKOUT_STATUS_UPDATED' && data.alert) {
        const updatedAlert: MWBreakoutAlert = data.alert;
        setMwBreakoutAlerts((prev) =>
          prev.map((a) => (a.alert_id === updatedAlert.alert_id ? updatedAlert : a))
        );
      }
      // 2. HIGH-CONFLUENCE BREAKOUT ALERTS (Dedicated Event Channel)
      else if (data.type === 'HIGH_CONFLUENCE_ALERT_TRIGGERED' && data.alert) {
        const hcAlert: HighConfluenceAlert = data.alert;
        playAlertSound();
        setHighConfluenceAlerts((prev) => {
          if (prev.some((a) => a.id === hcAlert.id)) return prev;
          return [hcAlert, ...prev];
        });
      }
      // 3. EXISTING STANDARD NOTIFICATIONS
      else if (data.type === 'ALERT_TRIGGERED' && data.alert) {
        const notif: AlertNotification = data.alert;
        playAlertSound();
        setUnreadCount((c) => c + 1);
        setLatestToast(notif);
        setTimeout(() => setLatestToast(null), 7000);
        setNotifications((prev) => [notif, ...prev]);
      } 
      // 4. SYNTHESIS TICK UPDATES — Update state directly without re-triggering full HTTP fetch
      else if (data.type === 'SYNTHESIS_UPDATE' && data.symbol) {
        setSyntheses((prev) => {
          const existing = prev[data.symbol];
          if (!existing) return prev;
          return {
            ...prev,
            [data.symbol]: {
              ...existing,
              current_price: data.current_price || existing.current_price,
              overall_bias: data.overall_bias || existing.overall_bias,
              current_state: data.current_state || existing.current_state,
              evidence_score: {
                ...existing.evidence_score,
                total_score: data.evidence_score !== undefined ? data.evidence_score : existing.evidence_score.total_score
              },
              latest_important_event: data.latest_event || existing.latest_important_event
            }
          };
        });
      }
    });

    const pollInterval = setInterval(() => {
      // Light background refresh without blocking UI
      refreshAllAnalysis();
    }, 60000);

    return () => {
      unsubscribe();
      clearInterval(pollInterval);
      wsClient.disconnect();
    };
  }, []);

  // Handle Provider Switch
  const handleSelectProvider = async (pName: string) => {
    try {
      await api.setProvider(pName);
      setCurrentProvider(pName);
      refreshAllAnalysis();
    } catch (err) {
      console.error('Provider change error:', err);
    }
  };

  return (
    <div className="min-h-screen w-full max-w-full overflow-x-hidden bg-slate-50 text-slate-900 flex flex-col selection:bg-blue-500 selection:text-white font-sans">
      {/* Top Navigation Bar */}
      <Navbar
        currentProvider={currentProvider}
        availableProviders={availableProviders}
        onSelectProvider={handleSelectProvider}
        onRefreshAll={refreshAllAnalysis}
        isLoading={isLoading}
        unreadAlertCount={unreadCount}
        mwBreakoutCount={mwBreakoutAlerts.length}
        mwUnreadCount={mwUnreadCount}
        onOpenAlerts={() => {
          setIsAlertsOpen(true);
          setUnreadCount(0);
        }}
        onOpenBacktest={() => navigate('/backtest')}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      {/* Main Multi-Page Container */}
      <main className="flex-1 max-w-7xl w-full min-w-0 mx-auto px-2.5 sm:px-6 lg:px-8 py-4 sm:py-6">
        <Routes>
          {/* DEFAULT ROUTE & DASHBOARD: Open the Live Chart & Market Analysis directly! */}
          <Route
            path="/"
            element={
              <MarketAnalysisPage
                instruments={instruments}
                syntheses={syntheses}
                highConfluenceAlerts={highConfluenceAlerts}
                mwBreakoutAlerts={mwBreakoutAlerts}
                onClearHighConfluenceAlerts={() => setHighConfluenceAlerts([])}
                onHighConfluenceAlertTriggered={(alert) => {
                  setHighConfluenceAlerts((prev) => {
                    if (prev.some((a) => a.id === alert.id)) return prev;
                    return [alert, ...prev];
                  });
                }}
                onOpenAlerts={() => {
                  setIsAlertsOpen(true);
                  setUnreadCount(0);
                }}
                onOpenBacktest={() => navigate('/backtest')}
              />
            }
          />

          <Route path="/dashboard" element={<Navigate to="/" replace />} />

          {/* PAGE 1: Market List (Market Selection Interface) */}
          <Route
            path="/markets"
            element={
              <MarketListPage
                instruments={instruments}
                syntheses={syntheses}
                isLoading={isLoading}
                onRefresh={refreshAllAnalysis}
                onOpenManageModal={() => setIsManageOpen(true)}
              />
            }
          />

          {/* PAGE 2: Dedicated Selected Market Analysis Page with Chart */}
          <Route
            path="/markets/:symbol"
            element={
              <MarketAnalysisPage
                instruments={instruments}
                syntheses={syntheses}
                highConfluenceAlerts={highConfluenceAlerts}
                mwBreakoutAlerts={mwBreakoutAlerts}
                onClearHighConfluenceAlerts={() => setHighConfluenceAlerts([])}
                onHighConfluenceAlertTriggered={(alert) => {
                  setHighConfluenceAlerts((prev) => {
                    if (prev.some((a) => a.id === alert.id)) return prev;
                    return [alert, ...prev];
                  });
                }}
                onOpenAlerts={() => {
                  setIsAlertsOpen(true);
                  setUnreadCount(0);
                }}
                onOpenBacktest={() => navigate('/backtest')}
              />
            }
          />

          {/* PAGE 3: DEDICATED M/W PATTERN BREAKOUTS PAGE (Isolated with ErrorBoundary) */}
          <Route
            path="/mw-breakouts"
            element={
              <ErrorBoundary fallbackTitle="M/W Breakouts Temporarily Unavailable">
                <MWBreakoutsPage
                  alerts={mwBreakoutAlerts}
                  soundEnabled={soundEnabled}
                  onToggleSound={() => setSoundEnabled(!soundEnabled)}
                  onRefresh={loadMWBreakouts}
                />
              </ErrorBoundary>
            }
          />

          {/* PAGE 4: DEDICATED M/W BREAKOUT DETAILS PAGE (Isolated with ErrorBoundary) */}
          <Route
            path="/mw-breakouts/:alertId"
            element={
              <ErrorBoundary fallbackTitle="M/W Breakout Details Temporarily Unavailable">
                <MWBreakoutDetailPage />
              </ErrorBoundary>
            }
          />

          {/* Structure Breakout Log View */}
          <Route
            path="/events"
            element={
              <EventHistoryTable
                notifications={notifications}
                onClear={() => {
                  api.clearNotifications();
                  setNotifications([]);
                }}
              />
            }
          />

          {/* Backtesting View */}
          <Route
            path="/backtest"
            element={
              <BacktestModal
                instruments={instruments}
                selectedSymbol={instruments[0]?.symbol || 'NIFTY 50'}
              />
            }
          />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/markets" replace />} />
        </Routes>
      </main>

      {/* Clean Global Footer */}
      <footer className="w-full border-t border-slate-200 bg-white py-4 text-center text-xs text-slate-500">
        <p>
          AI Multi-Timeframe Market Structure Analyzer • Quantitative Breakout & Forecasting Decision Support
        </p>
      </footer>

      {/* Floating Real-Time Breakout Toast Notification */}
      {latestToast && (
        <div className="fixed bottom-4 right-4 left-4 sm:left-auto sm:bottom-6 sm:right-6 z-50 max-w-sm w-auto bg-white border border-blue-500 shadow-2xl rounded-2xl p-4 backdrop-blur-md flex items-start gap-3">
          <div className="p-2 rounded-xl bg-blue-50 text-blue-600 border border-blue-200 shrink-0">
            <Bell className="h-5 w-5 animate-pulse" />
          </div>
          <div className="flex-1 text-xs">
            <div className="flex items-center justify-between font-bold text-slate-900">
              <span>{latestToast.symbol} ({latestToast.timeframe})</span>
              <span className="text-[10px] text-blue-600 font-mono">Score: {latestToast.evidence_score}/100</span>
            </div>
            <p className="text-slate-800 text-[11px] font-semibold mt-1 leading-snug">
              {latestToast.message}
            </p>
            <div className="text-[10px] text-slate-500 font-mono mt-1">
              Break Price: {latestToast.price.toFixed(2)}
            </div>
          </div>
          <button
            onClick={() => setLatestToast(null)}
            className="text-slate-400 hover:text-slate-700 text-xs p-1 cursor-pointer"
          >
            ✕
          </button>
        </div>
      )}

      {/* Slide-over Breakout Alerts Drawer */}
      <AlertsDrawer
        isOpen={isAlertsOpen}
        onClose={() => setIsAlertsOpen(false)}
        notifications={notifications}
        rules={rules}
        onRefreshRules={async () => {
          const r = await api.getAlertRules();
          setRules(r);
        }}
        onClearNotifications={() => {
          api.clearNotifications();
          setNotifications([]);
        }}
        soundEnabled={soundEnabled}
        onToggleSound={() => setSoundEnabled(!soundEnabled)}
        onTestAlertTriggered={(testNotif) => {
          playAlertSound();
          setUnreadCount((c) => c + 1);
          setLatestToast(testNotif);
          setTimeout(() => setLatestToast(null), 7000);
          setNotifications((prev) => [testNotif, ...prev]);
        }}
      />

      {/* Instrument Manager Modal */}
      <InstrumentManagerModal
        isOpen={isManageOpen}
        onClose={() => setIsManageOpen(false)}
        instruments={instruments}
        onRefresh={async () => {
          const list = await api.getInstruments();
          setInstruments(list);
        }}
      />

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        geminiApiKey=""
        onSaveGeminiApiKey={() => {}}
      />
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
};

export default App;
