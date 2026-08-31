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
        has_reversal: bool = True
    ) -> Tuple[int, Dict[str, int]]:
        """
        Calculates dedicated W/M Pattern Quality Score (0 to 100 points maximum).
        
        Strict Standardized Rubric (Max 100/100):
        - Reversal condition: 40 points (confirmed W/M structural reversal geometry)
        - Trendline breakout condition: 30 points (breakout close confirms trendline break)
        - EMA breakout condition: 30 points (breakout close confirms 20 EMA break)
        Total = 40 + 30 + 30 = 100/100 max.
        """
        reversal_pts = 40 if has_reversal else 0

        # Trendline breakout (30 pts)
        if tl_broken is not None:
            tl_pts = 30 if tl_broken else 0
        elif tl is not None and breakout_candle is not None:
            tl_p1_idx = getattr(tl, "p1_index", 0)
            tl_p1_price = getattr(tl, "p1_price", 0.0)
            tl_slope = getattr(tl, "slope", 0.0)
            bc_idx = getattr(breakout_candle, "index", tl_p1_idx)
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
        target_extension: Optional[float] = None
    ) -> PatternTargetAnalysis:
        """
        Calculates objective technical measured-move targets, intermediate obstacles, and invalidation levels.
        Stop Loss is strictly independent of the neckline (behind Point 2 / second swing with ATR buffer).
        W: SL = Low 2 - ATR_buffer (strictly < neckline)
        M: SL = High 2 + ATR_buffer (strictly > neckline)
        """
        buffer_atr = sl_atr_buffer if sl_atr_buffer is not None else getattr(settings, "W_M_SL_ATR_BUFFER", 0.15)
        extension = target_extension if target_extension is not None else getattr(settings, "W_M_TARGET_2_EXTENSION", 1.618)

        if pattern_type == "W":
            pattern_low = min(s1_price, s2_price)
            w_height = round(neckline_price - pattern_low, 2)
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
                f"The measured target 1 is ₹{measured_target:,.2f}, Target 2 is ₹{target_2:,.2f}"
                + (f", subject to intervening resistance at ₹{nearest_obstacle:,.2f}." if nearest_obstacle else ".")
            )

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
                interpretation=interp
            )

        else:  # M Pattern
            pattern_high = max(s1_price, s2_price)
            m_height = round(pattern_high - neckline_price, 2)
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
                f"The measured target is a technical projection (₹{measured_target:,.2f})"
                + (f" and may encounter support before reaching it at ₹{nearest_obstacle:,.2f}." if nearest_obstacle else ".")
            )

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

                if i < tl.p2_index:
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
    def _validate_preceding_trend(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        point_1: SwingPoint,
        pattern_type: str,
        atr_val: float,
        timeframe: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Validates that a meaningful directional impulse/trend preceded Point 1.
        W: Prior move must be a meaningful decline into Low 1.
        M: Prior move must be a meaningful advance into High 1.
        Displacement requirement: max(2.0 * ATR, point_1.price * pct_floor) scaled by timeframe.
        Rejects sideways/consolidating structures prior to Point 1.
        """
        tf_clean = (timeframe or "1H").upper()
        tf_multipliers = {
            "5M": 0.002,   # 0.20% minimum displacement floor for 5M intraday
            "15M": 0.004,  # 0.40% minimum displacement floor for 15M
            "1H": 0.008,   # 0.80% minimum displacement floor for 1H
            "4H": 0.012    # 1.20% minimum displacement floor for 4H/Daily
        }
        pct = tf_multipliers.get(tf_clean, 0.008)
        min_disp = max(2.0 * atr_val, point_1.price * pct)

        if pattern_type == "W":
            prior_highs = [s for s in swings if s.is_high and s.index < point_1.index]
            if prior_highs:
                recent_highs = [h for h in prior_highs if (point_1.index - h.index) <= 60]
                origin_high = max(recent_highs if recent_highs else prior_highs[-2:], key=lambda h: h.price)
                disp = origin_high.price - point_1.price
                if disp < min_disp:
                    return False, f"Insufficient preceding downward move into Low 1 ({disp:.2f} < {min_disp:.2f})"

                # Sideways consolidation check
                prior_swings = [s for s in swings if origin_high.index <= s.index <= point_1.index]
                if len(prior_swings) >= 4:
                    spread = max(s.price for s in prior_swings) - min(s.price for s in prior_swings)
                    if spread < 1.5 * atr_val:
                        return False, "Preceding market structure is sideways/consolidating"
                return True, "OK"
            else:
                start_idx = max(0, point_1.index - 35)
                pre_candles = candles[start_idx:point_1.index]
                if pre_candles:
                    highest_pre = max(c.high for c in pre_candles)
                    disp = highest_pre - point_1.price
                    if disp < min_disp:
                        return False, f"Insufficient preceding downward move into Low 1 ({disp:.2f} < {min_disp:.2f})"
                    return True, "OK"
                return False, "No preceding move detected before Low 1"

        else:  # M Pattern
            prior_lows = [s for s in swings if not s.is_high and s.index < point_1.index]
            if prior_lows:
                recent_lows = [l for l in prior_lows if (point_1.index - l.index) <= 60]
                origin_low = min(recent_lows if recent_lows else prior_lows[-2:], key=lambda l: l.price)
                disp = point_1.price - origin_low.price
                if disp < min_disp:
                    return False, f"Insufficient preceding upward move into High 1 ({disp:.2f} < {min_disp:.2f})"

                # Sideways consolidation check
                prior_swings = [s for s in swings if origin_low.index <= s.index <= point_1.index]
                if len(prior_swings) >= 4:
                    spread = max(s.price for s in prior_swings) - min(s.price for s in prior_swings)
                    if spread < 1.5 * atr_val:
                        return False, "Preceding market structure is sideways/consolidating"
                return True, "OK"
            else:
                start_idx = max(0, point_1.index - 35)
                pre_candles = candles[start_idx:point_1.index]
                if pre_candles:
                    lowest_pre = min(c.low for c in pre_candles)
                    disp = point_1.price - lowest_pre
                    if disp < min_disp:
                        return False, f"Insufficient preceding upward move into High 1 ({disp:.2f} < {min_disp:.2f})"
                    return True, "OK"
                return False, "No preceding move detected before High 1"

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
        min_bar_spacing: int = 5,
        max_bar_spacing: int = 60,
        min_breakout_dist_atr: float = 0.05,
        key_supports: List[float] = [],
        key_resistances: List[float] = []
    ) -> Tuple[List[StructureBreakEvent], List[WMPatternStructure], Optional[WMPatternStructure], List[WMPatternStructure]]:
        """
        Complete Structural W/M Pattern Engine.
        
        Returns:
        - events: Confirmed high-confluence breakout events (for alerts).
        - confirmed_patterns: List of all confirmed W/M patterns (for history toggle).
        - active_pattern: Single latest active confirmed (or forming) pattern to keep chart clean.
        - debug_candidates: Evaluated candidate formations with rejection diagnostics.
        """
        if len(candles) < 10 or len(swings) < 3:
            return [], [], None, []

        events: List[StructureBreakEvent] = []
        confirmed_patterns: List[WMPatternStructure] = []
        debug_candidates: List[WMPatternStructure] = []
        n = len(candles)
        min_breakout_dist = max(0.0001, min_breakout_dist_atr * atr_val)

        low_swings = [s for s in swings if not s.is_high]
        high_swings = [s for s in swings if s.is_high]

        # -------------------------------------------------------------
        # 1. EVALUATE M PATTERNS (Double Top Reversals)
        # -------------------------------------------------------------
        for idx_h1 in range(len(high_swings) - 1):
            h1 = high_swings[idx_h1]
            for idx_h2 in range(idx_h1 + 1, min(idx_h1 + 4, len(high_swings))):
                h2 = high_swings[idx_h2]
                bar_sep = h2.index - h1.index

                # Horizontal separation filter
                if bar_sep < min_bar_spacing or bar_sep > max_bar_spacing:
                    continue

                # Intermediate trough swing low (Neckline)
                inter_lows = [l for l in low_swings if h1.index < l.index < h2.index]
                if not inter_lows:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=h1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason="No confirmed structural reaction low between High 1 and High 2"
                    ))
                    continue

                # Wave structure check: Structural adjacency rule
                # There must NOT be an intervening swing high between High 1 and High 2
                inter_highs = [h for h in high_swings if h1.index < h.index < h2.index]
                if len(inter_highs) > 0:
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

                # Neckline check: Exactly ONE intermediate structural low (neckline) between High 1 and High 2
                if len(inter_lows) > 1:
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

                # Preceding trend validation leading into High 1 (meaningful upward move)
                is_valid_trend, trend_reason = cls._validate_preceding_trend(
                    candles=candles, swings=swings, point_1=h1, pattern_type="M", atr_val=atr_val, timeframe=timeframe
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

                # Early-wave / 5-wave exhaustion check leading into H1
                prior_highs = [s for s in high_swings if s.index < h1.index]
                if len(prior_highs) >= 3 and (prior_highs[-3].price < prior_highs[-2].price < prior_highs[-1].price < h1.price):
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=h1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason="Pattern formed after extended 5-wave movement (>= 3 consecutive higher highs prior to H1)",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # Point 2 = High 2. SL = High 2 + configurable ATR buffer (strictly > neckline)
                sl_buf = getattr(settings, "W_M_SL_ATR_BUFFER", 0.15)
                m_sl_val = round(h2.price + (sl_buf * atr_val), 2)
                m_sl_time = h2.timestamp

                mid_trough = min(inter_lows, key=lambda l: l.price)
                neckline = mid_trough.price

                # Symmetry & Depth
                diff_price = abs(h1.price - h2.price)
                diff_atr = diff_price / max(0.0001, atr_val)
                pattern_depth = max(h1.price, h2.price) - neckline
                depth_atr = pattern_depth / max(0.0001, atr_val)

                if depth_atr < min_depth_atr:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=45,
                        rejection_reason=f"Insufficient neckline depth ({depth_atr:.2f} ATR < {min_depth_atr:.2f} ATR)",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # Individual leg amplitude requirement: BOTH legs must independently satisfy >= max(1.2 * ATR, h1.price * pct)
                tf_clean_m = (timeframe or "1H").upper()
                leg_pct_map_m = {
                    "5M": 0.001,   # 0.10% on 5M
                    "15M": 0.002,  # 0.20% on 15M
                    "1H": 0.004,   # 0.40% on 1H
                    "4H": 0.008    # 0.80% on 4H/Daily
                }
                min_leg_amp = max(1.2 * atr_val, h1.price * leg_pct_map_m.get(tf_clean_m, 0.004))
                leg1_amp = h1.price - neckline
                leg2_amp = h2.price - neckline

                if leg1_amp < min_leg_amp:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=35,
                        rejection_reason=f"Leg 1 amplitude too small ({leg1_amp:.2f} < {min_leg_amp:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                if leg2_amp < min_leg_amp:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=35,
                        rejection_reason=f"Leg 2 amplitude too small ({leg2_amp:.2f} < {min_leg_amp:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # Tightened symmetry: max(1.2 * ATR, 1.5% of Point 1 price)
                max_allowed_diff = max(1.2 * atr_val, h1.price * 0.015)
                if diff_price > max_allowed_diff:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}",
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=40,
                        rejection_reason=f"Highs too asymmetric ({diff_price:.2f} > {max_allowed_diff:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                pattern_id = f"{symbol}_{timeframe}_M_{h1.timestamp}_{h2.timestamp}"

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
                    sl_atr_buffer=sl_buf
                )

                # Scan for confirmed breakout candle strictly after Point 2 (H2)
                structural_break_idx: Optional[int] = None
                structural_break_time: Optional[str] = None
                structural_break_close: Optional[float] = None
                is_high_confluence = False
                breakout_tl: Optional[Trendline] = None
                breakout_ema: Optional[float] = None
                breakout_vol: float = 1.25
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

                for i in range(h2.index + 1, max_scan_index):
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
                        # Structural Breakdown condition: candle close below neckline (wick-only does NOT count)
                        prev_c = candles[i - 1]
                        if c.close <= (neckline - min_breakout_dist) and prev_c.close >= (neckline - min_breakout_dist * 0.5):
                            # Reject if candle already moved substantially past Target 1 area
                            if c.close <= (neckline - 0.75 * pattern_depth):
                                already_moved_too_far = True
                                break

                            structural_break_idx = i
                            structural_break_time = c.timestamp
                            structural_break_close = c.close

                            ema_20: Optional[float] = None
                            rel_vol: float = 1.25
                            if df_indicators is not None and i < len(df_indicators):
                                row = df_indicators.iloc[i]
                                if "ema_20" in row and not pd.isna(row["ema_20"]):
                                    ema_20 = float(row["ema_20"])
                                if "relative_volume" in row and not pd.isna(row["relative_volume"]):
                                    rel_vol = float(row["relative_volume"])

                            ema_broken = (c.close < ema_20) if ema_20 is not None else True
                            
                            tl_broken = True
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

                            breakout_tl = matching_tl or (relevant_tls[0] if relevant_tls else None)
                            breakout_ema = ema_20
                            breakout_vol = rel_vol

                            # Check High Confluence conditions on this breakout candle
                            if ema_broken and tl_broken and rel_vol >= 1.15:
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

                if already_moved_too_far:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=pattern_id,
                        pattern_type="M",
                        status="REJECTED",
                        s1_index=h1.index, s1_price=round(h1.price, 2), s1_time=h1.timestamp,
                        neckline_index=mid_trough.index, neckline_price=round(neckline, 2), neckline_time=mid_trough.timestamp,
                        s2_index=h2.index, s2_price=round(h2.price, 2), s2_time=h2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason="Breakout candle already moved substantially prior to confirmation (exceeded 75% of pattern depth)",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

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
                elif is_target_1_hit:
                    pat_status = "TARGET_1_HIT"
                elif is_invalidated:
                    pat_status = "INVALIDATED"
                elif structural_break_idx is not None:
                    if is_high_confluence and q_score >= 75:
                        pat_status = "HIGH_CONFLUENCE_CONFIRMED"
                    else:
                        pat_status = "BREAKOUT_CONFIRMED"
                elif is_forming:
                    pat_status = "BREAKDOWN_FORMING"
                else:
                    pat_status = "CONFIRMED"

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
                    outcome_timestamp=outcome_ts if (is_target_2_hit or is_target_1_hit or is_invalidated) else None
                )

                confirmed_patterns.append(m_pattern_obj)
                debug_candidates.append(m_pattern_obj)

                # ALWAYS emit structure break event for the chart upon confirmed candle close!
                if structural_break_idx is not None:
                    is_high_conf_alert = (is_high_confluence and q_score >= 75)
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
            for idx_l2 in range(idx_l1 + 1, min(idx_l1 + 4, len(low_swings))):
                l2 = low_swings[idx_l2]
                bar_sep = l2.index - l1.index

                if bar_sep < min_bar_spacing or bar_sep > max_bar_spacing:
                    continue

                inter_highs = [h for h in high_swings if l1.index < h.index < l2.index]
                if not inter_highs:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=l1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason="No confirmed structural reaction high between Low 1 and Low 2"
                    ))
                    continue

                # Wave structure check: Structural adjacency rule
                # There must NOT be an intervening swing low between Low 1 and Low 2
                inter_lows = [l for l in low_swings if l1.index < l.index < l2.index]
                if len(inter_lows) > 0:
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

                # Neckline check: Exactly ONE intermediate structural high (neckline) between Low 1 and Low 2
                if len(inter_highs) > 1:
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

                # Preceding trend validation leading into Low 1 (meaningful downward move)
                is_valid_trend, trend_reason = cls._validate_preceding_trend(
                    candles=candles, swings=swings, point_1=l1, pattern_type="W", atr_val=atr_val, timeframe=timeframe
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

                # Early-wave / 5-wave exhaustion check leading into L1
                prior_lows = [s for s in low_swings if s.index < l1.index]
                if len(prior_lows) >= 3 and (prior_lows[-3].price > prior_lows[-2].price > prior_lows[-1].price > l1.price):
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=l1.index + 1, neckline_price=0.0, neckline_time="",
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=0.0, depth_atr=0.0, symmetry_atr=0.0, bar_separation=bar_sep,
                        quality_score=0, rejection_reason="Pattern formed after extended 5-wave movement (>= 3 consecutive lower lows prior to L1)",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # Point 2 = Low 2. SL = Low 2 - configurable ATR buffer (strictly < neckline)
                sl_buf = getattr(settings, "W_M_SL_ATR_BUFFER", 0.15)
                w_sl_val = round(l2.price - (sl_buf * atr_val), 2)
                w_sl_time = l2.timestamp

                mid_peak = max(inter_highs, key=lambda h: h.price)
                neckline = mid_peak.price

                diff_price = abs(l1.price - l2.price)
                diff_atr = diff_price / max(0.0001, atr_val)
                pattern_depth = neckline - min(l1.price, l2.price)
                depth_atr = pattern_depth / max(0.0001, atr_val)

                if depth_atr < min_depth_atr:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=45,
                        rejection_reason=f"Insufficient neckline depth ({depth_atr:.2f} ATR < {min_depth_atr:.2f} ATR)",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # Individual leg amplitude requirement: BOTH legs must independently satisfy >= max(1.2 * ATR, l1.price * pct)
                tf_clean_w = (timeframe or "1H").upper()
                leg_pct_map_w = {
                    "5M": 0.001,   # 0.10% on 5M
                    "15M": 0.002,  # 0.20% on 15M
                    "1H": 0.004,   # 0.40% on 1H
                    "4H": 0.008    # 0.80% on 4H/Daily
                }
                min_leg_amp = max(1.2 * atr_val, l1.price * leg_pct_map_w.get(tf_clean_w, 0.004))
                leg1_amp = neckline - l1.price
                leg2_amp = neckline - l2.price

                if leg1_amp < min_leg_amp:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=35,
                        rejection_reason=f"Leg 1 amplitude too small ({leg1_amp:.2f} < {min_leg_amp:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                if leg2_amp < min_leg_amp:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=35,
                        rejection_reason=f"Leg 2 amplitude too small ({leg2_amp:.2f} < {min_leg_amp:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                # Tightened symmetry: max(1.2 * ATR, 1.5% of Point 1 price)
                max_allowed_diff = max(1.2 * atr_val, l1.price * 0.015)
                if diff_price > max_allowed_diff:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}",
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=40,
                        rejection_reason=f"Lows too asymmetric ({diff_price:.2f} > {max_allowed_diff:.2f})",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

                pattern_id = f"{symbol}_{timeframe}_W_{l1.timestamp}_{l2.timestamp}"

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
                    sl_atr_buffer=sl_buf
                )

                # Scan for confirmed breakout candle strictly after Point 2 (L2)
                structural_break_idx = None
                structural_break_time = None
                structural_break_close = None
                is_high_confluence = False
                breakout_tl = None
                breakout_ema = None
                breakout_vol = 1.25
                tl_broken = False
                ema_broken = False
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

                for i in range(l2.index + 1, max_scan_index):
                    c = candles[i]
                    is_latest_candle = (i == n - 1)

                    if is_latest_candle:
                        if c.close > neckline or c.high > neckline:
                            if structural_break_idx is None:
                                is_forming = True
                        continue

                    if structural_break_idx is None:
                        # Structural Breakout condition: candle close above neckline (wick-only does NOT count)
                        prev_c = candles[i - 1]
                        if c.close >= (neckline + min_breakout_dist) and prev_c.close <= (neckline + min_breakout_dist * 0.5):
                            if c.close >= (neckline + 0.75 * pattern_depth):
                                already_moved_too_far = True
                                break

                            structural_break_idx = i
                            structural_break_time = c.timestamp
                            structural_break_close = c.close

                            ema_20: Optional[float] = None
                            rel_vol: float = 1.25
                            if df_indicators is not None and i < len(df_indicators):
                                row = df_indicators.iloc[i]
                                if "ema_20" in row and not pd.isna(row["ema_20"]):
                                    ema_20 = float(row["ema_20"])
                                if "relative_volume" in row and not pd.isna(row["relative_volume"]):
                                    rel_vol = float(row["relative_volume"])

                            ema_broken = (c.close > ema_20) if ema_20 is not None else True
                            
                            tl_broken = True
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

                            breakout_tl = matching_tl or (relevant_tls[0] if relevant_tls else None)
                            breakout_ema = ema_20
                            breakout_vol = rel_vol

                            if ema_broken and tl_broken and rel_vol >= 1.15:
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

                if already_moved_too_far:
                    debug_candidates.append(WMPatternStructure(
                        pattern_id=pattern_id,
                        pattern_type="W",
                        status="REJECTED",
                        s1_index=l1.index, s1_price=round(l1.price, 2), s1_time=l1.timestamp,
                        neckline_index=mid_peak.index, neckline_price=round(neckline, 2), neckline_time=mid_peak.timestamp,
                        s2_index=l2.index, s2_price=round(l2.price, 2), s2_time=l2.timestamp,
                        pattern_height=round(pattern_depth, 2), depth_atr=round(depth_atr, 2), symmetry_atr=round(diff_atr, 2),
                        bar_separation=bar_sep, quality_score=0,
                        rejection_reason="Breakout candle already moved substantially prior to confirmation (exceeded 75% of pattern depth)",
                        symbol=symbol, timeframe=timeframe
                    ))
                    continue

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
                elif is_target_1_hit:
                    pat_status = "TARGET_1_HIT"
                elif is_invalidated:
                    pat_status = "INVALIDATED"
                elif structural_break_idx is not None:
                    if is_high_confluence and q_score >= 75:
                        pat_status = "HIGH_CONFLUENCE_CONFIRMED"
                    else:
                        pat_status = "BREAKOUT_CONFIRMED"
                elif is_forming:
                    pat_status = "BREAKOUT_FORMING"
                else:
                    pat_status = "CONFIRMED"

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
                    outcome_timestamp=outcome_ts if (is_target_2_hit or is_target_1_hit or is_invalidated) else None
                )

                confirmed_patterns.append(w_pattern_obj)
                debug_candidates.append(w_pattern_obj)

                if structural_break_idx is not None:
                    is_high_conf_alert = (is_high_confluence and q_score >= 75)
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
        # 3. SELECT SINGLE ACTIVE PATTERN (Removes Chart Clutter)
        # -------------------------------------------------------------
        active_pattern: Optional[WMPatternStructure] = None
        # Sort patterns by breakout index or formation index
        confirmed_patterns.sort(key=lambda p: (p.breakout_candle_index or p.s2_index), reverse=True)

        if confirmed_patterns:
            active_pattern = confirmed_patterns[0]
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
