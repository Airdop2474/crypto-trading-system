# AI 优化方案：多角色辩论稿

**文档版本**：v1.0
**创建日期**：2026-06-25
**状态**：辩论稿（含初始方案 + 4 角色辩论 + 最终方案）

---

## 参与角色

| 角色 | 代号 | 关注点 | 底线 |
|------|------|--------|------|
| 量化策略师 | **QS** | 策略 alpha、回测可信度、参数稳健性 | 不能做降低策略质量的妥协 |
| 风控工程师 | **RE** | 安全性、熔断、止损、仓位控制 | 不能放松任何风控约束 |
| 系统架构师 | **SA** | 代码质量、可维护性、向后兼容 | 不能引入破坏性变更 |
| 产品经理 | **PM** | 用户价值、ROI、交付速度 | 不能做用户感知不到的功能 |

---

# 第一部分：初始方案

## 问题清单（来自代码审查）

| # | 问题 | 文件 | 严重程度 |
|---|------|------|---------|
| P1 | `auto_apply` 实际不生效（`update_strategy_params()` 未实现） | evolution_engine.py:237 | 高 |
| P2 | 最优参数只取单窗口最高 Sharpe，过拟合风险 | evolution_engine.py:195 | 高 |
| P3 | Sharpe 提升检查对负值失效 | evolution_guardrails.py:72 | 中 |
| P4 | TradingAnalyzer 没有接入 LLM，纯规则 | analyzer.py | 中 |
| P5 | 无 Monte Carlo 验证 | - | 中 |
| P6 | 无参数稳定性分析 | - | 中 |
| P7 | LLM 只用于进化解读一个场景 | llm_client.py | 低 |
| P8 | `_assess_signal_quality()` 把亏损=假信号 | analyzer.py:280 | 低 |

## 初始方案：3 阶段修复

### 阶段 1：Bug 修复（1 周）

1. **修复 P1**：实现 `MultiStrategyRunner.update_strategy_params()`
2. **修复 P2**：`_extract_best()` 改为跨窗口聚合——取所有窗口中 OOS Sharpe 中位数最高的参数组合
3. **修复 P3**：`EvolutionGuardrails.validate()` 增加 `current_sharpe < 0` 的特殊处理
4. **修复 P8**：重新定义"假信号"——只有入场理由不成立的亏损才算假信号，正常止损不算

### 阶段 2：AI 能力增强（2.5 周）

5. **Monte Carlo 模拟器**：新建 `src/backtest/monte_carlo.py`
6. **参数稳定性分析**：新建 `src/backtest/robustness.py`
7. **TradingAnalyzer 接入 LLM**：`analyze_backtest()` 和 `analyze_weekly_review()` 增加 LLM 解读路径
8. **LLM 扩展到更多场景**：失败交易归因、市场日报

### 阶段 3：智能化闭环（2 周）

9. **自然语言交易日志**：每笔交易自动生成解释
10. **策略健康度评分**：综合多维度给策略打分
11. **Telegram 通知**：进化结果、风控告警、每日汇总

**总工时**：约 5.5 周

---

# 第二部分：四角色辩论

---

## 第一轮：阶段 1 的优先级

**PM 先发言**：

> 阶段 1 的 4 个 bug 修复我同意，但我想问：P1（auto_apply 失效）真的是高优先级吗？用户手动在前端点一下"应用"也就 3 秒钟。相比之下 P2（过拟合参数选择）才是真正的风险——选了一个过拟合的参数自动应用到实盘，那损失是真金白银。我建议 P2 排在 P1 前面。

**RE 响应**：

> 我同意 PM 的判断。P2 的过拟合风险比我之前标注的更严重。让我补充一个细节：当前 `_extract_best()` 取的是 `wf_df["out_sample_sharpe"].idxmax()`，也就是"单个窗口 OOS Sharpe 最高"的那一行。但如果 3 个窗口中有一个 Sharpe 特别高（比如 2.5），另外两个接近 0 或负数，这个参数组合大概率是过拟合的。正确的做法应该是：
>
> 1. 对每个参数组合，取所有窗口 OOS Sharpe 的**中位数**
> 2. 按中位数排序，取最高的
> 3. 额外检查：如果任意一个窗口的 OOS Sharpe < 0，直接排除
>
> 这比简单取 max 要稳健得多。

