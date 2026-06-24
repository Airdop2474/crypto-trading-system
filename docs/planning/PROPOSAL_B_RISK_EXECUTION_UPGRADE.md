# 方案 B：风控与执行层升级方案

**文档版本**：v1.0
**创建日期**：2026-06-25
**状态**：草案
**目标**：从"能止损"进化到"精细化风险管理"，从"能下单"进化到"智能执行"

---

## 一、背景与问题

### 1.1 现状

**风控层**：
- `RiskAwareStrategy`（策略级）：连亏熔断、日亏熔断、累计回撤熔断
- `RiskManager`（账户级）：日亏损、连亏、总仓位、API 失败、总回撤
- 双层 OR 关系，任一暂停即止

**执行层**：
- `BacktestEngine`：固定滑点（0.05%），固定手续费（0.1%）
- `PaperBroker`：模拟市价单，无滑点建模
- `ExchangeBroker`：交易所接口（开发中）
- `OrderGuard`：订单安全检查（存在但未深入使用）

### 1.2 核心问题

1. **止损静态**：所有策略没有内建止损逻辑，完全依赖熔断。熔断是"最后防线"，不是"交易止损"
2. **仓位管理粗放**：BUY 信号一来就是 fraction 仓位，没有根据波动率或置信度调整
3. **滑点建模过于简单**：回测用固定 0.05%，实盘滑点与订单大小、流动性强相关
4. **无移动止损**：盈利后只能等反向信号平仓，无法锁定利润
5. **无时间止损**：持仓可能无限期，资金效率低
6. **组合级热力未利用**：RiskManager 有 `max_total_position` 但只是简单的比例检查

---

## 二、升级方案

### 2.1 ATR 自适应止损

**文件**：新建 `src/execution/stop_loss.py`

**设计**：提供可复用的止损计算模块，策略在生成信号时调用。

```python
class ATRStopLoss:
    """ATR 自适应止损计算器。

    止损价 = 入场价 - atr_multiplier * ATR(atr_period)
    高波动时止损自动放宽，低波动时自动收紧。
    """

    def __init__(
        self,
        atr_period: int = 14,
        atr_multiplier: float = 2.0,
        min_stop_pct: float = 0.01,   # 最小止损距离 1%
        max_stop_pct: float = 0.10,   # 最大止损距离 10%
    ):
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.min_stop_pct = min_stop_pct
        self.max_stop_pct = max_stop_pct

    def calculate_stop_price(
        self,
        entry_price: float,
        data: pd.DataFrame,
    ) -> float:
        """计算止损价格。

        参数：
            entry_price: 入场价格
            data: 包含 high/low/close 的 DataFrame

        返回：
            止损价格（低于 entry_price）
        """
        atr = self._calc_atr(data)
        stop_distance = atr * self.atr_multiplier

        # 钳位到合理范围
        stop_distance = max(stop_distance, entry_price * self.min_stop_pct)
        stop_distance = min(stop_distance, entry_price * self.max_stop_pct)

        return entry_price - stop_distance

    def _calc_atr(self, data: pd.DataFrame) -> float:
        """计算 ATR（增量版本，O(1) per bar）。"""
        ...
```

**集成方式**：
- 策略在 `on_bar()` 中检查是否触发止损
- `BacktestEngine` 不需要改动，止损由策略内部处理

```python
# 策略中使用示例
def on_bar(self, data, current_time):
    if self._is_paused(current_time):
        return None

    # 检查止损
    if self.position > 0:
        stop_price = self.stop_loss.calculate_stop_price(
            self.entry_price, data
        )
        if data['close'].iloc[-1] < stop_price:
            return 'SELL'  # 止损平仓

    # 原有信号逻辑...
```

**验收标准**：
- [ ] RSI 策略 + ATR 止损回测，最大回撤下降 > 20%（对比无止损）
- [ ] 止损触发率 < 30%（不应过于频繁）
- [ ] 代码覆盖率 > 90%

### 2.2 移动止损（Trailing Stop）

**文件**：扩展 `src/execution/stop_loss.py`

