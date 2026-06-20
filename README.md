# Crypto Trading System

> 加密货币自动化量化交易系统 — 8 策略引擎 + Next.js 仪表盘 + Paper Trading

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue.svg)](https://www.typescriptlang.org/)
[![Tests](https://img.shields.io/badge/Tests-475%20passed-green.svg)]()
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
| 后端 | Python 3.11, FastAPI, pandas, numpy, ccxt |
| 前端 | Next.js 16, React 19, TypeScript, Tailwind 4, SWR, shadcn/ui |
| 数据 | TimescaleDB, Redis |
| 监控 | Grafana |
| 部署 | Docker Compose

---

## 🚀 快速开始

### 前置要求

- Python 3.11+
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

# 启动控制台（Phase 4+，当前仓库默认未安装 streamlit）
streamlit run src/monitor/dashboard.py
```

---

## 📚 文档

- **[项目策划文档](docs/planning/PROJECT_PLAN.md)** - 需求分析、技术方案、开发计划
- **[工程开发文档](docs/technical/ENGINEERING.md)** - 环境配置、模块设计、开发规范
- **[API 文档](docs/API.md)** - 接口说明（待完善）
- **[部署文档](docs/DEPLOYMENT.md)** - 生产环境部署指南（待完善）

---

## 🏗️ 项目结构

```
crypto-trading-system/
├── src/                    # 源代码
│   ├── data/              # 数据层（交易所接口、数据库）
│   ├── strategy/          # 策略层（交易策略实现）
│   ├── execution/         # 执行层（订单管理、风控）
│   ├── backtest/          # 回测层（回测引擎、指标计算）
│   ├── monitor/           # 监控层（仪表盘、告警）
│   ├── agent/             # AI 优化层（Agent 接口）
│   └── utils/             # 工具模块
├── tests/                 # 测试
├── scripts/               # 脚本工具
├── config/                # 配置文件
├── data/                  # 数据文件（.gitignore）
├── logs/                  # 日志文件（.gitignore）
└── docs/                  # 文档
```

---

## 🎯 开发路线图

### Phase 0: 环境准备 ✅
- [x] 项目结构设计
- [x] 文档编写
- [ ] 环境搭建

### Phase 1: 数据层（5 天）
- [ ] 交易所接口封装
- [ ] 历史数据下载
- [ ] 数据库设计实现

### Phase 2: 回测框架（7 天）
- [ ] 回测引擎开发
- [ ] 网格策略实现
- [ ] 性能指标计算

### Phase 3: 实盘交易（7 天）
- [ ] 实时行情接入
- [ ] 订单管理
- [ ] 风控引擎

### Phase 4: 监控和 Agent（5 天）
- [ ] 监控仪表盘
- [ ] Agent 接口集成
- [ ] 触发器系统

### Phase 5: AI 优化闭环（5 天）
- [ ] 参数自动调优
- [ ] A/B 测试框架
- [ ] 优化审核流程

### Phase 6: 模拟盘验证（30 天）
- [ ] 连续运行测试
- [ ] 问题修复
- [ ] 文档完善

---

## 🔧 技术栈

**语言：**
- Python 3.11+ (主要开发语言)
- Rust (性能优化，可选)

**数据存储：**
- TimescaleDB (时序数据)
- PostgreSQL (关系数据)
- Redis (缓存)

**核心库：**
- ccxt - 交易所接口
- pandas - 数据处理
- backtesting.py - 回测框架
- sqlalchemy - ORM
- streamlit - Web 控制台

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
- [backtesting.py](https://kernc.github.io/backtesting.py/) - 回测框架
- [TimescaleDB](https://www.timescale.com/) - 时序数据库

---

**⚡ 开始你的量化交易之旅吧！**
