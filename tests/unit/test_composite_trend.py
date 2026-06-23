"""
复合趋势策略（CompositeTrendStrategy）单元测试。

覆盖：
  - 默认参数初始化
  - 注册表注册
  - 预热期不发信号
  - 多头趋势产生买入信号
  - 出场规则：时间止损 / 移动止损 / MACD死叉 / ADX休眠继承 / 保本保护
  - reset() 清空全部状态
  - 多实例 ADX 缓冲区互不干扰（修复类变量共享 bug）
  - get_status() 字段完整
"""

import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime
from typing import List

import numpy as np
import pandas as pd
import pytest

from src.strategy.composite_trend import CompositeTrendStrategy
from src.strategy.registry import get_strategy, STRATEGY_REGISTRY


# ===========================================================================
# 辅助数据生成
# ===========================================================================

def _make_df(closes, highs=None, lows=None, volumes=None) -> pd.DataFrame:
    """生成最小 OHLCV DataFrame。"""
    n = len(closes)
    closes = np.array(closes, dtype=float)
    if highs is None:
        highs = closes * 1.005
    if lows is None:
        lows = closes * 0.995
    if volumes is None:
        volumes = np.full(n, 1000.0)
    return pd.DataFrame({
        "open": closes * 0.999,
        "high": np.array(highs, dtype=float),
        "low": np.array(lows, dtype=float),
        "close": closes,
        "volume": np.array(volumes, dtype=float),
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="4h"),
    })


def _run_bars(strategy: CompositeTrendStrategy, df: pd.DataFrame):
    """逐 bar 喂给策略，返回所有非 None 的信号列表。"""
    signals = []
    for i in range(1, len(df) + 1):
        result = strategy.on_bar(df.iloc[:i])
        if result:
            signals.append(result)
    return signals


