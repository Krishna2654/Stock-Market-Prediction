from typing import Dict, List
from app.core.config import settings
from app.data.base import MarketDataProvider
from app.data.yfinance_provider import YahooFinanceProvider
from app.models.schemas import InstrumentConfig

# Shared In-Memory State
configured_instruments: List[InstrumentConfig] = [
    InstrumentConfig(
        symbol=item["symbol"],
        ticker=item["ticker"],
        exchange=item.get("exchange", "NSE"),
        asset_type=item.get("asset_type", "EQUITY"),
        is_active=True
    )
    for item in settings.DEFAULT_INSTRUMENTS
]

from app.data.broker_providers import UpstoxProvider, ZerodhaKiteProvider

# Real Market Data Providers only (No Demo/Simulated in Production)
providers: Dict[str, MarketDataProvider] = {
    "yfinance": YahooFinanceProvider(),
    "upstox": UpstoxProvider(),
    "kite": ZerodhaKiteProvider()
}

current_provider_name: str = "yfinance"

def get_current_provider() -> MarketDataProvider:
    return providers.get(current_provider_name, providers["yfinance"])

def set_current_provider(name: str):
    global current_provider_name
    if name in providers:
        current_provider_name = name
