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
from loguru import logger
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Security, HTTPException, status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from pydantic import BaseModel, Field
from typing import Literal

from src.api import service
from src.api.ws_feed import ws_feed
from src.utils.cache import cache
from src.agent import TradingAnalyzer, AuditLog


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/停止 Binance WebSocket 行情订阅"""
    task = asyncio.create_task(ws_feed.start())
    yield
    await ws_feed.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Crypto Trading System API", version="1.0", lifespan=lifespan)

# 开发期放行前端（Next.js 默认 3000；本项目 3000 被 Grafana 占用，前端用 3001）。
# 生产应收紧到具体来源。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
    ],
    allow_methods=["GET", "PATCH", "POST", "OPTIONS"],
    allow_headers=["X-API-Token", "Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Inject CSP and HSTS security headers on every HTTP response."""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response

# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["50/second"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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
    return {"status": "ok"}


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
    return service.account_summary(service.get_state())


@app.get("/market/tickers")
def tickers():
    # 优先使用 WebSocket 缓存（实时），回退到 REST 轮询
    ws_tickers = ws_feed.get_tickers()
    if ws_tickers:
        return ws_tickers
    return service.tickers(service.get_state())


WS_PORT = 8000
MAX_WS_CLIENTS = 50


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

    # WebSocket 认证 — 通过首条 JSON 消息 {"type":"auth","token":"..."}
    from src.utils.config import config
    if config.API_TOKEN is None or config.API_TOKEN == "":
        await ws.send_text(json.dumps({"error": "Server not configured"}))
        await ws.close(code=4001)
        return
    try:
        first_msg = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
        auth_data = json.loads(first_msg)
    except WebSocketDisconnect:
        return
    except asyncio.TimeoutError:
        await ws.send_text(json.dumps({"error": "Authentication timeout"}))
        await ws.close(code=4001)
        return
    except json.JSONDecodeError:
        await ws.send_text(json.dumps({"error": "Invalid auth message"}))
        await ws.close(code=4001)
        return

    if auth_data.get("type") != "auth" or not secrets.compare_digest(
        auth_data.get("token", ""), config.API_TOKEN
    ):
        await ws.send_text(json.dumps({"error": "Invalid token"}))
        await ws.close(code=4001)
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
    return service.strategies(service.get_state())


@app.get("/positions")
def positions(_=Security(verify_api_token)):
    return service.positions(service.get_state())


@app.get("/assets")
def assets(_=Security(verify_api_token)):
    return service.assets(service.get_state())


@app.get("/orders")
def orders(_=Security(verify_api_token)):
    return service.orders(service.get_state())


@app.get("/analytics/pnl-history")
def pnl_history(_=Security(verify_api_token)):
    return service.pnl_history(service.get_state())


@app.get("/analytics/strategy-performance")
def strategy_performance(_=Security(verify_api_token)):
    return service.strategy_performance(service.get_state())


# --------------------------------------------------------------------------
# 多策略 API
# --------------------------------------------------------------------------
@app.get("/multi/summary")
def multi_summary(_=Security(verify_api_token)):
    """多策略聚合摘要（总盈亏、总交易数、各策略状态）"""
    return service.multi_strategy_summary(service.get_state())


@app.get("/multi/details")
def multi_details(_=Security(verify_api_token)):
    """每个策略的详细结果"""
    return service.multi_strategy_details(service.get_state())


@app.get("/multi/strategy/{strategy_id}")
def multi_strategy_detail(strategy_id: str, _=Security(verify_api_token)):
    """获取单个策略的运行结果"""
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
# AI Agent 分析端点（只分析，不执行）
# --------------------------------------------------------------------------
_audit_log = AuditLog()
_analyzer = TradingAnalyzer(_audit_log)


class AnalyzeRequest(BaseModel):
    task: Literal["backtest", "trade_attribution", "risk_checklist", "param_sensitivity", "weekly_review"]
    phase: str = "Phase 6"


@app.post("/agent/analyze")
@limiter.limit("10/minute")
def agent_analyze(body: AnalyzeRequest, _=Security(verify_api_token)):
    """触发 AI 分析（只分析，不执行任何交易决策）"""
    state = service.get_state()

    if body.task == "backtest":
        # 使用 Paper Trading 结果作为回测替代
        result = state["result"]
        metrics = {
            "total_return": result.get("statistics", {}).get("total_return", 0),
            "win_rate": 0.5,  # Paper Trading 无内置胜率
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
        # 从 state 构建清单
        report = _analyzer.analyze_risk_checklist({
            "paper_trading_days": service._running_days(state),
            "risk_tests_passed": True,
            "api_key_restricted": False,  # 需要人工确认
            "initial_capital": 10000.0,
            "max_drawdown": 0.0,  # 需要实际数据
            "data_quality_score": 1.0,
        })
    elif body.task == "param_sensitivity":
        import pandas as pd
        base_params = getattr(state["strategy"], "parameters", {})
        report = _analyzer.analyze_param_sensitivity(
            scan_results=pd.DataFrame(),
            base_params=base_params,
        )
    else:
        return {"error": f"Unknown task type: {body.task}"}

    return report


@app.get("/agent/audit-logs")
@limiter.limit("10/minute")
def agent_audit_logs(task: Optional[str] = None, limit: int = 50, _=Security(verify_api_token)):
    """获取 AI 分析审计日志"""
    return _audit_log.get_logs(task=task, limit=limit)


@app.get("/agent/adoption-rate")
@limiter.limit("10/minute")
def agent_adoption_rate(task: Optional[str] = None, _=Security(verify_api_token)):
    """获取 AI 建议采纳率统计"""
    return _audit_log.get_adoption_rate(task=task)