**QS 补充**：

> RE 说的方案我基本同意，但有一个细节问题。如果 walk_forward 只有 3 个窗口，中位数就是第 2 大的值，区分度很低。我建议同时增加窗口数到 5（从 `n_windows=3` 改为 `n_windows=5`），虽然回测时间会增加，但参数选择的可靠性显著提升。另外，P3（负 Sharpe 通过校验）的问题比想象的更严重——如果 current_sharpe = -0.5，那么 `target = -0.5 * 1.1 = -0.55`，任何 OOS Sharpe > -0.55 都能通过。这意味着一个更差的参数组合也能通过校验。

**SA 总结**：

> 好，阶段 1 的优先级我重新排序：
>
> 1. **P2**（过拟合参数选择）— 风险最高，先修
> 2. **P3**（负 Sharpe 校验失效）— 与 P2 相关，一起修
> 3. **P1**（auto_apply 失效）— 功能缺失，但有手动替代
> 4. **P8**（假信号定义）— 影响分析准确性，但不阻塞
>
> 工时不变，还是 1 周，但顺序变了。

**全员同意**。

---

## 第二轮：阶段 2 的取舍

**PM 先发言**：

> 阶段 2 列了 4 项，我有异议。Monte Carlo 和参数稳定性是"让回测更可信"，TradingAnalyzer 接入 LLM 是"让分析更智能"。但如果只能选 2 个，我选 Monte Carlo + 参数稳定性。原因：LLM 分析目前不是瓶颈——用户看回测报告时最关心的是"这个结果可不可信"，不是"AI 怎么解读"。而且 LLM 有成本（API 调用费）和不确定性（输出质量不稳定）。

**QS 强烈反对**：

> PM 说"LLM 分析不是瓶颈"我不同意。让我举一个真实场景：用户跑完一个策略的回测，看到 Sharpe 1.8、最大回撤 8%，觉得很好。但他不知道的是：这 8% 的回撤集中在最近一个月，而且恰好是 BTC 从 70000 涨到 75000 那段——策略只是因为买入持有就赚了。**纯规则分析器看不出来这个问题**，因为它只看数字，不看时间分布和市场环境。LLM 可以结合市场背景给出更有洞察的分析。
>
> 但是，我同意 PM 说的"LLM 成本和不确定性"。我的建议是：**不把 LLM 作为必须项，而是作为增强项**。具体做法：
> 1. `_local_interpret()` 保持为默认路径（零成本、零延迟）
> 2. LLM 解读作为可选增强，用户可以在前端手动触发"AI 深度分析"
> 3. 两种路径的输出格式完全一致，前端不需要区分

**RE 插话**：

> 等一下，我要从风控角度说一个被忽略的点。Monte Carlo 模拟器不只是"让回测更可信"——它能回答一个关键问题：**"在最差的 5% 情景下，我会亏多少？"** 这就是 VaR/CVaR。现在系统完全没有这个能力。用户只知道"最大回撤 15%"，不知道"95% 的情况下回撤不会超过 15%，但有 5% 的概率会到 30%"。这个信息对实盘决策至关重要。
>
> 我建议 Monte Carlo 必须做，而且要**集成到 EvolutionEngine 的安全校验中**。进化后的新参数不仅要通过现有的 6 道防线，还要通过 Monte Carlo 验证——95% VaR 不能超过阈值。

**SA 分析**：

