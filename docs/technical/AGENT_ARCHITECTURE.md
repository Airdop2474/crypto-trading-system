# AI Agent 架构设计（只分析不执行 + 策略进化闭环）

**文档版本：** v1.0  
**创建日期：** 2026-06-25  
**状态：** 已批准  
**优先级：** 高

---

## 目的

本文档定义 AI Agent 子系统的架构设计。Agent 子系统提供两类核心能力：

1. **AI 分析能力**：5 种结构化分析任务（回测解释、失败归因、风险清单、参数敏感性、每周复盘），所有输出标注"需要人工确认"，**只分析，不自动执行交易决策**。
2. **策略进化闭环**：Walk-Forward 搜索 → 安全校验 → LLM 解读 → 自动应用，在通过 6 道安全防线时自动替换运行中策略的参数。

**核心原则：**
- 只分析，不自动执行交易
- 所有 AI 输出标注"需要人工确认"
- 完整审计日志（DB 优先，JSON 回退）
- 结构化 JSON 输出
- 进化自动应用受多道安全阈值约束

---

## 架构概述

```
┌──────────────────────────────────────────────────────────────┐
│                     API 层 (/agent/*)                         │
│  analyze | audit-logs | adoption-rate | evolve               │
│  evolution-history | evolution-stats | hermes/*              │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                     Agent 核心层                              │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │ TradingAnalyzer  │  │ EvolutionEngine  │                 │
│  │ (5 种分析任务)   │  │ (策略进化闭环)   │                 │
│  └────────┬─────────┘  └────────┬─────────┘                 │
│           │                     │                            │
│  ┌────────▼─────────────────────▼─────────┐                 │
│  │              AuditLog (审计日志)        │                 │
│  └────────────────────────────────────────┘                 │
└──────────────────────────────────────────────────────────────┘
         │                     │                    │
         ▼                     ▼                    ▼
┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   记忆系统       │  │  LLM 抽象层      │  │  Hermes 桥接     │
│ MemoryStore     │  │  LLMClient       │  │  hermes_bridge   │
│ ContextBuilder  │  │ (OpenAI/         │  │ (文件 IPC +      │
│ Consolidator    │  │  Anthropic/local)│  │  HTTP 回调)      │
│ Embedder        │  │                  │  │                  │
└────────┬────────┘  └──────────────────┘  └──────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│                       持久化层                                │
│  PostgreSQL + pgvector (主)  │  JSON 文件 (回退)             │
│  agent_memories | audit_log | strategy_evolutions            │
└──────────────────────────────────────────────────────────────┘
```

**设计理念：**
- 分析与执行分离：Agent 永远不直接下单
- 两层存储降级：DB 不可用时所有组件回退 JSON 文件，保证主流程不中断
- 外部依赖静默失败：Hermes / LLM / Embedding 不可用时回退本地规则，不影响主流程
- 记忆驱动上下文：每次分析/进化注入历史记忆，让 AI 感知上下文

---

## 核心组件

### 1. TradingAnalyzer（AI 分析引擎）

**源文件：** `src/agent/analyzer.py`  
**类名：** `TradingAnalyzer`（导出别名见 `src/agent/__init__.py`）

**定位：** 只分析，不执行。所有输出包含 `requires_human_approval: True`。

提供 5 种分析任务（对应 `AI_USAGE_BOUNDARIES.md` 规范）：

| 方法 | 任务类型 | 输入 | 阶段 |
|------|---------|------|------|
| `analyze_backtest()` | `backtest` | 回测结果 + 指标 | Phase 2-3 |
| `analyze_failed_trades()` | `trade_attribution` | 交易记录 + 权益曲线 | Phase 4-6 |
| `analyze_risk_checklist()` | `risk_checklist` | 风险清单 dict | Phase 5-6 |
| `analyze_param_sensitivity()` | `param_sensitivity` | ParameterScanner 扫描 DataFrame | Phase 2-3 |
| `analyze_weekly_review()` | `weekly_review` | PaperTrading 报告 + 交易历史 | Phase 6 |

**统一输出格式：**

```python
{
    "task": "backtest_analysis",
    "analysis": "分析结论",
    "reasoning": { ... },              # 推理过程（结构化）
    "recommendation": "建议",
    "risks": ["风险提示列表"],
    "requires_human_approval": True,    # 恒为 True
    "confidence": 0.0 - 1.0
}
```

