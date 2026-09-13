# SENTRY-ID Border Screening Platform PowerShell Launcher
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "Starting SENTRY-ID Border Screening Platform..." -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Cyan

$root = $PSScriptRoot
$pyCmd = if (Test-Path "$root\.venv\Scripts\python.exe") { "$root\.venv\Scripts\python.exe" } else { "python" }

Write-Host "[1/2] Launching FastAPI Backend on http://127.0.0.1:8000 ..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\sentry-id-backend'; & '$pyCmd' -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

Start-Sleep -Seconds 2

Write-Host "[2/2] Launching Frontend on http://localhost:5173 ..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\fake-id-screening'; npm run dev"

Write-Host "`nBoth services launched in separate windows!" -ForegroundColor Green
Write-Host "Backend:  http://127.0.0.1:8000" -ForegroundColor White
Write-Host "Frontend: http://localhost:5173" -ForegroundColor White