> 让我评估一下每项的工程复杂度：
>
> | 功能 | 新增代码量 | 改动现有代码 | 风险 |
> |------|-----------|-------------|------|
> | Monte Carlo | ~200 行新文件 | 不改现有 | 低 |
> | 参数稳定性 | ~150 行新文件 | EvolutionEngine +10 行 | 低 |
> | TradingAnalyzer 接入 LLM | ~100 行改动 | analyzer.py 大改 | 中 |
> | LLM 扩展场景 | ~200 行新文件 | 不改现有 | 低 |
>
> 从工程角度看，Monte Carlo 和参数稳定性是**纯新增**，不改现有代码，风险最低。TradingAnalyzer 接入 LLM 需要改 600 行的现有模块，风险更高。
>
> 我同意 QS 的"LLM 作为增强项"方案，但要加一个约束：**TradingAnalyzer 的改动不能改变现有接口**。所有 LLM 增强都是在现有方法内部增加一个可选的 LLM 路径，对外接口不变。

**PM 妥协**：

> 好，我接受 QS 的"LLM 作为增强项"方案。但我加一个条件：**LLM 调用必须有超时和降级**。如果 LLM 调用失败或超时（> 15 秒），必须自动降级到规则分析，不能阻塞用户操作。这个 LLMClient 已经有 `_local_interpret()` 降级，所以实际上是满足的。
>
> 阶段 2 最终方案：
> 1. Monte Carlo（必须，集成到安全校验）
> 2. 参数稳定性（必须，集成到进化引擎）
> 3. TradingAnalyzer LLM 增强（可选，不改接口）
> 4. LLM 扩展场景（可选，优先做失败交易归因）

**全员同意**。

---

## 第三轮：阶段 3 的争议

**PM 先发言**：

> 阶段 3 列了 3 项：交易日志、健康度评分、Telegram 通知。我的排序是：Telegram > 交易日志 > 健康度评分。原因：
> - Telegram 是**实盘必备**——用户不可能 24 小时盯着 Grafana
> - 交易日志是**复盘必备**——没有日志就无法改进
> - 健康度评分是**锦上添花**——有最好，没有也行

**RE 强烈支持 Telegram**：

> 我必须强调 Telegram 的重要性。当前系统有一个致命盲区：**熔断触发后用户可能几小时都不知道**。RiskManager 触发了 PAUSED 状态，策略停止交易，但用户没有收到任何通知。如果这时候市场在走趋势行情，用户错过了入场机会；如果策略是因为真正的风险暂停的，用户不知道也不会去检查。
>
> 我建议 Telegram 通知不只是"锦上添花"，而是**P0 优先级**，应该放到阶段 1 之前。具体通知触发条件：
> 1. 熔断触发（PAUSED/STOPPED）
> 2. 手动恢复（resume/reset）
> 3. 进化结果（新参数应用/拒绝）
> 4. 每日汇总（收益、交易笔数、风险指标）

**QS 对交易日志有想法**：

> 交易日志我同意做，但我要提出一个更高效的方案。现在 LLMClient 已经有了，交易日志不需要复杂的 LLM 调用——用**模板生成**就够了：
>
> ```
> "在 BTC 66500 处买入。策略：RSI Momentum。
>  信号：RSI(14)=28，超卖区间；价格在 EMA50 上方，趋势过滤通过。
>  市场状态：RANGING（ADX=18）。"
> ```
>
> 这种结构化的模板比 LLM 生成的自然语言更准确、更可靠、零成本。LLM 可以作为"升级版"——用户手动点击"AI 解读"时才调用。
>
> 好处：
> 1. 零 API 成本
> 2. 输出 100% 准确（因为是模板，不会编造）
> 3. 实现简单（~100 行）

**SA 提出架构问题**：

> 我要提一个被所有人忽略的问题：**交易日志的数据从哪来？**
>
> 当前 `BacktestEngine.run()` 返回的 trades 列表里有 `profit`、`time`、`side`、`price`、`quantity`，但**没有信号原因**。策略的 `on_bar()` 只返回 `Order` 对象（side/tag/fraction），不返回"为什么生成这个信号"。
>
> 要做交易日志，需要：
> 1. 策略在生成信号时附带一个 `reason` 字段
> 2. 引擎在记录交易时保存这个 reason
> 3. 日志生成器读取 reason 并格式化
>
> 这意味着要改 `Order` dataclass 和 `BacktestEngine` 的交易记录逻辑。改动量不大，但需要所有策略都配合。

