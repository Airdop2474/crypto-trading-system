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
    "supertrend": "SuperTrend",
    "reversal": "关键位反转",
    "priceaction": "价格行为学",
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
