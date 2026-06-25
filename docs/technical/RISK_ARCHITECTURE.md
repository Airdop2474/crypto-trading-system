# 风控架构设计

**文档版本：** v1.0  
**创建日期：** 2026-06-25  
**状态：** ✅ 已批准  
**优先级：** 最高

---

## 目的

本文档定义系统的多层风控架构，覆盖从单笔下单到账户整体资金安全的完整防护链。
风控是实盘交易的生命线，所有风控逻辑必须基于代码实际实现，不允许编造不存在的功能。

**核心原则：** 多层防御、职责分离、状态机驱动、宁停勿亏。

---

## 架构概述

系统采用四层风控架构，从最贴近交易的下单护栏逐级上升到跨策略的组合热力协调，
每一层回答不同的问题，任一层拦截即止：

```
                      ┌─────────────────────────────┐
                      │     PortfolioHeatManager     │  跨策略热力协调
                      │  (Σ 持仓市值×ATR% / 总资金)  │  回答：组合是否过热？
                      └──────────────┬──────────────┘
                                     │ 拒绝新开仓
                      ┌──────────────▼──────────────┐
                      │       RiskManager            │  账户级状态机
                      │  (ACTIVE / PAUSED / STOPPED) │  回答：账户是否安全？
                      └──────────────┬──────────────┘
                                     │ can_trade() / record_fill()
                ┌────────────────────┼────────────────────┐
                │                    │                    │
      ┌─────────▼─────────┐ ┌────────▼─────────┐ ┌───────▼──────────┐
      │ RiskAwareStrategy  │ │  OrderRateGuard   │ │  StopLossManager │
      │  (策略级熔断基类)   │ │  (订单级下单护栏) │ │  (止损管理器)     │
      │  回答：策略是否     │ │  回答：这笔单     │ │  回答：持仓是否   │
      │  适应当前市场？     │ │  能不能下？       │ │  该止损？         │
      └────────────────────┘ └───────────────────┘ └──────────────────┘
```

**设计理念：**
- 每一层职责独立，互不重复，组合形成纵深防御
- 策略级熔断与账户级熔断是 OR 关系：任一暂停即止交易
- 回测模式仅用策略级熔断；纸面/实盘同时启用全部四层

---

## 1. 风控层级总览

| 层级 | 组件 | 文件 | 作用域 | 核心问题 |
|------|------|------|--------|----------|
| L1 订单护栏 | `OrderRateGuard` | `src/execution/order_guard.py` | 单笔订单 | 这笔单能不能下？ |
| L1 止损管理 | `StopLossManager` | `src/strategy/stop_loss.py` | 单策略持仓 | 持仓是否该止损？ |
| L2 策略熔断 | `RiskAwareStrategy` | `src/strategy/risk_aware.py` | 单策略 | 策略是否适应当前市场？ |
| L3 账户状态机 | `RiskManager` | `src/execution/risk_manager.py` | 账户整体 | 账户是否还在安全线内？ |
| L4 组合热力 | `PortfolioHeatManager` | `src/risk/portfolio_heat.py` | 跨策略 | 组合是否过热？ |

---

## 2. 订单护栏（OrderRateGuard）

**文件：** `src/execution/order_guard.py`

### 定位

补齐下单提交层的节流护栏。Exchange 模式真实下单绕过了 PaperBroker 的每单仓位检查，
RiskManager 又只管账户级 fill/pnl 熔断，故在下单提交层另设一道节流。

### 三道护栏

```python
class OrderRateGuard:
    def __init__(self, reference_capital, max_position_per_trade=0.20,
                 min_trade_interval=300, max_trades_per_day=10):
```

| 护栏 | 默认值 | 说明 |
|------|--------|------|
| 单笔名义额上限 | `20%` × 资金基准 | 防止单笔下单过大 |
| 最小决策间隔 | `300` 秒 | 防止短时间频繁下单（按 bar 时间戳判） |
| 日订单数上限 | `10` 笔 | 限制每日下单频率 |

### 工作机制

