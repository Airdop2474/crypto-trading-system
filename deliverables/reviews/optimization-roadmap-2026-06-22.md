# 系统优化清单 · 全面盘点

> 生成日期：2026-06-22
> 范围：前后端代码、架构、安全、可观测性、数据、工程化、运维
> 已排除：本次会话已修复的 7 项（见 `frontend-backend-gap-fix-2026-06-22.md`）

---

## 怎么读这份清单

按"价值密度 × 实施难度"四象限排序，不是按优先级数字。先看高价值低成本的"快赢"，再看高价值高成本的"硬骨头"。

每项标注：
- **价值**：用户体验 / 系统健壮性 / 工程效率 / 安全
- **难度**：S（< 1h）/ M（半天）/ L（1-2 天）/ XL（多天）

---

## 🟢 快赢区（高价值 · 低成本）

### 1. `/risk` 风险管理页面（报告 P1 未做）

**价值**：报告里 P1 第 4 项，文档反复强调 "multi-layer risk controls"，但前端完全没有可视化入口

**实施**：
- 新建 `frontend/app/risk/page.tsx`
- 后端 `src/execution/risk_manager.py` 已有完整风控逻辑（连亏熔断 / 日亏 / 回撤），需暴露 `/risk/status` 端点
- 前端展示：最大回撤曲线、当前风险敞口、风控状态（正常/警告/熔断）、止损配置
- 数据源：复用 `service.get_state()["result"]["statistics"]` + `RiskManager` 状态

**难度**：M

---

### 2. 总览页加风险指标看板（报告 P2）

**价值**：用户打开仪表盘第一眼就想看"最大回撤 / 夏普 / 波动率"，目前只有 PnL

**实施**：
- 在 `app/page.tsx` 加一行 4 张卡：Max Drawdown / Sharpe / Sortino / Volatility
- 后端 `src/backtest/metrics.py` 已算这些指标，加 `/account/risk-metrics` 端点透出
- 前端 `lib/api.ts` 加 `getRiskMetrics()` + `RiskMetrics` 类型

**难度**：S-M

---

### 3. 数据导出 CSV（报告 P2）

**价值**：用户做复盘/对外汇报时刚需。当前所有页面只能看不能下载

**实施**：
- 写一个共用 `exportCsv(filename, rows, columns)` 工具函数（纯前端 Blob 实现，无后端依赖）
- 订单页、持仓页、PnL 历史页各加一个"导出 CSV"按钮
- 用当前 SWR 缓存的数据生成，导出当前视图

**难度**：S（半天搞定 3 个页面）

---

### 4. CSP 头过于严格（安全/功能隐患）

**问题**：`app.py:65` 设 `Content-Security-Policy: default-src 'self'`，这会阻断：
- Next.js 内联 script（hydration 会挂）
- Google Fonts（`next/font/google` 实际走 `@font-face` 自托管，OK；但若有人加 CDN 字体会挂）
- WebSocket（`connect-src` 默认继承 `default-src`，只允许同源，前端连 `ws://localhost:8000` 会被拦）

**实施**：改为
```
default-src 'self';
script-src 'self' 'unsafe-inline' 'unsafe-eval';
style-src 'self' 'unsafe-inline';
connect-src 'self' ws://localhost:8000 wss://localhost:8000 http://localhost:8000;
img-src 'self' data:;
font-src 'self' data:;
```
生产环境收紧 `'unsafe-eval'`，dev 保留。

**难度**：S

---

### 5. CORS origins 从 env 读

**问题**：`app.py:52-58` 写死 4 个 localhost URL，生产部署必须改代码

**实施**：`config.py` 加 `CORS_ORIGINS: List[str]`，从 `os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")` 读

**难度**：S

---

### 6. `mock-data.ts` 清理

**问题**：`frontend/lib/mock-data.ts` 已切换到真实 API 后仍在仓库（200+ 行），新人会困惑"到底用 mock 还是真实"

**实施**：删除 `lib/mock-data.ts`，或挪到 `frontend/lib/__mocks__/` 仅供测试用。先 grep 一遍无引用再删

**难度**：S

---

### 7. 日志文件入 `.gitignore`

**问题**：仓库里已有 `start.log` / `start.err` / `logs/*.log`（15 个 log 文件）被提交

**实施**：
- `.gitignore` 加 `logs/`、`*.log`、`start.log`、`start.err`
- `git rm --cached` 移除已跟踪的日志

**难度**：S

---

## 🟡 中价值 · 中成本

### 8. 策略详情页（报告 P2）

**价值**：点击网格卡片 / 价格行为卡片应能进入详情，看每格成交、信号历史、参数

**实施**：
- `frontend/app/grid/[id]/page.tsx` — 调用 `api.getMultiStrategy(id)`（已在 P0-2 修了类型），展示 trade_history / signals / open_lots
- `frontend/app/price-action/[id]/page.tsx` — 同上，覆盖 Donchian/Structure/SuperTrend/Reversal
- 卡片加 `<Link href={`/grid/${id}`}>`

**难度**：M

---

