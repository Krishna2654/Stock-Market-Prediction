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

import logging
from pathlib import Path
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# In-memory performance caches with TTL & disk persistence
_CACHE_FILE = Path(__file__).resolve().parents[2] / "data" / "market_synthesis_cache.json"
_synthesis_cache: Dict[str, Tuple[float, MultiTimeframeSynthesis]] = {}
_chart_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_chart_in_flight: Dict[str, asyncio.Task] = {}
_refresh_tasks: Dict[str, asyncio.Task] = {}

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

def _create_lightweight_synthesis(symbol: str, ticker: str, provider_name: str) -> MultiTimeframeSynthesis:
    """
    Constructs an immediate baseline synthesis in 0ms when no cache exists at all,
    ensuring HTTP responses never block waiting for network providers.
    """
    return MultiTimeframeAnalyzer.synthesize(
        symbol=symbol,
        ticker=ticker,
        provider_name=provider_name,
        mtf_candles={},
        is_stale=True,
        status_message="Initializing Live Market Analysis",
        data_status="LIVE"
    )

def _schedule_background_refresh(symbol: str, ticker: str, provider):
    """
    Schedules an asynchronous background refresh for an instrument's synthesis.
    Deduplicates tasks so that only one background refresh runs per symbol.
    """
    existing_task = _refresh_tasks.get(symbol)
    if existing_task and not existing_task.done():
        return existing_task

    async def _do_refresh():
        try:
            synth = await _analyze_instrument(symbol, ticker, provider)
            update_synthesis_cache(symbol, synth)

            # Broadcast WebSocket updates and evaluate alerts
            try:
                alert_engine.process_synthesis_for_alerts(synth)
            except Exception:
                pass
            try:
                high_confluence_alert_engine.process_synthesis_for_high_confluence_alerts(synth)
            except Exception:
                pass
            try:
                mw_breakout_engine.process_synthesis_with_updates(synth)
            except Exception:
                pass
            try:
                trendline_shortlist_engine.process_synthesis(synth)
            except Exception:
                pass

            asyncio.create_task(ws_manager.broadcast({
                "type": "SYNTHESIS_UPDATE",
                "symbol": symbol,
                "data": synth.model_dump()
            }))
        except Exception as e:
            logger.warning(f"[RoutesAnalysis] Background refresh error for {symbol}: {e}")
        finally:
            _refresh_tasks.pop(symbol, None)

    task = asyncio.create_task(_do_refresh())
    _refresh_tasks[symbol] = task
    return task

async def _analyze_instrument_cached(symbol: str, ticker: str, provider) -> MultiTimeframeSynthesis:
    now = time.time()
    if symbol in _synthesis_cache:
        cached_time, cached_synth = _synthesis_cache[symbol]
        if (now - cached_time) >= 120.0:
            # Stale-while-revalidate: schedule refresh in background, return cached data immediately
            _schedule_background_refresh(symbol, ticker, provider)
        return cached_synth

    # Cache miss: construct lightweight placeholder immediately (<1ms) and schedule deep analysis
    synth = _create_lightweight_synthesis(symbol, ticker, provider.provider_name)
    _synthesis_cache[symbol] = (now, synth)
    _schedule_background_refresh(symbol, ticker, provider)
    return synth

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

from app.analysis.chart_cache import worker_chart_cache, build_chart_payload

# Alias for backward compatibility
compute_chart_payload = build_chart_payload

def update_chart_cache(symbol: str, timeframe: str, data: Dict[str, Any], limit: int = 250):
    """Primes or updates in-memory chart cache for instant 0ms responses."""
    cache_key = f"{symbol}_{timeframe}_{limit}"
    _chart_cache[cache_key] = (time.time(), data)
    worker_chart_cache.set(symbol, timeframe, data)

@router.get("/chart/{symbol:path}")
async def get_chart_data(
    symbol: str,
    timeframe: str = Query("15M", pattern="^(4H|1H|15M|5M)$"),
    limit: int = Query(250, ge=30, le=500)
):
    # 1. Ultra-fast path: Return worker precomputed buffer (<1ms)
    worker_data = worker_chart_cache.get(symbol, timeframe)
    if worker_data is not None:
        return worker_data

    cache_key = f"{symbol}_{timeframe}_{limit}"
    now = time.time()
    # Generous 60s TTL matching candle interval - returns precomputed data in <50ms!
    if cache_key in _chart_cache:
        c_time, c_data = _chart_cache[cache_key]
        if (now - c_time) < 60.0:
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

            # Request via live priority semaphore (never blocked by background catch-up)
            try:
                candles = await provider.fetch_candles(symbol, ticker, timeframe, limit=limit, is_catchup=False)
            except TypeError as te:
                if "is_catchup" in str(te):
                    candles = await provider.fetch_candles(symbol, ticker, timeframe, limit=limit)
                else:
                    raise
            if not candles:
                raise HTTPException(status_code=404, detail=f"No candle data available for {symbol} on {timeframe}")

            resp_data = build_chart_payload(symbol, ticker, timeframe, candles)
            latest_ts = candles[-1].timestamp if candles else None
            worker_chart_cache.set(symbol, timeframe, resp_data, latest_candle_timestamp=latest_ts, is_worker_producer=False)
            _chart_cache[cache_key] = (time.time(), resp_data)
            return resp_data
        finally:
            _chart_in_flight.pop(cache_key, None)

    task = asyncio.create_task(_compute_chart())
    _chart_in_flight[cache_key] = task
    return await task