**关键行为：**
- 每次分析调用 `ContextBuilder` 注入历史记忆上下文
- 分析结果写入 `MemoryStore`（`MemoryKind.ANALYSIS` 或 `MemoryKind.DAILY`）
- 每次调用写审计日志（`AuditLog.record`）
- 内置规则引擎，不依赖外部 LLM（分析任务全部本地完成）

**回测分析（`analyze_backtest`）能力：**
- 收益来源分析（趋势 vs 震荡，基于胜率 + 盈亏比）
- 回撤分析（最大回撤、持续 K 线数、严重度 low/medium/high）
- 风险评估（交易次数、夏普、回撤、胜率、盈亏比多维度）
- 置信度计算（基于交易次数、夏普、回撤加权）

**失败交易归因（`analyze_failed_trades`）能力：**
- 亏损模式分析（平均亏损、最大单笔亏损、盈亏比）
- 信号质量评估（假信号率、信号质量评分）
- 最大连续亏损笔数
- 亏损时间分布（按小时统计）

**风险清单检查（`analyze_risk_checklist`）6 项强制检查：**
- 模拟交易天数 ≥ 60
- 风控测试通过
- API Key 已限制
- 初始资金 ≤ 500
- 最大回撤 < 10%
- 数据质量评分 ≥ 99%

**参数敏感性分析（`analyze_param_sensitivity`）能力：**
- 每个参数与收益的相关系数
- 最敏感参数识别
- 过拟合风险评估（高相关参数数 + 收益变异系数）

**每周复盘（`analyze_weekly_review`）能力：**
- 表现评级（excellent/good/normal/poor/critical）
- 异常检测（买卖不平衡、未平仓档位过多）
- 下周关注重点识别

---

### 2. EvolutionEngine（策略进化引擎）

**源文件：** `src/agent/evolution_engine.py`  
**类名：** `EvolutionEngine`

**定位：** 策略参数自动进化闭环，由前端 Agent 页面手动触发，满足安全阈值时自动替换运行中策略参数。

**进化流水线（9 步）：**

```
1. 获取策略类 (STRATEGY_REGISTRY)
2. 生成搜索空间 (ParamGridBuilder.build_grid)
3. Walk-Forward 搜索 (ParameterScanner.walk_forward, 3 窗口, 70% 样本内)
4. 提取最佳参数 (按 OOS Sharpe 排名)
5. 安全校验 (EvolutionGuardrails.validate, 6 道防线)
6. LLM 解读 (LLMClient.interpret_evolution, 注入历史进化记忆)
7. 自动应用 (multi_runner.update_strategy_params 热替换)
8. 审计日志 (AuditLog.record, phase="evolution")
9. 持久化到 DB (strategy_evolutions 表) + 写入记忆系统
```

**核心方法：**
- `evolve_strategy(strategy_id, current_strategy, current_params, ...)`：单个策略进化
- `evolve_all(slots, skip, multi_runner, risk_manager_state)`：批量进化（默认跳过 `buyhold`）

**strategy_id 解析约定：**
- `"grid-btc-usdt"` → 策略类型 `grid`，交易对 `BTC/USDT`
- 取第一段作为策略类型 key，从 `STRATEGY_REGISTRY` 获取策略类

**EvolutionResult 数据结构：**

```python
@dataclass
class EvolutionResult:
    strategy_id: str
    strategy_name: str
    old_params: Dict[str, Any]
    new_params: Optional[Dict[str, Any]]
    old_metrics: Dict[str, Any]
    new_metrics: Optional[Dict[str, Any]]
    guardrail_passed: bool
    guardrail_reasons: List[str]
    llm_interpretation: Optional[Dict[str, Any]]
    applied: bool
    timestamp: str
    walk_forward_windows: int
```

**自动应用条件：**
- `guardrail_passed == True`
- `auto_apply == True`
- `multi_runner` 已实现 `update_strategy_params()` 方法

**记忆写入：** 进化结果以 `MemoryKind.EVOLUTION` 写入记忆系统，标签为 `[strategy_key, strategy_id, "evolution"]`。

---

### 3. EvolutionGuardrails（进化安全校验）

**源文件：** `src/agent/evolution_guardrails.py`  
**类名：** `EvolutionGuardrails` + `EvolutionThresholds`

**定位：** 6 道防线确保自动应用的参数不会引入过度风险。

