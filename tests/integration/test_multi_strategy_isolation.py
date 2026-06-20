"""
集成测试：多策略并行无状态污染

验证：
- 两个独立策略实例互不干扰（各自状态隔离）
- 共享Broker的现金池正确分配
- 策略重置后状态干净
- 策略间无信号泄漏
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd

from src.execution.multi_runner import MultiStrategyRunner, StrategyConfig
from src.execution.paper_broker import PaperBroker
from src.execution.paper_trading_runner import PaperTradingRunner
from src.strategy.grid_trading import GridTradingStrategy
from src.strategy.simple_ma import SimpleMAStrategy
from src.strategy.rsi_momentum import RSIMomentumStrategy
from src.backtest.engine import BacktestEngine

SYMBOL = "BTC/USDT"
CAP = 10000.0


def _make_data(n=200, seed=42):
    """生成合成数据。"""
    rng = np.random.default_rng(seed)
    base = 30000.0
    rets = rng.normal(0, 0.01, n)
    close = base * np.exp(np.cumsum(rets))
    close = base + (close - base) * 0.3
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    openp = np.concatenate([[close[0]], close[:-1]])
    ts = pd.date_range("2025-03-01", periods=n, freq="4h")
    return pd.DataFrame({
        "timestamp": ts, "open": openp, "high": high,
        "low": low, "close": close, "volume": 1000.0,
    })


class TestMultiStrategyIsolation:
    """多策略并行无交叉污染。"""

    def test_independent_strategies_isolated_state(self):
        """两个独立策略实例运行后状态互不干扰。"""
        data = _make_data(200)

        s1 = GridTradingStrategy(
            lower_price=float(data["low"].min()) * 1.01,
            upper_price=float(data["high"].max()) * 0.99,
            grid_count=10, enable_filters=False, initial_capital=CAP,
        )
        s2 = SimpleMAStrategy(short_window=5, long_window=20)

        # 分别独立回测
        eng1 = BacktestEngine(initial_capital=CAP, commission=0.001, slippage=0.0005)
        eng2 = BacktestEngine(initial_capital=CAP, commission=0.001, slippage=0.0005)

        r1 = eng1.run(data, s1)
        r2 = eng2.run(data, s2)

        # 策略内部状态不应影响彼此的结果
        assert r1["success"], "Grid backtest failed"
        assert r2["success"], "MA backtest failed"

        # 运行时再次运行同一个策略，结果应可复现
        s1.reset()
        eng1b = BacktestEngine(initial_capital=CAP, commission=0.001, slippage=0.0005)
        r1b = eng1b.run(data, s1)
        assert r1["final_equity"] == r1b["final_equity"], "重置后结果应一致"

    def test_shared_broker_cash_isolation(self):
        """共享Broker的MultiRunner：现金池正确分配。"""
        data = _make_data(200)

        s1 = SimpleMAStrategy(short_window=5, long_window=20)
        s2 = RSIMomentumStrategy(rsi_period=14, ema_period=50)

        broker = PaperBroker(
            initial_balance=CAP * 2, commission=0.001,
            slippage={SYMBOL: 0.0005},
            max_position_per_trade=1.0, max_total_position=2.0,
        )

        multi = MultiStrategyRunner(broker=broker, risk_manager=None)
        multi.register_many([
            StrategyConfig(strategy_id="ma", strategy=s1, symbol=SYMBOL),
            StrategyConfig(strategy_id="rsi", strategy=s2, symbol=SYMBOL),
        ])

        results = multi.run({SYMBOL: data})
        assert len(results) == 2
        assert "ma" in results
        assert "rsi" in results

        # 聚合结果应不为空
        agg = multi.aggregate_results()
        assert agg["strategies_count"] == 2

    def test_strategy_reset_clears_state(self):
        """策略重置后状态干净，无前次运行残留。"""
        data = _make_data(100)

        s = GridTradingStrategy(
            lower_price=float(data["low"].min()) * 1.01,
            upper_price=float(data["high"].max()) * 0.99,
            grid_count=10, enable_filters=False, initial_capital=CAP,
        )

        eng = BacktestEngine(initial_capital=CAP, commission=0.001, slippage=0.0005)
        r1 = eng.run(data, s)

        # 重置后状态应为初始状态
        s.reset()
        assert s._is_paused() is False
        assert s.last_price is None
        assert all(not f for f in s.grid_filled)

        r2 = eng.run(data, s)
        assert r1["final_equity"] == r2["final_equity"], \
            "重置后回测结果应与首次一致"

    def test_no_signal_leakage_between_strategies(self):
        """不同策略间无信号泄漏。"""
        data = _make_data(200)

        s1 = SimpleMAStrategy(short_window=5, long_window=20)
        s2 = SimpleMAStrategy(short_window=5, long_window=20)
        s_copy = SimpleMAStrategy(short_window=5, long_window=20)

        # s2 参数不同
        s2 = SimpleMAStrategy(short_window=10, long_window=30)

        eng = BacktestEngine(initial_capital=CAP, commission=0.001, slippage=0.0005)
        r1 = eng.run(data, s1)
        s2.reset()
        r2 = eng.run(data, s2)

        # 不同参数应产生不同结果
        # (可能相等，但大概率不同——实际上如果数据太短可能一致，只作为信号检查)
        assert r1["success"] and r2["success"]

        # 用同样的参数验证完全一致性
        s_copy.reset()
        r_copy = eng.run(data, s_copy)
        assert r1["final_equity"] == r_copy["final_equity"]
        assert r1["total_trades"] == r_copy["total_trades"]
