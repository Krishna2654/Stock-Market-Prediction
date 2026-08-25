from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Dict, Any, Optional
from app.models.schemas import PaperOrder
from app.api.deps import get_current_provider, configured_instruments
from app.multi_timeframe.synthesis import MultiTimeframeAnalyzer
from app.paper_trading.simulator import paper_simulator

router = APIRouter(prefix="/api/paper", tags=["paper"])

@router.get("/setup/{symbol:path}")
async def get_hypothetical_setup(
    symbol: str,
    account_size: float = Query(100000.0, ge=1000.0),
    risk_pct: float = Query(1.0, ge=0.1, le=5.0)
):
    """
    Computes a strictly hypothetical, educational risk/reward setup.
    """
    provider = get_current_provider()
    target = next((i for i in configured_instruments if i.symbol.upper() == symbol.upper()), None)
    ticker = target.ticker if target else symbol

    mtf_candles = await provider.get_multi_timeframe_data(symbol, ticker, ["4H", "1H", "15M", "5M"], limit=150)
    has_data = any(len(c) > 0 for c in mtf_candles.values())
    if not has_data:
        raise HTTPException(status_code=404, detail="No data available")

    synthesis = MultiTimeframeAnalyzer.synthesize(
        symbol=symbol,
        ticker=ticker,
        provider_name=provider.provider_name,
        mtf_candles=mtf_candles,
        is_stale=False,
        status_message="Active"
    )

    setup = paper_simulator.calculate_hypothetical_setup(
        synthesis=synthesis,
        account_size=account_size,
        risk_pct=risk_pct
    )
    return setup

@router.get("/orders", response_model=List[PaperOrder])
def get_paper_orders():
    return paper_simulator.get_paper_orders()

@router.post("/orders", response_model=PaperOrder)
def place_paper_order(
    symbol: str = Body(...),
    direction: str = Body(...),
    entry_price: float = Body(...),
    stop_loss: float = Body(...),
    target: float = Body(...),
    quantity: float = Body(...),
    notes: str = Body("")
):
    order = paper_simulator.place_paper_order(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target=target,
        quantity=quantity,
        notes=notes
    )
    return order
