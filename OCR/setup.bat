@echo off
rem Double-click launcher for setup.ps1 (handles PowerShell Execution Policy for you).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if %errorlevel% neq 0 ( pause )