**RE 问健康度评分**：

> 健康度评分我有保留意见。现在系统的"分析"已经太多了——回测分析、失败归因、参数敏感性、每周复盘。用户真的会去看一个额外的"健康度分数"吗？
>
> 我的建议是：**不做独立的健康度评分模块**，而是把健康度概念**融入进化引擎**。具体做法：
> - EvolutionEngine 进化后，如果新参数的 Monte Carlo 95% CVaR 比旧参数差，直接标记为"不健康"
> - 这个信息已经包含在进化结果里，不需要额外模块

**PM 总结**：

> 好，阶段 3 最终方案：
>
> 1. **Telegram 通知**（RE 强烈要求提前，我同意）
> 2. **交易日志**（QS 的模板方案 + SA 的 reason 字段改造）
> 3. ~~健康度评分~~（RE 建议融入进化引擎，取消独立模块）

**全员同意**。

---

## 第四轮：被忽略的问题

**SA 提出**：

> 我发现一个没人提到的问题：`AuditLog.record()` 的方法签名在两个调用方之间不一致。
>
> - `TradingAnalyzer` 调用时传的是 `task, phase, input_summary, output_summary`
> - `EvolutionEngine._record_audit()` 传的是 `phase, task, input_summary, output_summary, model, tokens_used, human_approved, action_taken`
>
> 但 `AuditLog.record()` 的签名是 `task, phase, input_summary, output_summary, model, tokens_used`——**没有 `human_approved` 和 `action_taken` 参数**。
>
> 这意味着 `EvolutionEngine._record_audit()` 传了两个多余参数，Python 不会报错（因为是 kwargs），但这些参数会被忽略。审计日志里永远记录不到"是否人工采纳"和"执行的动作"。
>
> 这是一个 **数据完整性 bug**，必须修复。

**RE 震惊**：

> 等等，这意味着 `get_adoption_rate()` 返回的"采纳率"永远是 0？因为 `human_approved` 永远不会被写入？

**SA 确认**：

> 是的。`AuditLog.record()` 不接受 `human_approved` 参数，所以这个字段永远是默认值 `False`。`get_adoption_rate()` 统计的是 `human_approved=True` 的比例，结果永远是 0%。
>
> 修复方案：给 `AuditLog.record()` 增加 `human_approved` 和 `action_taken` 参数。

**PM 补充**：

> 这个 bug 也解释了为什么前端 Agent 页面的"采纳率"一直显示 0%——不是用户不采纳，是数据没写进去。必须修。

**全员同意，P9 加入问题清单**。

---

## 第五轮：最终优先级投票

**SA 主持**：

> 现在我们有 9 个问题 + 新增功能。让我列出所有待办项，每人投 3 票（最重要/次重要/第三重要）：

| # | 待办项 | QS | RE | SA | PM | 总票 |
|---|--------|----|----|----|----|------|
| P2 | 过拟合参数选择修复 | ★ | ★ | | | 2 |
| P3 | 负 Sharpe 校验修复 | | ★ | | | 1 |
| P1 | auto_apply 实现 | | | ★ | | 1 |
| P9 | AuditLog 签名修复 | | | ★ | ★ | 2 |
| N1 | Monte Carlo 模拟器 | ★ | | ★ | ★ | 3 |
| N2 | 参数稳定性分析 | | | | | 0 |
| N3 | TradingAnalyzer LLM 增强 | | | | | 0 |
| N4 | Telegram 通知 | | ★ | | ★ | 2 |
| N5 | 交易日志（模板版） | | | | | 0 |

**投票结果排序**：

