# 监控与告警架构设计

**文档版本：** v1.0  
**创建日期：** 2026-06-25  
**状态：** ✅ 已批准  
**优先级：** 高

---

## 目的

本文档定义系统的监控与告警架构，覆盖运行时指标采集、告警产生与限流防抖、
多通道外部派发、市场状态分类四个子系统。

**核心原则：**
- 告警系统自身必须高可用——通道故障不能拖垮交易/监控主流程，且故障必须可被察觉（兜底升级）。
- 限流防抖优先——相同告警在冷却期内去重，每个来源有每分钟上限，避免刷屏。
- 纯逻辑与外部依赖解耦——`AlertManager` / `MetricsCollector` / `MarketClassifier` 为纯逻辑、可单测；外部通道发送函数可注入。

---

## 架构概述

```
┌──────────────────────────────────────────────────────────────┐
│                      运行时数据源                              │
│   PaperTradingRunner.run()  │  RiskManager  │  OHLCV 行情     │
└──────────────┬──────────────┴───────┬───────┴────────┬────────┘
               │                      │                │
       ┌───────▼────────┐    ┌────────▼─────────┐    ┌─▼──────────────┐
       │ MetricsCollector│    │   AlertManager    │    │MarketClassifier│
       │  (指标快照采集)  │    │ (告警产生+限流防抖)│    │ (市场状态分类)  │
       └───────┬────────┘    └────────┬─────────┘    └────────────────┘
               │                      │ 派发
               │ 展平记录              │
       ┌───────▼────────┐    ┌────────▼─────────────────────────┐
       │  MetricsWriter  │    │          外部告警通道             │
       │ (写 monitor_metrics)│ │  ┌──────────┐┌────────┐┌───────┐│
       └───────┬────────┘    │  │Telegram  ││Webhook ││Email  ││
               │             │  │Channel   ││Channel ││Channel││
               ▼             │  └────┬─────┘└────┬───┘└───┬───┘│
        ┌────────────┐       └───────┼───────────┼────────┼─────┘
        │MySQL/SQLite│               ▼           ▼        ▼
        │monitor_     │         Telegram Bot  HTTP POST   SMTP
        │metrics 表   │         (无 Token 降级  (Telegram/   (默认仅
        └────────────┘          为纯日志)      Slack/自建)  CRITICAL)
                                        ▲
                                        │ 共享单例
                            ┌───────────┴────────────┐
                            │     AlertHub (单例)     │
                            │ API server + daemon 共享 │
                            └────────────────────────┘
```

**设计理念：**
- `AlertHub` 作为全局单例，API server 与 daemon 共享同一组告警通道，确保非 daemon 场景（如远程急停）也能发出通知。
- 告警通道按级别过滤（`min_level`），低级别不刷屏；通道发送失败被 `AlertManager` 隔离，全部失败时记 CRITICAL 兜底日志。
- 指标采集与落库解耦：`MetricsCollector` 累积内存快照，`MetricsWriter` 批量写入 `monitor_metrics` 表，DB 不可用时静默跳过。

---

## 1. 核心组件

### 1.1 AlertManager（告警管理器）

**源文件：** `src/monitor/alert_manager.py`

**定位：** 把风控事件与指标阈值越界转成结构化告警，含限流防抖与外部通道派发。

#### 告警级别

```python
INFO = "INFO"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
```

#### 限流配置常量

| 常量 | 默认值 | 含义 |
|------|--------|------|
| `_MAX_ALERTS` | 10000 | 内存中告警列表最大容量（环形缓冲区） |
| `_COOLDOWN_SECONDS` | 300 | 相同 `(source, message)` 的冷却时间（5 分钟） |
| `_MAX_PER_SOURCE` | 60 | 每个 source 每分钟最多告警数 |

#### 构造参数

```python
AlertManager(
    max_drawdown_alert: float = 0.10,        # 回撤告警阈值
    channels: Optional[List["AlertChannel"]] = None,  # 外部告警通道列表
    cooldown_seconds: int = _COOLDOWN_SECONDS,        # 相同消息冷却时间（秒）
    max_alerts_per_source: int = _MAX_PER_SOURCE,     # 每 source 每分钟告警上限
)
```

#### 限流防抖逻辑（`_should_throttle`）