**设计**：盈利后不急着止盈，而是跟踪最高价设置移动止损。

```python
class TrailingStop:
    """移动止损管理器。

    跟踪持仓期间的最高价，当价格从最高点回撤超过阈值时触发止损。
    """

    def __init__(
        self,
        trail_pct: float = 0.03,        # 回撤阈值 3%
        activation_profit: float = 0.02, # 盈利 2% 后才激活
        trail_atr_multiplier: float = 0, # 0 表示用固定百分比，> 0 用 ATR
    ):
        self.trail_pct = trail_pct
        self.activation_profit = activation_profit
        self.trail_atr_multiplier = trail_atr_multiplier

        # 状态
        self._highest_price: float = 0.0
        self._activated: bool = False
        self._entry_price: float = 0.0

    def update(self, current_price: float, entry_price: float) -> None:
        """更新移动止损状态。"""
        if current_price > self._highest_price:
            self._highest_price = current_price

        profit_pct = (current_price - entry_price) / entry_price
        if profit_pct >= self.activation_profit:
            self._activated = True

    def should_stop(self, current_price: float) -> bool:
        """检查是否触发移动止损。"""
        if not self._activated:
            return False

        drawdown = (self._highest_price - current_price) / self._highest_price
        return drawdown >= self.trail_pct

    def reset(self) -> None:
        """重置状态（平仓后调用）。"""
        self._highest_price = 0.0
        self._activated = False
```

**与 ATR 止损的关系**：
- ATR 止损是"初始止损"，在入场时确定
- 移动止损是"跟踪止损"，随价格变动
- 两者取较宽松的那个（避免被正常波动扫出）

**验收标准**：
- [ ] 趋势市中移动止损能多捕获 > 15% 的利润（对比固定止损）
- [ ] 震荡市中移动止损触发率 < 20%
- [ ] 代码覆盖率 > 90%

### 2.3 时间止损

**文件**：扩展 `src/execution/stop_loss.py`

**设计**：持仓超过 N 根 K 线仍未达到目标收益时强制平仓。

```python
class TimeStop:
    """时间止损管理器。

    避免资金被僵尸仓位占用。
    """

    def __init__(
        self,
        max_bars: int = 50,           # 最大持仓 K 线数
        min_profit_pct: float = 0.01, # 持仓期间最低盈利要求
    ):
        self.max_bars = max_bars
        self.min_profit_pct = min_profit_pct

    def should_stop(
        self,
        bars_held: int,
        current_profit_pct: float,
    ) -> bool:
        """检查是否触发时间止损。"""
        if bars_held >= self.max_bars:
            if current_profit_pct < self.min_profit_pct:
                return True  # 超时且未达标
        return False
```

**验收标准**：
- [ ] 时间止损触发后，资金周转率提升 > 10%
- [ ] 不显著影响策略总收益（< 5% 收益损失）

### 2.4 Kelly 公式动态仓位

**文件**：新建 `src/execution/position_sizer.py`

**设计**：利用已有的 Kelly Criterion 计算结果，动态调整每笔交易的仓位大小。

```python
class KellyPositionSizer:
    """基于 Kelly 公式的动态仓位管理。

    使用半 Kelly（Kelly/2）以降低风险。
    """

    def __init__(
        self,
        kelly_fraction: float = 0.5,  # 半 Kelly
        min_position: float = 0.05,   # 最小仓位 5%
        max_position: float = 0.25,   # 最大仓位 25%
        lookback_trades: int = 30,    # 回看最近 30 笔交易
    ):
        self.kelly_fraction = kelly_fraction
        self.min_position = min_position
        self.max_position = max_position
        self.lookback_trades = lookback_trades

    def calculate_position_size(
        self,
        recent_trades: List[Dict],
        current_equity: float,
    ) -> float:
        """计算建议仓位比例。

        参数：
            recent_trades: 最近的交易记录
            current_equity: 当前权益

        返回：
            建议仓位比例（0-1）
        """
        if len(recent_trades) < 10:
            return self.min_position  # 数据不足，用最小仓位

        win_rate = sum(1 for t in recent_trades if t['profit'] > 0) / len(recent_trades)
        avg_win = np.mean([t['profit'] for t in recent_trades if t['profit'] > 0])
        avg_loss = abs(np.mean([t['profit'] for t in recent_trades if t['profit'] < 0]))

        if avg_loss == 0:
            return self.max_position

        # Kelly 公式：f* = (p * b - q) / b
        # p = 胜率, q = 败率, b = 赔率
        b = avg_win / avg_loss
        q = 1 - win_rate
        kelly = (win_rate * b - q) / b

        # 应用半 Kelly 和钳位
        position = kelly * self.kelly_fraction
        position = max(self.min_position, min(self.max_position, position))

        return position
```

