# Crypto Trading System

> 加密货币自动化量化交易系统 — 8 策略引擎 + Next.js 仪表盘 + Paper Trading

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue.svg)](https://www.typescriptlang.org/)
[![Tests](https://img.shields.io/badge/Tests-481%20passed%20(484%20total)-green.svg)]()
[![Status](https://img.shields.io/badge/Status-Paper%20Trading-yellow.svg)]()

---

## 📋 项目简介

集成 8 交易策略的量化交易系统，支持回测、Paper Trading（模拟交易）和实盘交易。前端基于 Next.js 16 + React 19 仪表盘提供实时策略跑分、持仓管理和盈亏分析。

### 核心特性

- ✅ **完整回测框架** — 事件驱动 bar-by-bar，无前视偏差
- ✅ **8 策略引擎** — Grid/RSI/MA/BuyHold/Donchian/Structure/SuperTrend/Reversal
- ✅ **熔断风控** — 策略级 + 账户级双重熔断（连亏/日亏/回撤）
- ✅ **Paper Trading** — 60 天模拟交易流程，实盘前硬门禁
- ✅ **实时仪表盘** — Next.js 16 + SWR + shadcn/ui，策略跑分/持仓/盈亏
- ✅ **时序数据库** — TimescaleDB 高效存储交易数据
- ✅ **Docker 部署** — docker compose up 一键启动基础设施

### 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.13, FastAPI, pandas, numpy, ccxt |
| 前端 | Next.js 16, React 19, TypeScript, Tailwind 4, SWR, shadcn/ui |
| 数据 | TimescaleDB, Redis |
| 监控 | Grafana |
| 部署 | Docker Compose

---

## 🚀 快速开始

### 前置要求

- Python 3.13+
- Node.js 18+
- Docker (推荐)
- TimescaleDB + Redis (Docker 方式自动包含)

### 安装步骤

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd crypto-trading-system

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的配置（GRAFANA_ADMIN_PASSWORD 等必填）

# 3. 安装依赖
pip install -r requirements.txt
cd frontend && npm install --legacy-peer-deps && cd ..

# 4. 启动基础设施（Docker）
docker compose up -d

# 5. 启动后端 API
python -m uvicorn src.api.app:app --port 8000

# 6. 启动前端仪表盘（另一个终端）
cd frontend && npm run dev -- --port 3001

# 7. 打开浏览器
# http://localhost:3001  (前端仪表盘)
# http://localhost:8000/docs  (API 文档)

# 8. 运行第一次回测
python scripts/run_backtest.py --strategy grid
```

### 验证安装

```bash
# 运行测试
pytest tests/

# 验证环境配置
python scripts/check_environment.py
```

---

## 📚 文档

- **[项目策划文档](docs/planning/PROJECT_PLAN.md)** - 需求分析、技术方案、开发计划
- **[工程开发文档](docs/technical/ENGINEERING.md)** - 环境配置、模块设计、开发规范
- **[API 文档](docs/reference/API_REFERENCE.md)** - FastAPI 接口说明（18 端点 + WebSocket）
- **[部署文档](docs/DEPLOYMENT.md)** - 生产环境部署指南
- **[安全策略](SECURITY.md)** - 安全防线说明与漏洞报告流程
- **[变更日志](CHANGELOG.md)** - 版本变更记录

---

## 🏗️ 项目结构

```
crypto-trading-system/
├── src/                    # 源代码
│   ├── api/               # API 层（FastAPI 18 端点 + WebSocket）
│   ├── data/              # 数据层（交易所接口、数据库）
│   ├── strategy/          # 策略层（8 策略 + RiskAwareStrategy 基类）
│   ├── execution/         # 执行层（订单管理、Paper Broker、风控）
│   ├── backtest/          # 回测层（事件驱动引擎、指标计算）
│   ├── monitor/           # 监控层（告警、Market Classifier）
│   ├── agent/             # AI 分析层（Agent 接口）
│   └── utils/             # 工具模块（trading、config、cache）
├── frontend/              # 前端仪表盘（Next.js 16 + React 19 + SWR）
├── tests/                 # 测试（481 passed, 484 total, 83% 覆盖）
├── scripts/               # 脚本工具
├── config/                # 配置文件（Grafana、SQL、告警）
├── deliverables/          # 交付物（QA 报告、审查文档）
├── data/                  # 数据文件（.gitignore）
├── logs/                  # 日志文件（.gitignore）
└── docs/                  # 文档
```

---

## 🎯 开发路线图

### Phase 0: 边界确认 ✅
- [x] 明确系统边界（只做现货、BTC/ETH）
- [x] 风控默认配置安全
- [x] 实盘开关默认关闭

### Phase 1: 数据可信闭环 ✅
- [x] 数据下载（Binance, ccxt）
- [x] 7 项强制数据质量检查
- [x] 数据修复策略与时区统一
- [x] 数据版本冻结（SHA256）

### Phase 2: 回测可信闭环 ✅
- [x] 事件驱动回测引擎
- [x] 前视偏差检查（零容忍）
- [x] 成本模型（手续费 + 滑点）
- [x] 参数敏感性测试

### Phase 3: 策略引擎验证（8策略）✅
- [x] Grid / RSI / MA / BuyHold 策略
- [x] Donchian / Structure / SuperTrend / Reversal 策略
- [x] 熔断风控（连亏/日亏/回撤）
- [x] RiskAwareStrategy 继承体系

### Phase 4: Paper Trading（60天）🔄 进行中
- [x] Paper Broker 完善实现（99% 覆盖）
- [x] PaperTradingRunner + Multi-Runner
- [x] FastAPI API 层（18 端点 + WebSocket）
- [x] Next.js 16 仪表盘
- [ ] 60 天连续运行验证

### Phase 5: 风控强化
- [ ] 日亏损限制（3%）
- [ ] 最大仓位限制（60%）
- [ ] 人工恢复机制
- [ ] Grafana 监控仪表盘

### Phase 6: 小资金实盘（90天+）
- [ ] 前置条件验证（门禁清单）
- [ ] 初始资金 ≤ $500
- [ ] 连续 3 月无严重风控事故
- [ ] 回撤可控、决策可追溯

### Phase 7+: 研究线与 AI 辅助
- [ ] 价格行为策略研究（独立分支）
- [ ] AI 辅助分析深化
- [ ] 技术储备与扩展验证

---

## 🔧 技术栈

**语言：**
- Python 3.13+ (主要开发语言)
- Rust (性能优化，可选)

**数据存储：**
- TimescaleDB (时序数据)
- PostgreSQL (关系数据)
- Redis (缓存)

**核心库：**
- ccxt - 交易所接口
- pandas - 数据处理
- 自研事件驱动回测引擎（`src/backtest/engine.py`）
- sqlalchemy - ORM
- Next.js 16 仪表盘（`frontend/`）

**监控：**
- Grafana - 指标监控
- Loguru - 日志管理

---

## ⚠️ 风险提示

1. **本项目仅供学习研究使用**
2. **加密货币交易存在高风险，可能导致本金损失**
3. **回测收益不等于实盘收益**
4. **使用实盘交易前请充分测试**
5. **建议只投入可承受损失的资金**

---

## 📊 示例策略：网格交易

```python
from src.strategy.grid_trading import GridTradingStrategy

# 创建策略实例
strategy = GridTradingStrategy(
    symbol='BTC/USDT',
    timeframe='1h',
    parameters={
        'lower_price': 25000,
        'upper_price': 35000,
        'num_grids': 20,
        'total_amount': 1000,
        'stop_loss_pct': 0.15
    }
)

# 运行回测
from src.backtest.engine import BacktestEngine

engine = BacktestEngine(initial_balance=10000)
result = engine.run(strategy, historical_data)

print(f"年化收益: {result['metrics']['annual_return']:.2%}")
print(f"最大回撤: {result['metrics']['max_drawdown']:.2%}")
print(f"夏普比率: {result['metrics']['sharpe_ratio']:.2f}")
```

---

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'feat: Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

---

## 📄 开源协议

本项目采用 MIT 协议 - 详见 [LICENSE](LICENSE) 文件

---

## 📧 联系方式

- 项目地址：[GitHub](https://github.com/yourusername/crypto-trading-system)
- 问题反馈：[Issues](https://github.com/yourusername/crypto-trading-system/issues)

---

## 🙏 致谢

- [ccxt](https://github.com/ccxt/ccxt) - 统一交易所接口
- [TimescaleDB](https://www.timescale.com/) - 时序数据库

---

**⚡ 开始你的量化交易之旅吧！**