### 9. 持仓页补"平仓历史 / 交易时间线 / 盈亏分布"（报告 P2）

**价值**：当前持仓页只有"现在"，看不到"过去"

**实施**：
- 后端复用 `closed_trades` 数据（`MultiStrategyResult.closed_trades`），加 `/positions/history` 端点
- 前端三张新卡：
  - 平仓历史表（时间 / 入场价 / 平仓价 / 盈亏 / 持有时长）
  - 交易时间线（横向 timeline，标注每笔开平仓点）
  - 盈亏分布直方图（用 recharts BarChart）

**难度**：M-L

---

### 10. 分析页加"胜率趋势 / 回撤曲线 / 相关性矩阵"（报告 P2）

**价值**：当前分析页只有 PnL 曲线，缺多维分析视角

**实施**：
- 胜率趋势：滑动窗口（如 20 笔）算胜率，折线图
- 回撤曲线：从权益曲线派生 `drawdown = (equity - cummax) / cummax`，AreaChart
- 相关性矩阵：8 策略日 PnL 两两 Pearson 相关，热力图（recharts 不直接支持，可用 SVG 手写或加 `react-heatmap-grid`）

**难度**：L

---

### 11. `/system` 系统状态页（报告 P2）

**价值**：`/health/detailed` 已有数据，但只能 curl 看。运维需要可视化

**实施**：
- `frontend/app/system/page.tsx` — 调用 `api.getHealthDetailed()`，5 秒自动刷新
- 展示：WS 连接状态（绿/红）、WS 客户端数、缓存后端、缓存可用性、API 速率（可用 SlowAPI 的统计）
- 加一行"如果 ws_clients=0 且 ws_connected=false，提示用户检查 Binance 连接"

**难度**：S-M

---

### 12. `/settings` 设置页（报告 P2）

**价值**：当前所有配置都改 `.env`，非技术用户无法操作

**实施**：
- 至少做 UI 偏好部分（暗色/浅色、刷新频率、默认页面、每页条数）—— 纯前端 localStorage
- API 密钥管理部分需谨慎：前端不应直接保存密钥，应让用户填后调后端 `/settings/api-key` 端点加密存储
- 通知配置（Telegram/Email）调后端

**难度**：M（UI 偏好部分 S，密钥管理部分 L）

---

### 13. `get_state()` 阻塞事件循环（架构问题）

**问题**：`service.py:234` `get_state()` 在首次请求时同步跑 Paper Trading（CPU 密集，8 个策略全跑），FastAPI 是 async 框架，同步阻塞会让事件循环卡死，期间所有其他请求（包括 WebSocket 心跳）都阻塞

**实施**：
- 选项 A：`app.py` startup hook 里 `await asyncio.to_thread(service.get_state)` 预热
- 选项 B：所有端点改 `async def`，内部 `await run_in_threadpool(service.get_state)`
- 选项 C：用 `run_in_executor` 包装

**难度**：M

---

### 14. `_state` 无热刷新机制

**问题**：一旦 `_state` 构建，数据更新后只能重启服务

**实施**：
- 加 `POST /admin/refresh-state` 端点（需 admin token），重置 `_state = None`，下次请求重建
- 或加文件 watcher，监听 `data/raw/*.csv` 变化自动失效

**难度**：M

---

## 🔴 高价值 · 高成本（硬骨头）

### 15. `_state` 多 worker 不共享

**问题**：`_state` 是模块级变量，`uvicorn --workers 4` 时每个 worker 各跑一次 Paper Trading，4 倍内存 + 4 倍 CPU

**实施**：
- 短期：限制单 worker（`--workers 1`），文档说明
- 长期：把完整 state 序列化到 Redis（不仅摘要），所有 worker 共享；或拆出独立 Paper Trading worker 进程，API 只读 Redis

**难度**：XL

---

### 16. AI Agent 接真实 LLM

**现状**：`analyzer.py` 是纯规则引擎（local-analyzer），输出模板化。`audit_log.py` 的 `tokens_used` 永远是 0

**实施**：
- `.env.example` 已有 `OPENAI_API_KEY` / `OPENAI_MODEL` 占位
- `analyzer.py` 加 `LLMAnalyzer` 子类，调用 OpenAI/Claude
- 加 fallback：LLM 失败时回退到规则引擎
- 审计日志记录真实 token 用量
- 加成本控制：单日 token 上限

**难度**：L-XL（含 prompt 工程 + 测试）

---

### 17. 实盘交易路径完整化

**现状**：`src/execution/exchange_broker.py` / `exchange_execution.py` 已存在但未启用，`LIVE_TRADING_ENABLED=false` 默认关

**实施**：
- 实盘前必备：IP 白名单、API key 权限收紧（无提币）、订单金额硬上限、二次确认 UI
- 前端加"实盘模式"开关（双确认 + 倒计时）
- 风控规则实盘化（不只是 Paper 模拟）
- 完整的 kill switch（一键停止所有实盘策略）

**难度**：XL（这是 Phase 7+ 工作，慎重）

---

### 18. 数据源从离线 CSV 切到实时

