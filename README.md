# Crypto Trading System

> 加密货币自动化量化交易系统 — 12 策略引擎 + AI 自进化 + 实时纸盘 + Next.js 仪表盘

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue.svg)](https://www.typescriptlang.org/)
[![Strategies](https://img.shields.io/badge/Strategies-12-blue.svg)]()
[![Status](https://img.shields.io/badge/Status-Live%20Paper%20Trading-green.svg)]()

---

## 项目简介

集成 12 种交易策略的量化交易系统，支持实时纸盘模拟交易、历史回放、Binance Testnet 实盘验证。内置 AI 进化引擎自动优化策略参数，前端仪表盘实时展示持仓、盈亏、风控状态。支持 VPS 一键部署，7x24 不间断运行。

### 核心特性

- **12 策略引擎** — Grid / RSI / MA / BuyHold / Donchian / Structure / SuperTrend / Reversal / PriceAction / Bollinger / MACD / Composite，多策略并行运行
- **三种运行模式** — 实时纸盘（实时行情 + 模拟撮合）、回放纸盘（历史数据回放）、Testnet 实盘（Binance testnet 真实下单）
- **多策略并行** — 每个策略独立子进程运行，互不阻塞，崩溃自动恢复
- **实时数据驱动** — 仪表盘 / 持仓 / 订单 / AI 分析全部从实时纸盘 daemon state 读取，非预跑回测
- **AI 自进化** — Walk-Forward 参数搜索 + LLM 解读 + 6 道安全校验 + 参数热替换
- **熔断风控** — 策略级 + 账户级双重熔断（连续亏损 / 日亏损 / 最大回撤），状态机驱动
- **AI 分析中心** — 回测解读、交易归因、风险清单、参数敏感性、周报复盘，5 种分析类型
- **全栈容错** — 无 PostgreSQL → 内存回退，无 Redis → MemoryCache，无 LLM Key → 本地规则

### 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.13, FastAPI, pandas, numpy, ccxt |
| 前端 | Next.js 16, React 19, TypeScript 5.7, Tailwind 4, SWR, shadcn/ui |
| 数据库 | TimescaleDB (时序) + PostgreSQL (关系) + Redis (缓存) |
| AI | OpenAI / Anthropic / 本地规则引擎 |
| 部署 | Docker Compose (TimescaleDB + Redis + Grafana + App) |

---

## 快速开始

### VPS 部署（推荐，7x24 不间断运行）

```bash
# 1. 克隆仓库
git clone https://github.com/Airdop2474/crypto-trading-system.git /opt/crypto-trading-system
cd /opt/crypto-trading-system

# 2. 首次部署（自动安装 Docker、生成 .env）
bash deploy.sh

# 3. 编辑 .env，填入 Binance API Key
nano .env

# 4. 启动服务
bash deploy.sh

# 5. 交互式启动交易
bash start.sh
```

`start.sh` 会引导你选择运行模式、交易对、策略组合，确认后一键启动。

### 本地开发

**前置要求：** Python 3.11+、Node.js 18+、Docker（推荐）

```bash
# 克隆项目
git clone https://github.com/Airdop2474/crypto-trading-system.git
cd crypto-trading-system

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API_TOKEN、Binance API Key 等

# 启动基础设施
docker compose up -d

# 安装后端依赖并启动
pip install -r requirements.txt
python -m uvicorn src.api.app:app --port 8000

# 另一个终端，安装前端依赖并启动
cd frontend
npm install --legacy-peer-deps
npm run dev
```

### 本地前端连接 VPS 后端

VPS 部署后，本地前端可直接连 VPS 后端：

```bash
cd frontend
# 编辑 .env.local
#   NEXT_PUBLIC_API_BASE=http://<VPS_IP>:8000
#   NEXT_PUBLIC_API_TOKEN=<VPS .env 中的 API_TOKEN>
npm run dev
```

浏览器打开 `http://localhost:3000`，前端在本地跑，数据从 VPS 后端拉取。

### 访问地址

| 服务 | 地址 |
|------|------|
| 前端仪表盘 | http://localhost:3000 |
| API 文档 (Swagger) | http://localhost:8000/docs |
| Grafana 监控 | http://localhost:3000 (VPS) |

---

## 运行模式

| 模式 | 说明 | 行情 | 撮合 | 资金 |
|------|------|------|------|------|
| **实时纸盘** (live_paper) | 实时行情 + 本地模拟撮合 | Binance 真实行情 | PaperBroker 模拟 | 虚拟余额 |
| **回放纸盘** (replay_paper) | 历史数据回放验证 | 生成/CSV | PaperBroker 模拟 | 虚拟余额 |
| **Testnet 实盘** (testnet_live) | Binance testnet 真实下单 | Testnet 行情 | Testnet 真实撮合 | Testnet 余额 |

实时纸盘适合验证策略逻辑，Testnet 实盘验证完整下单链路（API 签名、网络异常、资金不足等）。

---

## 策略引擎

12 种策略均继承 `RiskAwareStrategy` 基类，统一接入风控熔断机制：

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
| 价格行为 | `PriceActionStrategy` | 裸K结构分析 |
| 布林带 | `BollingerBandsStrategy` | 均值回归 |
| MACD | `MACDStrategy` | 趋势跟踪 |
| 综合趋势 | `CompositeTrendStrategy` | 多信号融合 |

### 风控熔断

每个策略自动继承三级熔断保护：连续亏损次数限制、日亏损比例限制、最大回撤比例限制。熔断触发后策略进入 `CIRCUIT_BROKEN` 状态，需人工确认恢复。全局 `RiskManager` 状态机管理策略生命周期（ACTIVE → COOLDOWN → CIRCUIT_BROKEN）。

---

## AI 分析中心

5 种分析类型，数据全部来自实时纸盘运行结果：

| 分析类型 | 功能 |
|----------|------|
| 回测解读 | 解释收益来源、回撤原因与潜在风险 |
| 交易归因 | 对失败交易做归因分析，找出共性错误 |
| 风险清单 | 逐项检查风控、密钥、数据质量等合规项 |
| 参数敏感性 | 总结参数扫描结果，指出稳健区间 |
| 周报复盘 | 生成本周策略表现综述与下周建议 |

---

## AI 进化引擎

系统内置 Walk-Forward 参数进化流水线，可自动搜索更优策略参数并安全应用：

```
ParamGridBuilder → ParameterScanner.walk_forward → EvolutionGuardrails → LLM 解读 → 参数热替换
```

- **6 道安全校验** — 参数合法性、Sharpe 提升、回撤控制、OOS 稳定性、交易样本量、多窗口共识
- **LLM 三级回退** — OpenAI → Anthropic → 本地规则，无 API Key 时功能完整
- **参数热替换** — 运行时更新策略参数，保留持仓和风控状态，下一根 bar 即生效

---

## 前端仪表盘

基于 Next.js 16 + React 19 + TypeScript + Tailwind 4 + SWR + shadcn/ui：

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` | 总览仪表盘 | 账户摘要、权益曲线、运行中策略、多策略跑分、风险指标 |
| `/positions` | 持仓与资产 | 当前持仓、资产配置、平仓历史、盈亏分布 |
| `/orders` | 订单成交 | 订单列表（分页）、累计统计 |
| `/strategies` | 策略管理 | 策略列表、创建策略、参数配置 |
| `/strategy/[id]` | 策略详情 | 单策略跑分、参数、持仓 |
| `/analytics` | 数据分析 | PnL 分布、胜率趋势、策略相关性 |
| `/risk` | 风控面板 | 回撤曲线、风控状态机、事件日志 |
| `/agent` | AI 分析中心 | 5 种分析类型、进化面板、进化历史 |
| `/system` | 系统状态 | 运行模式管理、健康检查、实时日志流 |
| `/settings` | 设置 | 环境配置、API Key 管理 |

---

## Docker 部署

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

# 停止 / 重启
docker compose down
docker compose restart
```

---

## 项目结构

```
crypto-trading-system/
├── src/
│   ├── api/                    # FastAPI 应用 + 实时数据聚合 + 模式管理
│   ├── agent/                  # AI 进化引擎 + 分析器
│   ├── backtest/               # 回测引擎 + 参数扫描
│   ├── data/                   # 数据管道（交易所接口 + 质量检查）
│   ├── execution/              # 执行层（PaperBroker + ExchangeBroker + 多策略 Runner）
│   ├── models/                 # SQLAlchemy ORM + Alembic 迁移
│   ├── strategy/               # 12 策略 + RiskAwareStrategy 基类 + 注册表
│   └── utils/                  # 配置、缓存、数据库、日志
├── frontend/                   # Next.js 16 仪表盘
│   ├── app/                    # 路由页面
│   ├── components/             # UI 组件
│   └── lib/                    # API 客户端 + 类型定义
├── scripts/                    # 运维脚本（daemon、回测、数据下载等）
├── tests/                      # 单元测试 + 集成测试
├── config/                     # SQL 初始化 + Grafana 配置
├── deploy.sh                   # VPS 一键部署脚本
├── start.sh                    # VPS 交互式启动脚本
├── docker-compose.yml          # Docker 编排（4 服务）
├── Dockerfile                  # 多阶段构建
└── requirements.txt            # Python 依赖
```

---

## 环境变量

复制 `.env.example` 为 `.env` 后填入：

| 变量 | 必填 | 说明 |
|------|------|------|
| `API_TOKEN` | 是 | 后端 API 认证 Token（前后端必须一致） |
| `BINANCE_API_KEY` | 是 | Binance testnet API Key |
| `BINANCE_SECRET` | 是 | Binance testnet Secret |
| `POSTGRES_PASSWORD` | Docker | PostgreSQL 密码 |
| `REDIS_PASSWORD` | Docker | Redis 密码 |
| `GRAFANA_ADMIN_PASSWORD` | Docker | Grafana 管理员密码 |
| `LLM_API_KEY` | 可选 | AI 进化 LLM 解读（无 Key 走本地规则） |
| `LIVE_TRADING_ENABLED` | 否 | 实盘开关，默认 `false` |

---

## 常用命令

```bash
# VPS 部署
bash deploy.sh              # 首次部署 / 启动服务
bash start.sh               # 交互式启动交易
bash start.sh status        # 查看运行状态
bash start.sh stop          # 停止所有运行模式

# Docker 运维
docker compose ps           # 查看服务状态
docker compose logs -f      # 查看日志
docker compose restart      # 重启服务

# 本地开发
pytest tests/               # 运行测试
python scripts/run_backtest.py --strategy grid  # 运行回测
```

---

## 风险提示

本项目仅供学习研究使用。加密货币交易存在高风险，可能导致本金全部损失。回测收益不等于实盘收益，使用实盘交易前请充分测试，且只投入可承受损失的资金。实盘 API Key 必须限制权限（禁止提币）。

---

## 开源协议

MIT — 详见 [LICENSE](LICENSE)
