import React, { useEffect, useRef, useState, useCallback } from 'react';
import { api } from '../services/api';
import { MWBreakoutAlert } from '../types';
import {
  formatCandleTime,
  formatCandleDate,
  formatMarketTime,
  formatMarketDateTime,
  formatMarketTimeWithSeconds
} from '../utils/time';
import {
  Layers,
  RefreshCw,
  TrendingUp,
  Sliders,
  Check,
  X,
  Zap,
  Radio,
  Clock,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  ArrowRight,
  ChevronLeft,
  Target,
  Activity,
  Eye,
  EyeOff,
  Info
} from 'lucide-react';

interface ChartViewProps {
  symbol: string;
  timeframe?: '4H' | '1H' | '15M' | '5M';
  onSelectTimeframe?: (tf: '4H' | '1H' | '15M' | '5M') => void;
  keySupports?: number[];
  keyResistances?: number[];
  invalidationLevel?: number | null;
  onActivePatternChange?: (pattern: any, alert: MWBreakoutAlert | null) => void;
}

// Module-level instant memory cache for 0ms timeframe switching and zero-latency chart rendering
const chartMemoryCache = new Map<string, any>();

export const ChartView: React.FC<ChartViewProps> = ({
  symbol,
  timeframe: propTimeframe = '15M',
  onSelectTimeframe,
  keySupports = [],
  keyResistances = [],
  invalidationLevel,
  onActivePatternChange
}) => {
  // Timeframe state
  const [internalTimeframe, setInternalTimeframe] = useState<'4H' | '1H' | '15M' | '5M'>(propTimeframe);
  const activeTimeframe = onSelectTimeframe ? propTimeframe : internalTimeframe;

  const initialKey = `${symbol}_${activeTimeframe}`;
  const [chartData, setChartData] = useState<any>(() => chartMemoryCache.get(initialKey) || null);
  const [isLoading, setIsLoading] = useState<boolean>(() => !chartMemoryCache.has(initialKey));

  const handleTimeframeChange = (tf: '4H' | '1H' | '15M' | '5M') => {
    setInternalTimeframe(tf);
    if (onSelectTimeframe) {
      onSelectTimeframe(tf);
    }
    // Instant cache check on timeframe change
    const nextKey = `${symbol}_${tf}`;
    if (chartMemoryCache.has(nextKey)) {
      const cached = chartMemoryCache.get(nextKey);
      setChartData(cached);
      setIsLoading(false);
      if (onActivePatternChange) {
        onActivePatternChange(cached.active_wm_pattern || null, cached.active_wm_alert || null);
      }
    }
    // Reset pan & restore auto-follow on timeframe switch
    setPanOffset(0);
    setIsAutoFollow(true);
  };

  // Pan & Zoom Engine State
  const [candleSpacing, setCandleSpacing] = useState<number>(11); // Zoom scale: 4px to 40px
  const [panOffset, setPanOffset] = useState<number>(0);          // 0 = live edge, >0 = bars back into history
  const [isAutoFollow, setIsAutoFollow] = useState<boolean>(true); // true = snap with latest candles

  // Drag interaction state
  const isDraggingRef = useRef<boolean>(false);
  const dragStartXRef = useRef<number>(0);
  const dragStartPanRef = useRef<number>(0);

  // Hover Crosshair & Tooltip state
  const [hoverData, setHoverData] = useState<{
    candle: any;
    x: number;
    y: number;
  } | null>(null);

  // Overlay Settings Drawer
  const [isOverlayPanelOpen, setIsOverlayPanelOpen] = useState(false);

  // Granular Overlay States
  const [showEma20, setShowEma20] = useState(true);
  const [showEma50, setShowEma50] = useState(true);
  const [showEma200, setShowEma200] = useState(true);

  const [showChoch, setShowChoch] = useState(true);
  const [showBos, setShowBos] = useState(true);
  const [showTlBreaks, setShowTlBreaks] = useState(true);
  const [showSrBreaks, setShowSrBreaks] = useState(true);
  const [showPrecisionBreakouts, setShowPrecisionBreakouts] = useState(true);

  // Trendline Granular Controls
  const [showPrimaryTrendlines, setShowPrimaryTrendlines] = useState(true);
  const [showSecondaryTrendlines, setShowSecondaryTrendlines] = useState(true);
  const [showMinorTrendlines, setShowMinorTrendlines] = useState(true);
  const [showBrokenTrendlines, setShowBrokenTrendlines] = useState(false);
  const [showAnchorPoints, setShowAnchorPoints] = useState(true);

  // Live Price Line toggle
  const [showLivePriceLine, setShowLivePriceLine] = useState(true);
  const [showSRZones, setShowSRZones] = useState(true);

  // W/M Structural Pattern Visualization States (Uncluttered Chart Rules)
  const [showActiveWmPattern, setShowActiveWmPattern] = useState(true);
  const [showPatternHistory, setShowPatternHistory] = useState(false);
  const [showWmDebug, setShowWmDebug] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const isCryptoOrUsd = symbol.includes('BTC') || symbol.includes('USD');
  const currSym = isCryptoOrUsd ? '$' : '₹';

  const anyEmaActive = showEma20 || showEma50 || showEma200;
  const anyBreaksActive = showChoch || showBos || showTlBreaks || showSrBreaks;
  const anyTrendlinesActive = showPrimaryTrendlines || showSecondaryTrendlines || showMinorTrendlines;

  const toggleAllEmas = () => {
    const nextState = !anyEmaActive;
    setShowEma20(nextState);
    setShowEma50(nextState);
    setShowEma200(nextState);
  };

  const toggleAllBreaks = () => {
    const nextState = !anyBreaksActive;
    setShowChoch(nextState);
    setShowBos(nextState);
    setShowTlBreaks(nextState);
    setShowSrBreaks(nextState);
  };

  const toggleAllTrendlines = () => {
    const nextState = !anyTrendlinesActive;
    setShowPrimaryTrendlines(nextState);
    setShowSecondaryTrendlines(nextState);
    setShowMinorTrendlines(nextState);
  };

  // Zoom Controls
  const zoomIn = () => setCandleSpacing((s) => Math.min(38, Math.round(s * 1.25)));
  const zoomOut = () => setCandleSpacing((s) => Math.max(4, Math.round(s * 0.8)));
  const resetZoomAndPan = () => {
    setCandleSpacing(11);
    setPanOffset(0);
    setIsAutoFollow(true);
  };

  const goToLive = () => {
    setPanOffset(0);
    setIsAutoFollow(true);
  };

  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState<number>(800);

  // Responsive container width tracking
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleResize = () => {
      if (container.clientWidth > 0) {
        setContainerWidth(container.clientWidth);
      }
    };

    handleResize();

    const resizeObserver = new ResizeObserver(() => {
      handleResize();
    });
    resizeObserver.observe(container);
    window.addEventListener('resize', handleResize);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  // Fetch real market data for active timeframe with instant cache hit
  const fetchChart = useCallback(async (showSpinner = false) => {
    const cacheKey = `${symbol}_${activeTimeframe}`;
    if (chartMemoryCache.has(cacheKey)) {
      const cached = chartMemoryCache.get(cacheKey);
      setChartData(cached);
      setIsLoading(false);
      if (onActivePatternChange) {
        onActivePatternChange(cached.active_wm_pattern || null, cached.active_wm_alert || null);
      }
    } else if (showSpinner) {
      setIsLoading(true);
    }

    try {
      const data = await api.getChartData(symbol, activeTimeframe, 250);
      chartMemoryCache.set(cacheKey, data);
      setChartData(data);
      if (onActivePatternChange) {
        onActivePatternChange(data.active_wm_pattern || null, data.active_wm_alert || null);
      }
    } catch (err) {
      console.error('Failed to load chart data:', err);
    } finally {
      setIsLoading(false);
    }
  }, [symbol, activeTimeframe]);

  useEffect(() => {
    fetchChart(true);
    // Smooth background auto-refresh every 20 seconds without blocking UI
    const interval = setInterval(() => {
      fetchChart(false);
    }, 20000);

    return () => clearInterval(interval);
  }, [fetchChart]);

  // Render chart on canvas with Pan/Zoom viewport
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !chartData || !chartData.candles || chartData.candles.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.parentElement?.clientWidth || containerWidth || 800;
    const isMobile = width < 640;
    const isSmallMobile = width < 420;

    const height = isMobile ? (isSmallMobile ? 330 : 370) : 480;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);

    // Crisp Light Background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);

    const candles = chartData.candles;
    const totalCandles = candles.length;

    const paddingLeft = isSmallMobile ? 6 : isMobile ? 8 : 14;
    const paddingRight = isSmallMobile ? 54 : isMobile ? 62 : 85;
    const paddingTop = isMobile ? 18 : 24;
    const paddingBottom = isMobile ? 22 : 32;

    const chartWidth = width - paddingLeft - paddingRight;
    const chartHeight = height - paddingTop - paddingBottom;

    // Viewport calculations based on zoom (candleSpacing) and panOffset
    const visibleCapacity = Math.max(5, Math.floor(chartWidth / candleSpacing));
    const effectivePan = Math.max(0, Math.min(totalCandles - 5, panOffset));

    const endIdx = Math.max(0, totalCandles - 1 - effectivePan);
    const startIdx = Math.max(0, endIdx - visibleCapacity + 1);

    const visibleCandles = candles.slice(startIdx, endIdx + 1);
    if (visibleCandles.length === 0) return;

    const candleWidth = Math.max(2, Math.floor(candleSpacing * 0.72));

    // Determine min/max price bounds from visible window
    let minPrice = Infinity;
    let maxPrice = -Infinity;

    visibleCandles.forEach((c: any) => {
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
      if (showEma20 && c.ema_20) {
        if (c.ema_20 < minPrice) minPrice = c.ema_20;
        if (c.ema_20 > maxPrice) maxPrice = c.ema_20;
      }
      if (showEma50 && c.ema_50) {
        if (c.ema_50 < minPrice) minPrice = c.ema_50;
        if (c.ema_50 > maxPrice) maxPrice = c.ema_50;
      }
      if (showEma200 && c.ema_200) {
        if (c.ema_200 < minPrice) minPrice = c.ema_200;
        if (c.ema_200 > maxPrice) maxPrice = c.ema_200;
      }
    });

    // Add 6% headroom and footroom
    const priceRange = Math.max(0.01, maxPrice - minPrice);
    minPrice -= priceRange * 0.06;
    maxPrice += priceRange * 0.06;
    const fullRange = maxPrice - minPrice;

    const getY = (price: number) => {
      return paddingTop + chartHeight - ((price - minPrice) / fullRange) * chartHeight;
    };

    const getX = (candleIndex: number) => {
      return paddingLeft + (candleIndex - startIdx) * candleSpacing + candleSpacing / 2;
    };

    // -------------------------------------------------------------
    // 1. Gridlines & Right Price Scale
    // -------------------------------------------------------------
    ctx.strokeStyle = '#f1f5f9';
    ctx.lineWidth = 1;

    const priceSteps = isMobile ? 4 : 6;
    for (let i = 0; i <= priceSteps; i++) {
      const priceVal = minPrice + (fullRange / priceSteps) * i;
      const y = getY(priceVal);

      // Horizontal grid line
      ctx.beginPath();
      ctx.moveTo(paddingLeft, y);
      ctx.lineTo(paddingLeft + chartWidth, y);
      ctx.stroke();

      // Right price text
      ctx.fillStyle = '#64748b';
      ctx.font = isSmallMobile ? 'bold 8px monospace' : isMobile ? 'bold 8.5px monospace' : '10px monospace';
      ctx.textAlign = 'left';
      const formattedPrice = `${currSym}${priceVal >= 1000 ? priceVal.toFixed(1) : priceVal.toFixed(2)}`;
      ctx.fillText(formattedPrice, paddingLeft + chartWidth + (isMobile ? 3 : 6), y + 3.5);
    }

    // -------------------------------------------------------------
    // 2. Support / Resistance Liquidity Bands
    // -------------------------------------------------------------
    if (showSRZones) {
      keySupports.forEach((sup, idx) => {
        const y = getY(sup);
        if (y >= paddingTop && y <= paddingTop + chartHeight) {
          ctx.strokeStyle = 'rgba(22, 163, 74, 0.45)';
          ctx.lineWidth = idx === 0 ? 1.8 : 1.2;
          ctx.setLineDash([5, 4]);
          ctx.beginPath();
          ctx.moveTo(paddingLeft, y);
          ctx.lineTo(paddingLeft + chartWidth, y);
          ctx.stroke();
          ctx.setLineDash([]);

          ctx.fillStyle = '#16a34a';
          ctx.font = isMobile ? 'bold 7.5px sans-serif' : 'bold 9px sans-serif';
          ctx.textAlign = 'right';
          ctx.fillText(`SUP ${currSym}${sup.toFixed(isMobile ? 0 : 1)}`, paddingLeft + chartWidth - (isMobile ? 3 : 6), y - 3.5);
        }
      });

      keyResistances.forEach((res, idx) => {
        const y = getY(res);
        if (y >= paddingTop && y <= paddingTop + chartHeight) {
          ctx.strokeStyle = 'rgba(220, 38, 38, 0.45)';
          ctx.lineWidth = idx === 0 ? 1.8 : 1.2;
          ctx.setLineDash([5, 4]);
          ctx.beginPath();
          ctx.moveTo(paddingLeft, y);
          ctx.lineTo(paddingLeft + chartWidth, y);
          ctx.stroke();
          ctx.setLineDash([]);

          ctx.fillStyle = '#dc2626';
          ctx.font = isMobile ? 'bold 7.5px sans-serif' : 'bold 9px sans-serif';
          ctx.textAlign = 'right';
          ctx.fillText(`RES ${currSym}${res.toFixed(isMobile ? 0 : 1)}`, paddingLeft + chartWidth - (isMobile ? 3 : 6), y - 3.5);
        }
      });

      // -------------------------------------------------------------
      // 3. Structural Invalidation Level (Stop Loss Line)
      // -------------------------------------------------------------
      if (invalidationLevel) {
        const y = getY(invalidationLevel);
        if (y >= paddingTop && y <= paddingTop + chartHeight) {
          ctx.strokeStyle = 'rgba(217, 119, 6, 0.65)';
          ctx.lineWidth = 1.4;
          ctx.setLineDash([3, 3]);
          ctx.beginPath();
          ctx.moveTo(paddingLeft, y);
          ctx.lineTo(paddingLeft + chartWidth, y);
          ctx.stroke();
          ctx.setLineDash([]);

          ctx.fillStyle = '#d97706';
          ctx.font = isMobile ? 'bold 7.5px sans-serif' : 'bold 9px sans-serif';
          ctx.textAlign = 'right';
          ctx.fillText(isMobile ? 'INVAL (SL)' : 'INVALIDATION (SL)', paddingLeft + chartWidth - (isMobile ? 3 : 6), y - 3.5);
        }
      }
    }

    // -------------------------------------------------------------
    // 4. Multi-Trendlines Rendering
    // -------------------------------------------------------------
    if (chartData.trendlines) {
      chartData.trendlines.forEach((tl: any) => {
        const isSupport = tl.line_type === 'ASCENDING_SUPPORT';
        const rank = tl.rank || 'PRIMARY';
        const isBroken = tl.is_broken || tl.status === 'BROKEN';

        // Filter checks
        if (rank === 'PRIMARY' && !showPrimaryTrendlines) return;
        if (rank === 'SECONDARY' && !showSecondaryTrendlines) return;
        if (rank === 'MINOR' && !showMinorTrendlines) return;
        if (isBroken && !showBrokenTrendlines) return;

        const startIndex = Math.max(0, tl.p1_index);
        const endIndex = isBroken ? Math.min(totalCandles - 1, tl.end_index || tl.p2_index) : (totalCandles - 1);

        const x1 = getX(startIndex);
        const p1 = tl.p1_price + tl.slope * (startIndex - tl.p1_index);
        const y1 = getY(p1);

        const x2 = getX(endIndex);
        const p2 = tl.p1_price + tl.slope * (endIndex - tl.p1_index);
        const y2 = getY(p2);

        // Styling
        if (isSupport) {
          if (rank === 'PRIMARY') {
            ctx.strokeStyle = isBroken ? 'rgba(22, 163, 74, 0.4)' : '#16a34a';
            ctx.lineWidth = 2.4;
            ctx.setLineDash(isBroken ? [3, 4] : []);
          } else if (rank === 'SECONDARY') {
            ctx.strokeStyle = isBroken ? 'rgba(13, 148, 136, 0.4)' : '#0d9488';
            ctx.lineWidth = 1.8;
            ctx.setLineDash([6, 4]);
          } else {
            ctx.strokeStyle = isBroken ? 'rgba(52, 211, 153, 0.4)' : '#34d399';
            ctx.lineWidth = 1.2;
            ctx.setLineDash([3, 3]);
          }
        } else {
          if (rank === 'PRIMARY') {
            ctx.strokeStyle = isBroken ? 'rgba(220, 38, 38, 0.4)' : '#dc2626';
            ctx.lineWidth = 2.4;
            ctx.setLineDash(isBroken ? [3, 4] : []);
          } else if (rank === 'SECONDARY') {
            ctx.strokeStyle = isBroken ? 'rgba(225, 29, 72, 0.4)' : '#e11d48';
            ctx.lineWidth = 1.8;
            ctx.setLineDash([6, 4]);
          } else {
            ctx.strokeStyle = isBroken ? 'rgba(251, 113, 133, 0.4)' : '#fb7185';
            ctx.lineWidth = 1.2;
            ctx.setLineDash([3, 3]);
          }
        }

        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        ctx.setLineDash([]);

        // Render Anchor Points
        if (showAnchorPoints) {
          const points = tl.touch_points && tl.touch_points.length > 0
            ? tl.touch_points
            : [
                { index: tl.p1_index, price: tl.p1_price },
                { index: tl.p2_index, price: tl.p2_price }
              ];

          points.forEach((tp: any) => {
            if (tp.index >= startIdx && tp.index <= endIdx) {
              const xAnchor = getX(tp.index);
              const yAnchor = getY(tp.price);

              ctx.fillStyle = isSupport ? '#16a34a' : '#dc2626';
              ctx.beginPath();
              ctx.arc(xAnchor, yAnchor, rank === 'PRIMARY' ? 3.5 : 2.5, 0, 2 * Math.PI);
              ctx.fill();

              ctx.strokeStyle = '#ffffff';
              ctx.lineWidth = 1;
              ctx.stroke();
            }
          });
        }
      });
    }

    // -------------------------------------------------------------
    // 4. Moving Averages EMAs
    // -------------------------------------------------------------
    const drawLineSeries = (key: string, color: string) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      let started = false;

      for (let i = startIdx; i <= endIdx; i++) {
        const c = candles[i];
        if (c && c[key] !== null && c[key] !== undefined) {
          const x = getX(i);
          const y = getY(c[key]);
          if (!started) {
            ctx.moveTo(x, y);
            started = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
      }
      ctx.stroke();
    };

    if (showEma200) drawLineSeries('ema_200', '#9333ea');
    if (showEma50) drawLineSeries('ema_50', '#d97706');
    if (showEma20) drawLineSeries('ema_20', '#2563eb');

    // -------------------------------------------------------------
    // 5. Candlesticks (Visible Window Only)
    // -------------------------------------------------------------
    for (let i = startIdx; i <= endIdx; i++) {
      const c = candles[i];
      if (!c) continue;

      const xCenter = getX(i);
      const isBullish = c.close >= c.open;

      const yOpen = getY(c.open);
      const yClose = getY(c.close);
      const yHigh = getY(c.high);
      const yLow = getY(c.low);

      const bodyTop = Math.min(yOpen, yClose);
      const bodyHeight = Math.max(1.5, Math.abs(yClose - yOpen));

      ctx.strokeStyle = isBullish ? '#16a34a' : '#dc2626';
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(xCenter, yHigh);
      ctx.lineTo(xCenter, yLow);
      ctx.stroke();

      ctx.fillStyle = isBullish ? '#16a34a' : '#dc2626';
      ctx.fillRect(xCenter - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
    }

    // -------------------------------------------------------------
    // 6. Live Current Price Line & Beacon
    // -------------------------------------------------------------
    if (showLivePriceLine && totalCandles > 0) {
      const latestCandle = candles[totalCandles - 1];
      const livePrice = chartData.current_price || latestCandle.close;
      const liveY = getY(livePrice);
      const isCurrentBullish = latestCandle.close >= latestCandle.open;
      const liveColor = isCurrentBullish ? '#16a34a' : '#dc2626';

      if (liveY >= paddingTop && liveY <= paddingTop + chartHeight) {
        ctx.strokeStyle = liveColor;
        ctx.lineWidth = 1.4;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(paddingLeft, liveY);
        ctx.lineTo(paddingLeft + chartWidth, liveY);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = liveColor;
        ctx.beginPath();
        ctx.arc(paddingLeft + chartWidth, liveY, 3.5, 0, 2 * Math.PI);
        ctx.fill();

        // Right scale badge pill
        const badgeW = 78;
        const badgeH = 18;
        const badgeX = paddingLeft + chartWidth + 2;
        const badgeY = liveY - 9;

        ctx.fillStyle = liveColor;
        ctx.beginPath();
        if ((ctx as any).roundRect) {
          (ctx as any).roundRect(badgeX, badgeY, badgeW, badgeH, 4);
        } else {
          ctx.rect(badgeX, badgeY, badgeW, badgeH);
        }
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 10px monospace';
        ctx.textAlign = 'left';
        ctx.fillText(`${currSym}${livePrice.toFixed(2)}`, badgeX + 4, liveY + 3.5);
      }
    }

    // -------------------------------------------------------------
    // 6.5. Active W/M Structural Pattern (Clean Visualization - Max 1 Active)
    // -------------------------------------------------------------
    if (showActiveWmPattern && chartData) {
      let patternsToDraw: any[] = [];
      if (showPatternHistory && chartData.wm_patterns && chartData.wm_patterns.length > 0) {
        patternsToDraw = chartData.wm_patterns.slice(0, 3); // Max 3 in historical mode
      } else if (chartData.active_wm_pattern) {
        patternsToDraw = [chartData.active_wm_pattern];
      }

      patternsToDraw.forEach((pat: any, pIdx: number) => {
        const isBull = pat.pattern_type === 'W';
        const isMainActive = pIdx === 0;
        const alpha = isMainActive ? 0.95 : 0.40;
        const color = isBull ? `rgba(147, 51, 234, ${alpha})` : `rgba(225, 29, 72, ${alpha})`;
        const targetColor = isBull ? `rgba(16, 185, 129, ${alpha})` : `rgba(244, 63, 94, ${alpha})`;

        // 1. Structural connecting pattern lines: S1 -> Neckline -> S2
        const s1Idx = pat.s1_index;
        const neckIdx = pat.neckline_index;
        const s2Idx = pat.s2_index;

        if (s1Idx < candles.length && neckIdx < candles.length && s2Idx < candles.length) {
          const x1 = getX(s1Idx);
          const y1 = getY(pat.s1_price);
          const xN = getX(neckIdx);
          const yN = getY(pat.neckline_price);
          const x2 = getX(s2Idx);
          const y2 = getY(pat.s2_price);

          ctx.strokeStyle = color;
          ctx.lineWidth = isMainActive ? 2.0 : 1.2;
          ctx.setLineDash([4, 2]);
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(xN, yN);
          ctx.lineTo(x2, y2);
          ctx.stroke();
          ctx.setLineDash([]);

          // Draw vertex dots with labels
          [
            { x: x1, y: y1, lbl: isBull ? 'LOW 1' : 'HIGH 1', price: pat.s1_price },
            { x: xN, y: yN, lbl: 'NECKLINE', price: pat.neckline_price },
            { x: x2, y: y2, lbl: isBull ? 'LOW 2' : 'HIGH 2', price: pat.s2_price }
          ].forEach((pt) => {
            if (pt.x >= paddingLeft - 20 && pt.x <= paddingLeft + chartWidth + 20) {
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(pt.x, pt.y, isMainActive ? 3.5 : 2.5, 0, 2 * Math.PI);
              ctx.fill();

              ctx.fillStyle = isBull ? '#9333ea' : '#e11d48';
              ctx.font = 'bold 8px monospace';
              ctx.textAlign = 'center';
              const labelY = isBull ? pt.y + 11 : pt.y - 6;
              ctx.fillText(`${pt.lbl} (${pt.price.toFixed(1)})`, pt.x, labelY);
            }
          });
        }

        // 2. Draw SINGLE horizontal Neckline level
        if (pat.neckline_price) {
          const neckY = getY(pat.neckline_price);
          if (neckY >= paddingTop && neckY <= paddingTop + chartHeight) {
            ctx.strokeStyle = color;
            ctx.lineWidth = isMainActive ? 1.5 : 1.0;
            ctx.setLineDash([6, 3]);
            ctx.beginPath();
            ctx.moveTo(paddingLeft, neckY);
            ctx.lineTo(paddingLeft + chartWidth, neckY);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = color;
            ctx.font = isMobile ? 'bold 7px sans-serif' : 'bold 8px sans-serif';
            ctx.textAlign = 'left';
            const neckLabel = isBull ? 'ACTIVE W NECKLINE' : 'ACTIVE M NECKLINE';
            const neckText = isMobile ? `${neckLabel}: ${currSym}${pat.neckline_price.toFixed(isMobile ? 0 : 2)}` : `${neckLabel}: ${currSym}${pat.neckline_price.toFixed(2)}`;
            ctx.fillText(neckText, paddingLeft + 6, neckY - 3);
          }
        }

        // 3. Draw SINGLE horizontal Measured Target 1 level
        const measuredTarget = pat.target_analysis?.measured_target;
        if (measuredTarget) {
          const targetY = getY(measuredTarget);
          if (targetY >= paddingTop && targetY <= paddingTop + chartHeight) {
            ctx.strokeStyle = targetColor;
            ctx.lineWidth = isMainActive ? 1.5 : 1.0;
            ctx.setLineDash([3, 3]);
            ctx.beginPath();
            ctx.moveTo(paddingLeft, targetY);
            ctx.lineTo(paddingLeft + chartWidth, targetY);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = targetColor;
            ctx.font = isMobile ? 'bold 7px sans-serif' : 'bold 8px sans-serif';
            ctx.textAlign = 'left';
            const targetLabel = isBull ? 'W TARGET 1' : 'M TARGET 1';
            const targetText = isMobile ? `${targetLabel}: ${currSym}${measuredTarget.toFixed(isMobile ? 0 : 2)}` : `${targetLabel}: ${currSym}${measuredTarget.toFixed(2)} (Score: ${pat.quality_score}/100)`;
            ctx.fillText(targetText, paddingLeft + 6, targetY - 3);
          }
        }

        // 4. Draw BREAKOUT marker on exact breakout candle if confirmed
        if (pat.breakout_candle_index !== undefined && pat.breakout_candle_index !== null) {
          const brkIdx = pat.breakout_candle_index;
          if (brkIdx >= startIdx && brkIdx <= endIdx && brkIdx < candles.length) {
            const brkX = getX(brkIdx);
            const brkPrice = pat.breakout_close || pat.neckline_price;
            const brkY = isBull ? getY(brkPrice) - (isMobile ? 14 : 18) : getY(brkPrice) + (isMobile ? 14 : 18);
            const isHighConf = pat.status === 'HIGH_CONFLUENCE_CONFIRMED' || pat.quality_score >= 75;
            const brkLabel = isBull 
              ? (isHighConf ? (isMobile ? 'W+TL+EMA ↑' : 'W + TL + EMA + VOL ↑') : 'W BREAKOUT ↑')
              : (isHighConf ? (isMobile ? 'M+TL+EMA ↓' : 'M + TL + EMA + VOL ↓') : 'M BREAKDOWN ↓');

            ctx.font = isMobile ? 'bold 7.5px sans-serif' : 'bold 9px sans-serif';
            const metrics = ctx.measureText(brkLabel);
            const boxW = metrics.width + (isMobile ? 8 : 12);
            const boxH = isMobile ? 13 : 16;
            const boxX = brkX - boxW / 2;
            const boxY = brkY - (isMobile ? 8 : 10);

            ctx.fillStyle = isBull ? '#16a34a' : '#dc2626';
            ctx.beginPath();
            if ((ctx as any).roundRect) {
              (ctx as any).roundRect(boxX, boxY, boxW, boxH, 3);
            } else {
              ctx.rect(boxX, boxY, boxW, boxH);
            }
            ctx.fill();

            ctx.fillStyle = '#ffffff';
            ctx.textAlign = 'center';
            ctx.fillText(brkLabel, brkX, brkY + (isMobile ? 1.5 : 2));
          }
        } else if (pat.status === 'BREAKOUT_FORMING' || pat.status === 'BREAKDOWN_FORMING') {
          // Draw Forming Indicator on latest candle
          const latestIdx = candles.length - 1;
          if (latestIdx >= startIdx && latestIdx <= endIdx) {
            const formX = getX(latestIdx);
            const formPrice = candles[latestIdx].close;
            const formY = isBull ? getY(formPrice) - 16 : getY(formPrice) + 16;
            const formLabel = isBull ? (isMobile ? '⏳ W FORMING' : '⏳ W BREAKOUT FORMING') : (isMobile ? '⏳ M FORMING' : '⏳ M BREAKDOWN FORMING');

            ctx.fillStyle = '#d97706';
            ctx.font = isMobile ? 'bold 7px sans-serif' : 'bold 8px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(formLabel, formX, formY);
          }
        }
      });
    }

    // -------------------------------------------------------------
    // 7. Structure Break Markers (CHoCH, BOS, TL, S/R, Precision Breakouts)
    // -------------------------------------------------------------
    const rawBreaks = chartData.breaks || chartData.structure_breaks || [];
    if (rawBreaks && rawBreaks.length > 0) {
      const drawnPatternKeys = new Set<string>();

      rawBreaks.forEach((b: any) => {
        const isPrecisionTlVol = b.event_type?.includes('TRENDLINE_EMA_VOLUME');
        const isPrecisionWm = b.event_type?.includes('PATTERN_TRENDLINE_EMA') || b.event_type?.includes('PATTERN_BREAK');
        const isChochEvent = b.event_type?.includes('CHOCH');
        const isBosEvent = b.event_type?.includes('BOS');
        const isTlEvent = b.event_type?.includes('TREND_LINE') || b.event_type?.includes('TRENDLINE');
        const isSrEvent = b.event_type?.includes('SUPPORT') || b.event_type?.includes('RESISTANCE');

        if ((isPrecisionTlVol || isPrecisionWm) && !showPrecisionBreakouts) return;
        if (isChochEvent && !showChoch) return;
        if (isBosEvent && !showBos) return;
        if (isTlEvent && !isPrecisionTlVol && !isPrecisionWm && !showTlBreaks) return;
        if (isSrEvent && !showSrBreaks) return;

        // Deduplication: ONE badge per pattern
        const dedupeKey = b.pattern_id || b.id || `${b.event_type}_${b.timestamp}`;
        if (drawnPatternKeys.has(dedupeKey)) return;
        drawnPatternKeys.add(dedupeKey);

        let targetCandleIndex = candles.findIndex((c: any) => c.time === b.timestamp);
        if (targetCandleIndex < 0 && b.break_candle_index !== undefined && b.break_candle_index < candles.length) {
          targetCandleIndex = b.break_candle_index;
        }

        if (targetCandleIndex >= startIdx && targetCandleIndex <= endIdx) {
          const x = getX(targetCandleIndex);
          const isBull = b.direction === 'BULLISH';
          const y = isBull ? getY(b.break_price) - (isMobile ? 13 : 16) : getY(b.break_price) + (isMobile ? 13 : 16);

          ctx.fillStyle = isBull ? '#16a34a' : '#dc2626';
          ctx.font = isMobile ? 'bold 7.5px sans-serif' : 'bold 9px sans-serif';
          ctx.textAlign = 'center';

          let label = 'BOS';
          if (b.event_type === 'TRENDLINE_EMA_VOLUME_UP_BREAKOUT') {
            label = isMobile ? 'TL+EMA UP' : 'TL + EMA + VOL UP';
          } else if (b.event_type === 'TRENDLINE_EMA_VOLUME_DOWN_BREAKOUT') {
            label = isMobile ? 'TL+EMA DN' : 'TL + EMA + VOL DOWN';
          } else if (b.event_type === 'W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT') {
            label = isMobile ? 'W+TL+EMA ↑' : 'W + TL + EMA + VOL ↑';
          } else if (b.event_type === 'M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT') {
            label = isMobile ? 'M+TL+EMA ↓' : 'M + TL + EMA + VOL ↓';
          } else if (b.event_type === 'W_PATTERN_BREAKOUT' || b.event_type?.includes('W_PAT')) {
            label = 'W BREAKOUT ↑';
          } else if (b.event_type === 'M_PATTERN_BREAKDOWN' || b.event_type?.includes('M_PAT')) {
            label = 'M BREAKDOWN ↓';
          } else if (isChochEvent) {
            label = 'CHoCH';
          } else if (isTlEvent) {
            label = 'TL BREAK';
          } else if (b.event_type.includes('SUPPORT')) {
            label = 'SUP BREAK';
          } else if (b.event_type.includes('RESISTANCE')) {
            label = 'RES BREAK';
          }

          // Draw highlight badge
          if (isPrecisionTlVol || isPrecisionWm) {
            const metrics = ctx.measureText(label);
            const boxW = metrics.width + (isMobile ? 6 : 10);
            const boxH = isMobile ? 12 : 15;
            const boxX = x - boxW / 2;
            const boxY = y - (isMobile ? 8 : 10);

            ctx.fillStyle = isBull ? '#16a34a' : '#dc2626';
            ctx.beginPath();
            if ((ctx as any).roundRect) {
              (ctx as any).roundRect(boxX, boxY, boxW, boxH, 3);
            } else {
              ctx.rect(boxX, boxY, boxW, boxH);
            }
            ctx.fill();

            ctx.fillStyle = '#ffffff';
            ctx.fillText(label, x, y + 1);
          } else {
            ctx.fillText(label, x, y);
          }

          ctx.beginPath();
          ctx.fillStyle = isBull ? '#16a34a' : '#dc2626';
          if (isBull) {
            ctx.moveTo(x, y + (isMobile ? 3 : 4));
            ctx.lineTo(x - 2.5, y + (isMobile ? 7 : 9));
            ctx.lineTo(x + 2.5, y + (isMobile ? 7 : 9));
          } else {
            ctx.moveTo(x, y - (isMobile ? 3 : 4));
            ctx.lineTo(x - 2.5, y - (isMobile ? 7 : 9));
            ctx.lineTo(x + 2.5, y - (isMobile ? 7 : 9));
          }
          ctx.closePath();
          ctx.fill();
        }
      });
    }

    // -------------------------------------------------------------
    // 8. Time Axis (X-Axis) Strictly Formatted in Asia/Kolkata (IST)
    // -------------------------------------------------------------
    ctx.fillStyle = '#64748b';
    ctx.font = isSmallMobile ? 'bold 7.5px monospace' : isMobile ? 'bold 8px monospace' : 'bold 9px monospace';
    ctx.textAlign = 'center';

    const labelDivisor = isSmallMobile ? 2.8 : isMobile ? 3.8 : 7;
    const labelInterval = Math.max(1, Math.floor(visibleCandles.length / labelDivisor));
    for (let i = startIdx; i <= endIdx; i += labelInterval) {
      const c = candles[i];
      if (!c) continue;
      const x = getX(i);
      const timeStr = formatCandleTime(c.time, symbol);
      ctx.fillText(timeStr, x, height - (isMobile ? 6 : 10));
    }
  }, [
    chartData,
    activeTimeframe,
    candleSpacing,
    panOffset,
    showEma20,
    showEma50,
    showEma200,
    showChoch,
    showBos,
    showTlBreaks,
    showSrBreaks,
    showPrimaryTrendlines,
    showSecondaryTrendlines,
    showMinorTrendlines,
    showBrokenTrendlines,
    showAnchorPoints,
    showLivePriceLine,
    showSRZones,
    showActiveWmPattern,
    showPatternHistory,
    keySupports,
    keyResistances,
    invalidationLevel,
    symbol,
    containerWidth
  ]);

  // Mouse Drag Panning Handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 0) return; // Left mouse click only
    isDraggingRef.current = true;
    dragStartXRef.current = e.clientX;
    dragStartPanRef.current = panOffset;
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !chartData || !chartData.candles || chartData.candles.length === 0) return;

    const candles = chartData.candles;
    const totalCandles = candles.length;

    const isMobile = canvas.clientWidth < 640;
    const isSmallMobile = canvas.clientWidth < 420;
    const paddingLeft = isSmallMobile ? 6 : isMobile ? 8 : 14;
    const paddingRight = isSmallMobile ? 54 : isMobile ? 62 : 85;
    const chartWidth = canvas.clientWidth - paddingLeft - paddingRight;

    if (isDraggingRef.current) {
      const deltaX = e.clientX - dragStartXRef.current;
      // Dragging to right (deltaX > 0) pulls older bars into view (increases panOffset)
      // Dragging to left (deltaX < 0) pulls newer bars into view (decreases panOffset)
      const deltaBars = Math.round(deltaX / candleSpacing);
      const newPan = Math.max(0, Math.min(totalCandles - 6, dragStartPanRef.current + deltaBars));
      setPanOffset(newPan);

      if (newPan > 0) {
        setIsAutoFollow(false);
      } else {
        setIsAutoFollow(true);
      }
      setHoverData(null);
    } else {
      // Calculate hovered candle
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const visibleCapacity = Math.max(5, Math.floor(chartWidth / candleSpacing));
      const effectivePan = Math.max(0, Math.min(totalCandles - 5, panOffset));
      const endIdx = Math.max(0, totalCandles - 1 - effectivePan);
      const startIdx = Math.max(0, endIdx - visibleCapacity + 1);

      const offsetIdx = Math.floor((mouseX - paddingLeft) / candleSpacing);
      const candleIdx = startIdx + offsetIdx;

      if (candleIdx >= startIdx && candleIdx <= endIdx && candleIdx < totalCandles) {
        setHoverData({
          candle: candles[candleIdx],
          x: mouseX,
          y: mouseY
        });
      } else {
        setHoverData(null);
      }
    }
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
  };

  const handleMouseLeave = () => {
    isDraggingRef.current = false;
    setHoverData(null);
  };

  // Wheel Zoom Listener
  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    if (e.deltaY < 0) {
      // Zoom In
      setCandleSpacing((s) => Math.min(38, Math.round(s * 1.15)));
    } else {
      // Zoom Out
      setCandleSpacing((s) => Math.max(4, Math.round(s * 0.85)));
    }
  };

  // Touch Swipe for Mobile Panning
  const touchStartXRef = useRef<number>(0);
  const touchStartPanRef = useRef<number>(0);

  const handleTouchStart = (e: React.TouchEvent<HTMLCanvasElement>) => {
    if (e.touches.length === 1) {
      touchStartXRef.current = e.touches[0].clientX;
      touchStartPanRef.current = panOffset;
    }
  };

  const handleTouchMove = (e: React.TouchEvent<HTMLCanvasElement>) => {
    if (e.touches.length === 1 && chartData?.candles) {
      const deltaX = e.touches[0].clientX - touchStartXRef.current;
      const deltaBars = Math.round(deltaX / candleSpacing);
      const newPan = Math.max(0, Math.min(chartData.candles.length - 6, touchStartPanRef.current + deltaBars));
      setPanOffset(newPan);
      if (newPan > 0) setIsAutoFollow(false);
      else setIsAutoFollow(true);
    }
  };

  const currentPrice = chartData?.current_price || (chartData?.candles && chartData.candles.length > 0 ? chartData.candles[chartData.candles.length - 1].close : null);
  const priceChange = chartData?.price_change;
  const priceChangePct = chartData?.price_change_pct;
  const isPriceUp = (priceChange ?? 0) >= 0;
  const marketSession = chartData?.market_session;
  const isMarketRunning = marketSession?.is_running ?? true;

  return (
    <div ref={containerRef} className="glass-panel rounded-2xl p-3 sm:p-5 shadow-xs flex flex-col gap-3 sm:gap-4 bg-white border border-slate-200 relative select-none w-full max-w-full min-w-0 overflow-hidden">
      {/* Top Banner: Real-Time Market Status & Live Current Price Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 sm:gap-3 bg-slate-50 p-2.5 sm:p-3 rounded-xl border border-slate-200 w-full min-w-0">
        {/* Current Live Price & Day Delta */}
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          {currentPrice !== null && (
            <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
              <span className="text-[10px] sm:text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                Current Price:
              </span>
              <span className="text-lg sm:text-xl font-black font-mono text-slate-900 truncate">
                {currSym}{currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              {priceChange !== undefined && (
                <span
                  className={`text-[11px] sm:text-xs font-mono font-bold px-1.5 sm:px-2 py-0.5 rounded-lg flex items-center gap-0.5 shrink-0 ${
                    isPriceUp ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                  }`}
                >
                  {isPriceUp ? '+' : ''}{priceChange.toFixed(2)} ({isPriceUp ? '+' : ''}{priceChangePct?.toFixed(2)}%)
                </span>
              )}
            </div>
          )}
        </div>

        {/* Live Market Running Indicator & Navigation Pill */}
        <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
          {/* Historical vs Live Follow Status Button */}
          {panOffset > 0 ? (
            <button
              onClick={goToLive}
              className="flex items-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-1 rounded-full text-[11px] sm:text-xs font-bold bg-amber-500 hover:bg-amber-600 text-white shadow-xs transition-all animate-pulse cursor-pointer"
              title="Click to restore live edge"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              <span>LIVE ({panOffset} back)</span>
            </button>
          ) : (
            <div className="flex items-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-1 rounded-full text-[11px] sm:text-xs font-bold bg-emerald-50 text-emerald-800 border border-emerald-300 shadow-2xs">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>LIVE FOLLOWING</span>
            </div>
          )}

          {/* Session Status */}
          <div
            className={`flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1 rounded-full text-[10px] sm:text-xs font-bold border shadow-2xs ${
              isMarketRunning
                ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                : 'bg-slate-100 text-slate-700 border-slate-300'
            }`}
          >
            <span
              className={`h-2 w-2 sm:h-2.5 sm:w-2.5 rounded-full ${
                isMarketRunning ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'
              }`}
            />
            <span>{marketSession?.message || (isMarketRunning ? '● LIVE' : '○ CLOSED')}</span>
          </div>

          <div className="hidden md:flex items-center gap-1 text-[11px] text-slate-500 font-mono">
            <Clock className="h-3 w-3 text-slate-400" />
            <span>
              {chartData?.latest_candle_time
                ? formatMarketTime(chartData.latest_candle_time, symbol)
                : 'Live'}
            </span>
          </div>
        </div>
      </div>

      {/* Header Toolbar: Timeframe Selector + Zoom / Overlay Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 sm:gap-3 border-b border-slate-200 pb-3 w-full min-w-0">
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap min-w-0">
          {/* Timeframe Selector (4H | 1H | 15M | 5M) */}
          <div className="flex items-center gap-0.5 sm:gap-1 bg-slate-100 p-0.5 sm:p-1 rounded-xl border border-slate-200 shadow-inner shrink-0">
            {(['4H', '1H', '15M', '5M'] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => handleTimeframeChange(tf)}
                className={`px-2.5 sm:px-3.5 py-1 sm:py-1.5 text-xs font-black rounded-lg transition-all cursor-pointer ${
                  activeTimeframe === tf
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-white'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Zoom Controls (+ / - / Reset) */}
          <div className="flex items-center gap-0.5 sm:gap-1 bg-slate-100 p-0.5 sm:p-1 rounded-xl border border-slate-200 shrink-0">
            <button
              onClick={zoomIn}
              className="p-1 sm:p-1.5 rounded-lg hover:bg-white text-slate-600 hover:text-slate-900 transition-all cursor-pointer min-h-[30px] min-w-[30px] flex items-center justify-center"
              title="Zoom In (or Wheel Up)"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={zoomOut}
              className="p-1 sm:p-1.5 rounded-lg hover:bg-white text-slate-600 hover:text-slate-900 transition-all cursor-pointer min-h-[30px] min-w-[30px] flex items-center justify-center"
              title="Zoom Out (or Wheel Down)"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={resetZoomAndPan}
              className="p-1 sm:p-1.5 rounded-lg hover:bg-white text-slate-600 hover:text-slate-900 transition-all cursor-pointer min-h-[30px] min-w-[30px] flex items-center justify-center"
              title="Reset Zoom & Pan"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Quick Visibility Pills */}
          <div className="hidden xl:flex items-center gap-1.5 text-xs">
            <button
              onClick={toggleAllTrendlines}
              className={`px-2.5 py-1 rounded-lg border font-semibold flex items-center gap-1 transition-all cursor-pointer ${
                anyTrendlinesActive
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-300'
                  : 'bg-slate-50 text-slate-400 border-slate-200'
              }`}
              title="Toggle Structural Trendlines"
            >
              <TrendingUp className="h-3 w-3" />
              <span>Trendlines</span>
            </button>

            <button
              onClick={toggleAllEmas}
              className={`px-2.5 py-1 rounded-lg border font-semibold flex items-center gap-1 transition-all cursor-pointer ${
                anyEmaActive
                  ? 'bg-blue-50 text-blue-700 border-blue-300'
                  : 'bg-slate-50 text-slate-400 border-slate-200'
              }`}
              title="Toggle EMAs (20, 50, 200)"
            >
              <Layers className="h-3 w-3" />
              <span>EMAs</span>
            </button>

            <button
              onClick={toggleAllBreaks}
              className={`px-2.5 py-1 rounded-lg border font-semibold flex items-center gap-1 transition-all cursor-pointer ${
                anyBreaksActive
                  ? 'bg-rose-50 text-rose-700 border-rose-300'
                  : 'bg-slate-50 text-slate-400 border-slate-200'
              }`}
              title="Toggle Break Markers (BOS, CHoCH, Breaks)"
            >
              <Zap className="h-3 w-3" />
              <span>Breaks</span>
            </button>

            {/* W/M Active Pattern Toggle */}
            <button
              onClick={() => setShowActiveWmPattern(!showActiveWmPattern)}
              className={`px-2.5 py-1 rounded-lg border font-semibold flex items-center gap-1 transition-all cursor-pointer ${
                showActiveWmPattern
                  ? 'bg-purple-50 text-purple-700 border-purple-300'
                  : 'bg-slate-50 text-slate-400 border-slate-200'
              }`}
              title="Toggle Active W/M Pattern & Target"
            >
              <Target className="h-3 w-3" />
              <span>W/M Pattern</span>
            </button>

            {/* W/M History Toggle */}
            <button
              onClick={() => setShowPatternHistory(!showPatternHistory)}
              className={`px-2 py-1 rounded-lg border font-semibold flex items-center gap-1 transition-all cursor-pointer text-[11px] ${
                showPatternHistory
                  ? 'bg-indigo-600 text-white border-indigo-600 shadow-2xs'
                  : 'bg-slate-50 text-slate-500 border-slate-200 hover:bg-slate-100'
              }`}
              title="Toggle Past W/M Patterns (Default Off for Clean Chart)"
            >
              <span>History: {showPatternHistory ? 'ON' : 'OFF'}</span>
            </button>

            {/* W/M Debug Diagnostics Toggle */}
            <button
              onClick={() => setShowWmDebug(!showWmDebug)}
              className={`px-2 py-1 rounded-lg border font-semibold flex items-center gap-1 transition-all cursor-pointer text-[11px] ${
                showWmDebug
                  ? 'bg-amber-500 text-white border-amber-500 shadow-2xs'
                  : 'bg-slate-50 text-slate-500 border-slate-200 hover:bg-slate-100'
              }`}
              title="Show Structural W/M Detection Debug Diagnostics"
            >
              <Activity className="h-3 w-3" />
              <span>Debug HUD</span>
            </button>
          </div>
        </div>

        {/* Right Action: Overlay Manager Drawer */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsOverlayPanelOpen(!isOverlayPanelOpen)}
            className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
              isOverlayPanelOpen
                ? 'bg-blue-600 text-white border-blue-600 shadow-xs'
                : 'bg-slate-50 hover:bg-slate-100 border-slate-200 text-slate-700'
            }`}
          >
            <Sliders className="h-3.5 w-3.5" />
            <span>Overlays & Controls</span>
          </button>
        </div>
      </div>

      {/* Floating Overlays Drawer */}
      {isOverlayPanelOpen && (
        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-sm grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4 text-xs">
          {/* Trendline Controls */}
          <div className="space-y-2">
            <span className="font-bold text-[11px] text-slate-700 uppercase tracking-wider block">
              Trendline Layers
            </span>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showPrimaryTrendlines}
                onChange={(e) => setShowPrimaryTrendlines(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>Primary Trendlines</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showSecondaryTrendlines}
                onChange={(e) => setShowSecondaryTrendlines(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>Secondary Trendlines</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showMinorTrendlines}
                onChange={(e) => setShowMinorTrendlines(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>Minor Trendlines</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showBrokenTrendlines}
                onChange={(e) => setShowBrokenTrendlines(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>Show Broken Trendlines</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showAnchorPoints}
                onChange={(e) => setShowAnchorPoints(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>Show Anchor Points</span>
            </label>
          </div>

          {/* EMAs */}
          <div className="space-y-2">
            <span className="font-bold text-[11px] text-slate-700 uppercase tracking-wider block">
              Moving Averages
            </span>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showEma20}
                onChange={(e) => setShowEma20(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-blue-600" /> EMA 20 (Fast)
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showEma50}
                onChange={(e) => setShowEma50(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-amber-600" /> EMA 50 (Trend)
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showEma200}
                onChange={(e) => setShowEma200(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-purple-600" /> EMA 200 (Macro)
              </span>
            </label>
          </div>

          {/* Structure Events */}
          <div className="space-y-2">
            <span className="font-bold text-[11px] text-slate-700 uppercase tracking-wider block">
              Structure Markers
            </span>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showChoch}
                onChange={(e) => setShowChoch(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>CHoCH (Character Change)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showBos}
                onChange={(e) => setShowBos(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>BOS (Structure Break)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showTlBreaks}
                onChange={(e) => setShowTlBreaks(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>Trendline Breaks</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showSrBreaks}
                onChange={(e) => setShowSrBreaks(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>S/R Breakouts</span>
            </label>
          </div>

          {/* Live Price & Zones */}
          <div className="space-y-2">
            <span className="font-bold text-[11px] text-slate-700 uppercase tracking-wider block">
              Live Price & Zones
            </span>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showLivePriceLine}
                onChange={(e) => setShowLivePriceLine(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>Live Price Line & Badge</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showSRZones}
                onChange={(e) => setShowSRZones(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>S/R Liquidity Bands</span>
            </label>
          </div>

          {/* W/M Pattern Engine Settings */}
          <div className="space-y-2">
            <span className="font-bold text-[11px] text-slate-700 uppercase tracking-wider block">
              W/M Pattern Engine
            </span>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showActiveWmPattern}
                onChange={(e) => setShowActiveWmPattern(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>Show Active Pattern & Target</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showPatternHistory}
                onChange={(e) => setShowPatternHistory(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>Show Pattern History (Last 3)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={showWmDebug}
                onChange={(e) => setShowWmDebug(e.target.checked)}
                className="rounded border-slate-300 text-blue-600"
              />
              <span>Show W/M Debug Diagnostics</span>
            </label>
          </div>
        </div>
      )}

      {/* W/M Detection Debug Diagnostics HUD */}
      {showWmDebug && (
        <div className="p-3.5 rounded-xl bg-slate-900 text-slate-100 border border-slate-700 shadow-md text-xs font-mono space-y-2">
          <div className="flex items-center justify-between border-b border-slate-700 pb-1.5">
            <div className="flex items-center gap-2 text-amber-400 font-bold">
              <Activity className="h-4 w-4" />
              <span>W/M STRUCTURAL DETECTION DIAGNOSTICS ({activeTimeframe})</span>
            </div>
            <button
              onClick={() => setShowWmDebug(false)}
              className="text-slate-400 hover:text-white cursor-pointer"
            >
              ✕
            </button>
          </div>

          {chartData?.wm_debug_candidates && chartData.wm_debug_candidates.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5 max-h-48 overflow-y-auto pr-1">
              {chartData.wm_debug_candidates.map((cand: any, idx: number) => {
                const isConfirmed = cand.status === 'BREAKOUT_CONFIRMED' || cand.status === 'CONFIRMED';
                return (
                  <div
                    key={idx}
                    className={`p-2.5 rounded-lg border text-[11px] space-y-1 ${
                      isConfirmed
                        ? 'bg-emerald-950/40 border-emerald-500/60 text-emerald-200'
                        : 'bg-slate-800/80 border-slate-700 text-slate-300'
                    }`}
                  >
                    <div className="flex items-center justify-between font-bold">
                      <span className={cand.pattern_type === 'W' ? 'text-purple-400' : 'text-rose-400'}>
                        {cand.pattern_type === 'W' ? 'W Pattern Candidate' : 'M Pattern Candidate'}
                      </span>
                      <span className={`px-1.5 py-0.2 rounded text-[10px] ${
                        isConfirmed ? 'bg-emerald-800 text-white' : 'bg-slate-700 text-slate-300'
                      }`}>
                        {cand.status}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-x-2 text-[10px] text-slate-400">
                      <span>{cand.pattern_type === 'W' ? 'L1' : 'H1'}: {currSym}{cand.s1_price}</span>
                      <span>{cand.pattern_type === 'W' ? 'L2' : 'H2'}: {currSym}{cand.s2_price}</span>
                      <span>Neckline: {currSym}{cand.neckline_price}</span>
                      <span>Separation: {cand.bar_separation} bars</span>
                      <span>Depth: {cand.depth_atr} ATR</span>
                      <span>Symmetry: {cand.symmetry_atr} ATR</span>
                    </div>

                    <div className="flex items-center justify-between pt-1 border-t border-slate-700/60 text-[10px]">
                      <span>Quality Score: <strong className="text-white">{cand.quality_score}/100</strong></span>
                      {cand.rejection_reason && (
                        <span className="text-rose-300 truncate max-w-[140px]" title={cand.rejection_reason}>
                          ✗ {cand.rejection_reason}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-slate-400 py-2 text-center italic">
              No structural W/M candidate formations detected on recent {activeTimeframe} swings.
            </div>
          )}
        </div>
      )}

      {/* Interactive Chart Canvas Area with Drag Panning & Wheel Zoom */}
      <div className="relative w-full h-[330px] sm:h-[370px] md:h-[480px] rounded-xl overflow-hidden bg-white border border-slate-200 min-w-0">
        {isLoading && (
          <div className="absolute inset-0 bg-white/70 backdrop-blur-xs flex items-center justify-center z-10">
            <div className="flex items-center gap-2 text-slate-700 font-semibold text-xs">
              <RefreshCw className="h-4 w-4 animate-spin text-blue-600" />
              <span>Loading {symbol} ({activeTimeframe}) live market data...</span>
            </div>
          </div>
        )}

        {/* Hover Crosshair Tooltip with IST Formatting */}
        {hoverData && (
          <div
            className="absolute z-20 pointer-events-none bg-slate-900/95 text-white rounded-xl p-3 border border-slate-700 shadow-2xl backdrop-blur-md text-[11px] font-mono space-y-1.5 min-w-[190px]"
            style={{
              left: Math.min(Math.max(10, hoverData.x - 95), (canvasRef.current?.clientWidth || 700) - 210),
              top: 15
            }}
          >
            <div className="flex items-center justify-between gap-3 font-bold border-b border-slate-700 pb-1 text-blue-400">
              <span>{formatCandleDate(hoverData.candle.time, symbol)}</span>
              <span className="bg-blue-900/60 px-1.5 py-0.2 rounded border border-blue-600/40 text-[10px]">
                {formatMarketTime(hoverData.candle.time, symbol)}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-2.5 gap-y-0.5 pt-0.5 text-slate-200">
              <span>O: {currSym}{hoverData.candle.open.toFixed(2)}</span>
              <span>H: {currSym}{hoverData.candle.high.toFixed(2)}</span>
              <span>L: {currSym}{hoverData.candle.low.toFixed(2)}</span>
              <span className={hoverData.candle.close >= hoverData.candle.open ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                C: {currSym}{hoverData.candle.close.toFixed(2)}
              </span>
            </div>
            <div className="text-[10px] text-slate-400 pt-1 border-t border-slate-800 flex justify-between">
              <span>Vol: {Number(hoverData.candle.volume).toLocaleString()}</span>
              {hoverData.candle.rsi_14 !== null && hoverData.candle.rsi_14 !== undefined && (
                <span>RSI: {Number(hoverData.candle.rsi_14).toFixed(1)}</span>
              )}
            </div>
          </div>
        )}

        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
          onWheel={handleWheel}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          className="w-full h-full block cursor-grab active:cursor-grabbing touch-none"
        />
      </div>
    </div>
  );
};
export default ChartView;
