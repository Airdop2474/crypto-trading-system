# 新策略实现方案

**文档版本：** v1.0  
**创建日期：** 2026-06-20  
**状态：** ✅ 待执行  
**依赖：** Phase 1-2 优化已完成，RiskAwareStrategy + STRATEGY_REGISTRY 就位

---

## 概览

| # | 策略 | 类型 | 信号模式 | 行数预估 | 市场环境 |
|---|------|------|----------|----------|----------|
| 1 | Donchian Channel | 趋势突破 | `'BUY'/'SELL'` | ~50 | 趋势 |
| 2 | Market Structure Break | 价格行为 | `'BUY'/'SELL'` | ~60 | 趋势 |
| 3 | SuperTrend | 趋势跟踪 | `'BUY'/'SELL'` | ~65 | 趋势 |
| 4 | Key Level Reversal | 价格行为 | `'BUY'/'SELL'` | ~80 | 震荡/转折 |

全部策略继承 `RiskAwareStrategy`（自带连亏/日亏/回撤熔断），走 `STRATEGY_REGISTRY` 注册。

---

## 策略实现优先级

### 🥇 第1批（本周末）：Donchian + 市场结构突破

**理由：** 网格抓震荡 → 这两个抓趋势，形成完整攻守组合。实现后立即用 `run_multi.py` 跑四策略对比。

### 🥈 第2批（下周）：SuperTrend + 关键位反转

**理由：** SuperTrend 补齐持仓型出场逻辑；关键位反转为价格行为确认层。

---

## 一、Donchian Channel 突破策略

### 1.1 核心逻辑

```
信号规则：
  上轨 = 过去 N 根 bar 最高价 MAX
  下轨 = 过去 N 根 bar 最低价 MIN
  
  if close > 上轨[-1] and not in_position:
      → BUY（突破买入）
  if close < 下轨[-1] and in_position:
      → SELL（跌破卖出）

出场条件：
  - 价格跌破下轨（追踪止损）
  - 熔断触发（继承 RiskAwareStrategy）
```

### 1.2 代码实现

**文件：** `src/strategy/donchian_channel.py`

```python
"""
Donchian Channel 突破策略

Richard Donchian 的经典趋势跟踪策略：价格突破 N 日最高价时买入，
跌破 N 日最低价时卖出。在强趋势市场中表现优异，与网格策略互补。

适用环境：趋势市场（尤其单边行情）。
不适用环境：横盘震荡（频繁假突破）。
"""

from typing import Optional
from datetime import datetime
import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class DonchianChannelStrategy(RiskAwareStrategy):
    """Donchian Channel 突破策略

    逻辑：
    - 上轨 = 过去 period 根 bar 最高价
    - 下轨 = 过去 period 根 bar 最低价
    - close > 上轨 → BUY
    - close < 下轨 → SELL
    - 出场后下轨作为追踪止损参考
    """

    PARAM_SCHEMA = {
        "period":       {"type": int,   "min": 5,  "max": 100, "default": 20},
        "max_consecutive_losses": {"type": int, "min": 1, "default": 3},
        "max_daily_loss": {"type": float, "min": 0, "max": 0.1, "default": 0.02},
    }

    def __init__(
        self,
        period: int = 20,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="DonchianChannel",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )

        if period < 2:
            raise ValueError("period must be >= 2")
        self.period = period

        self._in_position = False
        self._upper: Optional[float] = None
        self._lower: Optional[float] = None

        self.set_parameters(period=period)

        logger.info(f"DonchianChannel initialized: period={period}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._upper = None
        self._lower = None

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.period:
            return None

        if self._is_paused():
            return None

        # 计算通道（用前一根 bar 的 OHLC 避免当前 bar 的前视）
        window = data.iloc[-(self.period + 1):-1]
        self._upper = float(window["high"].max())
        self._lower = float(window["low"].min())

        current_price = float(data["close"].iloc[-1])

        if not self._in_position:
            if current_price > self._upper:
                self._in_position = True
                return "BUY"
        else:
            if current_price < self._lower:
                self._in_position = False
                return "SELL"

        return None
```

### 1.3 注册（`src/strategy/registry.py`）