两层过滤：

1. **去重：** 以 `f"{source}:{message}"` 为去重键，冷却期内（默认 300s）相同键直接跳过。
2. **限流：** 每个 source 维护最近 60s 内的发送时间戳列表，清理超过 60s 的记录后，若已达上限（默认 60 条/分钟）则跳过。

通过限流后更新计数与去重时间戳。

#### `emit(level, source, message) -> dict`

产生一条告警的主入口：

1. 先过 `_should_throttle`，被限流则返回空 `{}`。
2. 构造告警字典 `{time, level, source, message}`（time 为 `datetime.now().isoformat()`）。
3. 环形缓冲区：达到 `_MAX_ALERTS` 时 `pop(0)` 移除最旧告警，再 append。
4. 按级别写日志：`CRITICAL` → `logger.error`，`WARNING` → `logger.warning`，`INFO` → `logger.info`。
5. 调 `_dispatch` 派发到外部通道。
6. 返回告警字典。

#### `_dispatch(alert)` 通道派发与兜底升级

- 遍历 `self.channels`，对每个通道先 `should_send(alert["level"])` 过滤，再 `send(alert)`。
- **故障隔离：** 单个通道 `send` 抛异常被 `try/except` 捕获，仅记 `logger.error`，绝不影响告警主流程与其它通道。
- **兜底升级：** 统计本应发送的通道数 `attempted` 与失败数 `failed`；若 `attempted > 0 and failed == attempted`（全部失败），记一条 `CRITICAL` 日志 `ALERT DELIVERY FAILURE`——避免"告警系统自身静默失效"无人察觉。
- 无通道时（`channels` 为空）为 no-op，不触发兜底。

#### `check_channels_health() -> Dict[str, bool]`

通道健康自检：对每个通道发送一条 INFO 探针，返回 `{通道类名: 是否成功}`。

- 探针强制发送，绕过 `should_send` 级别过滤。
- 探针不进 `self.alerts`，也不受限流影响（直接调通道）。
- 全部失败时记 `CRITICAL` 日志 `ALERT CHANNELS UNHEALTHY`。

#### `check_risk_events(rm: RiskManager) -> List[dict]`

检查 `RiskManager` 新增事件并产生告警（增量，避免重复）：

- 维护 `_seen_event_count`，取 `rm.events` 自该计数之后的增量。
- 事件类型映射级别：`EMERGENCY_STOP` → `CRITICAL`，`PAUSE` → `WARNING`，其它 → `INFO`。
- 逐条 `emit`，返回本次新产生的告警列表。

#### `check_drawdown(total_return) -> Optional[dict]`

收益率越过回撤阈值则告警：当 `total_return <= -max_drawdown_alert` 时 `emit(CRITICAL, "drawdown", ...)`，否则返回 `None`。

#### `critical_alerts() -> List[dict]`

返回所有 `CRITICAL` 级别告警，daemon 结束时用于汇总输出。

---

### 1.2 告警通道（Alert Channels）

**源文件：** `src/monitor/alert_channels.py`

**设计要点：**
- 通道按级别过滤（`min_level`），避免低级别刷屏。
- 实际发送函数可注入（`post_fn` / `send_fn`），默认用标准库（`urllib` / `smtplib`），不新增第三方依赖；测试可注入假函数，不触网络/SMTP。
- 通道发送失败由 `AlertManager` 隔离。

#### 级别排序

```python
_LEVEL_ORDER = {INFO: 0, WARNING: 1, CRITICAL: 2}
```

#### `AlertChannel`（抽象基类）

```python
class AlertChannel(ABC):
    def __init__(self, min_level: str = WARNING): ...
    def should_send(self, level: str) -> bool:
        # 级别达到阈值才发送
        return _LEVEL_ORDER.get(level, 0) >= _LEVEL_ORDER[self.min_level]
    @abstractmethod
    def send(self, alert: dict) -> None: ...
```

#### `WebhookChannel`

Webhook 通道（POST JSON），可对接 Telegram bot / Slack / 自建 endpoint。

```python
WebhookChannel(
    url: str,
    min_level: str = WARNING,
    timeout: float = 5.0,
    post_fn: Optional[Callable[[str, dict, float], None]] = None,
)
```

