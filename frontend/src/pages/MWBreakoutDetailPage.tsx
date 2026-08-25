import React, { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { MWBreakoutAlert, Candle } from '../types';
import { api } from '../services/api';
import { formatMarketTime, formatCandleDate } from '../utils/time';
import {
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  Target,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  Activity,
  Layers,
  Sparkles,
  BarChart2,
  RefreshCw,
  AlertCircle
} from 'lucide-react';

// Module-level cache for instant M/W Breakout Details opening
const detailMemoryCache = new Map<string, { alert: MWBreakoutAlert; candles: Candle[] }>();

export const MWBreakoutDetailPage: React.FC = () => {
  const { alertId } = useParams<{ alertId: string }>();
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const decodedAlertId = alertId ? decodeURIComponent(alertId) : '';
  const cachedDetail = detailMemoryCache.get(decodedAlertId);

  const [alert, setAlert] = useState<MWBreakoutAlert | null>(() => cachedDetail?.alert || null);
  const [candles, setCandles] = useState<Candle[]>(() => cachedDetail?.candles || []);
  const [isLoading, setIsLoading] = useState<boolean>(() => !cachedDetail);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!decodedAlertId) return;

    const loadDetail = async () => {
      if (!detailMemoryCache.has(decodedAlertId)) {
        setIsLoading(true);
      }
      setError(null);
      try {
        const data = await api.getMWBreakoutDetail(decodedAlertId);
        setAlert(data);

        // Fetch chart data for symbol & timeframe
        const chartRes = await api.getChartData(data.symbol, data.timeframe, 150);
        const candleList = chartRes && chartRes.candles ? chartRes.candles : [];
        setCandles(candleList);

        detailMemoryCache.set(decodedAlertId, { alert: data, candles: candleList });
      } catch (err: any) {
        console.error('Failed to load breakout detail:', err);
        if (!alert) {
          setError(err.message || 'Breakout signal details not found');
        }
      } finally {
        setIsLoading(false);
      }
    };

    loadDetail();
  }, [decodedAlertId]);

  // Render the Focused Pattern Canvas Chart
  useEffect(() => {
    if (!canvasRef.current || !alert || candles.length === 0) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);

    // Responsive Padding
    const isMobile = width < 600;
    const isSmallMobile = width < 420;
    const paddingLeft = isSmallMobile ? 6 : isMobile ? 10 : 20;
    const paddingRight = isSmallMobile ? 54 : isMobile ? 62 : 95;
    const paddingTop = isMobile ? 18 : 25;
    const chartHeight = height - (isMobile ? 38 : 50);

    // Filter to relevant candles around pattern
    const patternTime = new Date(alert.s1_timestamp).getTime();
    let startIndex = candles.findIndex((c) => new Date(c.timestamp).getTime() >= patternTime - 20 * 60 * 1000);
    if (startIndex === -1 || startIndex > candles.length - 20) {
      startIndex = Math.max(0, candles.length - 45);
    } else {
      startIndex = Math.max(0, startIndex - 5);
    }

    const visibleCandles = candles.slice(startIndex);
    if (visibleCandles.length < 5) return;

    // Calculate Price Range
    let minPrice = Infinity;
    let maxPrice = -Infinity;

    visibleCandles.forEach((c) => {
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
    });

    // Include pattern levels in bounds
    minPrice = Math.min(minPrice, alert.s1_price, alert.s2_price, alert.neckline_price, alert.measured_target, alert.invalidation_level);
    maxPrice = Math.max(maxPrice, alert.s1_price, alert.s2_price, alert.neckline_price, alert.measured_target, alert.invalidation_level);

    const priceMargin = (maxPrice - minPrice) * 0.12 || 10;
    minPrice -= priceMargin;
    maxPrice += priceMargin;
    const priceRange = maxPrice - minPrice;

    const getX = (idx: number) => {
      const step = (width - paddingLeft - paddingRight) / (visibleCandles.length - 1 || 1);
      return paddingLeft + idx * step;
    };

    const getY = (price: number) => {
      return paddingTop + chartHeight - ((price - minPrice) / priceRange) * chartHeight;
    };

    // Draw Subtle Grid
    ctx.strokeStyle = '#f1f5f9';
    ctx.lineWidth = 1;
    for (let i = 0; i < 5; i++) {
      const p = minPrice + (priceRange / 4) * i;
      const y = getY(p);
      ctx.beginPath();
      ctx.moveTo(paddingLeft, y);
      ctx.lineTo(width - paddingRight, y);
      ctx.stroke();

      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px monospace';
      ctx.textAlign = 'left';
      ctx.fillText(p.toFixed(2), width - paddingRight + 8, y + 3);
    }

    // Draw Candlesticks
    const candleWidth = Math.max(3, (width - paddingLeft - paddingRight) / visibleCandles.length * 0.65);
    visibleCandles.forEach((c, idx) => {
      const x = getX(idx);
      const openY = getY(c.open);
      const closeY = getY(c.close);
      const highY = getY(c.high);
      const lowY = getY(c.low);
      const isBull = c.close >= c.open;

      ctx.strokeStyle = isBull ? '#10b981' : '#f43f5e';
      ctx.fillStyle = isBull ? '#10b981' : '#f43f5e';
      ctx.lineWidth = 1.2;

      // Wick
      ctx.beginPath();
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.stroke();

      // Body
      const top = Math.min(openY, closeY);
      const bHeight = Math.max(1.5, Math.abs(openY - closeY));
      ctx.fillRect(x - candleWidth / 2, top, candleWidth, bHeight);
    });

    // 1. Draw Pattern Connected Guideline: S1 -> Neckline -> S2
    const s1LocalIdx = visibleCandles.findIndex((c) => c.timestamp === alert.s1_timestamp);
    const neckLocalIdx = visibleCandles.findIndex((c) => c.timestamp === alert.neckline_timestamp);
    const s2LocalIdx = visibleCandles.findIndex((c) => c.timestamp === alert.s2_timestamp);

    const isW = alert.pattern_type === 'W';
    const lineColor = isW ? '#8b5cf6' : '#ec4899';

    if (s1LocalIdx !== -1 && neckLocalIdx !== -1 && s2LocalIdx !== -1) {
      const x1 = getX(s1LocalIdx);
      const y1 = getY(alert.s1_price);
      const xNeck = getX(neckLocalIdx);
      const yNeck = getY(alert.neckline_price);
      const x2 = getX(s2LocalIdx);
      const y2 = getY(alert.s2_price);

      ctx.strokeStyle = lineColor;
      ctx.lineWidth = 2.5;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(xNeck, yNeck);
      ctx.lineTo(x2, y2);
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw Vertex Dots
      [
        { x: x1, y: y1, label: isW ? 'L1' : 'H1' },
        { x: xNeck, y: yNeck, label: 'NECKLINE' },
        { x: x2, y: y2, label: isW ? 'L2' : 'H2' }
      ].forEach((pt) => {
        ctx.fillStyle = lineColor;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 4.5, 0, Math.PI * 2);
        ctx.fill();

        ctx.font = 'bold 9px sans-serif';
        ctx.fillStyle = '#475569';
        ctx.textAlign = 'center';
        ctx.fillText(pt.label, pt.x, pt.y - 8);
      });
    }

    // 2. Draw Clean Horizontal Neckline
    const yNeckline = getY(alert.neckline_price);
    ctx.strokeStyle = '#9333ea';
    ctx.lineWidth = 1.8;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(paddingLeft, yNeckline);
    ctx.lineTo(width - paddingRight, yNeckline);
    ctx.stroke();
    ctx.setLineDash([]);

    // Neckline Badge
    const badgeW = isMobile ? 54 : 86;
    const badgeH = isMobile ? 13 : 16;
    const badgeFont = isMobile ? 'bold 7.5px sans-serif' : 'bold 9px sans-serif';

    ctx.fillStyle = '#9333ea';
    ctx.fillRect(width - paddingRight + 2, yNeckline - (isMobile ? 6.5 : 8), badgeW, badgeH);
    ctx.fillStyle = '#ffffff';
    ctx.font = badgeFont;
    ctx.textAlign = 'left';
    ctx.fillText(isMobile ? `N:${alert.neckline_price.toFixed(0)}` : `NECK: ${alert.neckline_price.toFixed(1)}`, width - paddingRight + 4, yNeckline + (isMobile ? 2.5 : 3));

    // 3. Draw Clean Horizontal Target 1
    const yTarget = getY(alert.measured_target);
    ctx.strokeStyle = '#059669';
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 3]);
    ctx.beginPath();
    ctx.moveTo(paddingLeft, yTarget);
    ctx.lineTo(width - paddingRight, yTarget);
    ctx.stroke();
    ctx.setLineDash([]);

    // Target 1 Badge
    ctx.fillStyle = '#059669';
    ctx.fillRect(width - paddingRight + 2, yTarget - (isMobile ? 6.5 : 8), badgeW, badgeH);
    ctx.fillStyle = '#ffffff';
    ctx.font = badgeFont;
    ctx.fillText(isMobile ? `T:${alert.measured_target.toFixed(0)}` : `TARGET: ${alert.measured_target.toFixed(1)}`, width - paddingRight + 4, yTarget + (isMobile ? 2.5 : 3));

    // 4. Draw Invalidation Level
    const yInval = getY(alert.invalidation_level);
    ctx.strokeStyle = '#e11d48';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(paddingLeft, yInval);
    ctx.lineTo(width - paddingRight, yInval);
    ctx.stroke();
    ctx.setLineDash([]);

    // Invalidation Badge
    ctx.fillStyle = '#e11d48';
    ctx.fillRect(width - paddingRight + 2, yInval - (isMobile ? 6.5 : 8), badgeW, badgeH);
    ctx.fillStyle = '#ffffff';
    ctx.font = badgeFont;
    ctx.fillText(isMobile ? `SL:${alert.invalidation_level.toFixed(0)}` : `INVAL: ${alert.invalidation_level.toFixed(1)}`, width - paddingRight + 4, yInval + (isMobile ? 2.5 : 3));

    // 5. Draw Breakout Candle Marker Badge
    const breakLocalIdx = visibleCandles.findIndex((c) => c.timestamp === alert.breakout_candle_timestamp);
    if (breakLocalIdx !== -1) {
      const bx = getX(breakLocalIdx);
      const bCandle = visibleCandles[breakLocalIdx];
      const by = isW ? getY(bCandle.high) - (isMobile ? 12 : 15) : getY(bCandle.low) + (isMobile ? 16 : 20);
      const brkLabel = isW ? 'BREAKOUT ↑' : 'BREAKDOWN ↓';
      const m = ctx.measureText(brkLabel);
      const bW = m.width + (isMobile ? 6 : 14);
      const bH = isMobile ? 13 : 16;

      ctx.fillStyle = isW ? '#059669' : '#e11d48';
      ctx.fillRect(bx - bW / 2, by - (isMobile ? 6.5 : 8), bW, bH);
      ctx.fillStyle = '#ffffff';
      ctx.font = badgeFont;
      ctx.textAlign = 'center';
      ctx.fillText(brkLabel, bx, by + (isMobile ? 2.5 : 3));
    }
  }, [alert, candles]);

  if (isLoading) {
    return (
      <div className="w-full max-w-5xl mx-auto px-4 py-16 flex flex-col items-center justify-center space-y-3">
        <RefreshCw className="h-8 w-8 text-blue-600 animate-spin" />
        <p className="text-sm font-semibold text-slate-600">Loading confirmed M/W breakout signal...</p>
      </div>
    );
  }

  if (error || !alert) {
    return (
      <div className="w-full max-w-3xl mx-auto px-4 py-12 text-center space-y-4">
        <div className="p-3 bg-rose-50 text-rose-600 rounded-2xl w-fit mx-auto border border-rose-200">
          <AlertCircle className="h-8 w-8" />
        </div>
        <h2 className="text-xl font-bold text-slate-900">Breakout Signal Not Found</h2>
        <p className="text-xs text-slate-500">{error || 'This alert could not be found or has expired.'}</p>
        <button
          onClick={() => navigate('/mw-breakouts')}
          className="min-h-[44px] px-5 py-2 rounded-xl bg-slate-900 text-white font-bold text-xs shadow-xs"
        >
          Back to M/W Breakouts
        </button>
      </div>
    );
  }

  const isW = alert.pattern_type === 'W';
  const currSym = alert.symbol.includes('BTC') || alert.symbol.includes('ETH') ? '$' : '₹';

  return (
    <div className="w-full max-w-6xl mx-auto space-y-4 sm:space-y-6 min-w-0">
      {/* Top Navigation */}
      <div>
        <button
          onClick={() => navigate('/mw-breakouts')}
          className="inline-flex items-center gap-2 min-h-[38px] sm:min-h-[44px] px-3.5 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-bold text-xs shadow-2xs transition-all cursor-pointer"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back to M/W Breakouts</span>
        </button>
      </div>

      {/* Signal Header Banner */}
      <div
        className={`p-5 sm:p-6 rounded-3xl border shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
          isW
            ? 'bg-gradient-to-r from-emerald-50 via-white to-emerald-50/30 border-emerald-200'
            : 'bg-gradient-to-r from-rose-50 via-white to-rose-50/30 border-rose-200'
        }`}
      >
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`px-3 py-1 rounded-xl text-xs font-black tracking-wide text-white shadow-xs ${
                isW ? 'bg-emerald-600' : 'bg-rose-600'
              }`}
            >
              {isW ? '🟢 W PATTERN BREAKOUT' : '🔴 M PATTERN BREAKDOWN'}
            </span>
            <span
              className={`px-2.5 py-1 rounded-lg text-xs font-bold border ${
                isW
                  ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                  : 'bg-rose-100 text-rose-800 border-rose-200'
              }`}
            >
              {isW ? 'UP BREAKOUT' : 'DOWN BREAKOUT'}
            </span>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <h1 className="text-2xl sm:text-3xl font-black text-slate-900">{alert.symbol}</h1>
            <span className="px-2.5 py-0.5 rounded-lg bg-slate-100 text-slate-700 font-bold text-sm font-mono border border-slate-200">
              {alert.timeframe}
            </span>
          </div>

          {/* Exact Breakout Timestamp in Asia/Kolkata */}
          <div className="flex items-center gap-2 text-xs text-slate-600 pt-1 font-mono">
            <Clock className="h-4 w-4 text-blue-600" />
            <span>Breakout Confirmed:</span>
            <span className="font-bold text-slate-900">
              {formatCandleDate(alert.breakout_candle_timestamp, alert.symbol)} • {formatMarketTime(alert.breakout_candle_timestamp, alert.symbol)}
            </span>
          </div>
        </div>

        {/* Status Badge & Quality Score */}
        <div className="flex sm:flex-col items-end justify-between sm:justify-center gap-2">
          <div
            className={`px-3.5 py-1.5 rounded-xl text-xs font-black tracking-wide flex items-center gap-1.5 border shadow-2xs ${
              alert.status === 'TARGET_1_HIT'
                ? 'bg-emerald-600 text-white border-emerald-700'
                : alert.status === 'INVALIDATED'
                ? 'bg-rose-600 text-white border-rose-700'
                : 'bg-blue-600 text-white border-blue-700'
            }`}
          >
            {alert.status === 'TARGET_1_HIT' ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : alert.status === 'INVALIDATED' ? (
              <XCircle className="h-4 w-4" />
            ) : (
              <span className="h-2 w-2 rounded-full bg-white animate-pulse" />
            )}
            <span>STATUS: {alert.status}</span>
          </div>

          <div className="text-right">
            <span className="text-[11px] font-bold text-slate-500 uppercase block">Pattern Quality</span>
            <span className="text-lg font-black text-slate-900 font-mono">{alert.quality_score}/100</span>
          </div>
        </div>
      </div>

      {/* Focused Pattern Canvas Chart */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-bold text-slate-700 uppercase tracking-wider">
            <BarChart2 className="h-4 w-4 text-blue-600" />
            <span>FOCUSED PATTERN STRUCTURE & TARGET CHART</span>
          </div>
          <span className="text-[11px] font-medium text-slate-500">
            Auto-centered on {alert.symbol} ({alert.timeframe}) breakout structure
          </span>
        </div>

        <div className="relative w-full h-[360px] sm:h-[420px] rounded-3xl overflow-hidden bg-white border border-slate-200 shadow-sm">
          <canvas ref={canvasRef} className="w-full h-full block" />
        </div>
      </div>

      {/* Structured Metrics 4-Column Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Pattern Geometry */}
        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2.5">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-wider border-b pb-1 flex items-center justify-between">
            <span>Pattern Geometry</span>
            <Target className="h-3.5 w-3.5 text-purple-600" />
          </div>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-600">{isW ? 'Low 1 (S1):' : 'High 1 (S1):'}</span>
              <span className="font-mono font-bold text-slate-900">{currSym}{alert.s1_price.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600">{isW ? 'Low 2 (S2):' : 'High 2 (S2):'}</span>
              <span className="font-mono font-bold text-slate-900">{currSym}{alert.s2_price.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600">Neckline:</span>
              <span className="font-mono font-bold text-purple-700">{currSym}{alert.neckline_price.toLocaleString()}</span>
            </div>
            <div className="flex justify-between pt-1 border-t border-slate-100">
              <span className="text-slate-600">Pattern Height:</span>
              <span className="font-mono font-semibold text-slate-900">{currSym}{alert.pattern_height.toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* Card 2: Breakout Confirmation */}
        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2.5">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-wider border-b pb-1 flex items-center justify-between">
            <span>Breakout Confirmation</span>
            <Zap className="h-3.5 w-3.5 text-amber-500" />
          </div>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-600">Breakout Close:</span>
              <span className={`font-mono font-bold ${isW ? 'text-emerald-700' : 'text-rose-700'}`}>
                {currSym}{alert.breakout_close.toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600">Trendline Level:</span>
              <span className="font-mono text-slate-800">{currSym}{alert.trendline_price.toLocaleString()} ✓</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600">20 EMA Level:</span>
              <span className="font-mono text-slate-800">{currSym}{alert.ema20_price.toLocaleString()} ✓</span>
            </div>
            <div className="flex justify-between pt-1 border-t border-slate-100">
              <span className="text-slate-600">Relative Volume:</span>
              <span className="font-mono font-bold text-blue-600">{alert.relative_volume}× ✓</span>
            </div>
          </div>
        </div>

        {/* Card 3: Measured Target & Projections */}
        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2.5">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-wider border-b pb-1 flex items-center justify-between">
            <span>Target & Projection</span>
            <Target className="h-3.5 w-3.5 text-emerald-600" />
          </div>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-600">Measured Target 1:</span>
              <span className="font-mono font-black text-emerald-600">{currSym}{alert.measured_target.toLocaleString()}</span>
            </div>
            {alert.target_2 && (
              <div className="flex justify-between">
                <span className="text-slate-600">Major Target 2:</span>
                <span className="font-mono font-bold text-emerald-700">{currSym}{alert.target_2.toLocaleString()}</span>
              </div>
            )}
            {alert.nearest_resistance && isW && (
              <div className="flex justify-between">
                <span className="text-slate-600">Nearest Resistance:</span>
                <span className="font-mono text-amber-700">{currSym}{alert.nearest_resistance.toLocaleString()}</span>
              </div>
            )}
            {alert.nearest_support && !isW && (
              <div className="flex justify-between">
                <span className="text-slate-600">Nearest Support:</span>
                <span className="font-mono text-amber-700">{currSym}{alert.nearest_support.toLocaleString()}</span>
              </div>
            )}
          </div>
        </div>

        {/* Card 4: Invalidation & Risk */}
        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2.5">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-wider border-b pb-1 flex items-center justify-between">
            <span>Invalidation & Risk</span>
            <ShieldAlert className="h-3.5 w-3.5 text-rose-500" />
          </div>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-600">Invalidation Level:</span>
              <span className="font-mono font-bold text-rose-600">{currSym}{alert.invalidation_level.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-600">Invalidation Rule:</span>
              <span className="text-slate-800 text-[11px] font-medium">
                {isW ? 'Close < Neckline' : 'Close > Neckline'}
              </span>
            </div>
            <div className="flex justify-between pt-1 border-t border-slate-100">
              <span className="text-slate-600">Candle State:</span>
              <span className="font-bold text-emerald-600">CLOSED ✓</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
