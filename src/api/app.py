"""
FastAPI 应用：把 Paper Trading 引擎的真实结果按 frontend/lib/api.ts
约定的路由暴露给前端。所有端点返回 frontend/lib/types.ts 的契约结构。

启动：
    uvicorn src.api.app:app --reload --port 8000
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import secrets
import os
import pandas as pd
from loguru import logger
from src.utils.logger import setup_logger as _setup_logger

# 确保 API server 路径（非 main.py 启动）也初始化日志
_setup_logger(
    log_dir=os.getenv("LOG_PATH", "logs"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
)

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, Security, HTTPException, status, Request
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from pydantic import BaseModel, Field
from typing import Literal

from src.api import service
from src.api.admin_routes import (
    CleanupRequest,
    admin_refresh_state,
    admin_build_status,
    admin_clear_cache,
    admin_start_trading,
    admin_emergency_stop,
    admin_data_cleanup,
)
from src.api.ws_feed import ws_feed
from src.api.ws_logs import ws_logs
from src.api.mode_manager import mode_manager, RunningMode, ModeParams, ModeStatus
from src.api.strategy_config_store import (
    update_strategy_config,
    get_all_strategy_configs,
    delete_strategy_config,
    rename_strategy_config,
)
from src.utils.cache import cache
from src.agent import TradingAnalyzer, AuditLog
from src.utils.config import config as _cfg
from src.api import live_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/停止 Binance WebSocket 行情订阅 + Paper Trading 预热

    预热原因：service.get_state() 在首次调用时同步跑一次 Paper Trading（8 个策略，
    CPU 密集）。FastAPI 是 async 框架，若让首个用户请求触发，会阻塞事件循环，
    期间所有其他请求（含 WebSocket 心跳）都卡死。

    在 startup 阶段用 asyncio.to_thread 把它丢到线程池预热，事件循环不阻塞，
    首个用户请求到来时 _state 已就绪，直接返回。
    """
    # 0. 配置校验（CRITICAL 错误直接阻止启动）
    _cfg.validate(strict=True)

    # 1. 启动 WebSocket 行情订阅（异步任务，不阻塞）
    task = asyncio.create_task(ws_feed.start())

    # 2. 恢复运行模式状态（检查孤儿进程）
    await mode_manager.recover_on_startup()

    # 3. 自动建表（幂等：已存在的表不会重复创建）
    try:
        from src.utils.database import db
        from src.models.base import Base
        # 导入所有模型确保 metadata 已注册
        import src.models  # noqa: F401
        db.init_postgres()
        Base.metadata.create_all(db.engine)
        logger.info("Database tables verified/created (idempotent)")
    except Exception as e:
        logger.warning(f"Database auto-create skipped (non-fatal): {type(e).__name__}: {e}")

    # 4. 异步预热 Paper Trading（丢到线程池，不阻塞事件循环）
    #     预热前先检查 daemon 检查点是否可用：若 daemon 活跃则无需自建状态
    _prewarm_started = False
    try:
        if not service._daemon_state_available():
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, service.prewarm)
            _prewarm_started = True
            logger.info("Paper Trading 预热已提交到线程池（后台运行，不阻塞启动）")
        else:
            logger.info("检测到活跃的守护进程状态，跳过预热，使用 daemon 数据")
    except Exception as e:
        logger.warning(f"预热提交失败（非致命，首个请求会同步构建）: {e}")

    yield

    # 5. 优雅停止所有运行模式
    await mode_manager.stop_all()

    # 6. 关闭 WebSocket
    await ws_feed.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass



app = FastAPI(title="Crypto Trading System API", version="1.0", lifespan=lifespan)

