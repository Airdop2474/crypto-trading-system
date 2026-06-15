# 项目辅助 Skills 设计方案

## 新增 Skills（6个）

### 1. `/project-onboard` - 项目入门引导

**目的：** 帮助新成员快速理解项目

**功能：**
- 读取 PROJECT_PLAN.md 和 ENGINEERING.md 的关键部分
- 展示项目架构图（ASCII）
- 列出关键目录和文件
- 说明技术栈和依赖关系
- 输出"新手任务"清单

**Token 优化：**
- 只展示文档摘要，不读取全文
- 使用预定义的架构图模板
- 缓存项目基本信息

---

### 2. `/project-context` - 项目上下文速查

**目的：** 快速了解项目当前状态和路径

**功能：**
- 显示项目目录结构（树形）
- 当前开发阶段（Phase 0-6）
- 关键路径说明（数据层、策略层等）
- 最近修改的文件（git status）
- 待实现的模块列表

**Token 优化：**
- 只显示关键路径，不遍历全部文件
- 缓存目录结构（除非有 git 变更）
- 使用符号链接而非完整路径

---

### 3. `/code-style` - 代码规范检查器

**目的：** 确保代码符合项目规范

**功能：**
- 检查代码格式（black, isort）
- 验证类型注解（mypy）
- 检查 docstring 完整性
- 验证命名规范（snake_case, CamelCase）
- 输出不符合规范的代码行

**Token 优化：**
- 只扫描 git diff 的文件
- 使用工具输出而非读取全部代码
- 提供快速修复命令

---

### 4. `/dev-log` - 开发日志管理

**目的：** 记录和查询开发进度

**功能：**
- 记录今日完成的任务
- 查询历史开发日志
- 生成进度报告
- 追踪 Phase 完成度
- 标记阻塞问题

**Token 优化：**
- 日志存储在 `.claude/dev-log/YYYY-MM-DD.md`
- 只读取最近 7 天的日志
- 使用模板化格式

---

### 5. `/token-budget` - Token 使用优化器

**目的：** 分析和优化 Token 消耗

**功能：**
- 分析对话历史中的 Token 使用
- 识别高消耗操作（读取大文件、重复查询）
- 建议优化方案（缓存、分块、采样）
- 估算任务 Token 成本
- 生成 Token 使用报告

**Token 优化：**
- 只分析最近的对话（不读取完整历史）
- 使用启发式规则而非完整分析
- 提供预定义的优化模式库

---

### 6. `/workflow-control` - 工作流程总控 ⭐核心

**目的：** 控制开发流程，避免直接改代码

**功能：**
1. **需求分析阶段**
   - 理解用户需求
   - 询问澄清问题
   - 调用 `/project-context` 了解现状
   
2. **规划阶段**
   - 列出需要修改的文件
   - 评估影响范围
   - 推荐使用的 Skills
   - 生成任务清单
   
3. **验证阶段**
   - 调用 `/code-style` 检查规范
   - 调用 `/risk-audit` 检查安全
   - 调用 `/config-lint` 验证配置
   
4. **执行确认**
   - 展示完整计划
   - 等待用户确认
   - 记录到 `/dev-log`

**使用模式：**
```
User: "添加 RSI 指标到策略"

Assistant (通过 /workflow-control):
1. 理解需求...
2. 调用 /project-context 查看策略层结构
3. 计划：
   - 修改 src/strategy/indicators.py
   - 更新 tests/unit/test_indicators.py
   - 需要调用 /code-style 验证
4. 估算 Token: ~5000
5. 是否继续？[y/n]
```

**Token 优化：**
- 使用决策树而非完整分析
- 预定义常见任务的工作流
- 只读取必要的上下文

---

## Skills 依赖关系

```
/workflow-control (总控)
    ↓
    ├─→ /project-context (了解现状)
    ├─→ /project-onboard (新功能理解)
    ├─→ /code-style (代码规范)
    ├─→ /risk-audit (安全检查)
    ├─→ /config-lint (配置验证)
    ├─→ /token-budget (成本估算)
    └─→ /dev-log (记录进度)
```

---

## 典型工作流

### 场景 1：新成员加入
```
1. /project-onboard
   → 了解项目背景、架构、技术栈
   
2. /project-context
   → 查看当前目录结构和开发阶段
   
3. /dev-log --recent
   → 阅读最近的开发日志
```

### 场景 2：添加新功能
```
1. User: "添加 MACD 指标"

2. /workflow-control 自动执行：
   - 理解需求
   - /project-context 查看策略层
   - 列出影响文件
   - /token-budget 估算成本
   - 等待确认
   
3. 用户确认后：
   - 执行代码修改
   - /code-style 检查
   - /dev-log 记录
```

### 场景 3：代码审查
```
1. /code-style --check-all
   → 检查所有代码规范
   
2. /risk-audit
   → 安全审查
   
3. /token-budget --analyze
   → 分析 Token 使用是否合理
```

---

## 实现优先级

**高优先级（立即创建）：**
1. `/workflow-control` - 总控 Skill
2. `/project-context` - 项目上下文
3. `/dev-log` - 开发日志

**中优先级（本周）：**
4. `/project-onboard` - 新人引导
5. `/code-style` - 代码规范

**低优先级（按需）：**
6. `/token-budget` - Token 优化

---

这个设计方案是否符合你的需求？我可以立即开始创建这些 Skills。
