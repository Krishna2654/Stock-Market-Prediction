import asyncio
import time
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
from app.models.schemas import (
    MultiTimeframeSynthesis,
    SingleTimeframeAnalysis,
    Candle
)
from app.api.deps import get_current_provider, configured_instruments
from app.multi_timeframe.synthesis import MultiTimeframeAnalyzer
from app.alerts.engine import alert_engine
from app.indicators.technical import TechnicalIndicatorEngine
from app.market_structure.swings import SwingDetector
from app.market_structure.bos_choch import BOSCHoCHDetector
from app.market_structure.trendlines import TrendlineDetector
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.market_structure.support_resistance import SupportResistanceDetector
from app.market_structure.predictive_scenarios import PredictiveScenarioEngine
from app.core.config import settings

from app.alerts.high_confluence_engine import high_confluence_alert_engine
from app.alerts.mw_breakout_engine import mw_breakout_engine
from app.alerts.trendline_shortlist_engine import trendline_shortlist_engine
from app.api.websocket import ws_manager

from pathlib import Path
import json
from datetime import datetime, timezone

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# In-memory performance caches with TTL & disk persistence
_CACHE_FILE = Path(__file__).resolve().parents[2] / "data" / "market_synthesis_cache.json"
_synthesis_cache: Dict[str, Tuple[float, MultiTimeframeSynthesis]] = {}
_chart_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_chart_in_flight: Dict[str, asyncio.Task] = {}

def _load_disk_cache():
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for sym, item in data.items():
                    synth = MultiTimeframeSynthesis.model_validate(item["synthesis"])
                    _synthesis_cache[sym] = (item.get("timestamp", time.time()), synth)
            print(f"[Analysis Cache] Restored {len(_synthesis_cache)} cached syntheses from disk.")
        except Exception as e:
            print(f"[Analysis Cache] Disk load error: {e}")

def _save_disk_cache():
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        dump_data = {}
        for sym, (ts, synth) in _synthesis_cache.items():
            dump_data[sym] = {
                "timestamp": ts,
                "synthesis": synth.model_dump()
            }
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(dump_data, f)
    except Exception as e:
        print(f"[Analysis Cache] Disk save error: {e}")

# Pre-load cache from disk on module import for 0ms initial response
_load_disk_cache()

def update_synthesis_cache(symbol: str, synthesis: MultiTimeframeSynthesis):
    _synthesis_cache[symbol] = (time.time(), synthesis)
    _save_disk_cache()

@router.get("/fast-overview")
async def get_fast_overview():
    """
    Ultra-low latency endpoint (<10ms) returning current prices, bias, and status
    for all active instruments. Never blocks on deep 40-timeframe analysis.
    """
    summary = []
    for inst in configured_instruments:
        if not inst.is_active:
            continue
        cached = _synthesis_cache.get(inst.symbol)
        if cached:
            synth = cached[1]
            summary.append({
                "symbol": inst.symbol,
                "ticker": inst.ticker,
                "exchange": inst.exchange,
                "asset_type": inst.asset_type,
                "current_price": synth.current_price,
                "overall_bias": synth.overall_bias,
                "evidence_score": synth.evidence_score.total_score,
                "data_status": synth.data_status,
                "market_session": synth.market_session.model_dump() if synth.market_session else None,
                "last_updated": synth.last_updated
            })
        else:
            summary.append({
                "symbol": inst.symbol,
                "ticker": inst.ticker,
                "exchange": inst.exchange,
                "asset_type": inst.asset_type,
                "current_price": 0.0,
                "overall_bias": "NEUTRAL",
                "evidence_score": 50,
                "data_status": "LIVE",
                "market_session": None,
                "last_updated": datetime.now(timezone.utc).isoformat()
            })
    return summary

async def _analyze_instrument_cached(symbol: str, ticker: str, provider) -> MultiTimeframeSynthesis:
    now = time.time()
    if symbol in _synthesis_cache:
        cached_time, cached_synth = _synthesis_cache[symbol]
        if (now - cached_time) < 120.0:  # Fresh for 120s
            return cached_synth

    # Fetch fresh with fallback to cached
    try:
        synth = await _analyze_instrument(symbol, ticker, provider)
        _synthesis_cache[symbol] = (now, synth)
        return synth
    except Exception as e:
        if symbol in _synthesis_cache:
            return _synthesis_cache[symbol][1]
        raise e

