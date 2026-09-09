from typing import List, Dict, Optional, Tuple, Literal, Any
from datetime import datetime
import numpy as np
from app.models.schemas import Candle, SwingPoint, StructureBreakEvent, TrendlineSchema, TrendlineTouchPoint
from app.core.config import settings
from app.core.timezone import is_candle_closed

class Trendline:
    def __init__(
        self,
        line_type: Literal["ASCENDING_SUPPORT", "DESCENDING_RESISTANCE"],
        p1_index: int,
        p1_price: float,
        p1_time: str,
        p2_index: int,
        p2_price: float,
        p2_time: str,
        slope: float,
        intercept: float,
        end_index: int,
        end_price: float,
        touch_count: int = 2,
        touch_points: Optional[List[TrendlineTouchPoint]] = None,
        rank: Literal["PRIMARY", "SECONDARY", "MINOR"] = "PRIMARY",
        strength: Literal["MAJOR", "INTERMEDIATE", "MINOR"] = "INTERMEDIATE",
        status: Literal["ACTIVE", "BROKEN", "RETESTED"] = "ACTIVE",
        is_active: bool = True,
        is_broken: bool = False,
        r_squared: Optional[float] = None,
        swing_structure: Optional[str] = None,
        structure_points: Optional[List[str]] = None
    ):
        self.line_type = line_type
        self.p1_index = p1_index
        self.p1_price = p1_price
        self.p1_time = p1_time
        self.p2_index = p2_index
        self.p2_price = p2_price
        self.p2_time = p2_time
        self.slope = slope
        self.intercept = intercept
        self.end_index = end_index
        self.end_price = end_price
        self.touch_count = touch_count
        self.touch_points = touch_points or []
        self.rank = rank
        self.strength = strength
        self.status = status
        self.is_active = is_active
        self.is_broken = is_broken
        self.r_squared = r_squared
        self.swing_structure = swing_structure
        self.structure_points = structure_points or []

    def get_price_at_index(self, index: int) -> float:
        return self.slope * index + self.intercept

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_type": self.line_type,
            "rank": self.rank,
            "strength": self.strength,
            "p1_index": self.p1_index,
            "p1_price": round(self.p1_price, 2),
            "p1_time": self.p1_time,
            "p2_index": self.p2_index,
            "p2_price": round(self.p2_price, 2),
            "p2_time": self.p2_time,
            "end_index": self.end_index,
            "end_price": round(self.end_price, 2),
            "slope": self.slope,
            "intercept": self.intercept,
            "touch_count": self.touch_count,
            "touch_points": [tp.model_dump() if hasattr(tp, "model_dump") else tp for tp in self.touch_points],
            "r_squared": round(self.r_squared, 3) if self.r_squared is not None else None,
            "swing_structure": self.swing_structure,
            "structure_points": self.structure_points,
            "status": self.status,
            "is_active": self.is_active,
            "is_broken": self.is_broken
        }


