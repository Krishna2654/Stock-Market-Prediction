import asyncio
import json
import sys
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

yf.set_tz_cache_location(r"C:\Users\user\Desktop\ai_market_analyzer\backend\.market-data-cache")

from app.core.config import settings
from app.data.yfinance_provider import YahooFinanceProvider
from app.indicators.technical import TechnicalIndicatorEngine
from app.market_structure.precision_breakouts import PrecisionBreakoutDetector
from app.market_structure.support_resistance import SupportResistanceDetector
from app.market_structure.swings import SwingDetector
from app.market_structure.trendlines import TrendlineDetector


CONFIRMED_STATUSES = {
    "BREAKOUT_CONFIRMED",
    "HIGH_CONFLUENCE_CONFIRMED",
    "TARGET_1_HIT",
    "TARGET_2_HIT",
    "INVALIDATED",
}


def replay_outcome(pattern, candles):
    """Mirror the alert engine: first target/stop touch after the breakout wins."""
    target_info = pattern.target_analysis
    target_1 = target_info.measured_target if target_info else pattern.target_1
    target_2 = target_info.target_2 if target_info else pattern.target_2
    stop = target_info.invalidation_level if target_info else pattern.stop_loss
    start = (pattern.breakout_candle_index or -1) + 1

    if start <= 0 or target_1 is None or stop is None:
        return "open", None, False

    for candle in candles[start:]:
        if pattern.pattern_type == "W":
            hit_t2 = target_2 is not None and candle.high >= target_2
            hit_t1 = candle.high >= target_1
            hit_stop = candle.low <= stop
            if hit_t2:
                return "t2", candle.timestamp, False
            if hit_t1 and hit_stop:
                return ("sl" if candle.open < candle.close else "t1"), candle.timestamp, True
            if hit_t1:
                return "t1", candle.timestamp, False
            if hit_stop:
                return "sl", candle.timestamp, False
        else:
            hit_t2 = target_2 is not None and candle.low <= target_2
            hit_t1 = candle.low <= target_1
            hit_stop = candle.high >= stop
            if hit_t2:
                return "t2", candle.timestamp, False
            if hit_t1 and hit_stop:
                return ("sl" if candle.open > candle.close else "t1"), candle.timestamp, True
            if hit_t1:
                return "t1", candle.timestamp, False
            if hit_stop:
                return "sl", candle.timestamp, False

    return "open", None, False


def summarize(rows, field):
    groups = {}
    for row in rows:
        value = row.get(field, "UNKNOWN")
        group = groups.setdefault(value, {"signals": 0, "t1": 0, "t2": 0, "sl": 0, "open": 0})
        group["signals"] += 1
        group[row["outcome"]] += 1

    for group in groups.values():
        group["closed"] = group["t1"] + group["t2"] + group["sl"]
        group["hit_rate_closed_pct"] = (
            round((group["t1"] + group["t2"]) * 100 / group["closed"], 1)
            if group["closed"] else None
        )
        group["sl_rate_closed_pct"] = (
            round(group["sl"] * 100 / group["closed"], 1)
            if group["closed"] else None
        )
    return groups


