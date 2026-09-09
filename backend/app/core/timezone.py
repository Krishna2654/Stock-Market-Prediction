from datetime import datetime, timezone, time as dtime, timedelta
import zoneinfo
from typing import Optional, Union, Dict, Any

MARKET_TIMEZONE_STR: str = "Asia/Kolkata"
UTC_TIMEZONE_STR: str = "UTC"

KOLKATA_TZ: zoneinfo.ZoneInfo = zoneinfo.ZoneInfo(MARKET_TIMEZONE_STR)
UTC_TZ: zoneinfo.ZoneInfo = zoneinfo.ZoneInfo(UTC_TIMEZONE_STR)

def is_crypto_ticker(ticker_or_symbol: str) -> bool:
    s = (ticker_or_symbol or "").upper()
    return "BTC" in s or "ETH" in s or "USD" in s or "CRYPTO" in s

def get_market_tz(ticker_or_symbol: Optional[str] = None) -> zoneinfo.ZoneInfo:
    """
    Returns Asia/Kolkata for Indian exchange instruments (NSE/BSE)
    and UTC for 24/7 global cryptocurrency instruments.
    """
    if ticker_or_symbol and is_crypto_ticker(ticker_or_symbol):
        return UTC_TZ
    return KOLKATA_TZ

def parse_iso_datetime(
    ts_val: Union[str, datetime, int, float],
    default_tz: zoneinfo.ZoneInfo = KOLKATA_TZ
) -> datetime:
    """
    Safely parses ISO string, Unix epoch (seconds/milliseconds), or datetime object
    into a timezone-aware datetime.
    Never produces naive datetimes.
    """
    if isinstance(ts_val, datetime):
        if ts_val.tzinfo is None:
            return ts_val.replace(tzinfo=default_tz)
        return ts_val

    if isinstance(ts_val, (int, float)):
        # Check for milliseconds epoch (> 1e11) vs seconds epoch
        seconds = ts_val / 1000.0 if ts_val > 1e11 else float(ts_val)
        return datetime.fromtimestamp(seconds, tz=UTC_TZ)

    s = str(ts_val).strip()
    # Replace space with T if necessary
    if " " in s and "T" not in s:
        s = s.replace(" ", "T")

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=default_tz)
        return dt
    except Exception:
        # Fallback to pandas parsing
        import pandas as pd
        ts = pd.to_datetime(s)
        if ts.tz is None:
            ts = ts.tz_localize(default_tz)
        return ts.to_pydatetime()

def to_utc(dt_val: Union[str, datetime, int, float]) -> datetime:
    """
    Converts any timestamp to timezone-aware UTC datetime.
    """
    dt = parse_iso_datetime(dt_val)
    return dt.astimezone(UTC_TZ)

def to_market_tz(
    dt_val: Union[str, datetime, int, float],
    tz: zoneinfo.ZoneInfo = KOLKATA_TZ
) -> datetime:
    """
    Converts any timestamp to the market's timezone (default Asia/Kolkata).
    """
    dt = parse_iso_datetime(dt_val)
    return dt.astimezone(tz)

def format_market_time(
    dt_val: Union[str, datetime, int, float],
    tz: zoneinfo.ZoneInfo = KOLKATA_TZ,
    include_suffix: bool = True
) -> str:
    """
    Formats timestamp to 'HH:MM IST' (or 'HH:MM UTC' / 'HH:MM').
    """
    dt = to_market_tz(dt_val, tz)
    suffix = " IST" if tz == KOLKATA_TZ else (" UTC" if tz == UTC_TZ else "")
    formatted = dt.strftime("%H:%M")
    return f"{formatted}{suffix}" if include_suffix else formatted

def format_market_datetime(
    dt_val: Union[str, datetime, int, float],
    tz: zoneinfo.ZoneInfo = KOLKATA_TZ
) -> str:
    """
    Formats timestamp to 'YYYY-MM-DD HH:MM:SS IST'
    """
    dt = to_market_tz(dt_val, tz)
    suffix = " IST" if tz == KOLKATA_TZ else (" UTC" if tz == UTC_TZ else "")
    return f"{dt.strftime('%Y-%m-%d %H:%M:%S')}{suffix}"

def now_market_tz(tz: zoneinfo.ZoneInfo = KOLKATA_TZ) -> datetime:
    """
    Returns current timezone-aware datetime in market timezone.
    """
    return datetime.now(tz)

TIMEFRAME_MINUTES_MAP: Dict[str, int] = {
    "1M": 1,
    "3M": 3,
    "5M": 5,
    "15M": 15,
    "30M": 30,
    "1H": 60,
    "60M": 60,
    "2H": 120,
    "4H": 240,
    "240M": 240,
    "1D": 1440,
    "D": 1440,
}

def is_candle_closed(
    candle_timestamp: Union[str, datetime, int, float],
    timeframe: str,
    now: Optional[datetime] = None
) -> bool:
    """
    Determines if a candle has reached its timeframe close boundary.
    A candle is completed ONLY after its actual timeframe duration has elapsed.
    """
    try:
        start_dt = parse_iso_datetime(candle_timestamp)
    except Exception:
        return True

    tf_upper = (timeframe or "15M").upper()
    duration_min = TIMEFRAME_MINUTES_MAP.get(tf_upper, 15)

    close_dt = start_dt + timedelta(minutes=duration_min)

    # Session alignment for Indian equities session: session ends at 15:30 IST
    # Only applies to non-UTC / Indian market timestamps
    is_ist = (start_dt.tzinfo == KOLKATA_TZ) or (
        isinstance(candle_timestamp, str) and ("+05:30" in candle_timestamp or "+0530" in candle_timestamp)
    )
    if is_ist:
        ist_dt = start_dt.astimezone(KOLKATA_TZ)
        if ist_dt.hour == 15 and (ist_dt.minute == 15 or (ist_dt.minute == 0 and duration_min >= 30)):
            close_dt = ist_dt.replace(hour=15, minute=30, second=0, microsecond=0)

    curr_now = now or datetime.now(timezone.utc)
    if curr_now.tzinfo is None:
        curr_now = curr_now.replace(tzinfo=timezone.utc)

    close_utc = close_dt.astimezone(timezone.utc)
    now_utc = curr_now.astimezone(timezone.utc)

    return close_utc <= now_utc
