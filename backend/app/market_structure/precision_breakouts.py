from typing import List, Optional, Tuple, Dict, Any, Set
import pandas as pd
from app.models.schemas import Candle, SwingPoint, StructureBreakEvent, PatternTargetAnalysis, WMPatternStructure
from app.market_structure.trendlines import Trendline
from app.core.config import settings

class PrecisionBreakoutDetector:
    """
    Structural Swing-Pattern Engine for W/M Detection, Clean Visualization & Confluence Breakouts.
    
    Principles:
    1. STRICT STRUCTURAL SWINGS:
       - M Pattern: Confirmed Swing High (H1) -> Confirmed Reaction Low (Neckline) -> Confirmed Swing High (H2).
       - W Pattern: Confirmed Swing Low (L1) -> Confirmed Reaction High (Neckline) -> Confirmed Swing Low (L2).
    2. REAL-WORLD ATR-NORMALIZED TOLERANCE (Not rigid equality):
       - Evaluates H1 vs H2 (or L1 vs L2) against ATR. Allows natural market noise (up to 1.50 ATR).
    3. OBJECTIVE MEASURED TARGETS & OBSTACLES:
       - Height = Pattern Extent - Neckline.
       - Measured Target = Neckline ± Height.
    4. SINGLE ACTIVE PATTERN DISPLAY:
       - Identifies the latest active/confirmed pattern to keep the chart clean and uncluttered.
    5. SINGLE BREAKOUT PER PATTERN:
       - Confirmed on first completed candle close beyond Neckline + Trendline + 20 EMA.
    6. DEBUG & DIAGNOSTICS:
       - Retains candidate evaluation status, metrics, and rejection reasons for full transparency.
    """

    @classmethod
    def calculate_wm_quality_score(
        cls,
        pattern_type: str,
        s1: Optional[SwingPoint] = None,
        neckline_swing: Optional[SwingPoint] = None,
        s2: Optional[SwingPoint] = None,
        neckline_price: Optional[float] = None,
        breakout_candle: Optional[Candle] = None,
        tl: Optional[Trendline] = None,
        ema_20: Optional[float] = None,
        atr_val: float = 1.0,
        rel_vol: float = 1.0,
        tl_broken: Optional[bool] = None,
        ema_broken: Optional[bool] = None,
        has_reversal: bool = True,
        breakout_candle_index: Optional[int] = None
    ) -> Tuple[int, Dict[str, int]]:
        """
        Calculates dedicated W/M Pattern Quality Score (0 to 100 points maximum).
        
        Strict Standardized Rubric (Max 100/100):
        - Structural reversal condition: 40 points (confirmed W/M structural reversal geometry & context)
        - Trendline breakout condition: 30 points (breakout close confirms trendline break)
        - EMA breakout condition: 30 points (breakout close confirms 20 EMA break)
        
        CRITICAL GATE:
        If has_reversal is False, total score is STRICTLY 0 (no trendline or EMA points can be awarded).
        Missing indicators or missing trendlines NEVER award points.
        """
        if not has_reversal:
            return 0, {"reversal": 0, "trendline": 0, "ema": 0}

        reversal_pts = 40

        # Trendline breakout (30 pts)
        if tl_broken is not None:
            tl_pts = 30 if tl_broken else 0
        elif tl is not None and breakout_candle is not None:
            tl_p1_idx = getattr(tl, "p1_index", 0)
            tl_p1_price = getattr(tl, "p1_price", 0.0)
            tl_slope = getattr(tl, "slope", 0.0)
            bc_idx = breakout_candle_index if breakout_candle_index is not None else getattr(breakout_candle, "index", getattr(tl, "end_index", tl_p1_idx))
            tl_price = tl_p1_price + tl_slope * max(0, bc_idx - tl_p1_idx)
            tl_tolerance = max(tl_price * 0.0003, atr_val * 0.05)
            if pattern_type == "W" and breakout_candle.close > (tl_price + tl_tolerance):
                tl_pts = 30
            elif pattern_type == "M" and breakout_candle.close < (tl_price - tl_tolerance):
                tl_pts = 30
            else:
                tl_pts = 0
        else:
            tl_pts = 0

        # EMA breakout (30 pts)
        if ema_broken is not None:
            ema_pts = 30 if ema_broken else 0
        elif ema_20 is not None and breakout_candle is not None:
            if pattern_type == "W" and breakout_candle.close > ema_20:
                ema_pts = 30
            elif pattern_type == "M" and breakout_candle.close < ema_20:
                ema_pts = 30
            else:
                ema_pts = 0
        else:
            ema_pts = 0

        total = reversal_pts + tl_pts + ema_pts
        breakdown = {
            "reversal": reversal_pts,
            "trendline": tl_pts,
            "ema": ema_pts
        }
        return min(100, total), breakdown

    @classmethod
    def calculate_pattern_targets(
        cls,
        pattern_type: str,
        s1_price: float,
        s2_price: float,
        neckline_price: float,
        breakout_close: float,
        prev_swing_sl: Optional[float] = None,
        key_supports: List[float] = [],
        key_resistances: List[float] = [],
        quality_score: int = 85,
        quality_breakdown: Dict[str, int] = {},
        atr_val: float = 1.0,
        sl_atr_buffer: Optional[float] = None,
        target_extension: Optional[float] = None,
        reversal_target: Optional[float] = None
    ) -> PatternTargetAnalysis:
        """
        Calculates technical targets, intermediate obstacles, and invalidation levels.
        For genuine W/M reversals:
        - Target 1 represents the price level where the preceding trend started (reversal_target).
        - W: reversal_target must be strictly above the neckline.
        - M: reversal_target must be strictly below the neckline.
        - If reversal_target is missing or invalid, safely falls back to standard measured move.
        Stop Loss is strictly independent of the neckline (behind Point 2 / second swing with ATR buffer).
        W: SL = Low 2 - ATR_buffer (strictly < neckline)
        M: SL = High 2 + ATR_buffer (strictly > neckline)
        """
        buffer_atr = sl_atr_buffer if sl_atr_buffer is not None else getattr(settings, "W_M_SL_ATR_BUFFER", 0.15)
        extension = target_extension if target_extension is not None else getattr(settings, "W_M_TARGET_2_EXTENSION", 1.618)

        if pattern_type == "W":
            pattern_low = min(s1_price, s2_price)
            w_height = round(neckline_price - pattern_low, 2)

            # Target 1: Preceding bearish trend-origin swing high (Structural Reversal Target)
            # Safe compatibility fallback: Neckline + Pattern Height
            if reversal_target is not None and reversal_target > neckline_price:
                measured_target = round(reversal_target, 2)
            else:
                measured_target = round(neckline_price + w_height, 2)

            # Stop Loss / Invalidation Close:
            # Low 2 - ATR buffer (never neckline)
            if prev_swing_sl is not None:
                sl_val = prev_swing_sl
            else:
                sl_val = s2_price - (buffer_atr * atr_val)

            # Ensure SL is strictly below neckline and below Low 2
            if sl_val >= neckline_price or sl_val >= s2_price:
                sl_val = min(s2_price, pattern_low) - max(0.01, buffer_atr * atr_val)

            invalidation_level = round(sl_val, 2)
            if invalidation_level >= s2_price:
                invalidation_level = round(s2_price - max(0.01, buffer_atr * atr_val), 2)
            if invalidation_level >= neckline_price:
                invalidation_level = round(min(invalidation_level, neckline_price - 0.01), 2)

            retest_level = round(neckline_price, 2)

            intervening = [r for r in key_resistances if neckline_price < r < (measured_target - 0.05)]
            nearest_obstacle = min(intervening) if intervening else None

            # Target 2 strictly uses measured move: Neckline + Height * extension (no S/R override)
            target_2 = round(neckline_price + extension * w_height, 2)

            target_zone = f"₹{nearest_obstacle:.2f}–₹{measured_target:.2f}" if nearest_obstacle else f"₹{measured_target:.2f}"

            interp = (
                f"Confirmed W-pattern breakout with trendline and 20 EMA confluence. "
                f"Structural Reversal Target 1 is ₹{measured_target:,.2f}, Target 2 is ₹{target_2:,.2f}"
                + (f", subject to intervening resistance at ₹{nearest_obstacle:,.2f}." if nearest_obstacle else ".")
            )

            entry_p = breakout_close if breakout_close is not None else neckline_price
            t1_dist = abs(measured_target - entry_p)
            sl_dist = abs(entry_p - invalidation_level)
            rr_ratio = round(t1_dist / max(0.0001, sl_dist), 2)

            return PatternTargetAnalysis(
                pattern_height=w_height,
                measured_target=measured_target,
                nearest_obstacle=nearest_obstacle,
                target_2=target_2,
                target_zone=target_zone,
                invalidation_level=invalidation_level,
                retest_level=retest_level,
                retest_status="PENDING_RETEST",
                pattern_status="CONFIRMED_BREAKOUT",
                pattern_quality_score=quality_score,
                quality_breakdown=quality_breakdown,
                risk_reward_ratio=rr_ratio,
                interpretation=interp
            )

        else:  # M Pattern
            pattern_high = max(s1_price, s2_price)
            m_height = round(pattern_high - neckline_price, 2)

            # Target 1: Preceding bullish trend-origin swing low (Structural Reversal Target)
            # Safe compatibility fallback: Neckline - Pattern Height
            if reversal_target is not None and reversal_target < neckline_price:
                measured_target = round(reversal_target, 2)
            else:
                measured_target = round(neckline_price - m_height, 2)

            # Stop Loss / Invalidation Close:
            # High 2 + ATR buffer (never neckline)
            if prev_swing_sl is not None:
                sl_val = prev_swing_sl
            else:
                sl_val = s2_price + (buffer_atr * atr_val)

            # Ensure SL is strictly above neckline and above High 2
            if sl_val <= neckline_price or sl_val <= s2_price:
                sl_val = max(s2_price, pattern_high) + max(0.01, buffer_atr * atr_val)

            invalidation_level = round(sl_val, 2)
            if invalidation_level <= s2_price:
                invalidation_level = round(s2_price + max(0.01, buffer_atr * atr_val), 2)
            if invalidation_level <= neckline_price:
                invalidation_level = round(max(invalidation_level, neckline_price + 0.01), 2)

            retest_level = round(neckline_price, 2)

            intervening = [s for s in key_supports if (measured_target + 0.05) < s < neckline_price]
            nearest_obstacle = max(intervening) if intervening else None

            # Target 2 strictly uses measured move: Neckline - Height * extension (no S/R override)
            target_2 = round(neckline_price - extension * m_height, 2)

            target_zone = f"₹{measured_target:.2f}–₹{nearest_obstacle:.2f}" if nearest_obstacle else f"₹{measured_target:.2f}"

            interp = (
                f"Confirmed M-pattern breakdown with trendline and 20 EMA confluence. "
                f"Structural Reversal Target 1 is ₹{measured_target:,.2f}, Target 2 is ₹{target_2:,.2f}"
                + (f" and may encounter support before reaching it at ₹{nearest_obstacle:,.2f}." if nearest_obstacle else ".")
            )

            entry_p = breakout_close if breakout_close is not None else neckline_price
            t1_dist = abs(measured_target - entry_p)
            sl_dist = abs(entry_p - invalidation_level)
            rr_ratio = round(t1_dist / max(0.0001, sl_dist), 2)

            return PatternTargetAnalysis(
                pattern_height=m_height,
                measured_target=measured_target,
                nearest_obstacle=nearest_obstacle,
                target_2=target_2,
                target_zone=target_zone,
                invalidation_level=invalidation_level,
                retest_level=retest_level,
                retest_status="PENDING_RETEST",
                pattern_status="CONFIRMED_BREAKOUT",
                pattern_quality_score=quality_score,
                quality_breakdown=quality_breakdown,
                risk_reward_ratio=rr_ratio,
                interpretation=interp
            )

    @classmethod
    def detect_trendline_ema_volume_breakouts(
        cls,
        candles: List[Candle],
        trendlines: List[Trendline],
        df_indicators: Optional[pd.DataFrame],
        symbol: str,
        timeframe: str,
        atr_val: float,
        good_volume_threshold: float = settings.GOOD_VOLUME_THRESHOLD
    ) -> List[StructureBreakEvent]:
        if len(candles) < 10 or not trendlines:
            return []

        events: List[StructureBreakEvent] = []
        n = len(candles)
        broken_trendline_ids: Set[str] = set()

        for i in range(1, n):
            c = candles[i]
            prev_c = candles[i - 1]

            ema_20: Optional[float] = None
            rel_vol: float = 1.0

            if df_indicators is not None and i < len(df_indicators):
                row = df_indicators.iloc[i]
                if "ema_20" in row and not pd.isna(row["ema_20"]):
                    ema_20 = float(row["ema_20"])
                if "relative_volume" in row and not pd.isna(row["relative_volume"]):
                    rel_vol = float(row["relative_volume"])
                elif "volume_sma_20" in row and not pd.isna(row["volume_sma_20"]) and row["volume_sma_20"] > 0:
                    rel_vol = float(c.volume) / float(row["volume_sma_20"])
            else:
                start_v = max(0, i - 20)
                subset = candles[start_v:i]
                if subset:
                    avg_v = sum(k.volume for k in subset) / len(subset)
                    if avg_v > 0:
                        rel_vol = c.volume / avg_v

            # Strict volume requirement
            if rel_vol < good_volume_threshold:
                continue

            if ema_20 is None:
                continue

            for tl in trendlines:
                tl_id = f"{tl.line_type}_{tl.p1_index}_{tl.p2_index}"
                if tl_id in broken_trendline_ids:
                    continue

                if tl.rank == "MINOR" or tl.strength == "MINOR":
                    continue

                if tl.touch_points:
                    prior_tps = [tp for tp in tl.touch_points if tp.index < i]
                    if len(prior_tps) < 2:
                        continue
                elif i <= tl.p2_index:
                    continue

                line_price = tl.p1_price + tl.slope * (i - tl.p1_index)
                prev_line_price = tl.p1_price + tl.slope * (i - 1 - tl.p1_index)
                tolerance = max(line_price * 0.0003, atr_val * 0.05)

                # UP BREAKOUT
                if tl.line_type == "DESCENDING_RESISTANCE":
                    is_tl_broken = c.close > (line_price + tolerance)
                    is_ema_broken = c.close > ema_20

                    if is_tl_broken and is_ema_broken:
                        is_fresh = (prev_c.close <= (prev_line_price + tolerance)) or (prev_c.close <= ema_20)
                        if is_fresh:
                            broken_trendline_ids.add(tl_id)
                            event_id = f"{symbol}_{timeframe}_TL_EMA_VOL_UP_{c.timestamp}_{round(line_price, 1)}"
                            events.append(StructureBreakEvent(
                                id=event_id,
                                symbol=symbol,
                                timeframe=timeframe,
                                timestamp=c.timestamp,
                                event_type="TRENDLINE_EMA_VOLUME_UP_BREAKOUT",
                                direction="BULLISH",
                                broken_level=round(line_price, 2),
                                break_price=round(c.close, 2),
                                break_candle_index=i,
                                volume_confirmed=True,
                                atr_at_break=round(atr_val, 2),
                                htf_alignment="BULLISH",
                                evidence_score=85,
                                breakout_candle_open=round(c.open, 2),
                                breakout_candle_high=round(c.high, 2),
                                breakout_candle_low=round(c.low, 2),
                                breakout_candle_close=round(c.close, 2),
                                trendline_level=round(line_price, 2),
                                ema20_level=round(ema_20, 2),
                                volume_ratio=round(rel_vol, 2),
                                notes=f"🟢 TRENDLINE + 20 EMA + VOLUME — UP BREAKOUT: Close {c.close:.2f} > TL {line_price:.2f} & EMA {ema_20:.2f} (Vol: {rel_vol:.2f}x)"
                            ))

                # DOWN BREAKOUT
                elif tl.line_type == "ASCENDING_SUPPORT":
                    is_tl_broken = c.close < (line_price - tolerance)
                    is_ema_broken = c.close < ema_20

                    if is_tl_broken and is_ema_broken:
                        is_fresh = (prev_c.close >= (prev_line_price - tolerance)) or (prev_c.close >= ema_20)
                        if is_fresh:
                            broken_trendline_ids.add(tl_id)
                            event_id = f"{symbol}_{timeframe}_TL_EMA_VOL_DOWN_{c.timestamp}_{round(line_price, 1)}"
                            events.append(StructureBreakEvent(
                                id=event_id,
                                symbol=symbol,
                                timeframe=timeframe,
                                timestamp=c.timestamp,
                                event_type="TRENDLINE_EMA_VOLUME_DOWN_BREAKOUT",
                                direction="BEARISH",
                                broken_level=round(line_price, 2),
                                break_price=round(c.close, 2),
                                break_candle_index=i,
                                volume_confirmed=True,
                                atr_at_break=round(atr_val, 2),
                                htf_alignment="BEARISH",
                                evidence_score=85,
                                breakout_candle_open=round(c.open, 2),
                                breakout_candle_high=round(c.high, 2),
                                breakout_candle_low=round(c.low, 2),
                                breakout_candle_close=round(c.close, 2),
                                trendline_level=round(line_price, 2),
                                ema20_level=round(ema_20, 2),
                                volume_ratio=round(rel_vol, 2),
                                notes=f"🔴 TRENDLINE + 20 EMA + VOLUME — DOWN BREAKOUT: Close {c.close:.2f} < TL {line_price:.2f} & EMA {ema_20:.2f} (Vol: {rel_vol:.2f}x)"
                            ))

        return events

    @classmethod
    def classify_preceding_market_regime(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        point_1: SwingPoint,
        atr_val: float,
        timeframe: Optional[str] = None,
        df_indicators: Optional[pd.DataFrame] = None
    ) -> Tuple[str, str]:
        """
        Classifies the market regime strictly preceding Point 1 into:
        - "BEARISH": Confirmed bearish structural sequence (LH/LL progression or downward impulse).
        - "BULLISH": Confirmed bullish structural sequence (HH/HL progression or upward impulse).
        - "SIDEWAYS": Range-bound, oscillating, or tight consolidation without direction.
        - "UNCLEAR": Conflicting swings or insufficient structural data to establish a regime.
        """
        tf_clean = (timeframe or "1H").upper()
        tf_multipliers = {
            "1M": 0.0010,
            "3M": 0.0012,
            "5M": 0.0015,  # 0.15% minimum displacement floor for 5M intraday
            "15M": 0.003,  # 0.30% minimum displacement floor for 15M
            "30M": 0.0045, # 0.45% minimum displacement floor for 30M
            "1H": 0.006,   # 0.60% minimum displacement floor for 1H
            "2H": 0.008,
            "4H": 0.010,   # 1.00% minimum displacement floor for 4H/Daily
            "1D": 0.015
        }
        pct = tf_multipliers.get(tf_clean, 0.006)
        min_disp = max(0.80 * atr_val, point_1.price * pct)

        all_prior_swings = [s for s in swings if getattr(s, "confirmed", True) and s.index < point_1.index]
        all_prior_highs = [s for s in all_prior_swings if s.is_high]
        all_prior_lows = [s for s in all_prior_swings if not s.is_high]

        p1_idx = point_1.index
        start_idx = max(0, p1_idx - 20)
        pre_c = candles[start_idx:p1_idx]
        is_p1_high = point_1.is_high

        # 0 Prior Swings Boundary / Synthetic Mock Handling
        if len(all_prior_swings) == 0:
            if len(pre_c) >= 2:
                p1_date = point_1.timestamp.split("T")[0] if "T" in str(point_1.timestamp) else str(point_1.timestamp)[:10]
                same_sess_c = [c for c in pre_c if (c.timestamp.split("T")[0] if "T" in str(c.timestamp) else str(c.timestamp)[:10]) == p1_date]
                eval_c = same_sess_c if len(same_sess_c) >= 2 else pre_c
                
                if is_p1_high:
                    cand_disp = point_1.price - min(c.low for c in eval_c)
                    net_disp = eval_c[-1].close - eval_c[0].open
                    if cand_disp >= min_disp and net_disp >= 0:
                        return "BULLISH", f"Candle upward displacement into High 1 (+{cand_disp:.2f} >= {min_disp:.2f})"
                    elif min(c.low for c in eval_c) - point_1.price >= min_disp:
                        return "BEARISH", "Candle downward displacement into High 1"
                    else:
                        return "SIDEWAYS", "Insufficient directional displacement into High 1"
                else:
                    cand_disp = max(c.high for c in eval_c) - point_1.price
                    net_disp = eval_c[-1].close - eval_c[0].open
                    if cand_disp >= min_disp and net_disp <= 0:
                        return "BEARISH", f"Candle downward displacement into Low 1 (-{cand_disp:.2f} >= {min_disp:.2f})"
                    elif point_1.price - max(c.high for c in eval_c) >= min_disp:
                        return "BULLISH", "Candle upward displacement into Low 1"
                    else:
                        return "SIDEWAYS", "Insufficient directional displacement into Low 1"
            return "UNCLEAR", "INSUFFICIENT_PREVIOUS_STRUCTURE_NOT_REVERSAL: No prior swings or candles before Point 1"

        # Session boundary isolation for intraday timeframes (1M, 3M, 5M, 15M, 30M)
        p1_date = point_1.timestamp.split("T")[0] if "T" in str(point_1.timestamp) else str(point_1.timestamp)[:10]
        if tf_clean in ["1M", "3M", "5M", "15M", "30M"]:
            same_session_swings = [
                s for s in all_prior_swings
                if (s.timestamp.split("T")[0] if "T" in str(s.timestamp) else str(s.timestamp)[:10]) == p1_date
            ]
            if len(same_session_swings) >= 2:
                eval_swings = same_session_swings[-5:]
            else:
                eval_swings = all_prior_swings[-5:]
        else:
            eval_swings = all_prior_swings[-5:]

        prior_highs = [s for s in eval_swings if s.is_high]
        prior_lows = [s for s in eval_swings if not s.is_high]

        # Sideways / Range-Bound Compression Check (Evaluated before directional trend checks)
        if prior_highs and prior_lows:
            struct_range = max(h.price for h in prior_highs) - min(l.price for l in prior_lows)
            if struct_range < min_disp:
                return "SIDEWAYS", f"Consolidation / range-bound market leading into Point 1 (range span {struct_range:.2f} < min disp {min_disp:.2f})"

            if len(prior_highs) >= 2 and len(prior_lows) >= 2:
                high_diff = abs(prior_highs[-1].price - prior_highs[-2].price)
                low_diff = abs(prior_lows[-1].price - prior_lows[-2].price)
                if high_diff < 0.40 * atr_val and low_diff < 0.40 * atr_val:
                    return "SIDEWAYS", "Sideways horizontal consolidation without directional trend"

        # Structural progression indicators
        is_bull_hh = len(prior_highs) >= 2 and prior_highs[-1].price > prior_highs[-2].price
        is_bull_hl = len(prior_lows) >= 2 and prior_lows[-1].price > prior_lows[-2].price
        is_bear_lh = len(prior_highs) >= 2 and prior_highs[-1].price < prior_highs[-2].price
        is_bear_ll = len(prior_lows) >= 2 and prior_lows[-1].price < prior_lows[-2].price

        if is_p1_high:
            # Check extended 5-wave exhaustion
            if len(all_prior_highs) >= 3 and all(all_prior_highs[k].price > all_prior_highs[k-1].price for k in range(1, len(all_prior_highs))):
                return "UNCLEAR", "Pattern forming after extended 5-wave trending sequence is rejected"

            # Single-pivot boundary check (Section 5: Do not use single pivot as proof of reversal)
            if len(all_prior_swings) == 1 and all_prior_swings[0].is_high:
                return "UNCLEAR", "INSUFFICIENT_PREVIOUS_STRUCTURE_NOT_REVERSAL: Single prior high without swing structure cannot prove reversal"

            # -------------------------------------------------------------------------
            # 1. CONTINUATION REJECTION (FIRST PRIORITY: PATTERN 4 BEARISH CONTINUATION)
            # -------------------------------------------------------------------------
            # Definite downtrend sequence: Lower Lows + Lower Highs
            if is_bear_ll and is_bear_lh:
                return "BEARISH", "Point 1 is a relief bounce high in a confirmed bearish sequence (Pattern 4 continuation)"

            # Asymmetric Lower Lows: Downtrend established by Lower Lows into the trough
            if is_bear_ll:
                if prior_highs and point_1.price < max(h.price for h in prior_highs):
                    return "BEARISH", "Point 1 is a relief bounce high in a confirmed bearish sequence (Pattern 4 continuation)"
                if not is_bull_hl:
                    return "BEARISH", "Point 1 is a relief bounce following a confirmed lower-low decline (Pattern 4 continuation)"

            # Preceding swing high exists and High 1 is forming a Lower High in a bearish sequence
            if len(prior_highs) >= 1 and point_1.price < prior_highs[-1].price and (is_bear_ll or (prior_lows and prior_lows[-1].price < prior_highs[-1].price)):
                return "BEARISH", "Point 1 is a lower high in a confirmed bearish sequence (Pattern 4 continuation)"

            # Lower Highs without bullish HL progression: High 1 is a relief bounce
            if is_bear_lh and not is_bull_hl:
                if prior_lows and point_1.price < max(h.price for h in prior_highs):
                    return "BEARISH", "Point 1 is a relief bounce in a confirmed lower-high sequence (Pattern 4 continuation)"

            # -------------------------------------------------------------------------
            # 2. REVERSAL ACCEPTANCE (GENUINE BULLISH PRECEDING STRUCTURE + DISPLACEMENT)
            # -------------------------------------------------------------------------
            # Hard requirement: NO contradictory bearish trend evidence allowed to pass as bullish reversal
            if is_bear_ll or is_bear_lh:
                return "UNCLEAR", "Contradictory market structure: preceding bearish swings prevent bullish reversal confirmation"

            h1_is_hh = len(prior_highs) >= 1 and point_1.price > prior_highs[-1].price
            recent_low = min(l.price for l in prior_lows) if prior_lows else None
            up_disp = (point_1.price - recent_low) if recent_low is not None else 0.0

            # Form A: Multi-swing confirmed uptrend (HL + (HH or H1 > prior high))
            form_a = is_bull_hl and (is_bull_hh or h1_is_hh)

            # Form B: Asymmetric 1 Low + confirmed Higher Highs into H1
            form_b = len(prior_lows) == 1 and is_bull_hh and h1_is_hh

            # Form C: Dominant Low Ascent (Higher Lows or 1 single low trough with clean upward progression)
            form_c = len(prior_lows) >= 1 and h1_is_hh and (
                (len(prior_lows) >= 2 and is_bull_hl) or (len(prior_lows) == 1 and len(prior_highs) <= 1)
            )

            # Form D: Single prior swing is a Low (trough of session/move)
            form_d = len(all_prior_swings) == 1 and not all_prior_swings[0].is_high

            has_bull_structure = form_a or form_b or form_c or form_d

            if has_bull_structure and up_disp >= min_disp:
                return "BULLISH", f"Confirmed bullish sequence with upward displacement (+{up_disp:.2f} >= {min_disp:.2f})"

            # Displacement alone without bullish structural progression cannot prove reversal
            if up_disp >= min_disp and not has_bull_structure:
                return "SIDEWAYS", "Displacement alone without confirmed bullish structure cannot prove reversal"

            return "SIDEWAYS", "Insufficient bullish structure and displacement leading into High 1"

        else:
            # Check extended 5-wave exhaustion
            if len(all_prior_lows) >= 3 and all(all_prior_lows[k].price < all_prior_lows[k-1].price for k in range(1, len(all_prior_lows))):
                return "UNCLEAR", "Pattern forming after extended 5-wave trending sequence is rejected"

            # Single-pivot boundary check (Section 5: Do not use single pivot as proof of reversal)
            if len(all_prior_swings) == 1 and not all_prior_swings[0].is_high:
                return "UNCLEAR", "INSUFFICIENT_PREVIOUS_STRUCTURE_NOT_REVERSAL: Single prior low without swing structure cannot prove reversal"

            # -------------------------------------------------------------------------
            # 1. CONTINUATION REJECTION (FIRST PRIORITY: PATTERN 2 BULLISH CONTINUATION)
            # -------------------------------------------------------------------------
            # Definite uptrend sequence: Higher Highs + Higher Lows
            if is_bull_hh and is_bull_hl:
                return "BULLISH", "Point 1 is a pullback low in a confirmed bullish sequence (Pattern 2 continuation)"

            # Asymmetric Higher Highs: Uptrend established by Higher Highs into the peak
            if is_bull_hh:
                if prior_lows and point_1.price > min(l.price for l in prior_lows):
                    return "BULLISH", "Point 1 is a pullback low in a confirmed bullish sequence (Pattern 2 continuation)"
                if not is_bear_lh:
                    return "BULLISH", "Point 1 is a deep pullback following a confirmed higher-high advance (Pattern 2 continuation)"

            # Preceding swing low exists and Low 1 is forming a Higher Low in a bullish sequence
            if len(prior_lows) >= 1 and point_1.price > prior_lows[-1].price and (is_bull_hh or (prior_highs and prior_highs[-1].price > prior_lows[-1].price)):
                return "BULLISH", "Point 1 forms a higher low in a bullish sequence (Pattern 2 continuation)"

            # Higher Lows without bearish LH progression: Low 1 is a pullback
            if is_bull_hl and not is_bear_lh:
                if prior_highs and point_1.price > min(l.price for l in prior_lows):
                    return "BULLISH", "Point 1 is a pullback in a confirmed higher-low sequence (Pattern 2 continuation)"

            # -------------------------------------------------------------------------
            # 2. REVERSAL ACCEPTANCE (GENUINE BEARISH PRECEDING STRUCTURE + DISPLACEMENT)
            # -------------------------------------------------------------------------
            # Hard requirement: NO contradictory bullish trend evidence allowed to pass as bearish reversal
            if is_bull_hh or is_bull_hl:
                return "UNCLEAR", "Contradictory market structure: preceding bullish swings prevent bearish reversal confirmation"

            l1_is_ll = len(prior_lows) >= 1 and point_1.price < prior_lows[-1].price
            recent_high = max(h.price for h in prior_highs) if prior_highs else None
            down_disp = (recent_high - point_1.price) if recent_high is not None else 0.0

            # Form A: Multi-swing confirmed downtrend (LH + (LL or L1 < prior low))
            form_a = is_bear_lh and (is_bear_ll or l1_is_ll)

            # Form B: Asymmetric 1 High + confirmed Lower Lows into L1
            form_b = len(prior_highs) == 1 and is_bear_ll and l1_is_ll

            # Form C: Dominant High Descent (Lower Highs or 1 single high peak with clean downward progression)
            form_c = len(prior_highs) >= 1 and l1_is_ll and (
                (len(prior_highs) >= 2 and is_bear_lh) or (len(prior_highs) == 1 and len(prior_lows) <= 1)
            )

            # Form D: Single prior swing is a High (peak of session/move)
            form_d = len(all_prior_swings) == 1 and all_prior_swings[0].is_high

            has_bear_structure = form_a or form_b or form_c or form_d

            if has_bear_structure and down_disp >= min_disp:
                return "BEARISH", f"Confirmed bearish sequence with downward displacement (-{down_disp:.2f} >= {min_disp:.2f})"

            # Displacement alone without bearish structural progression cannot prove reversal
            if down_disp >= min_disp and not has_bear_structure:
                return "SIDEWAYS", "Displacement alone without confirmed bearish structure cannot prove reversal"

            return "SIDEWAYS", "Insufficient bearish structure and displacement leading into Low 1"

    @classmethod
    def _validate_reversal_context(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        point_1: SwingPoint,
        pattern_type: str,
        atr_val: float,
        timeframe: Optional[str] = None,
        df_indicators: Optional[pd.DataFrame] = None
    ) -> Tuple[bool, str]:
        """
        Structural Reversal Validator for W and M patterns.
        
        Evaluates the preceding market regime:
        - W pattern requires BEARISH regime (rejects BULLISH continuation, SIDEWAYS, or UNCLEAR).
        - M pattern requires BULLISH regime (rejects BEARISH continuation, SIDEWAYS, or UNCLEAR).
        """
        regime, reason = cls.classify_preceding_market_regime(
            candles=candles,
            swings=swings,
            point_1=point_1,
            atr_val=atr_val,
            timeframe=timeframe,
            df_indicators=df_indicators
        )

        if pattern_type == "W":
            if regime == "BULLISH":
                return False, "BULLISH_CONTINUATION_NOT_REVERSAL"
            elif regime == "SIDEWAYS":
                return False, "SIDEWAYS_NOT_REVERSAL"
            elif regime != "BEARISH":
                return False, reason or "UNCLEAR_NOT_REVERSAL"
            return True, "OK"
        else:  # M pattern
            if regime == "BEARISH":
                return False, "BEARISH_CONTINUATION_NOT_REVERSAL"
            elif regime == "SIDEWAYS":
                return False, "SIDEWAYS_NOT_REVERSAL"
            elif regime != "BULLISH":
                return False, reason or "UNCLEAR_NOT_REVERSAL"
            return True, "OK"

    @classmethod
    def _validate_preceding_trend(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        point_1: SwingPoint,
        pattern_type: str,
        atr_val: float,
        timeframe: Optional[str] = None,
        df_indicators: Optional[pd.DataFrame] = None
    ) -> Tuple[bool, str]:
        """
        Legacy compatibility wrapper for _validate_reversal_context.
        """
        return cls._validate_reversal_context(
            candles=candles,
            swings=swings,
            point_1=point_1,
            pattern_type=pattern_type,
            atr_val=atr_val,
            timeframe=timeframe,
            df_indicators=df_indicators
        )

    @classmethod
    def extract_preceding_trend_origin(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        point_1: SwingPoint,
        pattern_type: str,
        timeframe: Optional[str] = None
    ) -> Tuple[Optional[float], Optional[str]]:
        """
        Identifies the exact swing pivot that initiated the validated preceding trend leading into Point 1:
        - For W (reversal of bearish trend): The swing high at the beginning of the validated bearish sequence.
        - For M (reversal of bullish trend): The swing low at the beginning of the validated bullish sequence.

        Respects the same structural boundary and session scoping as classify_preceding_market_regime().
        Does NOT rely on an arbitrary candle/swing window (e.g. not prior_swings[-5:] or 20 candles).
        Does NOT blindly take max(prior_highs) or min(prior_lows) across all history;
        instead walks backwards along the uninterrupted progression to isolate the initiating pivot.
        """
        tf_clean = (timeframe or "1H").upper()
        all_prior = [s for s in swings if getattr(s, "confirmed", True) and s.index < point_1.index]
        p1_date = point_1.timestamp.split("T")[0] if "T" in str(point_1.timestamp) else str(point_1.timestamp)[:10]

        if tf_clean in ["1M", "3M", "5M", "15M", "30M"]:
            same_sess = [s for s in all_prior if (s.timestamp.split("T")[0] if "T" in str(s.timestamp) else str(s.timestamp)[:10]) == p1_date]
            swings_to_scan = same_sess if len(same_sess) >= 2 else all_prior
        else:
            swings_to_scan = all_prior

        if pattern_type == "W":
            prior_highs = [s for s in swings_to_scan if s.is_high]
            if prior_highs:
                # Walk backwards from the immediate high before Point 1 through the sequence of descending highs
                origin = prior_highs[-1]
                for i in range(len(prior_highs) - 2, -1, -1):
                    h = prior_highs[i]
                    if h.price > origin.price:
                        origin = h
                    else:
                        break
                return origin.price, origin.timestamp

            # Fallback if zero confirmed swing highs exist but same-session candles exist
            p1_idx = point_1.index
            if candles and p1_idx > 0:
                start_idx = max(0, p1_idx - 20)
                pre_c = candles[start_idx:p1_idx]
                same_sess_c = [c for c in pre_c if (c.timestamp.split("T")[0] if "T" in str(c.timestamp) else str(c.timestamp)[:10]) == p1_date]
                eval_c = same_sess_c if len(same_sess_c) >= 2 else pre_c
                if eval_c:
                    max_c = max(eval_c, key=lambda c: c.high)
                    return max_c.high, max_c.timestamp

            return None, None

        else:  # M Pattern
            prior_lows = [s for s in swings_to_scan if not s.is_high]
            if prior_lows:
                # Walk backwards from the immediate low before Point 1 through the sequence of ascending lows
                origin = prior_lows[-1]
                for i in range(len(prior_lows) - 2, -1, -1):
                    l = prior_lows[i]
                    if l.price < origin.price:
                        origin = l
                    else:
                        break
                return origin.price, origin.timestamp

            # Fallback if zero confirmed swing lows exist but same-session candles exist
            p1_idx = point_1.index
            if candles and p1_idx > 0:
                start_idx = max(0, p1_idx - 20)
                pre_c = candles[start_idx:p1_idx]
                same_sess_c = [c for c in pre_c if (c.timestamp.split("T")[0] if "T" in str(c.timestamp) else str(c.timestamp)[:10]) == p1_date]
                eval_c = same_sess_c if len(same_sess_c) >= 2 else pre_c
                if eval_c:
                    min_c = min(eval_c, key=lambda c: c.low)
                    return min_c.low, min_c.timestamp

            return None, None

    @staticmethod
    def _cluster_swings(swings: List[SwingPoint], atr_val: float, max_bar_diff: int = 3, price_tol_atr: float = 0.15) -> List[SwingPoint]:
        """
        Consolidates adjacent equivalent swing highs or lows within price_tol_atr * ATR and <= max_bar_diff bars
        into a single consolidated structural pivot.
        """
        if not swings:
            return []
        clustered = [swings[0]]
        for s in swings[1:]:
            prev = clustered[-1]
            if (s.is_high == prev.is_high and 
                abs(s.price - prev.price) <= price_tol_atr * max(0.0001, atr_val) and 
                abs(s.index - prev.index) <= max_bar_diff):
                # Merge into the more extreme price pivot
                if s.is_high:
                    if s.price >= prev.price:
                        clustered[-1] = s
                else:
                    if s.price <= prev.price:
                        clustered[-1] = s
            else:
                clustered.append(s)
        return clustered

    @classmethod
    def detect_wm_patterns(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        trendlines: List[Trendline],
        df_indicators: Optional[pd.DataFrame],
        symbol: str,
        timeframe: str,
        atr_val: float,
        price_tolerance_atr: float = 1.50,
        min_depth_atr: float = 0.80,
        min_bar_spacing: int = 6,
        max_bar_spacing: int = 60,
        min_breakout_dist_atr: float = 0.05,
        key_supports: List[float] = [],
        key_resistances: List[float] = [],
        enforce_precision: Optional[bool] = None
    ) -> Tuple[List[StructureBreakEvent], List[WMPatternStructure], Optional[WMPatternStructure], List[WMPatternStructure]]:
        """
        Complete Structural W/M Pattern Engine.
        
        Returns:
        - events: Confirmed high-confluence breakout events (for alerts).
        - confirmed_patterns: List of all confirmed W/M patterns (for history toggle).
        - active_pattern: Single latest active confirmed (or forming) pattern to keep chart clean.
        - debug_candidates: Evaluated candidate formations with rejection diagnostics.
        """
        if len(candles) < 10 or len(swings) < 2:
            return [], [], None, []

        if enforce_precision is None:
            enforce_precision = getattr(settings, "ENFORCE_BALANCED_WM_PRECISION", True)

        events: List[StructureBreakEvent] = []
        confirmed_patterns: List[WMPatternStructure] = []
        debug_candidates: List[WMPatternStructure] = []
        confirmed_structural_keys: Set[Tuple[str, str, str]] = set()
        confirmed_pattern_ids: Set[str] = set()
        confirmed_w_l1_timestamps: Set[str] = set()
        confirmed_m_h1_timestamps: Set[str] = set()
        n = len(candles)
        min_breakout_dist = max(0.0001, min_breakout_dist_atr * atr_val)

        tf_clean = (timeframe or "1H").upper()
        if tf_clean in ["5M", "1M", "3M"]:
            effective_min_bar_sep = 4
            effective_min_depth_atr = 0.80
        else:
            effective_min_bar_sep = max(min_bar_spacing, getattr(settings, "MIN_WM_BAR_SEPARATION", 6))
            effective_min_depth_atr = min_depth_atr

        raw_low_swings = [s for s in swings if not s.is_high and getattr(s, "confirmed", True)]
        raw_high_swings = [s for s in swings if s.is_high and getattr(s, "confirmed", True)]
        low_swings = cls._cluster_swings(raw_low_swings, atr_val, max_bar_diff=4, price_tol_atr=0.20)
        high_swings = cls._cluster_swings(raw_high_swings, atr_val, max_bar_diff=4, price_tol_atr=0.20)

        # -------------------------------------------------------------
        # 1. EVALUATE M PATTERNS (Double Top Reversals)
        # -------------------------------------------------------------
        max_swings_ahead = getattr(settings, "W_M_MAX_CANDIDATE_SWINGS_AHEAD", 10)
        for idx_h1 in range(len(high_swings) - 1):
            h1 = high_swings[idx_h1]

            # 1. HARD GATE: Preceding market context MUST be Bullish for M reversal
            is_valid_trend, trend_reason = cls._validate_reversal_context(
                candles=candles, swings=swings, point_1=h1, pattern_type="M", atr_val=atr_val, timeframe=timeframe, df_indicators=df_indicators
            )
            if not is_valid_trend:
                debug_candidates.append(WMPatternStructure(
                    pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_INVALID_CONTEXT",
                    pattern_type="M",
                    status="REJECTED",
                    s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                    neckline_index=h1.index + 1, neckline_price=0.0, neckline_time="",
                    s2_index=h1.index + 1, s2_price=0.0, s2_time="",
                    pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=0,
                    quality_score=0, rejection_reason=trend_reason,
                    symbol=symbol, timeframe=timeframe
                ))
                continue

            for idx_h2 in range(idx_h1 + 1, min(idx_h1 + max_swings_ahead, len(high_swings))):
                h2 = high_swings[idx_h2]
                bar_sep = h2.index - h1.index

                # Intraday Same-Session / Date Boundary Check (5M, 15M, 1M, 3M)
                if tf_clean in ["5M", "15M", "1M", "3M"]:
                    s1_date = h1.timestamp.split("T")[0] if "T" in str(h1.timestamp) else str(h1.timestamp)[:10]
                    s2_date = h2.timestamp.split("T")[0] if "T" in str(h2.timestamp) else str(h2.timestamp)[:10]
                    if s1_date != s2_date:
                        debug_candidates.append(WMPatternStructure(
                            pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                            pattern_type="M",
                            status="REJECTED",
                            s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                            neckline_index=h1.index + 1, neckline_price=0.0, neckline_time="",
                            s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                            pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                            quality_score=0, rejection_reason="Inter-day session boundary bridging not allowed for intraday timeframes",
                            symbol=symbol, timeframe=timeframe
                        ))
                        continue

                # Preceding trend validation leading into High 1 (must be BULLISH for M reversal)
                is_valid_trend, trend_reason = cls._validate_reversal_context(
                    candles=candles, swings=swings, point_1=h1, pattern_type="M", atr_val=atr_val, timeframe=timeframe, df_indicators=df_indicators
                )
                if not is_valid_trend:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=h1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason=trend_reason,
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # Horizontal separation filter
                if bar_sep < effective_min_bar_sep or bar_sep > max_bar_spacing:
                    if bar_sep < effective_min_bar_sep:
                        debug_candidates.append(WMPatternStructure(
                            pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                            pattern_type="M",
                            status="REJECTED",
                            s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                            neckline_index=h1.index + 1, neckline_price=0.0, neckline_time="",
                            s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                            pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                            quality_score=0, rejection_reason=f"Point 1 to Point 2 bar separation too narrow ({bar_sep} < {effective_min_bar_sep} bars)",
                            symbol=symbol, timeframe=timeframe
                        ))
                    continue

                # Intermediate trough swing low (Neckline)
                inter_lows = [l for l in low_swings if h1.index < l.index < h2.index]
                clustered_inter_lows = cls._cluster_swings(inter_lows, atr_val, max_bar_diff=4, price_tol_atr=0.20)
                if not clustered_inter_lows:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=h1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason="No confirmed structural reaction low between High 1 and High 2",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                mid_trough = min(clustered_inter_lows, key=lambda l: l.price)
                neckline = mid_trough.price
                pattern_depth = max(h1.price, h2.price) - neckline

                # Wave structure check: Discrimination between reaction zone consolidation vs independent multi-wave
                inter_highs = [h for h in high_swings if h1.index < h.index < h2.index]
                deep_inter_highs = [
                    h for h in inter_highs
                    if (h.price > neckline + 0.65 * pattern_depth) and
                    (h.index - h1.index >= 2) and (h2.index - h.index >= 2) and
                    not (abs(h.price - h1.price) <= 0.20 * atr_val and abs(h.index - h1.index) <= 4) and
                    not (abs(h.price - h2.price) <= 0.20 * atr_val and abs(h.index - h2.index) <= 4)
                ]
                if len(deep_inter_highs) > 0:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=h1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason="Intervening structural swing high between High 1 and High 2 (multi-wave structure)",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # If there are multiple separate non-clustered troughs (> 1), reject as competing necklines
                if len(clustered_inter_lows) > 1:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=h1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason="Multiple intermediate structural lows between High 1 and High 2 (competing necklines / multi-wave structure)",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # Point 2 = High 2. SL = High 2 + configurable ATR buffer (strictly > neckline)
                sl_buf = getattr(settings, "W_M_SL_ATR_BUFFER", 0.15)
                m_sl_val = round(h2.price + (sl_buf * atr_val), 2)
                m_sl_time = h2.timestamp

                mid_trough = clustered_inter_lows[0]
                neckline = mid_trough.price

                # Symmetry & Depth
                diff_price = abs(h1.price - h2.price)
                diff_atr = diff_price / max(0.0001, atr_val)
                pattern_depth = max(h1.price, h2.price) - neckline
                depth_atr = pattern_depth / max(0.0001, atr_val)

                # Structural leg spacing check
                min_leg_bars = 1 if tf_clean in ["5M", "1M", "3M"] else 2
                leg1_bars = mid_trough.index - h1.index
                leg2_bars = h2.index - mid_trough.index
                if leg1_bars < min_leg_bars or leg2_bars < min_leg_bars:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"Structural leg spacing too narrow (leg 1: {leg1_bars} bars, leg 2: {leg2_bars} bars; minimum 2 required)",
                        symbol=symbol, timeframe=timeframe,
                        preceding_regime="BULLISH",
                        primary_leg_amplitude=round(h1.price - neckline, 2),
                        retest_leg_amplitude=round(h2.price - neckline, 2),
                        s1_s2_difference=round(diff_price, 2),
                        reaction_zone_strength=float(len(clustered_inter_lows)),
                        intermediate_wave_count=len(inter_highs)
                    ))
                    continue

                # Relaxed structural depth: total pattern height must be >= 0.70 ATR
                if depth_atr < 0.70:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"Insufficient neckline depth ({depth_atr:.2f} ATR < 0.70 ATR)",
                        symbol=symbol, timeframe=timeframe,
                        preceding_regime="BULLISH",
                        primary_leg_amplitude=round(h1.price - neckline, 2),
                        retest_leg_amplitude=round(h2.price - neckline, 2),
                        s1_s2_difference=round(diff_price, 2),
                        reaction_zone_strength=float(len(clustered_inter_lows)),
                        intermediate_wave_count=len(inter_highs)
                    ))
                    continue

                # Primary & retest leg amplitude check (structural validation)
                leg1_amp = h1.price - neckline
                leg2_amp = h2.price - neckline
                min_primary_amp = 0.60 * atr_val
                min_retest_amp = max(0.30 * atr_val, 0.20 * pattern_depth)

                if max(leg1_amp, leg2_amp) < min_primary_amp:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"Primary leg amplitude too small ({max(leg1_amp, leg2_amp):.2f} < {min_primary_amp:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                if min(leg1_amp, leg2_amp) < min_retest_amp:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"Retest leg amplitude too small ({min(leg1_amp, leg2_amp):.2f} < {min_retest_amp:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # Bounded volatility-normalized symmetry: capped strictly between 1.10 ATR and 1.50 ATR
                max_allowed_diff = min(1.50 * atr_val, max(1.10 * atr_val, h1.price * 0.005))
                if diff_price > max_allowed_diff:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"Highs too asymmetric ({diff_price:.2f} > {max_allowed_diff:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # S2 Overshoot check (allows marginal liquidity sweeps up to bounded tolerance)
                max_m_overshoot = min(1.0 * atr_val, max(0.75 * atr_val, 0.25 * pattern_depth))
                if h2.price > h1.price + max_m_overshoot:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"High 2 overshoots High 1 beyond allowed sweep tolerance ({h2.price - h1.price:.2f} > {max_m_overshoot:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                pattern_id = f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}"

                # Calculate preceding trend origin for genuine M reversal target (preceding swing low)
                m_origin, _ = cls.extract_preceding_trend_origin(candles, swings, point_1=h1, pattern_type="M", timeframe=timeframe)

                # Calculate measured target and independent invalidation / Stop Loss
                target_analysis = cls.calculate_pattern_targets(
                    pattern_type="M",
                    s1_price=h1.price,
                    s2_price=h2.price,
                    neckline_price=neckline,
                    breakout_close=neckline - min_breakout_dist,
                    prev_swing_sl=m_sl_val,
                    key_supports=key_supports,
                    key_resistances=key_resistances,
                    atr_val=atr_val,
                    sl_atr_buffer=sl_buf,
                    reversal_target=m_origin
                )

                # Scan for confirmed breakout candle strictly after Point 2 (H2)
                # Look-ahead timing guard: breakout candle must be at or after H2's confirmation index
                h2_conf_idx = getattr(h2, "confirmation_index", None)
                min_breakout_scan_start = max(h2.index + 1, h2_conf_idx if h2_conf_idx is not None else h2.index + 1)

                structural_break_idx: Optional[int] = None
                structural_break_time: Optional[str] = None
                structural_break_close: Optional[float] = None
                is_high_confluence = False
                breakout_tl: Optional[Trendline] = None
                breakout_ema: Optional[float] = None
                breakout_vol: float = 1.0
                tl_broken: bool = False
                ema_broken: bool = False
                is_forming = False
                is_invalidated = False
                is_target_1_hit = False
                is_target_2_hit = False
                outcome_ts: Optional[str] = None

                relevant_tls = [
                    t for t in trendlines
                    if t.line_type == "ASCENDING_SUPPORT" and t.p1_index <= h2.index
                ] or [t for t in trendlines if t.line_type == "ASCENDING_SUPPORT"]

                max_scan_bars = max(15, min(35, int(bar_sep * 1.8)))
                max_scan_index = min(n, h2.index + max_scan_bars)
                already_moved_too_far = False

                max_extension_ratio = getattr(settings, "MAX_BREAKOUT_EXTENSION_DEPTH_RATIO", 0.75)

                for i in range(min_breakout_scan_start, max_scan_index):
                    c = candles[i]
                    is_latest_candle = (i == n - 1)

                    # If this is the active live unclosed candle, check for intrabar forming
                    if is_latest_candle:
                        if c.close < neckline or c.low < neckline:
                            if structural_break_idx is None:
                                is_forming = True
                        continue

                    # Completed candle close check
                    if structural_break_idx is None:
                        # Structural Breakdown condition: first completed candle closing below neckline
                        if c.close < neckline:
                            structural_break_idx = i
                            structural_break_time = c.timestamp
                            structural_break_close = c.close

                            # Check if breakout candle is overextended
                            if c.close <= (neckline - max_extension_ratio * pattern_depth):
                                already_moved_too_far = True

                            ema_20: Optional[float] = None
                            rel_vol: float = 1.0
                            if df_indicators is not None and i < len(df_indicators):
                                row = df_indicators.iloc[i]
                                if "ema_20" in row and not pd.isna(row["ema_20"]):
                                    ema_20 = float(row["ema_20"])
                                if "relative_volume" in row and not pd.isna(row["relative_volume"]):
                                    rel_vol = float(row["relative_volume"])

                            ema_broken = (c.close < ema_20) if ema_20 is not None else False
                            
                            tl_broken = False
                            matching_tl: Optional[Trendline] = None
                            if relevant_tls:
                                for tl in relevant_tls:
                                    tl_price = tl.p1_price + tl.slope * (i - tl.p1_index)
                                    tl_tolerance = max(tl_price * 0.0003, atr_val * 0.05)
                                    if c.close < (tl_price - tl_tolerance):
                                        tl_broken = True
                                        matching_tl = tl
                                        break
                                    else:
                                        tl_broken = False

                            breakout_tl = matching_tl
                            breakout_ema = ema_20
                            breakout_vol = rel_vol

                            # Check High Confluence conditions on this breakout candle
                            if ema_broken and tl_broken:
                                is_high_confluence = True
                    else:
                        # Subsequent candle evaluation:
                        # 1. Target 2 reached (terminal winner)
                        if c.low <= target_analysis.target_2:
                            is_target_2_hit = True
                            outcome_ts = c.timestamp
                            break
                        # 2. Target 1 reached
                        elif c.low <= target_analysis.measured_target:
                            is_target_1_hit = True
                            outcome_ts = c.timestamp
                        # 3. Stop Loss breach (only if Target 1 not reached)
                        elif not is_target_1_hit and (c.high >= target_analysis.invalidation_level or c.close >= target_analysis.invalidation_level):
                            is_invalidated = True
                            outcome_ts = c.timestamp
                            break

                # Quality Score
                q_score, q_breakdown = cls.calculate_wm_quality_score(
                    pattern_type="M",
                    s1=h1,
                    neckline_swing=mid_trough,
                    s2=h2,
                    neckline_price=neckline,
                    breakout_candle=candles[structural_break_idx] if structural_break_idx is not None else None,
                    tl=breakout_tl,
                    ema_20=breakout_ema,
                    atr_val=atr_val,
                    rel_vol=breakout_vol,
                    tl_broken=tl_broken,
                    ema_broken=ema_broken
                )

                min_quality_score = getattr(settings, "MIN_WM_QUALITY_SCORE", 70)
                min_rr = getattr(settings, "MIN_WM_RR", 0.85)

                actual_rr = target_analysis.risk_reward_ratio
                if structural_break_close is not None and target_analysis.invalidation_level is not None:
                    actual_risk = max(0.0001, target_analysis.invalidation_level - structural_break_close)
                    actual_reward = max(0.0, structural_break_close - target_analysis.measured_target)
                    actual_rr = round(actual_reward / actual_risk, 2)
                    target_analysis.risk_reward_ratio = actual_rr

                # Decoupled Entry Status and Trade Quality Classification
                if already_moved_too_far:
                    entry_status_val = "OVEREXTENDED"
                elif actual_rr is not None and actual_rr < min_rr:
                    entry_status_val = "POOR_RR"
                else:
                    entry_status_val = "VALID"

                if q_score >= 85:
                    trade_quality_val = "HIGH"
                elif q_score >= 70:
                    trade_quality_val = "MEDIUM"
                else:
                    trade_quality_val = "LOW"

                target_analysis.pattern_quality_score = q_score
                target_analysis.quality_breakdown = q_breakdown
                target_analysis.reversal_score = q_breakdown.get("reversal", 40)
                target_analysis.trendline_score = q_breakdown.get("trendline", 0)
                target_analysis.ema_score = q_breakdown.get("ema", 0)
                target_analysis.reversal_points = q_breakdown.get("reversal", 40)
                target_analysis.trendline_points = q_breakdown.get("trendline", 0)
                target_analysis.ema_points = q_breakdown.get("ema", 0)

                # Determine precise pattern lifecycle status
                if is_target_2_hit:
                    pat_status = "TARGET_2_HIT"
                    brk_status_val = "CONFIRMED"
                elif is_target_1_hit:
                    pat_status = "TARGET_1_HIT"
                    brk_status_val = "CONFIRMED"
                elif is_invalidated:
                    pat_status = "INVALIDATED"
                    brk_status_val = "CONFIRMED"
                elif structural_break_idx is not None:
                    if is_high_confluence and q_score >= min_quality_score:
                        pat_status = "HIGH_CONFLUENCE_CONFIRMED"
                    else:
                        pat_status = "BREAKOUT_CONFIRMED"
                    brk_status_val = "CONFIRMED"
                elif is_forming:
                    pat_status = "BREAKDOWN_FORMING"
                    brk_status_val = "PENDING"
                else:
                    pat_status = "FORMING"
                    brk_status_val = "PENDING"

                m_pattern_obj = WMPatternStructure(
                    pattern_id=pattern_id,
                    pattern_type="M",
                    status=pat_status,
                    s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                    neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                    s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                    pattern_height=round(target_analysis.pattern_height, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                    bar_separation=bar_sep, quality_score=q_score,
                    reversal_score=q_breakdown.get("reversal", 40),
                    trendline_score=q_breakdown.get("trendline", 0),
                    ema_score=q_breakdown.get("ema", 0),
                    reversal_points=q_breakdown.get("reversal", 40),
                    trendline_points=q_breakdown.get("trendline", 0),
                    ema_points=q_breakdown.get("ema", 0),
                    breakout_candle_index=structural_break_idx,
                    breakout_candle_time=structural_break_time,
                    breakout_close=round(structural_break_close, 2) if structural_break_close else None,
                    target_analysis=target_analysis,
                    is_active=False,
                    prev_swing_sl_price=round(m_sl_val, 2),
                    prev_swing_sl_time=m_sl_time,
                    symbol=symbol,
                    timeframe=timeframe,
                    target_1=round(target_analysis.measured_target, 2),
                    target_2=round(target_analysis.target_2, 2) if target_analysis.target_2 else None,
                    stop_loss=round(target_analysis.invalidation_level, 2),
                    risk_reward_ratio=actual_rr,
                    trade_quality=trade_quality_val,
                    entry_status=entry_status_val,
                    breakout_status=brk_status_val,
                    outcome_timestamp=outcome_ts if (is_target_2_hit or is_target_1_hit or is_invalidated) else None,
                    preceding_regime="BULLISH",
                    net_displacement=round(h1.price - min((l.price for l in swings if (not l.is_high) and l.index < h1.index), default=h1.price - 0.80 * atr_val), 2),
                    primary_leg_amplitude=round(max(leg1_amp, leg2_amp), 2),
                    retest_leg_amplitude=round(min(leg1_amp, leg2_amp), 2),
                    s1_s2_difference=round(diff_price, 2),
                    allowed_symmetry=round(max_allowed_diff, 2),
                    allowed_sweep=round(max_m_overshoot, 2),
                    reaction_zone_strength=float(len(clustered_inter_lows)),
                    intermediate_wave_count=len(inter_highs),
                    multi_wave_rejected=False,
                    continuation_rejected=False
                )

                m_struct_key = ("M", h1.timestamp, mid_trough.timestamp)
                if structural_break_idx is not None:
                    if m_struct_key in confirmed_structural_keys or pattern_id in confirmed_pattern_ids:
                        debug_candidates.append(m_pattern_obj)
                        continue
                    confirmed_structural_keys.add(m_struct_key)
                    confirmed_pattern_ids.add(pattern_id)
                    confirmed_m_h1_timestamps.add(h1.timestamp)
                    confirmed_patterns.append(m_pattern_obj)
                elif is_target_1_hit or is_target_2_hit or is_invalidated:
                    confirmed_patterns.append(m_pattern_obj)
                debug_candidates.append(m_pattern_obj)

                # Emit structure break event upon confirmed candle close!
                if structural_break_idx is not None:
                    is_high_conf_alert = (is_high_confluence and q_score >= min_quality_score)
                    event_type = (
                        "M_PATTERN_TRENDLINE_EMA_DOWN_BREAKOUT"
                        if is_high_conf_alert
                        else "M_PATTERN_BREAKDOWN"
                    )
                    event_id = f"{symbol}_{timeframe}_{event_type}_{structural_break_time}_{round(neckline, 1)}"
                    
                    events.append(StructureBreakEvent(
                        id=event_id,
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=structural_break_time,
                        event_type=event_type,
                        direction="BEARISH",
                        broken_level=round(neckline, 2),
                        break_price=round(structural_break_close, 2),
                        break_candle_index=structural_break_idx,
                        volume_confirmed=True if breakout_vol >= 1.15 else False,
                        atr_at_break=round(atr_val, 2),
                        htf_alignment="BEARISH",
                        evidence_score=q_score,
                        pattern_quality_score=q_score,
                        pattern_id=pattern_id,
                        pattern_type="M",
                        pattern_formed_time=h2.timestamp,
                        first_swing_price=round(h1.price, 2),
                        first_swing_time=h1.timestamp,
                        second_swing_price=round(h2.price, 2),
                        second_swing_time=h2.timestamp,
                        neckline_price=round(neckline, 2),
                        neckline_time=mid_trough.timestamp,
                        breakout_candle_open=round(candles[structural_break_idx].open, 2),
                        breakout_candle_high=round(candles[structural_break_idx].high, 2),
                        breakout_candle_low=round(candles[structural_break_idx].low, 2),
                        breakout_candle_close=round(structural_break_close, 2),
                        trendline_level=round(breakout_tl.p1_price + breakout_tl.slope * (structural_break_idx - breakout_tl.p1_index), 2) if breakout_tl else round(neckline, 2),
                        ema20_level=round(breakout_ema, 2) if breakout_ema else round(neckline, 2),
                        volume_ratio=round(breakout_vol, 2),
                        target_analysis=target_analysis,
                        notes=f"🔴 {'M + TL + EMA + VOL ↓' if is_high_conf_alert else 'M BREAKDOWN ↓'}: H1 {h1.price:.2f} -> Neckline {neckline:.2f} -> H2 {h2.price:.2f} | Breakout Close: {structural_break_close:.2f} at {structural_break_time} | Target: {target_analysis.measured_target:.2f}"
                    ))

        # -------------------------------------------------------------
        # 2. EVALUATE W PATTERNS (Double Bottom Reversals)
        # -------------------------------------------------------------
        for idx_l1 in range(len(low_swings) - 1):
            l1 = low_swings[idx_l1]

            # 1. HARD GATE: Preceding market context MUST be Bearish for W reversal
            is_valid_trend, trend_reason = cls._validate_reversal_context(
                candles=candles, swings=swings, point_1=l1, pattern_type="W", atr_val=atr_val, timeframe=timeframe, df_indicators=df_indicators
            )
            if not is_valid_trend:
                debug_candidates.append(WMPatternStructure(
                    pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_INVALID_CONTEXT",
                    pattern_type="W",
                    status="REJECTED",
                    s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                    neckline_index=l1.index + 1, neckline_price=0.0, neckline_time="",
                    s2_index=l1.index + 1, s2_price=0.0, s2_time="",
                    pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=0,
                    quality_score=0, rejection_reason=trend_reason,
                    symbol=symbol, timeframe=timeframe
                ))
                continue

            for idx_l2 in range(idx_l1 + 1, min(idx_l1 + max_swings_ahead, len(low_swings))):
                l2 = low_swings[idx_l2]
                bar_sep = l2.index - l1.index

                # Intraday Same-Session / Date Boundary Check (5M, 15M, 1M, 3M)
                if tf_clean in ["5M", "15M", "1M", "3M"]:
                    s1_date = l1.timestamp.split("T")[0] if "T" in str(l1.timestamp) else str(l1.timestamp)[:10]
                    s2_date = l2.timestamp.split("T")[0] if "T" in str(l2.timestamp) else str(l2.timestamp)[:10]
                    if s1_date != s2_date:
                        debug_candidates.append(WMPatternStructure(
                            pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                            pattern_type="W",
                            status="REJECTED",
                            s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                            neckline_index=l1.index + 1, neckline_price=0.0, neckline_time="",
                            s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                            pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                            quality_score=0, rejection_reason="Inter-day session boundary bridging not allowed for intraday timeframes",
                            symbol=symbol, timeframe=timeframe
                        ))
                        continue

                # Preceding trend validation leading into Low 1 (must be BEARISH for W reversal)
                is_valid_trend, trend_reason = cls._validate_reversal_context(
                    candles=candles, swings=swings, point_1=l1, pattern_type="W", atr_val=atr_val, timeframe=timeframe, df_indicators=df_indicators
                )
                if not is_valid_trend:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=l1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason=trend_reason,
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                if bar_sep < effective_min_bar_sep or bar_sep > max_bar_spacing:
                    if bar_sep < effective_min_bar_sep:
                        debug_candidates.append(WMPatternStructure(
                            pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                            pattern_type="W",
                            status="REJECTED",
                            s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                            neckline_index=l1.index + 1, neckline_price=0.0, neckline_time="",
                            s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                            pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                            quality_score=0, rejection_reason=f"Point 1 to Point 2 bar separation too narrow ({bar_sep} < {effective_min_bar_sep} bars)",
                            symbol=symbol, timeframe=timeframe
                        ))
                    continue

                inter_highs = [h for h in high_swings if l1.index < h.index < l2.index]
                clustered_inter_highs = cls._cluster_swings(inter_highs, atr_val, max_bar_diff=4, price_tol_atr=0.20)
                if not clustered_inter_highs:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=l1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason="No confirmed structural reaction high between Low 1 and Low 2",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                mid_peak = max(clustered_inter_highs, key=lambda h: h.price)
                neckline = mid_peak.price
                pattern_depth = neckline - min(l1.price, l2.price)

                # Wave structure check: Discrimination between reaction zone consolidation vs independent multi-wave
                inter_lows = [l for l in low_swings if l1.index < l.index < l2.index]
                deep_inter_lows = [
                    l for l in inter_lows
                    if (l.price < neckline - 0.65 * pattern_depth) and
                    (l.index - l1.index >= 2) and (l2.index - l.index >= 2) and
                    not (abs(l.price - l1.price) <= 0.20 * atr_val and abs(l.index - l1.index) <= 4) and
                    not (abs(l.price - l2.price) <= 0.20 * atr_val and abs(l.index - l2.index) <= 4)
                ]
                if len(deep_inter_lows) > 0:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=l1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason="Intervening structural swing low between Low 1 and Low 2 (multi-wave structure)",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # If there are multiple separate non-clustered peaks (> 1), reject as competing necklines
                if len(clustered_inter_highs) > 1:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=l1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason="Multiple intermediate structural highs between Low 1 and Low 2 (competing necklines / multi-wave structure)",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # Point 2 = Low 2. SL = Low 2 - configurable ATR buffer (strictly < neckline)
                sl_buf = getattr(settings, "W_M_SL_ATR_BUFFER", 0.15)
                w_sl_val = round(l2.price - (sl_buf * atr_val), 2)
                w_sl_time = l2.timestamp

                mid_peak = clustered_inter_highs[0]
                neckline = mid_peak.price

                diff_price = abs(l1.price - l2.price)
                diff_atr = diff_price / max(0.0001, atr_val)
                pattern_depth = neckline - min(l1.price, l2.price)
                depth_atr = pattern_depth / max(0.0001, atr_val)

                # Structural leg spacing check
                min_leg_bars = 1 if tf_clean in ["5M", "1M", "3M"] else 2
                leg1_bars = mid_peak.index - l1.index
                leg2_bars = l2.index - mid_peak.index
                if leg1_bars < min_leg_bars or leg2_bars < min_leg_bars:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"Structural leg spacing too narrow (leg 1: {leg1_bars} bars, leg 2: {leg2_bars} bars; minimum 2 required)",
                        symbol=symbol, timeframe=timeframe,
                        preceding_regime="BEARISH",
                        primary_leg_amplitude=round(neckline - l1.price, 2),
                        retest_leg_amplitude=round(neckline - l2.price, 2),
                        s1_s2_difference=round(diff_price, 2),
                        reaction_zone_strength=float(len(clustered_inter_highs)),
                        intermediate_wave_count=len(inter_lows)
                    ))
                    continue

                # Relaxed structural depth: total pattern height must be >= 0.70 ATR
                if depth_atr < 0.70:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"Insufficient neckline depth ({depth_atr:.2f} ATR < 0.70 ATR)",
                        symbol=symbol, timeframe=timeframe,
                        preceding_regime="BEARISH",
                        primary_leg_amplitude=round(neckline - l1.price, 2),
                        retest_leg_amplitude=round(neckline - l2.price, 2),
                        s1_s2_difference=round(diff_price, 2),
                        reaction_zone_strength=float(len(clustered_inter_highs)),
                        intermediate_wave_count=len(inter_lows)
                    ))
                    continue

                # Primary & retest leg amplitude check (structural validation)
                leg1_amp = neckline - l1.price
                leg2_amp = neckline - l2.price
                min_primary_amp = 0.60 * atr_val
                min_retest_amp = max(0.30 * atr_val, 0.20 * pattern_depth)

                if max(leg1_amp, leg2_amp) < min_primary_amp:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"Primary leg amplitude too small ({max(leg1_amp, leg2_amp):.2f} < {min_primary_amp:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                if min(leg1_amp, leg2_amp) < min_retest_amp:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"Retest leg amplitude too small ({min(leg1_amp, leg2_amp):.2f} < {min_retest_amp:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # Bounded volatility-normalized symmetry: capped strictly between 1.10 ATR and 1.50 ATR
                max_allowed_diff = min(1.50 * atr_val, max(1.10 * atr_val, l1.price * 0.005))
                if diff_price > max_allowed_diff:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"Lows too asymmetric ({diff_price:.2f} > {max_allowed_diff:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # S2 Overshoot check (allows marginal liquidity sweeps up to bounded tolerance)
                max_w_overshoot = min(1.0 * atr_val, max(0.75 * atr_val, 0.25 * pattern_depth))
                if l2.price < l1.price - max_w_overshoot:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason=f"Low 2 overshoots Low 1 beyond allowed sweep tolerance ({l1.price - l2.price:.2f} > {max_w_overshoot:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                pattern_id = f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}"

                # Calculate preceding trend origin for genuine W reversal target (preceding swing high)
                w_origin, _ = cls.extract_preceding_trend_origin(candles, swings, point_1=l1, pattern_type="W", timeframe=timeframe)

                # Calculate measured target and independent invalidation / Stop Loss
                target_analysis = cls.calculate_pattern_targets(
                    pattern_type="W",
                    s1_price=l1.price,
                    s2_price=l2.price,
                    neckline_price=neckline,
                    breakout_close=neckline + min_breakout_dist,
                    prev_swing_sl=w_sl_val,
                    key_supports=key_supports,
                    key_resistances=key_resistances,
                    atr_val=atr_val,
                    sl_atr_buffer=sl_buf,
                    reversal_target=w_origin
                )

                # Scan for confirmed breakout candle strictly after Point 2 (L2)
                l2_conf_idx = getattr(l2, "confirmation_index", None)
                min_breakout_scan_start = max(l2.index + 1, l2_conf_idx if l2_conf_idx is not None else l2.index + 1)

                structural_break_idx: Optional[int] = None
                structural_break_time: Optional[str] = None
                structural_break_close: Optional[float] = None
                is_high_confluence = False
                breakout_tl: Optional[Trendline] = None
                breakout_ema: Optional[float] = None
                breakout_vol: float = 1.0
                tl_broken: bool = False
                ema_broken: bool = False
                is_forming = False
                is_invalidated = False
                is_target_1_hit = False
                is_target_2_hit = False
                outcome_ts: Optional[str] = None

                relevant_tls = [
                    t for t in trendlines
                    if t.line_type == "DESCENDING_RESISTANCE" and t.p1_index <= l2.index
                ] or [t for t in trendlines if t.line_type == "DESCENDING_RESISTANCE"]

                max_scan_bars = max(15, min(35, int(bar_sep * 1.8)))
                max_scan_index = min(n, l2.index + max_scan_bars)
                already_moved_too_far = False

                max_extension_ratio = getattr(settings, "MAX_BREAKOUT_EXTENSION_DEPTH_RATIO", 0.75)

                for i in range(min_breakout_scan_start, max_scan_index):
                    c = candles[i]
                    is_latest_candle = (i == n - 1)

                    # If active unclosed candle, check for intrabar forming
                    if is_latest_candle:
                        if c.close > neckline or c.high > neckline:
                            if structural_break_idx is None:
                                is_forming = True
                        continue

                    if structural_break_idx is None:
                        # Structural Breakout condition: first completed candle closing above neckline
                        if c.close > neckline:
                            structural_break_idx = i
                            structural_break_time = c.timestamp
                            structural_break_close = c.close

                            # Check if breakout candle is overextended
                            if c.close >= (neckline + max_extension_ratio * pattern_depth):
                                already_moved_too_far = True

                            ema_20: Optional[float] = None
                            rel_vol: float = 1.0
                            if df_indicators is not None and i < len(df_indicators):
                                row = df_indicators.iloc[i]
                                if "ema_20" in row and not pd.isna(row["ema_20"]):
                                    ema_20 = float(row["ema_20"])
                                if "relative_volume" in row and not pd.isna(row["relative_volume"]):
                                    rel_vol = float(row["relative_volume"])

                            ema_broken = (c.close > ema_20) if ema_20 is not None else False
                            
                            tl_broken = False
                            matching_tl: Optional[Trendline] = None
                            if relevant_tls:
                                for tl in relevant_tls:
                                    tl_price = tl.p1_price + tl.slope * (i - tl.p1_index)
                                    tl_tolerance = max(tl_price * 0.0003, atr_val * 0.05)
                                    if c.close > (tl_price + tl_tolerance):
                                        tl_broken = True
                                        matching_tl = tl
                                        break
                                    else:
                                        tl_broken = False

                            breakout_tl = matching_tl
                            breakout_ema = ema_20
                            breakout_vol = rel_vol

                            if ema_broken and tl_broken:
                                is_high_confluence = True
                    else:
                        # Subsequent candle evaluation:
                        # 1. Target 2 reached (terminal winner)
                        if c.high >= target_analysis.target_2:
                            is_target_2_hit = True
                            outcome_ts = c.timestamp
                            break
                        # 2. Target 1 reached
                        elif c.high >= target_analysis.measured_target:
                            is_target_1_hit = True
                            outcome_ts = c.timestamp
                        # 3. Stop Loss breach (only if Target 1 not reached)
                        elif not is_target_1_hit and (c.low <= target_analysis.invalidation_level or c.close <= target_analysis.invalidation_level):
                            is_invalidated = True
                            outcome_ts = c.timestamp
                            break

                # Quality Score
                q_score, q_breakdown = cls.calculate_wm_quality_score(
                    pattern_type="W",
                    s1=l1,
                    neckline_swing=mid_peak,
                    s2=l2,
                    neckline_price=neckline,
                    breakout_candle=candles[structural_break_idx] if structural_break_idx is not None else None,
                    tl=breakout_tl,
                    ema_20=breakout_ema,
                    atr_val=atr_val,
                    rel_vol=breakout_vol,
                    tl_broken=tl_broken,
                    ema_broken=ema_broken
                )

                min_quality_score = getattr(settings, "MIN_WM_QUALITY_SCORE", 70)
                min_rr = getattr(settings, "MIN_WM_RR", 0.85)

                actual_rr = target_analysis.risk_reward_ratio
                if structural_break_close is not None and target_analysis.invalidation_level is not None:
                    actual_risk = max(0.0001, structural_break_close - target_analysis.invalidation_level)
                    actual_reward = max(0.0, target_analysis.measured_target - structural_break_close)
                    actual_rr = round(actual_reward / actual_risk, 2)
                    target_analysis.risk_reward_ratio = actual_rr

                # Decoupled Entry Status and Trade Quality Classification
                if already_moved_too_far:
                    entry_status_val = "OVEREXTENDED"
                elif actual_rr is not None and actual_rr < min_rr:
                    entry_status_val = "POOR_RR"
                else:
                    entry_status_val = "VALID"

                if q_score >= 85:
                    trade_quality_val = "HIGH"
                elif q_score >= 70:
                    trade_quality_val = "MEDIUM"
                else:
                    trade_quality_val = "LOW"

                target_analysis.pattern_quality_score = q_score
                target_analysis.quality_breakdown = q_breakdown
                target_analysis.reversal_score = q_breakdown.get("reversal", 40)
                target_analysis.trendline_score = q_breakdown.get("trendline", 0)
                target_analysis.ema_score = q_breakdown.get("ema", 0)
                target_analysis.reversal_points = q_breakdown.get("reversal", 40)
                target_analysis.trendline_points = q_breakdown.get("trendline", 0)
                target_analysis.ema_points = q_breakdown.get("ema", 0)

                if is_target_2_hit:
                    pat_status = "TARGET_2_HIT"
                    brk_status_val = "CONFIRMED"
                elif is_target_1_hit:
                    pat_status = "TARGET_1_HIT"
                    brk_status_val = "CONFIRMED"
                elif is_invalidated:
                    pat_status = "INVALIDATED"
                    brk_status_val = "CONFIRMED"
                elif structural_break_idx is not None:
                    if is_high_confluence and q_score >= min_quality_score:
                        pat_status = "HIGH_CONFLUENCE_CONFIRMED"
                    else:
                        pat_status = "BREAKOUT_CONFIRMED"
                    brk_status_val = "CONFIRMED"
                elif is_forming:
                    pat_status = "BREAKOUT_FORMING"
                    brk_status_val = "PENDING"
                else:
                    pat_status = "FORMING"
                    brk_status_val = "PENDING"

                w_pattern_obj = WMPatternStructure(
                    pattern_id=pattern_id,
                    pattern_type="W",
                    status=pat_status,
                    s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                    neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                    s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                    pattern_height=round(target_analysis.pattern_height, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                    bar_separation=bar_sep, quality_score=q_score,
                    reversal_score=q_breakdown.get("reversal", 40),
                    trendline_score=q_breakdown.get("trendline", 0),
                    ema_score=q_breakdown.get("ema", 0),
                    reversal_points=q_breakdown.get("reversal", 40),
                    trendline_points=q_breakdown.get("trendline", 0),
                    ema_points=q_breakdown.get("ema", 0),
                    breakout_candle_index=structural_break_idx,
                    breakout_candle_time=structural_break_time,
                    breakout_close=round(structural_break_close, 2) if structural_break_close else None,
                    target_analysis=target_analysis,
                    is_active=False,
                    prev_swing_sl_price=round(w_sl_val, 2),
                    prev_swing_sl_time=w_sl_time,
                    symbol=symbol,
                    timeframe=timeframe,
                    target_1=round(target_analysis.measured_target, 2),
                    target_2=round(target_analysis.target_2, 2) if target_analysis.target_2 else None,
                    stop_loss=round(target_analysis.invalidation_level, 2),
                    risk_reward_ratio=actual_rr,
                    trade_quality=trade_quality_val,
                    entry_status=entry_status_val,
                    breakout_status=brk_status_val,
                    outcome_timestamp=outcome_ts if (is_target_2_hit or is_target_1_hit or is_invalidated) else None,
                    preceding_regime="BEARISH",
                    net_displacement=round(max((h.price for h in swings if h.is_high and h.index < l1.index), default=l1.price + 0.80 * atr_val) - l1.price, 2),
                    primary_leg_amplitude=round(max(leg1_amp, leg2_amp), 2),
                    retest_leg_amplitude=round(min(leg1_amp, leg2_amp), 2),
                    s1_s2_difference=round(diff_price, 2),
                    allowed_symmetry=round(max_allowed_diff, 2),
                    allowed_sweep=round(max_w_overshoot, 2),
                    reaction_zone_strength=float(len(clustered_inter_highs)),
                    intermediate_wave_count=len(inter_lows),
                    multi_wave_rejected=False,
                    continuation_rejected=False
                )

                w_struct_key = ("W", l1.timestamp, mid_peak.timestamp)
                if structural_break_idx is not None:
                    if w_struct_key in confirmed_structural_keys or pattern_id in confirmed_pattern_ids:
                        debug_candidates.append(w_pattern_obj)
                        continue
                    confirmed_structural_keys.add(w_struct_key)
                    confirmed_pattern_ids.add(pattern_id)
                    confirmed_w_l1_timestamps.add(l1.timestamp)
                    confirmed_patterns.append(w_pattern_obj)
                elif is_target_1_hit or is_target_2_hit or is_invalidated:
                    confirmed_patterns.append(w_pattern_obj)
                debug_candidates.append(w_pattern_obj)

                if structural_break_idx is not None:
                    is_high_conf_alert = (is_high_confluence and q_score >= min_quality_score)
                    event_type = (
                        "W_PATTERN_TRENDLINE_EMA_UP_BREAKOUT"
                        if is_high_conf_alert
                        else "W_PATTERN_BREAKOUT"
                    )
                    event_id = f"{symbol}_{timeframe}_{event_type}_{structural_break_time}_{round(neckline, 1)}"
                    
                    events.append(StructureBreakEvent(
                        id=event_id,
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=structural_break_time,
                        event_type=event_type,
                        direction="BULLISH",
                        broken_level=round(neckline, 2),
                        break_price=round(structural_break_close, 2),
                        break_candle_index=structural_break_idx,
                        volume_confirmed=True if breakout_vol >= 1.15 else False,
                        atr_at_break=round(atr_val, 2),
                        htf_alignment="BULLISH",
                        evidence_score=q_score,
                        pattern_quality_score=q_score,
                        pattern_id=pattern_id,
                        pattern_type="W",
                        pattern_formed_time=l2.timestamp,
                        first_swing_price=round(l1.price, 2),
                        first_swing_time=l1.timestamp,
                        second_swing_price=round(l2.price, 2),
                        second_swing_time=l2.timestamp,
                        neckline_price=round(neckline, 2),
                        neckline_time=mid_peak.timestamp,
                        breakout_candle_open=round(candles[structural_break_idx].open, 2),
                        breakout_candle_high=round(candles[structural_break_idx].high, 2),
                        breakout_candle_low=round(candles[structural_break_idx].low, 2),
                        breakout_candle_close=round(structural_break_close, 2),
                        trendline_level=round(breakout_tl.p1_price + breakout_tl.slope * (structural_break_idx - breakout_tl.p1_index), 2) if breakout_tl else round(neckline, 2),
                        ema20_level=round(breakout_ema, 2) if breakout_ema else round(neckline, 2),
                        volume_ratio=round(breakout_vol, 2),
                        target_analysis=target_analysis,
                        notes=f"🟢 {'W + TL + EMA + VOL ↑' if is_high_conf_alert else 'W BREAKOUT ↑'}: L1 {l1.price:.2f} -> Neckline {neckline:.2f} -> L2 {l2.price:.2f} | Breakout Close: {structural_break_close:.2f} at {structural_break_time} | Target: {target_analysis.measured_target:.2f}"
                    ))

        # -------------------------------------------------------------
        # 2.5 FAST 5M INTRADAY REVERSAL EVALUATOR (Zero-Lookahead Fast Path)
        # -------------------------------------------------------------
        if tf_clean in ["5M", "1M", "3M"]:
            # Evaluate Fast W Reversals
            for l1 in low_swings:
                if l1.timestamp in confirmed_w_l1_timestamps:
                    continue
                is_valid_trend, _ = cls._validate_reversal_context(
                    candles=candles, swings=swings, point_1=l1, pattern_type="W", atr_val=atr_val, timeframe=timeframe, df_indicators=df_indicators
                )
                if not is_valid_trend:
                    continue
                
                l1_date = l1.timestamp.split("T")[0] if "T" in str(l1.timestamp) else str(l1.timestamp)[:10]
                w_fast_confirmed_for_l1 = False
                for idx_c in range(l1.index + 2, min(l1.index + 12, len(candles))):
                    if w_fast_confirmed_for_l1:
                        break
                    c_neck = candles[idx_c]
                    neck_date = c_neck.timestamp.split("T")[0] if "T" in str(c_neck.timestamp) else str(c_neck.timestamp)[:10]
                    if neck_date != l1_date:
                        break
                    
                    pat_id = f"{symbol}_{timeframe}_W_FAST_{l1.timestamp}_{c_neck.timestamp}"
                    fast_w_struct_key = ("W", l1.timestamp, c_neck.timestamp)
                    if fast_w_struct_key in confirmed_structural_keys or pat_id in confirmed_pattern_ids:
                        continue

                    if c_neck.high >= l1.price + 0.80 * atr_val:
                        for idx_l2 in range(idx_c + 1, min(idx_c + 8, len(candles))):
                            if w_fast_confirmed_for_l1:
                                break
                            if idx_l2 - l1.index < 4:
                                continue
                            c_l2 = candles[idx_l2]
                            l2_date = c_l2.timestamp.split("T")[0] if "T" in str(c_l2.timestamp) else str(c_l2.timestamp)[:10]
                            if l2_date != l1_date:
                                break
                            
                            # Symmetry and genuine double bottom pullback guard:
                            pat_height_cand = c_neck.high - l1.price
                            max_l2_sym = min(1.50 * atr_val, max(1.10 * atr_val, 0.35 * pat_height_cand))
                            max_l2_overshoot = min(1.0 * atr_val, max(0.75 * atr_val, 0.25 * pat_height_cand))
                            is_valid_l2 = (
                                c_l2.low >= l1.price - max_l2_overshoot and
                                c_l2.low <= l1.price + max_l2_sym and
                                c_l2.low <= c_neck.high - 0.30 * pat_height_cand
                            )
                            if is_valid_l2:
                                for idx_brk in range(idx_l2 + 1, min(idx_l2 + 8, len(candles))):
                                    if idx_brk == len(candles) - 1:
                                        continue
                                    c_brk = candles[idx_brk]
                                    brk_date = c_brk.timestamp.split("T")[0] if "T" in str(c_brk.timestamp) else str(c_brk.timestamp)[:10]
                                    if brk_date != l1_date:
                                        break
                                    
                                    if c_brk.close > c_neck.high:
                                        if fast_w_struct_key in confirmed_structural_keys or pat_id in confirmed_pattern_ids or l1.timestamp in confirmed_w_l1_timestamps:
                                            break
                                        if any(p.breakout_candle_time == c_brk.timestamp and p.pattern_type == "W" for p in confirmed_patterns):
                                            break
                                        
                                        fast_height = c_neck.high - min(l1.price, c_l2.low)
                                        primary_leg_fast = c_neck.high - l1.price
                                        retest_leg_fast = c_neck.high - c_l2.low
                                        min_primary_amp = 0.60 * atr_val
                                        min_retest_amp = max(0.30 * atr_val, 0.20 * fast_height)
                                        if fast_height < 0.70 * atr_val or primary_leg_fast < min_primary_amp or retest_leg_fast < min_retest_amp:
                                            break
                                        
                                        sl_val = round(c_l2.low - (0.15 * atr_val), 2)
                                        w_origin, _ = cls.extract_preceding_trend_origin(candles, swings, point_1=l1, pattern_type="W", timeframe=timeframe)
                                        if w_origin is not None and w_origin > c_neck.high:
                                            t1_val = round(w_origin, 2)
                                        else:
                                            t1_val = round(c_neck.high + fast_height, 2)
                                        t2_val = round(c_neck.high + (1.618 * fast_height), 2)
                                        risk_val = max(0.0001, c_brk.close - sl_val)
                                        reward_val = max(0.0, t1_val - c_brk.close)
                                        rr_val = reward_val / risk_val
                                        
                                        q_score = 70
                                        if c_brk.close >= c_neck.high + 0.1 * atr_val: q_score += 15
                                        if rr_val >= 1.5: q_score += 15

                                        max_extension_ratio = getattr(settings, "MAX_BREAKOUT_EXTENSION_DEPTH_RATIO", 0.75)
                                        if c_brk.close >= c_neck.high + max_extension_ratio * fast_height:
                                            entry_status_val = "OVEREXTENDED"
                                        elif rr_val < 0.85:
                                            entry_status_val = "POOR_RR"
                                        else:
                                            entry_status_val = "VALID"

                                        trade_quality_val = "HIGH" if q_score >= 85 else ("MEDIUM" if q_score >= 70 else "LOW")
                                        
                                        pat_id = f"{symbol}_{timeframe}_W_FAST_{l1.timestamp}_{c_neck.timestamp}"
                                        fast_pat = WMPatternStructure(
                                            pattern_id=pat_id,
                                            pattern_type="W",
                                            status="BREAKOUT_CONFIRMED",
                                            s1_index=l1.index,
                                            s1_price=round(l1.price, 2),
                                            s1_time=l1.timestamp,
                                            neckline_index=idx_c,
                                            neckline_price=round(c_neck.high, 2),
                                            neckline_time=c_neck.timestamp,
                                            s2_index=idx_l2,
                                            s2_price=round(c_l2.low, 2),
                                            s2_time=c_l2.timestamp,
                                            pattern_height=round(fast_height, 2),
                                            depth_atr=round(fast_height / atr_val, 2),
                                            symmetry_atr=round(abs(l1.price - c_l2.low) / atr_val, 2),
                                            bar_separation=idx_l2 - l1.index,
                                            quality_score=q_score,
                                            breakout_candle_index=idx_brk,
                                            breakout_candle_time=c_brk.timestamp,
                                            breakout_close=round(c_brk.close, 2),
                                            stop_loss=sl_val,
                                            target_1=t1_val,
                                            target_2=t2_val,
                                            risk_reward_ratio=round(rr_val, 2),
                                            trade_quality=trade_quality_val,
                                            entry_status=entry_status_val,
                                            breakout_status="CONFIRMED",
                                            symbol=symbol,
                                            timeframe=timeframe,
                                            preceding_regime="BEARISH",
                                            primary_leg_amplitude=round(primary_leg_fast, 2),
                                            retest_leg_amplitude=round(retest_leg_fast, 2),
                                            s1_s2_difference=round(abs(l1.price - c_l2.low), 2),
                                            allowed_symmetry=round(max_l2_sym, 2),
                                            allowed_sweep=round(max_l2_overshoot, 2),
                                            multi_wave_rejected=False,
                                            continuation_rejected=False
                                        )
                                        confirmed_patterns.append(fast_pat)
                                        debug_candidates.append(fast_pat)
                                        
                                        target_analysis = cls.calculate_pattern_targets(
                                            pattern_type="W",
                                            s1_price=l1.price,
                                            s2_price=c_l2.low,
                                            neckline_price=c_neck.high,
                                            breakout_close=c_brk.close,
                                            prev_swing_sl=sl_val,
                                            key_supports=key_supports,
                                            key_resistances=key_resistances,
                                            atr_val=atr_val,
                                            sl_atr_buffer=0.15,
                                            reversal_target=w_origin
                                        )
                                        fast_pat.target_analysis = target_analysis
                                        fast_pat.target_1 = round(target_analysis.measured_target, 2)
                                        fast_pat.target_2 = round(target_analysis.target_2, 2) if target_analysis.target_2 else None
                                        fast_pat.stop_loss = round(target_analysis.invalidation_level, 2)
                                        if target_analysis.risk_reward_ratio is not None:
                                            fast_pat.risk_reward_ratio = round(target_analysis.risk_reward_ratio, 2)
                                        
                                        events.append(StructureBreakEvent(
                                            id=f"{symbol}_{timeframe}_W_PATTERN_BREAKOUT_{c_brk.timestamp}_{round(c_neck.high, 1)}",
                                            symbol=symbol,
                                            timeframe=timeframe,
                                            timestamp=c_brk.timestamp,
                                            event_type="W_PATTERN_BREAKOUT",
                                            direction="BULLISH",
                                            broken_level=round(c_neck.high, 2),
                                            break_price=round(c_brk.close, 2),
                                            break_candle_index=idx_brk,
                                            volume_confirmed=False,
                                            atr_at_break=round(atr_val, 2),
                                            htf_alignment="BULLISH",
                                            evidence_score=q_score,
                                            pattern_quality_score=q_score,
                                            pattern_id=pat_id,
                                            pattern_type="W",
                                            pattern_formed_time=c_l2.timestamp,
                                            first_swing_price=round(l1.price, 2),
                                            first_swing_time=l1.timestamp,
                                            second_swing_price=round(c_l2.low, 2),
                                            second_swing_time=c_l2.timestamp,
                                            neckline_price=round(c_neck.high, 2),
                                            neckline_time=c_neck.timestamp,
                                            breakout_candle_open=round(candles[idx_brk].open, 2),
                                            breakout_candle_high=round(candles[idx_brk].high, 2),
                                            breakout_candle_low=round(candles[idx_brk].low, 2),
                                            breakout_candle_close=round(c_brk.close, 2),
                                            trendline_level=round(c_neck.high, 2),
                                            ema20_level=round(c_neck.high, 2),
                                            volume_ratio=1.0,
                                            target_analysis=target_analysis,
                                            notes=f"🟢 W FAST BREAKOUT ↑: L1 {l1.price:.2f} -> Neckline {c_neck.high:.2f} -> L2 {c_l2.low:.2f} | Breakout Close: {c_brk.close:.2f} at {c_brk.timestamp}"
                                        ))
                                        confirmed_structural_keys.add(fast_w_struct_key)
                                        confirmed_pattern_ids.add(pat_id)
                                        confirmed_w_l1_timestamps.add(l1.timestamp)
                                        w_fast_confirmed_for_l1 = True
                                        break

            # Evaluate Fast M Reversals
            for h1 in high_swings:
                if h1.timestamp in confirmed_m_h1_timestamps:
                    continue
                is_valid_trend, _ = cls._validate_reversal_context(
                    candles=candles, swings=swings, point_1=h1, pattern_type="M", atr_val=atr_val, timeframe=timeframe, df_indicators=df_indicators
                )
                if not is_valid_trend:
                    continue
                
                h1_date = h1.timestamp.split("T")[0] if "T" in str(h1.timestamp) else str(h1.timestamp)[:10]
                m_fast_confirmed_for_h1 = False
                for idx_c in range(h1.index + 2, min(h1.index + 12, len(candles))):
                    if m_fast_confirmed_for_h1:
                        break
                    c_neck = candles[idx_c]
                    neck_date = c_neck.timestamp.split("T")[0] if "T" in str(c_neck.timestamp) else str(c_neck.timestamp)[:10]
                    if neck_date != h1_date:
                        break

                    pat_id = f"{symbol}_{timeframe}_M_FAST_{h1.timestamp}_{c_neck.timestamp}"
                    fast_m_struct_key = ("M", h1.timestamp, c_neck.timestamp)
                    if fast_m_struct_key in confirmed_structural_keys or pat_id in confirmed_pattern_ids:
                        continue

                    if c_neck.low <= h1.price - 0.80 * atr_val:
                        for idx_h2 in range(idx_c + 1, min(idx_c + 8, len(candles))):
                            if m_fast_confirmed_for_h1:
                                break
                            if idx_h2 - h1.index < 4:
                                continue
                            c_h2 = candles[idx_h2]
                            l2_date = c_h2.timestamp.split("T")[0] if "T" in str(c_h2.timestamp) else str(c_h2.timestamp)[:10]
                            if l2_date != h1_date:
                                break
                            
                            # Symmetry and genuine double top bounce guard:
                            pat_height_cand = h1.price - c_neck.low
                            max_h2_sym = min(1.50 * atr_val, max(1.10 * atr_val, 0.35 * pat_height_cand))
                            max_h2_overshoot = min(1.0 * atr_val, max(0.75 * atr_val, 0.25 * pat_height_cand))
                            is_valid_h2 = (
                                c_h2.high <= h1.price + max_h2_overshoot and
                                c_h2.high >= h1.price - max_h2_sym and
                                c_h2.high >= c_neck.low + 0.30 * pat_height_cand
                            )
                            if is_valid_h2:
                                for idx_brk in range(idx_h2 + 1, min(idx_h2 + 8, len(candles))):
                                    if idx_brk == len(candles) - 1:
                                        continue
                                    c_brk = candles[idx_brk]
                                    brk_date = c_brk.timestamp.split("T")[0] if "T" in str(c_brk.timestamp) else str(c_brk.timestamp)[:10]
                                    if brk_date != h1_date:
                                        break
                                    
                                    if c_brk.close < c_neck.low:
                                        if fast_m_struct_key in confirmed_structural_keys or pat_id in confirmed_pattern_ids or h1.timestamp in confirmed_m_h1_timestamps:
                                            break
                                        if any(p.breakout_candle_time == c_brk.timestamp and p.pattern_type == "M" for p in confirmed_patterns):
                                            break
                                        
                                        fast_height = max(h1.price, c_h2.high) - c_neck.low
                                        primary_leg_fast = h1.price - c_neck.low
                                        retest_leg_fast = c_h2.high - c_neck.low
                                        min_primary_amp = 0.60 * atr_val
                                        min_retest_amp = max(0.30 * atr_val, 0.20 * fast_height)
                                        if fast_height < 0.70 * atr_val or primary_leg_fast < min_primary_amp or retest_leg_fast < min_retest_amp:
                                            break
                                        
                                        sl_val = round(c_h2.high + (0.15 * atr_val), 2)
                                        m_origin, _ = cls.extract_preceding_trend_origin(candles, swings, point_1=h1, pattern_type="M", timeframe=timeframe)
                                        if m_origin is not None and m_origin < c_neck.low:
                                            t1_val = round(m_origin, 2)
                                        else:
                                            t1_val = round(c_neck.low - fast_height, 2)
                                        t2_val = round(c_neck.low - (1.618 * fast_height), 2)
                                        risk_val = max(0.0001, sl_val - c_brk.close)
                                        reward_val = max(0.0, c_brk.close - t1_val)
                                        rr_val = reward_val / risk_val
                                        
                                        q_score = 70
                                        if c_brk.close <= c_neck.low - 0.1 * atr_val: q_score += 15
                                        if rr_val >= 1.5: q_score += 15

                                        max_extension_ratio = getattr(settings, "MAX_BREAKOUT_EXTENSION_DEPTH_RATIO", 0.75)
                                        if c_brk.close <= c_neck.low - max_extension_ratio * fast_height:
                                            entry_status_val = "OVEREXTENDED"
                                        elif rr_val < 0.85:
                                            entry_status_val = "POOR_RR"
                                        else:
                                            entry_status_val = "VALID"

                                        trade_quality_val = "HIGH" if q_score >= 85 else ("MEDIUM" if q_score >= 70 else "LOW")
                                        
                                        pat_id = f"{symbol}_{timeframe}_M_FAST_{h1.timestamp}_{c_neck.timestamp}"
                                        fast_pat = WMPatternStructure(
                                            pattern_id=pat_id,
                                            pattern_type="M",
                                            status="BREAKOUT_CONFIRMED",
                                            s1_index=h1.index,
                                            s1_price=round(h1.price, 2),
                                            s1_time=h1.timestamp,
                                            neckline_index=idx_c,
                                            neckline_price=round(c_neck.low, 2),
                                            neckline_time=c_neck.timestamp,
                                            s2_index=idx_h2,
                                            s2_price=round(c_h2.high, 2),
                                            s2_time=c_h2.timestamp,
                                            pattern_height=round(fast_height, 2),
                                            depth_atr=round(fast_height / atr_val, 2),
                                            symmetry_atr=round(abs(h1.price - c_h2.high) / atr_val, 2),
                                            bar_separation=idx_h2 - h1.index,
                                            quality_score=q_score,
                                            breakout_candle_index=idx_brk,
                                            breakout_candle_time=c_brk.timestamp,
                                            breakout_close=round(c_brk.close, 2),
                                            stop_loss=sl_val,
                                            target_1=t1_val,
                                            target_2=t2_val,
                                            risk_reward_ratio=round(rr_val, 2),
                                            trade_quality=trade_quality_val,
                                            entry_status=entry_status_val,
                                            breakout_status="CONFIRMED",
                                            symbol=symbol,
                                            timeframe=timeframe,
                                            preceding_regime="BULLISH",
                                            primary_leg_amplitude=round(primary_leg_fast, 2),
                                            retest_leg_amplitude=round(retest_leg_fast, 2),
                                            s1_s2_difference=round(abs(h1.price - c_h2.high), 2),
                                            allowed_symmetry=round(max_h2_sym, 2),
                                            allowed_sweep=round(max_h2_overshoot, 2),
                                            multi_wave_rejected=False,
                                            continuation_rejected=False
                                        )
                                        confirmed_patterns.append(fast_pat)
                                        debug_candidates.append(fast_pat)
                                        
                                        target_analysis = cls.calculate_pattern_targets(
                                            pattern_type="M",
                                            s1_price=h1.price,
                                            s2_price=c_h2.high,
                                            neckline_price=c_neck.low,
                                            breakout_close=c_brk.close,
                                            prev_swing_sl=sl_val,
                                            key_supports=key_supports,
                                            key_resistances=key_resistances,
                                            atr_val=atr_val,
                                            sl_atr_buffer=0.15,
                                            reversal_target=m_origin
                                        )
                                        fast_pat.target_analysis = target_analysis
                                        fast_pat.target_1 = round(target_analysis.measured_target, 2)
                                        fast_pat.target_2 = round(target_analysis.target_2, 2) if target_analysis.target_2 else None
                                        fast_pat.stop_loss = round(target_analysis.invalidation_level, 2)
                                        if target_analysis.risk_reward_ratio is not None:
                                            fast_pat.risk_reward_ratio = round(target_analysis.risk_reward_ratio, 2)
                                        
                                        events.append(StructureBreakEvent(
                                            id=f"{symbol}_{timeframe}_M_PATTERN_BREAKOUT_{c_brk.timestamp}_{round(c_neck.low, 1)}",
                                            symbol=symbol,
                                            timeframe=timeframe,
                                            timestamp=c_brk.timestamp,
                                            event_type="M_PATTERN_BREAKOUT",
                                            direction="BEARISH",
                                            broken_level=round(c_neck.low, 2),
                                            break_price=round(c_brk.close, 2),
                                            break_candle_index=idx_brk,
                                            volume_confirmed=False,
                                            atr_at_break=round(atr_val, 2),
                                            htf_alignment="BEARISH",
                                            evidence_score=q_score,
                                            pattern_quality_score=q_score,
                                            pattern_id=pat_id,
                                            pattern_type="M",
                                            pattern_formed_time=c_h2.timestamp,
                                            first_swing_price=round(h1.price, 2),
                                            first_swing_time=h1.timestamp,
                                            second_swing_price=round(c_h2.high, 2),
                                            second_swing_time=c_h2.timestamp,
                                            neckline_price=round(c_neck.low, 2),
                                            neckline_time=c_neck.timestamp,
                                            breakout_candle_open=round(candles[idx_brk].open, 2),
                                            breakout_candle_high=round(candles[idx_brk].high, 2),
                                            breakout_candle_low=round(candles[idx_brk].low, 2),
                                            breakout_candle_close=round(c_brk.close, 2),
                                            trendline_level=round(c_neck.low, 2),
                                            ema20_level=round(c_neck.low, 2),
                                            volume_ratio=1.0,
                                            target_analysis=target_analysis,
                                            notes=f"🔴 M FAST BREAKOUT ↓: H1 {h1.price:.2f} -> Neckline {c_neck.low:.2f} -> H2 {c_h2.high:.2f} | Breakout Close: {c_brk.close:.2f} at {c_brk.timestamp}"
                                        ))
                                        confirmed_structural_keys.add(fast_m_struct_key)
                                        confirmed_pattern_ids.add(pat_id)
                                        confirmed_m_h1_timestamps.add(h1.timestamp)
                                        m_fast_confirmed_for_h1 = True
                                        break

        # -------------------------------------------------------------
        # 3. SELECT SINGLE ACTIVE PATTERN (Removes Chart Clutter)
        # -------------------------------------------------------------
        # 1. Structural Deduplication: group confirmed patterns by structural pattern identity
        # (pattern_type, s1_time, neckline_time), strictly preserving the EARLIEST breakout candle index
        # (first qualifying completed candle) so that subsequent candles can never overwrite the original breakout.
        structural_best_patterns: Dict[Tuple[str, str, str], WMPatternStructure] = {}
        for p in confirmed_patterns:
            s_key = (p.pattern_type, p.s1_time or "", p.neckline_time or "")
            if s_key not in structural_best_patterns:
                structural_best_patterns[s_key] = p
            else:
                existing = structural_best_patterns[s_key]
                ex_idx = existing.breakout_candle_index if existing.breakout_candle_index is not None else 999999
                new_idx = p.breakout_candle_index if p.breakout_candle_index is not None else 999999
                if new_idx < ex_idx:
                    structural_best_patterns[s_key] = p
                elif new_idx == ex_idx:
                    ex_is_fast = 0 if "_FAST_" in existing.pattern_id else 1
                    new_is_fast = 0 if "_FAST_" in p.pattern_id else 1
                    if (new_is_fast, p.quality_score) > (ex_is_fast, existing.quality_score):
                        structural_best_patterns[s_key] = p

        confirmed_patterns = list(structural_best_patterns.values())

        # 2. Structural Deduplication for events: ensure only the earliest break event per structure is retained
        structural_best_events: Dict[Tuple[str, str, str], StructureBreakEvent] = {}
        for e in events:
            e_key = (e.pattern_type or "", e.first_swing_time or "", e.neckline_time or "")
            if e_key not in structural_best_events:
                structural_best_events[e_key] = e
            else:
                existing_e = structural_best_events[e_key]
                ex_e_idx = existing_e.break_candle_index if existing_e.break_candle_index is not None else 999999
                new_e_idx = e.break_candle_index if e.break_candle_index is not None else 999999
                if new_e_idx < ex_e_idx:
                    structural_best_events[e_key] = e
                elif new_e_idx == ex_e_idx:
                    if (e.evidence_score or 0) > (existing_e.evidence_score or 0):
                        structural_best_events[e_key] = e
        events = list(structural_best_events.values())

        active_pattern: Optional[WMPatternStructure] = None
        # Sort patterns: macro swing patterns take priority over fast patterns, then by breakout index and quality score
        confirmed_patterns.sort(
            key=lambda p: (
                0 if "_FAST_" in p.pattern_id else 1,
                p.breakout_candle_index or p.s2_index,
                p.quality_score
            ),
            reverse=True
        )

        # Deduplicate confirmed patterns sharing identical breakout candle and pattern type, keeping highest structural quality
        unique_confirmed: List[WMPatternStructure] = []
        seen_breaks = set()
        for p in confirmed_patterns:
            key = (p.pattern_type, p.breakout_candle_index)
            if key not in seen_breaks:
                seen_breaks.add(key)
                unique_confirmed.append(p)
        confirmed_patterns = unique_confirmed

        if confirmed_patterns:
            active_pattern = confirmed_patterns[0]
            active_pattern.is_active = True
        else:
            forming_cand = next((c for c in debug_candidates if c.status in ["BREAKOUT_FORMING", "BREAKDOWN_FORMING", "FORMING", "PENDING_BREAKOUT"]), None)
            if forming_cand:
                active_pattern = forming_cand
                active_pattern.is_active = True

        return events, confirmed_patterns, active_pattern, debug_candidates

    @classmethod
    def detect_wm_pattern_trendline_ema_breakouts(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        trendlines: List[Trendline],
        df_indicators: Optional[pd.DataFrame],
        symbol: str,
        timeframe: str,
        atr_val: float,
        price_tolerance_atr: float = 1.50,
        min_depth_atr: float = 0.80,
        min_bar_spacing: int = 5,
        min_breakout_dist_atr: float = 0.05,
        key_supports: List[float] = [],
        key_resistances: List[float] = []
    ) -> List[StructureBreakEvent]:
        """
        Backward-compatible wrapper for high-confluence breakout alerts.
        Filters for high-confluence events (Trendline + 20 EMA + Volume + Score >= 75).
        """
        events, _, _, _ = cls.detect_wm_patterns(
            candles=candles,
            swings=swings,
            trendlines=trendlines,
            df_indicators=df_indicators,
            symbol=symbol,
            timeframe=timeframe,
            atr_val=atr_val,
            price_tolerance_atr=price_tolerance_atr,
            min_depth_atr=min_depth_atr,
            min_bar_spacing=min_bar_spacing,
            min_breakout_dist_atr=min_breakout_dist_atr,
            key_supports=key_supports,
            key_resistances=key_resistances
        )
        return [e for e in events if "TRENDLINE_EMA" in e.event_type]
