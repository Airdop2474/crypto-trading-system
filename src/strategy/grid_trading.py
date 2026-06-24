"""
网格交易策略

在价格区间内设置网格，低买高卖，赚取震荡收益。

多仓位模型：价格每下穿一条网格线买入一档（各占 position_per_grid 资金），
每上穿一条网格线卖出对应档位。配合趋势/波动率过滤器和熔断条件，
在不适合的市场环境主动停止交易。
"""

from typing import List, Optional
from collections import deque
from datetime import datetime
import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.strategy.base import Order
from src.utils.logger import logger


# 参数安全范围（来自 STRATEGY_ASSUMPTIONS.md）
GRID_COUNT_MIN, GRID_COUNT_MAX = 5, 30
POSITION_PER_GRID_MIN, POSITION_PER_GRID_MAX = 0.02, 0.15


class GridTradingStrategy(RiskAwareStrategy):
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

    PRICE_RANGE_BUFFER = 0.05  # 网格边界缓冲区 (+/-5%)
    PAUSE_COOLDOWN = 3600  # 数据异常暂停冷却时间（秒），1 小时

    PARAM_SCHEMA = {
        "lower_price": {"type": float, "min": 0},
        "upper_price": {"type": float, "min": 0},
        "grid_count": {"type": int, "min": 5, "max": 30},
        "position_per_grid": {"type": float, "min": 0.02, "max": 0.15},
        "enable_filters": {"type": bool},
    }

    def __init__(
        self,
        lower_price: float,
        upper_price: float,
        grid_count: int = 10,
        position_per_grid: Optional[float] = None,
        enable_filters: bool = True,
        enable_adx_filter: bool = False,
        adx_period: int = 14,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
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
            stop_loss_config: 止损配置（StopLossConfig，可选，网格策略有自身边界保护不使用）
        """
        super().__init__(
            name="GridTrading",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )

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
        self.enable_adx_filter = enable_adx_filter

        # ADX 初始化
        self._init_adx(adx_period)

        # 计算网格间距与网格线
        self.grid_spacing = (upper_price - lower_price) / grid_count
        self.grids = [
            lower_price + i * self.grid_spacing for i in range(grid_count + 1)
        ]

        self._init_grid_state()

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

    def _init_grid_state(self) -> None:
        """初始化/重置网格专属运行状态（熔断状态由 RiskAwareStrategy 管理）"""
        # 每个网格档位是否已持仓
        self.grid_filled = [False] * (self.grid_count + 1)
        # 上一根 K 线价格（用于判断穿越）
        self.last_price: Optional[float] = None
        # 数据异常暂停时间戳（用于自动恢复）
        self._anomaly_paused_at: Optional[pd.Timestamp] = None
        # EMA 增量缓存（避免每根 bar 全量重算 O(n²)）
        self._ema20: Optional[float] = None
        self._ema50: Optional[float] = None
        # ATR 增量缓存（滑动窗口，O(1) per bar）
        self._atr_period = 14
        self._tr_window: Optional[deque] = None  # deque(maxlen=14)
        self._tr_sum: float = 0.0
        self._prev_close_atr: Optional[float] = None

    def _check_boundary_breach(self, current_price: float) -> tuple:
        """检查价格是否突破网格边界。

        参数：
            current_price: 当前价格

        返回：
            ("CONTINUE", None)     — 正常范围内
            ("PAUSE", reason)      — 突破上沿 5%，暂停交易
            ("LIQUIDATE", reason)  — 突破下沿 5%，建议清仓
        """
        if current_price > self.upper_price * (1 + self.PRICE_RANGE_BUFFER):
            return ("PAUSE", f"价格突破网格上沿{self.PRICE_RANGE_BUFFER:.0%}，暂停交易")
        if current_price < self.lower_price * (1 - self.PRICE_RANGE_BUFFER):
            return ("LIQUIDATE", f"价格突破网格下沿{self.PRICE_RANGE_BUFFER:.0%}，建议清仓")
        return ("CONTINUE", None)

    def on_bar(self, data: pd.DataFrame, current_time: datetime):
        """
        处理每根 K 线，返回订单列表（可能为空）

        决策顺序：
        1. _is_paused() 熔断 → 停止交易
        2. _check_boundary_breach() 边界检测 → PAUSE/LIQUIDATE
        3. NO_TRADE 过滤（价格越界/趋势/波动率/数据异常）→ 本根不交易
        4. 网格穿越 → 生成多档买卖订单
        """
        if len(data) < 2:
            self.last_price = data.iloc[-1]["close"] if len(data) else None
            return []

        current_price = data.iloc[-1]["close"]

        # ADX 增量更新（所有 bar）
        bar = data.iloc[-1]
        self._update_adx(float(bar["high"]), float(bar["low"]), float(bar["close"]))

        # --- 熔断暂停检查 ---
        if self._is_paused(current_time):
            self._try_recover(data)
            if self._is_paused(current_time):
                return []

        # --- ADX 趋势过滤（网格只在震荡市交易）---
        if self.enable_adx_filter and self._is_trending():
            self._reset_no_trade_counter()
            self._update_ema(current_price)
            return []

        # --- 网格边界击穿检测 ---
        breach_status, breach_reason = self._check_boundary_breach(current_price)
        if breach_status == "PAUSE":
            logger.warning(breach_reason)
            self._paused = True
            self.last_price = current_price
            return []
        elif breach_status == "LIQUIDATE":
            logger.warning(breach_reason)
            # 生成清仓订单：卖出所有已持仓的网格档位
            liquidate_orders = []
            for i, filled in enumerate(self.grid_filled):
                if filled:
                    liquidate_orders.append(Order(side="SELL", tag=i))
                    self.grid_filled[i] = False
            self._paused = True
            self.last_price = current_price
            return liquidate_orders if liquidate_orders else []

        # 数据异常（PAUSE）：最近窗口存在 NaN，记录时间戳以便自动恢复
        if self._has_data_anomaly(data):
            logger.warning("Data anomaly detected, pausing")
            self._paused = True
            self._anomaly_paused_at = data["timestamp"].iloc[-1]
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
            atr_pct = self._update_atr_pct(data)

            # 3. 波动率过高
            if atr_pct > 0.05:
                return f"volatility too high ({atr_pct:.2%})"

            # 4. 波动率过低
            if atr_pct < 0.005:
                return f"volatility too low ({atr_pct:.2%})"

            # 5. 趋势过强（非横盘）
            trend = self._trend(data)
            if trend != "sideways":
                return f"strong trend ({trend})"

        return None

    def _update_atr_pct(self, data: pd.DataFrame) -> float:
        """ATR(self._atr_period) 波动率百分比，增量更新 O(1) per bar。

        True Range = max(H-L, |H-prevC|, |L-prevC|)
        ATR = SMA(TR, period)，用 deque(maxlen=period) + running sum 维护
        atr_pct = ATR / current_close

        与原全量 numpy 版逐位一致（已验证，容差 1e-12，含 warmup 阶段）。
        首次调用用 data 的前一根 close 初始化 prev_close，保证首根即产出 TR。

        注意：增量状态在 _no_trade_reason 中随每根 bar 推进；PAUSE 熔断期间
        on_bar 提前 return 不更新窗口——与 _update_ema 同位置，假设 PAUSE 后
        不再恢复交易（当前熔断设计为单向，成立）。
        """
        period = self._atr_period
        high = float(data["high"].iloc[-1])
        low = float(data["low"].iloc[-1])
        close = float(data["close"].iloc[-1])

        # 首次调用：用 data 的前一根 close 初始化 prev（on_bar 保证 len>=2，
        # 故 iloc[-2] 存在），并立即产出当前 bar 的 TR——与全量版首根
        # （len==2 时已有 1 个 TR）逐位对齐，不占位返回 0。
        if self._prev_close_atr is None:
            if len(data) >= 2:
                self._prev_close_atr = float(data["close"].iloc[-2])
            else:
                self._prev_close_atr = close
                return 0.0

        tr = max(high - low, abs(high - self._prev_close_atr),
                 abs(low - self._prev_close_atr))
        self._prev_close_atr = close

        # 滑动窗口：满了先扣最旧元素再追加，running sum 始终 == sum(window)
        if self._tr_window is None:
            self._tr_window = deque(maxlen=period)
        if len(self._tr_window) == self._tr_window.maxlen:
            self._tr_sum -= self._tr_window[0]
        self._tr_window.append(tr)
        self._tr_sum += tr

        atr = self._tr_sum / len(self._tr_window)
        if close <= 0:
            return 0.0
        return atr / close

    def _update_ema(self, price: float) -> None:
        """增量更新 EMA20/EMA50，O(1) 而非 O(n)。
        仅在缓存已初始化后调用（_trend 负责初始化）。
        """
        alpha20 = 2.0 / 21.0
        alpha50 = 2.0 / 51.0
        self._ema20 = alpha20 * price + (1 - alpha20) * self._ema20
        self._ema50 = alpha50 * price + (1 - alpha50) * self._ema50

    def _trend(self, data: pd.DataFrame) -> str:
        """EMA20/EMA50 趋势过滤，返回 uptrend/downtrend/sideways

        使用增量缓存：前 49 根返回 sideways（数据不足），第 50 根起
        用全量 ewm 初始化，此后每根 O(1) 更新。回测 N 根 bar 总复杂度 O(n)。
        """
        price = data.iloc[-1]["close"]

        # 增量更新（仅当缓存已初始化时）
        if self._ema20 is not None:
            self._update_ema(price)
        elif len(data) >= 50:
            # 首次达到 50 根：全量初始化 EMA 缓存
            close = data["close"]
            ema_series_20 = close.ewm(span=20, adjust=False).mean()
            ema_series_50 = close.ewm(span=50, adjust=False).mean()
            self._ema20 = float(ema_series_20.iloc[-1])
            self._ema50 = float(ema_series_50.iloc[-1])
        else:
            return "sideways"

        if self._ema20 is None or self._ema50 is None:
            return "sideways"

        if price > self._ema20 * 1.05 and self._ema20 > self._ema50:
            return "uptrend"
        if price < self._ema20 * 0.95 and self._ema20 < self._ema50:
            return "downtrend"
        return "sideways"

    def _try_recover(self, data: pd.DataFrame) -> bool:
        """尝试从数据异常暂停中恢复。

        在冷却时间过后检查数据质量是否改善，若改善则自动恢复。

        返回：
            True: 已成功恢复
            False: 仍需暂停
        """
        if self._anomaly_paused_at is None:
            return False

        current_time = data["timestamp"].iloc[-1]
        elapsed = (current_time - self._anomaly_paused_at).total_seconds()

        if elapsed >= self.PAUSE_COOLDOWN:
            if not self._has_data_anomaly(data):
                logger.info(
                    f"Data quality recovered after {elapsed:.0f}s, resuming strategy"
                )
                self._paused = False
                self._anomaly_paused_at = None
                return True

        return False

    @staticmethod
    def _has_data_anomaly(data: pd.DataFrame, window: int = 5) -> bool:
        """最近 window 根 K 线是否存在 NaN"""
        recent = data.iloc[-window:][["open", "high", "low", "close"]]
        return bool(recent.isnull().values.any())

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
        self._init_grid_state()
        logger.debug("GridTrading strategy reset")

    def get_grid_status(self) -> dict:
        """获取网格状态（用于监控和调试）"""
        return {
            "grids": self.grids,
            "grid_filled": self.grid_filled,
            "last_price": self.last_price,
            "paused": self._paused,
            "consecutive_losses": self._consecutive_losses,
        }


# 导出
__all__ = ["GridTradingStrategy"]
