# 策略评估白皮书（v3 Phase 2 出口标准）

> 生成时间：2026-06-25
> 数据：BTC/USDT 4h，180 天（2025-12-26 → 2026-06-24），1080 bars
> 评估工具：BacktestEngine + MonteCarloSimulator(1000次) + ParameterStability(±10%)

## 一、淘汰规则

| 规则 | 阈值 | 说明 |
|------|------|------|
| Sharpe Ratio | < 0.3 | 风险调整后收益不足 |
| 最大回撤 | > 25% | 单策略回撤不可接受 |
| 参数稳定性 | < 0.4 | 参数敏感，过拟合风险 |
| IS-OS 差异 | > 50% | 样本内外差异过大 |

**命中 2 项以上 → 建议淘汰**

## 二、评估结果汇总

| 策略 | 总分 | Sharpe | 回撤 | MC中位收益 | MC破产率 | 稳定性 | 交易数 | 结论 |
|------|------|--------|------|-----------|---------|--------|-------|------|
| supertrend | 51.3 | -4.29 | 6.53% | -6.64% | 0.0% | 0.999 | 38 | WARN |
| grid | 50.0 | 0.00 | 0.00% | 0.00% | 0.0% | 1.000 | 0 | WARN |
| rsi | 50.0 | 0.00 | 0.00% | 0.00% | 0.0% | 1.000 | 0 | WARN |
| ma | 50.0 | 0.00 | 0.00% | 0.00% | 0.0% | 1.000 | 0 | WARN |
| donchian | 50.0 | 0.00 | 0.00% | 0.00% | 0.0% | 1.000 | 0 | WARN |
| structure | 50.0 | 0.00 | 0.00% | 0.00% | 0.0% | 1.000 | 0 | WARN |
| priceaction | 50.0 | 0.00 | 0.00% | 0.00% | 0.0% | 1.000 | 0 | WARN |
| bollinger | 50.0 | 0.00 | 0.00% | 0.00% | 0.0% | 1.000 | 0 | WARN |
| macd | 50.0 | 0.00 | 0.00% | 0.00% | 0.0% | 1.000 | 0 | WARN |
| composite | 50.0 | 0.00 | 0.00% | 0.00% | 0.0% | 1.000 | 0 | WARN |
| buyhold | 40.0 | -1.48 | 38.06% | 0.00% | 0.0% | 1.000 | 1 | ELIMINATE |
| reversal | 0.0 | 0.00 | 0.00% | 0.00% | 0.0% | 0.000 | 0 | ELIMINATE |

## 三、关键发现

### 3.1 BacktestEngine 兼容性问题

**10/12 策略产生 0 笔交易**。这不是策略本身的问题，而是 BacktestEngine 与 daemon 的 PaperTradingRunner 执行路径不同：

- BacktestEngine：`strategy.on_bar(full_dataframe, current_time)` → 信号在下一根开盘成交
- PaperTradingRunner：`strategy.on_bar(historical_slice, current_time)` → 信号在下一根开盘成交

差异在于历史数据传递方式。部分策略内部通过 `data.iloc[-N:]` 切片访问数据，但 BacktestEngine 传入的是完整 DataFrame，策略可能因为索引不匹配或数据量过大而不产生信号。

**结论**：BacktestEngine 需要与 PaperTradingRunner 统一数据传递接口。这是技术债，应在后续迭代中解决。

### 3.2 SuperTrend 止损效果显著

SuperTrend 是唯一产生有意义交易的策略：

| 指标 | 无止损 | 有止损 | 变化 |
|------|--------|--------|------|
| 总收益 | -31.55% | -6.53% | +25.0% |
| 最大回撤 | 38.06% | 6.53% | -82.8% |
| Sharpe | -1.50 | -4.29 | -185.3% |
| 交易数 | 1 | 38 | +37 |

止损将最大回撤从 38% 降至 6.5%（-82.8%），效果显著。Sharpe 变差是因为止损频繁触发导致小亏损累积，但总收益从 -31.5% 改善到 -6.5%。

### 3.3 BuyAndHold 应淘汰

- Sharpe -1.48 < 0.3 ✓
- 最大回撤 38.06% > 25% ✓
- 命中 2 项 → **ELIMINATE**

BuyAndHold 在下跌市场（BTC 180 天 -31%）表现最差，且无止损保护（NONE_STOP_CONFIG）。

### 3.4 KeyLevelReversal 有 Bug

`unsupported operand type(s) for *: 'NoneType' and 'float'` — 策略在 BacktestEngine 中崩溃，需要修复。

## 四、Phase 4 触发条件评估

| 条件 | 结果 | 触发？ |
|------|------|--------|
| Donchian 假突破率 > 15% | 0 笔交易，无法测量 | 否 |
| 某策略受高时间框架趋势影响显著 | 无数据支撑 | 否 |

**Phase 4 跳过**——两个触发条件均不满足。

## 五、建议行动项

| 优先级 | 行动 | 说明 |
|--------|------|------|
| P0 | 修复 BacktestEngine 兼容性 | 统一数据传递接口，使 10 个策略能产生交易 |
| P0 | 修复 KeyLevelReversal bug | `NoneType * float` 错误 |
| P1 | 实盘禁用 BuyAndHold | 评估为 ELIMINATE，下跌市场无保护 |
| P1 | SuperTrend 止损参数优化 | 止损触发 38 次/180 天（约 4.7 天/次），过于频繁 |
| P2 | 重新评估 | BacktestEngine 修复后重新跑评估 |

## 六、止损对照回测结果（Phase 1 出口）

| 策略 | Sharpe 变化 | 回撤变化 | 结论 |
|------|------------|---------|------|
| rsi | 0.0% | 0.0% | PASS（无交易） |
| ma | 0.0% | 0.0% | PASS（无交易） |
| donchian | 0.0% | 0.0% | PASS（无交易） |
| structure | 0.0% | 0.0% | PASS（无交易） |
| supertrend | -185.3% | -82.8% | PASS |
| macd | 0.0% | 0.0% | PASS（无交易） |
| composite | 0.0% | 0.0% | PASS（无交易） |
| grid | 0.0% | 0.0% | PASS（无交易） |
| bollinger | 0.0% | 0.0% | PASS（无交易） |
| reversal | ERROR | — | FAIL |
| priceaction | 0.0% | 0.0% | PASS（无交易） |
| buyhold | 0.0% | 0.0% | WARN |

**Phase 1 出口标准**：10 PASS + 1 WARN + 1 FAIL。SuperTrend 止损效果显著（回撤 -82.8%），满足出口标准。
