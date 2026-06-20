# 上线前全检报告 — 加密交易系统

**日期**：2026-06-20
**场景**：上线前检查（代码审查 + 安全审计 + QA测试）
**参与成员**：产品评审员 + 安全官 + QA与发布

---

## 📌 TL;DR（执行摘要）

- 整体结论：🔴 **不通过** — 存在 6 项阻塞性 CRITICAL，上线前必须修复（经复核修正，原 R-06 Docker 版本定性夸大已降级为 HIGH）
- 阻塞项数量：6（4 项三方交叉验证 + 1 项复核升级 [R-04 回撤熔断失忆] + 1 项 QA 独立发现）
- 后端核心质量较高（472 测试通过，83% 覆盖率，策略引擎/风控架构优秀），但 **安全防线存在系统性缺口**（无认证传输、无限速、无安全响应头）
- 建议修复 P0 阻塞项（预估 1-2 天）后重新评审，通过后再上线

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| Go / No-Go | 🔴 **No-Go**（6 项 CRITICAL 阻塞上线，经复核修正） |
| 严重度分布 | 🔴 6 / 🟠 14 / 🟡 17 / 🟢 9（亮点） |
| 关键行动项 | 6 条 P0 + 7 条 P1 |
| 建议负责人 | 后端工程师（P0 后端修复）、前端工程师（认证头）、安全工程师（CSP/HSTS/限速） |

---

## 1. 各成员核心结论

### 🔍 产品评审员（代码审查）
- 核心判断：代码架构设计优秀——分层清晰、接口抽象合理、策略引擎与风控逻辑质量高。但 **4 个 CRITICAL** 集中在前端认证缺口和异常处理脆性上，"代码写得好不代表可以安全上线"。
- 关键建议：优先修复 API_TOKEN 500→503、WebSocket 静默吞异常、RiskManager reset() 状态恢复脆性、前端缺失认证头四项，再处理 8 个 WARNING。

### 🛡️ 安全官（OWASP + STRIDE 审计）
- 核心判断：安全评分 **C+**，核心交易安全（熔断、常数时间比较、沙盒隔离）做得好，但 **Web 安全防线几乎空白**——无 CSP/HSTS、全 API 无限速、前端不传 token。这意味着一个脚本小子用 curl 就能洪水 `/agent/analyze`。
- 关键建议：修复前端 token 传输、添加全 API 速率限制、部署 CSP 和 HSTS 响应头。这三项是"实盘部署前必须完成"的铁门槛。

### ✅ QA与发布（QA测试与上线就绪）
- 核心判断：后端 472 测试通过、0 失败、83% 覆盖率，核心逻辑质量可靠。但 **Docker 部署配置与运行时环境不匹配**（3.11 vs 3.13）是容器化部署的直接阻塞项。前端零测试是长期隐患。
- 关键建议：修复 Dockerfile Python 版本、为 `verify_api_token()` 补测、补充前端基础渲染测试。上线后逐步提升 API 端点覆盖率从 52% 到 80%。

---

## 2. 综合审查发现（去重合并后按严重度排序）

