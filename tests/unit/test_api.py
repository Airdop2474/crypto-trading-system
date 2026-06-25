"""
API 契约测试：用 TestClient 跑通各端点，校验返回结构符合
frontend/lib/types.ts 的字段约定。

服务首次请求会跑一次 Paper Trading（进程内缓存），故 client 用 fixture
复用，避免重复运行。
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.utils.logger import setup_logger

setup_logger(log_level="ERROR")  # 压低 Paper Trading 运行噪声

from fastapi.testclient import TestClient

from src.api.app import app
from src.api import service as svc


_TOKEN_HEADER = {"X-API-Token": "test-token"}

# 懒加载：显式激活 Paper Trading，确保数据已生成
svc.activate()
svc.get_state()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health(client):
    d = client.get("/health").json()
    assert d["status"] == "ok"
    # /health 返回 status + checks（DB/缓存连通性），无需认证
    assert "checks" in d
    assert "database" in d["checks"]
    assert "cache" in d["checks"]


def test_health_detailed_requires_auth(client):
    """R-10: /health/detailed 需认证"""
    resp = client.get("/health/detailed")
    assert resp.status_code in (403, 401)


def test_health_detailed_with_auth(client):
    """R-10: /health/detailed 认证后返回完整信息"""
    resp = client.get("/health/detailed", headers=_TOKEN_HEADER)
    assert resp.status_code == 200
    d = resp.json()
    assert d["status"] == "ok"
    assert "ws_connected" in d
    assert "ws_clients" in d
    assert "cache_backend" in d
    assert "cache_available" in d


def test_account_summary_shape(client):
    d = client.get("/account/summary", headers=_TOKEN_HEADER).json()
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
    rows = client.get("/strategies", headers=_TOKEN_HEADER).json()
    assert len(rows) == 1
    s = rows[0]
    assert s["type"] == "grid"
    assert s["status"] in ("running", "paused", "stopped")
    assert set(["upperPrice", "lowerPrice", "gridCount"]).issubset(s["grid"])


def test_orders_shape(client):
    """R-订单分页：/orders 返回 {items,total,limit,offset,has_more,stats}"""
    d = client.get("/orders", headers=_TOKEN_HEADER).json()
    # 顶层结构
    for k in ["items", "total", "limit", "offset", "has_more", "stats"]:
        assert k in d, f"missing key: {k}"
    assert isinstance(d["items"], list)
    assert d["items"], "应有成交记录"
    assert d["total"] >= len(d["items"])
    assert d["limit"] >= 1
    assert d["offset"] == 0
    o = d["items"][0]
    for k in ["id", "time", "symbol", "side", "price", "amount", "status", "fee"]:
        assert k in o
    assert o["side"] in ("buy", "sell")

    # stats 结构
    s = d["stats"]
    for k in [
        "total_orders", "filled_count", "open_count",
        "partially_filled_count", "canceled_count", "total_fee",
    ]:
        assert k in s, f"missing stats key: {k}"
    assert s["total_orders"] == d["total"]
    assert s["filled_count"] == d["total"]  # Paper 模式全部 filled
    assert s["total_fee"] >= 0


def test_orders_pagination(client):
    """分页参数：limit + offset 正确切片，has_more 正确判定"""
    # 先取一份全集，确认 total
    full = client.get("/orders", headers=_TOKEN_HEADER).json()
    total = full["total"]
    assert total > 0

    # stats 不随分页变化
    stats_full = full["stats"]

    # limit=2, offset=0
    p1 = client.get("/orders?limit=2&offset=0", headers=_TOKEN_HEADER).json()
    assert p1["limit"] == 2
    assert p1["offset"] == 0
    assert len(p1["items"]) == min(2, total)
    assert p1["has_more"] == (total > 2)
    # stats 在分页响应中保持一致
    assert p1["stats"] == stats_full

    # limit=2, offset=2（下一页）
    if total > 2:
        p2 = client.get("/orders?limit=2&offset=2", headers=_TOKEN_HEADER).json()
        assert len(p2["items"]) == min(2, total - 2)
        assert p2["has_more"] == (total > 4)
        assert p2["stats"] == stats_full
        # 两页 id 不重叠
        ids1 = {o["id"] for o in p1["items"]}
        ids2 = {o["id"] for o in p2["items"]}
        assert not (ids1 & ids2)

    # 越界 offset 返回空 items，has_more=False
    tail = client.get(f"/orders?limit=10&offset={total}", headers=_TOKEN_HEADER).json()
    assert tail["items"] == []
    assert tail["has_more"] is False
    assert tail["stats"] == stats_full  # 即便空页 stats 仍正确

    # limit 超上限被夹紧到 500
    big = client.get("/orders?limit=9999", headers=_TOKEN_HEADER).json()
    assert big["limit"] == 500

    # 负 offset 被夹紧到 0
    neg = client.get("/orders?offset=-5", headers=_TOKEN_HEADER).json()
    assert neg["offset"] == 0


def test_pnl_history_monotonic_dates(client):
    rows = client.get("/analytics/pnl-history", headers=_TOKEN_HEADER).json()
    assert len(rows) > 1
    assert rows[0]["cumulativePnl"] == pytest.approx(0.0)
    for r in rows:
        assert set(["date", "equity", "pnl", "cumulativePnl"]).issubset(r)


def test_strategy_performance_winrate_range(client):
    perf = client.get("/analytics/strategy-performance", headers=_TOKEN_HEADER).json()[0]
    assert 0.0 <= perf["winRate"] <= 100.0
    assert perf["trades"] >= 0


def test_patch_status_echo(client):
    r = client.patch("/strategies/grid-btc-usdt/status", json={"status": "paused"}, headers=_TOKEN_HEADER)
    assert r.json() == {"id": "grid-btc-usdt", "status": "paused"}


def test_tickers_fallback_when_exchange_down(client, monkeypatch):
    """实时行情外呼失败时回退本地派生，不能 500（覆盖离线路径）。"""
    import src.api.market as market

    def boom(*a, **k):
        raise RuntimeError("simulated offline")

    monkeypatch.setattr(market, "get_live_tickers", boom)
    r = client.get("/market/tickers", headers=_TOKEN_HEADER)
    assert r.status_code == 200
    rows = r.json()
    assert rows
    for k in ["symbol", "price", "changePct", "volume", "high", "low"]:
        assert k in rows[0]


# --------------------------------------------------------------------------
# 风险指标端点
# --------------------------------------------------------------------------
def test_risk_metrics_shape(client):
    """R-风险：/account/risk-metrics 返回完整风险指标"""
    d = client.get("/account/risk-metrics", headers=_TOKEN_HEADER).json()
    for k in [
        "max_drawdown", "max_drawdown_pct", "sharpe_ratio", "sortino_ratio",
        "volatility", "annual_return", "current_drawdown",
        "equity_peak", "equity_current", "max_drawdown_duration",
    ]:
        assert k in d, f"missing key: {k}"
    # max_drawdown 应为非正数（回撤 <= 0）
    assert d["max_drawdown"] <= 0
    assert d["max_drawdown_pct"] <= 0
    # 当前权益应为正
    assert d["equity_current"] > 0
    assert d["equity_peak"] > 0
    assert d["equity_peak"] >= d["equity_current"]
    # 当前回撤 <= 0
    assert d["current_drawdown"] <= 0


def test_drawdown_curve_shape(client):
    """R-风险：/risk/drawdown-curve 返回回撤曲线，点数与权益快照一致"""
    rows = client.get("/risk/drawdown-curve", headers=_TOKEN_HEADER).json()
    assert isinstance(rows, list)
    assert len(rows) > 0
    for r in rows:
        for k in ["date", "equity", "peak", "drawdown"]:
            assert k in r
        # peak >= equity（峰值不可能小于当前）
        assert r["peak"] >= r["equity"]
        # drawdown <= 0（回撤非正）
        assert r["drawdown"] <= 0
    # 峰值应单调不减
    peaks = [r["peak"] for r in rows]
    assert peaks == sorted(peaks)


def test_risk_status_shape(client):
    """R-风险：/risk/status 返回风控状态机信息"""
    d = client.get("/risk/status", headers=_TOKEN_HEADER).json()
    for k in [
        "state", "can_trade", "daily_pnl", "daily_loss_limit_pct",
        "consecutive_losses", "max_consecutive_losses",
        "cumulative_pnl", "total_drawdown_pct", "max_total_drawdown_pct",
        "events", "limits",
    ]:
        assert k in d, f"missing key: {k}"
    assert d["state"] in ("ACTIVE", "PAUSED", "STOPPED")
    assert isinstance(d["can_trade"], bool)
    assert isinstance(d["events"], list)
    assert isinstance(d["limits"], dict)
    for k in ["max_daily_loss", "max_consecutive_losses", "max_total_position", "max_total_drawdown"]:
        assert k in d["limits"]


def test_security_headers_present(client):
    """R-安全：所有响应应含 CSP / HSTS / X-Content-Type-Options 等头"""
    r = client.get("/health")
    csp = r.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "script-src" in csp  # 不再只有 default-src，应显式放宽 script
    assert "connect-src" in csp  # 允许 WebSocket
    assert r.headers.get("strict-transport-security") == "max-age=31536000"
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"


# --------------------------------------------------------------------------
# 持仓历史 / 盈亏分布
# --------------------------------------------------------------------------
def test_positions_history_shape(client):
    """R-持仓历史：/positions/history 返回平仓交易列表"""
    rows = client.get("/positions/history", headers=_TOKEN_HEADER).json()
    assert isinstance(rows, list)
    if rows:
        o = rows[0]
        for k in ["id", "strategy_id", "strategy_name", "symbol", "tag",
                  "close_time", "profit", "profit_pct"]:
            assert k in o, f"missing key: {k}"
        assert isinstance(o["profit"], (int, float))


def test_positions_history_limit(client):
    """limit 参数生效"""
    full = client.get("/positions/history", headers=_TOKEN_HEADER).json()
    limited = client.get("/positions/history?limit=5", headers=_TOKEN_HEADER).json()
    assert len(limited) <= 5
    assert len(limited) <= len(full)


def test_pnl_distribution_shape(client):
    """R-盈亏分布：/analytics/pnl-distribution 返回 bins + stats"""
    d = client.get("/analytics/pnl-distribution", headers=_TOKEN_HEADER).json()
    for k in ["bins", "stats"]:
        assert k in d
    assert isinstance(d["bins"], list)
    assert len(d["bins"]) >= 2
    for b in d["bins"]:
        for k in ["range", "count", "label"]:
            assert k in b
        assert isinstance(b["count"], int)
    s = d["stats"]
    for k in ["total", "wins", "losses", "win_rate", "avg_profit", "avg_loss",
              "profit_factor", "best", "worst"]:
        assert k in s, f"missing stats key: {k}"
    assert s["total"] == s["wins"] + s["losses"]
    assert 0 <= s["win_rate"] <= 100


def test_win_rate_trend_shape(client):
    """R-胜率趋势：/analytics/win-rate-trend 返回滚动胜率序列"""
    rows = client.get("/analytics/win-rate-trend", headers=_TOKEN_HEADER).json()
    assert isinstance(rows, list)
    if rows:
        for r in rows:
            for k in ["index", "close_time", "win_rate", "strategy_id"]:
                assert k in r
            assert 0 <= r["win_rate"] <= 100


def test_strategy_correlation_shape(client):
    """R-相关性矩阵：/analytics/strategy-correlation 返回 N×N 矩阵"""
    d = client.get("/analytics/strategy-correlation", headers=_TOKEN_HEADER).json()
    for k in ["strategies", "labels", "matrix"]:
        assert k in d
    assert isinstance(d["strategies"], list)
    assert isinstance(d["labels"], list)
    assert len(d["strategies"]) == len(d["labels"])
    n = len(d["strategies"])
    if n > 0:
        assert len(d["matrix"]) == n
        for row in d["matrix"]:
            assert len(row) == n
        # 对角线应为 1.0（自相关）
        for i in range(n):
            assert abs(d["matrix"][i][i] - 1.0) < 1e-6 or d["matrix"][i][i] == 0


def test_admin_refresh_state(client):
    """R-管理：POST /admin/refresh-state 重置 state 缓存"""
    # 先确认 state 已构建（前面测试已触发）
    client.get("/account/summary", headers=_TOKEN_HEADER)
    # 重置
    r = client.post("/admin/refresh-state", headers=_TOKEN_HEADER)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    # 再次请求会重建（测试不报错即说明 reset + rebuild 链路正常）
    r2 = client.get("/account/summary", headers=_TOKEN_HEADER)
    assert r2.status_code == 200


def test_emergency_stop_requires_auth(client):
    """R-急停：POST /admin/emergency-stop 需认证"""
    resp = client.post("/admin/emergency-stop")
    assert resp.status_code in (403, 401)


def test_emergency_stop(client):
    """R-急停：POST /admin/emergency-stop 触发 STOPPED + 写信号文件"""
    # 确保 state 已构建（可能被前序测试 reset_state 清空）
    svc.activate()
    svc.get_state()
    client.get("/account/summary", headers=_TOKEN_HEADER)
    r = client.post("/admin/emergency-stop", headers=_TOKEN_HEADER)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["current_state"] == "STOPPED"
    assert "previous_state" in d
    # 信号文件应被创建
    from pathlib import Path
    signal_file = Path("data/.emergency_stop")
    assert signal_file.exists(), "急停信号文件未被创建"
    # 清理信号文件
    signal_file.unlink(missing_ok=True)