- 默认发送 `_default_post`：`urllib.request` POST JSON，**含指数退避重试**（最多 3 次，间隔 `2 ** attempt` 秒）。
- `send` 直接调用 `self._post(self.url, alert, self.timeout)`。

#### `EmailChannel`

邮件通道，默认只发 CRITICAL（邮件不适合刷屏）。

```python
EmailChannel(
    smtp_config: dict,       # {host, port, username, password, use_tls, timeout}
    from_addr: str,
    to_addrs: List[str],
    min_level: str = CRITICAL,
    send_fn: Optional[Callable[[EmailMessage, dict], None]] = None,
)
```

- 默认 `_default_smtp_send`：`smtplib.SMTP(host, port, timeout)`，`use_tls`（默认 True）时 `starttls()`，有 username/password 时 `login`，最后 `send_message`。
- 邮件主题 `[level] source`，正文含 time/level/source/message。
- `smtp_config` 默认端口 587、超时 10s。

#### `TelegramChannel`

Telegram 通知通道，桥接 `AlertManager` 结构化告警到 `TelegramNotifier`。

```python
TelegramChannel(min_level: str = WARNING)
```

- 级别映射：`INFO/WARNING/CRITICAL` → `NotificationLevel` 同名成员。
- `send` 构造 HTML 文本（`<b>source</b>` + message + `<i>time</i>`），调用 `notifier.send_sync(level, text)`。
- **降级行为：** 无 Bot Token 时 `TelegramNotifier` 自动降级为纯日志输出。

---

### 1.3 AlertHub（全局单例）

**源文件：** `src/monitor/alert_hub.py`

**定位：** API server 路径使用的全局 `AlertManager` 单例，与 daemon 共享同一组告警通道，确保急停、风控事件等在非 daemon 场景下也能发出通知。

```python
from src.monitor.alert_hub import alert_manager
alert_manager.emit("CRITICAL", "api", "远程急停已触发")
```

#### 延迟初始化（`_init`）

- **延迟初始化**，避免 import 时触发网络连接。
- 通道装配：
  - 始终挂载 `TelegramChannel()`。
  - 仅当环境变量 `ALERT_WEBHOOK_URL` 非空时挂载 `WebhookChannel(url=webhook_url)`；初始化失败非致命，记 `debug` 日志。
- 创建 `AlertManager(channels=channels)`，记 `info` 日志（通道数量）。

#### `_LazyProxy`

模块级便捷属性 `alert_manager`：首次访问任意属性时才触发 `_init()`，避免在 import 阶段就建立 Telegram 连接。

#### `get_alert_manager()`

显式获取单例的函数入口，等价于触发 `_LazyProxy` 初始化。

---

### 1.4 MetricsCollector（指标采集器）

**源文件：** `src/monitor/metrics_collector.py`

**定位：** 把运行时状态（账户/风控/交易）快照成结构化指标，供监控展示与告警。纯数据采集，不依赖外部服务。

#### `snapshot(runner_result, current_prices, risk_manager, timestamp) -> dict`

采集一次指标快照：

- 从 `runner_result["statistics"]` 取 `initial_balance / current_balance / positions / total_trades / total_cost`。
- 持仓市值 = `sum(amt * current_prices.get(sym, 0.0))`，总价值 = 现金 + 持仓市值，总收益率 = `(total_value - initial) / initial`。
- 风控状态由 `_risk_metrics(rm)` 采集。

返回并 append 快照字典：

```python
{
    "timestamp": ...,
    "account": {cash, position_value, total_value, total_return, realized_pnl},
    "trades": {total, total_cost, open_lots},
    "risk": {...},
}
```

#### `_risk_metrics(rm)`

- `rm is None` → `{"enabled": False}`。
- 否则返回 `{enabled: True, state, can_trade, daily_pnl, consecutive_losses, api_failures, event_count}`。

#### `latest() / to_records()`

- `latest()`：最近一次快照。
- `to_records()`：展平为时序记录（timestamp / total_value / total_return / realized_pnl / total_trades / risk_state / consecutive_losses），供写入 DB 或导出。

---

### 1.5 MetricsWriter（指标写库）

**源文件：** `src/monitor/metrics_writer.py`