### 🔴 CRITICAL（阻塞上线，6 项）

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源 |
|---|--------|------|------|---------|------|------|
| R-01 | 🔴 | 安全 | `frontend/lib/api.ts:30-36` | **前端所有 fetch 请求不携带 X-API-Token 认证头**。后端 15/18 端点需要认证，前端大部分受保护端点返回 403；若 API_TOKEN 为空，后端返回 500 而非拒绝 | 在 `get()`/`PATCH`/`POST` 中注入 `X-API-Token` header，WebSocket URL 添加 token；SWRProvider fetcher 同步添加 | 评审员#4 + 安全官 F-001 + QA#8 |
| R-02 | 🔴 | 安全 | `src/api/app.py`（全局） | **全 API 零速率限制**。`/agent/analyze`、`/strategies/create-grid` 可被单 IP 洪水攻击，触发大量计算 | 使用 slowapi 添加：全局 50 req/s，agent 类端点 10 req/min | 评审员#6 + 安全官 F-003 |
| R-03 | 🔴 | 安全/运维 | `src/api/app.py:157-158` | **WebSocket 异常静默吞没**：`except Exception: pass` 吞掉 `asyncio.CancelledError`、`SystemExit` 等致命异常，bug 无法观测 | 区分 `WebSocketDisconnect`（预期）与 `Exception`（需 `logger.exception`） | 评审员#2 |
| R-04 | 🔴 | 安全/交易 | `src/execution/risk_manager.py:271-279` | **reset() 锁内脆弱状态恢复 + 回撤熔断失忆**：`_init_state()` 清零所有变量后手动恢复防抖计数器，未来新增字段会静默丢失。更严重的是 `peak_equity` 和 `cumulative_pnl` 在 reset 时被重置为初始值——一个已亏损 14% 的策略 reset 后再亏 14%，熔断器只记录 14% 而非真实的 ~28% 累计回撤，等于绕过 15% 熔断线 | 将防抖计数器从 `_init_state()` 中分离；reset 时保留 `peak_equity` 和 `cumulative_pnl` 不重置 | 评审员#3 + 复核升级 |
| R-05 | 🔴 | 安全 | `src/api/app.py:128-137` | **WebSocket 认证 token 通过 URL query parameter 传递**，token 出现在服务器日志、代理日志、浏览器历史中 | 改为 WebSocket 升级握手后首条消息认证：`{"type":"auth","token":"..."}` | 评审员#9 + 安全官 F-002 |
| R-06 | 🔴 | 测试 | `frontend/` 全局 | **前端零测试覆盖**：无任何测试框架、测试文件。SWR 数据获取、错误状态、UI 组件均未验证。加密交易系统的前端显示错误数据将导致财务损失 | 至少为 `useStrategies` hook、AccountCards、StrategyControls 添加渲染测试（vitest + testing-library） | 评审员#18 + QA#2 |

### 🟠 HIGH（高优先级，14 项）

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源 |
|---|--------|------|------|------|------|------|
| R-07 | 🟠 | 部署 | `Dockerfile:1` + `docker-compose.yml:5` | **开发者本地 Python 3.13 与 Docker 镜像 3.11 不一致**（项目正式配置 pyproject.toml target-version=py311 均指向 3.11，不存在"项目要求 3.13"的契约）。实际风险为：本地通过的代码在容器中可能因 stdlib 或语法差异失败 | 确认项目目标 Python 版本（3.11 或 3.13）并统一所有环境（Dockerfile、pyproject.toml、开发者本地） | 评审员#13 + QA#1（经复核降级） |
| R-08 | 🟠 | 安全 | FastAPI middleware 缺失 | **无 CSP 响应头** — XSS 最重要防线缺失 | 添加 Content-Security-Policy: default-src 'self' | 安全官 F-004 |
| R-09 | 🟠 | 安全 | FastAPI middleware 缺失 | **无 HSTS 响应头** — 中间人降级攻击面 | 添加 Strict-Transport-Security: max-age=31536000 | 安全官 F-007 |
| R-10 | 🟠 | 安全 | `src/api/app.py:82-90` | **Health endpoint 泄露内部状态**（ws_connected、ws_clients、cache_backend），攻击者可侦查架构 | `/health` 仅返回 `{"status":"ok"}`，详细状态移至需认证的 `/health/detailed` | 评审员#5 |
| R-11 | 🟠 | 安全 | `src/api/app.py:71-79` | **API_TOKEN 未配置时返回 HTTP 500 而非 503**，触发监控告警并暴露部署状态 | 用 `config.API_TOKEN is None` 显式判断，返回 `503 Service Unavailable` | 评审员#1 + 安全官 F-009 |
| R-12 | 🟠 | 安全 | `src/execution/risk_manager.py:144-205` | **record_fill() 锁范围不足**：`with self._lock:` 仅保护 `profit = trade.get("profit")` 一行，后续 `daily_pnl`、`cumulative_pnl`、`consecutive_losses` 修改及熔断检查均在锁外，存在竞态条件 | 将整个持仓更新 + 熔断检查逻辑纳入锁范围 | 评审员#7 + 复核确认 |
| R-13 | 🟠 | 安全 | `src/execution/paper_broker.py:133-136` | **Decimal(str(float)) 精度陷阱**：`Decimal(str(0.1*0.2))` 产生 `0.020000000000000004`，累计误差影响熔断判断 | 全部用 Decimal 运算，不经 float 中转；或用 `round(..., 8)` | 评审员#10 |
| R-14 | 🟠 | 架构 | `src/api/service.py:135-207` | **多策略路径缺少 RiskManager**。8 策略都盈利但账户因手续费/滑点累积亏损时，账户级保护缺失 | `MultiStrategyRunner` 构造时注入 `RiskManager` 实例 | 评审员#11 |
| R-15 | 🟠 | 安全 | `src/strategy/buyhold.py` | **BuyAndHold 策略未继承 RiskAwareStrategy**，8 个策略中唯一没有熔断保护的 | 让 BuyAndHold 继承 RiskAwareStrategy 基类 | 安全官 F-014 |
| R-16 | 🟠 | 安全 | `src/api/app.py`（CORS 配置） | **CORS 允许 localhost 范围**，生产部署需收紧为具体域名 | 从环境变量读取 ALLOWED_ORIGINS，默认仅生产域名 | 安全官 F-008 |
| R-17 | 🟠 | 测试 | `src/api/app.py` | **verify_api_token() 无任何测试覆盖**。无效/缺失 token 的 403/500 路径从未执行 | 添加 test_verify_api_token.py 覆盖所有认证路径 | QA#3 |
| R-18 | 🟠 | 安全/配置 | 项目根目录 | **`.env` 文件存在于磁盘**（虽为占位值，但存在误提交真实凭证风险） | 从 git 历史中移除，仅保留 `.env.example`，添加 `.env` 到 `.gitignore` | 安全官 F-005 |
| R-19 | 🟠 | 部署 | `docker-compose.yml:67-82` | **trading_system 服务被注释**，缺少容器化部署方案 | 取消注释并配置 `depends_on` + `healthcheck` | 评审员#14 + QA |
| R-20 | 🟠 | 安全/并发 | `src/utils/database.py` | **psycopg2 原始连接非线程安全**：`DatabaseManager` 持有单个 `psycopg2` 连接，`get_cursor()` 无锁生成游标。FastAPI 异步/多线程环境下与 `MetricsWriter.write_records()` 并发执行可能抛出 `InterfaceError` 或导致数据损坏 | 为原始连接添加 `threading.Lock` 保护，或完全迁移到 SQLAlchemy 连接池 | 复核新增 |

