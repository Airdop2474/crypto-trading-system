# 项目记忆

## 系统架构
- 后端：Python 3.13，FastAPI 暴露 REST API
- 前端：Next.js 16 + React 19 + Tailwind 4 + SWR 数据获取
- 策略引擎：事件驱动 bar-by-bar 回测，RiskAwareStrategy 基类
- 缓存：Redis（可用时）+ 内存回退

## 策略注册表 (12个)
grid | rsi | ma | buyhold | donchian | structure | supertrend | reversal | priceaction | bollinger | macd | composite

## 关键设计决策
- 所有策略继承 RiskAwareStrategy（熔断：连亏3次/日亏2%/回撤15%）
- 前端 SWR 配置：30s 刷新、3次重试、5s 间隔
- API 层无数据库依赖，数据来自 PaperTrading 引擎内存快照
- `service.get_state()` lazy 构建，进程内只跑一次；startup hook 用 `asyncio.to_thread` 预热避免阻塞事件循环
- `_state` 模块级变量；`POST /admin/refresh-state` 可重置（限流 2/分钟）
- CSP 头允许内联 script/style + WebSocket + 字体（Next.js hydration 需要）
- **composite 策略注意**：`RiskAwareStrategy` 的 `_adx_*` 是类级变量（共享 bug），CompositeTrend 改用实例级 `_i_adx_*` 修复

## API 端点全表
### 行情与账户
- `GET /health` / `GET /health/detailed`（WS/缓存状态）
- `GET /account/summary` / `GET /account/risk-metrics`（max_dd/sharpe/sortino/vol）
- `GET /market/tickers` / `WS /ws/tickers`（首条消息认证）

### 策略与持仓
- `GET /strategies` / `PATCH /strategies/:id/status` / `POST /strategies/create-grid`
- `GET /positions` / `GET /positions/history`（平仓交易合并去重）
- `GET /assets` / `GET /orders?limit=&offset=`（分页 + stats 全量聚合）

### 多策略
- `GET /multi/summary` / `GET /multi/details` / `GET /multi/strategy/:id`

### 分析
- `GET /analytics/pnl-history` / `strategy-performance`
- `GET /analytics/pnl-distribution?bins=`（直方图 + 胜率/盈亏比）
- `GET /analytics/win-rate-trend?window=`（滚动胜率）
- `GET /analytics/strategy-correlation`（8 策略 Pearson 矩阵）

### 风险
- `GET /risk/drawdown-curve` / `GET /risk/status`（RiskManager 状态机）

### AI Agent
- `POST /agent/analyze`（5 种：backtest/trade_attribution/risk_checklist/param_sensitivity/weekly_review）
- `GET /agent/audit-logs` / `GET /agent/adoption-rate`

### 管理
- `POST /admin/refresh-state`（重建 Paper Trading state）

## 前端路由全表（12 个）
- `/` 总览（账户卡 + 风险卡 + 权益曲线 + 行情 + 策略跑分 + 多策略）
- `/grid` `/price-action` 网格与价格行为策略列表
- `/strategy/[id]` 策略详情（动态路由，5 卡 + 持仓/平仓/流水三表）
- `/positions` 持仓（+平仓历史 + 盈亏分布）
- `/orders` 订单（分页 + CSV 导出）
- `/analytics` 分析（PnL + 胜率趋势 + 回撤 + 相关性矩阵）
- `/risk` 风险管理（6 卡 + 回撤曲线 + 风控状态机）
- `/agent` AI 分析中心（5 种分析 + 审计日志 + 采纳率）
- `/system` 系统状态（WS/缓存 + 重建引擎按钮）
- `/settings` 设置（UI 偏好 localStorage）

## 前端约定
- 12 种策略元信息统一在 `lib/strategy-meta.ts`（标签/配色/图标），勿在各组件重复映射
- 新增策略时必须同步更新三个文件：`lib/types.ts`（StrategyType）、`lib/strategy-meta.ts`、`lib/param-labels.ts`
- `param-labels.ts` 同时保留 camelCase 和 snake_case 双写，兼容前后端不同命名风格
- CSV 导出用 `lib/csv.ts` 的 `exportCsv` + `<ExportButton>` 组件
- 主题：`ThemeProvider` + `theme-toggle.tsx`（深/浅/系统循环切换），CSS 用 `.dark` 选择器
- `@base-ui/react` 的 Select/DropdownMenu 用 `render` prop 而非 Radix 的 `asChild`；`onValueChange` 类型是 `(value: string | null) => void`

## 关键代码位置
- 后端 API：`src/api/app.py`（路由）+ `src/api/service.py`（业务映射，700+ 行）
- 后端指标：`src/backtest/metrics.py`（PerformanceMetrics，equity_curve 列名是 `time` 不是 `timestamp`）
- 风控：`src/execution/risk_manager.py`（ACTIVE/PAUSED/STOPPED 状态机）
- AI Agent：`src/agent/analyzer.py` + `audit_log.py`
- 前端 API 边界：`frontend/lib/api.ts`（唯一与后端对话的层）
- 前端类型契约：`frontend/lib/types.ts`

## 待办（剩余 7 项，按优先级）
- 🔴 多 worker 共享 state（当前 `--workers 4` 会跑 4 份 Paper Trading）
- 🔴 AI Agent 接真实 LLM（当前是规则引擎）
- 🔴 实盘交易路径完整化（IP 白名单/权限收紧/kill switch）
- 🔴 数据源从离线 CSV 切实时（TimescaleDB + 增量运行）
- 🟣 Prometheus `/metrics` 端点
- 🟣 CI/CD（GitHub Actions：lint + test + build）
- 🟣 审计日志改 SQLite/Postgres（当前 JSON 文件 O(n) 扫描）

