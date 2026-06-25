"""
Unit tests for src/api/live_data.py

Tests cover:
1. _load_all_states — 空目录 / 读取文件 / .final 优先 / 跳过无 strategy_name / TTL 缓存
2. _get_last_price / _get_symbol — 提取与默认值
3. account_summary / positions / assets / multi_strategy_result — 聚合逻辑

测试策略：
- 用 monkeypatch 把 live_data._DATA_DIR 指向 tmp_path
- 在 tmp_path 下创建模拟 daemon state JSON 文件
- 每个测试前后重置 _STATE_CACHE / _STATE_CACHE_TS 避免 TTL 缓存串扰
"""

import json
import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.api import live_data
from src.utils.logger import setup_logger

setup_logger(log_level="ERROR")  # 压低测试日志噪声


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _default_state(**overrides):
    """构造一个默认的 daemon state 字典，可选顶层覆写。"""
    state = {
        "version": 1,
        "symbol": "BTC/USDT",
        "strategy_name": "grid",
        "initial_capital": 10000.0,
        "day_count": 0,
        "last_bar_ts": "2024-01-01 00:00:00",
        "broker": {"balance": 10000.0, "positions": {}, "orders": []},
        "runner": {"lots": {}, "realized_pnl": 0.0, "closed_trades": []},
        "risk": {"state": "ACTIVE", "prev_close": None, "peak_equity": 10000.0},
    }
    state.update(overrides)
    return state


def _write_state(data_dir, state, mode="live_paper", strategy=None, final=False):
    """把 state 字典写成 daemon state JSON 文件，返回 Path。

    Args:
        data_dir: 目标目录 (Path)
        state:    state 字典
        mode:     模式 (live_paper / replay_paper / testnet_live)
        strategy: 策略名；None 时从 state['strategy_name'] 取
        final:    为 True 时写 .final 文件 (在 .json 后追加 .final)
    """
    strat = strategy or state.get("strategy_name", "grid")
    fname = f"paper_daemon_state_{mode}_{strat}.json"
    path = data_dir / fname
    if final:
        path = Path(str(path) + ".final")
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_cache():
    """每个测试前后重置 TTL 缓存，避免跨测试泄漏。"""
    live_data._STATE_CACHE = []
    live_data._STATE_CACHE_TS = 0.0
    yield
    live_data._STATE_CACHE = []
    live_data._STATE_CACHE_TS = 0.0


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """把 live_data._DATA_DIR 指向一个干净的 tmp_path。"""
    monkeypatch.setattr(live_data, "_DATA_DIR", tmp_path)
    return tmp_path


# ==========================================================================
# 1. _load_all_states — 空目录
# ==========================================================================

class TestLoadAllStatesEmpty:
    def test_empty_dir_returns_empty_list(self, data_dir):
        """无 state 文件时返回空列表。"""
        assert live_data._load_all_states() == []

    def test_has_live_data_false_when_empty(self, data_dir):
        """无 state 文件时 has_live_data() 返回 False。"""
        assert live_data.has_live_data() is False


# ==========================================================================
# 2. _load_all_states — 读取文件
# ==========================================================================

