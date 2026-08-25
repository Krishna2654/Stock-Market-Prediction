from fastapi import APIRouter, HTTPException
from app.models.schemas import BacktestRequest, BacktestResult
from app.api.deps import get_current_provider
from app.backtesting.engine import MarketStructureBacktester

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

@router.post("/run", response_model=BacktestResult)
async def run_backtest(req: BacktestRequest):
    """
    Executes a structure-based backtest for the specified instrument, timeframe, and strategy.
    """
    provider = get_current_provider()
    
    # Fetch extended candles for backtesting
    candles = await provider.fetch_candles(
        symbol=req.symbol,
        ticker=req.ticker,
        timeframe=req.timeframe,
        limit=350
    )
    
    if len(candles) < 30:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient candle history ({len(candles)} candles) to run backtest for {req.symbol} on {req.timeframe}."
        )

    result = MarketStructureBacktester.run_backtest(candles, req)
    return result