**定位：** 把 `MetricsCollector` 的展平时序写入 `monitor_metrics` 表，供 Grafana 读取，打通"内存指标 → DB"链路。

```python
TABLE = "monitor_metrics"
COLUMNS = [
    "timestamp", "total_value", "total_return", "realized_pnl",
    "total_trades", "risk_state", "consecutive_losses",
]
```

- `__init__(db=None)`：依赖 `DatabaseManager`，默认全局实例，可注入便于单测。
- `_insert_query()`：参数化 SQL（`%s` 占位），列名为静态常量、非用户输入，无注入风险。
- `write_records(records)`：写入一批展平记录，返回写入条数；**空输入返回 0、不触库**。
- `write_collector(collector)`：直接写入采集器累积的全部快照。

---

### 1.6 MarketClassifier（市场状态分类器）

**源文件：** `src/monitor/market_classifier.py`

**定位：** 基于近 20 天 OHLCV 数据，综合 EMA 趋势、ADX 趋势强度、布林带波动率三类指标，将市场状态归类为四种模式并给出策略推荐。

#### `MarketState` 枚举

| 状态 | 含义 | 推荐策略 |
|------|------|----------|
| `TRENDING_UP` | 上升趋势 | ma, rsi, buyhold |
| `TRENDING_DOWN` | 下降趋势 | buyhold, ma |
| `RANGING` | 横盘震荡 | grid, ma, rsi |
| `VOLATILE` | 高波动 | rsi, buyhold |

#### 指标计算（内部辅助函数）

- `_calc_ema(series, span)`：EMA（兼容旧版 pandas）。
- `_calc_adx(high, low, close, period=14)`：基于 **Wilder 平滑** 计算 ADX(14)，数据不足返回 0.0。
- `_calc_bollinger_width(close, period=20, num_std=2.0)`：布林带宽度 = `(上轨 - 下轨) / 中间价`，数据不足返回 0.0。

#### 可参数化阈值（类属性默认值）

| 阈值 | 默认值 | 含义 |
|------|--------|------|
| `ADX_TRENDING_THRESHOLD` | 25.0 | ADX 高于此值视为有趋势 |
| `ADX_RANGING_THRESHOLD` | 20.0 | ADX 低于此值视为横盘 |
| `BB_WIDTH_VOLATILE` | 0.05 | 布林带宽/中间价 > 5% 为高波动 |
| `BB_WIDTH_RANGING` | 0.02 | 布林带宽/中间价 < 2% 为横盘 |
| `EMA_SLOPE_UP` | 0.002 | EMA 斜率上行阈值 |
| `EMA_SLOPE_DOWN` | -0.002 | EMA 斜率下行阈值 |

所有阈值均可在 `__init__` 中参数化覆盖。

#### 分类判定逻辑（`_classify_with_intermediates`，优先级从高到低）

1. 高波动（`bb_width > BB_WIDTH_VOLATILE`）→ `volatile`（最高优先级）。
2. 强趋势（`adx > ADX_TRENDING_THRESHOLD`）：
   - 斜率上行且 `EMA20 > EMA50` → `trending_up`。
   - 斜率下行且 `EMA20 < EMA50` → `trending_down`。
   - 方向模糊时看 EMA 排列定上/下。
3. 低趋势强度（`adx < ADX_RANGING_THRESHOLD`）→ `ranging`。
4. 中等强度：`bb_width < BB_WIDTH_RANGING` → `ranging`，否则 → `volatile`。

数据不足（`len(df) < lookback`）时默认返回 `ranging`。

#### 模块级便捷函数

- `classify_market(df, lookback=20)`：委托默认 `_default_classifier` 实例。
- `get_strategy_recommendation(market_state)`：返回 `{state, strategies, action}`。
- `classify_and_recommend(df, lookback, classifier=None)`：一站式分类 + 推荐，只计算一次 ADX/BB/EMA，避免重复计算，返回结果含 `details`（ema20 / adx / bb_width）。

---

## 2. 告警流程

### 2.1 一次告警的端到端流转