```python
# 新增 import
from src.strategy.donchian_channel import DonchianChannelStrategy

# STRATEGY_REGISTRY 新增
"donchian": DonchianChannelStrategy,
```

### 1.4 回测命令

```bash
python scripts/run_backtest.py --strategy donchian --period 20
```

### 1.5 测试要点

| 测试场景 | 预期行为 |
|----------|----------|
| 突破上轨 | 产生 BUY 信号 |
| 跌破下轨 | 产生 SELL 信号 |
| 通道内震荡 | 无信号 |
| 连亏 3 笔 | 熔断暂停 |
| 首根 bar period 不足 | 返回 None |

### 1.6 已知局限

- 横盘震荡中假突破频繁（需配合 ADX 趋势过滤，可选增强）
- 出场依赖突破下轨，回吐较大（SuperTrend 可互补）

---

## 二、市场结构突破策略（Price Action）

### 2.1 核心逻辑

```
信号规则：
  持续追踪 swing_high（最近 N 根 bar 最高点）
  持续追踪 swing_low（最近 N 根 bar 最低点）
  
  if close > swing_high and not in_position:
      → BUY（结构突破，趋势确认）
  if close < swing_low and in_position:
      → SELL（结构破坏，趋势逆转）

关键：
  swing_high/lows 不是 rolling max/min — 只在 bar 创新高/新低时更新
  创新高 → swing_high = close，不创新高 → swing_high 保持
  创新低 → swing_low = close，不创新低 → swing_low 保持
```

### 2.2 代码实现

**文件：** `src/strategy/market_structure.py`

```python
"""
市场结构突破策略（Price Action）

基于传统 Wyckoff/Dow 理论的市场结构分析：
持续追踪 swing high / swing low，在结构突破时入场，
在结构破坏时出场。

与网格策略的互补关系：
- 网格适合震荡（区间内反复低买高卖）
- 结构突破适合趋势（突破关键位后吃大段）

适用环境：趋势市场，尤其结构清晰的单边行情。
不适用环境：窄幅横盘（结构不清晰，频繁假突破）。
"""

from typing import Optional
from datetime import datetime
import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class MarketStructureStrategy(RiskAwareStrategy):
    """市场结构突破策略

    逻辑：
    - swing_high: 自上次创新高以来的最高收盘价
    - swing_low:  自上次创新低以来的最低收盘价
    - close > swing_high → BUY（结构向上突破）
    - close < swing_low  → SELL（结构向下破坏）

    风控（继承自 RiskAwareStrategy）：
    - 连亏熔断（默认 3 笔）
    - 当日亏损熔断（默认 2%）
    - 累计回撤熔断（默认 15%）
    """

    PARAM_SCHEMA = {
        "lookback":    {"type": int,   "min": 3,  "max": 50,  "default": 10},
        "max_consecutive_losses": {"type": int, "min": 1, "default": 3},
        "max_daily_loss": {"type": float, "min": 0, "max": 0.1, "default": 0.02},
    }

    def __init__(
        self,
        lookback: int = 10,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="MarketStructure",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )

        if lookback < 3:
            raise ValueError("lookback must be >= 3")
        self.lookback = lookback

        self._in_position = False
        self._swing_high: Optional[float] = None
        self._swing_low: Optional[float] = None

        self.set_parameters(lookback=lookback)

        logger.info(f"MarketStructure initialized: lookback={lookback}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._swing_high = None
        self._swing_low = None

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.lookback:
            return None

        if self._is_paused():
            return None

        close = float(data["close"].iloc[-1])

        # 初始化 swing points
        if self._swing_high is None:
            window = data.iloc[-self.lookback:]
            self._swing_high = float(window["high"].max())
            self._swing_low = float(window["low"].min())

        # 更新 swing points（只在创新高/新低时更新）
        if close > self._swing_high:
            self._swing_high = close
        if close < self._swing_low:
            self._swing_low = close

        if not self._in_position:
            if close > self._swing_high:
                self._in_position = True
                return "BUY"
        else:
            if close < self._swing_low:
                self._in_position = False
                return "SELL"

        return None
```

### 2.3 注册（`src/strategy/registry.py`）