- **只作用于 exchange 模式**，由 `ExchangeRunnerBroker` 在 `place_order()` 中调用
- 频率主判用 runner 传入的 **bar timestamp**（下单决策周期），同一 bar 触发的多笔 grid lot 视作一次决策、全放行
- 单笔上限与日订单数仍逐单生效
- `check()` 返回 `(ok, reason)`，`ok=False` 时不下单；`record()` 登记一次实际下单

```python
# ExchangeRunnerBroker.place_order() 中的调用
if self.guard is not None:
    ok, reason = self.guard.check(order.amount * order.price, timestamp)
    if not ok:
        self._errors += 1
        return OrderResult(order_id=None, status="rejected", reason=reason)
# ... 成交后 ...
if self.guard is not None:
    self.guard.record(timestamp)
```

---

## 3. 止损管理（StopLossManager）

**文件：** `src/strategy/stop_loss.py`

### 定位

统一的止损门面类，跟踪持仓的入场价、入场时间、最高价，按配置的止损类型判断是否应止损。

### 四种止损类型

| 类型 | `stop_type` | 适用策略 | 说明 |
|------|-------------|----------|------|
| 不止损 | `"none"` | BuyHold | 不设止损 |
| ATR + 移动止损 | `"atr_trailing"` | 趋势策略 | 固定止损（入场 - N×ATR）+ 移动止损（最高价回撤） |
| 区间突破止损 | `"range_breakout"` | 均值回归策略 | 价格从入场价向不利方向突破一定比例 |
| 仅时间止损 | `"time_only"` | Grid / Donchian | 持仓超过 N 根 K 线平仓 |

### StopLossConfig 配置

```python
@dataclass
class StopLossConfig:
    stop_type: StopType = "atr_trailing"
    atr_mult: float = 1.5              # ATR 倍数，安全范围 [0.5, 4.0]
    trailing_activation: float = 0.03  # 移动止损激活阈值，[0.01, 0.10]
    trailing_drawback: float = 0.03    # 移动止损回撤比例，[0.01, 0.08]
    range_breakout_pct: float = 0.05   # 区间突破比例，[0.02, 0.10]
    max_bars: int = 50                 # 时间止损 K 线数，[0, 200]
    min_stop_pct: float = 0.01         # 最小止损比例，[0.005, 0.03]
```

**安全边界：** 所有参数在 `__post_init__` 中自动 clamp 到安全范围，防止 EvolutionEngine 优化出危险值。

### ATR + 移动止损逻辑（atr_trailing）

1. **固定止损价** = `entry - atr_mult × ATR`，且不低于 `entry × (1 - min_stop_pct)`
2. **移动止损价** = 当涨幅超过 `trailing_activation` 后，`highest × (1 - trailing_drawback)`
3. **生效止损价** = 取两者中较高者（更紧的止损）

```python
# 取两者中较高的（更紧的止损）
if trailing_stop is not None:
    self._current_stop_price = max(fixed_stop, trailing_stop)
else:
    self._current_stop_price = fixed_stop
```

### 区间突破止损逻辑（range_breakout）

对多头：价格跌破 `entry × (1 - range_breakout_pct)` 时触发。

### 生命周期

```
on_fill(BUY)  → 记录 entry_price, entry_time, highest_price
check_stop()  → 每根 K 线检查是否触发止损
on_fill(SELL) → 重置状态（部分卖出不重置）
```

- `check_stop()` 是无状态检查（纯函数逻辑，仅更新最高价和持仓 bar 数）
- `on_fill()` 处理加仓（更新最高价）和清仓（重置状态）
- 网格单档卖出（部分卖出）不重置整体状态

### 策略默认配置

**文件：** `src/strategy/stop_configs.py`

| 配置常量 | 止损类型 | 适用策略 |
|----------|----------|----------|
| `TREND_STOP_CONFIG` | atr_trailing | rsi, ma, structure, supertrend, macd, composite |
| `RANGE_STOP_CONFIG` | range_breakout | bollinger, reversal, priceaction |
| `DONCHIAN_STOP_CONFIG` | time_only (80 bars) | donchian（已有自带追踪止损） |
| `GRID_STOP_CONFIG` | time_only (100 bars) | grid（已有边界击穿保护） |
| `NONE_STOP_CONFIG` | none | buyhold |

