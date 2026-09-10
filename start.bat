@echo off
title SENTRY-ID Screening System Launcher
echo ====================================================
echo Starting SENTRY-ID Border Screening Platform...
echo ====================================================

echo [1/2] Launching FastAPI Backend on http://127.0.0.1:8000 ...
start "SENTRY-ID Backend" cmd /k "cd /d %~dp0sentry-id-backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 2 /nobreak >nul

echo [2/2] Launching Frontend on http://localhost:5173 ...
start "SENTRY-ID Frontend" cmd /k "cd /d %~dp0fake-id-screening && npm run dev"

echo.
echo Both services are launching in separate windows!
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://localhost:5173
echo ====================================================
