from typing import List, Dict, Optional, Tuple
import numpy as np
from app.models.schemas import Candle, SwingPoint, SupportResistanceLevel, SupportResistanceSummary

class SupportResistanceDetector:
    """
    Institutional Support & Resistance Engine.
    Combines:
    1. Fractal Swing Cluster Density (Price Pivots)
    2. Volume-Weighted Density Nodes (Volume-at-Price)
    3. Rejection Wick Analysis (Sharp Price Bounces)
    4. S/R Zone Width Calculation (Liquidity Bands)
    """

    @classmethod
    def detect_levels(
        cls,
        candles: List[Candle],
        swings: List[SwingPoint],
        timeframe: str,
        max_levels_to_return: int = 8
    ) -> SupportResistanceSummary:
        if not candles:
            return SupportResistanceSummary(current_price=0.0)

        current_price = candles[-1].close
        n = len(candles)
        
        # Calculate dynamic ATR for level tolerance
        atr_window = candles[-min(20, n):]
        atr = max(0.5, float(np.mean([c.high - c.low for c in atr_window])))
        tolerance = max(current_price * 0.0035, atr * 0.75)

        # -------------------------------------------------------------
        # 1. Collect Key Structural Anchor Points
        # -------------------------------------------------------------
        raw_points: List[Tuple[float, float, str]] = []  # (price, weight, source)

        # A. Swing Highs & Lows (High Weight)
        for s in swings:
            weight = 3.5 if s.confirmed else 2.0
            raw_points.append((s.price, weight, "SWING"))

        # B. Long Wick Rejection Pivots (Sharp Bounces)
        for i, c in enumerate(candles[-120:]):
            body_top = max(c.open, c.close)
            body_bottom = min(c.open, c.close)
            upper_wick = c.high - body_top
            lower_wick = body_bottom - c.low
            body_size = max(0.01, body_top - body_bottom)

            # Strong lower wick rejection -> Support node
            if lower_wick >= 2.0 * body_size and lower_wick >= (0.4 * atr):
                raw_points.append((c.low, 2.5, "WICK_REJECTION"))

            # Strong upper wick rejection -> Resistance node
            if upper_wick >= 2.0 * body_size and upper_wick >= (0.4 * atr):
                raw_points.append((c.high, 2.5, "WICK_REJECTION"))

        # C. Volume-at-Price Density (High Volume Nodes)
        prices = np.array([c.close for c in candles])
        volumes = np.array([max(1.0, c.volume) for c in candles])
        if len(prices) >= 20 and volumes.sum() > 0:
            hist, bin_edges = np.histogram(prices, bins=35, weights=volumes)
            top_bins = np.argsort(hist)[-5:]
            for idx in top_bins:
                mid_price = float(bin_edges[idx] + bin_edges[idx + 1]) / 2.0
                raw_points.append((mid_price, 2.0, "VOLUME_PROFILE"))

        # -------------------------------------------------------------
        # 2. Cluster Points within Adaptive ATR Band
        # -------------------------------------------------------------
        clusters: List[Dict] = []
        for p, w, src in raw_points:
            matched = False
            for cl in clusters:
                avg_p = cl["total_weighted_price"] / cl["total_weight"]
                if abs(p - avg_p) <= tolerance:
                    cl["prices"].append(p)
                    cl["total_weighted_price"] += (p * w)
                    cl["total_weight"] += w
                    cl["touches"] += 1
                    matched = True
                    break
            if not matched:
                clusters.append({
                    "prices": [p],
                    "total_weighted_price": p * w,
                    "total_weight": w,
                    "touches": 1
                })

        # -------------------------------------------------------------
        # 3. Formulate Ranked S/R Zones
        # -------------------------------------------------------------
        raw_levels: List[SupportResistanceLevel] = []
        for cl in clusters:
            level_price = round(cl["total_weighted_price"] / cl["total_weight"], 2)
            touch_count = cl["touches"]
            dist_pct = round(((level_price - current_price) / current_price) * 100.0, 2)
            
            level_type = "RESISTANCE" if level_price >= current_price else "SUPPORT"
            strength = "MAJOR" if (touch_count >= 3 or cl["total_weight"] >= 7.0) else "MINOR"

            raw_levels.append(SupportResistanceLevel(
                price=level_price,
                level_type=level_type,
                strength=strength,
                touch_count=min(touch_count, 12),
                timeframe=timeframe,
                distance_pct=dist_pct
            ))

        # Sort supports: closest below current price first
        supports = sorted(
            [lvl for lvl in raw_levels if lvl.price < current_price],
            key=lambda x: (x.strength == "MAJOR", x.touch_count, x.price),
            reverse=True
        )
        
        # Sort resistances: closest above current price first
        resistances = sorted(
            [lvl for lvl in raw_levels if lvl.price > current_price],
            key=lambda x: (x.strength == "MAJOR", x.touch_count, -x.price),
            reverse=True
        )

        minor_support = supports[0].price if len(supports) > 0 else round(current_price * 0.985, 2)
        major_support = supports[1].price if len(supports) > 1 else round(minor_support * 0.975, 2)

        minor_resistance = resistances[0].price if len(resistances) > 0 else round(current_price * 1.015, 2)
        major_resistance = resistances[1].price if len(resistances) > 1 else round(minor_resistance * 1.025, 2)

        # Top levels to return
        all_sorted = sorted(raw_levels, key=lambda x: x.touch_count, reverse=True)[:max_levels_to_return]

        return SupportResistanceSummary(
            major_support=major_support,
            minor_support=minor_support,
            current_price=round(current_price, 2),
            minor_resistance=minor_resistance,
            major_resistance=major_resistance,
            all_levels=all_sorted
        )