class TestLoadAllStatesReadFiles:
    def test_reads_state_file_correctly(self, data_dir):
        """用 tmp_path 创建模拟 state 文件，验证正确读取。"""
        _write_state(data_dir, _default_state(
            strategy_name="grid",
            broker={"balance": 12345.0, "positions": {}, "orders": []},
        ))
        states = live_data._load_all_states()
        assert len(states) == 1
        assert states[0]["strategy_name"] == "grid"
        assert states[0]["broker"]["balance"] == 12345.0

    def test_prefers_final_file(self, data_dir):
        """存在 .final 文件时，优先读取 .final 而非主 state 文件。"""
        # 主文件：balance=10000
        _write_state(data_dir, _default_state(
            strategy_name="grid",
            broker={"balance": 10000.0, "positions": {}, "orders": []},
        ))
        # .final 文件：balance=99999（回放结束强制平仓后的最终状态）
        _write_state(data_dir, _default_state(
            strategy_name="grid",
            broker={"balance": 99999.0, "positions": {}, "orders": []},
        ), final=True)

        states = live_data._load_all_states()
        assert len(states) == 1
        # 应读取 .final 的内容
        assert states[0]["broker"]["balance"] == 99999.0

    def test_skips_file_without_strategy_name(self, data_dir):
        """无 strategy_name 的文件应被跳过。"""
        state = _default_state()
        del state["strategy_name"]
        _write_state(data_dir, state)
        states = live_data._load_all_states()
        assert states == []

    def test_ttl_cache_no_reread_within_3s(self, data_dir):
        """3 秒内重复调用不重读文件（TTL 缓存命中）。"""
        # 第一次：写一个 grid state 文件并加载
        _write_state(data_dir, _default_state(strategy_name="grid"))
        states1 = live_data._load_all_states()
        assert len(states1) == 1

        # 新增第二个 state 文件（rsi）
        _write_state(data_dir, _default_state(strategy_name="rsi"))

        # 立即再次调用（在 3 秒 TTL 窗口内）——应返回缓存，仍只有 1 个
        states2 = live_data._load_all_states()
        assert len(states2) == 1
        assert states2[0]["strategy_name"] == "grid"

        # 手动让缓存过期（回退 4 秒），再次调用应重读，看到 2 个
        live_data._STATE_CACHE_TS = time.monotonic() - 4.0
        states3 = live_data._load_all_states()
        assert len(states3) == 2


# ==========================================================================
# 3. _get_last_price
# ==========================================================================

class TestGetLastPrice:
    def test_from_risk_prev_close(self):
        """从 risk.prev_close 获取价格。"""
        states = [_default_state(
            risk={"state": "ACTIVE", "prev_close": 51000.0, "peak_equity": 10000.0},
        )]
        assert live_data._get_last_price(states) == 51000.0

    def test_fallback_to_last_order_price(self):
        """prev_close 无效时回退到最后一笔订单的 price。"""
        orders = [
            {"order_id": "1", "price": 49000.0, "amount": 0.1, "commission": 0},
            {"order_id": "2", "price": 50500.0, "amount": 0.1, "commission": 0},
        ]
        states = [_default_state(
            risk={"state": "ACTIVE", "prev_close": None, "peak_equity": 10000.0},
            broker={"balance": 10000.0, "positions": {}, "orders": orders},
        )]
        assert live_data._get_last_price(states) == 50500.0

    def test_default_50000_when_no_data(self):
        """无 prev_close 且无 orders 时返回默认 50000。"""
        states = [_default_state(
            risk={"state": "ACTIVE", "prev_close": None, "peak_equity": 10000.0},
            broker={"balance": 10000.0, "positions": {}, "orders": []},
        )]
        assert live_data._get_last_price(states) == 50000.0


# ==========================================================================
# 4. _get_symbol
# ==========================================================================

class TestGetSymbol:
    def test_from_state(self):
        """从 state 文件获取 symbol。"""
        states = [_default_state(symbol="ETH/USDT")]
        assert live_data._get_symbol(states) == "ETH/USDT"

    def test_default_btc_usdt_when_missing(self):
        """无 symbol 时返回默认 BTC/USDT。"""
        states = [_default_state(symbol=None)]
        assert live_data._get_symbol(states) == "BTC/USDT"

    def test_default_btc_usdt_when_empty(self):
        """空 states 列表时返回默认 BTC/USDT。"""
        assert live_data._get_symbol([]) == "BTC/USDT"


# ==========================================================================
# 5. account_summary
# ==========================================================================

