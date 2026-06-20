"""统一交易工具函数

滑点计算和手续费计算的统一入口，消除 BacktestEngine 和 PaperBroker 中的重复实现。
"""


def apply_slippage(price: float, slippage_pct: float, side: str) -> float:
    """统一滑点计算。

    参数：
        price: 基准价格
        slippage_pct: 滑点比率（小数，如 0.0005 表示 0.05%）
        side: 交易方向，'buy' 或 'sell'

    返回：
        施加滑点后的实际成交价。
        - buy:  价格上浮（成交价更高）
        - sell: 价格下浮（成交价更低）
    """
    side_lower = side.lower()
    if side_lower not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got '{side}'")
    direction = 1 if side_lower == "buy" else -1
    return price * (1 + direction * slippage_pct)


def apply_commission(capital: float, rate: float) -> float:
    """统一手续费计算。

    参数：
        capital: 交易金额
        rate: 手续费率（小数，如 0.001 表示 0.1%）

    返回：
        扣除手续费后的可用金额。
    """
    return capital * (1 - rate)


__all__ = ["apply_slippage", "apply_commission"]
