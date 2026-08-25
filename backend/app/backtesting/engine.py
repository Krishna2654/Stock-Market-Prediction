from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from app.models.schemas import (
    Candle,
    BacktestRequest,
    BacktestResult,
    BacktestTrade
)
from app.indicators.technical import TechnicalIndicatorEngine
from app.market_structure.swings import SwingDetector
from app.market_structure.bos_choch import BOSCHoCHDetector
from app.market_structure.trendlines import TrendlineDetector

class MarketStructureBacktester:
    """
    Simulates and validates structure-based trading strategies
    (BOS Continuation, CHoCH Reversal, and Trendline Breakout) against historical candles.
    Enforces zero look-ahead bias and realistic slippage / fees.
    """

    @classmethod
    def run_backtest(
        cls,
        candles: List[Candle],
        req: BacktestRequest
    ) -> BacktestResult:
        if len(candles) < 30:
            return BacktestResult(
                symbol=req.symbol,
                timeframe=req.timeframe,
                strategy=req.strategy,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate_pct=0.0,
                loss_rate_pct=0.0,
                profit_factor=0.0,
                total_return_pct=0.0,
                max_drawdown_pct=0.0,
                avg_trade_pnl_pct=0.0,
                avg_favorable_excursion_pct=0.0,
                avg_adverse_excursion_pct=0.0,
                trades=[],
                equity_curve=[]
            )

        # 1. Compute indicators & swings
        df_indicators, _ = TechnicalIndicatorEngine.compute_all_indicators(candles)
        swings, _ = SwingDetector.detect_swings(candles, swing_length=5, confirmation_candles=2)
        breaks = BOSCHoCHDetector.detect_structure_breaks(
            candles=candles,
            swings=swings,
            symbol=req.symbol,
            timeframe=req.timeframe,
            df_indicators=df_indicators
        )

        trendlines = TrendlineDetector.fit_trendlines(candles, swings)
        tl_breaks = TrendlineDetector.detect_trendline_breaks(
            candles, trendlines, req.symbol, req.timeframe
        )
        for tb in tl_breaks:
            breaks.append(tb)

        # Map break events by candle index
        breaks_by_index: Dict[int, Any] = {b.break_candle_index: b for b in breaks}

        # Simulation state
        trades: List[BacktestTrade] = []
        equity = 100000.0  # Base simulated portfolio
        initial_equity = equity
        peak_equity = equity
        max_drawdown = 0.0
        equity_curve = [{"time": candles[0].timestamp, "equity": equity}]

        active_trade: Optional[Dict[str, Any]] = None
        trade_counter = 1

        slippage_factor = req.slippage_bps / 10000.0
        fee_factor = req.fee_bps / 10000.0

        for i in range(10, len(candles)):
            c = candles[i]
            current_close = c.close
            current_high = c.high
            current_low = c.low
            atr = float(df_indicators.iloc[i]["atr_14"]) if i < len(df_indicators) and "atr_14" in df_indicators.iloc[i] and not pd.isna(df_indicators.iloc[i]["atr_14"]) else (current_close * 0.01)

            # Manage active trade
            if active_trade is not None:
                bars_held = i - active_trade["entry_index"]
                direction = active_trade["direction"]
                entry_p = active_trade["entry_price"]
                sl = active_trade["stop_loss"]
                tp = active_trade["target"]

                # Track MAE & MFE
                if direction == "LONG":
                    max_fav = (current_high - entry_p) / entry_p * 100.0
                    max_adv = (entry_p - current_low) / entry_p * 100.0
                else:
                    max_fav = (entry_p - current_low) / entry_p * 100.0
                    max_adv = (current_high - entry_p) / entry_p * 100.0

                active_trade["mfe"] = max(active_trade["mfe"], max_fav)
                active_trade["mae"] = max(active_trade["mae"], max_adv)

                # Check Exit conditions
                exit_price = None
                exit_reason = None

                if direction == "LONG":
                    if current_high >= tp:
                        exit_price = tp * (1.0 - slippage_factor)
                        exit_reason = "TARGET"
                    elif current_low <= sl:
                        exit_price = sl * (1.0 - slippage_factor)
                        exit_reason = "STOP_LOSS"
                    elif bars_held >= 30:  # Time-based expiration
                        exit_price = current_close * (1.0 - slippage_factor)
                        exit_reason = "TIME_EXIT"
                else:  # SHORT
                    if current_low <= tp:
                        exit_price = tp * (1.0 + slippage_factor)
                        exit_reason = "TARGET"
                    elif current_high >= sl:
                        exit_price = sl * (1.0 + slippage_factor)
                        exit_reason = "STOP_LOSS"
                    elif bars_held >= 30:
                        exit_price = current_close * (1.0 + slippage_factor)
                        exit_reason = "TIME_EXIT"

                if exit_price is not None:
                    if direction == "LONG":
                        raw_pnl_pct = (exit_price - entry_p) / entry_p
                    else:
                        raw_pnl_pct = (entry_p - exit_price) / entry_p

                    # Deduct round-trip fees
                    net_pnl_pct = raw_pnl_pct - (2 * fee_factor)
                    pnl_amount = active_trade["position_size"] * net_pnl_pct
                    equity += pnl_amount

                    trades.append(BacktestTrade(
                        trade_id=trade_counter,
                        entry_time=active_trade["entry_time"],
                        exit_time=c.timestamp,
                        direction=direction,
                        entry_price=round(entry_p, 2),
                        exit_price=round(exit_price, 2),
                        stop_loss=round(sl, 2),
                        target=round(tp, 2),
                        pnl_pct=round(net_pnl_pct * 100.0, 2),
                        pnl_amount=round(pnl_amount, 2),
                        exit_reason=exit_reason,
                        mae_pct=round(active_trade["mae"], 2),
                        mfe_pct=round(active_trade["mfe"], 2),
                        bars_held=bars_held
                    ))
                    trade_counter += 1
                    active_trade = None

            # Check new entry signals if no active trade
            if active_trade is None and i in breaks_by_index:
                brk = breaks_by_index[i]
                
                should_enter = False
                direction = "LONG" if brk.direction == "BULLISH" else "SHORT"

                if req.strategy == "BOS_CONTINUATION" and "BOS" in brk.event_type:
                    should_enter = True
                elif req.strategy == "CHOCH_REVERSAL" and "CHOCH" in brk.event_type:
                    should_enter = True
                elif req.strategy == "TRENDLINE_BREAKOUT" and "TREND_LINE" in brk.event_type:
                    should_enter = True
                elif req.strategy == "MULTI_TF_ALIGNMENT":
                    should_enter = brk.volume_confirmed

                if should_enter:
                    entry_p = current_close * (1.0 + slippage_factor if direction == "LONG" else 1.0 - slippage_factor)
                    sl_dist = atr * req.stop_loss_atr_multiple
                    tp_dist = sl_dist * req.risk_reward_ratio

                    if direction == "LONG":
                        sl = entry_p - sl_dist
                        tp = entry_p + tp_dist
                    else:
                        sl = entry_p + sl_dist
                        tp = entry_p - tp_dist

                    risk_amount = equity * 0.01
                    risk_per_unit = abs(entry_p - sl)
                    pos_size = (risk_amount / risk_per_unit) * entry_p if risk_per_unit > 0 else equity * 0.1

                    active_trade = {
                        "entry_index": i,
                        "entry_time": c.timestamp,
                        "direction": direction,
                        "entry_price": entry_p,
                        "stop_loss": sl,
                        "target": tp,
                        "position_size": pos_size,
                        "mae": 0.0,
                        "mfe": 0.0
                    }

            peak_equity = max(peak_equity, equity)
            dd = (peak_equity - equity) / peak_equity * 100.0
            max_drawdown = max(max_drawdown, dd)
            equity_curve.append({"time": c.timestamp, "equity": round(equity, 2)})

        # Compute summary metrics
        total_trades = len(trades)
        wins = [t for t in trades if t.pnl_pct > 0]
        losses = [t for t in trades if t.pnl_pct <= 0]
        
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades * 100.0) if total_trades > 0 else 0.0
        loss_rate = (loss_count / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profit = sum(t.pnl_amount for t in wins)
        gross_loss = abs(sum(t.pnl_amount for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
        total_return_pct = ((equity - initial_equity) / initial_equity) * 100.0

        avg_pnl = (sum(t.pnl_pct for t in trades) / total_trades) if total_trades > 0 else 0.0
        avg_mfe = (sum(t.mfe_pct for t in trades) / total_trades) if total_trades > 0 else 0.0
        avg_mae = (sum(t.mae_pct for t in trades) / total_trades) if total_trades > 0 else 0.0

        return BacktestResult(
            symbol=req.symbol,
            timeframe=req.timeframe,
            strategy=req.strategy,
            total_trades=total_trades,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate_pct=round(win_rate, 2),
            loss_rate_pct=round(loss_rate, 2),
            profit_factor=round(profit_factor, 2),
            total_return_pct=round(total_return_pct, 2),
            max_drawdown_pct=round(max_drawdown, 2),
            avg_trade_pnl_pct=round(avg_pnl, 2),
            avg_favorable_excursion_pct=round(avg_mfe, 2),
            avg_adverse_excursion_pct=round(avg_mae, 2),
            trades=trades,
            equity_curve=equity_curve
        )