**现状**：Paper Trading 跑的是 `data/raw/BTC_USDT_4h_osc_*.csv` 离线数据；`ws_feed.py` 已接 Binance WS 但只用于 Ticker 展示

**实施**：
- `service.py:_load_data()` 改为优先从 TimescaleDB 读实时历史 K 线
- 加数据回填任务（`downloader.py` 已有，需调度）
- Paper Trading 改为增量运行（每根新 bar 触发一次），而非一次性跑全量

**难度**：XL

---

## 🟣 工程化与可观测性

### 19. Prometheus `/metrics` 端点

**现状**：`metrics_collector.py` 在采集指标但只快照到内存，无 HTTP 暴露。Grafana 配置存在但抓不到数据

**实施**：
- 加 `prometheus-fastapi-instrumentator` 依赖
- `/metrics` 端点暴露：HTTP 请求计数/延迟、WS 客户端数、订单数、PnL、缓存命中率
- Grafana dashboard 已在 `config/grafana/`，对接即可

**难度**：M

---

### 20. 结构化日志聚合

**现状**：loguru 写本地文件，无集中收集。生产排障需 SSH 上机器 grep

**实施**：
- 选项 A：loguru 加 JSON sink，输出到文件 + stdout，用 Promtail 采集到 Loki
- 选项 B：对接 Sentry（错误）/ Datadog（APM）
- 至少加 request_id 中间件，串联一次请求的所有日志

**难度**：M

---

### 21. 审计日志改 SQLite/Postgres

**现状**：`audit_log.py` 写 `data/reports/agent/audit_log.json`，`get_logs` 全表 O(n) 扫描，无索引

**实施**：
- 改用 `src/utils/database.py` 已有的 Postgres 连接
- 表结构：`id, timestamp, task, phase, input_json, output_json, model, tokens_used, human_approved, action_taken`
- 加 `(task, timestamp)` 复合索引
- 保留 JSON 文件作为冷备

**难度**：M

---

### 22. 前端 e2e 测试

**现状**：前端只有 TypeScript 类型检查，无 e2e。后端有 unit + integration

**实施**：
- 加 Playwright
- 至少覆盖 3 条核心路径：总览加载 → 订单翻页 → AI 分析触发
- CI 跑（见 #23）

**难度**：L

---

### 23. CI/CD 配置

**现状**：仓库无 `.github/workflows/`，无自动化

**实施**：
- GitHub Actions workflow：
  - `lint`：后端 ruff + 前端 eslint
  - `test-backend`：`pytest tests/`
  - `test-frontend`：`tsc --noEmit` + Playwright
  - `build-frontend`：`next build`
  - `docker-build`：构建镜像
- PR 必须全绿才能合并

**难度**：M

---

### 24. Docker healthcheck + 多阶段构建优化

**现状**：`Dockerfile` 存在但未见 healthcheck 配置

**实施**：
- `Dockerfile` 加 `HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1`
- `docker-compose.yml` 的 api 服务加 `healthcheck` + `depends_on: {condition: service_healthy}`
- 多阶段构建：builder 阶段装依赖，runtime 阶段只复制产物，减小镜像体积

**难度**：S-M

---

## ⚪ 数据与策略

### 25. 多策略支持多交易对

**现状**：`MultiStrategyRunner` 注册 8 个策略，但全用 `SYMBOL = "BTC/USDT"`，无分散

**实施**：注册时用不同 symbol：BTC/USDT、ETH/USDT、SOL/USDT 各跑几个策略，做跨品种分散

**难度**：M（需 broker 支持多 symbol 持仓隔离，`paper_broker.py` 看起来已支持）

---

### 26. 策略参数可配置

**现状**：策略参数在 `service.py:_build_multi_results` 硬编码（如 `grid_count=10`）

**实施**：
- 加 `/strategies/:id/params` PATCH 端点
- 前端策略详情页加参数编辑表单
- 改后需重新跑 Paper Trading（配合 #14 热刷新）

**难度**：M

---

## 📊 优先级矩阵汇总

| 象限 | 项目编号 | 推荐节奏 |
|-----|---------|---------|
| 🟢 高价值低成本 | 1, 2, 3, 4, 5, 6, 7 | 本周做完 |
| 🟡 中价值中成本 | 8, 9, 10, 11, 12, 13, 14 | 下个迭代 |
| 🔴 高价值高成本 | 15, 16, 17, 18 | 按季度规划 |
| 🟣 工程化 | 19, 20, 21, 22, 23, 24 | 持续推进 |
| ⚪ 数据策略 | 25, 26 | 与 18 一起做 |

---

## 推荐的下一步

如果让我挑 3 件最该立刻做的：

1. **#4 CSP 头修正** —— 这是个潜在生产事故，前端可能一上生产就白屏
2. **#13 `get_state` 阻塞修复** —— 加 `to_thread` 预热，避免首次请求卡死事件循环
3. **#1 `/risk` 风险页 + #2 总览风险卡** —— 用户最常看的核心功能，且后端已有数据

#23 CI/CD 也建议尽快做，越往后越难补。
