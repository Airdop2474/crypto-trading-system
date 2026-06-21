# 架构师技术文档审查报告 — 高见远

**审查日期：** 2026-06-20  
**审查人：** 高见远（架构师）  
**审查范围：** 技术文档域（3 技术文档 + 8 标准/门禁文档 + 2 设计讨论 + 4 交付物）  
**验证方法：** 逐文件读取 + 逐脚本 Glob 存在性验证 + 关键源文件交叉比对  

---

## 🔴 CRITICAL（阻塞上线 — 文档与代码不一致/命令不可执行/过时）

| # | 问题 | 文档位置 | 代码实际状态 | 严重度 | 修复建议 |
|---|------|----------|-------------|--------|---------|
| **C1** | `scripts/download_data.py` 和 `scripts/init_database.py` 在快速开始指南中被引用但**不存在** | `ENGINEERING.md` §7.1 第 6-7 步：`python scripts/init_database.py` / `python scripts/download_data.py --symbol BTC/USDT --days 365` | Glob 搜索 `scripts/download_data.py` 和 `scripts/init_database.py` 均返回 **0 结果**。这两个脚本从未被创建。 | 🔴 CRITICAL | 删除或替换为已有脚本引用。数据下载可用 `scripts/generate_oscillating_data.py`；数据库初始化由 docker compose 的 `config/sql/01_monitor_metrics.sql` 自动完成。 |
| **C2** | ENGINEERING.md 中 `.env` 模板使用错误的变量名，与实际系统不兼容 | `ENGINEERING.md` §2.2 `.env` 模板使用 `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | 实际 `docker-compose.yml` 使用 `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_USER`（无 `POSTGRES_HOST`/`POSTGRES_PORT` 在 env 级别）；实际 `src/utils/config.py` 使用 `TIMESCALE_*` 前缀。`OPERATIONS_MANUAL.md` §1 要求设置 `TIMESCALE_PASSWORD`，但 compose 读取 `POSTGRES_PASSWORD`。 | 🔴 CRITICAL | 统一所有文档和 `.env.example` 中的环境变量命名。建议以实际 `.env.example` 和 docker-compose.yml 为准。 |
| **C3** | OPERATIONS_MANUAL.md 环境变量名与 docker-compose 不匹配 | `OPERATIONS_MANUAL.md` §1 表：`TIMESCALE_PASSWORD` = `changeme` | `docker-compose.yml:11` 读 `${POSTGRES_PASSWORD:?...}`，**不读** `TIMESCALE_PASSWORD`。如用户按手册只设 `TIMESCALE_PASSWORD`，compose 启动时直接报错退出。 | 🔴 CRITICAL | `TROUBLESHOOTING.md` 故障 1 已意识到此差异（"确认 TIMESCALE_PASSWORD 与 compose 的 POSTGRES_PASSWORD 一致"），但 OPERATIONS_MANUAL.md 应从源头修正：把 `TIMESCALE_PASSWORD` 改为 `POSTGRES_PASSWORD`（或以 .env.example 为准统一）。 |
| **C4** | ENGINEERING.md 中的 `docker-compose.yml` 与实际完全不符 | `ENGINEERING.md` §6.1 完整列出了一个简化版 compose（仅 timescaledb + redis + trading_system，无 Grafana，无 Redis 密码，无健康检查） | 实际 `docker-compose.yml` 有 4 个服务（含 Grafana），Redis 有密码认证，timescaledb 有健康检查，trading_system 使用 uvicorn 启动。两者在服务数量、密码策略、健康检查、镜像版本、启动命令等方面**完全不同**。 | 🔴 CRITICAL | 删除 ENGINEERING.md §6.1 中的过时 compose 示例，替换为对实际 `docker-compose.yml` 的说明引用。 |
| **C5** | `docs/system_design.md` 描述的策略数量过时 | `system_design.md` §2.1 文件列表和 §3 类图中仅列出 4 个策略类：`GridTradingStrategy`, `RSIMomentumStrategy`, `SimpleMAStrategy`, `BuyAndHoldStrategy` | `src/strategy/registry.py` 实际注册了 **8 个策略**：grid, rsi, ma, buyhold, donchian, structure, supertrend, reversal。新增的 `DonchianChannelStrategy`, `MarketStructureStrategy`, `SuperTrendStrategy`, `KeyLevelReversalStrategy` 在 system_design.md 中完全没有提及。 | 🔴 CRITICAL | 更新 system_design.md 的类图和文件列表以反映实际 8 策略状态；或如果新策略属于 Phase 7+ 独立研究线，应在文档中明确标注其状态。 |
| **C6** | `docs/system_design.md` 的"下一步"指令已完全过时 | `system_design.md` 末尾（第 763 行）：*"下一步：交由交易代码专家按 T01→T02→T03/T04→T05 顺序执行"* | 经验证，T01-T05 的全部产物均已存在：`src/utils/trading.py` ✅、`src/strategy/risk_aware.py` ✅、`src/strategy/registry.py` ✅、`src/monitor/market_classifier.py` ✅、`scripts/grid_parameter_sweep.py` ✅、`tests/integration/test_backtest_paper_parity.py` ✅、`tests/integration/test_multi_strategy_isolation.py` ✅、`tests/integration/test_e2e_pipeline.py` ✅。**所有任务已完成。** | 🔴 CRITICAL | 将 system_design.md 状态从"待团队审核"更新为"已实施"，移除"下一步"指令，补充实际实施情况总结。 |
| **C7** | ENGINEERING.md 描述的 Dockerfile CMD 与实际启动命令不符 | `ENGINEERING.md` §6.1 Dockerfile：`CMD ["python", "src/main.py"]` | 实际 `docker-compose.yml:90`：`command: python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000`。两者启动模式完全不同（单文件 vs ASGI 服务器）。 | 🔴 CRITICAL | 删除 ENGINEERING.md 中的示例 Dockerfile（已过时），引用实际 Dockerfile。 |
| **C8** | ENGINEERING.md 完全遗漏 API 层 | `ENGINEERING.md` 全文无任何 FastAPI、REST API、WebSocket 相关内容。§7.2 仍描述 `streamlit run src/monitor/dashboard.py`。 | 实际系统以 FastAPI 为核心（`src/api/app.py` 提供 `/health`, `/account/summary`, `/market/tickers`, `/ws/tickers` 等端点），有 WebSocket 实时行情推送，有 API Token 认证，有 CORS 和限流中间件。Streamlit 方式已被完全取代。 | 🔴 CRITICAL | 在 ENGINEERING.md 中添加 API 层章节，或新建 `docs/technical/API_ARCHITECTURE.md`。 |
| **C9** | BROKER_ARCHITECTURE.md Phase 4 验收清单全部未勾选 | `BROKER_ARCHITECTURE.md` §"Phase 4 验收清单"（第 621-642 行）10 个功能项 + 7 个测试项全部为 `- [ ]` 未完成状态 | 实际 `src/execution/paper_broker.py` 已完整实现所有列表功能（资金管理、仓位管理、手续费、滑点、订单管理、风控检查、交易历史、统计信息），覆盖率 99%（QA 报告）。 | 🔴 CRITICAL | 勾选所有已实现项，标注"✅ 已实现（2026-06-20）"。 |

---

## 🟠 HIGH（高优先级 — 重要不一致/遗漏/过时）

| # | 问题 | 文档位置 | 代码实际状态 | 严重度 | 修复建议 |
|---|------|----------|-------------|--------|---------|
| **H1** | 日亏损熔断阈值在三份文档中不一致 | ① `ENGINEERING.md` §2.2 `.env`：`DAILY_LOSS_LIMIT_PCT=0.05`<br>② `LIVE_TRADING_CHECKLIST.md` §风控参数：`daily_loss_limit: 0.03`<br>③ `STRATEGY_ASSUMPTIONS.md` §6：当日亏损 ≥2% 触发 PAUSE | ① `RiskManager.__init__` 默认 `max_daily_loss=0.03`<br>② `RiskAwareStrategy.__init__` 默认 `max_daily_loss=0.02`<br>→ 存在 **0.02 / 0.03 / 0.05** 三个不同值 | 🟠 HIGH | 统一为 `0.03`（与 RiskManager 和 LIVE_TRADING_CHECKLIST 一致）。区分策略级（RiskAwareStrategy, 0.02 更保守可接受但需注明）和账户级（RiskManager, 0.03）。 |
| **H2** | ENGINEERING.md 本质是"从零构建教程"而非"当前系统文档" | `ENGINEERING.md` 全文以"创建 `src/data/exchange.py`"、"创建 `src/strategy/base.py`"等指令形式呈现，包含大量完整代码示例（约 1700 行），读起来像 Phase 0 的蓝图。 | 实际项目已有 30+ 源文件、8 策略、FastAPI 后端、WebSocket、Docker 部署。ENGINEERING.md 中的示例代码（如 `ExchangeConnector`, `DatabaseManager`, `GridTradingStrategy`）与实现有出入。 | 🟠 HIGH | 决策：要么将 ENGINEERING.md 重写为当前架构的**描述性文档**（推荐），要么在开头用醒目标注说明"本文档为 Phase 0 设计蓝图，实际实现见代码"。 |
| **H3** | ENGINEERING.md 未反映 ~90 项修复中的关键变更 | `ENGINEERING.md` 最后更新 2026-06-13 | `fix-summary-2026-06-20.md` 记录了 ~90 项修复，涉及 32 个文件。例如：RiskManager 加了 `threading.Lock`、cache.py 加了熔断器、config.py 加了 `strict` 参数——ENGINEERING.md 无任何反映。 | 🟠 HIGH | 在 ENGINEERING.md 开头添加"⚠️ 本文档创建于 2026-06-13，截至 2026-06-20 已有 ~90 项修复未同步更新"，并在对应章节标注实际变更。 |
| **H4** | `system_design.md` 描述的熔断机制与实际实现不同 | `system_design.md` §3 类图中 `RiskAwareStrategy.on_fill(trade)` 通过设置 `self.paused = True` 实现熔断。 | 实际 `src/strategy/risk_aware.py` 使用 `CircuitBreaker` **异常**机制 + `_is_paused()` 方法，熔断时抛出 `CircuitBreaker(reason)` 而非仅设标志位。设计决策在代码实现中发生了根本变化，文档未更新。 | 🟠 HIGH | 更新 system_design.md 的类图和描述以匹配实际 CircuitBreaker 异常模式。 |
| **H5** | `config/alerts.yaml` 被引用但不存在 | `ENGINEERING.md` §6.2（第 1464 行）引用 `config/alerts.yaml` 配置告警规则 | Glob 搜索 `config/alerts.yaml` → **0 结果**。实际告警逻辑在 `src/monitor/alert_manager.py` 中硬编码。 | 🟠 HIGH | 删除 ENGINEERING.md 中的引用，或实现该配置文件。 |
| **H6** | OPERATIONS_MANUAL.md pytest 基线数字严重过时 | `OPERATIONS_MANUAL.md` §4："基线：159 passed" | QA 报告显示 **475 total, 472 passed**（2026-06-20）。159 是 ~3x 低估。 | 🟠 HIGH | 更新基线为"472 passed / 475 total"。 |
| **H7** | ENGINEERING.md 的 `requirements.txt` 依赖列表与实际可能不符 | `ENGINEERING.md` §1.3 列出了 `ccxt==4.2.0`, `streamlit==1.30.0`, `backtesting==0.3.3` 等 | 实际项目使用 `fastapi` + `uvicorn`（ENGINEERING.md 中有列出），但 streamlit 可能不再需要。ccxt 版本是否仍为 4.2.0 未验证。 | 🟠 HIGH | 将 `requirements.txt` 引用替换为对项目实际 `requirements.txt` 文件的引用，而非内联代码块。 |
| **H8** | ENGINEERING.md 中 PYTHONPATH 硬编码为 Windows 路径 | `ENGINEERING.md` — 文档虽未直接硬编码，但上下文假设 Windows 环境（`venv\Scripts\activate`） | `OPERATIONS_MANUAL.md` §0 硬编码：`export PYTHONPATH=C:\Github\crypto-trading-system` — Linux/macOS 不可用。 | 🟠 HIGH | 改为通用写法：`export PYTHONPATH=$(pwd)` 或 `set PYTHONPATH=%cd%`。 |

---

## 🟡 MEDIUM（建议改进 — 次要不一致/缺失/可优化）

| # | 问题 | 文档位置 | 说明 | 修复建议 |
|---|------|----------|------|---------|
| **M1** | ENGINEERING.md §9 "后续优化方向" 大量 TODO 项已实现 | §9.1 短期优化："增加更多技术指标（RSI, MACD, Bollinger Bands）"、"实现趋势跟踪策略"、"实现 WebSocket 实时数据流" | 实际系统已有 RSI 策略、Donchian Channel 策略、SuperTrend 策略（8 策略），WebSocket 在 `src/api/ws_feed.py` 中实现。将已实现项勾选或移除。 | 逐项核实并标注状态。 |
| **M2** | ENGINEERING.md §6.3 `scripts/backup_database.sh` 不存在 | §6.3 完整列出了一个 bash 备份脚本 | Glob → **0 结果**。备份策略在文档中有设计但代码未落地。 | 如备份脚本未被实施，移除引用或标注"待实现"。 |
| **M3** | 多个文档引用 Python 3.11，实际运行环境是 3.13 | `ENGINEERING.md` §1.2：Python 3.11+；`pyproject.toml` 片段：`target-version = ['py311']` | QA 报告确认实际测试环境为 **Python 3.13.12**。版本偏差 2 个 minor 版本。 | 统一更新为 Python 3.11+（保持兼容性标注），同时注明已在 3.13 上验证。 |
| **M4** | BROKER_ARCHITECTURE.md 的审计日志路径与实际不一致 | `BROKER_ARCHITECTURE.md` §4 LiveBroker 写入 `audit_log.jsonl`（项目根目录） | 实际审计日志由 `src/agent/audit_log.py` 管理，路径由配置决定，非硬编码。 | 更新为对 `src/agent/audit_log.py` 的引用，移除硬编码文件名。 |
| **M5** | ENGINEERING.md 数据库 Schema 中使用表名 `ohlcv` 等与 DATA_QUALITY_STANDARD.md 中的 `ohlcv_data` 不一致 | `ENGINEERING.md` §3.1：`CREATE TABLE ohlcv`<br>`DATA_QUALITY_STANDARD.md` §数据存储格式：`CREATE TABLE ohlcv_data` | 两个文档描述了两套不同的数据库 schema。实际代码使用 SQLAlchemy ORM，表名由模型定义。 | 以实际代码中的 ORM 模型定义为准，统一所有文档中的表名引用。 |
| **M6** | ENGINEERING.md `config/grafana/dashboard.json` 与实际路径不符 | §6.2 引用 `config/grafana/dashboard.json` | 实际为 `config/grafana/dashboards/monitoring.json`（多了一层 `dashboards/` 目录，文件名也不同）。 | 修正路径引用。 |
| **M7** | 多个文档的日期/版本标注混乱 | `ENGINEERING.md` 头部："更新日期：2026-06-13" / 尾部："最后更新：2026-06-12" | 同一文档内存在两个不同的"最后更新"日期。`BROKER_ARCHITECTURE.md` 全部标注 2026-06-13，但实际系统早已超越 Phase 4。 | 统一每个文档的版本日期，优先使用实际最后修改时间。 |
| **M8** | TROUBLESHOOTING.md 故障编号与场景覆盖 | 共 7 个故障场景（故障 1-7），覆盖数据库、Grafana、pytest、模块导入、表缺失、风控熔断、数据缺失。 | 缺失场景：WebSocket 断连、API 限流 429、前端构建失败、Docker 资源耗尽。 | 按实际运维中遇到的问题逐步补充。当前 7 个场景对 paper trading 阶段足够。 |
| **M9** | ENGINEERING.md 的 Git 分支策略与实际使用不符 | §5.1 描述 `main → develop → feature/*` 分支模式 | 无法从文档确定实际分支策略，但项目记忆显示使用简化流程。 | 核实后更新或删除分支策略章节。 |

---

## 📋 缺失文档清单

以下技术文档应该存在但当前缺失：

| # | 缺失文档 | 重要度 | 理由 |
|---|---------|--------|------|
| **D1** | `docs/technical/API_REFERENCE.md` | 🔴 CRITICAL | 系统有 6+ REST 端点 + 1 WebSocket 端点 + API Token 认证 + CORS 策略，无任何 API 文档。`ENGINEERING.md` 完全未提及 API 层。 |
| **D2** | `docs/technical/DATABASE_SCHEMA.md` | 🟠 HIGH | ENGINEERING.md 和 DATA_QUALITY_STANDARD.md 各描述了一套 schema（表名不同），实际代码使用 SQLAlchemy ORM。需要一份以实际 ORM 模型为准的统一 schema 文档。 |
| **D3** | `docs/technical/FRONTEND_ARCHITECTURE.md` | 🟡 MEDIUM | QA 报告标记前端测试覆盖为 0%，无独立前端架构文档。前端代码（如 `frontend/` 或相关目录）的架构、组件树、状态管理未有文档。 |
| **D4** | `docs/technical/ENV_VARIABLE_REFERENCE.md` | 🟠 HIGH | 环境变量在各个文档中分散描述（ENGINEERING.md、OPERATIONS_MANUAL.md、LIVE_TRADING_CHECKLIST.md），命名不一致。需要一份权威的 `.env.example` 注释即文档的环境变量参考。 |
| **D5** | `docs/technical/STRATEGY_CATALOG.md` | 🟡 MEDIUM | 8 个策略分散在 registry.py 中，各自有独立的参数和假设。系统级策略目录文档缺失——STRATEGY_ASSUMPTIONS.md 仅覆盖网格策略。 |

---

## ✅ 做得好的地方

以下是技术文档和标准文档的质量亮点：

1. **标准/门禁文档体系完善**：`LIVE_TRADING_CHECKLIST.md`、`TROUBLESHOOTING.md`、`OPERATIONS_MANUAL.md`、`DATA_QUALITY_STANDARD.md`、`BACKTEST_VALIDATION.md`、`STRATEGY_ASSUMPTIONS.md`、`AI_USAGE_BOUNDARIES.md`、`REMAINING_MANUAL_WORK.md` — 8 份标准文档覆盖了安全、故障、操作、数据、回测、策略、AI 边界、人工工作等关键维度。

2. **OPERATIONS_MANUAL.md 命令可执行性高**：7 个关键脚本全部验证存在且路径正确：
   - `scripts/check_environment.py` ✅
   - `scripts/generate_oscillating_data.py` ✅
   - `scripts/run_paper_trading.py` ✅
   - `scripts/run_data_pipeline.py` ✅
   - `scripts/verify_grafana_e2e.py` ✅
   - `scripts/verify_risk_controls.py` ✅
   - `scripts/preflight_check.py` ✅

3. **TROUBLESHOOTING.md 实用性强**：7 个故障场景均有清晰的症状→原因→解决三段式结构，每个故障都有可直接复制执行的命令。故障 2（Grafana 数据源）甚至记录了真实修复的 git commit（`bc984c0`）。

4. **BROKER_ARCHITECTURE.md 设计清晰**：三层 Broker 架构（Paper / Exchange / Live）职责分明，代码示例完整，验收清单明确。

5. **LIVE_TRADING_CHECKLIST.md 安全门禁完备**：涵盖 API Key 权限、风控参数、初始资金、紧急停止、恢复流程、禁止事项、用户风险确认书——实盘前无遗漏。

6. **REMAINING_MANUAL_WORK.md 诚实务实**：明确区分了"代码能做"和"只有人能做的"，不夸大自动化能力，明确标注 Live Broker 尚未实现。

7. **fix-summary-2026-06-20.md 可追溯**：~90 项修复每项都有文件→问题→修复方式三列，修复文件清单完整（32 个文件）。

---

## 📊 审查统计

| 指标 | 数值 |
|------|------|
| **审查文件总数** | 17（3 技术 + 8 标准/门禁 + 2 设计讨论 + 4 交付物） |
| **交叉验证源文件数** | 5（registry.py, app.py, risk_manager.py, docker-compose.yml, risk_aware.py） |
| **验证的命令/脚本数** | 15 条命令验证，**12 通过 / 3 失败** |
| **脚本验证详情** | ✅ check_environment.py, generate_oscillating_data.py, run_paper_trading.py, run_data_pipeline.py, verify_grafana_e2e.py, verify_risk_controls.py, preflight_check.py, run_paper_trading_daemon.py, start_live_trading.py, verify_api_key_permissions.py, testnet_smoke.py, check_daemon_health.py<br>❌ download_data.py（不存在）, init_database.py（不存在）, backup_database.sh（不存在） |
| **发现 CRITICAL** | **9** |
| **发现 HIGH** | **8** |
| **发现 MEDIUM** | **9** |
| **缺失文档** | **5**（API_REFERENCE, DATABASE_SCHEMA, FRONTEND_ARCHITECTURE, ENV_VARIABLE_REFERENCE, STRATEGY_CATALOG） |

---

### 🔑 修复优先级建议

1. **立即修复（阻塞 Paper Trading 用户）**：C1, C2, C3 — 这些会导致新用户无法按文档启动系统。
2. **上线前修复（阻塞 Phase 6 实盘）**：C4, C5, C6, C7, C8, C9, H1, H2, H4 — 架构文档与实际系统不符。
3. **后续迭代修复**：H3, H5-H8, M1-M9, D1-D5 — 完善文档体系和补充缺失内容。

---

**审查结论：** 技术文档的**标准/门禁部分质量高**（OPERATIONS_MANUAL、TROUBLESHOOTING、LIVE_TRADING_CHECKLIST 等），但 **ENGINEERING.md 和 system_design.md 与实际代码严重脱节**。ENGINEERING.md 定位模糊（是教程还是现状文档？），system_design.md 的 T01-T05 已全部实施但文档未更新。最紧急的是 3 个环境变量命名不一致问题（C2/C3），会导致按文档操作的用户无法启动系统。