**默认阈值（`EvolutionThresholds`）：**

| 阈值 | 默认值 | 说明 |
|------|--------|------|
| `min_sharpe_improvement` | 0.10 | Sharpe 至少提升 10% |
| `max_drawdown_limit` | 0.15 | OOS 回撤 < 15% |
| `max_oos_degradation` | 0.50 | OOS Sharpe 标准差/均值 < 50% |
| `min_total_trades` | 10 | 每窗口至少 10 笔交易 |
| `min_oos_windows` | 2 | 至少 2 个窗口独立通过 |

**6 道防线（`validate()` 方法）：**

1. **风控状态检查**：`risk_manager_state != "ACTIVE"` 时直接拒绝
2. **参数合法性**：对照 `PARAM_SCHEMA` 的 min/max 校验
3. **Sharpe 提升**：`avg_oos_sharpe >= current_sharpe * (1 + 0.10)`
4. **OOS 回撤上限**：最差窗口回撤 ≤ 15%
5. **OOS 稳定性**：Sharpe 变异系数（std/|mean|）≤ 50%
6. **窗口共识**：独立通过（Sharpe>0 + 回撤≤上限 + 交易≥10）的窗口数 ≥ 2

---

### 4. LLMClient（LLM 抽象层）

**源文件：** `src/agent/llm_client.py`  
**类名：** `LLMClient`

**定位：** 仅用于策略进化解读（`interpret_evolution` 为唯一公共方法），不参与 5 种分析任务（分析任务全部本地规则完成）。

**Provider 检测优先级：**
```
LLM_API_KEY → OPENAI_API_KEY → ANTHROPIC_API_KEY → 本地规则回退
```

**支持协议：**
- OpenAI Chat Completions（默认模型 `gpt-4o-mini`）
- Anthropic Messages（默认模型 `claude-sonnet-4-20250514`）
- 通过 `LLM_BASE_URL` 可对接任意兼容提供商（DeepSeek / 智谱 / Ollama / vLLM）

**输出结构：**

```python
{
    "summary": "一句话总结",
    "reasoning": "参数调整逻辑分析",
    "risks": "潜在风险",
    "confidence": 0.0 - 1.0,
    "recommendation": "apply" | "reject" | "caution"
}
```

**降级策略：**
- 无 API key → 本地规则解读（`_local_interpret`），功能完整可用
- API 调用失败 → 回退本地规则解读
- 响应解析失败 → 返回低置信度（0.3）的 caution 建议

**本地规则解读逻辑（`_local_interpret`）：**
- 基础置信度 0.5
- Sharpe 上升 +0.2，下降 -0.1
- 回撤下降 +0.1，上升超 5% 扣 0.1
- 收益上升 +0.1
- OOS 波动 CV<0.3 加 0.1，CV>0.5 扣 0.1
- 置信度 ≥0.7 且 Sharpe 上升 → `apply`
- 置信度 <0.4 或 Sharpe 下降超 0.1 → `reject`

---

### 5. ParamGridBuilder（搜索空间生成）

**源文件：** `src/agent/param_grid_builder.py`  
**类名：** `ParamGridBuilder`

**定位：** 从策略 `PARAM_SCHEMA` 自动推导 walk_forward 所需的 `param_grid`，避免手写搜索空间。

**生成规则：**
- 跳过风控/开关类参数（`SKIP_PARAMS`：`max_consecutive_losses`、`max_daily_loss`、`initial_capital`、`enable_filters` 等）
- 跳过 bool 参数
- 有 min+max → `np.linspace` 均匀取 5 个点
- 有 min 无 max → 取 `[min, min*5]` 范围
- 价格类参数（`lower_price`/`upper_price`）→ 用行情 close 列分位数推导（5%~50% / 50%~95%）
- 组合数超 2000 → 逐轮缩减最大维度

---

### 6. AuditLog（审计日志）

**源文件：** `src/agent/audit_log.py`  
**类名：** `AuditLog`

**定位：** 记录所有 AI 分析调用，满足 `AI_USAGE_BOUNDARIES.md` 审计要求。

**存储策略：DB 优先（`audit_log` 表），JSON 文件回退（`data/reports/agent/audit_log.json`）。**

**记录字段：**

