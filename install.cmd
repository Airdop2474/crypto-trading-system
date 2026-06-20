@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   Crypto Trading System - One-Click Install ^& Start
echo ============================================================
echo.

REM ---------- 0. prerequisites ----------
echo [0/5] Checking prerequisites ...

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ from https://python.org
    echo         and make sure "Add to PATH" is checked during install.
    pause & exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install Node.js 18+ from https://nodejs.org
    pause & exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
    echo [WARN]  Docker not found. Infrastructure services (TimescaleDB, Redis,
    echo        Grafana) will not start. Install Docker Desktop to enable them.
    echo        The core trading system can still run without Docker.
    echo.
)

echo        Python: OK   Node.js: OK
echo.

REM ---------- 1. create .env from template ----------
echo [1/5] Setting up environment ...
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo        Created .env from .env.example - EDIT IT with your keys!
    ) else (
        echo [WARN]  .env.example not found. Create .env manually.
    )
) else (
    echo        .env already exists - skipping.
)

REM ---------- 2. python deps ----------
echo [2/5] Installing Python dependencies ...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Python dependency install failed.
    pause & exit /b 1
)

REM ---------- 3. frontend deps ----------
echo [3/5] Installing frontend dependencies ...
pushd frontend
call npm install --legacy-peer-deps
if errorlevel 1 (
    echo [ERROR] Frontend dependency install failed.
    popd & pause & exit /b 1
)
popd

REM ---------- 4. infrastructure (optional) ----------
echo [4/5] Starting infrastructure services (requires Docker) ...
where docker >nul 2>nul
if not errorlevel 1 (
    docker compose up -d 2>nul
    if errorlevel 1 (
        echo [WARN]  Docker Compose failed - check docker-compose.yml
    ) else (
        echo        TimescaleDB, Redis, Grafana started.
    )
) else (
    echo        Skipping - Docker not available.
)

REM ---------- 5. launch ----------
echo [5/5] Starting trading system ...
echo.
echo   Backend API :  http://localhost:8000
echo   Frontend    :  http://localhost:3001  ^(Grafana uses port 3000^)
echo   API Docs    :  http://localhost:8000/docs
echo.
echo   Starting servers in separate windows...
echo.

set "PYTHONPATH=%~dp0"
start "crypto-backend" /d "%~dp0" cmd /k "title Backend API (port 8000) ^& python -m uvicorn src.api.app:app --port 8000"
start "crypto-frontend" /d "%~dp0frontend" cmd /k "title Frontend (port 3001) ^& npm run dev -- --port 3001"

REM Wait for frontend, then open browser
set /a tries=0
:waitloop
timeout /t 2 /nobreak >nul
set /a tries+=1
curl -s -o nul http://localhost:3001 >nul 2>nul
if not errorlevel 1 goto ready
if !tries! geq 60 (
    echo [INFO] Timeout - open http://localhost:3001 manually.
    goto done
)
goto waitloop

:ready
start "" http://localhost:3001

:done
echo.
echo ============================================================
echo   System started!
echo   Close the server windows to stop.
echo ============================================================
echo.
endlocal