```
 触发源                  AlertManager.emit()                    外部通道
 ┌─────────┐   level,    ┌────────────────────┐   should_send    ┌─────────┐
 │ risk事件 │  source,   │ 1. _should_throttle │ ───过滤级别──▶ │Telegram │
 │ 回撤越界 │  message   │    去重+限流        │                 │Webhook  │
 │ API急停  │ ─────────▶ │ 2. 构造 alert dict   │                 │Email    │
 └─────────┘            │ 3. 环形缓冲区 append │                 └────┬────┘
                        │ 4. logger 按级别输出 │                      │
                        │ 5. _dispatch 派发    │      失败隔离 try/except
                        └─────────┬──────────┘                      │
                                  │ 全部失败 → CRITICAL 兜底日志      │
                                  ▼                                  ▼
                            返回 alert dict                    用户收到通知
```

### 2.2 daemon 内的告警调用（`scripts/run_paper_trading_daemon.py`）

daemon 通过 `AlertHub` 单例共享告警通道：

```python
self.alert_mgr = get_alert_manager()  # 共享单例（Telegram + 可选 Webhook）
```

每根 bar 处理（`_on_bar_inner`）中，**走 AlertManager 的两类告警**：

```python
# 1. 风控事件增量告警（EMERGENCY_STOP→CRITICAL, PAUSE→WARNING, 其它→INFO）
self.alert_mgr.check_risk_events(self.risk)

# 2. 回撤越界告警
total_ret = self.runner.realized_pnl / self.args.initial
self.alert_mgr.check_drawdown(total_ret)
```

daemon 结束（`_finish`）时汇总输出 CRITICAL 告警数量：

```python
crits = self.alert_mgr.critical_alerts()
if crits:
    print(f"[ALERT] {len(crits)} CRITICAL alerts")
```

> **注意：** daemon 中部分通知（闪崩保护、Portfolio Heat 超阈值、远程急停、daemon 启停）直接调用 `notifier.send_*_sync()`，**不经过 `AlertManager`**，因此不受限流防抖与级别过滤约束。这是有意为之——这些场景属于即时人工介入通知。

### 2.3 API server 的告警调用（`src/api/admin_routes.py`）

远程急停端点通过 `AlertHub` 单例发告警，并写入信号文件通知 daemon：

```python
risk_manager.emergency_stop("remote emergency-stop via API")

from src.monitor.alert_hub import alert_manager
alert_manager.emit(
    "CRITICAL", "api",
    f"远程急停已触发: {prev_state} -> STOPPED (via API)",
)

# 写入信号文件，daemon 下根 bar 检测后停止
signal_file = _Path("data/.emergency_stop")
signal_file.write_text("1", encoding="utf-8")
```

daemon 在每根 bar 开始时检查该信号文件（`_check_emergency_stop_signal`），存在则 `emergency_stop` 并删除文件。

---

## 3. 配置说明

### 3.1 AlertManager 限流参数

| 参数 | 默认值 | 配置方式 | 说明 |
|------|--------|----------|------|
| `cooldown_seconds` | 300 | 构造参数 | 相同 `(source, message)` 冷却时间 |
| `max_alerts_per_source` | 60 | 构造参数 | 每 source 每分钟告警上限 |
| `max_drawdown_alert` | 0.10 | 构造参数 | 回撤告警阈值（10%） |
| `_MAX_ALERTS` | 10000 | 模块常量 | 内存告警列表环形缓冲区上限 |

`AlertHub` 单例使用上述默认值构造 `AlertManager`。

### 3.2 通道配置

| 通道 | 启用条件 | `min_level` 默认 | 关键参数 |
|------|----------|------------------|----------|
| `TelegramChannel` | `AlertHub` 始终挂载 | `WARNING` | Bot Token 来自 `TelegramNotifier` 内部配置；无 Token 降级为纯日志 |
| `WebhookChannel` | 环境变量 `ALERT_WEBHOOK_URL` 非空 | `WARNING` | `url`、`timeout=5.0`、3 次指数退避重试 |
| `EmailChannel` | 需代码显式实例化并传入 | `CRITICAL` | `smtp_config`（host/port/use_tls/timeout/username/password）、`from_addr`、`to_addrs` |

> 当前 `AlertHub` 默认仅装配 `TelegramChannel` + 可选 `WebhookChannel`；`EmailChannel` 未被 `AlertHub` 默认挂载，需在自定义场景中手动构造并注入。

### 3.3 环境变量