```python
{
    "id": "backtest_20260625_120000_abc12345",
    "timestamp": "ISO-8601 UTC",
    "phase": "Phase 2-3",           # 项目阶段
    "task": "backtest",             # 任务类型
    "input_summary": { ... },       # 输入摘要（脱敏）
    "output_summary": { ... },      # 输出摘要
    "model": "local-analyzer",      # 使用的模型
    "tokens_used": 0,               # token 用量
    "human_approved": False,        # 是否人工采纳
    "action_taken": None            # 执行的动作
}
```

**核心方法：**
- `record(task, phase, input_summary, output_summary, model, tokens_used)` → 返回 entry_id
- `update_approval(entry_id, approved, action)` → 更新采纳状态
- `get_logs(task, limit)` → 查询日志
- `get_adoption_rate(task)` → 统计 AI 建议采纳率

**临时目录检测：** 测试环境（`tmp_path`）自动跳过 DB，避免旧数据干扰。

---

## Agent 工作流

### 分析工作流（只分析不执行）

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│ API 请求    │ ──▶ │ TradingAnalyzer  │ ──▶ │ 审计日志    │
│ /agent/     │     │  analyze_*()     │     │ AuditLog    │
│ analyze     │     └────────┬─────────┘     └─────────────┘
└─────────────┘              │
                             ├──▶ ContextBuilder.build_analysis_context()
                             │     (注入历史记忆上下文)
                             │
                             ├──▶ 本地规则分析（5 种任务）
                             │
                             ├──▶ MemoryStore.store(MemoryKind.ANALYSIS)
                             │     (写入分析结论到记忆)
                             │
                             └──▶ Hermes push_analysis_request()
                                   (异步推送，不阻塞)

                        返回结构化报告（requires_human_approval=True）
```

**数据来源优先级（`/agent/analyze` 端点）：**
1. 实时纸盘数据（`live_data.build_analysis_data`）
2. 预跑数据回退（`service.get_state()`）

### 进化工作流（可自动应用）

```
┌─────────────┐     ┌──────────────────────────────────────────┐
│ API 请求    │ ──▶ │ EvolutionEngine.evolve_strategy()        │
│ /agent/     │     │                                          │
│ evolve      │     │  1. STRATEGY_REGISTRY 获取策略类         │
└─────────────┘     │  2. ParamGridBuilder.build_grid()        │
                    │  3. ParameterScanner.walk_forward()      │
                    │     (3 窗口, 70% 样本内)                 │
                    │  4. 提取最佳参数 (OOS Sharpe 排名)       │
                    │  5. EvolutionGuardrails.validate()       │
                    │     (6 道防线)                           │
                    │  6. ContextBuilder.build_evolution_context│
                    │     (注入历史进化记忆)                   │
                    │  7. LLMClient.interpret_evolution()      │
                    │     (LLM 解读, 失败回退本地规则)         │
                    │  8. 自动应用 (guardrail_passed +         │
                    │     auto_apply + multi_runner 热替换)    │
                    │  9. AuditLog.record(phase="evolution")   │
                    │ 10. 持久化 strategy_evolutions 表        │
                    │ 11. MemoryStore.store(MemoryKind.EVOLUTION)│
                    └──────────────────────────────────────────┘
                                          │
                                          ▼
                                   EvolutionResult
                                   (返回前端 + DB)
