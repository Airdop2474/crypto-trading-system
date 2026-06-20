# 🚀 快速开始指南

**欢迎来到加密货币交易系统项目！**

---

## 📖 我是新成员，从哪里开始？

### 第1步：了解项目（15分钟）

阅读以下3个核心文档：

1. **README.md** - 项目概述（5分钟）
2. **[docs/planning/FINAL_PLAN_APPROVED.md](docs/planning/FINAL_PLAN_APPROVED.md)** - **最终方案（必读）** ⭐⭐⭐
3. **[docs/planning/GOALS_AND_DOCS.md](docs/planning/GOALS_AND_DOCS.md)** - 目标和文档索引

### 第2步：了解协作规范（20分钟）

4. **[docs/collaboration/CONTRIBUTING.md](docs/collaboration/CONTRIBUTING.md)** - **协作开发指南（必读）** ⭐
5. **[docs/collaboration/COLLABORATION_READY.md](docs/collaboration/COLLABORATION_READY.md)** - 协作准备清单

### 第3步：配置开发环境（1-2小时）

```bash
# 1. 克隆仓库
git clone <repo-url>
cd crypto-trading-system

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 复制环境变量模板
cp .env.example .env
# 然后编辑 .env 填入实际值

# 5. 启动数据库（Docker）
docker-compose up -d

# 6. 运行测试确认环境
pytest tests/
```

---

## 🎯 项目核心信息

### 项目定位（方案 C+）

> 构建一个数据可信、回测可信、风控优先、逐步验证的加密货币交易系统

**核心原则：**
1. 数据质量 > 策略收益
2. 系统可信 > 功能完整
3. 风险控制 > 自动化
4. 验证驱动 > 功能驱动

### Phase 规划

```
Phase 0: 边界确认（1天）✅
Phase 1: 数据可信闭环（7天）✅
Phase 2: 回测可信闭环（10天）✅
Phase 3: 策略引擎验证（8策略）✅
Phase 4: Paper Trading（60天）🔄 进行中
Phase 5: 风控强化（5天）
Phase 6: 小资金实盘（90天+）
────────────────────────────
Phase 7+: 价格行为策略研究线（独立）
```

**关键时间点：**
- 1个月：数据和回测闭环完成
- 3个月：Paper Trading 完成
- 6个月：开始实盘
- 9个月：实盘稳定

---

## 📚 文档导航

### 🔴 必读文档（新成员）
- [README.md](README.md) - 项目说明
- [docs/planning/FINAL_PLAN_APPROVED.md](docs/planning/FINAL_PLAN_APPROVED.md) - **最终方案** ⭐⭐⭐
- [docs/collaboration/CONTRIBUTING.md](docs/collaboration/CONTRIBUTING.md) - **协作规范** ⭐

### 🟡 规划文档
- [docs/planning/ROADMAP_UPDATE.md](docs/planning/ROADMAP_UPDATE.md) - 最新路线图
- [docs/planning/GOALS_AND_DOCS.md](docs/planning/GOALS_AND_DOCS.md) - 目标和文档索引
- [docs/planning/PROJECT_PLAN.md](docs/planning/PROJECT_PLAN.md) - 原始规划
- [docs/planning/PRICE_ACTION_PLAN.md](docs/planning/PRICE_ACTION_PLAN.md) - 价格行为策略（Phase 7+）

### 🟢 验收标准（开发必备）
- [docs/standards/DATA_QUALITY_STANDARD.md](docs/standards/DATA_QUALITY_STANDARD.md) - Phase 1 标准
- [docs/standards/BACKTEST_VALIDATION.md](docs/standards/BACKTEST_VALIDATION.md) - Phase 2 标准
- [docs/standards/STRATEGY_ASSUMPTIONS.md](docs/standards/STRATEGY_ASSUMPTIONS.md) - Phase 3 标准
- [docs/standards/AI_USAGE_BOUNDARIES.md](docs/standards/AI_USAGE_BOUNDARIES.md) - AI 使用规则
- [docs/standards/LIVE_TRADING_CHECKLIST.md](docs/standards/LIVE_TRADING_CHECKLIST.md) - Phase 6 门禁

### 🔵 技术文档
- [docs/technical/ENGINEERING.md](docs/technical/ENGINEERING.md) - 工程开发文档
- [docs/technical/BROKER_ARCHITECTURE.md](docs/technical/BROKER_ARCHITECTURE.md) - Broker 三层架构

### 🟣 参考文档
- [docs/reference/QUICK_REFERENCE.md](docs/reference/QUICK_REFERENCE.md) - 命令速查
- [docs/reference/SKILLS_GUIDE.md](docs/reference/SKILLS_GUIDE.md) - Skills 使用指南

### 📁 讨论归档
- [docs/design-review/](docs/design-review/) - 设计讨论记录

---

## ⚡ 快速命令

### 开发环境

```bash
# 激活虚拟环境
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 启动数据库
docker-compose up -d

# 停止数据库
docker-compose down

# 运行测试
pytest tests/

# 环境检查
python scripts/check_environment.py

# 代码格式化
black src/
isort src/

# 代码检查
flake8 src/
mypy src/
```