@router.get("/overview", response_model=List[MultiTimeframeSynthesis])
async def get_all_instruments_overview():
    provider = get_current_provider()
    tasks = []
    
    for inst in configured_instruments:
        if inst.is_active:
            tasks.append(
                _analyze_instrument_cached(inst.symbol, inst.ticker, provider)
            )
            
    results = await asyncio.gather(*tasks, return_exceptions=True)
    valid_syntheses: List[MultiTimeframeSynthesis] = []
    
    for res in results:
        if isinstance(res, MultiTimeframeSynthesis):
            valid_syntheses.append(res)
            try:
                new_alerts = alert_engine.process_synthesis_for_alerts(res)
                for alert in new_alerts:
                    asyncio.create_task(ws_manager.broadcast({
                        "type": "ALERT_TRIGGERED",
                        "alert": alert.model_dump()
                    }))
            except Exception as e:
                pass
            try:
                high_confluence_alert_engine.process_synthesis_for_high_confluence_alerts(res)
            except Exception as e:
                pass
            try:
                new_mw, updated_mw = mw_breakout_engine.process_synthesis_with_updates(res)
                for mwa in new_mw:
                    asyncio.create_task(ws_manager.broadcast({
                        "type": "MW_BREAKOUT_TRIGGERED",
                        "alert": mwa.model_dump()
                    }))
                for mwa in updated_mw:
                    asyncio.create_task(ws_manager.broadcast({
                        "type": "MW_BREAKOUT_STATUS_UPDATED",
                        "alert": mwa.model_dump()
                    }))
            except Exception as e:
                pass
            try:
                new_shortlist = trendline_shortlist_engine.process_synthesis(res)
                for cand in new_shortlist:
                    asyncio.create_task(ws_manager.broadcast({
                        "type": "TRENDLINE_SHORTLIST_UPDATED",
                        "candidate": cand.model_dump()
                    }))
            except Exception as e:
                pass
        elif isinstance(res, Exception):
            print(f"[Overview Error] {res}")
            
    return valid_syntheses

async def _analyze_instrument(symbol: str, ticker: str, provider) -> MultiTimeframeSynthesis:
    mtf_candles = await provider.get_multi_timeframe_data(symbol, ticker, ["4H", "1H", "15M", "5M"], limit=200)
    
    has_data = any(len(c) > 0 for c in mtf_candles.values())
    is_stale = False
    status_msg = f"Live Market Data from {provider.provider_name}" if has_data else f"No data received from {provider.provider_name}"
    data_status = getattr(provider, "get_connection_status", lambda t: "LIVE")(ticker)
    
    synthesis = MultiTimeframeAnalyzer.synthesize(
        symbol=symbol,
        ticker=ticker,
        provider_name=provider.provider_name,
        mtf_candles=mtf_candles,
        is_stale=is_stale,
        status_message=status_msg,
        data_status=data_status
    )
    return synthesis

@router.get("/detail/{symbol:path}", response_model=MultiTimeframeSynthesis)
async def get_instrument_detail(symbol: str):
    provider = get_current_provider()
    target = next((i for i in configured_instruments if i.symbol.upper() == symbol.upper()), None)
    ticker = target.ticker if target else symbol
    
    synthesis = await _analyze_instrument_cached(symbol, ticker, provider)
    try:
        new_alerts = alert_engine.process_synthesis_for_alerts(synthesis)
        for alert in new_alerts:
            asyncio.create_task(ws_manager.broadcast({
                "type": "ALERT_TRIGGERED",
                "alert": alert.model_dump()
            }))
    except Exception:
        pass
    try:
        high_confluence_alert_engine.process_synthesis_for_high_confluence_alerts(synthesis)
    except Exception:
        pass
    try:
        new_mw, updated_mw = mw_breakout_engine.process_synthesis_with_updates(synthesis)
        for mwa in new_mw:
            asyncio.create_task(ws_manager.broadcast({
                "type": "MW_BREAKOUT_TRIGGERED",
                "alert": mwa.model_dump()
            }))
        for mwa in updated_mw:
            asyncio.create_task(ws_manager.broadcast({
                "type": "MW_BREAKOUT_STATUS_UPDATED",
                "alert": mwa.model_dump()
            }))
    except Exception:
        pass
    try:
        new_shortlist = trendline_shortlist_engine.process_synthesis(synthesis)
        for cand in new_shortlist:
            asyncio.create_task(ws_manager.broadcast({
                "type": "TRENDLINE_SHORTLIST_UPDATED",
                "candidate": cand.model_dump()
            }))
    except Exception:
        pass
    return synthesis

