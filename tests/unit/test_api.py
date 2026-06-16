"""
API 契约测试：用 TestClient 跑通各端点，校验返回结构符合
frontend/lib/types.ts 的字段约定。

服务首次请求会跑一次 Paper Trading（进程内缓存），故 client 用 fixture
复用，避免重复运行。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.utils.logger import setup_logger

setup_logger(log_level="ERROR")  # 压低 Paper Trading 运行噪声

from fastapi.testclient import TestClient

from src.api.app import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_account_summary_shape(client):
    d = client.get("/account/summary").json()
    for k in [
        "totalEquity", "availableBalance", "positionValue", "unrealizedPnl",
        "todayPnl", "todayPnlPct", "totalPnl", "totalPnlPct",
    ]:
        assert k in d and isinstance(d[k], (int, float))
    # 权益 = 现金 + 持仓市值（对账）
    assert d["totalEquity"] == pytest.approx(
        d["availableBalance"] + d["positionValue"], rel=1e-6
    )


def test_strategies_shape(client):
    rows = client.get("/strategies").json()
    assert len(rows) == 1
    s = rows[0]
    assert s["type"] == "grid"
    assert s["status"] in ("running", "paused", "stopped")
    assert set(["upperPrice", "lowerPrice", "gridCount"]).issubset(s["grid"])


def test_orders_shape(client):
    rows = client.get("/orders").json()
    assert rows, "应有成交记录"
    o = rows[0]
    for k in ["id", "time", "symbol", "side", "price", "amount", "status", "fee"]:
        assert k in o
    assert o["side"] in ("buy", "sell")


def test_pnl_history_monotonic_dates(client):
    rows = client.get("/analytics/pnl-history").json()
    assert len(rows) > 1
    assert rows[0]["cumulativePnl"] == pytest.approx(0.0)
    for r in rows:
        assert set(["date", "equity", "pnl", "cumulativePnl"]).issubset(r)


def test_strategy_performance_winrate_range(client):
    perf = client.get("/analytics/strategy-performance").json()[0]
    assert 0.0 <= perf["winRate"] <= 100.0
    assert perf["trades"] >= 0


def test_patch_status_echo(client):
    r = client.patch("/strategies/grid-btc-usdt/status", json={"status": "paused"})
    assert r.json() == {"id": "grid-btc-usdt", "status": "paused"}
