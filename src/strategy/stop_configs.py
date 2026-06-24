"""
策略止损默认配置

为 12 个策略提供默认的止损参数配置。
趋势策略用 ATR + 移动止损，均值回归策略用区间突破止损。

这些配置可通过 EvolutionEngine 自动优化，但有安全边界约束。
"""

from src.strategy.stop_loss import StopLossConfig


# 趋势策略：ATR + 移动止损
TREND_STOP_CONFIG = StopLossConfig(
    stop_type="atr_trailing",
    atr_mult=1.5,               # 1.5 倍 ATR 固定止损
    trailing_activation=0.03,   # 涨 3% 后激活移动止损
    trailing_drawback=0.03,     # 从最高点回撤 3% 触发
    max_bars=50,                # 50 根 K 线时间止损
    min_stop_pct=0.01,          # 最小止损 1%
)

# 均值回归策略：区间突破止损
RANGE_STOP_CONFIG = StopLossConfig(
    stop_type="range_breakout",
    range_breakout_pct=0.05,    # 突破入场价 5% 触发
    max_bars=50,                # 50 根 K 线时间止损
    min_stop_pct=0.01,
)

# BuyHold：不止损
NONE_STOP_CONFIG = StopLossConfig(
    stop_type="none",
    max_bars=0,
)

# Grid：仅时间止损（已有边界击穿保护）
GRID_STOP_CONFIG = StopLossConfig(
    stop_type="time_only",
    max_bars=100,               # 网格持仓时间更长
)

# Donchian：已有自带追踪止损，仅加时间止损
DONCHIAN_STOP_CONFIG = StopLossConfig(
    stop_type="time_only",
    max_bars=80,
)


# 策略 → 止损配置映射
STRATEGY_STOP_CONFIGS = {
    # 趋势策略
    "rsi": TREND_STOP_CONFIG,
    "ma": TREND_STOP_CONFIG,
    "donchian": DONCHIAN_STOP_CONFIG,
    "structure": TREND_STOP_CONFIG,
    "supertrend": TREND_STOP_CONFIG,
    "macd": TREND_STOP_CONFIG,
    "composite": TREND_STOP_CONFIG,

    # 均值回归策略
    "grid": GRID_STOP_CONFIG,
    "bollinger": RANGE_STOP_CONFIG,
    "reversal": RANGE_STOP_CONFIG,
    "priceaction": RANGE_STOP_CONFIG,

    # 不止损
    "buyhold": NONE_STOP_CONFIG,
}


def get_stop_config(strategy_name: str) -> StopLossConfig:
    """获取策略的默认止损配置

    参数：
        strategy_name: 策略短名（如 "rsi", "grid"）

    返回：
        StopLossConfig 实例
    """
    return STRATEGY_STOP_CONFIGS.get(strategy_name, TREND_STOP_CONFIG)


__all__ = [
    "TREND_STOP_CONFIG",
    "RANGE_STOP_CONFIG",
    "NONE_STOP_CONFIG",
    "GRID_STOP_CONFIG",
    "DONCHIAN_STOP_CONFIG",
    "STRATEGY_STOP_CONFIGS",
    "get_stop_config",
]
