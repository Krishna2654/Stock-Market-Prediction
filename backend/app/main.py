import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes_instruments import router as instruments_router
from app.api.routes_analysis import router as analysis_router, _analyze_instrument
from app.api.routes_ai import router as ai_router
from app.api.routes_alerts import router as alerts_router
from app.api.routes_backtest import router as backtest_router
from app.api.routes_paper import router as paper_router
from app.api.websocket import ws_router, ws_manager
from app.api.deps import get_current_provider, configured_instruments
from app.alerts.engine import alert_engine
from app.alerts.high_confluence_engine import high_confluence_alert_engine

background_monitor_task = None

async def market_monitor_loop():
    """
    Background worker that warms up market data immediately on startup,
    runs periodically to detect new BOS, CHoCH, and Breakout events across all
    configured instruments, and broadcasts real-time updates via WebSockets.
    """
    print("[Market Monitor] Warming up market data cache on startup...")
    # Allow uvicorn to finish binding
    await asyncio.sleep(1)
    
    while True:
        try:
            provider = get_current_provider()
            for inst in configured_instruments:
                if inst.is_active:
                    try:
                        synthesis = await _analyze_instrument(inst.symbol, inst.ticker, provider)
                        new_alerts = alert_engine.process_synthesis_for_alerts(synthesis)
                        new_high_alerts = high_confluence_alert_engine.process_synthesis_for_high_confluence_alerts(synthesis)
                        
                        # Broadcast synthesis update
                        await ws_manager.broadcast({
                            "type": "SYNTHESIS_UPDATE",
                            "symbol": inst.symbol,
                            "overall_bias": synthesis.overall_bias,
                            "evidence_score": synthesis.evidence_score.total_score,
                            "current_price": synthesis.current_price,
                            "current_state": synthesis.current_state,
                            "latest_event": synthesis.latest_important_event.model_dump() if synthesis.latest_important_event else None
                        })
                        
                        # If standard alerts triggered, broadcast on ALERT_TRIGGERED
                        for alert in new_alerts:
                            await ws_manager.broadcast({
                                "type": "ALERT_TRIGGERED",
                                "alert": alert.model_dump()
                            })

                        # If high-confluence alerts triggered, broadcast on separate HIGH_CONFLUENCE_ALERT_TRIGGERED
                        for hc_alert in new_high_alerts:
                            await ws_manager.broadcast({
                                "type": "HIGH_CONFLUENCE_ALERT_TRIGGERED",
                                "alert": hc_alert.model_dump()
                            })
                    except Exception as e:
                        print(f"[Market Monitor Error for {inst.symbol}]: {e}")
            
            await asyncio.sleep(30)  # Refresh every 30s
        except asyncio.CancelledError:
            print("[Market Monitor] Stopped.")
            break
        except Exception as e:
            print(f"[Market Monitor Loop Exception]: {e}")
            await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    task = asyncio.create_task(market_monitor_loop())
    yield
    # Shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Quantitative multi-timeframe market structure analyzer with Swings, Protected Levels, BOS, CHoCH, Multi-Trendlines, Evidence Score, and AI Summaries.",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include Routers
app.include_router(instruments_router)
app.include_router(analysis_router)
app.include_router(ai_router)
app.include_router(alerts_router)
app.include_router(backtest_router)
app.include_router(paper_router)
app.include_router(ws_router)

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "active_instruments": len(configured_instruments)
    }

