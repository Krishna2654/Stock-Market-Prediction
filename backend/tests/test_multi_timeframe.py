import asyncio
import pytest
from app.data.simulated_provider import SimulatedMarketDataProvider
from app.multi_timeframe.synthesis import MultiTimeframeAnalyzer
from app.multi_timeframe.evidence_score import EvidenceScoreEngine

def test_multi_timeframe_synthesis():
    async def _run():
        provider = SimulatedMarketDataProvider()
        mtf_candles = await provider.get_multi_timeframe_data("NIFTY 50", "^NSEI", ["4H", "1H", "15M", "5M"], limit=150)
        
        assert len(mtf_candles["4H"]) > 0
        assert len(mtf_candles["1H"]) > 0
        assert len(mtf_candles["15M"]) > 0
        assert len(mtf_candles["5M"]) > 0
        
        synthesis = MultiTimeframeAnalyzer.synthesize(
            symbol="NIFTY 50",
            ticker="^NSEI",
            provider_name="Simulated Data Engine",
            mtf_candles=mtf_candles
        )
        
        assert synthesis.symbol == "NIFTY 50"
        assert synthesis.overall_bias in ["BULLISH", "BEARISH", "NEUTRAL", "MIXED"]
        assert 0 <= synthesis.evidence_score.total_score <= 100
        assert len(synthesis.evidence_score.details) > 0
        assert synthesis.current_state in [
            "FULL BULLISH ALIGNMENT",
            "FULL BEARISH ALIGNMENT",
            "BULLISH WITH SHORT-TERM PULLBACK",
            "BEARISH WITH SHORT-TERM BOUNCE",
            "CONSOLIDATION",
            "POSSIBLE REVERSAL",
            "MIXED",
            "NO CLEAR STRUCTURE"
        ]
    asyncio.run(_run())
