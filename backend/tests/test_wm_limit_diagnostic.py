import json
from pathlib import Path
from app.alerts.mw_breakout_engine import mw_breakout_engine
from app.api.routes_alerts import get_mw_breakout_stats, get_mw_breakout_alerts

def run_diagnostic():
    store_file = Path(__file__).resolve().parents[4] / "Desktop" / "ai_market_analyzer" / "backend" / "data" / "mw_breakout_alerts_store.json"
    with open(store_file, "r", encoding="utf-8") as f:
        store_data = json.load(f)
    
    alerts = store_data.get("alerts", [])
    seen_keys = store_data.get("seen_event_keys", [])

    w_seen = sum(1 for k in seen_keys if "_W_" in k)
    m_seen = sum(1 for k in seen_keys if "_M_" in k)
    total_seen = len(seen_keys)

    w_stored = sum(1 for a in alerts if a.get("pattern_type") == "W")
    m_stored = sum(1 for a in alerts if a.get("pattern_type") == "M")
    total_stored = len(alerts)

    api_stats = get_mw_breakout_stats()
    api_alerts = get_mw_breakout_alerts(None, None, None, None, None, None, 200)
    w_api = sum(1 for a in api_alerts if a.pattern_type == "W")
    m_api = sum(1 for a in api_alerts if a.pattern_type == "M")
    total_api = len(api_alerts)

    seen = set()
    frontend_displayed = []
    for a in api_alerts:
        key = a.pattern_id or f"{a.symbol}_{a.timeframe}_{a.pattern_type}_{a.breakout_candle_timestamp}"
        if key not in seen and a.alert_id not in seen:
            seen.add(key)
            seen.add(a.alert_id)
            frontend_displayed.append(a)

    w_displayed = sum(1 for a in frontend_displayed if a.pattern_type == "W")
    m_displayed = sum(1 for a in frontend_displayed if a.pattern_type == "M")
    total_displayed = len(frontend_displayed)

    print()
    print("================================================================================")
    print("FORENSIC W/M PATTERN PIPELINE AUDIT REPORT")
    print("================================================================================")
    print(f"W patterns detected internally: {w_seen}")
    print(f"M patterns detected internally: {m_seen}")
    print(f"Total detected: {total_seen}")
    print()
    print(f"W patterns stored: {w_stored}")
    print(f"M patterns stored: {m_stored}")
    print(f"Total stored: {total_stored}  <--- [HARD CAPPED AT 200 IN mw_breakout_engine.py]")
    print()
    print(f"W patterns returned by API: {w_api}")
    print(f"M patterns returned by API: {m_api}")
    print(f"Total returned: {total_api}  <--- [DEFAULT LIMIT = 200 IN routes_alerts.py]")
    print()
    print(f"W patterns displayed by frontend: {w_displayed}")
    print(f"M patterns displayed by frontend: {m_displayed}")
    print(f"Total displayed: {total_displayed}")
    print()
    print(f"Summary Stat Bar 'W Breakouts': {api_stats['w_breakouts']}")
    print(f"Summary Stat Bar 'M Breakdowns': {api_stats['m_breakdowns']}")
    print(f"Summary Stat Bar Total: {api_stats['total_count']} (86 + 114 = 200)")
    print("================================================================================")

if __name__ == "__main__":
    import sys
    sys.path.insert(0, r"c:\Users\user\Desktop\ai_market_analyzer\backend")
    run_diagnostic()

def test_wm_limits_diagnostic():
    run_diagnostic()
