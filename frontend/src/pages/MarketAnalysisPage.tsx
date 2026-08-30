import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import {
  HighConfluenceAlert,
  InstrumentConfig,
  MultiTimeframeSynthesis,
  AIAnalysisSummary,
  AlertNotification,
  MWBreakoutAlert
} from '../types';
import { api } from '../services/api';
import { formatMarketTimeWithSeconds } from '../utils/time';
import { ChartView } from '../components/ChartView';
import { MultiTimeframeCards } from '../components/MultiTimeframeCards';
import { WhatJustChangedPanel } from '../components/WhatJustChangedPanel';
import { TrendlinePanel } from '../components/TrendlinePanel';
import { HighConfluenceAlertsPanel } from '../components/HighConfluenceAlertsPanel';
import { MWBreakoutCard } from '../components/MWBreakoutCard';
import { EvidenceScoreGauge } from '../components/EvidenceScoreGauge';
import { AISummaryBox } from '../components/AISummaryBox';
import { SupportResistanceBox } from '../components/SupportResistanceBox';
import { HypotheticalSetup } from '../components/HypotheticalSetup';
import { PredictiveScenarioBox } from '../components/PredictiveScenarioBox';
import {
  ArrowLeft,
  RefreshCw,
  Clock,
  Sparkles,
  Layers,
  Calendar,
  Zap,
  TrendingUp,
  TrendingDown,
  Activity,
  Sliders,
  ArrowRight,
  Radio,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  ChevronDown,
  Bell,
  Target
} from 'lucide-react';

interface MarketAnalysisPageProps {
  instruments: InstrumentConfig[];
  syntheses: Record<string, MultiTimeframeSynthesis>;
  highConfluenceAlerts: HighConfluenceAlert[];
  mwBreakoutAlerts: MWBreakoutAlert[];
  onClearHighConfluenceAlerts?: () => void;
  onHighConfluenceAlertTriggered?: (alert: HighConfluenceAlert) => void;
  onOpenAlerts: () => void;
  onOpenBacktest?: (alert: HighConfluenceAlert) => void;
  onRefreshAll?: () => Promise<void>;
  isRefreshing?: boolean;
}