通过 `get_stop_config(strategy_name)` 获取，默认返回 `TREND_STOP_CONFIG`。

---

## 4. 策略级熔断（RiskAwareStrategy）

**文件：** `src/strategy/risk_aware.py`

### 定位

提取各策略中公共的熔断逻辑，统一封装为策略基类。子类只需继承并调用 `_is_paused()` 即可。
回答"这个策略是否还适合当前市场"。

### 与 RiskManager 的职责分工

| | RiskAwareStrategy | RiskManager |
|--|-------------------|-------------|
| 作用域 | 单策略 | 账户整体 |
| 回答 | 策略是否适应当前市场 | 账户是否还在安全线内 |
| 触发后 | 抛 `CircuitBreaker` 异常 | 状态机 PAUSED/STOPPED |
| 关系 | OR：任一暂停即止 | OR：任一暂停即止 |

### 三条熔断线（按序检测）

```python
def on_fill(self, trade: dict) -> None:
    # 1. 累计回撤 > max_drawdown（默认 15%）→ 触发
    # 2. 连亏笔数 >= max_consecutive_losses（默认 3）→ 触发
    # 3. 当日亏损 >= max_daily_loss（占初始资金，默认 2%）→ 触发
```

| 熔断条件 | 默认阈值 | 触发动作 |
|----------|----------|----------|
| 累计回撤 | `15%`（基于峰值回撤） | `_trigger_breaker()` |
| 连续亏损 | `3` 笔 | `_trigger_breaker()` |
| 当日亏损 | `2%`（占初始资金） | `_trigger_breaker()` |

### 日切自动恢复

- 如果当前交易日与暂停日不同且当日亏损未超限额，自动清除熔断状态
- **最多自动恢复 3 次**，超过后需手动 `reset()`
- **回撤熔断不自动恢复**（`"drawdown" not in reason`）

```python
# 日切自动恢复（仅日亏/连亏熔断；回撤熔断不自动恢复）
if current_time is not None and self._auto_resume_count < 3:
    bar_day = pd.Timestamp(current_time).date()
    if bar_day is not None and self._current_day != bar_day:
        if "drawdown" not in (self._paused_reason or ""):
            # 清除熔断状态，auto_resume_count += 1
```

### 止损集成

`RiskAwareStrategy` 内置 `StopLossManager`，通过 `_check_stop_loss()` 在 `on_bar()` 中调用：

```python
def _check_stop_loss(self, current_price, current_time=None, atr=None) -> tuple[bool, str]:
    # 1. 无止损管理器或未持仓 → 不触发
    # 2. 调用 slm.check_stop() 判断
    # 3. 触发时发送 Telegram 通知（异步，不阻塞）
```

止损触发时通过 `telegram_notifier` 发送通知，包含原因、入场价、当前价、持仓 K 线数、止损类型。

### ADX 趋势过滤器

基类还内置 ADX 指标计算（Wilder 平滑法），供子类判断趋势市/震荡市：
- `_is_trending(threshold=25.0)`：ADX > 25 → 趋势市
- `_is_ranging(threshold=20.0)`：ADX < 20 → 震荡市

---

## 5. 账户级状态机（RiskManager）

**文件：** `src/execution/risk_manager.py`

### 定位

独立的账户级风控状态机，与策略/Broker 解耦。回答"账户是否还在安全线内"。
多策略叠加时账户可能过热，即使各策略健康。

### 三态状态机

```
    ┌──────────────────────────────────────────────┐
    │                                              │
    ▼                                              │
┌─────────┐  熔断条件触发  ┌─────────┐  日切/人工  │
│ ACTIVE  │ ─────────────▶ │ PAUSED  │ ──────────┘
│ 正常交易 │                │ 熔断暂停 │
└─────────┘ ◀────────────── └─────────┘
    │                            │
    │       emergency_stop()     │
    │     ┌──────────────────────▶
    │     │                      │
    │     ▼                ┌──────────┐
    │  ┌──────────┐        │ STOPPED  │ 最强保护
    └─▶│  reset() │◀───────│ 紧急停止  │ 需 reset() 恢复
       └──────────┘        └──────────┘
```

