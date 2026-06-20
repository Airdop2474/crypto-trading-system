"""策略模块：所有交易策略的统一入口。"""

from src.strategy.base import Strategy, Order
from src.strategy.grid_trading import GridTradingStrategy
from src.strategy.rsi_momentum import RSIMomentumStrategy
from src.strategy.simple_ma import SimpleMAStrategy
from src.strategy.buy_and_hold import BuyAndHoldStrategy
from src.strategy.donchian_channel import DonchianChannelStrategy
from src.strategy.market_structure import MarketStructureStrategy
from src.strategy.super_trend import SuperTrendStrategy
from src.strategy.key_level_reversal import KeyLevelReversalStrategy
from src.strategy.risk_aware import RiskAwareStrategy, CircuitBreaker
from src.strategy.registry import (
    STRATEGY_REGISTRY,
    get_strategy,
    list_strategies,
)

__all__ = [
    "Strategy",
    "Order",
    "GridTradingStrategy",
    "RSIMomentumStrategy",
    "SimpleMAStrategy",
    "BuyAndHoldStrategy",
    "DonchianChannelStrategy",
    "MarketStructureStrategy",
    "SuperTrendStrategy",
    "KeyLevelReversalStrategy",
    "RiskAwareStrategy",
    "CircuitBreaker",
    "STRATEGY_REGISTRY",
    "get_strategy",
    "list_strategies",
]