### Git 工作流

```bash
# 创建功能分支
git checkout develop
git pull origin develop
git checkout -b feature/phase-1-data-layer

# 提交代码
git add .
git commit -m "feat(data): implement data download"

# 推送并创建 PR
git push origin feature/phase-1-data-layer
# 然后在 GitHub 上创建 Pull Request
```

---

## 🎯 当前状态

**Phase 0-3：✅ 全部已完成**

已完成工作：
- ✅ 8 策略引擎：Grid / RSI / MA / BuyHold / Donchian / Structure / SuperTrend / Reversal
- ✅ RiskAwareStrategy 继承体系（统一熔断风控）
- ✅ 事件驱动回测引擎（无前视偏差）
- ✅ FastAPI API 层（18 端点 + WebSocket 实时推送）
- ✅ Next.js 16 仪表盘（SWR + shadcn/ui）
- ✅ Paper Trading 基础设施（PaperBroker 99% 覆盖）
- ✅ 481 测试通过（484 总计，3 skipped），83% 代码覆盖率
- ✅ Docker Compose 一键部署（含 Grafana / Redis 密码认证）

**Phase 4：🔄 Paper Trading 进行中**
- 目标：60 天连续运行验证
- 状态：上线前审查阶段
- 验收标准：见 [docs/standards/STRATEGY_ASSUMPTIONS.md](docs/standards/STRATEGY_ASSUMPTIONS.md)

**第一个任务推荐：**
1. 运行 `python scripts/check_environment.py` 验证环境
2. 运行 `pytest tests/` 确认测试通过
3. 阅读 [docs/reference/API_REFERENCE.md](docs/reference/API_REFERENCE.md) 了解 API
4. 查看 [docs/planning/ROADMAP_UPDATE.md](docs/planning/ROADMAP_UPDATE.md) 了解路线图

---

## 🤝 如何贡献

### 认领任务
1. 查看 GitHub Issues
2. 找到感兴趣的任务
3. 评论 "我来做这个"
4. 创建功能分支开始开发

### 提交 PR
1. 确保所有测试通过
2. 使用规范的 commit message
3. 填写完整的 PR 模板
4. 等待 Code Review

详细流程见：[docs/collaboration/CONTRIBUTING.md](docs/collaboration/CONTRIBUTING.md)

---

## 📊 项目统计

- **文档数量：** 30 个核心文档
- **配置文件：** 6 个
- **GitHub 模板：** 3 个
- **CI/CD 检查：** 4 个流程
- **总计：** 43 个关键文件

---

## 💡 学习路径

### 如果你想了解...

**项目整体规划：**
→ [docs/planning/FINAL_PLAN_APPROVED.md](docs/planning/FINAL_PLAN_APPROVED.md)

**如何协作开发：**
→ [docs/collaboration/CONTRIBUTING.md](docs/collaboration/CONTRIBUTING.md)

**Phase 1 如何开发：**
→ [docs/standards/DATA_QUALITY_STANDARD.md](docs/standards/DATA_QUALITY_STANDARD.md)

**Broker 架构设计：**
→ [docs/technical/BROKER_ARCHITECTURE.md](docs/technical/BROKER_ARCHITECTURE.md)

**常用命令：**
→ [docs/reference/QUICK_REFERENCE.md](docs/reference/QUICK_REFERENCE.md)

---

## ⚠️ 重要提醒

### 安全原则
- ❌ 不要提交 .env 文件
- ❌ 不要提交 API Keys
- ❌ Phase 1-5 只用测试网
- ✅ 实盘从小资金开始（<$500）

### 开发原则
- ✅ 文档先行 - 修改代码前先更新文档
- ✅ 小步快跑 - 小的、频繁的提交
- ✅ 代码审查 - 所有代码必须 Review
- ✅ 测试驱动 - 先写测试，再写实现

---

## 🎊 开始你的旅程

你现在已经准备好开始了！

**第一个任务推荐：**
1. 配置开发环境
2. 运行测试确认
3. 认领一个 `good-first-issue`
4. 提交你的第一个 PR

**记住核心原则：**
1. 数据质量 > 策略收益
2. 系统可信 > 功能完整
3. 风险控制 > 自动化
4. 验证驱动 > 功能驱动

---

## 📞 获取帮助

- **文档问题：** 查看 [docs/planning/GOALS_AND_DOCS.md](docs/planning/GOALS_AND_DOCS.md)
- **技术问题：** 查看 [docs/technical/ENGINEERING.md](docs/technical/ENGINEERING.md)
- **协作问题：** 查看 [docs/collaboration/CONTRIBUTING.md](docs/collaboration/CONTRIBUTING.md)
- **其他问题：** 在团队频道提问或创建 GitHub Issue

---

**创建日期：** 2026-06-12  
**更新日期：** 2026-06-20  
**项目状态：** Phase 1-3 已完成，Phase 4 Paper Trading 进行中，上线前审查阶段  
**方案：** C+（已定案）

🚀 **祝你开发顺利！**
