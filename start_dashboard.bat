@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   Crypto Trading System - one-click start
echo   (backend + frontend + browser)
echo ============================================================
echo.

REM ---------- 0. check python / node ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found. Install Python 3.11+ and add to PATH.
    pause & exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] node not found. Install Node.js and retry.
    pause & exit /b 1
)

REM ---------- 1. backend deps ----------
echo [1/5] Installing backend deps (pip install -r requirements.txt) ...
python -m pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] backend deps install failed. & pause & exit /b 1 )

REM ---------- 2/3. frontend deps (npm; package-lock.json is the source of truth) ----------
REM Standardize on npm: it ships with Node and package-lock.json pins react-is
REM (recharts peer dep). pnpm-lock.yaml is stale on that dep, so we don't use pnpm.
echo [2/5] Installing frontend deps (npm install) ...
pushd frontend
call npm install --legacy-peer-deps
if errorlevel 1 ( echo [ERROR] frontend deps install failed. & popd & pause & exit /b 1 )
popd

REM ---------- 4. start backend + frontend (each in its own window) ----------
REM Note: port 3000 is used by Grafana (docker-compose), so frontend uses 3001.
echo [4/5] Starting backend (http://localhost:8000) and frontend (http://localhost:3001) ...
set "PYTHONPATH=%~dp0"
start "crypto-backend" /d "%~dp0" cmd /k "python -m uvicorn src.api.app:app --port 8000"
start "crypto-frontend" /d "%~dp0frontend" cmd /k "npm run dev -- --port 3001"

REM ---------- 5. wait for frontend, then open browser ----------
echo [5/5] Waiting for frontend, then opening browser ...
set /a tries=0
:waitloop
timeout /t 2 /nobreak >nul
set /a tries+=1
curl -s -o nul http://localhost:3001 >nul 2>nul
if not errorlevel 1 goto ready
if !tries! geq 60 (
    echo [INFO] Timeout. Please open http://localhost:3001 manually.
    goto ready
)
goto waitloop

:ready
start "" http://localhost:3001
echo.
echo Started. Backend and frontend run in separate windows; close them to stop.
echo Backend: http://localhost:8000   Frontend: http://localhost:3001
echo.
endlocal