```

**批量进化（`evolve_all`）：** 遍历 `multi_runner.slots`，默认跳过 `buyhold` 策略类型，单策略异常不影响其他策略。

---

## 与外部系统的交互（Hermes / LLM）

### Hermes 桥接

**源文件：** `src/agent/hermes_bridge/adapter.py`

**通信方式：**
1. **文件 IPC（推送）**：写 JSON 事件到 `data/hermes_events/` 目录，Hermes skill 监控此目录
2. **HTTP 回调（接收）**：Hermes POST `/agent/hermes/callback` 返回分析结果

**Hermes CLI 检测：**
- 优先查找 `HERMES_HOME/venv/Scripts/hermes.exe`
- 回退 `PATH` 中的 `hermes` 命令
- 不可用时静默跳过所有推送，不影响主流程

**推送事件类型：**

| 函数 | 事件 kind | 触发场景 |
|------|-----------|---------|
| `push_analysis_request()` | `analysis_request` | 分析完成后推送请求 |
| `push_trade_closed()` | `trade_closed` | 平仓事件 |
| `push_risk_event()` | `risk_triggered` | 风控触发 |
| `push_daily_summary()` | `daily_summary` | 日结摘要 |
| `push_evolution_completed()` | `evolution_completed` | 进化完成 |

**事件开关：** `set_events_enabled(False)` 可关闭推送（模拟盘/生成数据跑批时使用）。

**回调处理（`handle_callback`）：**
- 接收 Hermes 分析结果，存入内存 `_callback_results` 字典
- `status == "completed"` 时写入 `MemoryStore`（`MemoryKind.ANALYSIS`，标签含 `hermes`）
- 前端通过 `/agent/hermes/result/{event_id}` 轮询查询结果

**状态查询（`get_status`）：** 返回 available、hermes_home、event_dir、pending_events、completed_analyses。

### LLM 交互

LLM 仅参与**策略进化解读**（`LLMClient.interpret_evolution`），不参与 5 种分析任务。

**调用流程：**
1. `EvolutionEngine` 构建 walk_forward summary（含历史进化记忆）
2. `LLMClient` 根据 provider 分发（OpenAI / Anthropic / 本地）
3. 调用失败或无 API key → 回退 `_local_interpret` 本地规则
4. 结果回填到 `EvolutionResult.llm_interpretation`，并记录 `provider`

**超时配置：** 15 秒（`_TIMEOUT_SECONDS`）。  
**Token 限制：** `max_tokens=800`，`temperature=0.3`。

### API 端点（9 个）

**源文件：** `src/api/app.py`（第 1008-1245 行）

| 端点 | 方法 | 限流 | 功能 |
|------|------|------|------|
| `/agent/analyze` | POST | 10/min | 触发 AI 分析（5 种任务） |
| `/agent/audit-logs` | GET | 10/min | 获取审计日志 |
| `/agent/adoption-rate` | GET | 10/min | AI 建议采纳率统计 |
| `/agent/evolve` | POST | 2/min | 触发策略进化 |
| `/agent/evolution-history` | GET | 10/min | 进化历史记录 |
| `/agent/evolution-stats` | GET | 10/min | 进化统计摘要 |
| `/agent/hermes/status` | GET | - | Hermes 连接状态 |
| `/agent/hermes/callback` | POST | - | Hermes 分析结果回调 |
| `/agent/hermes/result/{event_id}` | GET | - | 查询 Hermes 分析结果 |

**全局实例初始化（`app.py` 第 998-999 行）：**

```python
_audit_log = AuditLog()
_analyzer = TradingAnalyzer(_audit_log)
```

**`/agent/evolve` 端点流程：**
1. 从 `service.get_state()` 获取 `multi_runner` 和风控状态
2. 构建行情数据 dict `{symbol: DataFrame}`
3. 实例化 `EvolutionEngine(data, audit_log, auto_apply)`
4. 调用 `evolve_all(slots, skip={"buyhold"}, multi_runner, risk_manager_state)`
5. 返回 `EvolutionResult.to_dict()` 列表

**`/agent/evolve` 请求体：**

```python
class EvolveRequest(BaseModel):
    strategy_ids: list[str] | None = None   # None = 进化全部（排除 buyhold）
    auto_apply: bool = True
```

---

## 记忆系统

**源目录：** `src/agent/memory/`

记忆系统为 Agent 提供持久化记忆能力，让 AI 分析/进化时感知历史上下文。

### 架构

```
┌───────────────────────────────────────────────────────┐
│                   记忆系统架构                         │
│                                                       │
│  ┌──────────────┐  写入/检索  ┌──────────────────┐   │
│  │ ContextBuilder│ ◀────────▶ │   MemoryStore    │   │
│  │ (上下文构建)  │            │  (两层存储核心)  │   │
│  └──────────────┘            └────────┬─────────┘   │
│                                       │              │
│  ┌──────────────┐  维护       ┌───────▼──────────┐  │
│  │Consolidator  │ ◀────────▶ │  Embedder        │  │
│  │ (衰减/去重)  │            │ (embedding 生成) │  │
│  └──────────────┘            └──────────────────┘  │
└───────────────────────────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  PostgreSQL + pgvector (主存储)   │
    │  agent_memories 表                │
    │  (语义搜索: 1 - (embedding <=> )) │
    └───────────────────────────────────┘
                    │ (DB 不可用时回退)
                    ▼
    ┌───────────────────────────────────┐
    │  JSON 文件 (data/memory/          │
    │  memories.json, 最近 1000 条)     │
    └───────────────────────────────────┘
