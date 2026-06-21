# 上线前文档审查报告 — 加密交易系统

**日期**: 2026-06-20
**审查范围**: 项目全部文档（README、架构、运维、部署、API、配置、CI/CD 等）
**审查目标**: 评估文档是否满足生产上线要求，识别断链、过时、矛盾和缺失项

---

## 执行摘要

项目拥有约 153 个文档文件、总计约 37,000 行，在规划和设计阶段投入了大量文档工作。然而，文档体系存在一个核心矛盾：**开发规划文档丰富，生产运维文档薄弱**。最关键的阻塞项是——README 链接的两个核心文档（`docs/API.md` 和 `docs/DEPLOYMENT.md`）不存在，`.env.example` 缺少 API 认证必需的 `API_TOKEN`，多处文档引用的脚本和文件在代码中不存在。

整体评估：**文档尚未达到上线就绪状态**，需修复 5 项 HIGH 阻塞和 8 项 MEDIUM 问题后方可发布。

---

## 1. 文档资产盘点

### 1.1 核心文档清单

| 文件 | 行数（约） | 内容 | 状态 |
|------|-----------|------|------|
| `README.md` | 200 | 项目概览、快速启动、技术栈、徽章 | 存在但有多处过时 |
| `START_HERE.md` | 300 | 新手入门导航、项目路线图 | 存在但项目状态描述过时 |
| `docs/technical/ARCHITECTURE.md` | ~500 | 系统架构、组件关系、数据流 | 存在，质量较好 |
| `docs/technical/ENGINEERING.md` | ~1600 | 工程实现细节、代码示例、测试结构 | 存在但多处与代码不一致 |
| `docs/technical/BROKER_ARCHITECTURE.md` | ~300 | 交易执行层架构设计 | 存在，描述了尚未实现的组件 |
| `docs/operations/OPERATIONS_MANUAL.md` | ~400 | 运维手册、监控、告警 | 存在，质量较好 |
| `docs/operations/TROUBLESHOOTING.md` | ~300 | 常见故障排查 | 存在 |
| `docs/reference/QUICK_REFERENCE.md` | ~120 | 常用命令速查 | 存在但引用了不存在的脚本 |
| `docs/collaboration/CONTRIBUTING.md` | ~350 | 贡献指南、代码规范 | 存在 |
| `.env.example` | ~80 | 环境变量模板 | 存在但缺少关键变量 |
| `docker-compose.yml` | ~90 | 容器编排配置 | 存在，`trading_system` 服务被注释 |
| `Dockerfile` | ~40 | 容器镜像构建 | 存在 |
| `docs/API.md` | — | API 接口文档 | **不存在**（README 中有链接） |
| `docs/DEPLOYMENT.md` | — | 部署指南 | **不存在**（README 中有链接） |
| `SECURITY.md` | — | 安全策略 | **不存在** |
| `CHANGELOG.md` | — | 变更日志 | **不存在** |

### 1.2 文档分布统计

- `docs/` 目录下约 30+ 个 `.md` 文件，涵盖技术设计、运维、协作规范
- `deliverables/` 目录包含审查报告、QA 报告等交付物
- `.gstack/` 目录包含安全审计历史
- 源码子目录（`src/`、`frontend/`）无内联 README

---

## 2. 文档与代码一致性检查

这是本次审查发现最密集的区域。文档中引用的文件、脚本、命令如果不存在或已变更，将直接导致新用户或运维人员无法按指引操作。

### 2.1 引用的文件和脚本不存在

| 文档中的引用 | 引用位置 | 实际状态 |
|-------------|---------|---------|
| `src/monitor/dashboard.py` | README.md, START_HERE.md, QUICK_REFERENCE.md | **文件不存在**。`src/monitor/` 下无 dashboard.py，streamlit 在 requirements.txt 中也被注释 |
| `src/main.py` | QUICK_REFERENCE.md, ENGINEERING.md | **文件不存在**。项目无统一入口脚本 |
| `scripts/init_database.py` | README.md, QUICK_REFERENCE.md, ENGINEERING.md | **文件不存在** |
| `scripts/download_data.py` | README.md, QUICK_REFERENCE.md, ENGINEERING.md | **文件不存在** |
| `scripts/quick_start.py` | QUICK_REFERENCE.md | **文件不存在** |
| `docs/API.md` | README.md 第 97 行 | **文件不存在**，链接为断链 |
| `docs/DEPLOYMENT.md` | README.md 第 98 行 | **文件不存在**，链接为断链 |
| `tests/fixtures/` | CONTRIBUTING.md 第 344 行 | **目录不存在** |
| `src/data/database.py` | ENGINEERING.md 代码示例 | **文件不存在**，实际为 `src/utils/database.py` |
| `src/agent/interface.py` | ENGINEERING.md 代码示例 | **文件不存在**，实际为 `src/agent/analyzer.py` |
| `src/agent/trigger.py` | ENGINEERING.md 代码示例 | **文件不存在** |