```python
from src.strategy.market_structure import MarketStructureStrategy

"structure": MarketStructureStrategy,  # 新增
```

### 2.4 回测命令

```bash
python scripts/run_backtest.py --strategy structure --lookback 10
```

### 2.5 测试要点

| 场景 | 预期 |
|------|------|
| 创新高（突破 swing_high） | BUY |
| 创新低（跌破 swing_low） | SELL |
| swing_high/lows 不更新时 | 维持原方向 |
| 连续创新高后横盘再创新低 | BUY → 持有 → SELL |

### 2.6 已知局限

- 窄幅横盘时假突破频繁
- lookback 参数敏感（太小→噪声，太大→滞后）

---

## 三、SuperTrend 策略

### 3.1 核心逻辑

```
ATR × multiplier = 波动带宽度
上轨 = (high + low) / 2 + ATR × multiplier
下轨 = (high + low) / 2 - ATR × multiplier

SuperTrend 方向：
  close > 上轨 → 趋势向上 → BUY
  close < 下轨 → 趋势向下 → SELL
  
关键：SuperTrend 线是单向的──
  上升趋势中只走下轨（动态支撑），不走上轨
  下降趋势中只走上轨（动态阻力），不走下轨
  趋势反转时：close 跌破上升趋势的支撑线 → 转为下降
```

### 3.2 代码实现

**文件：** `src/strategy/super_trend.py`

```python
"""
SuperTrend 策略

基于 ATR 的动态趋势跟踪指标。相比 Donchian Channel 和双均线，
SuperTrend 自带波动率调整，在高波动时放宽止损、低波动时收紧止损，
对假突破的过滤更好。

核心优势：出场逻辑内建（SuperTrend 线反向信号即出场），
不依赖固定回看窗口（由 ATR 自适应）。

适用环境：趋势市场。
不适用环境：横盘震荡（频繁翻转）。
"""

from typing import Optional
from datetime import datetime
import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class SuperTrendStrategy(RiskAwareStrategy):
    """SuperTrend 策略

    逻辑：
    - 计算 ATR(period)
    - 上轨 = hl2 + multiplier × ATR
    - 下轨 = hl2 - multiplier × ATR
    - SuperTrend 方向翻转 → 入场/出场

    优势：出场逻辑内建，止损由波动率自适应。
    """

    PARAM_SCHEMA = {
        "period":     {"type": int,   "min": 2,  "max": 50,  "default": 10},
        "multiplier": {"type": float, "min": 0.5, "max": 5.0, "default": 3.0},
        "max_consecutive_losses": {"type": int, "min": 1, "default": 3},
        "max_daily_loss": {"type": float, "min": 0, "max": 0.1, "default": 0.02},
    }

    def __init__(
        self,
        period: int = 10,
        multiplier: float = 3.0,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="SuperTrend",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )

        if period < 2:
            raise ValueError("period must be >= 2")
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        self.period = period
        self.multiplier = multiplier

        self._in_position = False
        self._trend_up: Optional[bool] = None  # True=上升趋势，False=下降趋势
        self._atr: Optional[float] = None        # 当前 ATR 值

        self.set_parameters(period=period, multiplier=multiplier)

        logger.info(
            f"SuperTrend initialized: period={period}, multiplier={multiplier}"
        )

    def reset(self):
        super().reset()
        self._in_position = False
        self._trend_up = None
        self._atr = None

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.period + 1:
            return None

        if self._is_paused():
            return None

        close = data["close"]
        high = data["high"]
        low = data["low"]
        current_close = float(close.iloc[-1])

        # 计算 ATR（全量，简单正确的实现；后续可替换为增量）
        atr = self._calc_atr(high, low, close, self.period)
        hl2 = (float(high.iloc[-1]) + float(low.iloc[-1])) / 2.0

        upper_band = hl2 + self.multiplier * atr
        lower_band = hl2 - self.multiplier * atr

        # 判断 SuperTrend 方向
        # 初值：当前价在上半区 → 上升趋势
        if self._trend_up is None:
            self._trend_up = current_close > lower_band

        # SuperTrend 方向更新（单向翻转）
        if self._trend_up:
            # 上升趋势中：下轨 = max(下轨, 前下轨)
            if current_close < lower_band:
                self._trend_up = False  # 趋势翻转
        else:
            # 下降趋势中：上轨 = min(上轨, 前上轨)
            if current_close > upper_band:
                self._trend_up = True   # 趋势翻转

        # 信号
        if not self._in_position:
            if self._trend_up:
                self._in_position = True
                return "BUY"
        else:
            if not self._trend_up:
                self._in_position = False
                return "SELL"

        return None

    @staticmethod
    def _calc_atr(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int
    ) -> float:
        """计算 ATR（全量 rolling 实现）"""
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])
```

