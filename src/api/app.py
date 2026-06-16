"""
FastAPI 应用：把 Paper Trading 引擎的真实结果按 frontend/lib/api.ts
约定的路由暴露给前端。所有端点返回 frontend/lib/types.ts 的契约结构。

启动：
    uvicorn src.api.app:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.api import service

app = FastAPI(title="Crypto Trading System API", version="1.0")

# 开发期放行前端（Next.js 默认 3000；本项目 3000 被 Grafana 占用，前端用 3001）。
# 生产应收紧到具体来源。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
    ],
    allow_methods=["GET", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/account/summary")
def account_summary():
    return service.account_summary(service.get_state())


@app.get("/market/tickers")
def tickers():
    return service.tickers(service.get_state())


@app.get("/strategies")
def strategies():
    return service.strategies(service.get_state())


@app.get("/positions")
def positions():
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


class StatusPatch(BaseModel):
    status: str


@app.patch("/strategies/{strategy_id}/status")
def update_strategy_status(strategy_id: str, body: StatusPatch):
    return service.set_strategy_status(strategy_id, body.status)