| 状态 | 含义 | 恢复方式 |
|------|------|----------|
| `ACTIVE` | 正常交易 | — |
| `PAUSED` | 熔断暂停 | 日切自动恢复（仅日亏）或人工 `resume()` |
| `STOPPED` | 紧急停止 | 仅人工 `reset()`（带防抖保护） |

### 熔断条件

| 条件 | 默认阈值 | 触发方法 |
|------|----------|----------|
| 当日亏损 | `3%`（占资金基准） | `record_fill()` → `_trip_pause("daily loss")` |
| 连续亏损 | `5` 笔 | `record_fill()` → `_trip_pause("consecutive losses")` |
| 账户级最大回撤 | `15%`（累计慢亏保护） | `record_fill()` → `_trip_pause("total drawdown")` |
| 数据异常 | — | `record_data_anomaly()` → `_trip_pause()` |
| API 连续失败 | `3` 次 | `record_api_failure()` → `_trip_pause("api failures")` |

```python
class RiskManager:
    def __init__(self, capital_base, max_daily_loss=0.03,
                 max_consecutive_losses=5, max_total_position=0.60,
                 max_api_failures=3, max_total_drawdown=0.15):
```

### 日切恢复机制

```python
def check_new_day(self, bar_timestamp) -> None:
    """检测日切，重置日内限额并在条件满足时自动恢复。"""
```

- **仅 daily loss 触发的 PAUSE 可日切自动恢复**
- consecutive losses / drawdown / API failures 触发的 PAUSE 不自动恢复
- STOPPED 状态不自动恢复（需人工 `reset()`）
- 由守护进程每根 bar 调用

### 成交回报驱动熔断

`record_fill(trade)` 处理一笔成交，更新盈亏并按需熔断：

```python
def record_fill(self, trade: dict) -> None:
    profit = trade.get("profit")
    if profit is None:
        return  # 买入无已实现盈亏

    self.daily_pnl += profit
    self.cumulative_pnl += profit

    # 连亏计数（profit==0 不改变趋势）
    if profit < 0:
        self.consecutive_losses += 1
    elif profit > 0:
        self.consecutive_losses = 0

    # 依次检测：连亏 → 日亏 → 回撤
```

### 人工恢复与防抖保护

**`resume()`：** PAUSED → ACTIVE，重置瞬时熔断计数（连亏/API），保留当日盈亏。STOPPED 不能 resume。

**`reset()`：** 完全重置到 ACTIVE（含 STOPPED），带双重防抖保护：

| 防抖机制 | 参数 | 说明 |
|----------|------|------|
| 冷却期 | 5 分钟 | reset() 后 5 分钟内禁止再次 reset |
| 频次限制 | 3 次/小时 | 1 小时内超过 3 次 reset → 拒绝，需人工确认 |

**回撤跟踪不清零：** `peak_equity` 和 `cumulative_pnl` 在 reset() 时保留，避免已亏损策略 reset 后绕过年化回撤熔断线。

### 线程安全

所有状态读写通过 `threading.Lock` 保护，`can_trade()` / `is_paused()` / `is_stopped()` 均加锁。

### 仓位检查

```python
def check_position(self, new_position_value, total_value) -> bool:
    """新持仓市值占比是否在上限内（默认 60%）"""
```

与 Broker 的每单资金/仓位 sanity 检查互补。

---

## 6. 组合热力（PortfolioHeatManager）

**文件：** `src/risk/portfolio_heat.py`

### 定位

跨策略的风险敞口协调。计算所有策略持仓的总风险敞口占总资金的比例，超过阈值时拒绝新开仓。

### 公式

```
Portfolio Heat = Σ(持仓市值 × ATR%) / 总资金
ATR% = ATR / price（归一化波动率）
```

### 多进程协调架构

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  RSI daemon │  │  MA daemon  │  │ Grid daemon │
│             │  │             │  │             │
│ update_     │  │ update_     │  │ update_     │
│ position_   │  │ position_   │  │ position_   │
│ heat()      │  │ heat()      │  │ heat()      │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┼────────────────┘
                        ▼
          ┌─────────────────────────────┐
          │  data/portfolio_heat.json    │  共享文件（原子写入）
          │  {                           │
          │    "strategies": {           │
          │      "rsi": {heat, ...},     │
          │      "ma": {heat, ...},      │
          │      "grid": {heat, ...}     │
          │    }                         │
          │  }                           │
          └──────────────┬──────────────┘
                         │
       ┌─────────────────┼─────────────────┐
       ▼                 ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ can_open_   │  │ can_open_   │  │ can_open_   │
