import os
import json
from typing import Optional
from datetime import datetime, timezone
from app.models.schemas import MultiTimeframeSynthesis, AIAnalysisSummary
from app.ai.fallback_summarizer import FallbackSummarizer
from app.core.config import settings

class GeminiAnalyzer:
    """
    Google GenAI SDK Integration for anti-hallucinatory market structure summarization.
    Strictly constrained by quantitative JSON inputs.
    """

    SYSTEM_INSTRUCTION = """
You are an expert Quantitative Technical Analyst and Market Structure AI assistant.
Your task is to interpret and summarize the provided structured multi-timeframe market structure data (4H, 1H, 15M, 5M).

CRITICAL ANTI-HALLUCINATION & COMPLIANCE RULES:
1. You must ONLY reason from the supplied quantitative JSON data.
2. NEVER invent prices, levels, indicators, or BOS/CHoCH events that are not in the payload.
3. NEVER claim to predict the future with certainty. NEVER say "Price will definitely rise/fall" or "guaranteed breakout/profit".
4. Always frame conclusions in terms of "Current evidence indicates...", "Higher timeframes remain aligned...", "The setup is invalidated if price closes beyond...".
5. Strictly adhere to the requested markdown sections:
   ## Market Summary
   ## 4H
   ## 1H
   ## 15M
   ## 5M
   ## Multi-Timeframe Interpretation
   ## Important Levels
   ## Current State
   ## Risk Note
"""

    @classmethod
    async def generate_ai_summary(
        cls,
        synthesis: MultiTimeframeSynthesis,
        api_key: Optional[str] = None
    ) -> AIAnalysisSummary:
        key = api_key or os.environ.get("GEMINI_API_KEY") or settings.GEMINI_API_KEY
        
        # If no key available, generate formatted analytical fallback
        if not key or key.strip() == "":
            markdown_content = FallbackSummarizer.generate_summary(synthesis)
            return AIAnalysisSummary(
                symbol=synthesis.symbol,
                generated_at=datetime.now(timezone.utc).isoformat(),
                model_used="Quantitative Rule Engine (Offline/Fallback)",
                overall_bias=synthesis.overall_bias,
                evidence_alignment_score=synthesis.evidence_score.total_score,
                summary_markdown=markdown_content,
                raw_synthesis=synthesis
            )

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=key)
            
            # Prepare compact structured JSON
            payload = {
                "symbol": synthesis.symbol,
                "ticker": synthesis.ticker,
                "current_price": synthesis.current_price,
                "overall_bias": synthesis.overall_bias,
                "current_state": synthesis.current_state,
                "evidence_alignment_score": synthesis.evidence_score.total_score,
                "score_category": synthesis.evidence_score.category,
                "timeframes": {
                    tf_name: {
                        "trend": tf.trend,
                        "structure_type": tf.structure_type,
                        "important_level": tf.important_level,
                        "rsi": tf.indicators.rsi_14,
                        "ema20": tf.indicators.ema_20,
                        "ema50": tf.indicators.ema_50,
                        "ema200": tf.indicators.ema_200,
                        "breakout_status": tf.breakout_status,
                        "latest_break": tf.latest_event.model_dump() if tf.latest_event else None
                    }
                    for tf_name, tf in synthesis.timeframes.items()
                },
                "key_supports": synthesis.key_supports,
                "key_resistances": synthesis.key_resistances,
                "invalidation_level": synthesis.invalidation_level,
                "synthesis_rationale": synthesis.synthesis_rationale
            }

            prompt = f"""
Analyze the following multi-timeframe market structure data and generate the complete analytical summary in the required format:

DATA JSON:
{json.dumps(payload, indent=2)}
"""

            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=cls.SYSTEM_INSTRUCTION,
                    temperature=0.2,
                    max_output_tokens=1500
                )
            )

            text = response.text if response and response.text else FallbackSummarizer.generate_summary(synthesis)

            return AIAnalysisSummary(
                symbol=synthesis.symbol,
                generated_at=datetime.now(timezone.utc).isoformat(),
                model_used=f"Google Gemini ({settings.GEMINI_MODEL})",
                overall_bias=synthesis.overall_bias,
                evidence_alignment_score=synthesis.evidence_score.total_score,
                summary_markdown=text,
                raw_synthesis=synthesis
            )

        except Exception as e:
            print(f"[GeminiAnalyzer] API call failed: {e}. Using deterministic fallback.")
            markdown_content = FallbackSummarizer.generate_summary(synthesis)
            return AIAnalysisSummary(
                symbol=synthesis.symbol,
                generated_at=datetime.now(timezone.utc).isoformat(),
                model_used=f"Deterministic Engine (Gemini API Note: {str(e)[:50]})",
                overall_bias=synthesis.overall_bias,
                evidence_alignment_score=synthesis.evidence_score.total_score,
                summary_markdown=markdown_content,
                raw_synthesis=synthesis
            )
