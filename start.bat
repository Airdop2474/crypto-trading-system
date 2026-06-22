@echo off
chcp 936>nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  +==========================================================+
echo  ^|     Crypto Trading System - 一键安装启动                ^|
echo  ^|     Backend :8000  ^|  Frontend :3001  ^|  Grafana :3000 ^|
echo  +==========================================================+
echo.

REM ========================================================================
REM  Step 0: 环境检查
REM ========================================================================
echo [0/6] 检查环境 ...

where python >nul 2>nul
if errorlevel 1 (
    echo   [X] Python 未找到。请安装 Python 3.11+ 并勾选 "Add to PATH"
    echo       https://www.python.org/downloads/
    pause & exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   Python %PYVER% OK

where node >nul 2>nul
if errorlevel 1 (
    echo   [X] Node.js 未找到。请安装 Node.js 18+
    echo       https://nodejs.org/
    pause & exit /b 1
)
for /f "tokens=1 delims=v" %%v in ('node --version 2^>^&1') do set NODEVER=%%v
echo   Node.js %NODEVER% OK

set DOCKER_OK=0
where docker >nul 2>nul
if not errorlevel 1 (
    docker info >nul 2>nul
    if not errorlevel 1 (
        set DOCKER_OK=1
        echo   Docker OK
    ) else (
        echo   [!] Docker 已安装但未运行。基础设施（DB/Redis/Grafana）将跳过。
    )
) else (
    echo   [!] Docker 未安装。基础设施（DB/Redis/Grafana）将跳过，核心功能不受影响。
)
echo.

REM ========================================================================
REM  Step 1: 配置 API Keys
REM ========================================================================
echo [1/6] 配置 API Keys ...

REM 如果 .env 不存在，从模板创建
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo   已从 .env.example 创建 .env
    ) else (
        echo   [X] .env.example 不存在，无法创建配置文件
        pause & exit /b 1
    )
)

REM 检测 .env 中的 key 是否还是占位符，如果是则提示用户填写
set NEED_CONFIG=0

REM --- API Token（前后端通信密钥，必填） ---
findstr /C:"API_TOKEN=change-me" .env >nul 2>nul
if not errorlevel 1 set NEED_CONFIG=1
findstr /C:"API_TOKEN=" .env >nul 2>nul
if errorlevel 1 set NEED_CONFIG=1

REM --- Binance API（选填） ---
findstr /C:"BINANCE_API_KEY=your_testnet" .env >nul 2>nul
if not errorlevel 1 set NEED_CONFIG=1

REM --- LLM API（选填） ---
findstr /C:"LLM_API_KEY=" .env >nul 2>nul
if errorlevel 1 set NEED_CONFIG=1

if "!NEED_CONFIG!"=="1" (
    echo.
    echo   +---------------------------------------------+
    echo   ^|  请输入 API Keys（直接回车跳过可稍后填写 .env）^|
    echo   +---------------------------------------------+
    echo.

    REM API Token - 自动生成一个随机 token
    for /f %%a in ('python -c "import secrets; print(secrets.token_hex(16))" 2^>nul') do set RND_TOKEN=%%a
    if not defined RND_TOKEN set RND_TOKEN=crypto-trading-dev-token

    echo   [1] API Token（前后端通信密钥）
    echo       留空使用自动生成: !RND_TOKEN!
    set /p "USER_TOKEN=       输入: "
    if "!USER_TOKEN!"=="" set USER_TOKEN=!RND_TOKEN!

    REM 写入 .env
    python -c "import re; p='.env'; t=open(p,encoding='utf-8').read(); t=re.sub(r'API_TOKEN=.*','API_TOKEN=!USER_TOKEN!',t); open(p,'w',encoding='utf-8').write(t)"
    echo       ^> API_TOKEN 已设置

    echo.
    echo   [2] Binance Testnet API Key（获取地址: https://testnet.binance.vision/）
    set /p "BN_KEY=       Key（回车跳过）: "
    if not "!BN_KEY!"=="" (
        python -c "import re; p='.env'; t=open(p,encoding='utf-8').read(); t=re.sub(r'BINANCE_API_KEY=.*','BINANCE_API_KEY=!BN_KEY!',t); open(p,'w',encoding='utf-8').write(t)"
        echo       ^> BINANCE_API_KEY 已设置
    ) else (
        echo       ^> 已跳过（Paper Trading 模式无需此 Key）
    )

    echo.
    echo   [3] Binance Testnet Secret
    set /p "BN_SECRET=       Secret（回车跳过）: "
    if not "!BN_SECRET!"=="" (
        python -c "import re; p='.env'; t=open(p,encoding='utf-8').read(); t=re.sub(r'BINANCE_SECRET=.*','BINANCE_SECRET=!BN_SECRET!',t); open(p,'w',encoding='utf-8').write(t)"
        echo       ^> BINANCE_SECRET 已设置
    ) else (
        echo       ^> 已跳过
    )

    echo.
    echo   [4] LLM 配置（策略进化 AI 解读，支持 DeepSeek/智谱/Ollama 等）
    echo       1=OpenAI兼容协议  2=Anthropic协议  3=跳过
    set /p "LLM_CHOICE=       选择(1/2/3，回车跳过): "
    set LLM_PROV=
    if "!LLM_CHOICE!"=="1" set LLM_PROV=openai
    if "!LLM_CHOICE!"=="2" set LLM_PROV=anthropic
    if not defined LLM_PROV (
        echo       ^> 已跳过，将使用本地规则解读
    ) else (
        echo.
        echo       API Key:
        set /p "LLM_KEY=       Key: "
        echo.
        echo       Base URL（留空用官方默认，常用: DeepSeek https://api.deepseek.com/v1）
        set /p "LLM_URL=       URL（回车跳过）: "
        echo.
        echo       模型（留空用默认: openai=gpt-4o-mini / anthropic=claude-sonnet-4-20250514）
        set /p "LLM_MOD=       Model（回车跳过）: "
        python scripts\set_llm_env.py --provider "!LLM_PROV!" --key "!LLM_KEY!" --url "!LLM_URL!" --model "!LLM_MOD!"
        echo       ^> LLM 配置已更新: provider=!LLM_PROV!
    )
    echo.
) else (
    echo   .env 已配置，跳过。
    echo.
)