1. **N1 Monte Carlo**（3 票）— QS/SA/PM 都认为最重要
2. **P2 过拟合修复**（2 票）— QS/RE 认为最关键
3. **P9 AuditLog 修复**（2 票）— SA/PM 认为影响数据完整性
4. **N4 Telegram 通知**（2 票）— RE/PM 认为实盘必备
5. **P3 负 Sharpe 修复**（1 票）— RE 认为与 P2 相关
6. **P1 auto_apply 实现**（1 票）— SA 认为功能完整性

**PM 提出异议**：

> 等等，N2（参数稳定性）和 N3（LLM 增强）0 票？不是说好要做的吗？

**QS 解释**：

> 不是不做，是优先级被其他项盖过了。N2 的核心逻辑（参数微扰测试）可以**合并到 Monte Carlo 里**——Monte Carlo 本身就是对交易序列的随机扰动，我们可以额外加一个"参数微扰"模式。N3（LLM 增强）是"可选项"，在基础功能稳定后再加。

**SA 同意**：

> QS 说的"合并到 Monte Carlo"我支持。这样 N2 不需要独立文件，直接在 `monte_carlo.py` 里加一个 `ParameterPerturbation` 类。减少模块数量，降低维护成本。

**RE 补充**：

> N5（交易日志）也是 0 票，但我不认为它不重要。问题是 SA 说的"需要改 Order dataclass 和所有策略"——这个改动范围太大，不适合在本轮做。我建议交易日志**先做简化版**：只记录已有的信息（side/price/quantity/profit/time），不记录信号原因。信号原因的改造留到下一轮。

**PM 同意**：

> 简化版交易日志可以做到 50 行代码以内，而且对复盘已经很有价值了。同意。

---

# 第三部分：最终方案

---

## 最终优先级排序

| 优先级 | 任务 | 来源 | 预计工时 | 依赖 |
|--------|------|------|---------|------|
| **P0** | Monte Carlo 模拟器 + 参数微扰 | N1 + N2 合并 | 3 天 | 无 |
| **P0** | 过拟合参数选择修复 | P2 | 1 天 | 无 |
| **P0** | 负 Sharpe 校验修复 | P3 | 0.5 天 | 无 |
| **P0** | AuditLog 签名修复 | P9 | 0.5 天 | 无 |
| **P1** | Telegram 通知 | N4 | 2 天 | 无 |
| **P1** | auto_apply 实现 | P1 | 1.5 天 | P2 修复后 |
| **P1** | 交易日志（简化版） | N5 简化 | 1 天 | 无 |
| **P2** | TradingAnalyzer LLM 增强 | N3 | 2 天 | P0 完成后 |
| **P2** | 假信号定义修复 | P8 | 0.5 天 | 无 |

**总工时**：约 12 天（2.5 周）

---

## 阶段 1：基础修复 + Monte Carlo（1 周）

### 任务 1.1：Monte Carlo 模拟器 + 参数微扰

**文件**：`src/backtest/monte_carlo.py`（新建）

**设计要点**（来自辩论结论）：

```python
class MonteCarloSimulator:
    """Monte Carlo 模拟器（含参数微扰）。"""

    def simulate_trades(
        self,
        trades: List[Dict],
        initial_capital: float,
        n_simulations: int = 1000,
    ) -> MonteCarloResult:
        """交易序列随机打乱，计算收益分布。

        返回：
            median_return, var_95, cvar_95, probability_of_loss,
            worst_max_drawdown, confidence_intervals
        """
        ...

    def simulate_params(
        self,
        strategy_class,
        base_params: Dict[str, Any],
        data: pd.DataFrame,
        perturbation_pct: float = 0.10,
        n_samples: int = 20,
    ) -> ParamRobustnessResult:
        """参数微扰测试。

        对每个参数 ±perturbation_pct，观察收益变化。
        返回 stability_score（0-1）和各参数的敏感度。
        """
        ...
```

**集成到 EvolutionEngine**：