│ new_        │  │ new_        │  │ new_        │
│ position()  │  │ position()  │  │ position()  │
└─────────────┘  └─────────────┘  └─────────────┘
```

- daemon 多进程隔离，各策略独立 state 文件
- 通过共享文件 `data/portfolio_heat.json` 协调
- 每个 daemon 写自己的 position_heat 到共享文件
- daemon 开仓前检查共享文件中的总热力

### 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `DEFAULT_MAX_HEAT` | `15%` | 组合热力上限 |
| `UPDATE_INTERVAL` | 5 秒 | 共享文件更新间隔（避免频繁 IO） |
| `LOCK_TIMEOUT` | 10 秒 | 共享文件锁超时 |

### 开仓检查

```python
def can_open_new_position(self, new_position_risk, initial_capital) -> bool:
    portfolio_heat = self.get_portfolio_heat()
    new_heat = new_position_risk / initial_capital
    projected_heat = portfolio_heat + new_heat
    if projected_heat > self.max_heat:
        return False  # 拒绝开仓
    return True
```

### 原子写入

使用 `tmp_file.replace(shared_file)` 实现原子写入，避免多进程并发写入损坏文件。

### ATR 不可用时的兜底

无 ATR 时用 `2%` 近似波动率：`atr_pct = 0.02`。

---

## 7. 急停机制

### 7.1 触发方式

#### 方式一：API 远程急停

**端点：** `POST /admin/emergency-stop`（`src/api/app.py` → `src/api/admin_routes.py`）

```python
def admin_emergency_stop():
    """远程急停：触发全局 RiskManager.emergency_stop()，停止所有策略交易。"""
    risk_manager = getattr(multi_runner, "risk_manager", None)
    risk_manager.emergency_stop("remote emergency-stop via API")
```

急停流程：
1. 从 `multi_runner` 获取 `RiskManager` 实例
2. 调用 `emergency_stop()` → 状态机进入 `STOPPED`
3. 写入信号文件 `data/.emergency_stop`（供守护进程检测）
4. 发送 `CRITICAL` 告警（`alert_manager.emit`）
5. 返回 `{ok, previous_state, current_state: "STOPPED", message}`

#### 方式二：代码内直接调用

```python
risk_manager.emergency_stop("reason")
```

### 7.2 emergency_stop() 内部逻辑

```python
def emergency_stop(self, reason="manual emergency stop") -> None:
    """紧急停止 -> STOPPED（最强保护，需 reset 才能恢复）"""
    if self.state == STOPPED:
        return  # 已停止不重复触发
    self.state = STOPPED
    self._log_event("EMERGENCY_STOP", reason)
    # 推送 Hermes 风控事件
    push_risk_event("EMERGENCY_STOP", reason, self.state)
```

- `STOPPED` 是最强保护状态，`_trip_pause()` 对 STOPPED 不降级
- 同时推送 Hermes 风控事件（`push_risk_event`）

### 7.3 恢复方式

STOPPED 状态只能通过 `reset()` 恢复（带防抖保护），不能通过 `resume()` 恢复：

```python
def reset(self) -> None:
    """完全重置到 ACTIVE（清空所有状态，含 STOPPED）。
    防抖：5 分钟冷却期 + 1 小时最多 3 次。
    回撤跟踪不清零，防止绕过年化回撤熔断线。
    """
