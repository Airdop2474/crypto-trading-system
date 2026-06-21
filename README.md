# Crypto Trading System

> 加密货币自动化量化交易系统 — 8 策略引擎 + AI 自进化 + Next.js 仪表盘

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue.svg)](https://www.typescriptlang.org/)
[![Tests](https://img.shields.io/badge/Tests-544%20functions%20·%2052%20files-green.svg)]()
[![Strategies](https://img.shields.io/badge/Strategies-8-blue.svg)]()
[![API](https://img.shields.io/badge/API-37%20endpoints-orange.svg)]()
[![Status](https://img.shields.io/badge/Status-Paper%20Trading-yellow.svg)]()

---

## 项目简介

集成 8 种交易策略的量化交易系统，支持回测、Paper Trading（模拟交易）和实盘交易。内置 AI 进化引擎，可基于 Walk-Forward 分析自动优化策略参数。前端基于 Next.js 16 + React 19 仪表盘，提供实时策略跑分、持仓管理、盈亏分析和进化历史。

### 核心特性

- **8 策略引擎** — Grid / RSI / MA / BuyHold / Donchian / Structure / SuperTrend / Reversal，统一继承 RiskAwareStrategy 基类
- **AI 自进化** — Walk-Forward 参数搜索 + LLM 解读（OpenAI / Anthropic / 本地规则回退） + 6 道安全校验 + 参数热替换
- **熔断风控** — 策略级 + 账户级双重熔断（连续亏损 / 日亏损 / 最大回撤），状态机驱动
- **事件驱动回测** — bar-by-bar 逐根 K 线，零前视偏差，含手续费 + 滑点成本模型
- **Paper Trading** — 完整模拟交易流程，实盘前硬门禁
- **实时仪表盘** — Next.js 16 + SWR + shadcn/ui，11 个页面覆盖策略跑分 / 持仓 / 盈亏 / 风控 / AI Agent
- **37 API 端点** — 行情、账户、策略、分析、风控、AI Agent、运行模式管理，含 WebSocket 实时推送
- **全栈容错** — 无 PostgreSQL → 内存回退，无 Redis → MemoryCache，无 LLM Key → 本地规则，无 Docker → 核心仍可运行

### 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.13, FastAPI, SQLAlchemy 2.0, pandas, numpy, ccxt |
| 前端 | Next.js 16, React 19, TypeScript 5.7, Tailwind 4, SWR, shadcn/ui |
| 数据库 | TimescaleDB (时序) + PostgreSQL (关系) + Redis (缓存) |
| AI | OpenAI GPT / Anthropic Claude / 本地规则引擎 |
| 监控 | Grafana + Loguru |
| 部署 | Docker Compose (TimescaleDB + Redis + Grafana + App) |
| 迁移 | Alembic |

---

## 快速开始

### 方式一：一键启动（Windows）

```bash
# 双击或命令行运行
start.bat
```

脚本会自动完成：环境检测（Python / Node.js / Docker） → 交互式填入 API Key → 安装依赖 → 启动 Docker 基础设施 → 启动后端 :8000 + 前端 :3001 → 自动打开浏览器。

### 方式二：手动安装

**前置要求：** Python 3.11+、Node.js 18+、Docker（推荐）

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd crypto-trading-system

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 GRAFANA_ADMIN_PASSWORD、POSTGRES_PASSWORD、REDIS_PASSWORD 等必填项

# 3. 安装后端依赖
pip install -r requirements.txt

# 4. 安装前端依赖
cd frontend && npm install --legacy-peer-deps && cd ..

# 5. 启动基础设施（Docker）
docker compose up -d

# 6. 启动后端 API
python -m uvicorn src.api.app:app --port 8000

# 7. 启动前端仪表盘（另一个终端）
cd frontend && npm run dev -- --port 3001
```

### 验证安装

```bash
# 运行全部测试
pytest tests/

# 检查环境配置
python scripts/check_environment.py

# 运行第一次回测
python scripts/run_backtest.py --strategy grid
```

### 访问地址

| 服务 | 地址 |
|------|------|
| 前端仪表盘 | http://localhost:3001 |
| API 文档 (Swagger) | http://localhost:8000/docs |
| Grafana 监控 | http://localhost:3000 |

---

## Docker 部署

项目提供完整的多阶段 Docker 配置，包含 4 个服务：

| 服务 | 镜像 | 端口 |
|------|------|------|
| TimescaleDB | `timescale/timescaledb:2.17.0-pg16` | 5432 |
| Redis | `redis:7.4-alpine` | 6379 |
| Grafana | `grafana/grafana-oss:10.4.12` | 3000 |
| 交易系统 | 自构建 (Python 3.13-slim) | 8000 |

```bash
# 配置 .env 后一键启动
docker compose up -d

# 查看日志
docker compose logs -f trading_system

# 数据库初始化脚本按编号自动执行：
# config/sql/01_monitor_metrics.sql  — 监控指标表
# config/sql/02_business_tables.sql  — 核心业务表
# config/sql/03_strategy_evolutions.sql — AI 进化记录表
```

---

## 策略引擎

8 种策略均继承 `RiskAwareStrategy` 基类，统一接入风控熔断机制：

| 策略 | 类名 | 适用市场 |
|------|------|----------|
| 网格交易 | `GridTradingStrategy` | 横盘震荡 |
| RSI 动量 | `RSIMomentumStrategy` | 趋势反转 |
| 均线交叉 | `SimpleMAStrategy` | 趋势跟踪 |
| 买入持有 | `BuyAndHoldStrategy` | 长期看多 |
| 唐奇安通道 | `DonchianChannelStrategy` | 突破行情 |
| 市场结构 | `MarketStructureStrategy` | 结构突破 |
| SuperTrend | `SuperTrendStrategy` | 趋势跟踪 |
| 关键位反转 | `KeyLevelReversalStrategy` | 支撑阻力反弹 |

策略注册表 (`src/strategy/registry.py`) 统一管理映射，支持 `get_strategy("grid")` 动态查找。

### 风控熔断

每个策略自动继承三级熔断保护：连续亏损次数限制、日亏损比例限制、最大回撤比例限制。熔断触发后策略进入 `CIRCUIT_BROKEN` 状态，需人工确认恢复。全局 `RiskManager` 状态机管理策略生命周期（ACTIVE → COOLDOWN → CIRCUIT_BROKEN）。

---

## AI 进化引擎

系统内置 Walk-Forward 参数进化流水线，可自动搜索更优策略参数并安全应用：

```
ParamGridBuilder → ParameterScanner.walk_forward → EvolutionGuardrails → LLM 解读 → 参数热替换
```

**核心模块（`src/agent/`）：**

- **ParamGridBuilder** — 从策略 `PARAM_SCHEMA` 自动生成搜索空间，跳过风控参数，int/float 用 linspace，价格参数用数据分位数，上限 2000 组合
- **EvolutionGuardrails** — 6 道安全校验：参数合法性、Sharpe ≥ 10% 提升、回撤 < 15%、OOS 稳定性 CV < 50%、每窗口 ≥ 10 笔交易、≥ 2 个窗口共识
- **LLMClient** — OpenAI → Anthropic → 本地规则三级回退，15 秒超时自动降级，无 API Key 时功能完整
- **EvolutionEngine** — 编排器，串联搜索 → 校验 → 解读 → 应用 → 持久化全链路

**参数热替换：** `MultiStrategyRunner.update_strategy_params()` 可在运行时更新策略参数，重置指标缓存，保留持仓和风控状态，下一根 bar 即生效。

**进化记录：** 每次进化结果写入 `strategy_evolutions` 表，包含新旧参数、新旧指标、校验结果、LLM 解读和是否已应用。

---

## API 端点

共 37 个端点（31 REST + 2 WebSocket + 4 运行模式管理），全部带 Bearer Token 认证和限速保护。

| 分类 | 端点数 | 说明 |
|------|--------|------|
| 行情 & 账户 | 5 | Tickers、WebSocket 推送、账户摘要、健康检查 |
| 策略 & 持仓 | 6 | 策略列表、持仓、资产、订单、创建策略、状态切换 |
| 分析 & 风控 | 7 | PnL 历史/分布、胜率趋势、策略相关性、回撤曲线、风控状态 |
| 多策略 | 3 | 聚合摘要、逐策略详情、单策略查询 |
| AI Agent | 6 | 5 种分析（回测/归因/风险/敏感性/评审）、审计日志、采纳率、进化触发/历史/统计 |
| 运行模式 | 7 | 模式列表/状态/启停/日志、Testnet 校验、WebSocket 日志流 |
| 管理 | 3 | 状态刷新、详细健康检查 |

API 文档自动生成：启动后访问 http://localhost:8000/docs

---

## 前端仪表盘

基于 Next.js 16 + React 19 + TypeScript + Tailwind 4 + SWR + shadcn/ui，共 11 个路由页面：

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` | 总览 | 账户摘要、策略聚合跑分、快速入口 |
| `/grid` | 网格交易 | Grid 策略配置与运行 |
| `/price-action` | 价格行为 | K 线形态分析 |
| `/strategy/[id]` | 策略详情 | 单策略跑分、参数、持仓 |
| `/positions` | 持仓管理 | 当前持仓 + 历史平仓 |
| `/orders` | 订单管理 | 订单列表（分页） |
| `/analytics` | 数据分析 | PnL 分布、胜率趋势、策略相关性 |
| `/risk` | 风控面板 | 回撤曲线、风控状态机、事件日志 |
| `/agent` | AI Agent | AI 分析、进化面板、进化历史、采纳率 |
| `/system` | 系统状态 | 运行模式、健康检查、日志流 |
| `/settings` | 设置 | 环境配置、API Key 管理 |

---

## 项目结构

```
crypto-trading-system/
├── src/                        # 源代码（~29,000 行 Python）
│   ├── api/                    # FastAPI 应用（37 端点 + WebSocket + 模式管理）
│   ├── agent/                  # AI 进化引擎（7 模块：分析/搜索/校验/LLM/编排/审计）
│   ├── backtest/               # 回测引擎（事件驱动 + 参数扫描 + Walk-Forward）
│   ├── data/                   # 数据管道（交易所接口 + 质量检查 + 下载器）
│   ├── execution/              # 执行层（Paper Broker + 交易所 Broker + 多策略 Runner）
│   ├── models/                 # SQLAlchemy 2.0 ORM（7 模型 + Alembic 迁移）
│   ├── monitor/                # 监控指标采集
│   ├── repositories/           # 数据访问层（5 个 Repository）
│   ├── strategy/               # 8 策略 + RiskAwareStrategy 基类 + 注册表
│   └── utils/                  # 工具（配置、缓存、数据库、日志）
├── frontend/                   # Next.js 16 仪表盘（11 路由 + shadcn/ui 组件）
│   ├── app/                    # 路由页面
│   ├── components/             # UI 组件
│   └── lib/                    # API 客户端 + 类型定义
├── tests/                      # 测试（544 函数 / 52 文件）
│   ├── unit/                   # 48 个单元测试文件
│   └── integration/            # 4 个集成测试文件
├── scripts/                    # 运维脚本（回测、环境检查、数据下载等）
├── config/                     # 配置
│   ├── sql/                    # Docker 数据库初始化脚本
│   └── grafana/                # Grafana 仪表盘配置
├── alembic/                    # 数据库迁移
├── docs/                       # 文档
├── deliverables/               # 交付物（审查报告、QA 文档）
├── docker-compose.yml          # Docker 编排（4 服务）
├── Dockerfile                  # 多阶段构建（Python 3.13-slim）
├── start.bat                   # Windows 一键启动脚本
└── requirements.txt            # Python 依赖
```

---

## 开发路线图

### Phase 0: 边界确认 ✅
- 明确系统边界（现货、BTC/ETH）、风控默认安全、实盘开关默认关闭

### Phase 1: 数据可信闭环 ✅
- Binance ccxt 数据下载、7 项质量检查、数据修复、SHA256 版本冻结

### Phase 2: 回测可信闭环 ✅
- 事件驱动回测引擎、零前视偏差、手续费 + 滑点成本模型、参数敏感性测试

### Phase 3: 策略引擎 ✅
- 8 策略实现 + RiskAwareStrategy 继承体系 + 熔断风控

### Phase 4: Paper Trading + 全栈 UI 🔄
- Paper Broker + Multi-Runner + FastAPI 37 端点 + Next.js 11 页面 + Docker 部署 + 一键启动脚本
- [ ] 60 天连续运行验证

### Phase 5: AI 进化引擎 ✅
- Walk-Forward 参数搜索 + 6 道安全校验 + LLM 解读（OpenAI / Anthropic / 本地回退） + 参数热替换 + 进化历史持久化 + 前端进化面板

### Phase 6: 风控强化
- [ ] Grafana 监控仪表盘对接
- [ ] 人工恢复机制
- [ ] 实盘前置条件自动校验

### Phase 7: 小资金实盘（90天+）
- [ ] 初始资金 ≤ $500、连续 3 月无严重风控事故

### Phase 8+: 研究线
- [ ] 价格行为策略深化
- [ ] Prometheus 指标暴露
- [ ] CI/CD 流水线

---

## 示例：运行网格策略回测

```python
from src.strategy.grid_trading import GridTradingStrategy
from src.backtest.engine import BacktestEngine
import pandas as pd

# 创建策略实例
strategy = GridTradingStrategy(
    lower_price=25000,
    upper_price=35000,
    grid_count=20,
    position_per_grid=0.05,
    max_consecutive_losses=3,
    max_daily_loss=0.02,
)

# 运行回测
engine = BacktestEngine(initial_balance=10000)
result = engine.run(strategy, historical_data)

print(f"年化收益: {result['metrics']['annual_return']:.2%}")
print(f"最大回撤: {result['metrics']['max_drawdown']:.2%}")
print(f"夏普比率: {result['metrics']['sharpe_ratio']:.2f}")
```

---

## 环境变量

复制 `.env.example` 为 `.env` 后填入：

| 变量 | 必填 | 说明 |
|------|------|------|
| `API_TOKEN` | 是 | 后端 API 认证 Token（前后端必须一致） |
| `POSTGRES_PASSWORD` | Docker | PostgreSQL 密码 |
| `REDIS_PASSWORD` | Docker | Redis 密码 |
| `GRAFANA_ADMIN_PASSWORD` | Docker | Grafana 管理员密码 |
| `BINANCE_API_KEY` | 可选 | Binance 测试网 API Key |
| `OPENAI_API_KEY` | 可选 | AI 进化 LLM 解读（无 Key 走本地规则） |
| `ANTHROPIC_API_KEY` | 可选 | 备选 LLM 提供商 |
| `LIVE_TRADING_ENABLED` | 否 | 实盘开关，默认 `false` |

---

## 文档

- [项目策划文档](docs/planning/PROJECT_PLAN.md) — 需求分析、技术方案、开发计划
- [工程开发文档](docs/technical/ENGINEERING.md) — 环境配置、模块设计、开发规范
- [API 参考文档](docs/reference/API_REFERENCE.md) — FastAPI 端点详细说明
- [部署文档](docs/DEPLOYMENT.md) — 生产环境部署指南
- [安全策略](SECURITY.md) — 安全防线与漏洞报告流程
- [变更日志](CHANGELOG.md) — 版本变更记录

---

## 风险提示

本项目仅供学习研究使用。加密货币交易存在高风险，可能导致本金全部损失。回测收益不等于实盘收益，使用实盘交易前请充分测试，且只投入可承受损失的资金。实盘 API Key 必须限制权限（禁止提币）。

---

## 开源协议

MIT — 详见 [LICENSE](LICENSE)

---

## 致谢

- [ccxt](https://github.com/ccxt/ccxt) — 统一交易所接口
- [TimescaleDB](https://www.timescale.com/) — 时序数据库
- [shadcn/ui](https://ui.shadcn.com/) — UI 组件库