REM 确保前端 .env.local 存在且包含 API Token
if not exist frontend\.env.local (
    if exist frontend\.env.local.example (
        copy frontend\.env.local.example frontend\.env.local >nul
    ) else (
        echo NEXT_PUBLIC_API_BASE=http://localhost:8000> frontend\.env.local
    )
)

REM 同步 API Token 到前端
for /f "tokens=1,* delims==" %%a in ('findstr /C:"API_TOKEN=" .env 2^>nul') do set API_TOKEN_VAL=%%b
if defined API_TOKEN_VAL (
    findstr /C:"NEXT_PUBLIC_API_TOKEN" frontend\.env.local >nul 2>nul
    if errorlevel 1 (
        echo NEXT_PUBLIC_API_TOKEN=!API_TOKEN_VAL!>> frontend\.env.local
    ) else (
        python -c "import re; p='frontend/.env.local'; t=open(p,encoding='utf-8').read(); t=re.sub(r'NEXT_PUBLIC_API_TOKEN=.*','NEXT_PUBLIC_API_TOKEN=!API_TOKEN_VAL!',t); open(p,'w',encoding='utf-8').write(t)"
    )
)

REM ========================================================================
REM  Step 2: 安装 Python 依赖
REM ========================================================================
echo [2/6] 安装 Python 依赖 ...
python -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo   [X] Python 依赖安装失败
    pause & exit /b 1
)
echo   OK

REM ========================================================================
REM  Step 3: 安装前端依赖
REM ========================================================================
echo [3/6] 安装前端依赖 ...
pushd frontend
call npm install --legacy-peer-deps --silent 2>nul
if errorlevel 1 (
    echo   [X] 前端依赖安装失败
    popd & pause & exit /b 1
)
popd
echo   OK

REM ========================================================================
REM  Step 4: 启动基础设施（Docker，可选）
REM ========================================================================
echo [4/6] 基础设施 ...
if "!DOCKER_OK!"=="1" (
    docker compose stop trading_system paper_daemon 2>nul
    docker compose up -d timescaledb redis grafana 2>nul
    if not errorlevel 1 (
        echo   TimescaleDB + Redis + Grafana 已启动
    ) else (
        echo   [!] Docker Compose 启动失败，核心功能不受影响
    )
) else (
    echo   跳过（无 Docker）
)

REM ========================================================================
REM  Step 5: 启动后端 + 前端
REM ========================================================================
echo [5/6] 启动服务 ...
echo.
set "PYTHONPATH=%~dp0"

REM 先杀掉可能残留的旧进程
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000.*LISTENING"') do (
    tasklist /FI "PID eq %%p" 2>nul | findstr /I "python" >nul && taskkill /PID %%p /F >nul 2>nul
)
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3001.*LISTENING"') do (
    tasklist /FI "PID eq %%p" 2>nul | findstr /I "node" >nul && taskkill /PID %%p /F >nul 2>nul
)

REM 启动后端
start "CryptoTrading-Backend" /d "%~dp0" cmd /c "title Backend API :8000 & color 0A & echo. & echo   Backend API running at http://localhost:8000 & echo   Swagger docs: http://localhost:8000/docs & echo. & python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000 & pause"

REM 启动前端
start "CryptoTrading-Frontend" /d "%~dp0frontend" cmd /c "title Frontend :3001 & color 0B & echo. & echo   Frontend running at http://localhost:3001 & echo. & call npm run dev -- --port 3001 & pause"

echo   Backend  → http://localhost:8000
echo   Frontend → http://localhost:3001
echo   API Docs → http://localhost:8000/docs
if "!DOCKER_OK!"=="1" echo   Grafana  → http://localhost:3000

REM ========================================================================
REM  Step 6: 等待前端就绪，打开浏览器
REM ========================================================================
echo [6/6] 等待前端就绪 ...

set /a tries=0
:waitloop
timeout /t 2 /nobreak >nul
set /a tries+=1
curl -s -o nul http://localhost:3001 >nul 2>nul
if not errorlevel 1 goto open_browser
if !tries! geq 45 (
    echo   超时，请手动打开 http://localhost:3001
    goto done
)
echo   等待中 ... (!tries!/45)
goto waitloop

:open_browser
echo.
echo   正在打开浏览器 ...
start "" http://localhost:3001

:done
echo.
echo  +==========================================================+
echo  ^|  系统已启动！                                            ^|
echo  ^|                                                          ^|
echo  ^|  前端界面: http://localhost:3001                         ^|
echo  ^|  后端 API: http://localhost:8000                         ^|
echo  ^|  API 文档: http://localhost:8000/docs                    ^|
echo  ^|                                                          ^|
echo  ^|  关闭 Backend / Frontend 窗口即可停止服务               ^|
echo  +==========================================================+
echo.
endlocal
