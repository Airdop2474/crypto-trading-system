"""策略注册表

集中管理所有策略的注册与查找，消除硬编码的 import + dict 映射。
"""

from src.strategy.base import Strategy

# Hardcoded imports for clarity — fall back to dynamic discovery on ImportError
try:
    from src.strategy.grid_trading import GridTradingStrategy
    from src.strategy.rsi_momentum import RSIMomentumStrategy
    from src.strategy.simple_ma import SimpleMAStrategy
    from src.strategy.buy_and_hold import BuyAndHoldStrategy
    from src.strategy.donchian_channel import DonchianChannelStrategy
    from src.strategy.market_structure import MarketStructureStrategy
    from src.strategy.super_trend import SuperTrendStrategy
    from src.strategy.key_level_reversal import KeyLevelReversalStrategy
    from src.strategy.price_action import PriceActionStrategy
    from src.strategy.bollinger_bands import BollingerBandsStrategy
    from src.strategy.macd import MACDStrategy
    from src.strategy.composite_trend import CompositeTrendStrategy
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
except ImportError:
    import importlib
    import inspect
    import pkgutil
    import src.strategy as pkg

    _loaded = {}
    for _, name, _ in pkgutil.iter_modules(pkg.__path__):
        mod = importlib.import_module(f"src.strategy.{name}")
        for _obj_name in dir(mod):
            obj = getattr(mod, _obj_name)
            if (
                inspect.isclass(obj)
                and issubclass(obj, Strategy)
                and obj is not Strategy
            ):
                _loaded[name] = obj

    GridTradingStrategy = _loaded.get("grid_trading")
    RSIMomentumStrategy = _loaded.get("rsi_momentum")
    SimpleMAStrategy = _loaded.get("simple_ma")
    BuyAndHoldStrategy = _loaded.get("buy_and_hold")
    DonchianChannelStrategy = _loaded.get("donchian_channel")
    MarketStructureStrategy = _loaded.get("market_structure")
    SuperTrendStrategy = _loaded.get("super_trend")
    KeyLevelReversalStrategy = _loaded.get("key_level_reversal")
    PriceActionStrategy = _loaded.get("price_action")
    BollingerBandsStrategy = _loaded.get("bollinger_bands")
    MACDStrategy = _loaded.get("macd")
    CompositeTrendStrategy = _loaded.get("composite_trend")
    MultiLevelBreakoutStrategy = _loaded.get("multi_level_breakout")
    SustainedSqueezeBreakoutStrategy = _loaded.get("sustained_squeeze_breakout")
    StrongCloseMomentumStrategy = _loaded.get("strong_close_momentum")
    PureKeyLevelReversalStrategy = _loaded.get("pure_key_level_reversal")
    ConfluenceVotingStrategy = _loaded.get("confluence_voting")
    CloseBreakoutStrategy = _loaded.get("close_breakout")
    ThreeSoldiersStrategy = _loaded.get("three_soldiers")
    BigBarStrategy = _loaded.get("big_bar")
    PinWithSmallBodyStrategy = _loaded.get("pin_small_body")
    MorningStarStrategy = _loaded.get("morning_star")
    PullbackBreakoutStrategy = _loaded.get("pullback_breakout")
    AmplitudeBreakoutStrategy = _loaded.get("amplitude_breakout")
    WickSweepStrategy = _loaded.get("wick_sweep")
    ConsecutiveFakeoutStrategy = _loaded.get("consecutive_fakeout")
    ConsecutiveMomentumStrategy = _loaded.get("consecutive_momentum")
    AcceleratingMomentumStrategy = _loaded.get("accelerating_momentum")
    BullEngulfingSequenceStrategy = _loaded.get("bull_engulfing_sequence")
    ShortLongSqueezeStrategy = _loaded.get("short_long_squeeze")
    InsideChainBreakoutStrategy = _loaded.get("inside_chain_breakout")
    QualitySqueezeBreakoutStrategy = _loaded.get("quality_squeeze_breakout")
    DecayKeyLevelStrategy = _loaded.get("decay_key_level")
    MultiWindowKeyLevelStrategy = _loaded.get("multi_window_key_level")
    WeightedVotingStrategy = _loaded.get("weighted_voting")
    RequiredCategoriesStrategy = _loaded.get("required_categories")
    MasterSlaveStrategy = _loaded.get("master_slave")
    SessionFilterStrategy = _loaded.get("session_filter")
    DayOfWeekStrategy = _loaded.get("day_of_week")
    MonthPositionStrategy = _loaded.get("month_position")
    CloseMonotonicStrategy = _loaded.get("close_monotonic")
    HighLowExpansionStrategy = _loaded.get("high_low_expansion")
    CloseDistributionStrategy = _loaded.get("close_distribution")
    MultiTimeframeConfluenceStrategy = _loaded.get("multi_timeframe_confluence")
    DualBreakoutStrategy = _loaded.get("dual_breakout")
    TimeframeDivergenceStrategy = _loaded.get("timeframe_divergence")
    VolumeBreakoutStrategy = _loaded.get("volume_breakout")
    VolumePriceDivergenceStrategy = _loaded.get("volume_price_divergence")
    TakerBuyRatioStrategy = _loaded.get("taker_buy_ratio")

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "grid":       GridTradingStrategy,
    "rsi":        RSIMomentumStrategy,
    "ma":         SimpleMAStrategy,
    "buyhold":    BuyAndHoldStrategy,
    "donchian":   DonchianChannelStrategy,
    "structure":  MarketStructureStrategy,
    "supertrend": SuperTrendStrategy,
    "reversal":   KeyLevelReversalStrategy,
    "priceaction": PriceActionStrategy,
    "bollinger":  BollingerBandsStrategy,
    "macd":       MACDStrategy,
    "composite":  CompositeTrendStrategy,
    "multilevel": MultiLevelBreakoutStrategy,
    "squeeze":    SustainedSqueezeBreakoutStrategy,
    "strongmom":  StrongCloseMomentumStrategy,
    "purekeylvl": PureKeyLevelReversalStrategy,
    "confluence": ConfluenceVotingStrategy,
    "closebreak": CloseBreakoutStrategy,
    "threesoldiers":    ThreeSoldiersStrategy,
    "bigbar":           BigBarStrategy,
    "pinsmall":         PinWithSmallBodyStrategy,
    "morningstar":      MorningStarStrategy,
    "pullback":         PullbackBreakoutStrategy,
    "ampbreak":         AmplitudeBreakoutStrategy,
    "wicksweep":        WickSweepStrategy,
    "confakeout":       ConsecutiveFakeoutStrategy,
    "consmomentum":     ConsecutiveMomentumStrategy,
    "accmomentum":      AcceleratingMomentumStrategy,
    "bullengulfseq":    BullEngulfingSequenceStrategy,
    "shortlongsqz":    ShortLongSqueezeStrategy,
    "insidechain":      InsideChainBreakoutStrategy,
    "qualitysqz":       QualitySqueezeBreakoutStrategy,
    "decaykey":         DecayKeyLevelStrategy,
    "multiwinkey":      MultiWindowKeyLevelStrategy,
    "weightedvote":      WeightedVotingStrategy,
    "requiredcat":      RequiredCategoriesStrategy,
    "masterslave":      MasterSlaveStrategy,
    "sessionfilter":    SessionFilterStrategy,
    "dayofweek":        DayOfWeekStrategy,
    "monthpos":         MonthPositionStrategy,
    "closemonotonic":   CloseMonotonicStrategy,
    "hlexpansion":      HighLowExpansionStrategy,
    "closedist":       CloseDistributionStrategy,
    "mtfconfluence":    MultiTimeframeConfluenceStrategy,
    "dualbreakout":     DualBreakoutStrategy,
    "tfdivergence":     TimeframeDivergenceStrategy,
    "volbreakout":      VolumeBreakoutStrategy,
    "volpricediv":      VolumePriceDivergenceStrategy,
    "takerbuyratio":    TakerBuyRatioStrategy,
}