### 3.3 回测命令

```bash
python scripts/run_backtest.py --strategy supertrend --period 10 --multiplier 3.0
```

### 3.4 测试要点

| 场景 | 预期 |
|------|------|
| 趋势向上 → 翻转 | BUY → 持有 → SELL |
| 参数 period=14, mult=2.0 | 更敏感，信号更频繁 |
| 参数 period=7, mult=4.0 | 更迟钝，信号更少 |
| 横盘震荡 | 可能频繁翻转，需要或暂停 |

---

## 四、关键位反转策略（Price Action）

### 4.1 核心逻辑

```
步骤1：S/R 区域识别
  从近 N 根 bar 中聚类 swing highs 和 swing lows
  每簇形成支撑区或阻力区

步骤2：pin bar 确认
  pin bar 判断：影线 > 实体 × threshold（默认 2.0）
  - 上影线 pin bar：价格冲高被拒绝 → 反转下跌信号
  - 下影线 pin bar：价格探底被拒绝 → 反转上涨信号

步骤3：入场
  价格在支撑区附近 + 下影线 pin bar → BUY
  价格在阻力区附近 + 上影线 pin bar → SELL

步骤4：出场
  - 固定止损（ATR × stop_mult 跟踪）
  - 反向 pin bar 出场
  - 熔断出场
```

### 4.2 代码实现

**文件：** `src/strategy/key_level_reversal.py`