```

---

## 8. API 端点

**文件：** `src/api/app.py`（部分实现委托到 `src/api/service.py`）

### 风控状态查询

| 端点 | 方法 | 说明 |
|------|------|------|
| `/account/risk-metrics` | GET | 账户级风险指标（最大回撤/夏普/Sortino/波动率/年化收益） |
| `/risk/drawdown-curve` | GET | 回撤曲线（每点含 equity/peak/drawdown%） |
| `/risk/status` | GET | 账户级风控状态（来自 RiskManager 状态机） |
| `/risk/portfolio-heat` | GET | 组合热力（跨策略风险敞口汇总） |

### `/risk/status` 返回结构

```python
{
    "state": "ACTIVE" | "PAUSED" | "STOPPED",
    "can_trade": bool,
    "daily_pnl": float,
    "daily_loss_limit_pct": float,      # 日亏上限（%）
    "daily_loss_used_pct": float,       # 已用日亏（%）
    "consecutive_losses": int,
    "max_consecutive_losses": int,
    "cumulative_pnl": float,
    "total_drawdown_pct": float,        # 累计回撤（%）
    "max_total_drawdown_pct": float,    # 回撤上限（%）
    "events": [...],                    # 最近 20 条风控事件
    "limits": {                         # 配置上限一览
        "max_daily_loss": float,
        "max_consecutive_losses": int,
        "max_total_position": float,
        "max_total_drawdown": float,
    }
}
```

### 止损配置管理

| 端点 | 方法 | 限流 | 说明 |
|------|------|------|------|
| `/risk/stop-config` | GET | — | 获取所有策略类型的止损配置 |
| `/risk/stop-config` | POST | `10/minute` | 更新指定策略的止损配置（热更新） |

```python
class StopConfigUpdateRequest(BaseModel):
    strategy_type: str
    stop_type: str = "atr_trailing"
    atr_mult: float = 1.5
    trailing_activation: float = 0.03
    trailing_drawback: float = 0.03
    range_breakout_pct: float = 0.05
    max_bars: int = 50
    min_stop_pct: float = 0.01
```

**热更新机制：** POST 请求直接修改模块级字典 `STRATEGY_STOP_CONFIGS[stype]`，运行中的策略下次创建 `StopLossManager` 时使用新配置。参数会被 `StopLossConfig.__post_init__` 自动 clamp 到安全范围。

### 急停端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/admin/emergency-stop` | POST | 远程急停，触发全局 `emergency_stop()` |

---

## 9. 与告警系统的集成

### 9.1 AlertManager 集成

**文件：** `src/monitor/alert_manager.py`

`AlertManager.check_risk_events()` 增量检查 `RiskManager.events`（deque，上限 10000），为新事件产生告警：

```python
def check_risk_events(self, rm: RiskManager) -> List[dict]:
    events_list = list(rm.events)
    new_events = events_list[self._seen_event_count:]
    self._seen_event_count = len(events_list)

    for ev in new_events:
        level = CRITICAL if ev["type"] == "EMERGENCY_STOP" else (
            WARNING if ev["type"] == "PAUSE" else INFO
        )
        new_alerts.append(
            self.emit(level, "risk_manager", f"{ev['type']}: {ev['reason']}")
        )
```

| 事件类型 | 告警级别 |
|----------|----------|
| `EMERGENCY_STOP` | `CRITICAL` |
| `PAUSE` | `WARNING` |
| 其他 | `INFO` |

### 9.2 告警限流防抖

`AlertManager.emit()` 内置两层限流：

| 机制 | 说明 |
|------|------|
| 去重 | 相同 `(source, message)` 在冷却期内不重复 |
| 限流 | 每个 source 每分钟不超过 `max_alerts_per_source` 条 |

### 9.3 急停告警链路

急停触发时，告警通过两条路径传播：

```
emergency_stop()
    │
    ├─▶ _log_event("EMERGENCY_STOP", reason)
    │       │
    │       └─▶ RiskManager.events (deque)
    │               │
    │               └─▶ AlertManager.check_risk_events() → CRITICAL 告警
    │
    └─▶ push_risk_event("EMERGENCY_STOP", reason, state)
            │
            └─▶ Hermes Bridge（AI 风控事件推送）
```

API 急停额外通过 `alert_manager.emit("CRITICAL", "api", ...)` 直接发送告警。

### 9.4 Telegram 通知

止损触发时，`RiskAwareStrategy._check_stop_loss()` 通过 `telegram_notifier.send_warning_sync()` 发送通知，包含：
- 策略名称
- 触发原因
- 入场价
- 当前价
- 持仓 K 线数
- 止损类型

