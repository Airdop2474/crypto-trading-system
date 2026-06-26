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
from src.strategy.multi_level_breakout import MultiLevelBreakoutStrategy
from src.strategy.sustained_squeeze_breakout import SustainedSqueezeBreakoutStrategy
from src.strategy.strong_close_momentum import StrongCloseMomentumStrategy
from src.strategy.pure_key_level_reversal import PureKeyLevelReversalStrategy
from src.strategy.confluence_voting import ConfluenceVotingStrategy
from src.strategy.close_breakout import CloseBreakoutStrategy
from src.strategy.three_soldiers import ThreeSoldiersStrategy
from src.strategy.big_bar import BigBarStrategy
from src.strategy.pin_small_body import PinWithSmallBodyStrategy
from src.strategy.morning_star import MorningStarStrategy
from src.strategy.pullback_breakout import PullbackBreakoutStrategy
from src.strategy.amplitude_breakout import AmplitudeBreakoutStrategy
from src.strategy.wick_sweep import WickSweepStrategy
from src.strategy.consecutive_fakeout import ConsecutiveFakeoutStrategy
from src.strategy.consecutive_momentum import ConsecutiveMomentumStrategy
from src.strategy.accelerating_momentum import AcceleratingMomentumStrategy
from src.strategy.bull_engulfing_sequence import BullEngulfingSequenceStrategy
from src.strategy.short_long_squeeze import ShortLongSqueezeStrategy
from src.strategy.inside_chain_breakout import InsideChainBreakoutStrategy
from src.strategy.quality_squeeze_breakout import QualitySqueezeBreakoutStrategy
from src.strategy.decay_key_level import DecayKeyLevelStrategy
from src.strategy.multi_window_key_level import MultiWindowKeyLevelStrategy
from src.strategy.weighted_voting import WeightedVotingStrategy
from src.strategy.required_categories import RequiredCategoriesStrategy
from src.strategy.master_slave import MasterSlaveStrategy
from src.strategy.session_filter import SessionFilterStrategy
from src.strategy.day_of_week import DayOfWeekStrategy
from src.strategy.month_position import MonthPositionStrategy
from src.strategy.close_monotonic import CloseMonotonicStrategy
from src.strategy.high_low_expansion import HighLowExpansionStrategy
from src.strategy.close_distribution import CloseDistributionStrategy
from src.strategy.multi_timeframe_confluence import MultiTimeframeConfluenceStrategy
from src.strategy.dual_breakout import DualBreakoutStrategy
from src.strategy.timeframe_divergence import TimeframeDivergenceStrategy
from src.strategy.volume_breakout import VolumeBreakoutStrategy
from src.strategy.volume_price_divergence import VolumePriceDivergenceStrategy
from src.strategy.taker_buy_ratio import TakerBuyRatioStrategy
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
    "MultiLevelBreakoutStrategy",
    "SustainedSqueezeBreakoutStrategy",
    "StrongCloseMomentumStrategy",
    "PureKeyLevelReversalStrategy",
    "ConfluenceVotingStrategy",
    "CloseBreakoutStrategy",
    "ThreeSoldiersStrategy",
    "BigBarStrategy",
    "PinWithSmallBodyStrategy",
    "MorningStarStrategy",
    "PullbackBreakoutStrategy",
    "AmplitudeBreakoutStrategy",
    "WickSweepStrategy",
    "ConsecutiveFakeoutStrategy",
    "ConsecutiveMomentumStrategy",
    "AcceleratingMomentumStrategy",
    "BullEngulfingSequenceStrategy",
    "ShortLongSqueezeStrategy",
    "InsideChainBreakoutStrategy",
    "QualitySqueezeBreakoutStrategy",
    "DecayKeyLevelStrategy",
    "MultiWindowKeyLevelStrategy",
    "WeightedVotingStrategy",
    "RequiredCategoriesStrategy",
    "MasterSlaveStrategy",
    "SessionFilterStrategy",
    "DayOfWeekStrategy",
    "MonthPositionStrategy",
    "CloseMonotonicStrategy",
    "HighLowExpansionStrategy",
    "CloseDistributionStrategy",
    "MultiTimeframeConfluenceStrategy",
    "DualBreakoutStrategy",
    "TimeframeDivergenceStrategy",
    "VolumeBreakoutStrategy",
    "VolumePriceDivergenceStrategy",
    "TakerBuyRatioStrategy",
    "RiskAwareStrategy",
    "CircuitBreaker",
    "STRATEGY_REGISTRY",
    "get_strategy",
    "list_strategies",
]
