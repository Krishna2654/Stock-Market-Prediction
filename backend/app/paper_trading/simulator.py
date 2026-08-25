import uuid
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from app.models.schemas import PaperOrder, MultiTimeframeSynthesis

class PaperTradingSimulator:
    """
    Educational & hypothetical paper trading architecture.
    Calculates hypothetical entry, invalidation levels, target zones, and risk/reward.
    Strictly isolated with no live broker connectivity.
    """

    def __init__(self):
        self.orders: List[PaperOrder] = []

    def calculate_hypothetical_setup(
        self,
        synthesis: MultiTimeframeSynthesis,
        account_size: float = 100000.0,
        risk_pct: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculates a hypothetical setup based on current multi-timeframe structure.
        """
        current_p = synthesis.current_price
        bias = synthesis.overall_bias
        inval = synthesis.invalidation_level

        if bias not in ["BULLISH", "BEARISH"] or not inval or inval == current_p:
            return {
                "status": "NO_SETUP",
                "message": "Market structure is currently neutral or conflicting. No clear hypothetical setup."
            }

        direction = "LONG" if bias == "BULLISH" else "SHORT"
        entry_price = current_p
        stop_loss = inval
        risk_per_share = abs(entry_price - stop_loss)

        # Target zones (1:2 and 1:3 R:R)
        if direction == "LONG":
            target_1 = entry_price + (risk_per_share * 2.0)
            target_2 = entry_price + (risk_per_share * 3.0)
        else:
            target_1 = entry_price - (risk_per_share * 2.0)
            target_2 = entry_price - (risk_per_share * 3.0)

        total_risk_capital = account_size * (risk_pct / 100.0)
        quantity = int(total_risk_capital / risk_per_share) if risk_per_share > 0 else 0

        return {
            "status": "HYPOTHETICAL_SETUP_AVAILABLE",
            "symbol": synthesis.symbol,
            "direction": direction,
            "entry_price": round(entry_price, 2),
            "stop_loss": round(stop_loss, 2),
            "target_1_rr2": round(target_1, 2),
            "target_2_rr3": round(target_2, 2),
            "risk_per_unit": round(risk_per_share, 2),
            "risk_reward_ratio": "1 : 2.0 (Target 1) / 1 : 3.0 (Target 2)",
            "hypothetical_quantity": quantity,
            "capital_at_risk": round(total_risk_capital, 2),
            "disclaimer": "This is a hypothetical mathematical calculation for decision-support only. Not financial advice."
        }

    def place_paper_order(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        target: float,
        quantity: float,
        notes: str = ""
    ) -> PaperOrder:
        order = PaperOrder(
            id=str(uuid.uuid4())[:8],
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            quantity=quantity,
            status="OPEN",
            created_at=datetime.now(timezone.utc).isoformat(),
            notes=notes
        )
        self.orders.append(order)
        return order

    def get_paper_orders(self) -> List[PaperOrder]:
        return self.orders[::-1]

paper_simulator = PaperTradingSimulator()
