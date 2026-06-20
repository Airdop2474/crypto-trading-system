# 操作手册（启动 / 停止）

**文档版本：** v1.0
**创建日期：** 2026-06-16
**状态：** ✅ 已批准
**对应门禁：** `LIVE_TRADING_CHECKLIST.md` §5「文档完整 → 操作手册」

---

## 目的

定义系统的**标准启动、运行、停止**流程，供日常运维与实盘前置（Phase 6）使用。

**配套文档：** 故障排查见 `TROUBLESHOOTING.md`；实盘门禁见 `LIVE_TRADING_CHECKLIST.md`。

> ⚠️ 当前阶段 `LIVE_TRADING_ENABLED=false`、`BINANCE_TESTNET=true`。本手册覆盖 **paper trading / 监控链路**；实盘启动须额外走 `LIVE_TRADING_CHECKLIST.md` 的双重确认。

---

## 0. 前置约定

所有 `python`/`pytest` 命令均假定：

```bash
# 1) 已在项目根目录（crypto-trading-system）
# 2) 项目根已加入 PYTHONPATH（脚本内部多已自动插入，手动跑模块时仍建议设）
#    Linux/macOS:
export PYTHONPATH=$(pwd)
#    Windows PowerShell: $env:PYTHONPATH = (Get-Location).Path
#    Windows CMD:        set PYTHONPATH=%cd%
```

数据库密码涉及**两层变量，需设为相同值**：`POSTGRES_PASSWORD` 是 Docker Compose 层变量（TimescaleDB 容器 + Grafana 数据源使用，compose 启动时强制要求，缺失即拒启）；`TIMESCALE_PASSWORD` 是 Python 应用层变量（`src/utils/config.py` 读取）。生产环境两者都必须改掉默认值。详见 `docs/reference/ENV_VARIABLE_REFERENCE.md` 与 `TROUBLESHOOTING.md` 故障 1。

---

## 1. 环境准备（首次 / 换机）

```bash
# 1. 安装依赖（Python 3.11+）
pip install -r requirements.txt

# 2. 准备 .env（从模板复制后填写）
cp .env.example .env

# 3. 体检：Python 版本 / 依赖 / .env / 配置 / 数据库 / 目录结构
python scripts/check_environment.py
```

`.env` 必填关键项：

| 变量 | 说明 | 当前阶段取值 |
|------|------|------|
| `TIMESCALE_PASSWORD` / `POSTGRES_PASSWORD` | 数据库密码（应用层 / Compose 层，两者设相同值） | `changeme`（对齐 compose 默认） |
| `BINANCE_API_KEY` / `BINANCE_SECRET` | 交易所 testnet 凭据 | testnet key（只读/现货） |
| `BINANCE_TESTNET` | 测试网开关 | `true`（实盘前强制） |
| `LIVE_TRADING_ENABLED` | **实盘总开关** | `false`（实盘前强制） |

> 完整变量见 `.env.example`。风控参数（`MAX_DAILY_LOSS` 等）有内置默认值，留空即用默认。

---

## 2. 启动基础设施（Docker）

```bash
# 启动 数据库 + Redis + Grafana
docker compose up -d

# 确认三个服务均 healthy / Up
docker compose ps
```

| 服务 | 容器名 | 端口 | 用途 |
|------|--------|------|------|
| `timescaledb` | crypto_trading_db | 5432 | 时序/业务库 |
| `redis` | crypto_trading_redis | 6379 | 缓存 |
| `grafana` | crypto_trading_grafana | 3000 | 监控面板 |

- **Grafana：** http://localhost:3000 （默认 `admin` / `admin`）
- **数据库初始化：** `config/sql/01_monitor_metrics.sql` 由容器**首次启动**自动执行（建 `monitor_metrics` 表）。若数据卷非空首启则不会重跑——表缺失时见 `TROUBLESHOOTING.md` 故障 5 手动补建。

---

## 3. 运行

### 3.1 生成数据（首次或数据缺失）

`run_paper_trading.py` 依赖 `data/raw/BTC_USDT_4h_osc_*.csv`：

```bash
python scripts/generate_oscillating_data.py
```

### 3.2 跑 Paper Trading（主链路）

```bash
python scripts/run_paper_trading.py
```

端到端流程：加载数据 → 网格策略 → PaperBroker 成交 → 生成报告 → 对账校验 → 指标落库到 `monitor_metrics`。

产出：
- `data/reports/paper_trading_result_*.json`
- `data/reports/paper_trading_report_*.md`

跑完后到 Grafana（:3000）查看权益/收益/风控时序。

### 3.3 数据质量链路（可选）

```bash
python scripts/run_data_pipeline.py   # 产出 data/reports/quality_*.{json,md}
```

---

## 4. 测试与验证

```bash
# 全量单测（必须加 -p no:asyncio，否则 pytest-asyncio 收集器冲突）
python -m pytest -p no:asyncio -q          # 基线：481 passed, 3 skipped（484 total）

# Grafana 端到端冒烟（写 12 条指标供面板读取）
export TIMESCALE_PASSWORD=changeme
python scripts/verify_grafana_e2e.py
```

> `pyproject.toml` **未**配置 `addopts`，所以 `-p no:asyncio` 必须每次手动带上。

---

## 5. 停止

```bash
# 停止运行中的脚本：前台 Ctrl+C（脚本无独立停止入口，跑完即退出）

# 停止基础设施（保留数据卷）
docker compose stop

# 停止并移除容器（保留数据卷；数据不丢）
docker compose down

# ⚠️ 连同数据卷一起删除（清空 DB/Grafana，慎用）
docker compose down -v
```

---

## 6. 风控暂停 / 紧急停止 / 恢复

风控状态机在 `src/execution/risk_manager.py`（`RiskManager`，状态 `ACTIVE / PAUSED / STOPPED`）。

| 动作 | 方法 | 状态流转 |
|------|------|---------|
| 查询能否交易 | `can_trade()` | True 仅当 `ACTIVE` |
| 是否被熔断暂停 | `is_paused()` | → `PAUSED` |
| 人工恢复 | `resume()` | `PAUSED → ACTIVE`（重置连亏/API 失败计数，保留当日盈亏） |
| 紧急停止 | `emergency_stop(reason)` | 任意 → `STOPPED` |
| 完全重置 | `reset()` | `STOPPED → ACTIVE` |

自动进入 `PAUSED` 的条件：连续亏损达上限、当日亏损超限、API 连续失败、数据异常（详见 `record_fill` / `record_api_failure` / `record_data_anomaly`）。

**恢复流程（人工）：** 查 `risk_mgr.events[-1]` 的 reason → 确认问题已解决 → `resume()`（或 `STOPPED` 时先 `reset()`）。实盘恢复须按 `LIVE_TRADING_CHECKLIST.md`「恢复流程」逐项确认。

---

**文档状态：** ✅ 已批准
**Phase：** Phase 6（实盘前置）
**更新日期：** 2026-06-16