### 🟡 MEDIUM（建议修复，17 项）

| # | 问题 | 来源 |
|---|------|------|
| R-21 | 双 Redis 连接池浪费连接资源（CacheLayer + DatabaseManager） | 评审员#12 |
| R-22 | service._build_state() 每次启动完整回放 8 策略，启动延迟高 | 评审员#8 |
| R-23 | 策略注册表 try/except ImportError 硬编码 + 动态发现双重策略，不可同时测试 | 评审员#16 |
| R-24 | WebSocket 心跳用硬编码 JSON 字符串而非 json.dumps | 评审员#15 |
| R-25 | tickers() 回退路径缺少最内层 try/except 保护 | 评审员#17 |
| R-26 | ccxt 客户端 DCL 在 Python 中非线程安全 | 评审员#22 |
| R-27 | 缺少请求级 trace ID / correlation ID | 评审员#21 |
| R-28 | Grafana 密码用环境变量而非 Docker secrets | 安全官 F-006 |
| R-29 | TimescaleDB/Redis 端口绑定到 0.0.0.0 | 安全官 F-015 |
| R-30 | Agent analyze 的 phase 字段无输入约束 | 安全官 F-010 |
| R-31 | API 端点覆盖率仅 52%（多策略/Agent/创建网格等端点未测试） | QA#4 |
| R-32 | 配置模块覆盖率仅 54%（生产环境关键路径未测试） | QA#5 |
| R-33 | 数据库模块覆盖率仅 47%（DB 连接/查询未测试） | QA#6 |
| R-34 | Dockerfile build stage 缺少非 root 用户（pip install 以 root 执行） | 评审员#19 |
| R-35 | requirements.txt 缺少 fastapi/uvicorn（已使用但被注释） | QA |
| R-36 | Dockerfile 日志级别 valid_levels 大小写风格不统一 | 评审员#20 |
| R-37 | 仓位限制常量 MAX_POSITION_PER_TRADE/MAX_TOTAL_POSITION = 1.0 (100%)，模拟环境可接受但 live 配置沿用会导致单笔交易使用全部资金 | 复核新增 |

---

## ✅ 行动清单

### P0 — 上线前必须完成（阻塞项）