| 变量 | 作用 | 缺省 |
|------|------|------|
| `ALERT_WEBHOOK_URL` | 启用 Webhook 通道的目标 URL | 空（不挂载 Webhook） |

### 3.4 MarketClassifier 阈值

所有阈值均可在 `MarketClassifier.__init__` 参数化覆盖，类属性默认值见上文 1.6 节表格。

### 3.5 指标落库

- 表名：`monitor_metrics`
- 列：`timestamp, total_value, total_return, realized_pnl, total_trades, risk_state, consecutive_losses`
- daemon 启动时构造 `MetricsWriter()`（除非 `--no-db`）；DB 不可用时 `writer=None`，落库静默跳过。

---

## 4. 与其他模块的集成关系

### 4.1 与 RiskManager 的集成

- `AlertManager.check_risk_events(rm)` 增量读取 `RiskManager.events`（deque，上限 10000）产生告警。
- `MetricsCollector._risk_metrics(rm)` 采集风控状态（state / can_trade / daily_pnl / consecutive_losses / api_failures / event_count）写入指标快照。
- daemon 每根 bar 后调用 `check_risk_events`，确保 PAUSE / EMERGENCY_STOP 等事件即时告警。

### 4.2 与 PaperTradingRunner / PaperBroker 的集成

- `MetricsCollector.snapshot()` 接收 `PaperTradingRunner.run()` 结果，计算账户/交易指标。
- daemon 每根 bar 后将采集器快照写入 `monitor_metrics`，写完清空 `collector.snapshots` 避免重复写入。
- 回撤告警基于 `runner.realized_pnl / initial` 计算收益率。

### 4.3 与 TelegramNotifier 的集成

- `TelegramChannel.send` 桥接到 `TelegramNotifier.send_sync(level, text)`，级别一一映射。
- daemon 中闪崩保护、Portfolio Heat 超阈值、远程急停、daemon 启停等通知**直接**调用 `notifier.send_critical_sync / send_warning_sync / send_info_sync`，绕过 `AlertManager`。
- 无 Bot Token 时 `TelegramNotifier` 自动降级为纯日志，通道不报错。

### 4.4 与 API server 的集成

- API server（FastAPI `admin_routes`）通过 `AlertHub` 单例与 daemon 共享同一组告警通道。
- 远程急停：API 端 `alert_manager.emit("CRITICAL", "api", ...)` + 写信号文件 `data/.emergency_stop`；daemon 轮询该文件实现跨进程急停联动。

### 4.5 与数据库的集成

- `MetricsWriter` 依赖 `DatabaseManager`（`src.utils.database.db`），通过 `execute_many` 批量写入。
- DB 可注入，便于单测不连真实库；daemon 运行时若 DB 不可用，落库静默跳过（`logger.debug`），不影响交易/监控主流程。

### 4.6 MarketClassifier 的集成边界

- `MarketClassifier` 为纯分析工具，基于 OHLCV DataFrame 输出市场状态与策略推荐。
- 当前监控告警链路未自动调用 `MarketClassifier`；它作为辅助决策模块，供策略选择与市场研判使用，与 `AlertManager` 无直接耦合。

---

## 关键原则

### 1. 告警系统自身高可用

- **故障隔离：** 单个通道失败不影响主流程与其它通道。
- **兜底升级：** 本应发送的通道全部失败时记 `CRITICAL` 日志，避免静默失效。
- **健康自检：** `check_channels_health` 提供主动探针，全部失败时升级告警。

### 2. 限流防抖优先

- 相同 `(source, message)` 冷却去重（默认 5 分钟）。
- 每 source 每分钟上限（默认 60 条），超限静默丢弃。
- 环形缓冲区限制内存（默认 10000 条）。

### 3. 纯逻辑与外部依赖解耦

- `AlertManager` / `MetricsCollector` / `MarketClassifier` 为纯逻辑、可单测。
- 通道发送函数、DatabaseManager 均可注入，测试不触网络/SMTP/真实库。

### 4. 跨进程共享单例

- `AlertHub` 让 API server 与 daemon 共享同一组告警通道，确保任意入口的急停/风控事件都能发出通知。

---

**文档状态：** ✅ 已批准  
**优先级：** 高  
**文档版本：** v1.0  
**更新日期：** 2026-06-25