class TestAccountSummary:
    def test_no_state_returns_none(self, data_dir):
        """无 state 时返回 None。"""
        assert live_data.account_summary() is None

    def test_aggregates_balance_initial_realized_pnl(self, data_dir):
        """有 state 时正确聚合 balance / initial / realized / pnl。"""
        # 策略 1: balance=10000, initial=10000, realized=100
        _write_state(data_dir, _default_state(
            strategy_name="grid",
            initial_capital=10000.0,
            broker={"balance": 10000.0, "positions": {}, "orders": []},
            runner={"lots": {}, "realized_pnl": 100.0, "closed_trades": []},
            risk={"state": "ACTIVE", "prev_close": 51000.0, "peak_equity": 10000.0},
        ))
        # 策略 2: balance=9000, initial=10000, realized=-50
        _write_state(data_dir, _default_state(
            strategy_name="rsi",
            initial_capital=10000.0,
            broker={"balance": 9000.0, "positions": {}, "orders": []},
            runner={"lots": {}, "realized_pnl": -50.0, "closed_trades": []},
            risk={"state": "ACTIVE", "prev_close": 51000.0, "peak_equity": 10000.0},
        ))

        d = live_data.account_summary()
        # total_balance = 10000 + 9000 = 19000
        # total_initial = 10000 + 10000 = 20000
        # total_realized = 100 + (-50) = 50
        # 无持仓 → position_value = 0, total_equity = 19000
        # total_pnl = 19000 - 20000 = -1000
        assert d["availableBalance"] == 19000.0
        assert d["positionValue"] == 0.0
        assert d["totalEquity"] == 19000.0
        assert d["todayPnl"] == 50.0
        assert d["totalPnl"] == -1000.0
        assert d["todayPnlPct"] == 0.25   # 50 / 20000 * 100
        assert d["totalPnlPct"] == -5.0   # -1000 / 20000 * 100

    def test_aggregates_lots_as_total_position(self, data_dir):
        """聚合多个策略的 lots 为总持仓。"""
        # 策略 1: 0.1 BTC @ 50000
        _write_state(data_dir, _default_state(
            strategy_name="grid",
            initial_capital=10000.0,
            broker={"balance": 10000.0, "positions": {}, "orders": []},
            runner={
                "lots": {"0": {"amount": 0.1, "cost_price": 50000.0}},
                "realized_pnl": 0.0,
                "closed_trades": [],
            },
            risk={"state": "ACTIVE", "prev_close": 51000.0, "peak_equity": 10000.0},
        ))
        # 策略 2: 0.2 BTC @ 49000
        _write_state(data_dir, _default_state(
            strategy_name="rsi",
            initial_capital=10000.0,
            broker={"balance": 9000.0, "positions": {}, "orders": []},
            runner={
                "lots": {"0": {"amount": 0.2, "cost_price": 49000.0}},
                "realized_pnl": 0.0,
                "closed_trades": [],
            },
            risk={"state": "ACTIVE", "prev_close": 51000.0, "peak_equity": 10000.0},
        ))

        d = live_data.account_summary()
        # total_amount = 0.1 + 0.2 = 0.3
        # total_cost   = 0.1*50000 + 0.2*49000 = 5000 + 9800 = 14800
        # last_price   = 51000
        # position_value = 0.3 * 51000 = 15300
        # total_balance  = 10000 + 9000 = 19000
        # total_equity   = 19000 + 15300 = 34300
        # unrealizedPnl  = 15300 - 14800 = 500
        assert d["positionValue"] == 15300.0
        assert d["totalEquity"] == 34300.0
        assert d["unrealizedPnl"] == 500.0


# ==========================================================================
# 6. positions
# ==========================================================================