**与策略的集成**：
- 策略在生成 BUY 信号时，调用 `position_sizer.calculate_position_size()` 获取建议仓位
- `Order.fraction` 使用计算结果而非固定值

**验收标准**：
- [ ] Kelly 动态仓位回测，夏普比率提升 > 10%（对比固定仓位）
- [ ] 最大回撤下降 > 15%
- [ ] 代码覆盖率 > 90%

### 2.5 组合级热力控制

**文件**：扩展 `src/execution/risk_manager.py`

**设计**：在现有 RiskManager 基础上增加 Portfolio Heat 计算。

```python
# RiskManager 新增方法
def calculate_portfolio_heat(
    self,
    positions: Dict[str, Dict],
    market_data: Dict[str, pd.DataFrame],
) -> float:
    """计算组合总风险暴露（Portfolio Heat）。

    Portfolio Heat = Σ(仓位大小 * ATR * 价格)
    反映组合在当前波动率下的总风险敞口。

    参数：
        positions: 持仓字典 {symbol: {qty, cost_price, ...}}
        market_data: 行情数据 {symbol: DataFrame}

    返回：
        组合热力值（占总权益的比例）
    """
    total_heat = 0.0
    for symbol, pos in positions.items():
        if pos['qty'] <= 0:
            continue
        df = market_data.get(symbol)
        if df is None:
            continue
        atr = self._calc_atr(df)
        position_value = pos['qty'] * df['close'].iloc[-1]
        position_risk = position_value * atr / df['close'].iloc[-1]
        total_heat += position_risk

    return total_heat / self.capital_base if self.capital_base > 0 else 0.0

def can_open_position_heat(
    self,
    new_position_risk: float,
    max_heat: float = 0.15,  # 最大组合热力 15%
) -> bool:
    """检查新开仓是否超过组合热力上限。"""
    current_heat = self._current_heat + new_position_risk
    return current_heat <= max_heat
```

**验收标准**：
- [ ] 组合热力超过阈值时自动停止新开仓
- [ ] 热力计算实时更新（每根 bar）

### 2.6 滑点建模增强

**文件**：扩展 `src/utils/trading.py`

**设计**：从固定滑点改为基于订单大小的滑点模型。

```python
def apply_slippage_enhanced(
    price: float,
    side: str,
    quantity: float,
    avg_daily_volume: float,
    base_slippage: float = 0.0005,
    impact_factor: float = 0.1,
) -> float:
    """增强的滑点计算。

    滑点 = 基础滑点 + 冲击系数 * (订单量 / 日均成交量)

    大单滑点更大，小单滑点更小。
    """
    volume_ratio = quantity / avg_daily_volume if avg_daily_volume > 0 else 0
    slippage = base_slippage + impact_factor * volume_ratio

    if side == 'BUY':
        return price * (1 + slippage)
    else:
        return price * (1 - slippage)
```

**BacktestEngine 改动**：
- 新增 `volume_data` 参数（可选）
- 如果提供了成交量数据，使用增强滑点模型
- 否则回退到固定滑点（向后兼容）

**验收标准**：
- [ ] 大单（> 日均成交量 1%）滑点增加 > 2x
- [ ] 小单（< 日均成交量 0.1%）滑点不变
- [ ] 现有测试全部通过

### 2.7 策略相关性监控

