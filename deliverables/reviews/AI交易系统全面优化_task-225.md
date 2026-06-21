# AI 交易系统全面优化方案

> 三路并行审查（代码质量 A / 性能 B / 生产就绪 C）的综合结论。
> 共 25 个优化任务，按 5 个阶段组织。

---

## Task 1：修复已知缺陷（P0，预计 30 分钟）

上次代码审查已确认但未修复的 6 个问题，全部独立可并行：

| # | 问题 | 文件 | 修复方向 |
|---|------|------|----------|
| 1.1 | `__init__.py` 重复 `__all__` 覆盖导出 | `src/execution/__init__.py` L34-62 | 删除第二个重复的 import + `__all__` 块 |
| 1.2 | 限价单成交额外施加滑点 | `src/execution/paper_broker.py` L120-143 | `_fill_order()` 中限价单跳过滑点：`actual_price = exec_price` |
| 1.3 | `MultiStrategyRunner.process_bar()` 引用不存在的 `_last_pending` | `src/execution/multi_runner.py` L246-249 | 在 `__init__` 增加 `self._pending_map`，`process_bar` 中使用它传递 pending signal |
| 1.4 | 守护进程序列化丢失 `limit_price` | `scripts/run_paper_trading_daemon.py` L57-74 | `_ser_pending` 包含 `limit_price`，`_deser_pending` 恢复 |
| 1.5 | Agent 端点缺少 `param_sensitivity` | `src/api/app.py` L225-269 | 添加 `elif body.task == "param_sensitivity"` 分支 |
| 1.6 | `websockets` 未列入 requirements.txt | `requirements.txt` | 添加 `websockets>=12.0` |

---

## Task 2：算法性能热点消除（P0，预计 2 小时）

策略层存在严重的 O(n^2) 性能问题，每根 bar 对全量历史重算：

### 2.1 RSI 增量计算
- **文件**: `src/strategy/rsi_momentum.py` L96-114
- **问题**: `_compute_rsi()` 每根 bar 对全量 close 做 `ewm()` → O(n) per bar → O(n^2) 总计
- **修复**: 改为 Wilder 平滑增量形式，维护 `_avg_gain` / `_avg_loss` 两个标量，每根 bar O(1) 更新
- **验证**: 同一数据集增量 vs 全量对比，容差 1e-6

### 2.2 RSI 趋势过滤 EMA 增量
- **文件**: `src/strategy/rsi_momentum.py` L138
- **问题**: 趋势过滤每根 bar 全量 `ewm(span=50)` → 又一个 O(n^2)
- **修复**: 参照 `grid_trading.py` 的 `_update_ema()` 模式，增量缓存 EMA

### 2.3 Grid ATR 滑动窗口
- **文件**: `src/strategy/grid_trading.py` L227-260
- **问题**: `_atr_pct()` 每根 bar 对全量 high/low/close 做 numpy 运算，但只用最后 14 个 TR
- **修复**: 维护长度 14 的 `deque` ring buffer + running sum，每根 bar O(1)
- **实现**: `_init_state()` 中增加 `self._tr_window: deque(maxlen=period)` + `self._tr_sum: float`

### 2.4 单元测试验证
- 对 RSI 和 Grid 策略分别添加性能基准测试：10000 bar 数据集运行时间 < 1 秒（当前可能 > 30 秒）

---

## Task 3：安全与韧性加固（P1，预计 2 小时）

### 3.1 Daemon 接入 AlertManager
- **文件**: `scripts/run_paper_trading_daemon.py`
- **问题**: `RiskManager.events` 仅在内存累积，不触发任何外部告警
- **修复**: `__init__` 创建 `AlertManager`，`_on_bar` 中风控状态变化后调用 `alert_manager.check_risk_events()`

### 3.2 Daemon 信号处理与优雅退出
- **文件**: `scripts/run_paper_trading_daemon.py`
- **问题**: `_run_live` 使用 `time.sleep()` 循环，未注册 SIGTERM/SIGINT
- **修复**: 注册信号处理器 → `self._shutdown_requested = True` → 退出前 `_checkpoint()`

### 3.3 API 基础认证
- **文件**: `src/api/app.py`
- **问题**: 所有 16 个端点无认证、无速率限制
- **修复**: FastAPI `Depends` 模式，Bearer Token 从 `.env` 读取；只读 GET 保持公开，POST/PATCH 要求认证

### 3.4 密码参数化
- **文件**: `docker-compose.yml` L42-43, `.env.example`
- **问题**: Grafana admin/admin、DB password 硬编码
- **修复**: 改为 `${GRAFANA_ADMIN_PASSWORD:-admin}` + `${POSTGRES_PASSWORD:-changeme}`

### 3.5 数据下载重试
- **文件**: `src/data/exchange.py` L86-117
- **问题**: `fetch_ohlcv` 网络失败直接抛异常，无重试
- **修复**: 指数退避重试 3 次（1s/2s/4s），仅对 `ccxt.NetworkError` + `ccxt.ExchangeNotAvailable`

### 3.6 Redis 故障自动重连
- **文件**: `src/utils/cache.py`
- **问题**: Redis 故障后永久回退到内存缓存，不恢复
- **修复**: 暂时回退 + 每 30s `ping()` 健康检查，恢复后自动切回 Redis

### 3.7 preflight 检查补全
- **文件**: `scripts/preflight_check.py`
- **修复**: `check_core_deps` 模块列表添加 `"websockets"`

---

## Task 4：代码架构整理（P2，预计 3 小时）