```python
# evolution_engine.py 新增步骤
def evolve_strategy(self, ...):
    ...
    # 步骤 4.5: Monte Carlo 验证
    mc = MonteCarloSimulator()
    mc_result = mc.simulate_trades(trades, initial_capital=10000)

    if mc_result.var_95 < -0.25:  # 95% VaR 超过 -25%
        passed = False
        reasons.append(f"Monte Carlo 95% VaR={mc_result.var_95:.2%}，超过安全阈值")

    # 步骤 4.6: 参数稳定性
    robustness = mc.simulate_params(strategy_class, best_params, market_data)
    if robustness.stability_score < 0.5:
        passed = False
        reasons.append(f"参数稳定性评分={robustness.stability_score:.2f}，低于阈值 0.5")
    ...
```

**验收标准**：
- [ ] 1000 次模拟 < 5 秒
- [ ] 参数微扰 20 个样本 < 30 秒
- [ ] 集成到 EvolutionEngine 后现有测试全部通过

### 任务 1.2：过拟合参数选择修复

**文件**：`src/agent/evolution_engine.py`

**改动**：

```python
# 旧代码（evolution_engine.py:195）
def _extract_best(self, wf_df, strategy_class):
    best_idx = wf_df["out_sample_sharpe"].idxmax()  # 单窗口最优
    ...

# 新代码
def _extract_best(self, wf_df, strategy_class):
    # 按参数组合分组，计算每个组合的 OOS Sharpe 中位数
    fixed_cols = {"window", "in_sample_return", "out_sample_return",
                  "out_sample_sharpe", "out_sample_max_drawdown", "out_sample_trades"}
    param_cols = [c for c in wf_df.columns if c not in fixed_cols]

    # 排除任何窗口 OOS Sharpe < 0 的组合
    valid_mask = wf_df.groupby(param_cols)["out_sample_sharpe"].transform("min") >= 0
    valid_df = wf_df[valid_mask]

    if valid_df.empty:
        # 所有组合都有负 Sharpe 窗口，回退到原始逻辑
        valid_df = wf_df

    # 按参数组合聚合，取中位数
    grouped = valid_df.groupby(param_cols)["out_sample_sharpe"].median()
    best_param_combo = grouped.idxmax()

    # 提取该组合的最佳窗口数据
    ...
```

**同时增加窗口数**：`n_windows=3` → `n_windows=5`

**验收标准**：
- [ ] 过拟合参数不再被选中（用已知过拟合场景测试）
- [ ] 窗口数增加后回测时间 < 2 分钟（5 窗口 × 参数网格）

### 任务 1.3：负 Sharpe 校验修复

**文件**：`src/agent/evolution_guardrails.py`

**改动**：

```python
# 旧代码（evolution_guardrails.py:72）
target_sharpe = current_sharpe * (1 + t.min_sharpe_improvement)

# 新代码
if current_sharpe >= 0:
    target_sharpe = current_sharpe * (1 + t.min_sharpe_improvement)
else:
    # 负 Sharpe 时，目标是"至少比当前好 10% 的绝对改善"
    # 例如 current=-0.5, 目标=-0.45（改善 0.05）
    target_sharpe = current_sharpe - current_sharpe * t.min_sharpe_improvement
    # 简化：target = current * (1 - improvement)
    # current=-0.5, improvement=0.10 → target=-0.45
```

**验收标准**：
- [ ] 负 Sharpe 场景下校验行为正确
- [ ] 正 Sharpe 场景行为不变

### 任务 1.4：AuditLog 签名修复

**文件**：`src/agent/audit_log.py`

**改动**：

```python
# 旧签名
def record(self, task, phase, input_summary, output_summary, model, tokens_used):

# 新签名
def record(
    self,
    task: str,
    phase: str,
    input_summary: Dict[str, Any],
    output_summary: Dict[str, Any],
    model: str = "local-analyzer",
    tokens_used: int = 0,
    human_approved: bool = False,      # 新增
    action_taken: Optional[str] = None, # 新增
) -> str:
```

**验收标准**：
- [ ] EvolutionEngine 的审计日志能正确记录 `human_approved`
- [ ] `get_adoption_rate()` 返回非零值

---

## 阶段 2：通知与热替换（1 周）

### 任务 2.1：Telegram 通知