@app.get("/", response_class=HTMLResponse)
def root_dashboard(request: Request):
    # Check if request prefers JSON (e.g. curl or API client)
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse({
            "status": "online",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "health": "/health",
            "active_instruments": len(configured_instruments)
        })

    instruments_html = "".join([
        f'<span style="display:inline-block; margin:4px; padding:6px 12px; background:#f1f5f9; border-radius:8px; font-weight:600; font-size:13px; color:#1e293b; border:1px solid #e2e8f0;">● {inst.symbol} <span style="color:#64748b; font-size:11px;">({inst.ticker})</span></span>'
        for inst in configured_instruments
    ])

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{settings.APP_NAME} — Backend API Server</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin:0; padding:0; }}
            body {{
                font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
                background-color: #f8fafc;
                color: #0f172a;
                padding: 40px 20px;
                line-height: 1.5;
            }}
            .container {{
                max-width: 900px;
                margin: 0 auto;
                background: #ffffff;
                border-radius: 20px;
                border: 1px solid #e2e8f0;
                box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
                color: #ffffff;
                padding: 32px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-wrap: wrap;
                gap: 16px;
            }}
            .header h1 {{ font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }}
            .header p {{ font-size: 13px; opacity: 0.9; margin-top: 4px; }}
            .badge-live {{
                display: inline-flex;
                align-items: center;
                gap: 6px;
                background: rgba(255, 255, 255, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.3);
                padding: 6px 14px;
                border-radius: 9999px;
                font-size: 12px;
                font-weight: 700;
                color: #ffffff;
            }}
            .dot {{ width: 8px; height: 8px; border-radius: 50%; background: #4ade80; box-shadow: 0 0 8px #4ade80; }}
            .content {{ padding: 32px; }}
            .section {{ margin-bottom: 28px; }}
            .section h2 {{
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: #64748b;
                margin-bottom: 12px;
                font-weight: 700;
            }}
            .btn-group {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }}
            .btn {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 10px 18px;
                border-radius: 12px;
                font-size: 13px;
                font-weight: 700;
                text-decoration: none;
                transition: all 0.15s ease;
            }}
            .btn-primary {{ background: #2563eb; color: #ffffff; }}
            .btn-primary:hover {{ background: #1d4ed8; }}
            .btn-secondary {{ background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1; }}
            .btn-secondary:hover {{ background: #e2e8f0; }}
            .btn-success {{ background: #059669; color: #ffffff; }}
            .btn-success:hover {{ background: #047857; }}
            .api-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
                gap: 12px;
            }}
            .api-card {{
                padding: 16px;
                border-radius: 14px;
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                text-decoration: none;
                color: inherit;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                transition: all 0.15s ease;
            }}
            .api-card:hover {{
                border-color: #3b82f6;
                background: #eff6ff;
                transform: translateY(-2px);
            }}
            .api-method {{
                font-family: 'JetBrains Mono', monospace;
                font-size: 10px;
                font-weight: 700;
                color: #0284c7;
                background: #e0f2fe;
                padding: 2px 6px;
                border-radius: 4px;
                align-self: flex-start;
                margin-bottom: 6px;
            }}
            .api-title {{ font-size: 13px; font-weight: 700; color: #0f172a; margin-bottom: 4px; }}
            .api-desc {{ font-size: 11px; color: #64748b; font-family: 'JetBrains Mono', monospace; }}
            .footer {{
                background: #f1f5f9;
                padding: 16px 32px;
                border-top: 1px solid #e2e8f0;
                font-size: 12px;
                color: #64748b;
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 8px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>
                    <h1>{settings.APP_NAME}</h1>
                    <p>Real-Time Quantitative Market Structure Analysis Engine (v{settings.APP_VERSION})</p>
                </div>
                <div class="badge-live">
                    <span class="dot"></span>
                    API SERVER ONLINE
                </div>
            </div>

            <div class="content">
                <div class="section">
                    <h2>Quick Navigation</h2>
                    <div class="btn-group">
                        <a href="http://localhost:5173" class="btn btn-success" target="_blank">
                            🖥️ Open Frontend Dashboard (Port 5173)
                        </a>
                        <a href="/docs" class="btn btn-primary">
                            📖 Interactive Swagger API Docs
                        </a>
                        <a href="/redoc" class="btn btn-secondary">
                            📚 ReDoc Documentation
                        </a>
                        <a href="/health" class="btn btn-secondary">
                            💚 Health Check
                        </a>
                    </div>
                </div>

                <div class="section">
                    <h2>Core Market Structure Endpoints (Click to View Live Data)</h2>
                    <div class="api-grid">
                        <a href="/api/analysis/overview" class="api-card">
                            <div>
                                <span class="api-method">GET</span>
                                <div class="api-title">Overview Matrix</div>
                                <div class="api-desc">/api/analysis/overview</div>
                            </div>
                        </a>
                        <a href="/api/analysis/chart/NIFTY%2050?timeframe=15M" class="api-card">
                            <div>
                                <span class="api-method">GET</span>
                                <div class="api-title">NIFTY 50 (15M Chart & Live Price)</div>
                                <div class="api-desc">/api/analysis/chart/NIFTY%2050</div>
                            </div>
                        </a>
                        <a href="/api/analysis/chart/BTC%2FUSD?timeframe=15M" class="api-card">
                            <div>
                                <span class="api-method">GET</span>
                                <div class="api-title">BTC/USD (Crypto Live Chart)</div>
                                <div class="api-desc">/api/analysis/chart/BTC%2FUSD</div>
                            </div>
                        </a>
                        <a href="/api/instruments" class="api-card">
                            <div>
                                <span class="api-method">GET</span>
                                <div class="api-title">Configured Instruments</div>
                                <div class="api-desc">/api/instruments</div>
                            </div>
                        </a>
                        <a href="/api/alerts/notifications" class="api-card">
                            <div>
                                <span class="api-method">GET</span>
                                <div class="api-title">Breakout Alert Feed</div>
                                <div class="api-desc">/api/alerts/notifications</div>
                            </div>
                        </a>
                        <a href="/api/backtest/strategies" class="api-card">
                            <div>
                                <span class="api-method">GET</span>
                                <div class="api-title">Backtesting Strategies</div>
                                <div class="api-desc">/api/backtest/strategies</div>
                            </div>
                        </a>
                    </div>
                </div>

                <div class="section">
                    <h2>Active Tracked Instruments ({len(configured_instruments)})</h2>
                    <div>
                        {instruments_html}
                    </div>
                </div>
            </div>

            <div class="footer">
                <span>FastAPI Backend • Port 8000</span>
                <span>Timezone: Asia/Kolkata (IST) & 24/7 Crypto</span>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
