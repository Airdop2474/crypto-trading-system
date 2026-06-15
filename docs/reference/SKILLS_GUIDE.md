# Claude Code Skills 使用指南

## ✅ Skills 已创建完成

已在项目的 `.claude/skills/` 目录创建了 **17 个 Skills**（16个自定义 + 1个外部），专为本项目设计。

**重要：** 这些 Skills 是**项目级别**的，只在当前项目中生效，不会影响其他项目。

### 🆕 新增辅助 Skills（6个）

为了提高团队协作效率和代码质量，新增了以下辅助 Skills：

1. **`/workflow-control`** ⭐ **核心总控** - 工作流程控制器
   - **强制执行开发流程**：理解需求 → 分析影响 → 规划任务 → 确认 → 执行
   - **避免直接修改代码**：先分析再动手
   - **自动调用其他 Skills**：project-context、code-style、risk-audit 等
   - **使用场景：** 任何代码变更请求都会自动触发

2. **`/project-context`** - 项目上下文速查
   - 显示项目结构、当前阶段、最近变更
   - 帮助快速定位代码位置
   
3. **`/project-onboard`** - 新成员入门引导
   - 项目介绍、技术栈、架构说明
   - 适合新加入的开发者
   
4. **`/code-style`** - 代码规范检查
   - 优先运行 `python scripts/check_code_style.py`
   - 自动运行 black, isort, flake8
   - 检查 docstring 和命名规范
   
5. **`/dev-log`** - 开发日志管理
   - 记录每日进度、跟踪任务
   - 查询开发历史
   
6. **`/token-budget`** - Token 使用优化
   - 估算操作成本
   - 分析并优化 Token 消耗

### 📚 外部 Skills（1个）

7. **`/karpathy-guidelines`** - Andrej Karpathy 编程指南
   - 来源：https://github.com/multica-ai/andrej-karpathy-skills
   - Andrej Karpathy 的编程最佳实践

### 📋 Skills 列表（17个）

#### 🎯 工作流控制（必读）
| Skill | 用途 | 重要性 |
|-------|------|--------|
| `/workflow-control` ⭐ | 总控：先分析再执行 | **核心** |
| `/project-context` | 项目上下文速查 | 高 |
| `/project-onboard` | 新人入门引导 | 中 |

#### 🛠️ 开发 Skills
| Skill | 用途 | 使用频率 |
|-------|------|---------|
| `/strategy-new` | 创建新策略脚手架 | 按需 |
| `/trading-backtest` | 执行策略回测 | 每天 |
| `/data-check` | 数据健康检查 | 每周 |
| `/code-style` | 代码规范检查 | 每天 |

#### 🔍 优化 Skills
| Skill | 用途 | 使用频率 |
|-------|------|---------|
| `/agent-optimize` | AI 策略优化 | 每周 |
| `/perf-analyze` | 性能瓶颈分析 | 按需 |
| `/token-budget` | Token 使用优化 | 按需 |

#### 🔒 安全 Skills
| Skill | 用途 | 使用频率 |
|-------|------|---------|
| `/risk-audit` | 安全风控审查 | 上线前 |
| `/config-lint` | 配置验证 | 每天 |

#### 🔧 维护 Skills
| Skill | 用途 | 使用频率 |
|-------|------|---------|
| `/db-evolve` | 数据库迁移 | 按需 |
| `/doc-update` | 文档同步 | 按需 |
| `/dev-log` | 开发日志管理 | 每天 |

#### 📈 报告 Skills
| Skill | 用途 | 使用频率 |
|-------|------|---------|
| `/trade-digest` | 交易报告生成 | 每周 |

#### 📚 参考 Skills
| Skill | 用途 | 来源 |
|-------|------|------|
| `/karpathy-guidelines` | 编程最佳实践 | Andrej Karpathy |

---

## 🚀 快速开始

### 方式 1：直接调用
```bash
# Claude Code 会自动识别
/trading-backtest
/strategy-new
```

### 方式 2：自然语言触发
```bash
# 系统会匹配到对应的 Skill
"backtest the grid strategy"
"create a new momentum strategy"
"check data integrity"
```

---

## 📖 典型工作流

### 🆕 推荐工作流（使用 workflow-control）

#### 开发新功能（自动化流程）
```
User: "添加 MACD 指标"

/workflow-control (自动触发)
   ↓ 
1. 理解需求：需要添加 MACD 技术指标
2. 调用 /project-context：查看策略层结构
3. 分析影响：
   - src/strategy/indicators.py
   - tests/unit/test_indicators.py
4. 生成计划：
   - 读取现有指标实现
   - 添加 calculate_macd() 函数
   - 编写单元测试
   - 验证代码规范
5. 等待确认：显示完整计划，等待用户同意
6. 执行：
   - 实现代码
   - /code-style 验证
   - /dev-log 记录
```

#### 新成员上手
```
1. /project-onboard
   → "了解项目背景、架构、技术栈"
   
2. /project-context
   → "查看目录结构和当前阶段"
   
3. /dev-log --recent
   → "阅读最近的开发日志"
   
4. 开始第一个任务
   → workflow-control 会引导你完成
```

#### 每日开发流程
```
Morning:
- /project-context → 查看昨日变更和当前状态
- /dev-log --recent → 了解团队进度

Development:
- 提出需求："实现 XXX 功能"
- /workflow-control 自动触发 → 分析 → 规划 → 确认
- 执行实现
- /code-style → 代码规范检查

Evening:
- /dev-log → 记录今日完成的工作
```