通知失败不影响止损逻辑（捕获异常后仅 debug 日志）。

### 9.5 Hermes Bridge 推送

`RiskManager` 在 `_trip_pause()` 和 `emergency_stop()` 时调用 `push_risk_event()` 推送事件给 Hermes AI 代理系统：

```python
from src.agent.hermes_bridge import push_risk_event
push_risk_event("PAUSE", reason, self.state)          # 熔断暂停
push_risk_event("EMERGENCY_STOP", reason, self.state) # 紧急停止
```

推送失败为非致命（捕获异常后 debug 日志），不影响风控逻辑。

---

## 10. 双层熔断职责边界

### 策略级 vs 账户级

```
┌─────────────────────────────────────────────────┐
│              交易决策流程                         │
│                                                 │
│  on_bar() 开头                                  │
│    │                                            │
│    ├─▶ RiskAwareStrategy._is_paused()           │  策略级熔断
│    │      (连亏/日亏/回撤)                       │  "策略是否适应当前市场？"
│    │                                            │
│    ├─▶ RiskManager.can_trade()                  │  账户级熔断
│    │      (状态机 ACTIVE?)                       │  "账户是否还在安全线内？"
│    │                                            │
│    └─▶ 两层 OR：任一暂停 → 跳过信号生成          │
│                                                 │
│  下单前                                         │
│    ├─▶ OrderRateGuard.check()                   │  订单护栏
│    ├─▶ PortfolioHeatManager.can_open_new_position()  组合热力
│    └─▶ RiskManager.check_position()             │  仓位上限
│                                                 │
│  成交后                                         │
│    └─▶ RiskManager.record_fill()                │  驱动日亏/连亏/回撤熔断
└─────────────────────────────────────────────────┘
```

### 模式差异

| 模式 | 策略级熔断 | 账户级状态机 | 订单护栏 | 组合热力 |
|------|-----------|-------------|----------|----------|
| 回测（BacktestEngine） | ✅ | ❌ | ❌ | ❌ |
| 纸面（PaperTradingRunner） | ✅ | ✅ | ❌ | ✅ |
| 实盘（ExchangeRunnerBroker） | ✅ | ✅ | ✅ | ✅ |

- 回测模式仅用策略级熔断（BacktestEngine 不接入 RiskManager）
- 纸面/实盘同时用两层：PaperTradingRunner 先 `can_trade()` 再发单，成交后 `record_fill()`
- 订单护栏仅 exchange 模式生效（PaperBroker 自带每单仓位检查）

---

## 关键原则

### 1. 多层防御、职责分离

每一层只回答一个问题，不重复：
- 订单护栏 → 这笔单能不能下？
- 止损管理 → 持仓是否该止损？
- 策略熔断 → 策略是否适应当前市场？
- 账户状态机 → 账户是否还在安全线内？
- 组合热力 → 组合是否过热？

### 2. 状态机驱动、宁停勿亏

- RiskManager 三态状态机（ACTIVE/PAUSED/STOPPED）明确表达风控状态
- 任何熔断条件触发立即 PAUSE，不等"再观察一下"
- 急停 STOPPED 是最强保护，只能人工 reset 恢复

### 3. 防抖保护、防止绕过

- `reset()` 带 5 分钟冷却 + 1 小时 3 次限制
- 回撤跟踪（peak_equity/cumulative_pnl）reset 不清零，防止绕过年化回撤熔断线
- 策略级自动恢复最多 3 次，超过需人工介入

### 4. 安全边界、参数约束

- `StopLossConfig` 所有参数在 `__post_init__` 自动 clamp 到安全范围
- 防止 EvolutionEngine 优化出危险值（如止损过紧或过松）
- API 更新止损配置同样受安全边界约束

### 5. 告警可达、不静默失败

- 熔断/急停事件通过 AlertManager + Hermes + Telegram 三路通知
- 通知失败为非致命，不影响风控逻辑（捕获异常后 debug 日志）
- AlertManager 内置限流防抖，避免告警风暴

---

**文档状态：** ✅ 已批准  
**优先级：** 最高  
**文档版本：** v1.0  
**更新日期：** 2026-06-25

**这是系统风控的核心架构，所有开发必须遵循！**
