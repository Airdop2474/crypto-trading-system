@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   Paper Trading - 60-day continuous run (--no-db)
echo ============================================================
echo.

REM ---------- check python ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found. Install Python 3.11+ and add to PATH.
    pause & exit /b 1
)

REM ---------- prepare log file (timestamped) ----------
REM Build YYYY-MM-DD_HHMMSS from PowerShell to avoid locale-dependent %date%/%time%.
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"`) do set "TS=%%t"
if not exist "logs" mkdir "logs"
set "LOGFILE=%~dp0logs\paper_60d_%TS%.log"

set "PYTHONPATH=%~dp0"

echo Symbol/timeframe : BTC/USDT 4h (daemon defaults)
echo Days             : 60   Mode: --no-db (no database, daily reports only)
echo Log file         : !LOGFILE!
echo.
echo Notes:
echo   - Keep this window open. Do NOT let the PC sleep, or the run dies.
echo   - Ctrl+C to stop. Re-run this .bat WITHOUT --fresh to resume from checkpoint.
echo   - Health check (another terminal): python scripts\check_daemon_health.py
echo   - If risk-paused: create empty file data\paper_daemon_state.json.resume
echo.

REM ---------- run, tee to console + log file ----------
REM Tee-Object shows progress live AND writes the log; 2>&1 merges stderr.
powershell -NoProfile -Command "python scripts/run_paper_trading_daemon.py --days 60 --no-db 2>&1 | Tee-Object -FilePath '!LOGFILE!'"

echo.
echo Daemon exited. Log saved to: !LOGFILE!
echo Daily reports: data\reports\paper\daily\
pause
endlocal