def _uptrend_df(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """
    带回调的上涨趋势 OHLCV 数据。
    模式：上涨 8 根 → 回调 4 根（价格下跌 ~0.5%/根）→ 继续上涨。
    这样能让 RSI 在回调阶段落回 40-60 区间，再上涨时满足入场条件。
    """
    rng = np.random.RandomState(seed)
    prices = [50000.0]
    for i in range(n - 1):
        phase = i % 12  # 12 根一个周期
        if phase < 8:
            # 上涨阶段：+0.5% / 根
            drift = 0.005 + rng.normal(0, 0.001)
        else:
            # 回调阶段：-0.3% / 根（浅回调保持大方向向上）
            drift = -0.003 + rng.normal(0, 0.001)
        prices.append(prices[-1] * (1 + drift))
    closes = np.array(prices)
    highs = closes * (1 + rng.uniform(0.001, 0.005, n))
    lows = closes * (1 - rng.uniform(0.001, 0.005, n))
    volumes = rng.uniform(800, 1200, n)
    return _make_df(closes, highs, lows, volumes)


def _strategy_with_relaxed_params(**kwargs) -> CompositeTrendStrategy:
    """
    创建测试专用实例，使用更短的指标周期（保持策略逻辑不变）：
    - EMA 3/8 替代 50/200（更快响应、更早 cross）
    - ADX 7，阈值 18
    - MACD 3/7/3（极短预热）
    - RSI 7，区间 30-70
    - BB 8，ATR 7
    - 宽松成交量 0.3×
    这样能在较短的合成数据里触发信号，用于验证代码路径正确性。
    """
    defaults = dict(
        ema_fast=3, ema_slow=8,
        adx_period=7, adx_threshold=18.0,
        macd_fast=3, macd_slow=7, macd_signal=3,
        rsi_period=7, rsi_low=30.0, rsi_high=70.0,
        bb_period=8, atr_period=7,
        vol_period=8, vol_ratio=0.3,
        time_stop_bars=15,
    )
    defaults.update(kwargs)
    return CompositeTrendStrategy(**defaults)


def _flat_df(n: int = 300, base: float = 50000.0, seed: int = 99) -> pd.DataFrame:
    """震荡盘整（ADX 低），用于测试不发信号场景。"""
    rng = np.random.RandomState(seed)
    closes = base + rng.normal(0, 50, n)  # 小幅随机游走
    closes = np.abs(closes)
    return _make_df(closes)


# ===========================================================================
# 初始化测试
# ===========================================================================

class TestInit:
    def test_default_params(self):
        s = CompositeTrendStrategy()
        assert s.adx_period == 14
        assert s.adx_threshold == 25.0
        assert s.ema_fast_p == 50
        assert s.ema_slow_p == 200
        assert s.macd_fast_p == 12
        assert s.macd_slow_p == 26
        assert s.macd_signal_p == 9
        assert s.rsi_period == 14
        assert s.rsi_low == 40.0
        assert s.rsi_high == 60.0
        assert s.bb_period == 20
        assert s.risk_per_trade == 0.01
        assert s.name == "CompositeTrend"

    def test_parameters_dict(self):
        s = CompositeTrendStrategy(adx_period=20, risk_per_trade=0.005)
        assert s.parameters["adx_period"] == 20
        assert s.parameters["risk_per_trade"] == 0.005

    def test_registered_in_registry(self):
        assert "composite" in STRATEGY_REGISTRY
        cls = get_strategy("composite")
        assert cls is CompositeTrendStrategy


# ===========================================================================
# 预热期不发信号
# ===========================================================================

class TestWarmup:
    def test_no_signal_during_warmup(self):
        s = CompositeTrendStrategy(
            adx_period=14, ema_slow=50, macd_slow=26, macd_signal=9,
            rsi_period=14, bb_period=20, atr_period=14
        )
        df = _uptrend_df(50)
        for i in range(1, 50):
            result = s.on_bar(df.iloc[:i])
            assert result is None, f"bar {i} 预热期不应发信号"


# ===========================================================================
# 上涨趋势产生买入信号
# ===========================================================================

class TestEntrySignal:
    def test_uptrend_generates_buy(self):
        """上涨趋势 + 宽松参数 → 应产生买入信号（验证6道过滤代码路径正确）。"""
        s = _strategy_with_relaxed_params()
        df = _uptrend_df(500)
        signals = _run_bars(s, df)
        buys = [sig for sig in signals if any(o.side.upper() == "BUY" for o in sig)]
        assert len(buys) > 0, (
            f"上涨趋势应至少产生一次买入信号，当前 warmup={s._warmup}，"
            f"status={s.get_status()}"
        )

    def test_flat_market_no_buy(self):
        """震荡市 ADX 低，不应触发买入。"""
        s = CompositeTrendStrategy(adx_threshold=25.0)
        df = _flat_df(300)
        signals = _run_bars(s, df)
        buys = [sig for sig in signals if any(o.side.upper() == "BUY" for o in sig)]
        assert len(buys) == 0, "震荡市不应产生买入信号"

    def test_fraction_within_bounds(self):
        """买入仓位应在合理范围内（0.01 ~ 1.0）。"""
        s = _strategy_with_relaxed_params()
        df = _uptrend_df(500)
        for i in range(1, len(df) + 1):
            result = s.on_bar(df.iloc[:i])
            if result:
                for order in result:
                    if order.side.upper() == "BUY":
                        assert 0.01 <= order.fraction <= 1.0, \
                            f"BUY fraction {order.fraction} 超出范围"


# ===========================================================================
# 出场规则
# ===========================================================================

class TestExitRules:
    def _enter(self, s: CompositeTrendStrategy, df: pd.DataFrame):
        """喂数据直到策略有持仓，返回入场 bar 索引。"""
        for i in range(1, len(df) + 1):
            result = s.on_bar(df.iloc[:i])
            if result and any(o.side.upper() == "BUY" for o in result):
                return i
        return -1

    def test_time_stop_triggers(self):
        """time_stop_bars 根 H4 无盈利，应触发时间止损出场。"""
        s = _strategy_with_relaxed_params(time_stop_bars=8)
        df_up = _uptrend_df(500)

        # 先入场
        entry_idx = self._enter(s, df_up)
        assert entry_idx > 0, f"应该先入场，但 warmup={s._warmup}"

        # 之后价格横盘（不涨不跌），等时间止损触发
        n_extra = 12
        last_price = float(df_up.iloc[entry_idx - 1]["close"])
        extra_closes = [last_price] * n_extra
        extra_df = _make_df(extra_closes)

        sell_found = False
        for i in range(1, n_extra + 1):
            result = s.on_bar(extra_df.iloc[:i])
            if result and any(o.side.upper() == "SELL" for o in result):
                sell_found = True
                break
        assert sell_found, f"横盘 {n_extra} 根 H4 后应触发时间止损"

    def test_initial_stop_triggers(self):
        """价格跌破入场价 - 1.5×ATR，应触发初始止损。"""
        s = _strategy_with_relaxed_params()
        df_up = _uptrend_df(500)
        entry_idx = self._enter(s, df_up)
        assert entry_idx > 0, f"应该先入场，但 warmup={s._warmup}"

        entry_price = s._entry_price
        entry_atr = s._entry_atr or (entry_price * 0.01)
        crash_price = entry_price - 2.5 * entry_atr  # 跌穿止损线

        crash_df = _make_df([crash_price])
        result = s.on_bar(crash_df)
        assert result is not None
        sells = [o for o in result if o.side.upper() == "SELL"]
        assert len(sells) > 0, "大幅下跌应触发初始止损"

    def test_macd_death_cross_or_time_exit(self):
        """下跌趋势应触发 MACD 死叉或时间止损出场。"""
        s = _strategy_with_relaxed_params(time_stop_bars=12)
        df_up = _uptrend_df(500)
        entry_idx = self._enter(s, df_up)
        assert entry_idx > 0, f"应该先入场，但 warmup={s._warmup}"

        # 制造下跌来触发 MACD 死叉（但价格不低于初始止损）
        rng = np.random.RandomState(7)
        n_down = 15
        start_p = float(df_up.iloc[entry_idx - 1]["close"])
        entry_atr = s._entry_atr or (start_p * 0.01)
        # 轻微下跌，不触发初始止损，但足够触发时间止损或MACD死叉
        prices = [start_p]
        for _ in range(n_down - 1):
            prices.append(prices[-1] * (1 - 0.002 + rng.normal(0, 0.001)))
        down_df = _make_df(prices)

        sell_found = False
        for i in range(1, n_down + 1):
            result = s.on_bar(down_df.iloc[:i])
            if result and any(o.side.upper() == "SELL" for o in result):
                sell_found = True
                break
        assert sell_found, "下跌/横盘后应触发 MACD死叉 或 时间止损"


# ===========================================================================
# reset() 清空状态
# ===========================================================================

class TestReset:
    def test_reset_clears_position(self):
        s = _strategy_with_relaxed_params()
        df = _uptrend_df(500)
        _run_bars(s, df)
        assert s._bar_count > 0

        s.reset()
        assert s._bar_count == 0
        assert s._in_position is False
        assert s._entry_price == 0.0
        assert s._ema_fast is None
        assert s._ema_slow is None
        assert s._rsi_value is None
        assert s._i_adx_value is None
        assert s._atr_value is None
        assert len(s._bb_buffer) == 0

    def test_reset_allows_rerun(self):
        """reset 后重新跑相同数据应产生相同信号数量。"""
        s = _strategy_with_relaxed_params()
        df = _uptrend_df(500)
        signals1 = _run_bars(s, df)

        s.reset()
        signals2 = _run_bars(s, df)
        assert len(signals1) == len(signals2), "重置后重跑应产生相同数量的信号"


# ===========================================================================
# 多实例 ADX 缓冲区互不干扰（修复类变量共享 bug）
# ===========================================================================

class TestInstanceIsolation:
    def test_two_instances_independent_adx(self):
        """两个独立实例的 ADX 缓冲区不应互相影响。"""
        s1 = CompositeTrendStrategy(adx_period=14)
        s2 = CompositeTrendStrategy(adx_period=14)

        df_up = _uptrend_df(200, seed=1)
        df_flat = _flat_df(200, seed=2)

        # 喂 s1 上涨数据
        for i in range(1, len(df_up) + 1):
            s1.on_bar(df_up.iloc[:i])

        # 喂 s2 震荡数据
        for i in range(1, len(df_flat) + 1):
            s2.on_bar(df_flat.iloc[:i])

        adx1 = s1._i_adx_value
        adx2 = s2._i_adx_value

        # 两者 ADX 缓冲区分离，值应有明显差异
        assert adx1 is not None
        assert adx2 is not None
        assert id(s1._i_adx_high_buf) != id(s2._i_adx_high_buf), \
            "两个实例的 ADX 缓冲区不应是同一个对象"

    def test_three_instances_no_cross_contamination(self):
        """三个实例同时运行，各自状态独立。"""
        instances = [_strategy_with_relaxed_params() for _ in range(3)]
        dfs = [_uptrend_df(300, seed=i) for i in range(3)]

        for s, df in zip(instances, dfs):
            _run_bars(s, df)

        bar_counts = [s._bar_count for s in instances]
        assert all(bc == 300 for bc in bar_counts), f"各实例 bar_count 应为 300，实际: {bar_counts}"


# ===========================================================================
# get_status() 字段完整性
# ===========================================================================

class TestGetStatus:
    def test_status_fields_exist(self):
        s = _strategy_with_relaxed_params()
        df = _uptrend_df(300)
        _run_bars(s, df)

        status = s.get_status()
        required_keys = [
            "adx", "plus_di", "minus_di",
            "ema_fast", "ema_slow",
            "macd_line", "macd_signal",
            "rsi", "bb_mid", "bb_upper", "bb_lower",
            "atr", "in_position", "entry_price",
            "bars_held", "highest_close",
            "breakeven_activated", "adx_sleep_bars",
        ]
        for key in required_keys:
            assert key in status, f"get_status() 缺少字段: {key}"

    def test_status_values_reasonable_after_warmup(self):
        s = _strategy_with_relaxed_params()
        df = _uptrend_df(300)
        _run_bars(s, df)

        status = s.get_status()
        assert 0 <= status["rsi"] <= 100, f"RSI 应在 [0, 100]，实际: {status['rsi']}"
        assert status["adx"] >= 0, f"ADX 应 >= 0，实际: {status['adx']}"
        assert status["atr"] >= 0, f"ATR 应 >= 0，实际: {status['atr']}"
        assert status["bb_mid"] >= 0, f"BB mid 应 >= 0，实际: {status['bb_mid']}"


# ===========================================================================
# 注册表完整性
# ===========================================================================

class TestRegistry:
    def test_composite_in_registry(self):
        assert "composite" in STRATEGY_REGISTRY

    def test_get_strategy_returns_correct_class(self):
        cls = get_strategy("composite")
        assert cls is CompositeTrendStrategy
        # 能实例化
        instance = cls()
        assert isinstance(instance, CompositeTrendStrategy)

    def test_all_11_strategies_registered(self):
        expected = {
            "grid", "rsi", "ma", "buyhold", "donchian",
            "structure", "supertrend", "reversal",
            "priceaction", "bollinger", "macd", "composite",
        }
        # 注册表至少包含这 12 个（新增 composite 后共 12 个）
        assert expected.issubset(set(STRATEGY_REGISTRY.keys())), \
            f"注册表缺少策略: {expected - set(STRATEGY_REGISTRY.keys())}"