class TestPositions:
    def test_no_state_returns_none(self, data_dir):
        """无 state 时返回 None。"""
        assert live_data.positions() is None

    def test_no_lots_returns_empty_list(self, data_dir):
        """无持仓时返回空列表。"""
        _write_state(data_dir, _default_state(
            runner={"lots": {}, "realized_pnl": 0.0, "closed_trades": []},
            risk={"state": "ACTIVE", "prev_close": 51000.0, "peak_equity": 10000.0},
        ))
        assert live_data.positions() == []

    def test_with_lots_calculates_avg_cost_and_upnl(self, data_dir):
        """有持仓时正确计算 avg_cost / unrealizedPnl。"""
        _write_state(data_dir, _default_state(
            strategy_name="grid",
            symbol="BTC/USDT",
            initial_capital=10000.0,
            broker={"balance": 10000.0, "positions": {}, "orders": []},
            runner={
                "lots": {"0": {"amount": 0.1, "cost_price": 50000.0}},
                "realized_pnl": 0.0,
                "closed_trades": [],
            },
            risk={"state": "ACTIVE", "prev_close": 52000.0, "peak_equity": 10000.0},
        ))

        rows = live_data.positions()
        assert len(rows) == 1
        pos = rows[0]
        # total_amount = 0.1, total_cost = 0.1*50000 = 5000
        # avg_cost = 5000 / 0.1 = 50000
        # last_price = 52000
        # upnl = 0.1 * (52000 - 50000) = 200
        # upnl_pct = 200 / 5000 * 100 = 4.0
        assert pos["symbol"] == "BTC/USDT"
        assert pos["side"] == "buy"
        assert pos["size"] == 0.1
        assert pos["entryPrice"] == 50000.0
        assert pos["markPrice"] == 52000.0
        assert pos["unrealizedPnl"] == 200.0
        assert pos["unrealizedPnlPct"] == 4.0

    def test_aggregates_multi_strategy_lots(self, data_dir):
        """多策略 lots 聚合为单个净持仓。"""
        _write_state(data_dir, _default_state(
            strategy_name="grid",
            runner={
                "lots": {"0": {"amount": 0.1, "cost_price": 50000.0}},
                "realized_pnl": 0.0, "closed_trades": [],
            },
            risk={"state": "ACTIVE", "prev_close": 52000.0, "peak_equity": 10000.0},
        ))
        _write_state(data_dir, _default_state(
            strategy_name="rsi",
            runner={
                "lots": {"0": {"amount": 0.2, "cost_price": 49000.0}},
                "realized_pnl": 0.0, "closed_trades": [],
            },
            risk={"state": "ACTIVE", "prev_close": 52000.0, "peak_equity": 10000.0},
        ))

        rows = live_data.positions()
        assert len(rows) == 1
        pos = rows[0]
        # total_amount = 0.3, total_cost = 5000 + 9800 = 14800
        # avg_cost = 14800 / 0.3 ≈ 49333.33
        # upnl = 0.3 * (52000 - 49333.33) = 0.3 * 2666.67 = 800
        assert pos["size"] == pytest.approx(0.3, abs=1e-8)
        assert pos["entryPrice"] == pytest.approx(49333.33, abs=0.01)
        assert pos["unrealizedPnl"] == 800.0


# ==========================================================================
# 7. assets
# ==========================================================================

class TestAssets:
    def test_no_state_returns_none(self, data_dir):
        """无 state 时返回 None。"""
        assert live_data.assets() is None

    def test_returns_usdt_and_btc(self, data_dir):
        """正确返回 USDT + BTC 资产列表。"""
        _write_state(data_dir, _default_state(
            broker={"balance": 10000.0, "positions": {}, "orders": []},
            runner={
                "lots": {"0": {"amount": 0.2, "cost_price": 50000.0}},
                "realized_pnl": 0.0, "closed_trades": [],
            },
            risk={"state": "ACTIVE", "prev_close": 51000.0, "peak_equity": 10000.0},
        ))

        rows = live_data.assets()
        assert len(rows) == 2
        amap = {r["asset"]: r for r in rows}
        assert "USDT" in amap
        assert "BTC" in amap
        # USDT: balance=10000
        assert amap["USDT"]["total"] == 10000.0
        assert amap["USDT"]["valueUsdt"] == 10000.0
        # BTC: amount=0.2, value=0.2*51000=10200
        assert amap["BTC"]["total"] == 0.2
        assert amap["BTC"]["valueUsdt"] == 10200.0

    def test_no_btc_returns_only_usdt(self, data_dir):
        """无 BTC 持仓时只返回 USDT。"""
        _write_state(data_dir, _default_state(
            broker={"balance": 10000.0, "positions": {}, "orders": []},
            runner={"lots": {}, "realized_pnl": 0.0, "closed_trades": []},
            risk={"state": "ACTIVE", "prev_close": 51000.0, "peak_equity": 10000.0},
        ))

        rows = live_data.assets()
        assert len(rows) == 1
        assert rows[0]["asset"] == "USDT"
        assert rows[0]["total"] == 10000.0