**文件**：`src/monitor/telegram_notifier.py`（新建）

**设计要点**（来自辩论结论）：

```python
class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        ...

    def send_circuit_breaker(self, strategy_id: str, reason: str) -> None:
        """熔断触发通知（P0 级别，必须即时送达）。"""
        ...

    def send_evolution_result(self, result: EvolutionResult) -> None:
        """进化结果通知。"""
        ...

    def send_daily_summary(self, summary: Dict) -> None:
        """每日汇总（定时发送）。"""
        ...
```

**集成点**：
- `RiskManager._trigger_breaker()` 调用 `send_circuit_breaker()`
- `EvolutionEngine.evolve_strategy()` 最后调用 `send_evolution_result()`
- 定时任务（APScheduler 或 cron）调用 `send_daily_summary()`

**验收标准**：
- [ ] 熔断通知延迟 < 5 秒
- [ ] 通知发送失败不影响主流程（异步 + try/except）

### 任务 2.2：auto_apply 实现

**文件**：`src/execution/multi_runner.py`

**改动**：

```python
# MultiStrategyRunner 新增方法
def update_strategy_params(
    self,
    strategy_id: str,
    new_params: Dict[str, Any],
) -> bool:
    """热替换策略参数。

    找到对应的 StrategySlot，重新创建策略实例。
    """
    slot = self.slots.get(strategy_id)
    if slot is None:
        return False

    strategy_class = type(slot.config.strategy)
    init_params = {**slot.config.strategy.parameters, **new_params}

    try:
        new_strategy = strategy_class(**init_params)
        slot.config.strategy = new_strategy
        logger.info(f"策略 {strategy_id} 参数热替换成功: {new_params}")
        return True
    except Exception as e:
        logger.error(f"策略 {strategy_id} 参数热替换失败: {e}")
        return False
```

**验收标准**：
- [ ] 进化引擎 auto_apply=True 时参数自动生效
- [ ] 热替换后策略状态正确重置

### 任务 2.3：交易日志（简化版）

**文件**：`src/agent/trade_journal.py`（新建）

**设计要点**（来自辩论结论）：

```python
class TradeJournal:
    """简化版交易日志（模板生成，零 LLM 成本）。"""

    def log_trade(
        self,
        trade: Dict,
        strategy_name: str,
        market_state: str = "unknown",
    ) -> str:
        """生成交易日志条目。

        使用模板生成，不调用 LLM。
        """
        side = "买入" if trade.get("side") == "BUY" else "卖出"
        return (
            f"[{trade.get('time')}] {side} {trade.get('symbol', 'BTC/USDT')} "
            f"@ {trade.get('price', 0):.2f}, 数量 {trade.get('quantity', 0):.6f}, "
            f"策略 {strategy_name}, 市场 {market_state}"
        )
```

**集成到 BacktestEngine 和 PaperTradingRunner**：
- 交易记录时自动调用 `journal.log_trade()`
- 日志存储到 `trade_notes` 字段（数据库）或 `data/reports/trades/`（JSON）

**验收标准**：
- [ ] 每笔交易都有日志条目
- [ ] 日志格式统一、可读

---

## 阶段 3：AI 增强（0.5 周）

### 任务 3.1：TradingAnalyzer LLM 增强

**文件**：`src/agent/analyzer.py`

**改动**（来自辩论结论：不改接口，内部增加可选 LLM 路径）：

```python
class TradingAnalyzer:
    def __init__(self, audit_log=None, llm_client=None):
        self.audit_log = audit_log or AuditLog()
        self.llm_client = llm_client  # 可选

    def analyze_backtest(self, results, metrics=None, strategy_name="Unknown"):
        # 原有规则分析（保持不变）
        report = self._rule_based_analysis(results, metrics, strategy_name)

        # 可选 LLM 增强
        if self.llm_client is not None:
            llm_insight = self._llm_enhanced_analysis(results, report)
            report["llm_insight"] = llm_insight  # 附加字段，不覆盖原有

        return report

    def _llm_enhanced_analysis(self, results, rule_report):
        """LLM 深度分析（可选路径）。"""
        try:
            prompt = self._build_analysis_prompt(results, rule_report)
            return self.llm_client.interpret_evolution(...)  # 复用现有方法
        except Exception:
            return None  # 失败时不影响主报告
```

