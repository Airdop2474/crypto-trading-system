# AI 使用边界

**文档版本：** v1.0  
**创建日期：** 2026-06-13  
**状态：** ✅ 已批准

---

## 目的

明确 AI Agent 在不同阶段的使用边界和禁止事项。

**核心原则：** AI 早期只做分析，不做自动执行。

---

## AI 使用阶段划分

### Phase 1-6: AI 只分析，不执行

**允许的 AI 用途：**

#### 1. 回测报告解释
```python
# Phase 2-3
prompt = f"""
分析以下回测结果：
- 总收益：23%
- 最大回撤：-18%
- 胜率：62%
- 交易次数：150

请解释：
1. 收益来源（趋势还是震荡）
2. 回撤原因
3. 潜在风险
"""
```

#### 2. 失败交易归因
```python
# Phase 4-6
prompt = f"""
分析失败交易：
- 时间：2024-03-15 08:00
- 信号：买入
- 入场价：$42,000
- 出场价：$41,200
- 亏损：-1.9%

请分析：
1. 为什么亏损？
2. 信号是否有问题？
3. 下次如何避免？
"""
```

#### 3. 风险清单检查
```python
# Phase 5-6
prompt = f"""
检查实盘准备清单：
- Paper Trading: 60天通过
- 风控测试：通过
- API Key：已限制权限
- 初始资金：$500

是否有遗漏的风险？
"""
```

#### 4. 参数敏感性分析总结
```python
# Phase 2-3
prompt = f"""
参数敏感性测试结果：
- 网格数量 ±20%: 收益变化 25%
- 价格区间 ±20%: 收益变化 45%
- 单网格仓位 ±20%: 收益变化 15%

请总结：
1. 哪个参数最敏感？
2. 是否在可接受范围内？
3. 建议优化方向（不自动执行）
"""
```

#### 5. 每周策略复盘
```python
# Phase 6
prompt = f"""
本周实盘数据：
- 收益：+2.3%
- 交易次数：15
- 胜率：60%
- 最大回撤：-1.5%

请分析：
1. 表现是否正常？
2. 有无异常信号？
3. 下周关注重点？
"""
```

**重要：** 所有 AI 输出只作为建议，不自动执行。

---

### Phase 7+: AI 仍然只建议

**即使实盘稳定，AI 也不能自动执行。**

**允许的增强：**
- 更深度的模式识别
- 更复杂的归因分析
- 策略组合建议

**仍然禁止：**
- 自动调参
- 自动切换策略
- 自动增加仓位

---

## 禁止事项（所有阶段）

### ❌ 1. 自动调参

**禁止：**
```python
# 错误示例
ai_suggestion = agent.optimize_parameters(backtest_result)
strategy.update_parameters(ai_suggestion)  # ❌ 禁止
```

**正确：**
```python
ai_suggestion = agent.analyze_parameters(backtest_result)
print(f"AI 建议：{ai_suggestion}")
print("请人工审查后决定是否采纳")
# 等待人工确认
if user_confirms:
    strategy.update_parameters(ai_suggestion)  # ✅ 人工确认
```

### ❌ 2. 自动决策是否交易

**禁止：**
```python
# 错误示例
ai_decision = agent.should_trade(market_data)
if ai_decision == "YES":
    execute_trade()  # ❌ 禁止
```

**正确：**
```python
# 策略生成信号（基于明确规则）
signal = strategy.generate_signal(market_data)

# AI 只分析信号质量
ai_analysis = agent.analyze_signal_quality(signal, market_data)
print(f"AI 评估：{ai_analysis['score']}/10")
print(f"AI 建议：{ai_analysis['recommendation']}")

# 人工决策
if user_confirms and signal.action == "BUY":
    execute_trade()  # ✅ 人工确认
```

### ❌ 3. 自动切换策略

**禁止：**
```python
# 错误示例
if ai.detect_market_regime_change():
    switch_to_strategy("trend_following")  # ❌ 禁止
```

### ❌ 4. 自动扩大仓位

**禁止：**
```python
# 错误示例
if ai.confidence_score > 0.8:
    position_size *= 2  # ❌ 禁止
```