### 4.1 提取 CircuitBreaker Mixin
- **文件**: `src/strategy/grid_trading.py` L307-338, `src/strategy/simple_ma.py` L138-166, `src/strategy/rsi_momentum.py` L157-185
- **问题**: 熔断逻辑（consecutive_losses 追踪、daily_pnl 重置、PAUSE 触发）在 3 个策略中近乎复制粘贴
- **修复**: 创建 `src/strategy/mixins.py` → `CircuitBreakerMixin`，3 个策略继承

### 4.2 集中常量定义
- **问题**: `WATCH_SYMBOLS` 重复定义在 `ws_feed.py` L36 和 `market.py` L16；`LEGACY_TAG` 重复在 `engine.py` L31 和 `paper_trading_runner.py` L69
- **修复**: 创建 `src/api/constants.py`（WATCH_SYMBOLS）、`src/strategy/base.py` 添加 `LEGACY_TAG`

### 4.3 提取 Pydantic schemas
- **文件**: `src/api/app.py` L165-225
- **问题**: Pydantic 模型内联在路由文件中
- **修复**: 创建 `src/api/schemas.py`，移出 `StatusPatch`、`CreateGridRequest`、`AnalyzeRequest`

### 4.4 完善 RunnerBroker Protocol
- **文件**: `src/execution/paper_trading_runner.py` L49-63
- **问题**: Protocol 未声明 `check_pending_orders` 和 `pending_orders`，runner 用 `hasattr` 检查
- **修复**: Protocol 增加可选方法声明，移除 `hasattr` 守卫

### 4.5 PaperTradingRunner 公共 API
- **文件**: `src/execution/paper_trading_runner.py`, `src/execution/multi_runner.py`
- **问题**: `MultiStrategyRunner.run()` 直接操作 runner 的私有属性（`lots`、`realized_pnl`、`_build_result()`）
- **修复**: 添加公共 `reset_state()` 和 `build_result()` 方法

### 4.6 共享测试 fixtures
- **文件**: `tests/unit/test_grid_trading.py` L21-37, `tests/unit/test_paper_trading_runner.py` L23-54, `tests/unit/test_multi_runner.py` L32-64
- **问题**: `make_data()`、`make_bar()`、`make_df()`、`ScriptedStrategy` 在多处重复定义
- **修复**: 移至 `tests/conftest.py` 作为 pytest fixtures

### 4.7 共享 DataFrame hash 工具
- **文件**: `src/data/downloader.py` L202-215, `src/data/quality_checker.py` L374-397
- **问题**: SHA256 hash 计算逻辑重复
- **修复**: 提取到 `src/utils/hash.py`

### 4.8 `_build_state()` 消除双重运行
- **文件**: `src/api/service.py` L59-164
- **问题**: 单策略路径和多策略路径各跑一次完整的 Paper Trading，且多策略已包含 Grid
- **修复**: 从多策略运行结果中提取 Grid 策略数据作为单策略路径数据，省去一次完整运行

---

## Task 5：前端与体验增强（P2，预计 1.5 小时）

### 5.1 SWR 全局配置与自动刷新
- **文件**: `frontend/lib/api.ts` 或新建 `frontend/lib/swr-config.ts`
- **问题**: 账户/策略/订单数据永不自动刷新，仅组件挂载时拉取一次
- **修复**: `refreshInterval: 30000`、`dedupingInterval: 2000`、`revalidateOnFocus: true`

### 5.2 WebSocket state 批量更新
- **文件**: `frontend/hooks/use-tickers-ws.ts` L75-77
- **问题**: 每条 WS 消息（每秒一次）替换整个 tickers 数组 → React 全树重渲染
- **修复**: `useRef` 存储 + `requestAnimationFrame` 每 100ms 合并一次批量更新

### 5.3 WS 断线回退优化
- **文件**: `frontend/hooks/use-tickers-ws.ts` L83-95
- **问题**: 断线期间 REST 回退仅在 onclose 触发一次 + 10s 定时器，数据可能过时 10s
- **修复**: 断线期间持续以 5s 间隔轮询 REST，WS 恢复后自动停止

---

## 依赖关系

```
Task 1 (缺陷修复)     → 无前置，全部独立
Task 2 (性能热点)     → 无前置，全部独立
Task 3 (安全韧性)     → Task 1.1 完成后做 3.1（MultiStrategyRunner 需可导入）
Task 4 (架构整理)     → Task 1 完成后开始；4.8 依赖 Task 2
Task 5 (前端增强)     → 独立
```

**推荐执行顺序**: Task 1 → Task 2 → Task 3 → Task 4 → Task 5

---

## 被否决的替代方案

| 方案 | 否决原因 |
|------|----------|
| 拆分 `TradingAnalyzer` (890行) 为 5 个文件 | 当前仅 1 个调用者 (`app.py`)，Facade 模式足够；拆分增加复杂度但收益有限 |
| 全量 async 改造 API 端点 | FastAPI 的同步端点在线程池中运行性能可接受；全量改造工作量大且引入新竞态风险 |
| 用 `ccxt.async_support` 替换同步 ccxt | 项目当前无 async 数据管线，改造范围过大，建议仅在下载器中用 ThreadPoolExecutor |
| 删除 `.claude/plans/` 旧文件 | 属于文档清理范畴，不影响功能，不纳入本技术方案 |

---

## 关键文件清单

| 文件 | 重要性 |
|------|--------|
| `src/execution/__init__.py` | P0 缺陷：重复 `__all__` 阻断多策略导出 |
| `src/strategy/rsi_momentum.py` | P0 性能：最大 O(n^2) 热点 |
| `src/execution/paper_broker.py` | P0 缺陷：限价单滑点错误 |
| `scripts/run_paper_trading_daemon.py` | P1 安全：缺 AlertManager + 信号处理 |
| `src/api/service.py` | P2 架构：双重运行 + 全局状态 |