### 原有工作流（仍然有效）

#### 开发新策略（手动流程）
```
1. /strategy-new
   → "Create a new trend following strategy"
   
2. /config-lint
   → "Validate the strategy configuration"
   
3. /data-check
   → "Check BTC/USDT data completeness"
   
4. /trading-backtest
   → "Backtest trend strategy on last year"
   
5. /agent-optimize
   → "Let agent analyze the backtest results"
   
6. /risk-audit
   → "Audit risk controls before live trading"
```

### 每日开发流程
```
Morning:
- /data-check → 验证数据
- /config-lint → 检查配置

Development:
- 修改代码
- /trading-backtest → 测试

Evening:
- /doc-update → 更新文档
```

### 每周维护
```
Weekly:
- /trade-digest → 生成周报
- /agent-optimize → AI 分析
- /perf-analyze → 性能检查（如有问题）
```

---

## 💡 Skills 设计特点

### Token 优化
所有 Skills 都经过优化以减少 token 消耗：

- ✅ **增量分析** - 只处理变更的文件
- ✅ **数据库查询** - 使用聚合而非加载原始数据
- ✅ **模板化输出** - 预定义格式
- ✅ **采样分析** - 智能采样而非全量扫描

### 职责分离
每个 Skill 只做一件事：

- `/trading-backtest` - 只负责回测，不做优化
- `/agent-optimize` - 只负责调用 Agent，不执行回测
- `/risk-audit` - 只做安全检查，不修改代码

### 项目特定
专为加密货币交易系统设计：

- 理解时序数据库结构
- 熟悉策略配置格式
- 知道风控检查重点
- 集成 AI Agent 优化流程

---

## 📁 Skills 目录结构

```
.claude/skills/
├── README.md                    # Skills 总览
│
├── trading-backtest/
│   ├── SKILL.md                # Skill 定义
│   └── templates/              # 报告模板（待添加）
│
├── strategy-new/
│   ├── SKILL.md
│   └── templates/              # 策略模板（待添加）
│
├── data-check/
│   ├── SKILL.md
│   └── queries/                # SQL 查询（待添加）
│
├── agent-optimize/
│   ├── SKILL.md
│   ├── prompts/                # Agent 提示词（待添加）
│   └── schemas/                # 响应格式（待添加）
│
├── risk-audit/
│   ├── SKILL.md
│   └── rules/                  # 审查规则（待添加）
│
├── db-evolve/
│   ├── SKILL.md
│   └── templates/              # 迁移模板（待添加）
│
├── perf-analyze/
│   ├── SKILL.md
│   └── patterns/               # 优化模式（待添加）
│
├── doc-update/
│   ├── SKILL.md
│   └── templates/              # 文档模板（待添加）
│
├── config-lint/
│   ├── SKILL.md
│   └── schemas/                # JSON Schema（待添加）
│
└── trade-digest/
    ├── SKILL.md
    ├── templates/              # 报告模板（待添加）
    └── queries/                # SQL 查询（待添加）
```

---

## 🔧 后续完善

随着项目开发，可以添加：

### 模板文件
- 报告模板（Jinja2）
- 策略代码模板
- 测试用例模板

### 配置文件
- JSON Schema 验证规则
- SQL 查询模板
- Agent 提示词模板

### 规则文件
- 安全审查规则
- 性能优化模式
- 代码检查规则

**目前 SKILL.md 已完成，模板文件可在实际使用时逐步添加。**

---

## ✨ 使用建议

### 1. 从简单开始
先使用高频 Skills：
- `/config-lint` - 每次修改配置后
- `/trading-backtest` - 测试策略时

### 2. 逐步熟悉
随着开发进展，使用更多 Skills：
- `/agent-optimize` - AI 分析阶段
- `/risk-audit` - 准备上线前

### 3. 按需定制
如果 Skill 不完全符合需求，可以：
- 直接告诉 Claude 具体要求
- 修改 SKILL.md 指令部分
- 添加自定义模板文件

---

## 🎯 与内置 Skills 的区别

| 场景 | 内置 Skill | 自定义 Skill | 理由 |
|------|-----------|-------------|------|
| 代码审查 | `/code-review` | `/risk-audit` | 专注交易安全 |
| 运行验证 | `/verify` | `/trading-backtest` | 专注策略回测 |
| 性能优化 | `/simplify` | `/perf-analyze` | 专注性能瓶颈 |
| 一般优化 | - | `/agent-optimize` | 项目特有流程 |
| 数据检查 | - | `/data-check` | 时序数据特性 |

**建议：** 
- 通用任务用内置 Skills
- 项目特定任务用自定义 Skills

---

## 📞 获取帮助

### 查看 Skill 详情
```bash
# 查看特定 Skill 的完整说明
cat .claude/skills/trading-backtest/SKILL.md
```

### 修改 Skill
```bash
# 编辑 Skill 定义
code .claude/skills/trading-backtest/SKILL.md
```

### 添加模板
```bash
# 在对应的 templates/ 目录下添加文件
.claude/skills/trading-backtest/templates/report.md.j2
```

---

**创建时间：** 2026-06-12  
**Skills 数量：** 10 个  
**状态：** ✅ 已部署，可立即使用  
**位置：** `.claude/skills/`

**下一步：** 在开发过程中使用这些 Skills，根据实际需求添加模板文件。