@router.get("/chart/{symbol:path}")
async def get_chart_data(
    symbol: str,
    timeframe: str = Query("15M", pattern="^(4H|1H|15M|5M)$"),
    limit: int = Query(250, ge=30, le=500)
):
    cache_key = f"{symbol}_{timeframe}_{limit}"
    now = time.time()
    if cache_key in _chart_cache:
        c_time, c_data = _chart_cache[cache_key]
        if (now - c_time) < 30.0:  # Fresh for 30s -> Instant return!
            return c_data

    if cache_key in _chart_in_flight:
        try:
            return await _chart_in_flight[cache_key]
        except Exception:
            pass

    async def _compute_chart():
        try:
            provider = get_current_provider()
            target = next((i for i in configured_instruments if i.symbol.upper() == symbol.upper()), None)
            ticker = target.ticker if target else symbol

            candles = await provider.fetch_candles(symbol, ticker, timeframe, limit=limit)
            if not candles:
                raise HTTPException(status_code=404, detail=f"No candle data available for {symbol} on {timeframe}")

            df_indicators, _ = TechnicalIndicatorEngine.compute_all_indicators(candles)
            tf_clean = (timeframe or "15M").upper()
            eff_swing_length = 3 if tf_clean in ["5M", "1M", "3M"] else 5
            swings, protected_swing = SwingDetector.detect_swings(candles, swing_length=eff_swing_length, confirmation_candles=2)
            breaks = BOSCHoCHDetector.detect_structure_breaks(
                candles=candles,
                swings=swings,
                symbol=symbol,
                timeframe=timeframe,
                df_indicators=df_indicators
            )
            trendlines = TrendlineDetector.fit_trendlines(candles, swings, max_lines_per_direction=settings.MAX_TRENDLINES_PER_DIRECTION)
            atr_val = float(df_indicators["atr_14"].iloc[-1]) if "atr_14" in df_indicators and not pd.isna(df_indicators["atr_14"].iloc[-1]) else (candles[-1].close * 0.005)
            
            # Standard trendline breaks
            tl_breaks = TrendlineDetector.detect_trendline_breaks(candles, trendlines, symbol, timeframe, atr_val=atr_val)
            for tb in tl_breaks:
                breaks.append(tb)

            # Precision Breakouts (Notification 1 & 2)
            tl_ema_vol_breaks = PrecisionBreakoutDetector.detect_trendline_ema_volume_breakouts(
                candles=candles, trendlines=trendlines, df_indicators=df_indicators,
                symbol=symbol, timeframe=timeframe, atr_val=atr_val,
                good_volume_threshold=settings.GOOD_VOLUME_THRESHOLD
            )
            for pb in tl_ema_vol_breaks:
                breaks.append(pb)

            sr_summary = SupportResistanceDetector.detect_levels(candles, swings, timeframe)
            key_sups = [lvl.price for lvl in sr_summary.all_levels if lvl.level_type == "SUPPORT"]
            key_res = [lvl.price for lvl in sr_summary.all_levels if lvl.level_type == "RESISTANCE"]

            wm_breaks, confirmed_wm_patterns, active_wm_pattern, debug_wm_candidates = PrecisionBreakoutDetector.detect_wm_patterns(
                candles=candles, swings=swings, trendlines=trendlines, df_indicators=df_indicators,
                symbol=symbol, timeframe=timeframe, atr_val=atr_val,
                price_tolerance_atr=settings.W_M_SWING_TOLERANCE_ATR,
                min_depth_atr=settings.MIN_PATTERN_DEPTH_ATR,
                min_bar_spacing=settings.MIN_W_M_SWING_SEPARATION,
                key_supports=key_sups,
                key_resistances=key_res
            )
            for wb in wm_breaks:
                breaks.append(wb)

            # Single Source of Truth: Synchronize canonical chart patterns with mw_breakout_engine
            canonical_active_alert = mw_breakout_engine.sync_chart_patterns(
                symbol=symbol,
                timeframe=timeframe,
                confirmed_patterns=confirmed_wm_patterns,
                active_pattern=active_wm_pattern,
                candles=candles,
                ticker=ticker
            )

            predictive_scenarios = PredictiveScenarioEngine.compute_scenarios(
                candles=candles,
                swings=swings,
                sr_summary=sr_summary,
                recent_events=breaks,
                timeframe=timeframe,
                symbol=symbol
            )

            chart_candles = []
            for i, c in enumerate(candles):
                row = df_indicators.iloc[i] if i < len(df_indicators) else None
                item = {
                    "time": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "rsi_14": float(row["rsi_14"]) if row is not None and "rsi_14" in row and not pd.isna(row["rsi_14"]) else None,
                    "ema_20": float(row["ema_20"]) if row is not None and "ema_20" in row and not pd.isna(row["ema_20"]) else None,
                    "ema_50": float(row["ema_50"]) if row is not None and "ema_50" in row and not pd.isna(row["ema_50"]) else None,
                    "ema_200": float(row["ema_200"]) if row is not None and "ema_200" in row and not pd.isna(row["ema_200"]) else None,
                    "atr_14": float(row["atr_14"]) if row is not None and "atr_14" in row and not pd.isna(row["atr_14"]) else None
                }
                chart_candles.append(item)

            resp_data = {
                "symbol": symbol,
                "timeframe": timeframe,
                "candles": chart_candles,
                "swings": [s.model_dump() for s in swings],
                "protected_swing": protected_swing.model_dump() if protected_swing else None,
                "structure_breaks": [b.model_dump() for b in breaks],
                "breaks": [b.model_dump() for b in breaks],
                "trendlines": trendlines,
                "support_resistance": sr_summary.model_dump(),
                "predictive_scenarios": predictive_scenarios,
                "wm_patterns": [p.model_dump() for p in confirmed_wm_patterns],
                "active_wm_pattern": active_wm_pattern.model_dump() if active_wm_pattern else None,
                "active_wm_alert": canonical_active_alert.model_dump() if canonical_active_alert else None,
                "wm_debug_candidates": [c.model_dump() for c in debug_wm_candidates]
            }

            _chart_cache[cache_key] = (time.time(), resp_data)
            return resp_data
        finally:
            _chart_in_flight.pop(cache_key, None)

    task = asyncio.create_task(_compute_chart())
    _chart_in_flight[cache_key] = task
    return await task