### 2.2 环境变量不一致

环境变量命名在多份文档和代码间存在三套不同的命名体系，这是最容易引发部署事故的问题。

| 变量用途 | `.env.example` | `config.py` 实际读取 | `ENGINEERING.md` 描述 | `docker-compose.yml` |
|---------|---------------|---------------------|----------------------|---------------------|
| 数据库主机 | `TIMESCALE_HOST` | `TIMESCALE_HOST` | `POSTGRES_HOST` | 无（服务名寻址） |
| 数据库密码 | `TIMESCALE_PASSWORD` | `TIMESCALE_PASSWORD` | `POSTGRES_PASSWORD` | `POSTGRES_PASSWORD` |
| Binance 密钥 | `BINANCE_SECRET` | `BINANCE_SECRET` | `BINANCE_API_SECRET` | 无 |
| API 认证令牌 | **缺失** | `API_TOKEN` | 未提及 | 未提及 |
| 最大持仓 | `MAX_POSITION_SIZE` | `MAX_POSITION_SIZE` | `MAX_POSITION_PCT` | 无 |
| 日亏损限制 | `MAX_DAILY_LOSS` | `MAX_DAILY_LOSS` | `DAILY_LOSS_LIMIT_PCT` | 无 |

**最严重的问题**: `API_TOKEN` 是 API 服务器强制要求的变量（未配置时返回 HTTP 500），但 `.env.example` 中完全没有这个条目。按照 README 快速启动流程 `cp .env.example .env` 操作的用户，无论如何都无法成功调用 API。

### 2.3 Python 版本不一致

| 来源 | Python 版本 |
|------|-----------|
| README.md | "Python 3.11+" |
| START_HERE.md | 未明确版本 |
| ENGINEERING.md | "需要 3.11+" |
| `.github/workflows/ci.yml` | `3.11` |
| `Dockerfile` | `3.13-slim-bookworm` |
| `pyproject.toml` (black/mypy) | `py313` / `3.13` |

文档体系指向 3.11，而实际构建配置已迁移到 3.13。新用户按文档安装 3.11 可能在运行时遇到兼容性问题。

### 2.4 其他不一致

- **策略数量**: README 声称"8 策略引擎"，但 `src/strategy/` 下有 9 个具体策略实现
- **测试数量**: README 徽章标注"475 tests passed"，与 QA 报告的 472 不一致（可能是不同时间点的数据，但徽章应反映当前状态）
- **`docker-compose` vs `docker compose`**: START_HERE.md 和 QUICK_REFERENCE.md 使用旧版 `docker-compose` 语法，README.md 使用新版 `docker compose`
- **端口冲突**: `docker-compose.yml` 将 Grafana 映射到 3000 端口，与 Next.js 默认端口冲突。代码注释和 README 提到前端用 3001，但 START_HERE.md 和 ENGINEERING.md 从未说明此冲突
- **Redis 健康检查**: `docker-compose.yml` 中 Redis 配置了密码（`--requirepass`），但 healthcheck 命令 `redis-cli ping` 未传密码参数，健康检查会失败
- **项目状态**: START_HERE.md 标注"Phase 0 完成，Phase 1 准备中"，实际代码已远超此阶段

---

## 3. 关键文档质量评估

### 3.1 README.md — 评分: 3/5

**优点**: 项目定位清晰，技术栈描述完整，快速启动流程有基本骨架。