**验收标准**：
- [ ] 无 LLM 时行为完全不变
- [ ] 有 LLM 时报告增加 `llm_insight` 字段
- [ ] LLM 调用失败时自动降级

### 任务 3.2：假信号定义修复

**文件**：`src/agent/analyzer.py`

**改动**：

```python
# 旧代码
def _assess_signal_quality(self, winners, losers):
    false_signal_rate = len(losers) / total  # 亏损 = 假信号

# 新代码
def _assess_signal_quality(self, winners, losers, trades):
    # 假信号 = 入场后短期（< N 根 K 线）内止损出场的交易
    # 正常止损出场不算假信号
    false_signals = [
        t for t in losers
        if t.get("hold_bars", 999) < 5  # 持仓不到 5 根 K 线就止损
        and t.get("exit_reason") == "stop_loss"  # 出场原因是止损
    ]
    false_signal_rate = len(false_signals) / total
```

**注意**：这需要 `hold_bars` 和 `exit_reason` 字段，当前 trades 没有。简化方案：先用时间差判断（出场时间 - 入场时间 < 阈值）。

**验收标准**：
- [ ] 假信号率下降（对比旧逻辑）
- [ ] 不影响现有测试

---

## 总结

### 辩论达成的共识

1. **Monte Carlo 比 LLM 更重要**（3 票 vs 0 票）——回测可信度是基础，AI 解读是上层
2. **参数稳定性合并到 Monte Carlo**——减少模块数量，降低维护成本
3. **LLM 作为可选增强**——不改现有接口，失败自动降级
4. **Telegram 是实盘必备**——熔断通知必须即时送达
5. **交易日志用模板**——零成本、100% 准确、LLM 作为可选升级
6. **健康度评分取消**——融入进化引擎的 Monte Carlo 验证
7. **AuditLog bug 必须修**——影响数据完整性和前端展示

### 辩论中的分歧与妥协

| 分歧 | 初始立场 | 最终妥协 |
|------|---------|---------|
| PM 认为 LLM 不重要，QS 认为很重要 | PM: 延后 / QS: 必须做 | LLM 作为可选增强，不阻塞主流程 |
| RE 要求 Telegram 提前到 P0 | 阶段 3 → 阶段 2 | 放到阶段 2，与 auto_apply 并行 |
| 健康度评分 | 阶段 3 要做 | RE 建议融入进化引擎，取消独立模块 |
| 交易日志需要改 Order | SA: 改动范围大 | RE 建议简化版，不改 Order，只记录已有信息 |

### 最终工时

| 阶段 | 工时 | 内容 |
|------|------|------|
| 阶段 1 | 1 周 | Monte Carlo + 3 个 bug 修复 |
| 阶段 2 | 1 周 | Telegram + auto_apply + 交易日志 |
| 阶段 3 | 0.5 周 | LLM 增强 + 假信号修复 |
| **总计** | **2.5 周** | **比初始方案节省 3 周** |

### 与初始方案的差异

| 初始方案 | 最终方案 | 变化原因 |
|---------|---------|---------|
| 阶段 1：4 bug 修复 | 阶段 1：3 bug + Monte Carlo | Monte Carlo 优先级提升（3 票） |
| 阶段 2：Monte Carlo + 参数稳定性 + LLM | 阶段 2：Telegram + auto_apply + 日志 | Telegram 提前，LLM 延后 |
| 阶段 3：Telegram + 日志 + 健康度 | 阶段 3：LLM 增强 + 假信号修复 | 健康度取消，LLM 降级为可选 |
| 总工时 5.5 周 | 总工时 2.5 周 | 砍掉独立健康度模块，LLM 降级 |

---

*辩论结束*