```python
"""
关键位反转策略（Price Action）

基于支撑/阻力位 + pin bar 确认的反转策略。
在历史关键价位等待价格行为确认信号入场。

与网格策略的异同：
- 相同：都在关键区间内低买高卖
- 不同：网格是固定间距机械挂单，反转是价格行为确认后入场
- 互补：网格负责区间内持续收割，反转负责转折点的精准入场

适用环境：支撑阻力清晰的震荡/转折市场。
不适用环境：强单边、无历史结构的新高/新低区域。
"""

from typing import Optional, List, Tuple
from datetime import datetime
import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class KeyLevelReversalStrategy(RiskAwareStrategy):
    """关键位反转策略

    逻辑：
    1. 从近 lookback 根 bar 中识别支撑/阻力区域
    2. 在 S/R 附近检测 pin bar（拒绝信号）
    3. pin bar 确认后入场
    4. 固定 ATR 止损 + 反向 pin bar 出场
    """

    PARAM_SCHEMA = {
        "lookback":       {"type": int,   "min": 10, "max": 100, "default": 50},
        "pin_threshold":  {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "stop_atr_mult":  {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "atr_period":     {"type": int,   "min": 2,   "max": 50,  "default": 14},
        "max_consecutive_losses": {"type": int, "min": 1, "default": 3},
        "max_daily_loss": {"type": float, "min": 0, "max": 0.1, "default": 0.02},
    }

    def __init__(
        self,
        lookback: int = 50,
        pin_threshold: float = 2.0,
        stop_atr_mult: float = 2.0,
        atr_period: int = 14,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="KeyLevelReversal",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )

        self.lookback = lookback
        self.pin_threshold = pin_threshold
        self.stop_atr_mult = stop_atr_mult
        self.atr_period = atr_period

        self._in_position = False
        self._support_zone: Tuple[float, float] = (0, 0)
        self._resistance_zone: Tuple[float, float] = (0, 0)

        self.set_parameters(
            lookback=lookback, pin_threshold=pin_threshold,
            stop_atr_mult=stop_atr_mult, atr_period=atr_period,
        )

        logger.info(
            f"KeyLevelReversal initialized: "
            f"lookback={lookback}, pin_threshold={pin_threshold}"
        )

    # ---- 核心逻辑 ----

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.lookback:
            return None

        if self._is_paused():
            return None

        close = float(data["close"].iloc[-1])
        atr = self._calc_atr(data, self.atr_period)

        # 识别 S/R 区域
        sr = self._identify_sr_zones(data)
        self._support_zone = sr["support"]
        self._resistance_zone = sr["resistance"]

        # 检测 pin bar
        pin = self._detect_pin_bar(data)

        if not self._in_position:
            # 在支撑区附近 + 下影线 pin bar → BUY
            near_support = self._in_zone(close, self._support_zone, atr)
            if near_support and pin == "bullish":
                self._in_position = True
                return "BUY"
        else:
            # 出场条件
            exit_signal = self._check_exit(data, close, atr, pin)
            if exit_signal:
                self._in_position = False
                return "SELL"

        return None

    # ---- 辅助方法 ----

    def _identify_sr_zones(self, data: pd.DataFrame) -> dict:
        """从 lookback 窗口识别支撑/阻力区域"""
        window = data.iloc[-self.lookback:]
        highs = window["high"].values
        lows = window["low"].values
        closes = window["close"].values

        # 简单方法：取 lookback 内的最高和最低区域作为 S/R
        # 生产级可扩展为 swing point 聚类
        support = (
            float(np.percentile(lows, 10)),
            float(np.percentile(lows, 30)),
        )
        resistance = (
            float(np.percentile(highs, 70)),
            float(np.percentile(highs, 90)),
        )
        return {"support": support, "resistance": resistance}

    def _in_zone(self, price: float, zone: Tuple[float, float], atr: float) -> bool:
        """检查价格是否在区域附近（±0.5 ATR 容忍度）"""
        margin = atr * 0.5
        return (zone[0] - margin) <= price <= (zone[1] + margin)

    def _detect_pin_bar(self, data: pd.DataFrame) -> Optional[str]:
        """检测 pin bar（拒绝信号）

        返回：'bullish'（下影线 pin bar）、'bearish'（上影线 pin bar）、None
        """
        bar = data.iloc[-1]
        open_, high, low, close = (
            float(bar["open"]), float(bar["high"]),
            float(bar["low"]), float(bar["close"]),
        )

        body = abs(close - open_)
        if body == 0:
            return None  # doji，不算 pin bar

        upper_wick = high - max(open_, close_)
        lower_wick = min(open_, close_) - low

        if lower_wick > body * self.pin_threshold:
            return "bullish"
        if upper_wick > body * self.pin_threshold:
            return "bearish"
        return None

    def _check_exit(
        self, data: pd.DataFrame, close: float, atr: float, pin: Optional[str]
    ) -> bool:
        """检查出场条件"""
        # 条件1：价格回到阻力区 + 上影线 pin bar
        if pin == "bearish" and self._in_zone(close, self._resistance_zone, atr):
            return True

        # 条件2：ATR 追踪止损
        # （简化：固定 ATR 倍数止损，生产级可用 trailing stop）
        entry_bar = self._get_entry_price(data)
        if entry_bar is not None:
            stop_loss = entry_bar - self.stop_atr_mult * atr
            if close < stop_loss:
                return True

        return False

    def _get_entry_price(self, data: pd.DataFrame) -> Optional[float]:
        """获取入场价格（简化：用最近一根 bar 的 close 近似）"""
        if not self._in_position:
            return None
        if len(data) < 2:
            return None
        return float(data["close"].iloc[-2])

    @staticmethod
    def _calc_atr(data: pd.DataFrame, period: int) -> float:
        high, low, close = data["high"], data["low"], data["close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])

    def reset(self):
        super().reset()
        self._in_position = False
        self._support_zone = (0, 0)
        self._resistance_zone = (0, 0)
```

### 4.3 回测命令

```bash
python scripts/run_backtest.py --strategy reversal --lookback 50 --pin-threshold 2.0
```

### 4.4 测试要点

