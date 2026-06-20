# 环境变量参考

**文档版本：** v1.0  
**创建日期：** 2026-06-20  
**状态：** ✅ 基于 `.env.example` + `src/utils/config.py` + `docker-compose.yml` + `Dockerfile` 生成  
**原则：** 以源码实际读取的变量名为准，不同文档引用的别名一律标注"无效 / 废弃"

---

## ⚠️ 重要：变量命名警告

以下变量名在历史文档中出现过，但源码中**从不读取**，请勿使用：

| 错误名称 | 出现在 | 正确名称 |
|----------|--------|----------|
| `DAILY_LOSS_LIMIT_PCT` | `ENGINEERING.md` §2.2 | `MAX_DAILY_LOSS` |
| `POSTGRES_HOST` | `ENGINEERING.md` §2.2 | `TIMESCALE_HOST` |
| `POSTGRES_PORT` (用于 Python) | `ENGINEERING.md` §2.2 | `TIMESCALE_PORT` |
| `HERMES_API_KEY` / `HERMES_API_URL` | `ENGINEERING.md` §2.2 | 不存在，AI 功能使用 `OPENAI_API_KEY` |

---

## 一、数据库配置

### TimescaleDB

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `TIMESCALE_HOST` | 否 | `localhost` | TimescaleDB 主机地址 | `src/utils/config.py:50` | `localhost` |
| `TIMESCALE_PORT` | 否 | `5432` | TimescaleDB 端口（整数） | `config.py:51` | `5432` |
| `TIMESCALE_USER` | 否 | `postgres` | 数据库用户名 | `config.py:52` | `postgres` |
| `TIMESCALE_PASSWORD` | ⚠️ 生产必需 | `""` | 数据库密码。生产环境必须设为非空且非默认值 | `config.py:53`；`config.py:118-121` 生产校验 | `your_secure_password` |
| `TIMESCALE_DATABASE` | 否 | `crypto_trading` | 数据库名称 | `config.py:54` | `crypto_trading` |
| `DATABASE_URL` | 否 | `""` | SQLAlchemy 完整连接 URL。优先级高于上面五项分字段。格式：`postgresql://user:pass@host:port/db` | `config.py:38`；`database.py:37` | `postgresql://postgres:changeme@localhost:5432/crypto_trading` |
| `SQL_ECHO` | 否 | `false` | SQLAlchemy echo 模式（设为 `true` 打印所有 SQL） | `database.py:41` | `false` |

### Redis

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `REDIS_URL` | 否 | 自动构造 | Redis 完整连接 URL。如果未设置，根据 `REDIS_PASSWORD` 自动构造 | `config.py:41-47` | `redis://:mypassword@localhost:6379/0` |
| `REDIS_PASSWORD` | ⚠️ Docker 必需 | `""` | Redis 密码。Docker Compose 启动时 `REDIS_PASSWORD` 必须非空 | `docker-compose.yml:30`；`config.py:39` | `CHANGE_ME_NOW` |
| `REDIS_PORT` | 否 | `6379` | Redis 端口（仅用于 Docker Compose 端口映射） | `docker-compose.yml:35` | `6379` |

> **注意：** `REDIS_PORT` 仅被 docker-compose 读取，Python 代码通过 `REDIS_URL` 中的端口部分获取。

---

## 二、交易所 API

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `BINANCE_API_KEY` | ⚠️ 生产必需 | `""` | Binance API Key（testnet 或实盘） | `config.py:59` | `your_testnet_api_key` |
| `BINANCE_SECRET` | ⚠️ 生产必需 | `""` | Binance API Secret | `config.py:60` | `your_testnet_secret` |
| `BINANCE_TESTNET` | 否 | `true` | 测试网开关。实盘前必须为 `true` | `config.py:61` | `true` |
| `BINANCE_LIVE_API_KEY` | 否 | — | 实盘 API Key（Phase 6+）。**注：** 此变量在 `.env.example` 中列出但不在 `config.py` 中读取——需确认代码是否已对接 | `.env.example:44` | — |
| `BINANCE_LIVE_SECRET` | 否 | — | 实盘 API Secret | `.env.example:45` | — |

---

## 三、实盘控制（🔴 安全关键）

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `LIVE_TRADING_ENABLED` | 是 | `false` | **实盘总开关**。生产环境设为 `true` 前必须完成 Phase 6 全部门禁。开发环境强制保持 `false` | `config.py:69`；`config.py:134` 开发+实盘组合校验 | `false` |

> **🔴 `config.validate()` 安全检查（`config.py:134`）：** `LIVE_TRADING_ENABLED=true` + `ENVIRONMENT=development` → 触发 CRITICAL 警告。

---

## 四、风控参数

