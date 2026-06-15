"""
网格交易策略

在价格区间内设置网格，低买高卖，赚取震荡收益。

多仓位模型：价格每下穿一条网格线买入一档（各占 position_per_grid 资金），
每上穿一条网格线卖出对应档位。配合趋势/波动率过滤器和熔断条件，
在不适合的市场环境主动停止交易。
"""

from typing import List, Optional
from datetime import datetime
import pandas as pd

from src.strategy.base import Strategy, Order
from src.utils.logger import logger


# 参数安全范围（来自 STRATEGY_ASSUMPTIONS.md）
GRID_COUNT_MIN, GRID_COUNT_MAX = 5, 30
POSITION_PER_GRID_MIN, POSITION_PER_GRID_MAX = 0.02, 0.15


class GridTradingStrategy(Strategy):
    """
    网格交易策略（多仓位）

    原理：
    1. 在价格区间内设置多个网格线
    2. 价格下穿网格线时买入一档
    3. 价格上穿网格线时卖出该档
    4. 适合震荡市场

    适用环境：横盘震荡、波动率适中、流动性好。
    不适用环境（主动 NO_TRADE / PAUSE）见 on_bar 与过滤器。
    """

    def __init__(
        self,
        lower_price: float,
        upper_price: float,
        grid_count: int = 10,
        position_per_grid: Optional[float] = None,
        enable_filters: bool = True,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        """
        初始化网格策略

        参数：
            lower_price: 价格下界
            upper_price: 价格上界
            grid_count: 网格数量（安全范围 5-30）
            position_per_grid: 每档占初始资金比例（默认 1/grid_count，安全范围 2%-15%）
            enable_filters: 是否启用趋势/波动率过滤器
            max_consecutive_losses: 连亏熔断阈值
            max_daily_loss: 当日亏损熔断阈值（占初始资金比例）
            initial_capital: 初始资金（用于当日亏损熔断的资金基准，应与引擎一致）
        """
        super().__init__(name="GridTrading")

        if lower_price >= upper_price:
            raise ValueError("lower_price must be less than upper_price")

        if not (GRID_COUNT_MIN <= grid_count <= GRID_COUNT_MAX):
            raise ValueError(
                f"grid_count must be in [{GRID_COUNT_MIN}, {GRID_COUNT_MAX}], "
                f"got {grid_count}"
            )

        # 默认每档均分资金，但不超过单档安全上限
        if position_per_grid is None:
            position_per_grid = min(1.0 / grid_count, POSITION_PER_GRID_MAX)

        if not (POSITION_PER_GRID_MIN <= position_per_grid <= POSITION_PER_GRID_MAX):
            raise ValueError(
                f"position_per_grid must be in "
                f"[{POSITION_PER_GRID_MIN}, {POSITION_PER_GRID_MAX}], "
                f"got {position_per_grid:.4f}"
            )

        self.lower_price = lower_price
        self.upper_price = upper_price
        self.grid_count = grid_count
        self.position_per_grid = position_per_grid
        self.enable_filters = enable_filters
        self.max_consecutive_losses = max_consecutive_losses
        self.max_daily_loss = max_daily_loss
        self.initial_capital = initial_capital

        # 计算网格间距与网格线
        self.grid_spacing = (upper_price - lower_price) / grid_count
        self.grids = [
            lower_price + i * self.grid_spacing for i in range(grid_count + 1)
        ]

        self._init_state()

        self.set_parameters(
            lower_price=lower_price,
            upper_price=upper_price,
            grid_count=grid_count,
            position_per_grid=position_per_grid,
        )

        logger.info(
            f"GridTrading initialized: "
            f"range=[{lower_price:.2f}, {upper_price:.2f}], "
            f"grids={grid_count}, spacing={self.grid_spacing:.2f}, "
            f"pos/grid={position_per_grid:.2%}"
        )

    def _init_state(self) -> None:
        """初始化/重置运行状态"""
        # 每个网格档位是否已持仓
        self.grid_filled = [False] * (self.grid_count + 1)
        # 上一根 K 线价格（用于判断穿越）
        self.last_price: Optional[float] = None
        # 熔断状态
        self.consecutive_losses = 0
        self.paused = False
        self.current_day = None
        self.daily_pnl = 0.0

    # PLACEHOLDER_ONBAR

    def on_bar(self, data: pd.DataFrame, current_time: datetime):
        """
        处理每根 K 线，返回订单列表（可能为空）

        决策顺序：
        1. PAUSE 熔断（连亏/当日亏损）→ 停止交易
        2. NO_TRADE 过滤（价格越界/趋势/波动率/数据异常）→ 本根不交易
        3. 网格穿越 → 生成多档买卖订单
        """
        if len(data) < 2:
            self.last_price = data.iloc[-1]["close"] if len(data) else None
            return []

        current_price = data.iloc[-1]["close"]

        # --- PAUSE 熔断：触发后不再交易 ---
        if self.paused:
            return []

        # 数据异常（PAUSE）：最近窗口存在 NaN
        if self._has_data_anomaly(data):
            logger.warning("Data anomaly detected, pausing")
            self.paused = True
            return []

        # --- NO_TRADE 过滤：条件恢复后自动继续 ---
        no_trade = self._no_trade_reason(data, current_price)
        if no_trade:
            logger.debug(f"NO_TRADE: {no_trade}")
            self.last_price = current_price
            return []

        # 第一根有效 K 线，仅记录价格
        if self.last_price is None:
            self.last_price = current_price
            return []

        orders = self._grid_orders(current_price)

        self.last_price = current_price
        return orders

    def _grid_orders(self, current_price: float) -> List[Order]:
        """根据价格穿越网格线生成多档买卖订单"""
        current_idx = self._find_grid_index(current_price)
        last_idx = self._find_grid_index(self.last_price)
        orders: List[Order] = []

        if current_idx < last_idx:
            # 价格下跌，下穿网格线 → 逐档买入未持仓的网格
            for i in range(last_idx, current_idx, -1):
                if not self.grid_filled[i]:
                    self.grid_filled[i] = True
                    orders.append(
                        Order(side="BUY", tag=i, fraction=self.position_per_grid)
                    )
        elif current_idx > last_idx:
            # 价格上涨，上穿网格线 → 逐档卖出已持仓的网格
            for i in range(last_idx + 1, current_idx + 1):
                if self.grid_filled[i]:
                    self.grid_filled[i] = False
                    orders.append(Order(side="SELL", tag=i))

        return orders

    def _no_trade_reason(
        self, data: pd.DataFrame, current_price: float
    ) -> Optional[str]:
        """返回 NO_TRADE 原因，None 表示允许交易（5 个条件）"""
        # 1. 单边上涨：突破上界 20%
        if current_price > self.upper_price * 1.2:
            return "price > upper * 1.2 (uptrend breakout)"

        # 2. 单边下跌：跌破下界 15%
        if current_price < self.lower_price * 0.85:
            return "price < lower * 0.85 (downtrend breakout)"

        if self.enable_filters:
            daily_range = self._daily_range(data)

            # 3. 波动率过高
            if daily_range > 0.05:
                return f"volatility too high ({daily_range:.2%})"

            # 4. 波动率过低
            if daily_range < 0.005:
                return f"volatility too low ({daily_range:.2%})"

            # 5. 趋势过强（非横盘）
            trend = self._trend(data)
            if trend != "sideways":
                return f"strong trend ({trend})"

        return None

    @staticmethod
    def _daily_range(data: pd.DataFrame) -> float:
        """最近一根 K 线的振幅 (high-low)/open"""
        row = data.iloc[-1]
        if row["open"] <= 0:
            return 0.0
        return (row["high"] - row["low"]) / row["open"]

    @staticmethod
    def _trend(data: pd.DataFrame) -> str:
        """EMA20/EMA50 趋势过滤，返回 uptrend/downtrend/sideways"""
        if len(data) < 50:
            # 数据不足以判断趋势，视为横盘（不阻止网格）
            return "sideways"

        close = data["close"]
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
        price = close.iloc[-1]

        if price > ema20 * 1.05 and ema20 > ema50:
            return "uptrend"
        if price < ema20 * 0.95 and ema20 < ema50:
            return "downtrend"
        return "sideways"

    @staticmethod
    def _has_data_anomaly(data: pd.DataFrame, window: int = 5) -> bool:
        """最近 window 根 K 线是否存在 NaN"""
        recent = data.iloc[-window:][["open", "high", "low", "close"]]
        return bool(recent.isnull().values.any())

    def on_fill(self, trade: dict) -> None:
        """成交回报：跟踪盈亏，触发连亏/当日亏损熔断"""
        profit = trade.get("profit")
        if profit is None:
            return  # 买入无已实现盈亏，不计入

        # 当日亏损熔断：按成交日重置当日累计盈亏
        trade_day = pd.Timestamp(trade["time"]).date()
        if self.current_day != trade_day:
            self.current_day = trade_day
            self.daily_pnl = 0.0

        self.daily_pnl += profit

        # 连亏计数
        if profit < 0:
            self.consecutive_losses += 1
        elif profit > 0:
            self.consecutive_losses = 0

        if self.consecutive_losses >= self.max_consecutive_losses:
            logger.warning(
                f"PAUSE: {self.consecutive_losses} consecutive losses"
            )
            self.paused = True

        # 当日亏损熔断：当日已实现亏损占初始资金比例 >= 阈值
        if self.daily_pnl < 0 and self.initial_capital > 0:
            loss_ratio = abs(self.daily_pnl) / self.initial_capital
            if loss_ratio >= self.max_daily_loss:
                logger.warning(f"PAUSE: daily loss {loss_ratio:.2%}")
                self.paused = True

    def _find_grid_index(self, price: float) -> int:
        """找到价格所在的网格索引（0 到 grid_count）"""
        if price <= self.lower_price:
            return 0
        if price >= self.upper_price:
            return self.grid_count
        index = int((price - self.lower_price) / self.grid_spacing)
        return min(max(index, 0), self.grid_count)

    def reset(self):
        """重置策略状态"""
        super().reset()
        self._init_state()
        logger.debug("GridTrading strategy reset")

    def get_grid_status(self) -> dict:
        """获取网格状态（用于监控和调试）"""
        return {
            "grids": self.grids,
            "grid_filled": self.grid_filled,
            "last_price": self.last_price,
            "paused": self.paused,
            "consecutive_losses": self.consecutive_losses,
        }


# 导出
__all__ = ["GridTradingStrategy"]
