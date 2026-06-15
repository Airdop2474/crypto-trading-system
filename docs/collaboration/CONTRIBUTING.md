# 多人协作开发指南

**文档版本：** v1.0  
**创建日期：** 2026-06-13  
**状态：** ✅ 已批准

---

## 目的

本文档定义多人协作开发的规范、流程和最佳实践。

---

## 🎯 协作原则

### 核心原则

1. **文档先行** - 修改代码前先更新文档
2. **小步快跑** - 小的、频繁的提交优于大的、稀疏的提交
3. **代码审查** - 所有代码必须经过 Review
4. **测试驱动** - 先写测试，再写实现
5. **沟通透明** - 及时同步进度和问题

---

## 🔀 Git 工作流

### 分支策略

```
main (受保护)
  ├─ develop (开发主分支)
  │   ├─ feature/phase-1-data-layer (功能分支)
  │   ├─ feature/phase-2-backtest (功能分支)
  │   └─ feature/broker-architecture (功能分支)
  └─ hotfix/critical-bug (紧急修复)
```

### 分支命名规范

```bash
# 功能开发
feature/phase-1-data-layer
feature/broker-paper-implementation
feature/grid-strategy

# Bug 修复
bugfix/data-gap-handling
bugfix/order-execution

# 紧急修复（直接从 main）
hotfix/critical-security-issue

# 文档更新
docs/update-phase-1-guide
docs/add-api-documentation

# 重构
refactor/broker-interface
refactor/signal-management
```

### 分支生命周期

```bash
# 1. 创建功能分支
git checkout develop
git pull origin develop
git checkout -b feature/phase-1-data-layer

# 2. 开发过程中频繁提交
git add .
git commit -m "feat(data): implement data download from Binance"

# 3. 定期同步 develop
git fetch origin develop
git merge origin/develop

# 4. 完成后推送
git push origin feature/phase-1-data-layer

# 5. 创建 Pull Request
# 在 GitHub/GitLab 上创建 PR
# 标题：[Phase 1] Data layer implementation
# 描述：详细说明修改内容

# 6. Code Review 通过后合并
# 由 maintainer 合并到 develop

# 7. 删除功能分支
git branch -d feature/phase-1-data-layer
git push origin --delete feature/phase-1-data-layer
```

---

## 📝 提交信息规范

### Commit Message 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型

| Type | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(data): add data quality check` |
| `fix` | Bug 修复 | `fix(broker): correct slippage calculation` |
| `docs` | 文档 | `docs(readme): update installation guide` |
| `style` | 格式（不影响代码运行） | `style(data): format code with black` |
| `refactor` | 重构 | `refactor(strategy): extract signal logic` |
| `test` | 测试 | `test(broker): add unit tests for Paper Broker` |
| `chore` | 构建、依赖 | `chore(deps): update ccxt to 4.2.0` |
| `perf` | 性能优化 | `perf(backtest): optimize data loading` |

### Scope 范围

- `data` - 数据层
- `backtest` - 回测层
- `strategy` - 策略层
- `broker` - 执行层
- `monitor` - 监控层
- `ai` - AI 层
- `docs` - 文档

### 示例

```bash
# 好的提交信息 ✅
feat(data): implement 7 data quality checks

- Add time continuity check
- Add time uniqueness check
- Add price logic check
- Generate quality report with SHA256

Closes #12

# 不好的提交信息 ❌
update code
fix bug
完成功能
```

---

## 👥 任务分配机制

### Phase 任务拆解

每个 Phase 应该拆解为可独立完成的任务：

**Phase 1 示例：**
```
Phase 1: 数据可信闭环（7天）
  ├─ Task 1.1: 环境配置（0.5天）@开发者A
  ├─ Task 1.2: 数据下载模块（1天）@开发者B
  ├─ Task 1.3: 数据质量检查（2天）@开发者A
  ├─ Task 1.4: 数据存储（1天）@开发者B
  ├─ Task 1.5: 质量报告生成（1天）@开发者A
  ├─ Task 1.6: 单元测试（1天）@开发者B
  └─ Task 1.7: 文档和验收（0.5天）@开发者A
```

### 任务认领流程

```bash
# 1. 查看任务列表
# 在 GitHub Issues 或项目管理工具

# 2. 认领任务
# 在 Issue 中评论 "我来做这个"
# 或者分配给自己

# 3. 创建分支
git checkout -b feature/task-1.2-data-download

# 4. 开发完成后
# 提交 PR，关联 Issue
# 在 PR 描述中写：Closes #issue_number