```

### 数据模型（`schemas.py`）

**记忆类型枚举（`MemoryKind`）：**

| 类型 | 说明 | 写入来源 |
|------|------|---------|
| `ANALYSIS` | AI 分析结论 | TradingAnalyzer / Hermes 回调 |
| `TRADE` | 已平仓交易 | - |
| `EVOLUTION` | 策略参数进化 | EvolutionEngine |
| `FEEDBACK` | 人类反馈 | `MemoryStore.feedback()` |
| `RISK` | 风控事件 | - |
| `DAILY` | 日结摘要 | TradingAnalyzer（周报） |

**核心数据类：**
- `MemoryEntry`：一条记忆（kind, content, tags, source, memory_id, score, feedback_count, feedback_avg_score, created_at）
- `SearchQuery`：检索请求（query, kind, tags, limit, min_score）
- `SearchResult`：检索结果（entry, similarity, matched_tags）
- `FeedbackRecord`：人类反馈（memory_id, score 1-5, note）

### MemoryStore（存储核心）

**源文件：** `src/agent/memory/store.py`  
**类名：** `MemoryStore`（全局单例 `get_memory_store()`）

**两层存储：**
1. **PostgreSQL + pgvector（主）**：支持语义搜索（`1 - (embedding <=> query_embedding)`）
2. **JSON 文件（回退）**：`data/memory/memories.json`，保留最近 1000 条

**写入（`store`）：** 自动生成 embedding，DB 优先写入，失败回退 JSON。

**语义搜索（`search`）：**
- 有 embedding → 按 `1 - (embedding <=> :embedding)` 相似度降序
- 无 embedding → 按时间倒序 + 标签过滤
- 支持类型过滤 + 标签过滤 + 最低分数过滤

**人类反馈（`feedback`）：** 评分 1-5，更新 `feedback_count` 和 `feedback_avg_score`（滚动平均）。

**检索常量：**
- `DEFAULT_SEARCH_LIMIT = 10`
- `MAX_SEARCH_LIMIT = 100`
- `MIN_FEEDBACK_SCORE = 1`，`MAX_FEEDBACK_SCORE = 5`

### EmbeddingGenerator（向量生成）

**源文件：** `src/agent/memory/vector.py`  
**类名：** `EmbeddingGenerator`（全局单例 `get_embedder()`）

**定位：** 将记忆文本转为 embedding 向量，供语义搜索使用。

- 优先使用 OpenAI `text-embedding-3-small`（1536 维）
- 检测条件：`LLM_API_KEY` 或 `OPENAI_API_KEY` 存在
- 无 API key → 返回空向量，检索仅依赖标签 + 时间（`available = False`）
- 支持单条 `generate()` 和批量 `generate_batch()`
- 生成失败静默返回空向量，不影响主流程

### ContextBuilder（上下文构建）

**源文件：** `src/agent/memory/context_builder.py`  
**类名：** `ContextBuilder`

**定位：** 从记忆库检索相关信息，拼成上下文文本注入 LLM prompt。

**三种上下文构建方法：**

| 方法 | 调用方 | 检索内容 |
|------|--------|---------|
| `build_analysis_context(strategy_id, task)` | TradingAnalyzer（回测分析） | 同类分析历史 + 最近交易 + 人类反馈 |
| `build_evolution_context(strategy_id, strategy_key)` | EvolutionEngine | 同类策略进化历史 |
| `build_daily_context(tags)` | TradingAnalyzer（周报） | 近期日结摘要 + 风控事件 |

**输出格式：**

```
[相关历史分析]
  - [2026-06-20 14:30] #grid #backtest (评分:4.5/反馈3次)
    策略总收益 12.5% | 胜率 58%

[最近交易]
  - [2026-06-24 09:15] #grid
    profit: 125.30 | symbol: BTC/USDT