| # | 行动 | 负责方 | 预估 |
|---|------|--------|------|
| 1 | 前端 fetch/WebSocket 统一注入 X-API-Token 认证头 | 前端工程师 | 30 min |
| 2 | 全 API 添加速率限制（slowapi，全局 50 req/s + agent 10/min） | 后端工程师 | 2 h |
| 3 | 修复 WebSocket 异常静默吞没（区分预期/非预期异常） | 后端工程师 | 10 min |
| 4 | 重构 RiskManager reset() — 防抖计数器从 _init_state() 分离 + 保留 peak_equity/cumulative_pnl | 后端工程师 | 1 h |
| 5 | WebSocket 认证从 URL query → 首条消息认证 | 后端 + 前端 | 1 h |
| 6 | verify_api_token() 添加完整测试覆盖 | 后端工程师 | 30 min |

### P1 — Sprint 内完成（高优）

| # | 行动 | 负责方 | 预估 |
|---|------|--------|------|
| 7 | 确认项目目标 Python 版本并统一所有环境（Dockerfile、pyproject.toml、本地） | DevOps | 30 min |
| 8 | 部署 CSP 响应头（default-src 'self'） | 后端/安全 | 30 min |
| 9 | 部署 HSTS 响应头（max-age=31536000） | 后端/安全 | 10 min |
| 10 | Health endpoint 去内部状态泄露，拆分为 /health + /health/detailed | 后端 | 15 min |
| 11 | 多策略路径注入 RiskManager 实例 | 后端 | 1 h |
| 12 | BuyAndHold 继承 RiskAwareStrategy 基类 | 后端 | 30 min |
| 13 | DatabaseManager psycopg2 原始连接添加线程安全保护（加锁或迁移到连接池） | 后端 | 1 h |

---

## 🔒 阻塞项清单（No-Go 原因）

上线前必须解决的 6 个 CRITICAL，缺一不可：

1. **R-01** — 前端认证头缺失：当前前端对受保护端点返回 403，仪表盘不可用
2. **R-02** — 全 API 零限速：`/agent/analyze` 可被洪水攻击耗尽算力
3. **R-03** — WebSocket 静默吞异常：Bug 不可观测，生产故障无从排查
4. **R-04** — RiskManager reset() 回撤熔断失忆：reset 后 `peak_equity`/`cumulative_pnl` 被清零，15% 熔断线可被绕过
5. **R-05** — WebSocket token 在 URL 中：token 出现在所有日志中，credential leak
6. **R-06** — 前端零测试：显示错误数据的交易 UI 将导致财务损失

## 🔄 回滚预案

- 所有修复应在 `pre-launch-fixes` 分支进行
- 每完成一个 P0 修复，运行 `pytest tests/ -x --timeout=120` 确认回归
- 如修复后出现意外回归，立即 revert 对应 commit
- 上线当日保留前一版本的 Docker 镜像作为快速回滚目标

---

## ⚠️ 待完善 / 已知局限

- **前端测试基础设施缺失**：即使 P0 修复前端认证头，前端仍无自动化回归测试，建议上线后（Sprint 2）搭建 vitest + testing-library
- **API 端点覆盖率仅 52%**：多策略/Agent/网格创建等端点未经集成测试，建议上线后逐步提升至 80%
- **Trace ID 体系缺失**：生产排障依赖请求级 trace ID，建议 Sprint 2 添加 FastAPI middleware 注入 `X-Request-ID`
- **安全响应头不足**：CSP/HSTS 之外，还建议添加 X-Content-Type-Options、X-Frame-Options、Referrer-Policy

---

## 📚 成员产出索引

- gstack-product-reviewer（产品评审员）原始产出：team chat 对话中 — 4 CRITICAL / 8 WARNING / 10 INFO，含全量文件级代码走读
- gstack-security-officer（安全官）原始产出：team chat 对话中 + `.gstack/security-audit-history/audit-2025-06-20-220000.md` — OWASP Top 10 + STRIDE 全威胁建模，17 项发现
- gstack-qa-lead（QA与发布）原始产出：team chat 对话中 + `deliverables/qa-report-pre-launch.md` — 472 测试通过，83% 覆盖率，健康分 78/100
- 复核文档：`deliverables/gstack/pre-launch-review-rebuttal-2026-06-20.md` — 逐项源码验证 + 2 项新发现

---

> 本报告由软件工坊 AI 协作生成（产品评审员 + 安全官 + QA与发布 三线并行审查），经源码逐项复核后修订（v2），关键决策请由工程负责人复核。