# 5. Review 通过后合并
```

---

## 🔍 Code Review 规范

### Review 检查清单

**功能性：**
- [ ] 代码是否实现了要求的功能
- [ ] 是否通过了所有测试
- [ ] 是否有充分的单元测试

**代码质量：**
- [ ] 代码是否清晰易读
- [ ] 是否遵循项目代码风格
- [ ] 是否有适当的注释
- [ ] 是否有潜在的 bug

**架构设计：**
- [ ] 是否符合项目架构（如 Broker 三层）
- [ ] 是否有过度设计
- [ ] 是否有代码重复

**文档：**
- [ ] 是否更新了相关文档
- [ ] README 是否需要更新
- [ ] 是否有 CHANGELOG 条目

**安全性：**
- [ ] 是否有安全漏洞
- [ ] 敏感信息是否泄露（API Key 等）
- [ ] 是否有 SQL 注入风险

### Review 流程

```
1. 开发者提交 PR
   ↓
2. 自动运行测试（CI）
   ↓
3. 至少 1 人 Review（推荐 2 人）
   ↓
4. Review 反馈
   ├─ Approve（通过）→ 合并
   ├─ Request Changes（需要修改）→ 修改后再审
   └─ Comment（评论）→ 讨论
   ↓
5. 合并到 develop
   ↓
6. 删除功能分支
```

### Review 注释规范

```python
# ✅ 好的 Review 注释
# 建议：这里可以用列表推导式简化
# [x for x in data if x > 0] 代替循环

# 疑问：这里为什么用 0.1% 作为阈值？
# 建议在代码或文档中说明原因

# 必须修改：这里有潜在的除零错误
# 需要添加检查：if denominator != 0

# ❌ 不好的 Review 注释
# 这个不行
# 改一下
# 有问题
```

---

## 🎨 代码规范

### Python 代码风格

**使用工具：**
```bash
# 代码格式化
black src/

# 导入排序
isort src/

# 类型检查
mypy src/

# Linter
flake8 src/
pylint src/
```

**命名规范：**
```python
# 类名：大驼峰
class PaperBroker:
    pass

# 函数名：小写+下划线
def calculate_slippage(price, amount):
    pass

# 常量：大写+下划线
MAX_POSITION_SIZE = 0.20

# 私有方法：前缀下划线
def _internal_method():
    pass

# 模块名：小写+下划线
# data_quality_checker.py
```

**文档字符串：**
```python
def place_order(self, order: Order) -> OrderResult:
    """
    下单
    
    参数：
        order: 订单对象
        
    返回：
        OrderResult: 订单结果
        
    异常：
        ValueError: 订单参数无效
        InsufficientFundsError: 资金不足
    """
    pass
```

### 目录结构规范

```
crypto-trading-system/
├── src/
│   ├── data/              # 数据层
│   │   ├── __init__.py
│   │   ├── downloader.py
│   │   └── quality_checker.py
│   ├── backtest/          # 回测层
│   ├── strategy/          # 策略层
│   ├── execution/         # 执行层
│   │   ├── broker.py      # Broker 接口
│   │   ├── paper_broker.py
│   │   └── exchange_broker.py
│   ├── monitor/           # 监控层
│   └── utils/             # 工具
├── tests/                 # 测试
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/                  # 文档
├── scripts/               # 脚本
├── config/                # 配置
├── .github/               # GitHub 配置
│   └── workflows/         # CI/CD
├── requirements.txt       # 依赖
├── .env.example           # 环境变量示例
├── .gitignore
└── README.md
```

---

## 🔧 环境一致性

### .env.example

创建环境变量模板：

```bash
# .env.example
# 复制此文件为 .env 并填入实际值

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/crypto_trading
REDIS_URL=redis://localhost:6379/0

# Exchange API (测试网)
BINANCE_API_KEY=your_testnet_api_key
BINANCE_SECRET=your_testnet_secret
BINANCE_TESTNET=true

# 实盘开关（默认关闭）
LIVE_TRADING_ENABLED=false

# 风控参数
MAX_DAILY_LOSS=0.03
MAX_POSITION_SIZE=0.20

# AI API
OPENAI_API_KEY=your_openai_key
```

### requirements.txt 固定版本

```txt
# requirements.txt
# 固定版本，确保环境一致

# 数据和回测
ccxt==4.2.75
pandas==2.2.0
numpy==1.26.3

# 数据库
psycopg2-binary==2.9.9
redis==5.0.1
sqlalchemy==2.0.25

# 可视化
matplotlib==3.8.2
plotly==5.18.0

# Web
fastapi==0.109.0
uvicorn==0.27.0
streamlit==1.30.0

# AI
openai==1.10.0

# 开发工具
black==24.1.1
isort==5.13.2
flake8==7.0.0
mypy==1.8.0
pytest==8.0.0
pytest-cov==4.1.0
```

### Docker 配置

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

CMD ["python", "main.py"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  timescaledb:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_PASSWORD: secure_password
      POSTGRES_DB: crypto_trading
    ports:
      - "5432:5432"
    volumes:
      - timescaledb_data:/var/lib/postgresql/data

  redis:
    image: redis:latest
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  app:
    build: .
    depends_on:
      - timescaledb
      - redis
    env_file:
      - .env
    volumes:
      - ./src:/app/src

volumes:
  timescaledb_data:
  redis_data:
```

