# Crypto Trading System - Claude Code Skills

Custom skills for crypto trading system development and maintenance.

## 📊 Skills Overview (17个)

### 🎯 工作流控制
1. **workflow-control** ⭐ MASTER - 工作流程总控，先分析再执行
2. **project-context** - 项目上下文速查
3. **project-onboard** - 新人入门引导

### 🛠️ 开发 Skills
4. **strategy-new** - 策略脚手架生成器
5. **trading-backtest** - 回测执行器
6. **data-check** - 数据健康检查
7. **code-style** - 代码规范检查

### 🔍 优化 Skills
8. **agent-optimize** - AI 驱动优化
9. **perf-analyze** - 性能分析器
10. **token-budget** - Token 使用优化

### 🔒 安全 Skills
11. **risk-audit** - 安全审查
12. **config-lint** - 配置验证

### 🔧 维护 Skills
13. **db-evolve** - 数据库迁移
14. **doc-update** - 文档同步
15. **dev-log** - 开发日志

### 📈 报告 Skills
16. **trade-digest** - 交易报告生成

### 📚 参考 Skills
17. **karpathy-guidelines** - Andrej Karpathy 编程指南

---

## 🚀 推荐工作流

### 新功能开发
```
1. /workflow-control  (自动触发)
   ↓ 调用 /project-context (了解现状)
   ↓ 分析影响
   ↓ 生成计划
   ↓ 等待确认
   
2. 执行实现
   ↓ /code-style (验证)
   ↓ /risk-audit (如涉及资金)
   
3. /dev-log (记录)
```

### 新成员上手
```
1. /project-onboard   → 了解项目
2. /project-context   → 查看结构
3. /dev-log --recent  → 阅读进度
4. 开始第一个任务
```

### 每日工作
```
Morning:
- /project-context (查看昨日变更)
- /dev-log --recent (了解进度)

Development:
- /workflow-control (规划任务)
- 实现代码
- /code-style (验证)

Evening:
- /dev-log (记录今日工作)
```

---

## 📁 目录结构

```
.claude/skills/
├── README.md                          # 本文件
│
├── workflow-control/ ⭐               # 总控
├── project-context/                   # 上下文
├── project-onboard/                   # 入门
│
├── trading-backtest/                  # 回测
├── strategy-new/                      # 新策略
├── data-check/                        # 数据检查
├── code-style/                        # 代码规范
│
├── agent-optimize/                    # AI 优化
├── perf-analyze/                      # 性能分析
├── token-budget/                      # Token 优化
│
├── risk-audit/                        # 安全审查
├── config-lint/                       # 配置验证
│
├── db-evolve/                         # 数据库
├── doc-update/                        # 文档
├── dev-log/                           # 日志
│
├── trade-digest/                      # 报告
└── karpathy-guidelines/               # Karpathy 指南
```

---

## 💡 核心特性

### 工作流控制
- ✅ /workflow-control 自动拦截代码变更请求
- ✅ 强制执行：理解 → 规划 → 确认 → 执行
- ✅ 避免盲目修改代码

### Token 优化
- ✅ 增量分析（Git diff）
- ✅ 数据库聚合查询
- ✅ 模板化输出
- ✅ 智能采样

### 项目协作
- ✅ /dev-log 追踪进度
- ✅ /project-context 快速定位
- ✅ /code-style 统一规范

---

## 🎯 使用频率

**每次开发前（必须）：**
- /workflow-control - 自动触发

**每天：**
- /project-context - 查看现状
- /code-style - 代码检查
- /dev-log - 记录进度

**每周：**
- /agent-optimize - AI 分析
- /trade-digest - 生成报告
- /token-budget - 成本分析

**按需：**
- /strategy-new - 新策略
- /risk-audit - 安全检查
- /perf-analyze - 性能问题
- /db-evolve - 数据库变更

---

## 📝 Skills 作用域

**重要：** 这些 Skills 是项目级别的：
- ✅ 只在本项目中生效
- ✅ 提交到 Git，团队共享
- ✅ 不影响其他项目

---

## 🔗 外部 Skills

**Karpathy Guidelines：**
- 来源：https://github.com/multica-ai/andrej-karpathy-skills
- 用途：Andrej Karpathy 的编程最佳实践
- 调用：/karpathy-guidelines

---

Created: 2026-06-12
Total Skills: 17 (16 custom + 1 external)
Status: Ready to use
