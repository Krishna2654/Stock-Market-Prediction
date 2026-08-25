@echo off
echo ===================================================
echo   AI Multi-Timeframe Market Structure Analyzer
echo ===================================================
echo Starting FastAPI Backend (Port 8000)...
start "Market Analyzer Backend" cmd /k "cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo Starting React Vite Frontend (Port 5173)...
start "Market Analyzer Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Both servers are launching!
echo Backend API: http://127.0.0.1:8000/docs
echo Frontend UI: http://localhost:5173
echo.