def analyze(symbol, ticker, timeframe, candles):
    if len(candles) < 30:
        return [], {"symbol": symbol, "timeframe": timeframe, "candles": len(candles), "error": "insufficient"}

    indicator_frame, indicators = TechnicalIndicatorEngine.compute_all_indicators(candles)
    swing_length = 3 if timeframe == "5M" else 5
    swings, _ = SwingDetector.detect_swings(candles, swing_length=swing_length, confirmation_candles=2)
    trendlines = TrendlineDetector.fit_trendlines(
        candles, swings, max_lines_per_direction=settings.MAX_TRENDLINES_PER_DIRECTION
    )
    levels = SupportResistanceDetector.detect_levels(candles, swings, timeframe)
    supports = [level.price for level in levels.all_levels if level.level_type == "SUPPORT"]
    resistances = [level.price for level in levels.all_levels if level.level_type == "RESISTANCE"]
    for level in (levels.minor_support, levels.major_support):
        if level and level not in supports:
            supports.append(level)
    for level in (levels.minor_resistance, levels.major_resistance):
        if level and level not in resistances:
            resistances.append(level)

    atr = indicators.atr_14 or candles[-1].close * 0.005
    _, patterns, _, _ = PrecisionBreakoutDetector.detect_wm_patterns(
        candles=candles,
        swings=swings,
        trendlines=trendlines,
        df_indicators=indicator_frame,
        symbol=symbol,
        timeframe=timeframe,
        atr_val=atr,
        price_tolerance_atr=settings.W_M_SWING_TOLERANCE_ATR,
        min_depth_atr=settings.MIN_PATTERN_DEPTH_ATR,
        min_bar_spacing=settings.MIN_W_M_SWING_SEPARATION,
        min_breakout_dist_atr=settings.MIN_BREAKOUT_DISTANCE_ATR,
        key_supports=supports,
        key_resistances=resistances,
    )

    seen, rows = set(), []
    for pattern in patterns:
        if (
            pattern.status not in CONFIRMED_STATUSES
            or pattern.quality_score < 60
            or pattern.breakout_candle_index is None
        ):
            continue
        signal_key = (pattern.pattern_type, pattern.breakout_candle_index)
        if signal_key in seen:
            continue
        seen.add(signal_key)

        target_info = pattern.target_analysis
        target_1 = target_info.measured_target if target_info else pattern.target_1
        target_2 = target_info.target_2 if target_info else pattern.target_2
        stop = target_info.invalidation_level if target_info else pattern.stop_loss
        outcome, outcome_time, ambiguous = replay_outcome(pattern, candles)

        prior_highs = [swing for swing in swings if swing.is_high and swing.index < pattern.s1_index]
        source_high = prior_highs[-1].price if prior_highs else None
        target_vs_source = "NO_PRIOR_HIGH"
        delta_in_heights = None
        if pattern.pattern_type == "W" and source_high is not None and pattern.pattern_height:
            delta_in_heights = round((target_1 - source_high) / pattern.pattern_height, 3)
            if delta_in_heights > 0.25:
                target_vs_source = "ABOVE_SOURCE_HIGH"
            elif delta_in_heights < -0.25:
                target_vs_source = "BELOW_SOURCE_HIGH"
            else:
                target_vs_source = "NEAR_SOURCE_HIGH"

        rows.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "pattern": pattern.pattern_type,
            "kind": "FAST" if "_FAST_" in pattern.pattern_id else "STRUCTURAL",
            "quality": pattern.quality_score,
            "confluence": (
                "TL+EMA" if pattern.trendline_score > 0 and pattern.ema_score > 0
                else "EMA_ONLY" if pattern.ema_score > 0
                else "TL_ONLY" if pattern.trendline_score > 0
                else "NONE"
            ),
            "entry_status": pattern.entry_status or "UNKNOWN",
            "outcome": outcome,
            "ambiguous": ambiguous,
            "breakout_time": pattern.breakout_candle_time,
            "outcome_time": outcome_time,
            "entry": pattern.breakout_close,
            "neckline": pattern.neckline_price,
            "height": pattern.pattern_height,
            "target_1": target_1,
            "target_2": target_2,
            "stop": stop,
            "source_high": source_high,
            "target_delta_in_heights": delta_in_heights,
            "target_vs_source": target_vs_source,
        })

    return rows, {"symbol": symbol, "timeframe": timeframe, "candles": len(candles), "patterns": len(rows)}


async def main():
    provider = YahooFinanceProvider()
    all_rows, coverage, errors = [], [], []

    for instrument in settings.DEFAULT_INSTRUMENTS:
        symbol, ticker = instrument["symbol"], instrument["ticker"]
        try:
            datasets = {
                "5M": await provider.fetch_candles(symbol, ticker, "5M", limit=10000),
                "15M": await provider.fetch_candles(symbol, ticker, "15M", limit=10000),
            }
            for timeframe, candles in datasets.items():
                rows, metadata = analyze(symbol, ticker, timeframe, candles)
                all_rows.extend(rows)
                coverage.append(metadata)
        except Exception as error:
            errors.append({"symbol": symbol, "error": str(error)})

    closed = [row for row in all_rows if row["outcome"] != "open"]
    w_rows = [row for row in all_rows if row["pattern"] == "W"]
    source_comparison = {
        value: sum(row["target_vs_source"] == value for row in w_rows)
        for value in ("ABOVE_SOURCE_HIGH", "NEAR_SOURCE_HIGH", "BELOW_SOURCE_HIGH", "NO_PRIOR_HIGH")
    }
    source_deltas = [row["target_delta_in_heights"] for row in w_rows if row["target_delta_in_heights"] is not None]

    result = {
        "method": "Retrospective replay of every confirmed app W/M signal. The first subsequent T1/T2 or stop touch is the outcome.",
        "coverage": coverage,
        "errors": errors,
        "summary": {
            "signals": len(all_rows),
            "t1": sum(row["outcome"] == "t1" for row in all_rows),
            "t2": sum(row["outcome"] == "t2" for row in all_rows),
            "target_hits": sum(row["outcome"] in {"t1", "t2"} for row in all_rows),
            "sl": sum(row["outcome"] == "sl" for row in all_rows),
            "open": sum(row["outcome"] == "open" for row in all_rows),
            "closed": len(closed),
            "target_hit_rate_closed_pct": round(
                sum(row["outcome"] in {"t1", "t2"} for row in closed) * 100 / len(closed), 1
            ) if closed else None,
            "ambiguous_same_candle": sum(row["ambiguous"] for row in all_rows),
        },
        "by_pattern": summarize(all_rows, "pattern"),
        "by_timeframe": summarize(all_rows, "timeframe"),
        "by_kind": summarize(all_rows, "kind"),
        "by_confluence": summarize(all_rows, "confluence"),
        "by_entry_status": summarize(all_rows, "entry_status"),
        "w_target_source_comparison": source_comparison,
        "w_mean_target_minus_source_high_in_pattern_heights": round(sum(source_deltas) / len(source_deltas), 3) if source_deltas else None,
        "sl_examples": [row for row in all_rows if row["outcome"] == "sl"][:12],
        "target_examples": [row for row in all_rows if row["outcome"] in {"t1", "t2"}][:12],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