class TrendlineDetector:
    """
    Multi-Trendline Structural Engine:
    Detects up to MAX_TRENDLINES_PER_DIRECTION ascending support and descending resistance lines,
    validates candidate geometry, clusters redundant lines, ranks into Primary/Secondary/Minor,
    dynamically extends active lines to the latest candle (stopping broken lines at break index),
    and detects structural breaks and retests.
    """

    @staticmethod
    def _calculate_atr(candles: List[Candle]) -> float:
        if not candles:
            return 1.0
        recent = candles[-min(20, len(candles)):]
        ranges = [
            max(c.high - c.low, abs(c.high - c.close), abs(c.low - c.close))
            for c in recent
        ]
        return max(float(np.mean(ranges)), 0.0001)

    @classmethod
    def _build_uptrend_candidates(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        atr: float
    ) -> List[Tuple[float, Trendline]]:
        lows = sorted([s for s in swings if not s.is_high and getattr(s, "confirmed", True)], key=lambda s: s.index)
        if len(lows) < 2:
            return []

        n = len(candles)
        candidates: List[Tuple[float, Trendline]] = []

        for start_idx, first in enumerate(lows):
            subsequent = lows[start_idx + 1:]
            if not subsequent:
                continue

            for second in subsequent:
                dx = second.index - first.index
                if dx < 2:
                    continue

                slope = (second.price - first.price) / dx
                if slope <= 0:
                    continue

                intercept = first.price - slope * first.index

                touches: List[SwingPoint] = [first, second]
                violations = 0
                deviations: List[float] = [0.0, 0.0]

                # Collect all qualifying swing lows after second within tolerance (0.65 * atr)
                for s in lows:
                    if s.index <= second.index:
                        continue
                    line_price = slope * s.index + intercept
                    dist = abs(s.price - line_price)
                    if dist <= 0.65 * atr:
                        touches.append(s)
                        deviations.append(dist)

                unique_touch_swings = {s.index: s for s in touches}
                sorted_touch_indices = sorted(unique_touch_swings.keys())
                touch_count = len(sorted_touch_indices)

                # Minimum 2 confirmed structural touches
                if touch_count < 2:
                    continue

                # Check candle body penetration
                check_limit = n
                break_index = None
                for k in range(first.index, check_limit):
                    c = candles[k]
                    line_price = slope * k + intercept
                    body_bottom = min(c.open, c.close)
                    if body_bottom < (line_price - 0.28 * atr):
                        violations += 1
                        if break_index is None and k > second.index:
                            break_index = k

                # If the line was broken before or at the last touch point, it cannot be a valid established line
                if break_index is not None and break_index <= sorted_touch_indices[-1]:
                    continue

                if violations > 5 and break_index is not None and break_index <= sorted_touch_indices[-1]:
                    continue

                span = sorted_touch_indices[-1] - sorted_touch_indices[0]
                mean_dev = np.mean(deviations) if deviations else atr
                recency = n - sorted_touch_indices[-1]

                is_base_origin = (first.index == lows[0].index)
                base_bonus = 150 if (is_base_origin and touch_count >= 3) else (50 if is_base_origin else 0)

                score = (
                    touch_count * 100
                    + span * 1.5
                    + base_bonus
                    - (mean_dev / atr) * 25
                    - violations * 30
                    - recency * 0.10
                )

                current_price = candles[-1].close
                line_end_price = slope * (n - 1) + intercept
                is_broken = current_price < (line_end_price - 0.25 * atr) or (break_index is not None)

                if is_broken and break_index is not None:
                    end_idx = break_index
                    end_pr = slope * break_index + intercept
                    status = "BROKEN"
                else:
                    end_idx = n - 1
                    end_pr = line_end_price
                    status = "ACTIVE"

                strength: Literal["MAJOR", "INTERMEDIATE", "MINOR"] = (
                    "MAJOR" if touch_count >= 4 or (is_base_origin and touch_count >= 3) else ("INTERMEDIATE" if touch_count >= 2 else "MINOR")
                )

                touch_point_objs = [
                    TrendlineTouchPoint(index=s.index, timestamp=s.timestamp, price=s.price)
                    for s in [unique_touch_swings[idx] for idx in sorted_touch_indices]
                ]

                # Calculate R^2 goodness-of-fit across all touch points
                r_squared = 1.0
                if len(touch_point_objs) >= 2:
                    xs = np.array([tp.index for tp in touch_point_objs], dtype=float)
                    ys = np.array([tp.price for tp in touch_point_objs], dtype=float)
                    mean_x = np.mean(xs)
                    mean_y = np.mean(ys)
                    ss_xx = np.sum((xs - mean_x) ** 2)
                    ss_yy = np.sum((ys - mean_y) ** 2)
                    ss_xy = np.sum((xs - mean_x) * (ys - mean_y))
                    if ss_xx > 1e-6 and ss_yy > 1e-6:
                        r_val = ss_xy / np.sqrt(ss_xx * ss_yy)
                        r_squared = max(0.0, min(1.0, float(r_val ** 2)))
                    else:
                        r_squared = 0.95

                swing_structure = f"Higher Low × {touch_count}"
                structure_points = ["HL"] * touch_count

                tl = Trendline(
                    line_type="ASCENDING_SUPPORT",
                    p1_index=first.index,
                    p1_price=first.price,
                    p1_time=first.timestamp,
                    p2_index=second.index,
                    p2_price=second.price,
                    p2_time=second.timestamp,
                    end_index=end_idx,
                    end_price=end_pr,
                    slope=slope,
                    intercept=intercept,
                    touch_count=touch_count,
                    touch_points=touch_point_objs,
                    strength=strength,
                    status=status,
                    is_active=not is_broken,
                    is_broken=is_broken,
                    r_squared=r_squared,
                    swing_structure=swing_structure,
                    structure_points=structure_points
                )
                candidates.append((score, tl))

        return candidates

    @classmethod
    def _build_downtrend_candidates(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        atr: float
    ) -> List[Tuple[float, Trendline]]:
        highs = sorted([s for s in swings if s.is_high and getattr(s, "confirmed", True)], key=lambda s: s.index)
        if len(highs) < 2:
            return []

        n = len(candles)
        candidates: List[Tuple[float, Trendline]] = []

        for start_idx, first in enumerate(highs):
            subsequent = highs[start_idx + 1:]
            if not subsequent:
                continue

            for second in subsequent:
                dx = second.index - first.index
                if dx < 2:
                    continue

                slope = (second.price - first.price) / dx
                if slope >= 0:
                    continue

                intercept = first.price - slope * first.index

                touches: List[SwingPoint] = [first, second]
                violations = 0
                deviations: List[float] = [0.0, 0.0]

                # Collect all qualifying swing highs after second within tolerance (0.65 * atr)
                for s in highs:
                    if s.index <= second.index:
                        continue
                    line_price = slope * s.index + intercept
                    dist = abs(s.price - line_price)
                    if dist <= 0.65 * atr:
                        touches.append(s)
                        deviations.append(dist)

                unique_touch_swings = {s.index: s for s in touches}
                sorted_touch_indices = sorted(unique_touch_swings.keys())
                touch_count = len(sorted_touch_indices)

                # Minimum 2 confirmed structural touches
                if touch_count < 2:
                    continue

                # Check candle body penetration
                check_limit = n
                break_index = None
                for k in range(first.index, check_limit):
                    c = candles[k]
                    line_price = slope * k + intercept
                    body_top = max(c.open, c.close)
                    if body_top > (line_price + 0.28 * atr):
                        violations += 1
                        if break_index is None and k > second.index:
                            break_index = k

                # If broken before or at the last touch point, candidate is invalid
                if break_index is not None and break_index <= sorted_touch_indices[-1]:
                    continue

                if violations > 5 and break_index is not None and break_index <= sorted_touch_indices[-1]:
                    continue

                span = sorted_touch_indices[-1] - sorted_touch_indices[0]
                mean_dev = np.mean(deviations) if deviations else atr
                recency = n - sorted_touch_indices[-1]

                is_base_origin = (first.index == highs[0].index)
                base_bonus = 150 if (is_base_origin and touch_count >= 3) else (50 if is_base_origin else 0)

                score = (
                    touch_count * 100
                    + span * 1.5
                    + base_bonus
                    - (mean_dev / atr) * 25
                    - violations * 30
                    - recency * 0.10
                )

                current_price = candles[-1].close
                line_end_price = slope * (n - 1) + intercept
                is_broken = current_price > (line_end_price + 0.25 * atr) or (break_index is not None)

                if is_broken and break_index is not None:
                    end_idx = break_index
                    end_pr = slope * break_index + intercept
                    status = "BROKEN"
                else:
                    end_idx = n - 1
                    end_pr = line_end_price
                    status = "ACTIVE"

                strength: Literal["MAJOR", "INTERMEDIATE", "MINOR"] = (
                    "MAJOR" if touch_count >= 4 or (is_base_origin and touch_count >= 3) else ("INTERMEDIATE" if touch_count >= 2 else "MINOR")
                )

                touch_point_objs = [
                    TrendlineTouchPoint(index=s.index, timestamp=s.timestamp, price=s.price)
                    for s in [unique_touch_swings[idx] for idx in sorted_touch_indices]
                ]

                # Calculate R^2 goodness-of-fit across all touch points
                r_squared = 1.0
                if len(touch_point_objs) >= 2:
                    xs = np.array([tp.index for tp in touch_point_objs], dtype=float)
                    ys = np.array([tp.price for tp in touch_point_objs], dtype=float)
                    mean_x = np.mean(xs)
                    mean_y = np.mean(ys)
                    ss_xx = np.sum((xs - mean_x) ** 2)
                    ss_yy = np.sum((ys - mean_y) ** 2)
                    ss_xy = np.sum((xs - mean_x) * (ys - mean_y))
                    if ss_xx > 1e-6 and ss_yy > 1e-6:
                        r_val = ss_xy / np.sqrt(ss_xx * ss_yy)
                        r_squared = max(0.0, min(1.0, float(r_val ** 2)))
                    else:
                        r_squared = 0.95

                swing_structure = f"Lower High × {touch_count}"
                structure_points = ["LH"] * touch_count

                tl = Trendline(
                    line_type="DESCENDING_RESISTANCE",
                    p1_index=first.index,
                    p1_price=first.price,
                    p1_time=first.timestamp,
                    p2_index=second.index,
                    p2_price=second.price,
                    p2_time=second.timestamp,
                    end_index=end_idx,
                    end_price=end_pr,
                    slope=slope,
                    intercept=intercept,
                    touch_count=touch_count,
                    touch_points=touch_point_objs,
                    strength=strength,
                    status=status,
                    is_active=not is_broken,
                    is_broken=is_broken,
                    r_squared=r_squared,
                    swing_structure=swing_structure,
                    structure_points=structure_points
                )
                candidates.append((score, tl))

        return candidates

    @classmethod
    def _cluster_and_rank_lines(
        cls,
        candidates: List[Tuple[float, Trendline]],
        atr: float,
        n: int,
        max_lines: int = 5
    ) -> List[Trendline]:
        if not candidates:
            return []

        candidates.sort(key=lambda x: x[0], reverse=True)
        selected: List[Trendline] = []

        for score, candidate in candidates:
            is_duplicate = False
            for existing in selected:
                current_diff = abs(
                    existing.get_price_at_index(n - 1) - candidate.get_price_at_index(n - 1)
                )
                slope_diff = abs(existing.slope - candidate.slope)

                if current_diff < 0.60 * atr and slope_diff < 0.025 * atr:
                    is_duplicate = True
                    break

            if is_duplicate:
                continue

            selected.append(candidate)
            if len(selected) >= max_lines:
                break

        for idx, line in enumerate(selected):
            if idx == 0:
                line.rank = "PRIMARY"
            elif idx <= 2:
                line.rank = "SECONDARY"
            else:
                line.rank = "MINOR"

        return selected

    @classmethod
    def fit_trendlines(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        max_lines_per_direction: int = 5
    ) -> List[Trendline]:
        if len(candles) < 4 or len(swings) < 2:
            return []

        atr = cls._calculate_atr(candles)
        n = len(candles)
        # Cap swings to the most recent 80 swings to prevent combinatorial explosion
        eval_swings = swings[-80:] if len(swings) > 80 else swings

        up_candidates = cls._build_uptrend_candidates(candles, eval_swings, atr)
        down_candidates = cls._build_downtrend_candidates(candles, eval_swings, atr)

        ranked_support = cls._cluster_and_rank_lines(up_candidates, atr, n, max_lines_per_direction)
        ranked_resistance = cls._cluster_and_rank_lines(down_candidates, atr, n, max_lines_per_direction)

        return ranked_support + ranked_resistance

    @classmethod
    def find_opposing_safety_line(
        cls,
        trendlines: List[Trendline],
        action_line: Trendline,
        candle_index: int,
        atr_val: float
    ) -> Optional[Trendline]:
        """
        Finds a valid opposing Safety Line for the given action line at candle_index.
        For ASCENDING_SUPPORT (bearish break), opposing line is DESCENDING_RESISTANCE.
        For DESCENDING_RESISTANCE (bullish break), opposing line is ASCENDING_SUPPORT.
        Requirements:
        1. Formed before or at candle_index (p2_index <= candle_index).
        2. Proximity: distance between action line and safety line <= 8.0 * atr_val.
        3. Structural direction:
           - For bearish breakdown of ascending support, safety resistance line should be above (or near).
           - For bullish breakout of descending resistance, safety support line should be below (or near).
        """
        opposing_type = (
            "DESCENDING_RESISTANCE"
            if action_line.line_type == "ASCENDING_SUPPORT"
            else "ASCENDING_SUPPORT"
        )
        candidates = [
            tl for tl in trendlines
            if tl.line_type == opposing_type and getattr(tl, "p2_index", 0) <= candle_index
        ]
        if not candidates:
            return None

        action_price = action_line.get_price_at_index(candle_index)
        valid_proximity: List[Tuple[float, Trendline]] = []
        for tl in candidates:
            safety_price = tl.get_price_at_index(candle_index)
            dist = abs(action_price - safety_price)
            if dist <= 8.0 * atr_val:
                if action_line.line_type == "ASCENDING_SUPPORT":
                    if safety_price >= action_price - 0.5 * atr_val:
                        valid_proximity.append((dist, tl))
                else:
                    if safety_price <= action_price + 0.5 * atr_val:
                        valid_proximity.append((dist, tl))

        if not valid_proximity:
            return None

        # Sort primarily by rank (PRIMARY first), then by closest proximity
        valid_proximity.sort(key=lambda x: (0 if x[1].rank == "PRIMARY" else (1 if x[1].rank == "SECONDARY" else 2), x[0]))
        return valid_proximity[0][1]

    @classmethod
    def detect_trendline_breaks(
        cls,
        candles: List[Candle],
        trendlines: List[Trendline],
        symbol: str,
        timeframe: str,
        atr_val: float = 1.0,
        require_safety_line: bool = False,
        now: Optional[datetime] = None
    ) -> List[StructureBreakEvent]:
        if not candles or not trendlines:
            return []

        # Map candle_index -> list of (priority_tuple, StructureBreakEvent)
        events_by_candle: Dict[int, List[Tuple[Tuple[int, int, int, float], StructureBreakEvent]]] = {}
        start = max(1, len(candles) - 10)

        for i in range(start, len(candles)):
            current = candles[i]
            previous = candles[i - 1]

            # Rule 7 & 8: Unfinished candle rejection and candle-close timing
            if not is_candle_closed(current.timestamp, timeframe, now=now):
                continue

            for tl in trendlines:
                # Evaluates touches occurring strictly before candle i
                if tl.touch_points:
                    prior_touches = [tp for tp in tl.touch_points if tp.index < i]
                else:
                    prior_touches = [1, 2] if i > tl.p2_index else []

                if len(prior_touches) < 2:
                    continue

                # Classify touch count before the breakout candle
                touch_count_prior = len(prior_touches)
                is_3touch = touch_count_prior >= 3
                touch_class = "3-TOUCH" if is_3touch else "2-TOUCH"

                # Opposing Safety Line check
                safety_line = cls.find_opposing_safety_line(trendlines, tl, i, atr_val)
                if require_safety_line and safety_line is None:
                    continue

                line_now = tl.get_price_at_index(i)
                line_previous = tl.get_price_at_index(i - 1)

                # ASCENDING SUPPORT BREAK (Bearish / Short)
                if tl.line_type == "ASCENDING_SUPPORT":
                    previous_above = previous.close >= line_previous - (0.20 * atr_val)
                    current_below = current.close < (line_now - 0.20 * atr_val)

                    if previous_above and current_below:
                        displacement = (line_now - current.close) / atr_val
                        score = 90 if is_3touch else 75
                        notes = f"{touch_class} TRENDLINE BREAK — BEARISH | {tl.rank} {tl.strength.lower()} ascending support broken"
                        if safety_line:
                            sl_touches = len(safety_line.touch_points) if safety_line.touch_points else 2
                            notes += f" | Safety Line: {safety_line.line_type} ({sl_touches}T)"

                        ev = StructureBreakEvent(
                            id=f"{symbol}_{timeframe}_TL_BEAR_{current.timestamp}_{i}",
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=current.timestamp,
                            event_type="TREND_LINE_BREAK",
                            direction="BEARISH",
                            broken_level=round(line_now, 2),
                            break_price=round(current.close, 2),
                            break_candle_index=i,
                            volume_confirmed=current.volume > 0,
                            atr_at_break=round(atr_val, 2),
                            htf_alignment="BEARISH",
                            evidence_score=score,
                            notes=notes
                        )
                        rank_tier = 2 if tl.rank == "PRIMARY" else (1 if tl.rank == "SECONDARY" else 0)
                        priority = (2 if is_3touch else 1, rank_tier, 1 if safety_line else 0, displacement)
                        events_by_candle.setdefault(i, []).append((priority, ev))

                # DESCENDING RESISTANCE BREAK (Bullish / Long)
                elif tl.line_type == "DESCENDING_RESISTANCE":
                    previous_below = previous.close <= line_previous + (0.20 * atr_val)
                    current_above = current.close > (line_now + 0.20 * atr_val)

                    if previous_below and current_above:
                        displacement = (current.close - line_now) / atr_val
                        score = 90 if is_3touch else 75
                        notes = f"{touch_class} TRENDLINE BREAK — BULLISH | {tl.rank} {tl.strength.lower()} descending resistance broken"
                        if safety_line:
                            sl_touches = len(safety_line.touch_points) if safety_line.touch_points else 2
                            notes += f" | Safety Line: {safety_line.line_type} ({sl_touches}T)"

                        ev = StructureBreakEvent(
                            id=f"{symbol}_{timeframe}_TL_BULL_{current.timestamp}_{i}",
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=current.timestamp,
                            event_type="TREND_LINE_BREAK",
                            direction="BULLISH",
                            broken_level=round(line_now, 2),
                            break_price=round(current.close, 2),
                            break_candle_index=i,
                            volume_confirmed=current.volume > 0,
                            atr_at_break=round(atr_val, 2),
                            htf_alignment="BULLISH",
                            evidence_score=score,
                            notes=notes
                        )
                        rank_tier = 2 if tl.rank == "PRIMARY" else (1 if tl.rank == "SECONDARY" else 0)
                        priority = (2 if is_3touch else 1, rank_tier, 1 if safety_line else 0, displacement)
                        events_by_candle.setdefault(i, []).append((priority, ev))

        # Rule 9: One directional breakout per symbol/timeframe/candle
        final_events: List[StructureBreakEvent] = []
        for idx in sorted(events_by_candle.keys()):
            candle_candidates = events_by_candle[idx]
            candle_candidates.sort(key=lambda x: x[0], reverse=True)
            final_events.append(candle_candidates[0][1])

        return final_events