**问题**:
- 2 个断链（`docs/API.md`、`docs/DEPLOYMENT.md`）
- 3 个不存在的脚本命令
- 快速启动流程未提及 `API_TOKEN`（强制变量）
- Python 版本信息与代码不一致
- "backtesting.py"被列为核心依赖库，但项目使用自研回测引擎

### 3.2 架构文档 — 评分: 4/5

**优点**: 系统分层清晰，组件关系描述准确，策略引擎和风控架构的设计文档质量高。

**问题**: ENGINEERING.md 中部分代码示例引用了已重构或不存在的模块（`database.py`、`agent/interface.py`、`agent/trigger.py`），测试结构描述与实际 tests/ 目录不匹配。

### 3.3 运维手册 — 评分: 4/5

**优点**: 覆盖了监控、告警、日志管理等运维场景。

**问题**: 缺少 incident response 的标准流程（STRIDE 威胁模型在审计报告中，未转化为运维 runbook）。

### 3.4 故障排查文档 — 评分: 3.5/5

**优点**: 覆盖了常见后端问题。

**问题**: 缺少前端故障场景和 WebSocket 连接问题的排查指引。

### 3.5 `.env.example` — 评分: 2/5

**优点**: 大部分变量有注释说明。

**问题**:
- 缺少 `API_TOKEN`（API 强制变量）
- 包含大量 `config.py` 从未读取的变量（GRAFANA_*、TELEGRAM_*、EMAIL_*、OPENAI_*、ANTHROPIC_*、OKEX_* 等），制造噪音
- 部分变量仅被 `docker-compose.yml` 使用而非 Python 代码，但无标注区分

### 3.6 API 文档 — 评分: 0/5

**不存在**。README 中的链接指向空文件。18 个 API 端点（含 WebSocket）无任何外部文档。

### 3.7 部署文档 — 评分: 0/5

**不存在**。README 中的链接指向空文件。无反向代理/TLS 配置说明、无生产环境部署 checklist、无 CI/CD 流程文档。

### 3.8 安全文档 — 评分: 1/5

**不存在独立的 SECURITY.md**。安全审计工作（OWASP + STRIDE）已体现在 `deliverables/` 和 `.gstack/` 中，但：
- 无面向用户的安全策略声明
- 无漏洞报告流程
- 审计发现缺少跟踪机制（32 项发现未转化为 issue 或 checklist）

---

## 4. 缺失文档清单（按优先级）

### 上线前必须补充

| 优先级 | 缺失文档 | 理由 |
|-------|---------|------|
| P0 | `docs/API.md` | README 断链，前端开发者/集成方无法了解接口契约 |
| P0 | `docs/DEPLOYMENT.md` | README 断链，运维人员无法执行生产部署 |
| P0 | `.env.example` 补全 `API_TOKEN` | 快速启动流程断裂，新用户无法认证 |
| P1 | `SECURITY.md` | 无安全策略、无漏洞报告流程，不符合开源/商业项目基本安全规范 |
| P1 | `CHANGELOG.md` | 无变更追踪，上线后版本管理缺少依据 |

### 上线后 Sprint 内补充

| 优先级 | 缺失文档 | 理由 |
|-------|---------|------|
| P2 | 反向代理/TLS 配置指南 | 生产环境必须 HTTPS，当前无任何 Nginx/Caddy 配置 |
| P2 | 告警规则与 Runbook | 运维手册描述了监控框架但无具体告警阈值和响应流程 |
| P2 | 数据备份与恢复方案 | TimescaleDB 数据持久化无备份策略 |
| P2 | 前端文档（README 或组件说明） | `frontend/` 目录无任何内联文档 |

---

## 5. 发现汇总

### HIGH（5 项，上线阻塞）

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| D-01 | `.env.example` 缺少 `API_TOKEN` | 快速启动流程完全断裂，新用户无法认证 API | 立即添加 `API_TOKEN=` 及说明 |
| D-02 | `docs/API.md` 不存在（README 断链） | API 接口无文档，前后端协作和集成受阻 | 基于 `app.py` 生成 OpenAPI/Swagger 或手写 API 文档 |
| D-03 | `docs/DEPLOYMENT.md` 不存在（README 断链） | 生产部署无标准流程，运维人员只能猜测 | 编写部署指南（含 Docker、TLS、DNS、健康检查） |
| D-04 | README/QUICK_REFERENCE 引用 5 个不存在的脚本 | 新用户按文档操作会连续遇到命令失败 | 删除无效引用或补充脚本 |
| D-05 | Python 版本文档(3.11)与构建配置(3.13)不一致 | 用户可能安装错误版本导致运行时失败 | 统一所有文档和配置到同一版本 |