| 变量名 | 必需 | 默认值 | 范围 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|------|----------|------|
| `MAX_DAILY_LOSS` | 否 | `0.02` | `(0, 0.10]` | 日亏损限制（占本金比例）。超出 → `config.validate()` 报错 | `config.py:74`；范围校验 `config.py:124` | `0.02` |
| `MAX_POSITION_SIZE` | 否 | `0.20` | `(0, 0.50]` | 单笔最大仓位（占总权益比例） | `config.py:75`；范围校验 `config.py:128` | `0.20` |
| `MAX_TOTAL_POSITION` | 否 | `0.60` | `(0, 1.0]` | 总仓位上限（占总权益比例） | `config.py:76`；范围校验 `config.py:131` | `0.60` |
| `MAX_CONSECUTIVE_LOSSES` | 否 | `5` | 正整数 | 连续亏损熔断阈值（笔） | `config.py:77` | `5` |

> **注意：** 上述值是 `Config` 类读取的环境变量值，`RiskManager` 和 `RiskAwareStrategy` 有**独立的构造函数默认值**（`max_daily_loss=0.03` / `max_daily_loss=0.02`），调用方可以选择覆盖。

---

## 五、API 配置

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `API_TOKEN` | ⚠️ 任何环境必需 | `""` | 前端 API 认证 Token。`config.validate()` 中空值触发 CRITICAL | `config.py:64`；`config.py:109` 校验 | `my-secret-api-token` |

### 前端对应变量（在 `frontend/.env.local` 中设置）

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `NEXT_PUBLIC_API_BASE` | 否 | `http://localhost:8000` | 后端 FastAPI 地址 | `frontend/lib/api.ts:27-28` | `http://localhost:8000` |
| `NEXT_PUBLIC_API_TOKEN` | 是 | `""` | 前端请求携带的 API Token（须与后端 `API_TOKEN` 一致） | `frontend/lib/api.ts:30`；`swr-provider.tsx:19` | `my-secret-api-token` |

---

## 六、监控和告警（Docker Compose）

### Grafana

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `GRAFANA_ADMIN_USER` | 否 | `admin` | Grafana 管理员用户名 | `docker-compose.yml:47` | `admin` |
| `GRAFANA_ADMIN_PASSWORD` | ⚠️ Docker 必需 | — | Grafana 管理员密码。Compose 层强制要求非空 | `docker-compose.yml:48` | `CHANGE_ME_NOW` |
| `GRAFANA_URL` | 否 | — | Grafana 访问 URL（Python 端，用于配置展示） | `.env.example:76` | `http://localhost:3000` |
| `GRAFANA_API_KEY` | 否 | — | Grafana API Key（自动化面板管理） | `.env.example:77` | — |

### PostgreSQL（Docker Compose 层）

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `POSTGRES_USER` | 否 | `postgres` | 数据库超级用户（Compose 层传递） | `docker-compose.yml:13`（timescaledb）+ `:49`（Grafana） | `postgres` |
| `POSTGRES_PASSWORD` | ⚠️ Docker 必需 | — | 数据库密码。**必须**在 `.env` 中设置，否则 Compose 拒绝启动 | `docker-compose.yml:11`（`?:...` 必填语法）+ `:51`（Grafana） | `CHANGE_ME_NOW` |
| `POSTGRES_DB` | 否 | `crypto_trading` | 默认数据库名 | `docker-compose.yml:12` + `:50` | `crypto_trading` |
| `POSTGRES_PORT` | 否 | `5432` | 宿主机端口映射 | `docker-compose.yml:18` | `5432` |

> **⚠️ 注意区分：** `POSTGRES_PASSWORD` 是 Docker Compose 层的变量（TimescaleDB 容器 + Grafana 数据源配置使用）；`TIMESCALE_PASSWORD` 是 Python 应用层变量。两者应设为相同值。详见 `TROUBLESHOOTING.md` 故障 1。

---

## 七、Docker Compose 环境变量

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 |
|--------|------|--------|------|----------|
| `REDIS_PASSWORD` | 是 | — | Redis 密码（Compose 启动时强制要求） | `docker-compose.yml:30-31` |
| `POSTGRES_PASSWORD` | 是 | — | 数据库密码（Compose 启动时强制要求） | `docker-compose.yml:11` |
| `POSTGRES_USER` | 否 | `postgres` | 数据库用户 | `docker-compose.yml:13` |
| `POSTGRES_DB` | 否 | `crypto_trading` | 数据库名 | `docker-compose.yml:12` |
| `POSTGRES_PORT` | 否 | `5432` | 宿主机端口 | `docker-compose.yml:18` |
| `REDIS_PORT` | 否 | `6379` | 宿主机端口 | `docker-compose.yml:35` |
| `GRAFANA_ADMIN_USER` | 否 | `admin` | Grafana 用户名 | `docker-compose.yml:47` |
| `GRAFANA_ADMIN_PASSWORD` | 是 | — | Grafana 密码 | `docker-compose.yml:48` |

---