```

### MemoryConsolidator（记忆维护）

**源文件：** `src/agent/memory/consolidator.py`  
**类名：** `MemoryConsolidator`

**定位：** 定时维护记忆库，防止无限膨胀。由后台定时任务调用（如每日一次）。

**维护内容（`run_once()`）：**
1. **衰减**：所有记忆 `score *= 0.95`（旧记忆自然降权）
2. **修剪**：删除 `score < 0.1` 的记忆
3. **去重**：`content` 完全相同的合并（保留最早）

**配置：**
- `decay_rate = 0.95`
- `prune_threshold = 0.1`
- `merge_threshold = 0.95`

**注意：** 维护仅对 PostgreSQL 生效，DB 不可用时跳过。

---

## 关键原则

### 1. 只分析，不执行

**Agent 永远不直接下单：**
- 5 种分析任务全部 `requires_human_approval: True`
- 分析任务使用本地规则引擎，不调用外部 LLM
- 所有 AI 输出供人工决策参考

### 2. 进化受多道防线约束

**自动应用参数必须全部通过：**
- 6 道 Guardrails 安全校验
- `auto_apply` 开关开启
- 风控状态为 `ACTIVE`
- `multi_runner` 实现 `update_strategy_params()`

### 3. 两层存储降级

**所有持久化组件 DB 优先 + JSON 回退：**
- AuditLog：`audit_log` 表 → `data/reports/agent/audit_log.json`
- MemoryStore：`agent_memories` 表 → `data/memory/memories.json`
- EvolutionEngine：`strategy_evolutions` 表 → 仅 DB（失败非致命）

### 4. 外部依赖静默失败

**所有外部依赖不可用时回退本地：**
- Hermes 不可用 → 跳过推送
- LLM 不可用 → 本地规则解读
- Embedding 不可用 → 空向量，标签 + 时间检索
- DB 不可用 → JSON 文件回退

### 5. 记忆驱动上下文

**每次分析/进化注入历史记忆：**
- TradingAnalyzer 调用 `ContextBuilder.build_analysis_context`
- EvolutionEngine 调用 `ContextBuilder.build_evolution_context`
- 分析结论和进化结果回写记忆系统，形成闭环

---

## 数据表

### agent_memories（记忆表）

```sql
CREATE TABLE agent_memories (
    id                  VARCHAR PRIMARY KEY,
    kind                VARCHAR,          -- analysis/trade/evolution/feedback/risk/daily
    content             JSONB,
    embedding           vector(1536),     -- pgvector, text-embedding-3-small
    tags                VARCHAR[],
    score               FLOAT DEFAULT 1.0,
    source              VARCHAR,
    feedback_count      INT DEFAULT 0,
    feedback_avg_score  FLOAT DEFAULT 0.0,
    created_at          TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ
);
```

### audit_log（审计日志表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR | 主键 |
| timestamp | TIMESTAMPTZ | 时间戳 |
| phase | VARCHAR | 项目阶段 |
| task | VARCHAR | 任务类型 |
| input_summary | JSONB | 输入摘要 |
| output_summary | JSONB | 输出摘要 |
| model | VARCHAR | 模型 |
| tokens_used | INT | token 用量 |
| human_approved | BOOL | 是否人工采纳 |
| action_taken | VARCHAR | 执行动作 |

### strategy_evolutions（进化记录表）

由 `EvolutionRepository` 管理，字段对应 `EvolutionResult`：strategy_id、strategy_name、old_params、new_params、old_metrics、new_metrics、guardrail_passed、guardrail_reasons、llm_provider、llm_summary、llm_confidence、applied、walk_forward_windows。

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `src/agent/analyzer.py` | TradingAnalyzer，5 种分析任务 |
| `src/agent/evolution_engine.py` | EvolutionEngine，策略进化闭环 |
| `src/agent/evolution_guardrails.py` | EvolutionGuardrails，6 道安全防线 |
| `src/agent/llm_client.py` | LLMClient，LLM 抽象层 |
| `src/agent/param_grid_builder.py` | ParamGridBuilder，搜索空间生成 |
| `src/agent/audit_log.py` | AuditLog，审计日志 |
| `src/agent/memory/store.py` | MemoryStore，记忆存储核心 |
| `src/agent/memory/vector.py` | EmbeddingGenerator，向量生成 |
| `src/agent/memory/consolidator.py` | MemoryConsolidator，记忆维护 |
| `src/agent/memory/context_builder.py` | ContextBuilder，上下文构建 |
| `src/agent/memory/schemas.py` | 数据模型与枚举 |
| `src/agent/hermes_bridge/adapter.py` | Hermes 桥接（推送 + 回调） |
| `src/api/app.py` | 9 个 `/agent/*` API 端点 |

---

**文档状态：** 已批准  
**优先级：** 高  
**文档版本：** v1.0  
**更新日期：** 2026-06-25

**本文档基于代码实际实现编写，所有组件、方法、阈值、端点均可在源文件中验证。**
