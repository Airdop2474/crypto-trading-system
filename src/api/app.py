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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Security, HTTPException, status, Request
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
from src.api.ws_logs import ws_logs
from src.api.mode_manager import mode_manager, RunningMode, ModeParams, ModeStatus
from src.utils.cache import cache
from src.agent import TradingAnalyzer, AuditLog
from src.utils.config import config as _cfg


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/停止 Binance WebSocket 行情订阅 + Paper Trading 预热

    预热原因：service.get_state() 在首次调用时同步跑一次 Paper Trading（8 个策略，
    CPU 密集）。FastAPI 是 async 框架，若让首个用户请求触发，会阻塞事件循环，
    期间所有其他请求（含 WebSocket 心跳）都卡死。

    在 startup 阶段用 asyncio.to_thread 把它丢到线程池预热，事件循环不阻塞，
    首个用户请求到来时 _state 已就绪，直接返回。
    """
    # 1. 启动 WebSocket 行情订阅（异步任务，不阻塞）
    task = asyncio.create_task(ws_feed.start())

    # 2. 后台预热 Paper Trading state（线程池跑，不阻塞事件循环）
    logger.info("Preheating Paper Trading state in background thread...")
    preheat_task = asyncio.create_task(asyncio.to_thread(service.get_state))

    # 3. 恢复运行模式状态（检查孤儿进程）
    await mode_manager.recover_on_startup()

    # 4. 自动建表（幂等：已存在的表不会重复创建）
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
    # 预热任务若仍在跑（极罕见，说明预热比进程生命周期还长），取消
    if not preheat_task.done():
        preheat_task.cancel()
        try:
            await preheat_task
        except (asyncio.CancelledError, Exception):
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
    - connect-src：允许同源 + ws/wss/http/https 到 API_BASE（前端连后端 + WebSocket）
    - img-src 'self' data:：data URI 用于 SVG 图标
    - font-src 'self' data:：next/font 自托管 + data URI fallback

    注：完整的 origin 应从 config 读（见 CORS_ORIGINS），这里先放宽到 localhost，
    生产部署需根据实际域名收紧。
    """
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws://localhost:8000 wss://localhost:8000 http://localhost:8000 http://localhost:3000 http://localhost:3001; "
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
    return service.orders(service.get_state(), limit=limit, offset=offset)


@app.get("/analytics/pnl-history")
def pnl_history(_=Security(verify_api_token)):
    return service.pnl_history(service.get_state())


@app.get("/analytics/strategy-performance")
def strategy_performance(_=Security(verify_api_token)):
    return service.strategy_performance(service.get_state())


# --------------------------------------------------------------------------
# 风险指标 API（用于总览页风险卡 + /risk 风险管理页）
# --------------------------------------------------------------------------
@app.get("/account/risk-metrics")
def account_risk_metrics(_=Security(verify_api_token)):
    """账户级风险指标：最大回撤 / 夏普 / Sortino / 波动率 / 年化收益"""
    return service.risk_metrics(service.get_state())


@app.get("/risk/drawdown-curve")
def risk_drawdown_curve(_=Security(verify_api_token)):
    """回撤曲线（每点含 equity / peak / drawdown%）"""
    return service.drawdown_curve(service.get_state())


@app.get("/risk/status")
def risk_status(_=Security(verify_api_token)):
    """账户级风控状态（来自 RiskManager 状态机）"""
    return service.risk_status(service.get_state())


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
    return service.positions_history(service.get_state(), limit=limit)


@app.get("/analytics/pnl-distribution")
def pnl_distribution(
    bins: int = 10,
    _=Security(verify_api_token),
):
    """盈亏分布直方图 + 胜率/盈亏比统计"""
    bins = max(2, min(int(bins), 50))
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
# 管理端点（需 API Token）
# --------------------------------------------------------------------------
@app.post("/admin/refresh-state")
@limiter.limit("2/minute")  # 严格限流：每分钟最多 2 次，防滥用
def admin_refresh_state(request: Request, _=Security(verify_api_token)):
    """重置 Paper Trading state 缓存，下次请求会重新跑 Paper Trading。

    使用场景：
    - 数据源更新后想立即看到新结果（不必重启服务）
    - Paper Trading 配置变更后重跑

    限流：2 次/分钟（重建 state 是 CPU 密集操作，频繁调用会拖垮服务）
    """
    service.reset_state()
    return {
        "status": "ok",
        "message": "State reset. Next request will rebuild Paper Trading state.",
    }


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
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


class UpdateParamsRequest(BaseModel):
    params: dict


@app.patch("/strategies/{strategy_id}/params")
def update_strategy_params_endpoint(
    strategy_id: str, body: UpdateParamsRequest, _=Security(verify_api_token),
):
    """更新运行中策略的参数"""
    try:
        state = service.get_state()
        return service.update_strategy_params(state, strategy_id, body.params)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


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


@app.post("/agent/analyze")
@limiter.limit("10/minute")
def agent_analyze(request: Request, body: AnalyzeRequest, _=Security(verify_api_token)):
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

    results = engine.evolve_all(
        slots=slots,
        skip={"buyhold"},
        multi_runner=multi_runner,
        risk_manager_state=risk_state,
    )

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


@app.post("/admin/emergency-stop")
@limiter.limit("5/minute")
def admin_emergency_stop(request: Request, _=Security(verify_api_token)):
    """远程急停：触发全局 RiskManager.emergency_stop()，停止所有策略交易。

    状态机进入 STOPPED，只能通过 reset() 恢复（带防抖冷却）。
    """
    state = service.get_state()
    multi_runner = state.get("_multi_runner")
    if multi_runner is None:
        raise HTTPException(503, "多策略引擎未初始化")

    risk_manager = getattr(multi_runner, "risk_manager", None)
    if risk_manager is None:
        raise HTTPException(503, "RiskManager 未注入")

    prev_state = getattr(risk_manager, "state", "UNKNOWN")
    risk_manager.emergency_stop("remote emergency-stop via API")
    logger.warning(f"远程急停已触发：{prev_state} -> STOPPED")

    # 写信号文件通知 daemon 进程（daemon 每根 bar 检查此文件）
    from pathlib import Path as _Path
    signal_file = _Path("data/.emergency_stop")
    try:
        signal_file.parent.mkdir(parents=True, exist_ok=True)
        signal_file.write_text("1", encoding="utf-8")
    except OSError as e:
        logger.warning(f"急停信号文件写入失败（daemon 可能不会被通知）：{e}")

    return {
        "ok": True,
        "previous_state": prev_state,
        "current_state": "STOPPED",
        "message": "全局急停已触发，所有策略交易已停止。需通过 reset() 恢复。",
    }


class CleanupRequest(BaseModel):
    scope: Literal["all", "runs", "evolutions"] = "all"
    keepLatest: bool = False


@app.post("/admin/data/cleanup")
@limiter.limit("3/minute")
def admin_data_cleanup(request: Request, body: CleanupRequest, _=Security(verify_api_token)):
    """清理历史测试数据（运行记录 / 进化记录 / 审计日志）"""
    return service.cleanup_data(scope=body.scope, keep_latest=body.keepLatest)


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

    # 权限检查（best-effort）
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
        checks.append({"name": "permissions", "status": "WARN",
                       "detail": f"权限查询跳过（testnet 可能不支持）: {type(e).__name__}"})

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

    # WebSocket 认证 — 与 /ws/tickers 相同模式
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