| 场景 | 预期 |
|------|------|
| 支撑区 + 下影线 pin bar | BUY |
| 阻力区 + 上影线 pin bar | SELL |
| 支撑区无 pin bar 确认 | 无信号 |
| 远离 S/R 区域的 pin bar | 无信号（不与任何区域关联） |
| 连亏 3 笔 | 熔断 |

---

## 五、公共操作清单

### 5.1 所有策略共用的模板

```
1. 继承 RiskAwareStrategy
2. 实现 on_bar(data, time) → 'BUY'/'SELL'/None
3. 实现 reset() → 调用 super().reset() + 重置自身状态
4. 定义 PARAM_SCHEMA
5. 在 __init__ 调用 super().__init__(name=..., ...)
6. 在 registry.py 中注册
7. 在 run_backtest.py 的 STRATEGY_DEFAULTS 中加默认参数
8. 在 run_multi.py 的 STRATEGY_FACTORY 中加工厂函数
```

### 5.2 注册表完整代码（`src/strategy/registry.py`）

```python
from src.strategy.base import Strategy
from src.strategy.grid_trading import GridTradingStrategy
from src.strategy.rsi_momentum import RSIMomentumStrategy
from src.strategy.simple_ma import SimpleMAStrategy
from src.strategy.buy_and_hold import BuyAndHoldStrategy
from src.strategy.donchian_channel import DonchianChannelStrategy       # 新增
from src.strategy.market_structure import MarketStructureStrategy      # 新增
from src.strategy.super_trend import SuperTrendStrategy                # 新增
from src.strategy.key_level_reversal import KeyLevelReversalStrategy   # 新增

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "grid":      GridTradingStrategy,
    "rsi":       RSIMomentumStrategy,
    "ma":        SimpleMAStrategy,
    "buyhold":   BuyAndHoldStrategy,
    "donchian":  DonchianChannelStrategy,       # 新增
    "structure": MarketStructureStrategy,       # 新增
    "supertrend": SuperTrendStrategy,           # 新增
    "reversal":  KeyLevelReversalStrategy,      # 新增
}
```

### 5.3 `run_multi.py` 工厂函数补充

```python
STRATEGY_FACTORY = {
    "grid":       lambda df: get_strategy("grid")(...),
    "rsi":        lambda df: get_strategy("rsi")(...),
    "ma":         lambda df: get_strategy("ma")(...),
    "buyhold":    lambda df: get_strategy("buyhold")(),
    "donchian":   lambda df: get_strategy("donchian")(period=20),      # 新增
    "structure":  lambda df: get_strategy("structure")(lookback=10),   # 新增
    "supertrend": lambda df: get_strategy("supertrend")(period=10, multiplier=3.0),  # 新增
    "reversal":   lambda df: get_strategy("reversal")(lookback=50),    # 新增
}
```

### 5.4 全策略对比回测

```bash
python scripts/run_multi.py --strategies grid,donchian,structure,rsi,ma,buyhold
```

预期输出对比表：

```
  Strategy      Return    Sharpe     MaxDD   WinRate  Trades
  ----------------------------------------------------------
  donchian      +X.XX%     X.XX     -X.XX%    XX.X%     XX
  structure     +X.XX%     X.XX     -X.XX%    XX.X%     XX
  grid          +X.XX%     X.XX     -X.XX%    XX.X%     XX
  rsi           +X.XX%     X.XX     -X.XX%    XX.X%     XX
  ma            +X.XX%     X.XX     -X.XX%    XX.X%     XX
  buyhold       +X.XX%     X.XX     -X.XX%    XX.X%     X
```

---

## 六、市场覆盖矩阵（8 策略完整版）

| 市场状态 | 推荐策略 | 分类器自动选择 |
|----------|----------|---------------|
| 横盘震荡 | grid, reversal | `classify_market` → "ranging" |
| 上升趋势 | donchian, structure, supertrend, rsi, ma | → "trending_up" |
| 下降趋势 | donchian (空仓), supertrend (空仓), buyhold | → "trending_down" |
| 高波动 | reversal, rsi | → "volatile" |

---

**文档状态：** ✅ 已批准  
**下一步：** 按第1批（donchian + structure）开始实现代码