export const MarketAnalysisPage: React.FC<MarketAnalysisPageProps> = ({
  instruments,
  syntheses,
  highConfluenceAlerts,
  mwBreakoutAlerts = [],
  onClearHighConfluenceAlerts,
  onHighConfluenceAlertTriggered,
  onOpenAlerts,
  onOpenBacktest,
  onRefreshAll,
  isRefreshing
}) => {
  const { symbol: rawSymbol } = useParams<{ symbol: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Normalize symbol comparison (removes slashes, dashes, underscores, spaces)
  const normSym = (s?: string) => (s || '').trim().toUpperCase().replace(/[/_\-\s]/g, '');

  // Decode symbol from URL parameter
  const decodedSymbol = rawSymbol ? decodeURIComponent(rawSymbol) : '';

  // Match against configured instruments (case-insensitive & whitespace/slash/dash flexible)
  const matchedInstrument = instruments.find(
    (i) =>
      normSym(i.symbol) === normSym(decodedSymbol) ||
      normSym(i.ticker) === normSym(decodedSymbol)
  );

  const activeSymbol = matchedInstrument ? matchedInstrument.symbol : (decodedSymbol || (instruments[0]?.symbol || 'NIFTY 50'));
  const currentSynthesis = syntheses[activeSymbol];

  // Central Single Source of Truth for Selected Timeframe (4H, 1H, 15M, 5M)
  const queryTf = searchParams.get('timeframe')?.toUpperCase();
  const validTf = (queryTf === '4H' || queryTf === '1H' || queryTf === '15M' || queryTf === '5M') ? queryTf : '15M';
  const [selectedTimeframe, setSelectedTimeframe] = useState<'4H' | '1H' | '15M' | '5M'>(validTf);

  // Sync selectedTimeframe when URL query param changes
  useEffect(() => {
    const qTf = searchParams.get('timeframe')?.toUpperCase();
    if (qTf === '4H' || qTf === '1H' || qTf === '15M' || qTf === '5M') {
      setSelectedTimeframe(qTf);
    }
  }, [searchParams]);

  const [aiSummary, setAiSummary] = useState<AIAnalysisSummary | null>(null);
  const [isAiLoading, setIsAiLoading] = useState<boolean>(false);
  const [activeChartAlert, setActiveChartAlert] = useState<MWBreakoutAlert | null>(null);

  const currentMWAlert = (
    activeChartAlert && normSym(activeChartAlert.symbol) === normSym(activeSymbol) && activeChartAlert.timeframe === selectedTimeframe
      ? activeChartAlert
      : null
  ) || mwBreakoutAlerts.find(
    (a) => normSym(a.symbol) === normSym(activeSymbol) && a.timeframe === selectedTimeframe
  ) || activeChartAlert || mwBreakoutAlerts.find(
    (a) => normSym(a.symbol) === normSym(activeSymbol)
  );

  // Reset active chart alert when switching symbol
  useEffect(() => {
    setActiveChartAlert(null);
  }, [activeSymbol]);

  // Dynamic Browser Page Title
  useEffect(() => {
    if (activeSymbol) {
      document.title = `AI Market Analyzer — ${activeSymbol}`;
    }
  }, [activeSymbol]);

  // Handle AI Summary Generation
  const handleGenerateAI = async () => {
    if (!activeSymbol) return;
    setIsAiLoading(true);
    try {
      const summary = await api.generateAISummary(activeSymbol);
      setAiSummary(summary);
    } catch (err) {
      console.error('AI generation error:', err);
    } finally {
      setIsAiLoading(false);
    }
  };

  // If instrument is completely invalid and not a known default
  const knownDefaults = ['NIFTY 50', 'BANK NIFTY', 'FINNIFTY', 'BTC/USD', 'ETH/USD', 'RELIANCE', 'TCS'];
  const isKnownDefault = knownDefaults.some(k => k.toUpperCase() === decodedSymbol.toUpperCase());
  if (!matchedInstrument && instruments.length > 0 && !isKnownDefault && decodedSymbol !== '') {
    return (
      <div className="max-w-xl mx-auto my-16 bg-white rounded-3xl p-8 border border-slate-200 shadow-xl text-center space-y-4">
        <div className="p-4 rounded-2xl bg-amber-50 text-amber-600 w-14 h-14 mx-auto flex items-center justify-center">
          <Layers className="h-7 w-7" />
        </div>
        <h2 className="text-xl font-black text-slate-900">Market Not Found</h2>
        <p className="text-xs text-slate-600">
          The requested market "<span className="font-mono font-bold text-slate-800">{decodedSymbol}</span>" does not exist in your active tracked instruments list.
        </p>
        <div className="pt-2">
          <Link
            to="/markets/NIFTY%2050"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold transition-all shadow-md"
          >
            <ArrowLeft className="h-4 w-4" /> Go to Main Chart (NIFTY 50)
          </Link>
        </div>
      </div>
    );
  }

  const isCryptoOrUsd = activeSymbol.includes('BTC') || activeSymbol.includes('USD');
  const currSym = isCryptoOrUsd ? '$' : '₹';

  const dataStatus = currentSynthesis?.data_status || 'LIVE';
  const dataStatusStyle =
    dataStatus === 'LIVE'
      ? 'bg-emerald-50 text-emerald-700 border-emerald-300'
      : dataStatus === 'RECONNECTING'
      ? 'bg-blue-50 text-blue-700 border-blue-300'
      : 'bg-amber-50 text-amber-700 border-amber-300';

  return (
    <div className="space-y-4 sm:space-y-6 pb-16 w-full max-w-full min-w-0">
      {/* Top Breadcrumb & Market Switcher Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white p-3 sm:p-3.5 rounded-2xl border border-slate-200 shadow-xs w-full min-w-0">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          {/* Back button */}
          <Link
            to="/markets"
            className="inline-flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-1.5 sm:py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-bold transition-all shadow-2xs group shrink-0"
          >
            <ArrowLeft className="h-4 w-4 group-hover:-translate-x-0.5 transition-transform" />
            <span>Back to Markets</span>
          </Link>

          {/* Dedicated M/W Breakouts Page Link */}
          <Link
            to="/mw-breakouts"
            className="inline-flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-1.5 sm:py-2 rounded-xl bg-purple-50 hover:bg-purple-100 text-purple-800 border border-purple-200 text-xs font-bold transition-all shadow-2xs group cursor-pointer shrink-0"
            title="Open Dedicated M/W Breakouts Page"
          >
            <Target className="h-4 w-4 text-purple-600 group-hover:scale-110 transition-transform" />
            <span>M/W BREAKOUTS</span>
            <span className="text-[9px] sm:text-[10px] bg-purple-600 text-white px-1.5 py-0.2 rounded-full font-mono">
              NEW
            </span>
          </Link>
        </div>

        {/* Quick Market Switcher Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto max-w-full py-1 no-scrollbar min-w-0">
          <span className="text-[11px] font-bold text-slate-400 uppercase mr-1 hidden sm:inline">
            Switch:
          </span>
          {instruments.map((inst) => {
            const isSelected = inst.symbol === activeSymbol;
            return (
              <button
                key={inst.symbol}
                onClick={() => navigate(`/markets/${encodeURIComponent(inst.symbol)}`)}
                className={`px-2.5 sm:px-3 py-1 sm:py-1.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all ${
                  isSelected
                    ? 'bg-blue-600 text-white shadow-2xs'
                    : 'bg-slate-50 text-slate-600 hover:bg-slate-100 hover:text-slate-900 border border-slate-200/60'
                }`}
              >
                {inst.symbol}
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Market Executive Header */}
      {currentSynthesis && (
        <div className="glass-panel rounded-3xl p-4 sm:p-6 shadow-xs flex flex-wrap items-center justify-between gap-4 sm:gap-6 border-l-4 border-blue-600 bg-white border border-slate-200 w-full min-w-0">
          <div className="flex items-center gap-3 sm:gap-4 min-w-0">
            <div className="p-2.5 sm:p-3.5 rounded-2xl bg-blue-50 border border-blue-200 text-blue-600 shadow-2xs shrink-0">
              <TrendingUp className="h-5 w-5 sm:h-7 sm:w-7" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 sm:gap-2.5 flex-wrap">
                <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight truncate">
                  {currentSynthesis.symbol}
                </h1>
                <span className="text-xs font-mono px-2 py-0.5 rounded-lg bg-slate-100 text-slate-600 font-bold border border-slate-200 shrink-0">
                  {currentSynthesis.ticker}
                </span>
                <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${dataStatusStyle} flex items-center gap-1`}>
                  <Radio className="h-2.5 w-2.5 animate-pulse" />
                  {dataStatus}
                </span>
                {currentSynthesis.market_session && (
                  <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border flex items-center gap-1.5 ${
                    currentSynthesis.market_session.is_running
                      ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                      : 'bg-slate-100 text-slate-700 border-slate-300'
                  }`}>
                    <span className={`h-2 w-2 rounded-full ${currentSynthesis.market_session.is_running ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} />
                    {currentSynthesis.market_session.message}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-1">
                {currentSynthesis.status_message} • Last Updated: {formatMarketTimeWithSeconds(currentSynthesis.last_updated, activeSymbol)}
              </p>
            </div>
          </div>

          {/* Header Stats */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Live Price */}
            <div className="bg-slate-50 px-5 py-2.5 rounded-2xl border border-slate-200 text-right shadow-2xs">
              <span className="text-[10px] text-slate-500 block uppercase font-bold">Current Live Price</span>
              <span className="text-2xl font-black font-mono text-slate-900">
                {currSym}{currentSynthesis.current_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>

            {/* Overall Bias */}
            <div className="bg-slate-50 px-4 py-2.5 rounded-2xl border border-slate-200 text-center shadow-2xs">
              <span className="text-[10px] text-slate-500 block uppercase font-bold">Overall Bias</span>
              <span className={`text-sm font-extrabold flex items-center gap-1 ${
                currentSynthesis.overall_bias === 'BULLISH'
                  ? 'text-emerald-700'
                  : currentSynthesis.overall_bias === 'BEARISH'
                  ? 'text-rose-700'
                  : 'text-amber-700'
              }`}>
                {currentSynthesis.overall_bias === 'BULLISH' ? <ArrowUpRight className="h-4 w-4" /> : currentSynthesis.overall_bias === 'BEARISH' ? <ArrowDownRight className="h-4 w-4" /> : <Minus className="h-4 w-4" />}
                {currentSynthesis.overall_bias}
              </span>
            </div>

            {/* Evidence Score */}
            <div className="bg-slate-50 px-4 py-2.5 rounded-2xl border border-slate-200 text-center shadow-2xs">
              <span className="text-[10px] text-slate-500 block uppercase font-bold">Evidence Score</span>
              <span className="text-lg font-black font-mono text-blue-600">
                {currentSynthesis.evidence_score.total_score}/100
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 1. What Just Changed Delta Breakout Pulse Panel */}
      {currentSynthesis && (
        <WhatJustChangedPanel
          whatJustChanged={currentSynthesis.what_just_changed}
          latestEvent={currentSynthesis.latest_important_event}
          currentSymbol={activeSymbol}
        />
      )}

      {/* 2. 4-Timeframe Breakdown Cards */}
      {currentSynthesis && (
        <MultiTimeframeCards timeframes={currentSynthesis.timeframes} />
      )}

      {/* 3. Interactive Candlestick Chart with Full Pan & Zoom */}
      <ChartView
        symbol={activeSymbol}
        timeframe={selectedTimeframe}
        onSelectTimeframe={setSelectedTimeframe}
        onActivePatternChange={(_pat, alert) => setActiveChartAlert(alert)}
        keySupports={
          currentSynthesis?.timeframes[selectedTimeframe]?.support_resistance?.all_levels
            ?.filter((l: any) => l.type === 'SUPPORT')
            ?.map((l: any) => l.price) || currentSynthesis?.key_supports || []
        }
        keyResistances={
          currentSynthesis?.timeframes[selectedTimeframe]?.support_resistance?.all_levels
            ?.filter((l: any) => l.type === 'RESISTANCE')
            ?.map((l: any) => l.price) || currentSynthesis?.key_resistances || []
        }
        invalidationLevel={currentSynthesis?.invalidation_level}
      />

      {/* 4. Structural Multi-Trendlines Matrix Panel (Synchronized with selectedTimeframe) */}
      {currentSynthesis && (
        <TrendlinePanel
          trendlines={currentSynthesis.timeframes[selectedTimeframe]?.trendlines || []}
          timeframe={selectedTimeframe}
        />
      )}

      {/* 4.5. DEDICATED M/W BREAKOUT CARD (Directly below Chart & Trendlines) */}
      {currentMWAlert && (
        <div className="space-y-2.5">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-purple-100 text-purple-700">
                <Target className="h-4 w-4" />
              </div>
              <h3 className="text-sm sm:text-base font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                <span>M/W BREAKOUTS</span>
                <span className="text-xs font-mono font-normal text-slate-400">•</span>
                <span className="font-bold text-slate-700">{currentMWAlert.symbol} ({currentMWAlert.timeframe})</span>
              </h3>
              <span className="text-[9px] bg-purple-600 text-white font-bold px-2 py-0.5 rounded-full uppercase tracking-wider shadow-2xs">
                CHART SYNCED
              </span>
            </div>
            <Link
              to="/mw-breakouts"
              className="text-xs font-bold text-purple-700 hover:text-purple-900 flex items-center gap-1 transition-colors group"
            >
              <span>View All M/W Breakouts</span>
              <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </div>
          <MWBreakoutCard alert={currentMWAlert} isHero={true} />
        </div>
      )}

      {/* 5. DEDICATED HIGH-CONFLUENCE BREAKOUT ALERTS PANEL */}
      <HighConfluenceAlertsPanel
        alerts={highConfluenceAlerts}
        currentSymbol={activeSymbol}
        onClearAlerts={onClearHighConfluenceAlerts}
        onAlertTriggered={onHighConfluenceAlertTriggered}
      />

      {/* 6. Predictive Target Roadmaps & Order Blocks (Synchronized with selectedTimeframe) */}
      {currentSynthesis && (
        <PredictiveScenarioBox
          scenarios={currentSynthesis.timeframes[selectedTimeframe]?.predictive_scenarios || currentSynthesis.predictive_scenarios}
          symbol={activeSymbol}
        />
      )}

      {/* 6. Evidence Score Gauge & Key S/R Panels (Synchronized with selectedTimeframe) */}
      {currentSynthesis && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <EvidenceScoreGauge scoreData={currentSynthesis.evidence_score} />
          <SupportResistanceBox
            sr={currentSynthesis.timeframes[selectedTimeframe]?.support_resistance || {
              major_support: currentSynthesis.key_supports[0] || null,
              minor_support: currentSynthesis.key_supports[1] || null,
              current_price: currentSynthesis.current_price,
              minor_resistance: currentSynthesis.key_resistances[0] || null,
              major_resistance: currentSynthesis.key_resistances[1] || null,
              all_levels: []
            }}
            invalidationLevel={currentSynthesis.invalidation_level}
          />
        </div>
      )}

      {/* 7. AI Summary Interpretation Box */}
      <AISummaryBox
        symbol={activeSymbol}
        summary={aiSummary}
        onGenerateSummary={handleGenerateAI}
        isLoading={isAiLoading}
      />

      {/* 8. Hypothetical Setup Decision Support */}
      <HypotheticalSetup symbol={activeSymbol} />
    </div>
  );
};
