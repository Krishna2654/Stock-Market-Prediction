import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["active_instruments"] >= 10

def test_get_instruments():
    res = client.get("/api/instruments/")
    assert res.status_code == 200
    instruments = res.json()
    assert len(instruments) >= 10
    assert any(i["symbol"] == "NIFTY 50" for i in instruments)

def test_alert_rules():
    res = client.get("/api/alerts/rules")
    assert res.status_code == 200
    rules = res.json()
    assert len(rules) >= 1

def test_trigger_test_alert():
    res = client.post("/api/alerts/test")
    assert res.status_code == 200
    alert = res.json()
    assert alert["symbol"] == "NIFTY 50"
    assert alert["event_type"] in ["RESISTANCE_BREAK", "BULLISH_BOS", "TREND_LINE_BREAK"]

def test_paper_trading_setup():
    res = client.get("/api/paper/setup/NIFTY 50")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