def get_strategy(name: str) -> type[Strategy]:
    """根据名称查找策略类。

    参数：
        name: 策略名称（"grid" / "rsi" / "ma" / "buyhold"）

    返回：
        对应的策略类

    异常：
        ValueError: 未知策略名称
    """
    if name not in STRATEGY_REGISTRY:
        raise ValueError(
            f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY)}"
        )
    return STRATEGY_REGISTRY[name]


def list_strategies() -> list[str]:
    """列出所有已注册策略的名称。

    返回：
        策略名称列表
    """
    return list(STRATEGY_REGISTRY.keys())


# 策略中文标签（供 API 层展示用，与前端 lib/strategy-meta.ts 保持一致）
_STRATEGY_LABELS = {
    "grid": "网格",
    "rsi": "RSI 动量",
    "ma": "均线",
    "buyhold": "买入持有",
    "donchian": "唐奇安通道",
    "structure": "市场结构",
    "supertrend": "超级趋势",
    "reversal": "关键位反转",
    "priceaction": "价格行为学",
    "bollinger": "布林带均值回归",
    "macd": "MACD 趋势跟踪",
    "composite": "复合趋势",
    "multilevel": "多级突破",
    "squeeze": "持续收缩突破",
    "strongmom": "强势收盘动量",
    "purekeylvl": "纯关键位反转",
    "confluence": "多信号共振",
    "closebreak": "收盘突破",
    "threesoldiers": "三兵",
    "bigbar": "大实体",
    "pinsmall": "Pin小实体",
    "morningstar": "晨星",
    "pullback": "回踩突破",
    "ampbreak": "幅度突破",
    "wicksweep": "影线扫损",
    "confakeout": "连续假突",
    "consmomentum": "连续动量",
    "accmomentum": "递增动量",
    "bullengulfseq": "阳包阴序列",
    "shortlongsqz": "短长期收缩",
    "insidechain": "内含线链",
    "qualitysqz": "质量突破",
    "decaykey": "降权关键位",
    "multiwinkey": "多窗口关键位",
    "weightedvote": "加权投票",
    "requiredcat": "必含项",
    "masterslave": "主从",
    "sessionfilter": "时段过滤",
    "dayofweek": "周内效应",
    "monthpos": "月内位置",
    "closemonotonic": "收盘单调",
    "hlexpansion": "高低点扩散",
    "closedist": "收盘分布",
    "mtfconfluence": "多周期共振",
    "dualbreakout": "双窗口突破",
    "tfdivergence": "周期背离",
    "volbreakout": "放量突破",
    "volpricediv": "量价背离",
    "takerbuyratio": "主动买盘比",
}


def get_strategy_label(strategy_id: str) -> str:
    """从 strategy_id（如 'grid-btc-usdt'）解析出中文标签。

    参数：
        strategy_id: 策略 ID，形如 `<type>-<symbol>-usdt`

    返回：
        中文标签；未知类型返回 strategy_id 原值
    """
    head = strategy_id.split("-")[0]
    return _STRATEGY_LABELS.get(head, strategy_id)


__all__ = [
    "STRATEGY_REGISTRY",
    "get_strategy",
    "list_strategies",
    "get_strategy_label",
]