### ❌ 5. 定义形态标准

**禁止：**
```python
# 错误示例（价格行为策略）
pin_bar_definition = ai.learn_pattern_from_data()  # ❌ 禁止
```

**正确：**
```python
# 人工定义规则
pin_bar_definition = {
    'shadow_to_body_ratio': 2.5,
    'body_percentage': 0.1
}

# AI 只评估质量
ai.evaluate_pattern_quality(pin_bar_definition)  # ✅ 分析
```

---

## AI 输出格式要求

**所有 AI 输出必须包括：**

1. **分析结论**
2. **理由说明**
3. **建议（如果有）**
4. **风险提示**
5. **明确标注"需要人工确认"**

**示例：**
```json
{
  "analysis": "回测收益主要来自震荡市场，趋势市场表现较差",
  "reasoning": "从交易分布看，80%盈利交易发生在波动率2-4%区间",
  "recommendation": "建议增强趋势过滤器",
  "risks": "趋势过滤可能减少交易频率",
  "requires_human_approval": true,
  "confidence": 0.75
}
```

---

## 审计要求

### AI 调用日志

**必须记录：**
```python
ai_call_log = {
    'timestamp': '2026-06-13T10:30:00Z',
    'phase': 'Phase 6',
    'task': 'weekly_review',
    'input': {...},
    'output': {...},
    'tokens_used': 1500,
    'model': 'hermes-v3',
    'human_approved': false,  # 是否被采纳
    'action_taken': None  # 如果采纳，记录执行的操作
}
```

### 每周审计

**Phase 6 实盘阶段：**
- 每周审查 AI 调用日志
- 统计采纳率
- 评估 AI 建议质量
- 检查是否有违规自动执行

---

## 未来放开条件（Phase 8+）

**如果未来考虑半自动化，必须满足：**

### 前置条件
- [ ] 实盘稳定运行 6 个月以上
- [ ] 连续 3 个月盈利
- [ ] 风控测试全部通过
- [ ] AI 建议历史准确率 >70%
- [ ] 用户明确同意

### 限制条件
- ✅ 参数变更有白名单（只能调整特定参数）
- ✅ 变更幅度有限制（±10%）
- ✅ 每次变更有审计记录
- ✅ 可一键回滚
- ✅ 人工可随时关闭

### 禁止场景
- ❌ 禁止 AI 调整风控参数
- ❌ 禁止 AI 增加总仓位
- ❌ 禁止 AI 关闭风控
- ❌ 禁止 AI 操作提币

**重要：** 目前（Phase 0-7）不考虑自动化，专注验证系统。

---

## Skills 设计约束

### /agent-analyze（不是 agent-optimize）

**正确命名：**
- ✅ `/agent-analyze` - AI 分析工具
- ❌ `/agent-optimize` - 容易误导为自动优化

**Skill 定义：**
```markdown
# agent-analyze

## Description
使用 AI Agent 分析回测结果、交易表现、策略假设。

**重要：只分析，不执行。**

## When to Use
- 回测后分析结果
- 每周实盘复盘
- 失败交易归因

## Instructions
1. 收集数据
2. 调用 AI Agent
3. 展示分析结果
4. 标注"需要人工决策"
5. 不自动执行任何建议

## Output
AI 分析报告（纯文本，不执行）
```

---

## 验收清单

**Phase 1-6 必须满足：**

- [ ] AI 只用于分析，无自动执行代码
- [ ] 所有 AI 输出标注"需要人工确认"
- [ ] AI 调用有完整日志
- [ ] 禁止事项在代码中强制检查
- [ ] Skills 命名正确（analyze 不是 optimize）
- [ ] 每周审计 AI 使用情况

**Phase 7 必须重新评估：**

- [ ] 实盘运行 6 个月以上
- [ ] AI 建议质量评估报告
- [ ] 用户明确同意半自动化
- [ ] 新的限制措施文档化

---

**文档状态：** ✅ 已批准  
**适用阶段：** Phase 1-7  
**优先级：** 最高  
**更新日期：** 2026-06-13

**核心原则：AI 是助手，不是驾驶员。**