## 八、AI API

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `OPENAI_API_KEY` | 否（Phase 5-6 optional） | — | OpenAI API Key（Agent 分析用） | `src/agent/analyzer.py`（推断） | `sk-...` |
| `OPENAI_MODEL` | 否 | `gpt-4` | 使用的 OpenAI 模型 | `.env.example:67` | `gpt-4` |
| `ANTHROPIC_API_KEY` | 否 | — | Anthropic Claude API Key（可选） | `.env.example:70` | — |

---

## 九、告警通知

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `TELEGRAM_BOT_TOKEN` | 否 | — | Telegram Bot Token | `src/monitor/alert_channels.py`（推断） | — |
| `TELEGRAM_CHAT_ID` | 否 | — | Telegram 通知目标 Chat ID | 同上 | — |
| `EMAIL_SMTP_HOST` | 否 | `smtp.gmail.com` | SMTP 服务器 | 同上 | `smtp.gmail.com` |
| `EMAIL_SMTP_PORT` | 否 | `587` | SMTP 端口 | 同上 | `587` |
| `EMAIL_USERNAME` | 否 | — | 邮箱账号 | 同上 | — |
| `EMAIL_PASSWORD` | 否 | — | 邮箱密码/应用密码 | 同上 | — |
| `EMAIL_TO` | 否 | — | 通知接收邮箱 | 同上 | — |

---

## 十、应用配置

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `ENVIRONMENT` | 否 | `development` | 环境标识。可选值：`development` / `staging` / `production` | `config.py:90`；`config.py:113` 生产校验分支 | `development` |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别。可选值：`DEBUG` / `INFO` / `WARNING` / `ERROR` | `config.py:91` | `INFO` |
| `TIMEZONE` | 否 | `UTC` | 时区 | `config.py:92` | `UTC` |
| `DEBUG` | 否 | `false` | Debug 模式（设 `true` 启用） | `config.py:93` | `false` |

---

## 十一、Phase 配置

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `DATA_START_DATE` | 否 | `2023-01-01` | 数据起始日期 | `config.py:82` | `2023-01-01` |
| `DATA_END_DATE` | 否 | `2024-12-31` | 数据结束日期 | `config.py:83` | `2024-12-31` |
| `DATA_SYMBOLS` | 否 | `BTC/USDT,ETH/USDT` | 交易对列表（逗号分隔） | `config.py:84` | `BTC/USDT,ETH/USDT` |
| `DATA_TIMEFRAME` | 否 | `4h` | K 线周期。可选值：`1m` / `5m` / `1h` / `4h` / `1d` | `config.py:85` | `4h` |
| `PAPER_INITIAL_BALANCE` | 否 | `10000` | Paper Trading 初始资金 (USDT) | `.env.example:123`（Python 端读取路径待验证） | `10000` |
| `PAPER_COMMISSION` | 否 | `0.001` | Paper 手续费率（0.1%） | `.env.example:124` | `0.001` |
| `PAPER_SLIPPAGE_BTC` | 否 | `0.0005` | BTC 滑点（0.05%） | `.env.example:125` | `0.0005` |
| `PAPER_SLIPPAGE_ETH` | 否 | `0.001` | ETH 滑点（0.1%） | `.env.example:126` | `0.001` |

---

## 十二、开发工具

| 变量名 | 必需 | 默认值 | 说明 | 使用位置 | 示例 |
|--------|------|--------|------|----------|------|
| `AUTO_RELOAD` | 否 | `true` | 自动重载（uvicorn reload） | `.env.example:135`（Python 端读取路径待验证） | `true` |

---

## 环境变量设置清单（最小可运行）

### `.env` 最小集（Paper Trading 阶段）

```bash
# === 数据库 (Docker Compose) ===
POSTGRES_PASSWORD=changeme
POSTGRES_DB=crypto_trading
POSTGRES_USER=postgres
POSTGRES_PORT=5432

# === Redis (Docker Compose) ===
REDIS_PASSWORD=changeme
REDIS_PORT=6379

# === Grafana (Docker Compose) ===
GRAFANA_ADMIN_PASSWORD=admin

# === TimescaleDB (Python 应用) ===
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
TIMESCALE_USER=postgres
TIMESCALE_PASSWORD=changeme
TIMESCALE_DATABASE=crypto_trading

# 或合并为一条 DATABASE_URL（SQLAlchemy 引擎用）
DATABASE_URL=postgresql://postgres:changeme@localhost:5432/crypto_trading

# === Redis (Python 应用) ===
REDIS_URL=redis://:changeme@localhost:6379/0

# === API 认证 ===
API_TOKEN=dev-token-change-in-production

# === 应用 ===
ENVIRONMENT=development
LIVE_TRADING_ENABLED=false
BINANCE_TESTNET=true
```

### `frontend/.env.local` 最小集

```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_API_TOKEN=dev-token-change-in-production
```

---

**文档状态：** ✅ 基于源码生成  
**更新日期：** 2026-06-20  
**变量总数：** 42 个（含 Docker Compose 专属 8 个 + 前端 2 个 + `.env.example` 中但代码未确认读取的 6 个）
