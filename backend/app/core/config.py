import os
from typing import List, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "Share Market Prediction"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True
    
    # AI Credentials (strictly server-side, never exposed to client)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    # Data Provider: 'yfinance' | 'upstox'
    DEFAULT_DATA_PROVIDER: str = "yfinance"
    
    # Market Timezone
    TIMEZONE: str = "Asia/Kolkata"
    
    # Default Configured Instruments (Indian Equities, Indices & 24/7 Crypto)
    DEFAULT_INSTRUMENTS: List[Dict[str, str]] = [
        {"symbol": "BTC/USD", "ticker": "BTC-USD", "exchange": "CRYPTO", "asset_type": "CRYPTO"},
        {"symbol": "NIFTY 50", "ticker": "^NSEI", "exchange": "NSE", "asset_type": "INDEX"},
        {"symbol": "BANK NIFTY", "ticker": "^NSEBANK", "exchange": "NSE", "asset_type": "INDEX"},
        {"symbol": "RELIANCE", "ticker": "RELIANCE.NS", "exchange": "NSE", "asset_type": "EQUITY"},
        {"symbol": "HDFCBANK", "ticker": "HDFCBANK.NS", "exchange": "NSE", "asset_type": "EQUITY"},
        {"symbol": "ICICIBANK", "ticker": "ICICIBANK.NS", "exchange": "NSE", "asset_type": "EQUITY"},
        {"symbol": "TCS", "ticker": "TCS.NS", "exchange": "NSE", "asset_type": "EQUITY"},
        {"symbol": "INFY", "ticker": "INFY.NS", "exchange": "NSE", "asset_type": "EQUITY"},
        {"symbol": "SBIN", "ticker": "SBIN.NS", "exchange": "NSE", "asset_type": "EQUITY"},
        {"symbol": "BHARTI AIRTEL", "ticker": "BHARTIARTL.NS", "exchange": "NSE", "asset_type": "EQUITY"}
    ]
    
    # Timeframes (Strict Priority: 4H > 1H > 15M > 5M)
    TIMEFRAMES: List[str] = ["4H", "1H", "15M", "5M"]
    
    # Quantitative Analysis Defaults
    DEFAULT_SWING_LENGTH: int = 5
    DEFAULT_CONFIRMATION_CANDLES: int = 2
    DEFAULT_MIN_BREAK_PCT: float = 0.0005  # 0.05%
    DEFAULT_MIN_BREAK_ATR_MULTIPLE: float = 0.15
    
    # Multi-Trendline Engine Defaults
    MAX_TRENDLINES_PER_DIRECTION: int = 5
    TRENDLINE_ATR_TOLERANCE: float = 0.30
    TRENDLINE_MIN_TOUCHES: int = 2
    
    # Precision Breakout & Pattern Alert Defaults
    GOOD_VOLUME_THRESHOLD: float = 1.20
    W_M_SWING_TOLERANCE_ATR: float = 0.75
    PATTERN_PRICE_TOLERANCE_ATR: float = 0.75
    MIN_PATTERN_DEPTH_ATR: float = 1.50
    MIN_W_M_SWING_SEPARATION: int = 5
    MIN_PATTERN_BAR_SPACING: int = 5
    MIN_BREAKOUT_DISTANCE_ATR: float = 0.10
    MIN_W_M_HIGH_CONFLUENCE_SCORE: int = 75
    
    # Indicator Periods
    EMA_FAST: int = 20
    EMA_MID: int = 50
    EMA_SLOW: int = 200
    RSI_PERIOD: int = 14
    ATR_PERIOD: int = 14
    
    # Stale Data Threshold in minutes
    STALE_DATA_MINUTES: int = 60 * 24
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    
    # Database
    DATABASE_PATH: str = "market_analyzer.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
