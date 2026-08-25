from app.models.schemas import MultiTimeframeSynthesis

class FallbackSummarizer:
    """
    Deterministic rule-based analytical narrative generator.
    Produces formatted Markdown summaries matching the exact required structure
    without hallucination when offline or when no Gemini API key is configured.
    """

    @classmethod
    def generate_summary(cls, synthesis: MultiTimeframeSynthesis) -> str:
        tf_4h = synthesis.timeframes.get("4H")
        tf_1h = synthesis.timeframes.get("1H")
        tf_15m = synthesis.timeframes.get("15M")
        tf_5m = synthesis.timeframes.get("5M")

        h4_break = tf_4h.latest_event.event_type.replace("_", " ") if tf_4h and tf_4h.latest_event else "No recent break"
        h1_break = tf_1h.latest_event.event_type.replace("_", " ") if tf_1h and tf_1h.latest_event else "No recent break"
        m15_break = tf_15m.latest_event.event_type.replace("_", " ") if tf_15m and tf_15m.latest_event else "No recent break"
        m5_break = tf_5m.latest_event.event_type.replace("_", " ") if tf_5m and tf_5m.latest_event else "No recent break"

        sup_str = ", ".join([f"{s:.2f}" for s in synthesis.key_supports[:3]]) if synthesis.key_supports else "None identified"
        res_str = ", ".join([f"{r:.2f}" for r in synthesis.key_resistances[:3]]) if synthesis.key_resistances else "None identified"
        
        inval_str = f"{synthesis.invalidation_level:.2f}" if synthesis.invalidation_level else "N/A"

        md = f"""## Market Summary

**Overall Bias**: {synthesis.overall_bias}
**Evidence Alignment**: {synthesis.evidence_score.total_score}/100 ({synthesis.evidence_score.category})
**Current Price**: {synthesis.current_price:.2f}

---

## 4H (Macro Structure)
* **Trend**: {tf_4h.trend if tf_4h else 'N/A'}
* **Structure**: {tf_4h.structure_type if tf_4h else 'N/A'}
* **Latest Break**: {h4_break}
* **Important Level**: {tf_4h.important_level if tf_4h and tf_4h.important_level else 'N/A'}

## 1H (Intermediate Trend)
* **Trend**: {tf_1h.trend if tf_1h else 'N/A'}
* **Structure**: {tf_1h.structure_type if tf_1h else 'N/A'}
* **Latest Break**: {h1_break}
* **Important Level**: {tf_1h.important_level if tf_1h and tf_1h.important_level else 'N/A'}

## 15M (Execution Structure)
* **Trend**: {tf_15m.trend if tf_15m else 'N/A'}
* **Structure**: {tf_15m.structure_type if tf_15m else 'N/A'}
* **Latest Break**: {m15_break}
* **Important Level**: {tf_15m.important_level if tf_15m and tf_15m.important_level else 'N/A'}

## 5M (Tactical Timing)
* **Trend**: {tf_5m.trend if tf_5m else 'N/A'}
* **Structure**: {tf_5m.structure_type if tf_5m else 'N/A'}
* **Latest Break**: {m5_break}
* **Important Level**: {tf_5m.important_level if tf_5m and tf_5m.important_level else 'N/A'}

---

## Multi-Timeframe Interpretation
{synthesis.synthesis_rationale}
The higher timeframes (4H and 1H) establish the dominant macro direction. The lower timeframes (15M and 5M) indicate {synthesis.short_term_state.lower()}.

## Important Levels
* **Key Support Zones**: {sup_str}
* **Key Resistance Zones**: {res_str}
* **Structural Invalidation Level**: {inval_str}

## Current State
**{synthesis.current_state}**
*Confirmation status*: {synthesis.confirmation_state}

## Risk Note
The current analytical interpretation remains valid as long as price maintains respect for the structural invalidation level at **{inval_str}**. A confirmed close beyond this level would signal a potential structural failure or trend change. *Note: This is an analytical decision-support tool, not financial advice or a guaranteed forecast.*
"""
        return md