---

## 📊 进度同步机制

### 日常站会（可选）

**时间：** 每天固定时间（如早上10点）  
**时长：** 15分钟  
**内容：**
1. 昨天完成了什么
2. 今天计划做什么
3. 遇到什么问题/阻塞

### 周会

**时间：** 每周固定时间  
**时长：** 30-60分钟  
**内容：**
1. 上周进度回顾
2. 本周计划
3. 技术讨论
4. 风险识别

### 文档同步

**强制要求：**
- 每完成一个 Task，更新 dev-log
- 每完成一个 Phase，更新 ROADMAP
- 遇到设计变更，先讨论再修改文档

---

## 🐛 问题追踪

### Issue 管理

**Issue 模板：**
```markdown
## 问题描述
简要描述问题

## 复现步骤
1. 
2. 
3. 

## 期望行为
应该如何

## 实际行为
实际如何

## 环境信息
- OS: 
- Python: 
- 相关依赖版本: 

## 相关日志
```

**标签分类：**
- `bug` - Bug
- `feature` - 新功能
- `enhancement` - 改进
- `documentation` - 文档
- `question` - 疑问
- `phase-1`, `phase-2` - Phase 标签
- `priority-high`, `priority-low` - 优先级

---

## ✅ Pull Request 规范

### PR 模板

```markdown
## 变更类型
- [ ] 新功能
- [ ] Bug 修复
- [ ] 文档更新
- [ ] 重构
- [ ] 性能优化

## 变更说明
简要描述此 PR 的目的

## 关联 Issue
Closes #issue_number

## 测试
- [ ] 已添加单元测试
- [ ] 已添加集成测试
- [ ] 所有测试通过

## 检查清单
- [ ] 代码遵循项目规范
- [ ] 已更新相关文档
- [ ] 已添加必要的注释
- [ ] 无敏感信息泄露
- [ ] 已通过 Code Review

## 截图（如适用）
```

### PR 大小建议

- ✅ **小 PR**（<300 行）- 推荐
- ⚠️ **中 PR**（300-800 行）- 可接受
- ❌ **大 PR**（>800 行）- 应该拆分

**原因：** 小 PR 更容易 Review，更快合并，降低冲突风险。

---

## 🔐 安全规范

### 敏感信息管理

**禁止提交：**
- ❌ API Keys
- ❌ 密码
- ❌ 私钥
- ❌ .env 文件

**正确做法：**
- ✅ 使用 .env.example 作为模板
- ✅ .env 添加到 .gitignore
- ✅ 使用环境变量管理敏感信息

### 检查工具

```bash
# 检查是否有敏感信息泄露
git secrets --scan

# 或使用 gitleaks
gitleaks detect --source .
```

---

## 📚 推荐工具

### 开发工具
- **IDE:** VS Code / PyCharm
- **Git GUI:** GitKraken / SourceTree
- **API 测试:** Postman / Insomnia

### 协作工具
- **项目管理:** GitHub Projects / Jira / Trello
- **文档协作:** Notion / Confluence
- **沟通:** Slack / Discord / 飞书

### 代码质量
- **Pre-commit hooks:** pre-commit
- **CI/CD:** GitHub Actions / GitLab CI
- **代码覆盖:** codecov

---

## 🎓 新成员入职流程

### 第1天：环境搭建
1. [ ] 克隆仓库
2. [ ] 阅读 START_HERE.md
3. [ ] 阅读 FINAL_PLAN_APPROVED.md
4. [ ] 配置开发环境
5. [ ] 运行测试，确保通过

### 第2天：熟悉代码
1. [ ] 阅读 GOALS_AND_DOCS.md
2. [ ] 浏览代码结构
3. [ ] 运行示例代码
4. [ ] 认领一个简单任务（good-first-issue）

### 第3天：开始贡献
1. [ ] 提交第一个 PR
2. [ ] 参与 Code Review
3. [ ] 熟悉团队工作流

---

## ⚠️ 常见问题

### Q: 遇到合并冲突怎么办？

```bash
# 1. 更新本地 develop
git fetch origin develop
git merge origin/develop

# 2. 解决冲突
# 手动编辑冲突文件
# 保留正确的部分

# 3. 标记为已解决
git add <冲突文件>
git commit -m "resolve merge conflict"

# 4. 推送
git push origin feature/your-branch
```

### Q: 如何回滚错误的提交？

```bash
# 如果还没推送
git reset HEAD~1

# 如果已经推送（创建新提交回滚）
git revert <commit-hash>
git push origin feature/your-branch
```

### Q: 如何同步别人的修改？

```bash
# 定期同步 develop
git checkout develop
git pull origin develop

# 合并到你的分支
git checkout feature/your-branch
git merge develop
```

---

**文档状态：** ✅ 已批准  
**优先级：** 最高  
**更新日期：** 2026-06-13

**记住：** 良好的协作从清晰的规范开始！
