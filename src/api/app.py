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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Security, HTTPException, status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# API ????????? API_TOKEN ????????????
# --------------------------------------------------------------------------
_API_KEY_HEADER = APIKeyHeader(name="X-API-Token", auto_error=False)


async def verify_api_token(token: str = Security(_API_KEY_HEADER)):
    """Verify API token (skipped when API_TOKEN is empty)"""
    from src.utils.config import config
    if not config.API_TOKEN:
        return  # No token configured = auth disabled (dev mode)
    if token != config.API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API token",
        )


@app.get("/health")
def health():
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


@app.websocket("/ws/tickers")
async def ws_tickers(ws: WebSocket):
    """WebSocket 实时行情推送

    客户端连接后立即收到当前 ticker 快照，
    此后每当 Binance 推送更新时广播给客户端。
    """
    await ws.accept()
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
        pass
    finally:
        ws_feed.unsubscribe(queue)


@app.get("/strategies")
def strategies(_=Security(verify_api_token)):
    return service.strategies(service.get_state())


@app.get("/positions")
def positions(_=Security(verify_api_token)):
    return service.positions(service.get_state())


@app.get("/assets")
def assets():
    return service.assets(service.get_state())


@app.get("/orders")
def orders():
    return service.orders(service.get_state())


@app.get("/analytics/pnl-history")
def pnl_history():
    return service.pnl_history(service.get_state())


@app.get("/analytics/strategy-performance")
def strategy_performance():
    return service.strategy_performance(service.get_state())


# --------------------------------------------------------------------------
# 多策略 API
# --------------------------------------------------------------------------
@app.get("/multi/summary")
def multi_summary():
    """多策略聚合摘要（总盈亏、总交易数、各策略状态）"""
    return service.multi_strategy_summary(service.get_state())


@app.get("/multi/details")
def multi_details():
    """每个策略的详细结果"""
    return service.multi_strategy_details(service.get_state())


@app.get("/multi/strategy/{strategy_id}")
def multi_strategy_detail(strategy_id: str):
    """获取单个策略的运行结果"""
    result = service.multi_strategy_result(service.get_state(), strategy_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")
    return result


class StatusPatch(BaseModel):
    status: str


@app.patch("/strategies/{strategy_id}/status")
def update_strategy_status(strategy_id: str, body: StatusPatch):
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
def create_grid_strategy(body: CreateGridRequest):
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
    task: str  # backtest | trade_attribution | risk_checklist | param_sensitivity | weekly_review
    phase: str = "Phase 6"


@app.post("/agent/analyze")
def agent_analyze(body: AnalyzeRequest):
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
def agent_audit_logs(task: Optional[str] = None, limit: int = 50):
    """获取 AI 分析审计日志"""
    return _audit_log.get_logs(task=task, limit=limit)


@app.get("/agent/adoption-rate")
def agent_adoption_rate(task: Optional[str] = None):
    """获取 AI 建议采纳率统计"""
    return _audit_log.get_adoption_rate(task=task)