# ==========================================================================
# 8. multi_strategy_result
# ==========================================================================

class TestMultiStrategyResult:
    def test_no_state_returns_none(self, data_dir):
        """无 state 时返回 None。"""
        assert live_data.multi_strategy_result("grid-btc-usdt") is None

    def test_matching_strategy_id(self, data_dir):
        """匹配 strategy_id 时返回正确格式。"""
        _write_state(data_dir, _default_state(
            strategy_name="grid",
            symbol="BTC/USDT",
            initial_capital=10000.0,
            broker={
                "balance": 10500.0,
                "positions": {},
                "orders": [
                    {
                        "order_id": "ord-1",
                        "timestamp": "2024-01-01 00:00:00",
                        "symbol": "BTC/USDT",
                        "side": "buy",
                        "order_type": "market",
                        "amount": 0.1,
                        "price": 50000.0,
                        "commission": 5.0,
                    },
                ],
            },
            runner={
                "lots": {"0": {"amount": 0.1, "cost_price": 50000.0}},
                "realized_pnl": 200.0,
                "closed_trades": [
                    {"tag": "0", "time": "2024-01-01", "profit": 200.0},
                ],
            },
            risk={"state": "ACTIVE", "prev_close": 51000.0, "peak_equity": 10500.0},
        ))

        # strategy_id = f"{strategy_name}-{symbol.lower().replace('/', '-')}"
        result = live_data.multi_strategy_result("grid-btc-usdt")
        assert result is not None
        assert result["symbol"] == "BTC/USDT"
        assert result["realized_pnl"] == 200.0
        assert result["signals"] == []

        # statistics
        stats = result["statistics"]
        assert stats["initial_balance"] == 10000.0
        assert stats["current_balance"] == 10500.0
        assert stats["total_trades"] == 1
        assert stats["total_commission"] == 5.0
        assert stats["total_slippage"] == 0.0
        assert stats["total_cost"] == 5.0
        assert stats["positions"] == {"0": 0.1}

        # open_lots: Record[str, number]
        assert result["open_lots"] == {"0": 0.1}

        # trade_history
        assert len(result["trade_history"]) == 1
        th = result["trade_history"][0]
        assert th["order_id"] == "ord-1"
        assert th["side"] == "buy"
        assert th["price"] == 50000.0
        assert th["amount"] == 0.1
        assert th["commission"] == 5.0
        assert th["slippage"] == 0.0
        assert th["status"] == "filled"

        # closed_trades
        assert len(result["closed_trades"]) == 1
        ct = result["closed_trades"][0]
        assert ct["tag"] == "0"
        assert ct["profit"] == 200.0

    def test_non_matching_returns_none(self, data_dir):
        """不匹配 strategy_id 时返回 None。"""
        _write_state(data_dir, _default_state(
            strategy_name="grid",
            symbol="BTC/USDT",
            risk={"state": "ACTIVE", "prev_close": 51000.0, "peak_equity": 10000.0},
        ))
        # 存在 grid-btc-usdt，但请求 rsi-btc-usdt
        assert live_data.multi_strategy_result("rsi-btc-usdt") is None