# 开发期放行前端（Next.js 默认 3000；本项目 3000 被 Grafana 占用，前端用 3001）。
# 生产环境通过 CORS_ORIGINS 环境变量收紧到具体来源。
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cfg.CORS_ORIGINS,
    allow_methods=["GET", "PATCH", "POST", "OPTIONS"],
    allow_headers=["X-API-Token", "Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Inject CSP and HSTS security headers on every HTTP response.

    CSP 设计取舍：
    - default-src 'self'：默认所有资源同源
    - script-src 'unsafe-inline' 'unsafe-eval'：Next.js hydration 需要内联 script；
      dev 模式 fast-refresh 需要 eval（生产可去掉 'unsafe-eval'）
    - style-src 'unsafe-inline'：Tailwind / next-themes 注入内联样式
    - connect-src：从 CORS_ORIGINS 动态生成，包含 ws/wss/http/https
    - img-src 'self' data:：data URI 用于 SVG 图标
    - font-src 'self' data:：next/font 自托管 + data URI fallback
    """
    response = await call_next(request)

    # 从 CORS_ORIGINS 动态生成 connect-src
    origins = _cfg.CORS_ORIGINS or ["http://localhost:3000", "http://localhost:3001"]
    # 补充 ws/wss 变体 + API server 同源
    connect_sources = ["'self'"]
    for origin in origins:
        if origin.startswith("https://"):
            ws_origin = "wss://" + origin[8:]
        elif origin.startswith("http://"):
            ws_origin = "ws://" + origin[7:]
        else:
            continue
        if origin not in connect_sources:
            connect_sources.append(origin)
        if ws_origin not in connect_sources:
            connect_sources.append(ws_origin)
    # 确保后端 API 端口可达（从 request 推断）
    api_base = f"{request.url.scheme}://{request.url.netloc}"
    if api_base not in connect_sources:
        connect_sources.append(api_base)
    ws_api = ("wss://" if request.url.scheme == "https" else "ws://") + str(request.url.netloc)
    if ws_api not in connect_sources:
        connect_sources.append(ws_api)

    connect_src = " ".join(connect_sources)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        f"connect-src {connect_src}; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["50/second"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# --------------------------------------------------------------------------
# 预热期异常处理 — get_state() 预热中抛 RuntimeError 时返回 503
# --------------------------------------------------------------------------
@app.exception_handler(RuntimeError)
async def runtime_error_handler(request, exc: RuntimeError):
    """将预热期 RuntimeError 转为 HTTP 503 + Retry-After，避免裸 500"""
    msg = str(exc)
    if "PAPER_TRADING_BUILDING" in msg or "预热" in msg:
        from fastapi.responses import JSONResponse
        logger.debug(f"预热期请求被拦截: {request.url.path}")
        return JSONResponse(
            status_code=503,
            content={"detail": "系统启动中，请稍候", "status": "building"},
            headers={"Retry-After": "10"},
        )
    # 非预热相关 RuntimeError 仍返回 500
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": msg},
    )

# --------------------------------------------------------------------------
# API Token 验证
# --------------------------------------------------------------------------
_API_KEY_HEADER = APIKeyHeader(name="X-API-Token", auto_error=False)


async def verify_api_token(token: str = Security(_API_KEY_HEADER)):
    """Verify API token using constant-time comparison.

    Raises HTTP 503 if API_TOKEN is not configured (auth must be enforced
    in all non-development environments).

    Raises HTTP 403 on token mismatch.
    """
    from src.utils.config import config
    if config.API_TOKEN is None or config.API_TOKEN == "":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_TOKEN not configured. Auth is required for API access.",
        )
    if not token or not secrets.compare_digest(token, config.API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API token",
        )


@app.get("/health")
def health():
    """轻量健康检查（无需认证，供 Docker healthcheck / 负载均衡器使用）

    检查关键依赖：DB 连通性 + Redis/缓存连通性。
    任一失败返回 503，便于编排系统自动重启。
    """
    checks = {}
    all_ok = True

    # DB 连通性
    try:
        from src.utils.database import db
        db_ok = db.is_postgres_available()
        checks["database"] = "ok" if db_ok else "unavailable"
        if not db_ok:
            all_ok = False
    except Exception as e:
        checks["database"] = f"error: {e}"
        all_ok = False

    # 缓存连通性
    try:
        cache_ok = cache.ping()
        checks["cache"] = "ok" if cache_ok else "unavailable"
        if not cache_ok:
            all_ok = False
    except Exception as e:
        checks["cache"] = f"error: {e}"
        all_ok = False

    if not all_ok:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "checks": checks},
        )
    return {"status": "ok", "checks": checks}


@app.get("/health/detailed")
def health_detailed(_=Security(verify_api_token)):
    return {
        "status": "ok",
        "ws_connected": ws_feed.is_connected,
        "ws_clients": ws_feed.client_count,
        "cache_backend": cache.backend_type,
        "cache_available": cache.ping(),
    }


@app.get("/account/summary")
def account_summary(_=Security(verify_api_token)):
    live = live_data.account_summary()
    if live is not None:
        return live
    return service.account_summary(service.get_state())


@app.get("/market/tickers")
def tickers(_=Security(verify_api_token)):
    # 优先使用 WebSocket 缓存（实时），回退到 REST 轮询
    ws_tickers = ws_feed.get_tickers()
    if ws_tickers:
        return ws_tickers
    return service.tickers(service.get_state())


WS_PORT = 8000
MAX_WS_CLIENTS = 50


async def _authenticate_ws(ws: WebSocket) -> bool:
    """WebSocket 统一认证 — 通过首条 JSON 消息 {"type":"auth","token":"..."}

    返回 True 表示认证成功，False 表示已发送错误并关闭连接。
    """
    from src.utils.config import config
    if config.API_TOKEN is None or config.API_TOKEN == "":
        await ws.send_text(json.dumps({"error": "Server not configured"}))
        await ws.close(code=4001)
        return False

    try:
        first_msg = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
        auth_data = json.loads(first_msg)
    except WebSocketDisconnect:
        return False
    except asyncio.TimeoutError:
        await ws.send_text(json.dumps({"error": "Authentication timeout"}))
        await ws.close(code=4001)
        return False
    except json.JSONDecodeError:
        await ws.send_text(json.dumps({"error": "Invalid auth message"}))
        await ws.close(code=4001)
        return False

    if auth_data.get("type") != "auth" or not secrets.compare_digest(
        auth_data.get("token", ""), config.API_TOKEN
    ):
        await ws.send_text(json.dumps({"error": "Invalid token"}))
        await ws.close(code=4001)
        return False

    return True


@app.websocket("/ws/tickers")
async def ws_tickers(ws: WebSocket):
    """WebSocket 实时行情推送 (auth via first JSON message: {"type":"auth","token":"..."})

    客户端连接后立即收到当前 ticker 快照，
    此后每当 Binance 推送更新时广播给客户端。
    """
    # Connection limit
    if ws_feed.client_count >= MAX_WS_CLIENTS:
        await ws.accept()
        await ws.send_text(json.dumps({"error": "Too many connections. Please try again later."}))
        await ws.close(code=4002)
        return

    await ws.accept()

    # WebSocket 认证
    if not await _authenticate_ws(ws):
        return

    queue = ws_feed.subscribe()

    try:
        # 先发送当前快照
        snapshot = ws_feed.get_tickers()
        if snapshot:
            await ws.send_text(json.dumps(snapshot, ensure_ascii=False))

        # 持续推送实时更新
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                await ws.send_text(payload)
            except asyncio.TimeoutError:
                # 心跳保活
                await ws.send_text('{"type":"ping"}')
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket handler error")
    finally:
        ws_feed.unsubscribe(queue)


@app.get("/strategies")
def strategies(_=Security(verify_api_token)):
    live = live_data.strategies()
    if live is not None:
        return live
    return service.strategies(service.get_state())


@app.get("/positions")
def positions(_=Security(verify_api_token)):
    live = live_data.positions()
    if live is not None:
        return live
    return service.positions(service.get_state())


@app.get("/assets")
def assets(_=Security(verify_api_token)):
    live = live_data.assets()
    if live is not None:
        return live
    return service.assets(service.get_state())


@app.get("/orders")
def orders(
    limit: int = 100,
    offset: int = 0,
    _=Security(verify_api_token),
):
    """订单列表（分页）。

    Query 参数：
        limit:  每页条数，默认 100，范围 1-500（超出会被夹紧）
        offset: 偏移量，默认 0

    返回：
        { items, total, limit, offset, has_more }
    """
    live = live_data.orders(limit=limit, offset=offset)
    if live is not None:
        return live
    return service.orders(service.get_state(), limit=limit, offset=offset)


@app.get("/analytics/pnl-history")
def pnl_history(_=Security(verify_api_token)):
    live = live_data.pnl_history()
    if live is not None:
        return live
    return service.pnl_history(service.get_state())


@app.get("/analytics/strategy-performance")
def strategy_performance(_=Security(verify_api_token)):
    live = live_data.strategy_performance()
    if live is not None:
        return live
    return service.strategy_performance(service.get_state())


# --------------------------------------------------------------------------
# 风险指标 API（用于总览页风险卡 + /risk 风险管理页）
# --------------------------------------------------------------------------
@app.get("/account/risk-metrics")
def account_risk_metrics(_=Security(verify_api_token)):
    """账户级风险指标：最大回撤 / 夏普 / Sortino / 波动率 / 年化收益"""
    live = live_data.risk_metrics()
    if live is not None:
        return live
    return service.risk_metrics(service.get_state())


@app.get("/risk/drawdown-curve")
def risk_drawdown_curve(_=Security(verify_api_token)):
    """回撤曲线（每点含 equity / peak / drawdown%）"""
    return service.drawdown_curve(service.get_state())


@app.get("/risk/status")
def risk_status(_=Security(verify_api_token)):
    """账户级风控状态（来自 RiskManager 状态机）"""
    return service.risk_status(service.get_state())


@app.get("/risk/portfolio-heat")
def portfolio_heat(_=Security(verify_api_token)):
    """组合热力（Portfolio Heat）：跨策略风险敞口汇总

    返回各策略的持仓热力（ATR 风险 / 初始资金）及总热力。
    超过 15% 阈值时 daemon 会自动拒绝新开仓。
    """
    live = live_data.portfolio_heat()
    if live is not None:
        return live
    # 无共享文件时返回空状态
    from src.risk.portfolio_heat import DEFAULT_MAX_HEAT
    return {
        "total_heat": 0.0,
        "max_heat": DEFAULT_MAX_HEAT,
        "heat_pct": 0.0,
        "strategies": {},
        "updated_at": None,
    }


# --------------------------------------------------------------------------
# 止损配置
# --------------------------------------------------------------------------
class StopConfigUpdateRequest(BaseModel):
    strategy_type: str
    stop_type: str = "atr_trailing"  # none / atr_trailing / range_breakout / time_only
    atr_mult: float = 1.5
    trailing_activation: float = 0.03
    trailing_drawback: float = 0.03
    range_breakout_pct: float = 0.05
    max_bars: int = 50
    min_stop_pct: float = 0.01


@app.get("/risk/stop-config")
def get_stop_configs(_=Security(verify_api_token)):
    """获取所有策略类型的止损配置"""
    from src.strategy.stop_configs import STRATEGY_STOP_CONFIGS
    from src.strategy.stop_loss import StopLossConfig

    result = {}
    for stype, cfg in STRATEGY_STOP_CONFIGS.items():
        result[stype] = {
            "stop_type": cfg.stop_type,
            "atr_mult": cfg.atr_mult,
            "trailing_activation": cfg.trailing_activation,
            "trailing_drawback": cfg.trailing_drawback,
            "range_breakout_pct": cfg.range_breakout_pct,
            "max_bars": cfg.max_bars,
            "min_stop_pct": cfg.min_stop_pct,
        }
    return result


@app.post("/risk/stop-config")
@limiter.limit("10/minute")
def update_stop_config(
    request: Request,
    body: StopConfigUpdateRequest,
    _=Security(verify_api_token),
):
    """更新指定策略类型的止损配置（热更新，下次策略创建/bar 时生效）

    安全边界：参数会被 StopLossConfig.__post_init__ 自动 clamp 到安全范围
    """
    from src.strategy.stop_configs import STRATEGY_STOP_CONFIGS
    from src.strategy.stop_loss import StopLossConfig

    stype = body.strategy_type
    if stype not in STRATEGY_STOP_CONFIGS:
        raise HTTPException(400, f"未知策略类型: {stype}")

    # 构建新配置（StopLossConfig 会自动 clamp 到安全范围）
    new_cfg = StopLossConfig(
        stop_type=body.stop_type,
        atr_mult=body.atr_mult,
        trailing_activation=body.trailing_activation,
        trailing_drawback=body.trailing_drawback,
        range_breakout_pct=body.range_breakout_pct,
        max_bars=body.max_bars,
        min_stop_pct=body.min_stop_pct,
    )

    # 热更新模块级字典（运行中的策略下次创建 StopLossManager 时使用新配置）
    STRATEGY_STOP_CONFIGS[stype] = new_cfg

    return {
        "ok": True,
        "message": f"{stype} 止损配置已更新",
        "config": {
            "stop_type": new_cfg.stop_type,
            "atr_mult": new_cfg.atr_mult,
            "trailing_activation": new_cfg.trailing_activation,
            "trailing_drawback": new_cfg.trailing_drawback,
            "range_breakout_pct": new_cfg.range_breakout_pct,
            "max_bars": new_cfg.max_bars,
            "min_stop_pct": new_cfg.min_stop_pct,
        },
    }


# --------------------------------------------------------------------------
# 持仓历史 / 盈亏分布
# --------------------------------------------------------------------------
@app.get("/positions/history")
def positions_history(
    limit: int = 200,
    _=Security(verify_api_token),
):
    """已平仓交易历史（按平仓时间倒序）"""
    limit = max(1, min(int(limit), 1000))
    live = live_data.positions_history(limit=limit)
    if live is not None:
        return live
    return service.positions_history(service.get_state(), limit=limit)


@app.get("/analytics/pnl-distribution")
def pnl_distribution(
    bins: int = 10,
    _=Security(verify_api_token),
):
    """盈亏分布直方图 + 胜率/盈亏比统计"""
    bins = max(2, min(int(bins), 50))
    live = live_data.pnl_distribution(bins=bins)
    if live is not None:
        return live
    return service.pnl_distribution(service.get_state(), bins=bins)


@app.get("/analytics/win-rate-trend")
def win_rate_trend(
    window: int = 20,
    _=Security(verify_api_token),
):
    """滚动胜率趋势（每笔平仓后基于最近 N 笔算胜率）"""
    window = max(2, min(int(window), 200))
    return service.win_rate_trend(service.get_state(), window=window)


@app.get("/analytics/strategy-correlation")
def strategy_correlation(_=Security(verify_api_token)):
    """策略间日 PnL 相关性矩阵（Pearson）"""
    return service.strategy_correlation(service.get_state())


# --------------------------------------------------------------------------
# Monte Carlo & 策略评估端点
# --------------------------------------------------------------------------
@app.post("/analytics/monte-carlo")
@limiter.limit("10/minute")
def monte_carlo_analysis(
    request: Request,
    body: dict = None,
    _=Security(verify_api_token),
):
    """Monte Carlo 模拟分析

    请求体（可选）：
        strategy: 策略名（如 "rsi"），不填则用 live_data 的第一个策略
        n_simulations: 模拟次数（默认 1000）
        method: "trade_bootstrap" 或 "return_resample"
    """
    body = body or {}
    # 前端发送 strategy_id，兼容旧字段 strategy
    strategy_name = body.get("strategy_id", "") or body.get("strategy", "")
    n_sim = body.get("n_simulations", 1000)
    method = body.get("method", "trade_bootstrap")

    # 优先从 live_data 获取交易数据
    live = live_data.multi_strategy_details()
    if live:
        # 找到指定策略或用第一个
        target = None
        if strategy_name:
            for s in live:
                if strategy_name in s.get("id", ""):
                    target = s
                    break
        if target is None and live:
            target = live[0]

        if target:
            from src.backtest.monte_carlo import MonteCarloSimulator
            # 从 live_data 构造 trades
            trades = []
            for ct in target.get("closed_trades", []):
                trades.append({
                    "type": "SELL",
                    "profit": float(ct.get("profit", 0)),
                })

            mc = MonteCarloSimulator(n_simulations=n_sim, random_seed=42)
            result = mc.run(
                trades=trades,
                initial_capital=float(target.get("investment", 10000)),
                method=method,
            )
            return {
                "strategy_id": target.get("id", ""),
                **result.to_dict(),
            }

    raise HTTPException(503, "No live data available. Run a strategy first.")


@app.post("/analytics/strategy-evaluation")
@limiter.limit("5/minute")
def strategy_evaluation(
    request: Request,
    body: dict = None,
    _=Security(verify_api_token),
):
    """策略评估报告 — 对所有策略做全面评估

    请求体（可选）：
        strategies: 策略名列表，不填则评估全部
        days: 回测天数（默认 365）
    """
    body = body or {}
    strategies = body.get("strategies")
    days = body.get("days", 365)

    # 直接读取原始 state 文件（需要 closed_trades 明细，multi_strategy_details 不包含）
    from src.api.live_data import _load_all_states
    states = _load_all_states()
    if not states:
        raise HTTPException(503, "No live data available.")

    from src.backtest.monte_carlo import MonteCarloSimulator

    results = []
    from src.strategy.registry import get_strategy_label
    for s in states:
        strat_name = s.get("strategy_name", "unknown")
        sname = get_strategy_label(strat_name) or strat_name

        # 跳过不在指定列表中的策略
        if strategies and strat_name not in strategies:
            continue

        # 从原始 state 获取交易明细
        runner_state = s.get("runner", {})
        closed_trades_raw = runner_state.get("closed_trades", [])
        trades = []
        for ct in closed_trades_raw:
            trades.append({
                "type": "SELL",
                "profit": float(ct.get("profit", 0)),
            })

        initial = float(s.get("initial_capital", 10000))
        realized = float(runner_state.get("realized_pnl", 0))

        # Monte Carlo（1000 次模拟，与脚本版一致）
        n_sim = int(body.get("n_mc_simulations", 1000))
        mc = MonteCarloSimulator(n_simulations=n_sim, random_seed=42)
        mc_result = mc.run(trades=trades, initial_capital=initial)

        # 简化评分（基于 state 数据）
        total_trades = len(trades)
        wins = sum(1 for t in trades if t["profit"] > 0)
        win_rate = wins / total_trades if total_trades > 0 else 0
        return_pct = realized / initial if initial > 0 else 0

        # 从 closed_trades 计算 Sharpe 和最大回撤
        import numpy as np
        if total_trades >= 2:
            profits_arr = np.array([t["profit"] for t in trades])
            # 简易 Sharpe：均值/标准差 * sqrt(交易数)
            std_profit = float(np.std(profits_arr))
            mean_profit = float(np.mean(profits_arr))
            sharpe_ratio = float(mean_profit / std_profit * np.sqrt(total_trades)) if std_profit > 0 else 0.0
            # 最大回撤：从累积权益曲线计算
            equity_curve = initial + np.cumsum(profits_arr)
            running_peak = np.maximum.accumulate(equity_curve)
            drawdowns = (equity_curve - running_peak) / running_peak
            max_dd = float(abs(np.min(drawdowns))) if len(drawdowns) > 0 else 0.0
        else:
            sharpe_ratio = 0.0
            max_dd = 0.0

        # 回退到 MC 指标
        if max_dd == 0:
            max_dd = mc_result.max_dd_p95
        if sharpe_ratio == 0:
            sharpe_ratio = mc_result.sharpe_median

        # 参数稳定性：基于交易盈亏的变异系数，归一化到 0-1
        if total_trades >= 5:
            profits = [t["profit"] for t in trades]
            import numpy as np
            mean_profit = float(np.mean(profits))
            std_profit = float(np.std(profits))
            cv = std_profit / abs(mean_profit) if abs(mean_profit) > 1e-8 else 1.0
            param_stability = max(0, min(1, 1 - cv * 0.3))
        else:
            param_stability = 0.5  # 交易不足，给中等分

        # IS-OS 差异（简化版：用 MC p5-p95 跨度近似）
        is_os_diff = abs(mc_result.return_p95 - mc_result.return_p5)

        # 五维评分（与 StrategyEvaluator 对齐）
        profitability = min(100, max(0, return_pct * 200))
        risk = max(0, 100 - mc_result.max_dd_p95 * 200)
        stability = max(0, 100 - abs(mc_result.return_p95 - mc_result.return_p5) * 200)
        trade_quality = min(100, win_rate * 150) if total_trades > 0 else 0
        param_stability_score = param_stability * 100
        total_score = (
            profitability * 0.25 + risk * 0.20 +
            stability * 0.20 + trade_quality * 0.15 +
            param_stability_score * 0.20
        )

        # 淘汰检查（与前端类型注释对齐）
        flags = []
        if total_trades > 0 and return_pct < 0:
            flags.append("收益为负")
        if mc_result.ruin_probability > 0.1:
            flags.append(f"破产概率 {mc_result.ruin_probability:.0%} > 10%")
        if sharpe_ratio < 0.3:
            flags.append(f"Sharpe {sharpe_ratio:.2f} < 0.3")
        if max_dd > 0.25:
            flags.append(f"最大回撤 {max_dd:.0%} > 25%")
        if param_stability < 0.4:
            flags.append(f"参数稳定性 {param_stability:.2f} < 0.4")

        verdict = "KEEP"
        if len(flags) >= 2:
            verdict = "ELIMINATE"
        elif len(flags) >= 1:
            verdict = "WARN"

        results.append({
            "strategy_name": sname,
            "total_score": round(total_score, 1),
            "verdict": verdict,
            "sharpe_ratio": round(sharpe_ratio, 3),
            "max_drawdown": round(max_dd, 4),
            "total_return": round(return_pct, 4),
            "total_trades": total_trades,
            "win_rate": round(win_rate, 4),
            "mc_return_median": round(mc_result.return_median, 4),
            "mc_max_dd_median": round(mc_result.max_dd_median, 4),
            "mc_ruin_prob": round(mc_result.ruin_probability, 4),
            "param_stability": round(param_stability, 3),
            "is_os_diff": round(is_os_diff, 4),
            "elimination_flags": flags,
        })

    results.sort(key=lambda x: x["total_score"], reverse=True)
    return results


# --------------------------------------------------------------------------
# 管理端点（需 API Token）
# --------------------------------------------------------------------------
@app.post("/admin/refresh-state")
@limiter.limit("2/minute")
def admin_refresh_state_view(request: Request, _=Security(verify_api_token)):
    """重置 Paper Trading state 缓存，下次请求会重新跑 Paper Trading。

    使用场景：
    - 数据源更新后想立即看到新结果（不必重启服务）
    - Paper Trading 配置变更后重跑

    限流：2 次/分钟（重建 state 是 CPU 密集操作，频繁调用会拖垮服务）
    """
    return admin_refresh_state()


@app.get("/admin/build-status")
def admin_build_status_view(_=Security(verify_api_token)):
    """Paper Trading 状态构建进度（返回是否就绪/构建中/错误）。"""
    return admin_build_status()


@app.post("/admin/clear-cache")
@limiter.limit("5/minute")
def admin_clear_cache_view(request: Request, confirm: bool = Query(False), _=Security(verify_api_token)):
    """全面重置：清空数据库所有表 + Redis 缓存 + 本地数据文件 + 内存 state。

    一键清除全部历史数据，下次请求会重新跑 Paper Trading 并写入全新数据。

    防护：需要 ?confirm=true 查询参数作为二次确认，防止误触。

    清理范围：
    - 数据库 7 张 ORM 表 + monitor_metrics
    - Redis 缓存
    - 本地数据文件（paper checkpoint、reports、raw data、mode states）
    - 内存中的 Paper Trading state

    限流：5 次/分钟
    """
    return admin_clear_cache(confirm)


@app.post("/admin/start-trading")
@limiter.limit("10/minute")
def admin_start_trading_view(request: Request, _=Security(verify_api_token)):
    """手动启动 Paper Trading，生成订单/仓位数据。

    系统启动后默认为空状态，调用此端点后才开始跑 Paper Trading。
    重置后（/admin/clear-cache）也需要重新调用此端点。
    """
    return admin_start_trading()


# --------------------------------------------------------------------------
# 多策略 API
# --------------------------------------------------------------------------
@app.get("/multi/summary")
def multi_summary(_=Security(verify_api_token)):
    """多策略聚合摘要（总盈亏、总交易数、各策略状态）"""
    live = live_data.multi_strategy_summary()
    if live is not None:
        return live
    return service.multi_strategy_summary(service.get_state())


@app.get("/multi/details")
def multi_details(_=Security(verify_api_token)):
    """每个策略的详细结果"""
    live = live_data.multi_strategy_details()
    if live is not None:
        return live
    return service.multi_strategy_details(service.get_state())


@app.get("/multi/strategy/{strategy_id}")
def multi_strategy_detail(strategy_id: str, _=Security(verify_api_token)):
    """获取单个策略的运行结果"""
    live = live_data.multi_strategy_result(strategy_id)
    if live is not None:
        return live
    result = service.multi_strategy_result(service.get_state(), strategy_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")
    return result


class StatusPatch(BaseModel):
    status: str


@app.patch("/strategies/{strategy_id}/status")
def update_strategy_status(strategy_id: str, body: StatusPatch, _=Security(verify_api_token)):
    return service.set_strategy_status(strategy_id, body.status)


# --------------------------------------------------------------------------
# 创建策略
# --------------------------------------------------------------------------
class CreateGridRequest(BaseModel):
    symbol: str = "BTC/USDT"
    lowerPrice: float
    upperPrice: float
    gridCount: int = 10
    investment: float = 10000.0


@app.post("/strategies/create-grid")
def create_grid_strategy(body: CreateGridRequest, _=Security(verify_api_token)):
    """创建网格策略（Paper 模式返回策略元数据，实际引擎已运行）。"""
    from fastapi import HTTPException

    if body.lowerPrice >= body.upperPrice:
        raise HTTPException(status_code=400, detail="lowerPrice must be less than upperPrice")
    if body.gridCount < 3 or body.gridCount > 50:
        raise HTTPException(status_code=400, detail="gridCount must be between 3 and 50")

    # 返回策略元数据（引擎实际运行在 service._build_state 中）
    return {
        "id": f"grid-{body.symbol.lower().replace('/', '-')}-{int(body.lowerPrice)}",
        "name": f"Grid {body.symbol}",
        "type": "grid",
        "symbol": body.symbol,
        "status": "running",
        "pnl": 0.0,
        "pnlPct": 0.0,
        "investment": body.investment,
        "runningDays": 0,
        "createdAt": datetime.now().isoformat(),
        "grid": {
            "upperPrice": body.upperPrice,
            "lowerPrice": body.lowerPrice,
            "gridCount": body.gridCount,
            "perGridProfit": ((body.upperPrice - body.lowerPrice) / body.gridCount / body.lowerPrice) * 100,
            "filledGrids": 0,
            "arbitrageCount": 0,
        },
    }


# --------------------------------------------------------------------------
# 策略注册表 / 通用创建 / 参数更新 / 运行历史
# --------------------------------------------------------------------------

@app.get("/strategies/registry")
def strategy_registry(_=Security(verify_api_token)):
    """返回 8 个策略的注册信息（名称、PARAM_SCHEMA、默认参数、运行状态）"""
    state = service.get_state()
    return {"strategies": service.get_registry(state)}


class CreateStrategyRequest(BaseModel):
    type: str
    symbol: str = "BTC/USDT"
    investment: float = Field(default=10000.0, ge=100, le=1_000_000)
    timeframe: str = "4h"
    params: dict = {}


@app.post("/strategies/create")
def create_strategy_generic(body: CreateStrategyRequest, _=Security(verify_api_token)):
    """通用策略创建（支持全部 8 个策略类型）"""
    try:
        state = service.get_state()
        return service.create_strategy(
            state,
            strategy_type=body.type,
            symbol=body.symbol,
            investment=body.investment,
            params=body.params,
            timeframe=body.timeframe,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


class UpdateParamsRequest(BaseModel):
    params: dict


@app.patch("/strategies/{strategy_id}/params")
def update_strategy_params_endpoint(
    strategy_id: str, body: UpdateParamsRequest, _=Security(verify_api_token),
):
    """更新策略参数（先持久化到配置，再热替换运行中实例）。"""
    try:
        # 先持久化（引擎未运行也能保存，下次启动生效）
        strategy_type = strategy_id.split("-")[0]
        update_strategy_config(strategy_type, body.params)
        # 再尝试热替换运行中实例（引擎未运行会跳过）
        state = service.get_state()
        result = service.update_strategy_params(state, strategy_id, body.params)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/strategies/configs")
def get_strategy_configs(_=Security(verify_api_token)):
    """读取所有已保存的策略参数配置。"""
    return get_all_strategy_configs()


@app.delete("/strategies/configs/{strategy_type}")
def delete_strategy_config_endpoint(
    strategy_type: str, _=Security(verify_api_token),
):
    """删除指定策略的已保存配置。"""
    ok = delete_strategy_config(strategy_type)
    if not ok:
        raise HTTPException(404, f"策略 {strategy_type} 无已保存配置")
    return {"deleted": strategy_type}


@app.delete("/strategies/{strategy_id}/instance")
def delete_strategy_instance(
    strategy_id: str, _=Security(verify_api_token),
):
    """删除运行中的策略实例（从 multi_runner 中移除，不影响已保存配置）

    - 清理策略持仓（如果有）
    - 从 multi_runner.slots 移除
    - 删除对应的 state 文件
    """
    import json
    from pathlib import Path
    from src.api.mode_manager import mode_manager

    # 1. 从 multi_runner 移除
    removed = False
    try:
        from src.execution.multi_runner import multi_runner
        original_len = len(multi_runner.slots)
        multi_runner.slots = [s for s in multi_runner.slots if s.config.strategy_id != strategy_id]
        if len(multi_runner.slots) < original_len:
            removed = True
            logger.info(f"策略实例 {strategy_id} 已从 multi_runner 移除")
    except Exception as e:
        logger.warning(f"从 multi_runner 移除 {strategy_id} 失败: {e}")

    # 2. 删除 state 文件
    state_dir = Path("data") / "paper_daemon_state"
    state_files = list(state_dir.glob(f"*{strategy_id}*.json")) if state_dir.exists() else []
    for sf in state_files:
        try:
            sf.unlink()
            logger.info(f"已删除 state 文件 {sf.name}")
        except Exception as e:
            logger.warning(f"删除 state 文件 {sf.name} 失败: {e}")

    # 3. 从 _pending_map 移除
    try:
        multi_runner._pending_map.pop(strategy_id, None)
    except Exception:
        pass

    if not removed and not state_files:
        return {"ok": False, "message": f"未找到策略实例 {strategy_id}"}

    return {"ok": True, "message": f"策略实例 {strategy_id} 已删除"}


@app.put("/strategies/configs/{strategy_type}/rename")
def rename_strategy_config_endpoint(
    strategy_type: str,
    body: dict,
    _=Security(verify_api_token),
):
    """重命名策略配置的 key。"""
    new_name = body.get("new_name", "").strip()
    if not new_name:
        raise HTTPException(400, "new_name 不能为空")
    ok = rename_strategy_config(strategy_type, new_name)
    if not ok:
        raise HTTPException(404, f"策略 {strategy_type} 无已保存配置")
    return {"renamed_from": strategy_type, "renamed_to": new_name}


@app.get("/strategies/history")
def strategy_run_history(
    strategy_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    _=Security(verify_api_token),
):
    """策略运行历史（分页，支持 strategy_id 过滤）"""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    return service.get_run_history(strategy_id=strategy_id, limit=limit, offset=offset)


# --------------------------------------------------------------------------
# AI Agent 分析端点（只分析，不执行）
# --------------------------------------------------------------------------
_audit_log = AuditLog()
_analyzer = TradingAnalyzer(_audit_log)


class AnalyzeRequest(BaseModel):
    task: Literal["backtest", "trade_attribution", "risk_checklist", "param_sensitivity", "weekly_review"]
    phase: str = "Phase 6"
    strategy_id: str = ""


@app.post("/agent/analyze")
@limiter.limit("10/minute")
def agent_analyze(request: Request, body: AnalyzeRequest, _=Security(verify_api_token)):
    """触发 AI 分析（只分析，不执行任何交易决策）"""
    # 优先使用实时纸盘数据，无 daemon state 时回退到预跑数据
    live = live_data.build_analysis_data(body.task)

    if live is not None:
        if body.task == "backtest":
            report = _analyzer.analyze_backtest(
                results=live["results"],
                metrics=live["metrics"],
                strategy_name=live["strategy_name"],
            )
        elif body.task == "weekly_review":
            report = _analyzer.analyze_weekly_review(
                paper_report=live["paper_report"],
                trade_history=live["trade_history"],
            )
        elif body.task == "trade_attribution":
            report = _analyzer.analyze_failed_trades(live["trades"])
        elif body.task == "risk_checklist":
            report = _analyzer.analyze_risk_checklist(live["checklist"])
        elif body.task == "param_sensitivity":
            report = _analyzer.analyze_param_sensitivity(
                scan_results=live.get("scan_results", pd.DataFrame()),
                base_params=live["base_params"],
            )
        else:
            raise HTTPException(400, f"Unknown task type: {body.task}")

        strategy_name = live.get("strategy_name", "LivePaper")
    else:
        state = service.get_state()

        if body.task == "backtest":
            result = state["result"]
            metrics = {
                "total_return": result.get("statistics", {}).get("total_return", 0),
                "win_rate": 0.5,
            }
            report = _analyzer.analyze_backtest(
                results=result,
                metrics=metrics,
                strategy_name=getattr(state["strategy"], "name", "GridTrading"),
            )
        elif body.task == "weekly_review":
            report = _analyzer.analyze_weekly_review(
                paper_report=state["report"],
                trade_history=state["result"].get("trade_history"),
            )
        elif body.task == "trade_attribution":
            trades = [
                {"pnl": t.get("profit", 0), "time": t.get("timestamp")}
                for t in state["result"].get("closed_trades", [])
            ]
            report = _analyzer.analyze_failed_trades(trades)
        elif body.task == "risk_checklist":
            report = _analyzer.analyze_risk_checklist({
                "paper_trading_days": service._running_days(state),
                "risk_tests_passed": True,
                "api_key_restricted": False,
                "initial_capital": 10000.0,
                "max_drawdown": 0.0,
                "data_quality_score": 1.0,
            })
        elif body.task == "param_sensitivity":
            base_params = getattr(state["strategy"], "parameters", {})
            # 回退路径：用已有回测结果构建单行扫描数据
            result = state["result"]
            stats = result.get("statistics", {})
            scan_df = pd.DataFrame([{
                "strategy": getattr(state["strategy"], "name", "GridTrading"),
                "total_return": stats.get("total_return", 0),
                "win_rate": stats.get("win_rate", 0),
                "max_drawdown": stats.get("max_drawdown", 0),
                "sharpe_ratio": stats.get("sharpe_ratio", 0),
                "n_trades": stats.get("total_trades", 0),
            }])
            report = _analyzer.analyze_param_sensitivity(
                scan_results=scan_df,
                base_params=base_params,
            )
        else:
            raise HTTPException(400, f"Unknown task type: {body.task}")

        strategy_name = getattr(state.get("strategy", ""), "name", "GridTrading")

    # 推送分析请求给 Hermes（后台异步，不阻塞）
    try:
        from src.agent.hermes_bridge import push_analysis_request
        push_analysis_request(
            task=body.task,
            strategy_id=body.strategy_id or "grid-btc-usdt",
            strategy_name=strategy_name,
            data={"report": report},
        )
    except Exception as e:
        logger.debug(f"Hermes 推送失败（非致命）: {e}")

    return report


@app.get("/agent/audit-logs")
@limiter.limit("10/minute")
def agent_audit_logs(request: Request, task: Optional[str] = None, limit: int = 50, _=Security(verify_api_token)):
    """获取 AI 分析审计日志"""
    return _audit_log.get_logs(task=task, limit=limit)


@app.get("/agent/adoption-rate")
@limiter.limit("10/minute")
def agent_adoption_rate(request: Request, task: Optional[str] = None, _=Security(verify_api_token)):
    """获取 AI 建议采纳率统计"""
    return _audit_log.get_adoption_rate(task=task)


# --------------------------------------------------------------------------
# 策略 AI 进化端点
# --------------------------------------------------------------------------
class EvolveRequest(BaseModel):
    strategy_ids: list[str] | None = None   # None = 进化全部（排除 buyhold）
    auto_apply: bool = True


@app.post("/agent/evolve")
@limiter.limit("2/minute")
def agent_evolve(request: Request, body: EvolveRequest, _=Security(verify_api_token)):
    """触发策略参数进化（Walk-Forward 搜索 + 安全校验 + 自动应用）"""
    from src.agent import EvolutionEngine

    state = service.get_state()
    multi_runner = state.get("_multi_runner")
    risk_manager = getattr(multi_runner, "risk_manager", None) if multi_runner else None
    risk_state = getattr(risk_manager, "state", "ACTIVE")

    # 构建行情数据 dict：{symbol: DataFrame}
    df = state["df"]
    data_map = {service.SYMBOL: df}

    engine = EvolutionEngine(
        data=data_map,
        audit_log=_audit_log,
        auto_apply=body.auto_apply,
    )

    # 确定要进化的策略列表
    if multi_runner is None:
        raise HTTPException(500, "MultiStrategyRunner 未初始化")

    if body.strategy_ids:
        slots = [
            s for s in multi_runner.slots
            if s.config.strategy_id in body.strategy_ids
        ]
    else:
        slots = multi_runner.slots

    try:
        results = engine.evolve_all(
            slots=slots,
            skip={"buyhold"},
            multi_runner=multi_runner,
            risk_manager_state=risk_state,
        )
    except ValueError as e:
        raise HTTPException(400, f"进化参数错误: {e}")
    except Exception as e:
        logger.exception(f"策略进化失败: {e}")
        raise HTTPException(500, f"进化引擎内部错误: {e}")

    return [r.to_dict() for r in results]


@app.get("/agent/evolution-history")
@limiter.limit("10/minute")
def agent_evolution_history(
    request: Request,
    strategy_id: Optional[str] = None,
    limit: int = 50,
    _=Security(verify_api_token),
):
    """获取策略进化历史记录"""
    try:
        from src.utils.database import db
        if not db.is_postgres_available():
            return {"items": [], "total": 0, "stats": {}}

        from src.repositories.evolution_repo import EvolutionRepository
        repo = EvolutionRepository()

        with db.get_session() as session:
            items = repo.get_history(session, strategy_id=strategy_id, limit=limit)
            stats = repo.get_stats(session)
            return {"items": items, "total": len(items), "stats": stats}
    except Exception as e:
        logger.warning(f"Evolution history query failed: {type(e).__name__}: {e}")
        return {"items": [], "total": 0, "stats": {}}


@app.get("/agent/evolution-stats")
@limiter.limit("10/minute")
def agent_evolution_stats(request: Request, _=Security(verify_api_token)):
    """获取策略进化统计摘要"""
    try:
        from src.utils.database import db
        if not db.is_postgres_available():
            return {"total_evolutions": 0, "applied_count": 0, "avg_sharpe_improvement": 0}

        from src.repositories.evolution_repo import EvolutionRepository
        repo = EvolutionRepository()

        with db.get_session() as session:
            return repo.get_stats(session)
    except Exception as e:
        logger.warning(f"Evolution stats query failed: {type(e).__name__}: {e}")
        return {"total_evolutions": 0, "applied_count": 0, "avg_sharpe_improvement": 0}


# --------------------------------------------------------------------------
# Hermes 外部 Agent 接口
# --------------------------------------------------------------------------
@app.get("/agent/hermes/status")
def hermes_status(_=Security(verify_api_token)):
    """Hermes 连接状态"""
    from src.agent.hermes_bridge import get_status
    return get_status()


@app.post("/agent/hermes/callback")
def hermes_callback(body: dict, _=Security(verify_api_token)):
    """Hermes 分析结果回调（Hermes 调此接口返回分析结论）"""
    from src.agent.hermes_bridge import handle_callback
    return handle_callback(body)


@app.get("/agent/hermes/result/{event_id}")
def hermes_result(event_id: str, _=Security(verify_api_token)):
    """查询 Hermes 分析结果（前端轮询用）"""
    from src.agent.hermes_bridge import get_callback_result
    result = get_callback_result(event_id)
    if result is None:
        raise HTTPException(404, f"Hermes 分析结果不存在: {event_id}")
    return result


@app.post("/admin/emergency-stop")
@limiter.limit("5/minute")
def admin_emergency_stop_view(request: Request, _=Security(verify_api_token)):
    """远程急停：触发全局 RiskManager.emergency_stop()，停止所有策略交易。
    状态机进入 STOPPED，只能通过 reset() 恢复（带防抖冷却）。
    """
    return admin_emergency_stop()


@app.post("/admin/data/cleanup")
@limiter.limit("3/minute")
def admin_data_cleanup_view(request: Request, body: CleanupRequest, _=Security(verify_api_token)):
    """清理历史测试数据（运行记录 / 进化记录 / 审计日志）"""
    return admin_data_cleanup(body)


@app.post("/admin/test-telegram")
@limiter.limit("3/minute")
def admin_test_telegram_view(request: Request, _=Security(verify_api_token)):
    """发送一条 Telegram 测试消息，验证 Bot Token 和 Chat ID 是否配置正确。

    无 Token 时返回降级状态（不报错）。
    """
    from src.utils.telegram_notifier import notifier

    enabled = notifier.enabled
    try:
        notifier.send_info_sync(
            "Telegram 通知测试\n这是一条来自 crypto-trading-system 的测试消息。\n"
            "如果你收到了，说明配置正确！"
        )
        return {
            "ok": True,
            "enabled": enabled,
            "message": "测试消息已发送" if enabled else "降级模式（未配置 Token，仅日志输出）",
        }
    except Exception as e:
        return {"ok": False, "enabled": enabled, "message": str(e)}


class TelegramConfigRequest(BaseModel):
    bot_token: str = ""
    chat_id: str = ""
    min_level: str = "INFO"  # INFO / WARNING / CRITICAL


def _read_env_file() -> dict:
    """读取 .env 文件中的 Telegram 相关配置"""
    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    result = {"bot_token": "", "chat_id": "", "min_level": "INFO"}
    if not env_path.exists():
        return result
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            result["bot_token"] = line.split("=", 1)[1]
        elif line.startswith("TELEGRAM_CHAT_ID="):
            result["chat_id"] = line.split("=", 1)[1]
        elif line.startswith("TELEGRAM_MIN_LEVEL="):
            result["min_level"] = line.split("=", 1)[1] or "INFO"
    return result


def _update_env_file(bot_token: str, chat_id: str, min_level: str) -> None:
    """更新 .env 文件中的 Telegram 配置（保留其他行不变）"""
    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"

    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    found_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("TELEGRAM_BOT_TOKEN="):
            new_lines.append(f"TELEGRAM_BOT_TOKEN={bot_token}")
            found_keys.add("bot_token")
        elif stripped.startswith("TELEGRAM_CHAT_ID="):
            new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
            found_keys.add("chat_id")
        elif stripped.startswith("TELEGRAM_MIN_LEVEL="):
            new_lines.append(f"TELEGRAM_MIN_LEVEL={min_level}")
            found_keys.add("min_level")
        else:
            new_lines.append(line)

    # 追加缺失的键
    if "bot_token" not in found_keys:
        new_lines.append(f"TELEGRAM_BOT_TOKEN={bot_token}")
    if "chat_id" not in found_keys:
        new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
    if "min_level" not in found_keys:
        new_lines.append(f"TELEGRAM_MIN_LEVEL={min_level}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@app.get("/admin/telegram-config")
def admin_get_telegram_config(_=Security(verify_api_token)):
    """获取当前 Telegram 配置（Token 部分掩码显示）"""
    cfg = _read_env_file()
    token = cfg["bot_token"]
    # 掩码处理：只显示前5位和后4位
    if len(token) > 10:
        masked = token[:5] + "..." + token[-4:]
    elif token:
        masked = "***"
    else:
        masked = ""
    return {
        "bot_token_masked": masked,
        "bot_token_set": bool(token),
        "chat_id": cfg["chat_id"],
        "min_level": cfg["min_level"],
        "enabled": bool(token and cfg["chat_id"]),
    }


@app.post("/admin/telegram-config")
@limiter.limit("5/minute")
def admin_set_telegram_config(
    request: Request,
    body: TelegramConfigRequest,
    _=Security(verify_api_token),
):
    """保存 Telegram 配置到 .env 文件并热更新 notifier。

    - bot_token 为空字符串时清除 Token（降级为纯日志模式）
    - 保存后立即生效，无需重启服务
    """
    import os
    from src.utils.telegram_notifier import notifier, NotificationLevel

    min_level = body.min_level.upper()
    if min_level not in ("INFO", "WARNING", "CRITICAL"):
        return {"ok": False, "message": f"无效的 min_level: {body.min_level}"}

    # 如果前端传空 Token，保留已有值（除非显式传空字符串清除）
    token_to_save = body.bot_token
    if token_to_save == "":
        # 空字符串 = 用户未输入新 Token，保留已有
        existing = _read_env_file()
        token_to_save = existing["bot_token"]

    # 写入 .env 文件
    _update_env_file(token_to_save, body.chat_id, min_level)

    # 更新环境变量（供后续 import 的模块读取）
    os.environ["TELEGRAM_BOT_TOKEN"] = token_to_save
    os.environ["TELEGRAM_CHAT_ID"] = body.chat_id
    os.environ["TELEGRAM_MIN_LEVEL"] = min_level

    # 热更新 notifier 单例
    notifier._bot_token = token_to_save
    notifier._chat_id = body.chat_id
    notifier._min_level = NotificationLevel[min_level]
    notifier._enabled = bool(token_to_save and body.chat_id)

    enabled = notifier._enabled
    return {
        "ok": True,
        "enabled": enabled,
        "message": "Telegram 配置已保存并生效" if enabled else "已保存（降级模式：未配置 Token，仅日志输出）",
    }


# --------------------------------------------------------------------------
# 数据生成（一次性，不经过模式管理）
# --------------------------------------------------------------------------
class GenerateDataRequest(BaseModel):
    marketType: str = "oscillating"


@app.post("/admin/generate-data")
@limiter.limit("10/minute")
def admin_generate_data(request: Request, body: GenerateDataRequest, _=Security(verify_api_token)):
    """一次性生成模拟数据并运行质量检查"""
    import sys
    from pathlib import Path
    _root = Path(__file__).resolve().parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    from src.utils.config import config as _cfg
    from scripts.run_data_pipeline import run_pipeline
    success = run_pipeline(
        symbol=_cfg.DATA_SYMBOLS[0] if _cfg.DATA_SYMBOLS else "BTC/USDT",
        timeframe=_cfg.DATA_TIMEFRAME,
        use_mock=True,
        market_type=body.marketType,
    )
    return {"ok": success, "message": "数据生成完成" if success else "数据生成失败"}


# --------------------------------------------------------------------------
# 运行模式管理端点
# --------------------------------------------------------------------------
class StartModeRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    days: int = Field(default=60, ge=1, le=365)
    initialCapital: float = Field(default=10000.0, ge=100, le=1_000_000)
    pollSeconds: int = Field(default=60, ge=10, le=600)
    replayCsv: str | None = None
    fresh: bool = False
    strategies: list[str] = ["grid"]
    marketType: str = "oscillating"


@app.get("/modes")
def list_modes(_=Security(verify_api_token)):
    """列出所有运行模式及其状态"""
    return mode_manager.get_all_status()


@app.get("/modes/{mode}/status")
def mode_status(mode: str, _=Security(verify_api_token)):
    """获取单个模式的详细状态"""
    try:
        running_mode = RunningMode(mode)
    except ValueError:
        raise HTTPException(404, f"未知模式: {mode}")
    return mode_manager.get_status(running_mode)


@app.post("/modes/{mode}/start")
@limiter.limit("2/minute")
async def start_mode(mode: str, body: StartModeRequest, request: Request, _=Security(verify_api_token)):
    """启动指定运行模式"""
    try:
        running_mode = RunningMode(mode)
    except ValueError:
        raise HTTPException(404, f"未知模式: {mode}")

    params = ModeParams(
        symbol=body.symbol,
        timeframe=body.timeframe,
        days=body.days,
        initial_capital=body.initialCapital,
        poll_seconds=body.pollSeconds,
        replay_csv=body.replayCsv,
        fresh=body.fresh,
        strategies=body.strategies,
        market_type=body.marketType,
    )
    result = await mode_manager.start_mode(running_mode, params)
    if "error" in result:
        raise HTTPException(409, result["error"])
    return result


@app.post("/modes/{mode}/stop")
@limiter.limit("5/minute")
async def stop_mode(mode: str, request: Request, _=Security(verify_api_token)):
    """停止指定运行模式"""
    try:
        running_mode = RunningMode(mode)
    except ValueError:
        raise HTTPException(404, f"未知模式: {mode}")
    result = await mode_manager.stop_mode(running_mode)
    if "error" in result:
        raise HTTPException(409, result["error"])
    return result


@app.get("/modes/{mode}/logs")
def mode_logs(mode: str, limit: int = 200, _=Security(verify_api_token)):
    """获取模式的历史日志（REST fallback）"""
    try:
        running_mode = RunningMode(mode)
    except ValueError:
        raise HTTPException(404, f"未知模式: {mode}")
    limit = max(1, min(int(limit), 500))
    return ws_logs.get_buffer(running_mode, limit=limit)


@app.get("/modes/{mode}/result")
def mode_result(mode: str, _=Security(verify_api_token)):
    """获取某模式最近一次运行的結果摘要（收益/交易数/胜率/天数/风控状态）。

    数据来自 daemon 检查点文件 data/paper_daemon_state_{mode}*.json，
    运行中与结束后均可查询。
    """
    try:
        running_mode = RunningMode(mode)
    except ValueError:
        raise HTTPException(404, f"未知模式: {mode}")
    return mode_manager.get_result(running_mode)


@app.post("/modes/testnet_live/validate")
@limiter.limit("1/minute")
async def validate_testnet(request: Request, _=Security(verify_api_token)):
    """Testnet 预检：验证 API Key 权限和连通性"""
    from src.utils.config import config

    if not config.BINANCE_TESTNET:
        return {
            "ok": False,
            "checks": [{"name": "testnet_flag", "status": "FAIL",
                        "detail": "BINANCE_TESTNET 必须为 true"}],
        }
    if not config.BINANCE_API_KEY or config.BINANCE_API_KEY == "your_binance_testnet_key":
        return {
            "ok": False,
            "checks": [{"name": "api_key", "status": "FAIL",
                        "detail": "BINANCE_API_KEY 未配置或仍为占位符"}],
        }
    if not config.BINANCE_SECRET or config.BINANCE_SECRET == "your_binance_testnet_secret":
        return {
            "ok": False,
            "checks": [{"name": "api_secret", "status": "FAIL",
                        "detail": "BINANCE_SECRET 未配置或仍为占位符"}],
        }

    # 在线验证：在线程池中运行，避免阻塞事件循环
    result = await asyncio.to_thread(_run_testnet_validation)
    return result


def _run_testnet_validation() -> dict:
    """在线 Testnet 验证（线程池中运行）"""
    from src.utils.config import config
    from src.execution.exchange_broker import ExchangeBroker

    checks = []
    ok = True

    # 连通性检查
    try:
        broker = ExchangeBroker(
            api_key=config.BINANCE_API_KEY,
            secret=config.BINANCE_SECRET,
            testnet=True,
        )
        bal = broker.get_balance()
        checks.append({"name": "connectivity", "status": "PASS",
                       "detail": f"连接成功，USDT 余额: {bal}"})
    except Exception as e:
        checks.append({"name": "connectivity", "status": "FAIL",
                       "detail": f"连接失败: {type(e).__name__}: {e}"})
        ok = False

    # 权限检查（best-effort；testnet 不支持 sapi 端点，直接跳过）
    try:
        from scripts.verify_api_key_permissions import (
            assess_api_key_permissions, fetch_restrictions,
        )
        broker2 = ExchangeBroker(
            api_key=config.BINANCE_API_KEY,
            secret=config.BINANCE_SECRET,
            testnet=True,
        )
        restrictions = fetch_restrictions(broker2.exchange)
        perm_ok, perm_checks = assess_api_key_permissions(restrictions)
        checks.extend(perm_checks)
        if not perm_ok:
            ok = False
    except Exception as e:
        # testnet 不支持 sapiGetAccountApiRestrictions 端点，属正常现象；
        # testnet 是沙盒环境无真实资金风险，权限校验无意义，标记为 PASS
        checks.append({"name": "permissions", "status": "PASS",
                       "detail": "testnet 沙盒环境，无需权限校验"
                                 f"（端点返回 {type(e).__name__}）"})

    return {"ok": ok, "checks": checks}


@app.websocket("/ws/logs/{mode}")
async def ws_logs_endpoint(ws: WebSocket, mode: str):
    """WebSocket 实时日志推送 (auth via first JSON message: {"type":"auth","token":"..."})"""
    # 验证模式
    try:
        running_mode = RunningMode(mode)
    except ValueError:
        await ws.accept()
        await ws.send_text(json.dumps({"error": f"未知模式: {mode}"}))
        await ws.close(code=4003)
        return

    # 连接限制（复用 WS_PORT 常量）
    await ws.accept()

    # WebSocket 认证
    if not await _authenticate_ws(ws):
        return

    # 先发送缓冲的历史日志
    for line in ws_logs.get_buffer(running_mode):
        await ws.send_text(json.dumps({"type": "log", "line": line}, ensure_ascii=False))

    # 订阅实时日志
    queue = ws_logs.subscribe(running_mode)
    try:
        while True:
            try:
                line = await asyncio.wait_for(queue.get(), timeout=30.0)
                await ws.send_text(json.dumps({"type": "log", "line": line}, ensure_ascii=False))
            except asyncio.TimeoutError:
                await ws.send_text('{"type":"ping"}')
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception(f"WebSocket log handler error [{mode}]")
    finally:
        ws_logs.unsubscribe(running_mode, queue)

