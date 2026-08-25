# AI Multi-Timeframe Market Structure Analyzer

A full-stack, production-quality quantitative analysis and decision-support web application designed to analyze financial instruments across four distinct timeframes:

* **4 Hour (4H)** — *Macro Structure & Dominant Anchor*
* **1 Hour (1H)** — *Intermediate Trend & Key Filter*
* **15 Minute (15M)** — *Execution Structure & BOS / CHoCH Setup Zone*
* **5 Minute (5M)** — *Tactical Timing & Immediate Retracements*

The system combines fractal market structure detection (**Higher Highs, Higher Lows, Lower Highs, Lower Lows**), **Break of Structure (BOS)**, **Change of Character (CHoCH)**, dynamic **Support/Resistance clustering**, a deterministic **Evidence Alignment Score (0–100)**, and anti-hallucinatory **Gemini AI Market Summaries** with a modern interactive charting dashboard, real-time alert engine, historical strategy backtester, and educational paper-trading simulator.

---

> [!IMPORTANT]
> **Educational Decision-Support Boundary**: This application is an analytical decision-support tool. It does **NOT** claim to predict future prices with certainty, does **NOT** guarantee trading profits, and does **NOT** place automatic trades. Every output distinguishes between observed market data, calculated indicator values, and AI interpretations.

---

## Key Features

1. **Multi-Timeframe Engine (4H > 1H > 15M > 5M)**:
   - Evaluates each timeframe independently and synthesizes them hierarchically.
   - Higher timeframes possess dominant structural weight over lower timeframes.
   - Prevents minor 5M noise from overriding macro 4H structures.

2. **Fractal Market Structure & Swing Detection**:
   - Dynamic peak/trough identification with configurable `swing_length` and confirmation windows.
   - Categorizes swings sequentially into **HH, HL, LH, LL**.

3. **Break of Structure (BOS) & Change of Character (CHoCH)**:
   - **BOS**: Confirmed candle close beyond previous swing high (Bullish BOS) or swing low (Bearish BOS).
   - **CHoCH**: Detects structural trend flips from Bullish to Bearish (break below HL) or Bearish to Bullish (break above LH).
   - Filters out temporary wicks via candle-close confirmation, volume expansion checks, and ATR break thresholds.

4. **Deterministic Evidence Alignment Score (0–100)**:
   - Programmatically calculated score reflecting structural confluence across all timeframes.
   - Transparent factor breakdown:
     - Structure (+25 pts)
     - HTF Trend Alignment (+25 pts)
     - Momentum (+20 pts)
     - Volume Expansion (+15 pts)
     - Breakout Confirmation (+15 pts)
   - Tiers: Strong Alignment (80-100), Moderate-to-Strong (65-79), Mixed (50-64), Weak (35-49), Conflicting (0-34).

5. **Anti-Hallucinatory AI Summaries (Google Gemini)**:
   - Powered by Google Gemini (`gemini-2.5-flash` / `gemini-2.5-pro`).
   - Strictly restricted to supplied quantitative JSON data — never invents prices, levels, or indicator values.
   - Includes robust offline fallback rule generator when API key is not present.

6. **Interactive Visual Dashboard**:
   - Master Multi-Timeframe Matrix table for up to 10 configured instruments (e.g. NIFTY 50, BANK NIFTY, RELIANCE, TCS, INFY, SBIN, etc.).
   - Interactive Candlestick Chart (4H, 1H, 15M, 5M) with toggleable EMA overlays (20, 50, 200), visual BOS/CHoCH markers, and Support/Resistance lines.
   - 4-Timeframe Breakdown Cards with RSI and Volume gauges.

7. **Historical Strategy Backtester**:
   - Simulates structure-based trading strategies (`BOS_CONTINUATION`, `CHOCH_REVERSAL`, `MULTI_TF_ALIGNMENT`) without look-ahead bias.
   - Evaluates Win Rate, Profit Factor, Max Drawdown %, Net Return %, MAE, MFE, and detailed per-trade audit log with realistic slippage and transaction costs.

8. **Real-time Event Alerts & WebSockets**:
   - Background monitoring loop continuously scans active instruments for new BOS/CHoCH breaks.
   - Dispatches live WebSocket alerts, sound notifications, and persistent event logs with CSV/JSON export.

9. **Modular Data Provider Architecture**:
   - `YahooFinanceProvider`: Live intraday and historical market data for Indian (`^NSEI`, `^NSEBANK`, `RELIANCE.NS`, etc.), US equities, and crypto with 4H resampling and TTL caching.
   - `SimulatedMarketDataProvider`: Deterministic, synthetic multi-timeframe price feed with realistic trend, pullback, BOS, and CHoCH patterns for offline and weekend testing.

---

## Project Structure

```
ai_market_analyzer/
├── backend/
│   ├── app/
│   │   ├── core/               # App configuration, settings, SQLite state
│   │   ├── models/             # Pydantic schemas (Candle, Swings, BOS, CHoCH, Synthesis, AI)
│   │   ├── data/               # Modular Data Providers (Yahoo Finance + Simulated Provider)
│   │   ├── indicators/         # Vectorized indicators (EMA 20/50/200, RSI 14, ATR 14, Volume)
│   │   ├── market_structure/   # Swings, BOS/CHoCH, Support/Resistance, Breakouts
│   │   ├── multi_timeframe/    # Single TF analyzer, MTF synthesis (4H>1H>15M>5M), Evidence Score
│   │   ├── ai/                 # Gemini API integration & deterministic fallback narrative
│   │   ├── alerts/             # Real-time alert rules & notification dispatcher
│   │   ├── backtesting/        # Historical market structure backtest simulator
│   │   ├── paper_trading/      # Educational paper trading & hypothetical R:R calculator
│   │   ├── api/                # FastAPI routes & WebSocket live stream
│   │   └── main.py             # FastAPI entrypoint & background monitoring loop
│   ├── tests/                  # Pytest test suite (100% passing)
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── components/         # React UI (OverviewTable, ChartView, MultiTF, AISummary, etc.)
│   │   ├── services/           # REST API client & WebSocket stream manager
│   │   ├── types/              # TypeScript definitions matching backend models
│   │   ├── App.tsx             # Main dashboard layout and view controller
│   │   └── index.css           # Tailwind CSS glassmorphic dark theme
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
└── start.bat                   # One-click launcher for backend and frontend
```

---

## Quick Start Guide

### 1. Prerequisites
- **Python 3.10+** (Python 3.14 supported)
- **Node.js 18+** (Node.js LTS v24 supported)

### 2. Backend Setup
```bash
cd backend

# Install Python dependencies
pip install -r requirements.txt

# (Optional) Add your Gemini API Key in .env
# GEMINI_API_KEY=your_gemini_api_key_here

# Run backend test suite
pytest tests/ -v

# Start FastAPI server on port 8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
API Documentation will be available at: `http://127.0.0.1:8000/docs`

### 3. Frontend Setup
```bash
cd frontend

# Install Node dependencies
npm install

# Start Vite dev server on port 5173
npm run dev
```
Open your browser at `http://localhost:5173`.

---

## Running the Automated Test Suite

```bash
cd backend
pytest tests/ -v
```

The test suite validates:
- Fractal swing high & swing low detection
- Bullish/Bearish BOS & CHoCH transitions with ATR thresholds
- EMA, RSI, ATR, and Volume calculations
- 4-Timeframe synthesis hierarchy (4H > 1H > 15M > 5M)
- Deterministic 0–100 Evidence Alignment Score calculation
- FastAPI endpoints & WebSocket communication