### MEDIUM（8 项，建议修复）

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| D-06 | 环境变量命名三套体系 | 部署时变量名混乱，容易配错 | 统一命名，ENGINEERING.md 与 `.env.example` 对齐 |
| D-07 | Redis healthcheck 未传密码 | `docker-compose up` 后 Redis 健康检查失败 | 修改为 `redis-cli -a ${REDIS_PASSWORD} ping` |
| D-08 | ENGINEERING.md 描述不存在的源码模块 | 开发者参考时会困惑 | 更新代码示例以匹配实际模块 |
| D-09 | Grafana 3000 端口与前端冲突未文档化 | 新开发者不知道前端要用 3001 | 在 START_HERE.md 和 ENGINEERING.md 中说明 |
| D-10 | START_HERE.md 项目状态描述过时 | 误导对项目进展的判断 | 更新为当前实际阶段 |
| D-11 | 无 SECURITY.md | 缺少安全策略和漏洞报告流程 | 添加基础 SECURITY.md |
| D-12 | 无 CHANGELOG.md | 版本变更无追踪 | 创建并维护 CHANGELOG |
| D-13 | `docker-compose` vs `docker compose` 语法不一致 | 旧版 Docker 用户可能遇到兼容问题 | 统一为 v2 `docker compose` 语法 |

### LOW（5 项，可选修复）

| # | 问题 |
|---|------|
| D-14 | README 策略数量"8"与实际 9 个不一致 |
| D-15 | README 测试徽章数值"475"与 QA 报告"472"不一致 |
| D-16 | README 将 `backtesting.py` 列为核心库（项目使用自研引擎） |
| D-17 | CONTRIBUTING.md 引用不存在的 `tests/fixtures/` 目录 |
| D-18 | `src/` 和 `frontend/` 子目录无内联 README |

---

## 6. 行动清单

### P0 — 上线前必须完成

| # | 行动 | 负责方 | 预估 |
|---|------|--------|------|
| 1 | `.env.example` 添加 `API_TOKEN` 及说明 | 后端工程师 | 5 min |
| 2 | 编写 `docs/API.md`（或从 FastAPI 自动生成 OpenAPI 文档） | 后端工程师 | 2-4 h |
| 3 | 编写 `docs/DEPLOYMENT.md`（Docker 部署 + TLS + 健康检查） | DevOps | 2-3 h |
| 4 | 修复 README/QUICK_REFERENCE 中对不存在脚本的引用 | 技术文档 | 30 min |
| 5 | 统一 Python 版本描述（文档 → 3.13，或代码 → 3.11） | DevOps | 15 min |

### P1 — Sprint 内完成

| # | 行动 | 负责方 | 预估 |
|---|------|--------|------|
| 6 | 统一环境变量命名体系，消除三套命名 | 后端工程师 | 1-2 h |
| 7 | 修复 Redis healthcheck 密码问题 | DevOps | 5 min |
| 8 | 更新 ENGINEERING.md 中过时的代码示例 | 后端工程师 | 1 h |
| 9 | 添加 `SECURITY.md`（安全策略 + 漏洞报告流程） | 安全工程师 | 30 min |
| 10 | 创建 `CHANGELOG.md` | 技术文档 | 30 min |
| 11 | 补充 START_HERE.md/ENGINEERING.md 中的端口冲突说明 | 后端工程师 | 10 min |

---

## 7. 结论

项目文档在架构设计和开发规划层面投入充分，但距离**上线就绪**仍有明确差距。核心问题是文档与代码的同步维护不足——项目经历了多轮迭代和重构，但文档未能同步更新，导致引用断链、命令失效、变量名分裂等问题累积。

建议按上述 P0 行动清单优先修复 5 项阻塞问题（预估 1 个工作日），然后进入 P1 修复。修复后文档可作为可靠的上线依据。

---

> 本报告基于项目源码与文档的逐项交叉验证生成，覆盖 153 个文档文件与全部关键代码路径。