**文件**：新建 `src/monitor/correlation_monitor.py`

**设计**：监控多策略间的交易相关性，避免同向重仓。

```python
class CorrelationMonitor:
    """策略交易相关性监控。

    基于最近 N 笔交易的盈亏序列计算相关系数。
    相关性过高时发出警告或抑制新信号。
    """

    def __init__(
        self,
        lookback_trades: int = 20,
        max_correlation: float = 0.7,
    ):
        self.lookback_trades = lookback_trades
        self.max_correlation = max_correlation

    def calculate_correlation(
        self,
        trades_a: List[Dict],
        trades_b: List[Dict],
    ) -> float:
        """计算两个策略的交易相关性。"""
        # 对齐时间戳，计算盈亏序列的相关系数
        ...

    def should_inhibit(
        self,
        strategy_id: str,
        active_strategies: Dict[str, List[Dict]],
    ) -> bool:
        """检查是否应该抑制新信号（相关性过高）。"""
        ...
```

**集成方式**：
- `MultiStrategyRunner` 在处理每个策略信号前调用 `should_inhibit()`
- 相关性过高时，只允许第一个策略开仓，后续抑制

**验收标准**：
- [ ] 相关性监控实时更新
- [ ] 相关性过高时自动抑制信号
- [ ] 代码覆盖率 > 85%

---

## 三、实施计划

### Phase B1：止损体系（2 周）

| 任务 | 预计工时 | 依赖 |
|------|---------|------|
| ATR 止损计算器 | 2 天 | 无 |
| 移动止损管理器 | 2 天 | ATR 止损 |
| 时间止损管理器 | 1 天 | 无 |
| 集成到 RSI/MA 策略 | 2 天 | 止损完成 |
| 回测验证 | 2 天 | 集成完成 |
| 文档更新 | 1 天 | 全部完成 |

### Phase B2：仓位管理（1.5 周）

| 任务 | 预计工时 | 依赖 |
|------|---------|------|
| Kelly 仓位计算器 | 2 天 | PerformanceMetrics（已有） |
| 集成到策略 | 2 天 | Kelly 完成 |
| 组合热力计算 | 2 天 | RiskManager |
| 回测验证 | 2 天 | 全部完成 |

### Phase B3：执行优化（1 周）

| 任务 | 预计工时 | 依赖 |
|------|---------|------|
| 增强滑点模型 | 2 天 | 无 |
| BacktestEngine 改动 | 1 天 | 滑点模型 |
| 相关性监控 | 2 天 | MultiStrategyRunner |
| 集成测试 | 1 天 | 全部完成 |

**总工时**：约 4.5 周

---

## 四、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| ATR 止损过于频繁 | 中 | 中 | 设置最小止损距离（1%）和最大止损距离（10%） |
| 移动止损扫出后趋势继续 | 中 | 中 | 设置激活阈值（盈利 2% 后才激活） |
| Kelly 仓位过小 | 低 | 低 | 设置最小仓位下限（5%） |
| 增强滑点导致回测过于悲观 | 低 | 低 | 提供开关，可回退到固定滑点 |
| 相关性监控误判 | 中 | 中 | 设置合理的回看窗口和阈值 |

---

## 五、成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| 最大回撤（RSI 策略） | ~15% | < 10%（ATR 止损后） |
| 盈亏比 | ~1.5:1 | > 2:1（移动止损后） |
| 资金周转率 | 低 | 提升 > 15%（时间止损后） |
| 组合夏普 | 单策略 ~1.5 | 动态仓位后 > 1.8 |
| 滑点模型精度 | 固定 0.05% | 基于成交量动态计算 |

---

## 六、依赖关系图

```
ATR 止损 ──┐
移动止损 ──┼──→ 集成到策略 ──→ 回测验证
时间止损 ──┘

Kelly 仓位 ──→ 集成到策略 ──→ 组合热力 ──→ RiskManager 增强

增强滑点 ──→ BacktestEngine 改动

相关性监控 ──→ MultiStrategyRunner 增强
```

---

*方案 B 结束*
