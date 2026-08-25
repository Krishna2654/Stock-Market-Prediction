from fastapi import APIRouter, HTTPException, Body
from typing import Optional
from app.models.schemas import AIAnalysisSummary
from app.api.deps import get_current_provider, configured_instruments
from app.multi_timeframe.synthesis import MultiTimeframeAnalyzer
from app.ai.gemini_analyzer import GeminiAnalyzer

router = APIRouter(prefix="/api/ai", tags=["ai"])

@router.post("/summary/{symbol:path}", response_model=AIAnalysisSummary)
async def generate_instrument_ai_summary(
    symbol: str,
    api_key: Optional[str] = Body(None, embed=True)
):
    """
    Triggers Gemini AI structured summary generation for the specified instrument.
    Falls back gracefully to deterministic rule summary if API key is not configured.
    """
    provider = get_current_provider()
    target = next((i for i in configured_instruments if i.symbol.upper() == symbol.upper()), None)
    ticker = target.ticker if target else symbol

    # Fetch 4H, 1H, 15M, 5M data
    mtf_candles = await provider.get_multi_timeframe_data(symbol, ticker, ["4H", "1H", "15M", "5M"], limit=200)
    has_data = any(len(c) > 0 for c in mtf_candles.values())
    
    if not has_data:
        raise HTTPException(status_code=404, detail=f"No market data available to generate AI summary for {symbol}")

    synthesis = MultiTimeframeAnalyzer.synthesize(
        symbol=symbol,
        ticker=ticker,
        provider_name=provider.provider_name,
        mtf_candles=mtf_candles,
        is_stale=False,
        status_message="Active Feed"
    )

    ai_summary = await GeminiAnalyzer.generate_ai_summary(synthesis, api_key=api_key)
    return ai_summary
