# Changelog

本项目所有重要变更记录于此。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
项目尚未发布正式版本（仍处 Paper Trading 阶段），故暂以日期里程碑分组，未采用语义化版本号。

## [Unreleased]

当前阶段：**Phase 4 — Paper Trading（60 天连续运行验证）**。实盘交易（Live Broker）属 Phase 7+，尚未实现。

### 待办（人工/时间轨道，无法用代码完成）
- 60 天 paper trading 连续运行（用户在本机持久终端执行）
- 实盘前门禁的人工确认项（风险确认书、初始资金 ≤ $500、双重确认开关）
- Live Broker（真实主网下单）— Phase 7+

---

## 2026-06-20 — 上线前审查与安全硬化

### Added
- 6 份参考文档：`API_REFERENCE.md`、`DEPLOYMENT.md`、`DATABASE_SCHEMA.md`、`FRONTEND_ARCHITECTURE.md`、`ENV_VARIABLE_REFERENCE.md`、`STRATEGY_CATALOG.md`
- `SECURITY.md`、`CHANGELOG.md`
- `.env.example` 补 `API_TOKEN`（任何环境必需，空值阻止 API 启动）
- API 安全：全局限速（slowapi）、CSP / HSTS 响应头、`/health` 与 `/health/detailed` 拆分（后者需认证）
- WebSocket 首条消息认证（`secrets.compare_digest`，10s 超时）
- 前端请求统一携带 `X-API-Token`

### Changed
- Python 版本全仓统一为 3.13（Dockerfile / pyproject / CI / 文档）
- `docker-compose`：`trading_system` 服务启用 uvicorn 启动 + `8000:8000` 端口映射
- Redis healthcheck 补密码认证（`redis-cli -a $REDIS_PASSWORD ping`）
- 测试基线更新为 481 passed / 484 collected
- 文档与代码对齐：移除对不存在脚本的可执行命令引用，`ENGINEERING.md` 加状态横幅 + 蓝图→实际模块映射表

### Fixed
- `RiskManager.reset()` 保留 `peak_equity` / `cumulative_pnl`，防回撤失忆
- `record_fill` 锁覆盖全函数体；psycopg2 游标全程持锁（线程安全）
- 多策略路径注入 `RiskManager`；`BuyAndHoldStrategy` 继承 `RiskAwareStrategy`

## 2026-06-19 — 功能扩展批次

### Added
- 多策略并行运行（`MultiStrategyRunner`：共享现金池、持仓按 symbol 隔离、风控全局）
- RSI 动量策略（RSI14 + EMA50 + 连亏熔断）
- AI 分析引擎（`src/agent/analyzer.py`，纯规则、无 LLM 外呼、只分析不执行）+ JSON 审计日志
- WebSocket 实时行情推送（替代 15s 轮询）
- API 新端点：`/multi/*`、`/agent/*`、`POST /strategies/create-grid`
- 风控回撤熔断（默认 15%）；daemon 闪崩保护（`--max-bar-drop-pct`）+ 优雅退出
- PaperBroker 限价单支持（Phase 7 v2 铺路）
- 基础设施：常量集中（`src/constants.py`）、Redis 缓存层（回退内存）、DataFrame 哈希

## 2026-06-17 — Phase 6 门禁 + 守护进程 + 上交易所前置线

### Added
- 前端接真实后端（FastAPI `src/api/`，9→18 端点）+ 一键启动脚本
- Ticker 接 Binance 实时行情（ccxt，TTL 缓存 + 离线回退）
- 60 天 paper trading 连续运行守护进程（崩溃重启续跑、跨日出日报、健康巡检）
- 实盘启动门禁入口（`start_live_trading.py`，双重确认开关）
- Phase 7 testnet 线 Stage 0-4（执行适配层、broker 无关 runner、`--broker exchange`、订单护栏 `OrderRateGuard`）
- preflight 自检聚合脚本 + CI

### Fixed
- winRate 精确化（用引擎逐笔平仓盈亏替换 FIFO 近似）
- 成交记录用 bar 时间而非 `datetime.now()`
- ExchangeBroker testnet sandbox 修复（`set_sandbox_mode`，原 `options.testnet` 不切 endpoint，会打主网）
- ExchangeBroker 查单/撤单补 symbol（testnet 实测打通）
- daemon live 冷启动公共行情用无凭据客户端 + 种子仅预热不回填历史

## 2026-06-16 — Phase 5 收尾 + 监控

### Added
- Grafana 面板 provisioning（采集器→DB→数据源→面板 端到端验证）
- ExchangeBroker 交易所接口适配层（Phase 6，testnet/查询为主）

### Fixed
- Grafana 数据源 provisioning 连接修复

## 2026-06-13 及更早 — Phase 1-4 基础（GitHub 迁移前）

### Added
- 数据可信闭环（数据质量校验、时区统一）
- 事件驱动回测引擎（统一分仓模型，t 收盘发信号 / t+1 开盘成交，无前视偏差）
- 网格交易策略 + RiskAwareStrategy 继承体系
- PaperBroker（资金/仓位管理、手续费、滑点、订单管理、风控检查），paper 路径与回测逐位一致

---

[Unreleased]: https://github.com/Airdop2474/crypto-trading-system/commits/master
