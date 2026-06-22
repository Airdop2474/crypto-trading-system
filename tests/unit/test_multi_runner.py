"""
MultiStrategyRunner 单元测试

验证：
- 策略注册与查找（register / get_slot / strategy_ids）
- 重复注册报错、disabled 策略跳过
- 单策略运行结果与独立 PaperTradingRunner 一致
- 多策略共享 Broker（现金池共享，持仓按 symbol 隔离）
- 批量回放（run）：各策略独立生成信号、独立成交
- 聚合结果（aggregate_results）
- 空数据处理
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from src.execution.multi_runner import MultiStrategyRunner, StrategyConfig, StrategySlot
from src.execution.paper_broker import PaperBroker
from src.execution.paper_trading_runner import PaperTradingRunner
from src.strategy.base import Strategy, Order


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------
def make_data(closes: list, symbol: str = "BTC/USDT") -> pd.DataFrame:
    """构造 OHLCV 测试数据"""
    times = pd.date_range("2024-01-01", periods=len(closes), freq="4h")
    return pd.DataFrame({
        "timestamp": times,
        "open": closes,
        "high": [c + 1 for c in closes],
        "low": [c - 1 for c in closes],
        "close": closes,
        "volume": [100.0] * len(closes),
    })


class ScriptedStrategy(Strategy):
    """按 bar 索引返回预设信号的测试策略"""

    def __init__(self, signals: dict, name: str = "Scripted"):
        super().__init__(name=name)
        self.signals = signals
        self.i = -1
        self.fills = []

    def on_bar(self, data, current_time):
        self.i += 1
        return self.signals.get(self.i)

    def on_fill(self, trade):
        self.fills.append(trade)

    def reset(self):
        super().reset()
        self.i = -1
        self.fills = []


def make_multi_runner(balance=100000.0) -> MultiStrategyRunner:
    broker = PaperBroker(
        balance, commission=0.001,
        slippage={"BTC/USDT": 0.0, "ETH/USDT": 0.0},
        max_position_per_trade=1.0, max_total_position=1.0,
    )
    return MultiStrategyRunner(broker=broker), broker


# ---------------------------------------------------------------------------
# 注册与查找
# ---------------------------------------------------------------------------
class TestRegistration:
    def test_register_and_get_slot(self):
        mr, _ = make_multi_runner()
        strat = ScriptedStrategy({})
        cfg = StrategyConfig(strategy_id="test-1", strategy=strat, symbol="BTC/USDT")
        mr.register(cfg)

        slot = mr.get_slot("test-1")
        assert slot is not None
        assert slot.config.strategy_id == "test-1"
        assert slot.config.symbol == "BTC/USDT"

    def test_strategy_ids(self):
        mr, _ = make_multi_runner()
        mr.register(StrategyConfig("s1", ScriptedStrategy({}), "BTC/USDT"))
        mr.register(StrategyConfig("s2", ScriptedStrategy({}), "ETH/USDT"))
        assert mr.strategy_ids == ["s1", "s2"]

    def test_duplicate_id_raises(self):
        mr, _ = make_multi_runner()
        mr.register(StrategyConfig("dup", ScriptedStrategy({}), "BTC/USDT"))
        with pytest.raises(ValueError, match="already registered"):
            mr.register(StrategyConfig("dup", ScriptedStrategy({}), "BTC/USDT"))

    def test_disabled_strategy_skipped(self):
        mr, _ = make_multi_runner()
        mr.register(StrategyConfig("off", ScriptedStrategy({}), "BTC/USDT", enabled=False))
        assert mr.get_slot("off") is None
        assert len(mr.slots) == 0

    def test_register_many(self):
        mr, _ = make_multi_runner()
        configs = [
            StrategyConfig(f"s{i}", ScriptedStrategy({}), "BTC/USDT")
            for i in range(5)
        ]
        mr.register_many(configs)
        assert len(mr.slots) == 5

    def test_get_slot_nonexistent_returns_none(self):
        mr, _ = make_multi_runner()
        assert mr.get_slot("nope") is None

    def test_slots_returns_copy(self):
        mr, _ = make_multi_runner()
        mr.register(StrategyConfig("s1", ScriptedStrategy({}), "BTC/USDT"))
        slots = mr.slots
        slots.clear()
        # 原始不应被修改
        assert len(mr.slots) == 1


# ---------------------------------------------------------------------------
# 运行
# ---------------------------------------------------------------------------
class TestRun:
    def test_single_strategy_matches_runner(self):
        """单策略运行结果应与独立 PaperTradingRunner 一致"""
        closes = [100, 110, 120, 115, 130]
        data = make_data(closes)

        # 独立 runner
        broker1 = PaperBroker(
            100000.0, commission=0.001, slippage={"BTC/USDT": 0.0},
            max_position_per_trade=1.0, max_total_position=1.0,
        )
        runner1 = PaperTradingRunner(broker1, "BTC/USDT")
        strat1 = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]})
        result1 = runner1.run(data, strat1)

        # multi runner
        mr, _ = make_multi_runner()
        strat2 = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]})
        cfg = StrategyConfig("test", strat2, "BTC/USDT")
        mr.register(cfg)
        results = mr.run({"BTC/USDT": data})

        r2 = results["test"]
        # 核心指标应一致
        assert r2["statistics"]["total_trades"] == result1["statistics"]["total_trades"]
        assert r2["realized_pnl"] == pytest.approx(result1["realized_pnl"])

    def test_multi_strategy_independent_signals(self):
        """多个策略独立生成信号，互不影响"""
        closes = [100, 100, 100, 100]
        data = make_data(closes)

        mr, _ = make_multi_runner()
        # 策略 A: bar 0 买入
        sA = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]}, name="A")
        # 策略 B: bar 1 买入
        sB = ScriptedStrategy({1: [Order("BUY", tag=1, fraction=0.1)]}, name="B")

        mr.register(StrategyConfig("a", sA, "BTC/USDT"))
        mr.register(StrategyConfig("b", sB, "BTC/USDT"))
        results = mr.run({"BTC/USDT": data})

        # 共享 broker 下 total_trades 是全局的（A + B）
        # A 的 trade_history 应有 1 笔 buy（bar 0 发信号，bar 1 open 成交）
        a_trades = results["a"]["trade_history"]
        b_trades = results["b"]["trade_history"]
        # A: bar 0 signal → bar 1 open fill
        assert len(a_trades) >= 1
        # B: bar 1 signal → bar 2 open fill
        assert len(b_trades) >= 1
        # A 的 on_fill 被调用 1 次
        assert len(sA.fills) == 1
        # B 的 on_fill 被调用 1 次
        assert len(sB.fills) == 1

    def test_multi_strategy_shared_cash(self):
        """多策略共享 broker 现金池"""
        closes = [100, 100, 100, 100]
        data = make_data(closes)

        mr, broker = make_multi_runner(balance=10000.0)
        # 两个策略各用 50% 资金买入
        sA = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.5)]})
        sB = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.5)]})

        mr.register(StrategyConfig("a", sA, "BTC/USDT"))
        mr.register(StrategyConfig("b", sB, "BTC/USDT"))
        mr.run({"BTC/USDT": data})

        # A 先成交（fraction 0.5），B 后成交（剩余 cash 的 fraction 0.5）
        # 总交易应 >= 1（至少 A 成功）
        assert broker.get_balance() < 10000.0  # 现金已减少

    def test_empty_data(self):
        """空数据不报错"""
        mr, _ = make_multi_runner()
        mr.register(StrategyConfig("s", ScriptedStrategy({}), "BTC/USDT"))
        results = mr.run({"BTC/USDT": make_data([])})
        assert "s" in results
        assert results["s"]["statistics"]["total_trades"] == 0

    def test_no_data_for_symbol(self):
        """策略的 symbol 没有数据时应优雅处理"""
        mr, _ = make_multi_runner()
        mr.register(StrategyConfig("s", ScriptedStrategy({}), "ETH/USDT"))
        # 只给 BTC 数据，不给 ETH
        results = mr.run({"BTC/USDT": make_data([100, 110, 120])})
        assert results["s"]["statistics"]["total_trades"] == 0

    def test_run_resets_state(self):
        """run() 应重置 runner 和策略状态"""
        data = make_data([100, 110, 120, 130])
        mr, _ = make_multi_runner()
        strat = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]})
        mr.register(StrategyConfig("s", strat, "BTC/USDT"))

        # 第一次运行
        r1 = mr.run({"BTC/USDT": data})
        # 验证策略被重置（第二次运行不应累加 fills）
        r2 = mr.run({"BTC/USDT": data})

        # 两次运行各自的 closed_trades 应相同
        assert len(r1["s"]["closed_trades"]) == len(r2["s"]["closed_trades"])
        # 策略的 fill 计数器应被重置
        assert strat.i == 3  # 最后一次运行处理了 4 根 bar（0-3）

    def test_buy_sell_cycle(self):
        """买入-卖出完整周期"""
        closes = [100, 100, 100, 100, 100]
        data = make_data(closes)

        mr, _ = make_multi_runner()
        strat = ScriptedStrategy({
            0: [Order("BUY", tag=1, fraction=0.1)],
            1: [Order("SELL", tag=1)],
        })
        mr.register(StrategyConfig("s", strat, "BTC/USDT"))
        results = mr.run({"BTC/USDT": data})

        assert results["s"]["statistics"]["total_trades"] == 2
        assert len(results["s"]["closed_trades"]) == 1


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------
class TestAggregate:
    def test_aggregate_empty(self):
        mr, _ = make_multi_runner()
        agg = mr.aggregate_results()
        assert agg["strategies_count"] == 0
        assert agg["total_realized_pnl"] == 0.0

    def test_aggregate_single(self):
        data = make_data([100, 100, 100, 100])
        mr, _ = make_multi_runner()
        strat = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]})
        mr.register(StrategyConfig("s", strat, "BTC/USDT"))
        mr.run({"BTC/USDT": data})

        agg = mr.aggregate_results()
        assert agg["strategies_count"] == 1
        assert agg["total_bars_processed"] == 4
        assert len(agg["strategies"]) == 1
        assert agg["strategies"][0]["strategy_id"] == "s"

    def test_aggregate_multi(self):
        data = make_data([100, 100, 100, 100])
        mr, _ = make_multi_runner()
        mr.register(StrategyConfig("a", ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]}), "BTC/USDT"))
        mr.register(StrategyConfig("b", ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]}), "BTC/USDT"))
        mr.run({"BTC/USDT": data})

        agg = mr.aggregate_results()
        assert agg["strategies_count"] == 2
        # 两个策略各处理 4 根 bar
        assert agg["total_bars_processed"] == 8
        assert sum(s["open_lots"] for s in agg["strategies"]) == 2

    def test_aggregate_strategy_names(self):
        data = make_data([100, 100])
        mr, _ = make_multi_runner()
        s = ScriptedStrategy({}, name="MyStrategy")
        mr.register(StrategyConfig("my-id", s, "BTC/USDT"))
        mr.run({"BTC/USDT": data})

        agg = mr.aggregate_results()
        assert agg["strategies"][0]["strategy_name"] == "MyStrategy"


# ---------------------------------------------------------------------------
# process_bar（实时模式）
# ---------------------------------------------------------------------------
class TestProcessBar:
    def test_process_bar_matches_symbol(self):
        """process_bar 只处理 symbol 匹配的策略"""
        mr, _ = make_multi_runner()
        mr.register(StrategyConfig("btc", ScriptedStrategy({}), "BTC/USDT"))
        mr.register(StrategyConfig("eth", ScriptedStrategy({}), "ETH/USDT"))

        # 构造带 _symbol 标记的 bar
        bar = pd.Series({"open": 100, "close": 100, "high": 101, "low": 99,
                         "volume": 100, "timestamp": pd.Timestamp("2024-01-01"),
                         "_symbol": "BTC/USDT"})
        historical = pd.DataFrame([bar])

        results = mr.process_bar(bar, historical, bar["timestamp"])
        # 只有 BTC 策略被调用
        assert "btc" in results
        assert "eth" not in results


# ---------------------------------------------------------------------------
# 边界条件
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_strategy_with_no_signals(self):
        """无信号策略不产生交易"""
        data = make_data([100, 110, 120])
        mr, _ = make_multi_runner()
        mr.register(StrategyConfig("idle", ScriptedStrategy({}), "BTC/USDT"))
        results = mr.run({"BTC/USDT": data})
        assert results["idle"]["statistics"]["total_trades"] == 0

    def test_different_symbols(self):
        """不同 symbol 的策略各自独立"""
        btc_data = make_data([100, 110, 120, 130])
        eth_data = make_data([2000, 2100, 2200, 2300])

        mr, broker = make_multi_runner()
        btc_strat = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]})
        eth_strat = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]})

        mr.register(StrategyConfig("btc", btc_strat, "BTC/USDT"))
        mr.register(StrategyConfig("eth", eth_strat, "ETH/USDT"))
        results = mr.run({"BTC/USDT": btc_data, "ETH/USDT": eth_data})

        # 各策略的 on_fill 应被调用 1 次
        assert len(btc_strat.fills) == 1
        assert len(eth_strat.fills) == 1
        # 两个 symbol 都有持仓
        assert broker.get_position("BTC/USDT") > 0
        assert broker.get_position("ETH/USDT") > 0

    def test_bars_processed_tracking(self):
        """bars_processed 正确追踪"""
        data = make_data([100, 110, 120, 130, 140])
        mr, _ = make_multi_runner()
        mr.register(StrategyConfig("s", ScriptedStrategy({}), "BTC/USDT"))
        mr.run({"BTC/USDT": data})

        slot = mr.get_slot("s")
        assert slot.bars_processed == 5


class TestCrashIsolation:
    def test_one_strategy_crash_doesnt_kill_others(self):
        """一个策略 process_bar 抛异常不影响其他策略继续运行"""

        class CrashingStrategy(Strategy):
            """在 on_bar 中始终抛异常"""
            def __init__(self):
                super().__init__("crash")
                self.calls = 0

            def on_bar(self, data, current_time):
                self.calls += 1
                raise RuntimeError("intentional crash")

        class CountingStrategy(Strategy):
            """记录 on_bar 调用次数"""
            def __init__(self):
                super().__init__("counter")
                self.calls = 0

            def on_bar(self, data, current_time):
                self.calls += 1
                return None

        data = make_data([100, 110, 120, 130])
        mr, broker = make_multi_runner()
        mr.register(StrategyConfig("crasher", CrashingStrategy(), "BTC/USDT"))
        mr.register(StrategyConfig("counter", CountingStrategy(), "BTC/USDT"))

        # run() 应完整跑完不抛异常
        results = mr.run({"BTC/USDT": data})

        # crasher 策略被调用 4 次（每根 bar）
        crasher_strat = mr.get_slot("crasher").config.strategy
        assert crasher_strat.calls == 4
        assert results["crasher"]["statistics"]["total_trades"] == 0

        # counter 策略也被调用 4 次——crasher 的异常没有中断整个循环
        counter_strat = mr.get_slot("counter").config.strategy
        assert counter_strat.calls == 4
        assert mr.get_slot("counter").bars_processed == 4
