# 方案 A：策略层增强方案

**文档版本**：v1.0
**创建日期**：2026-06-25
**状态**：草案
**目标**：从 8 个独立策略进化到策略生态系统，提升策略适应性和覆盖面

---

## 一、背景与问题

### 1.1 现状

当前系统有 8 个策略，覆盖震荡（Grid）和趋势（RSI/MA/Donchian/Structure/SuperTrend）两大类，以及混合型（Reversal）和基准（BuyHold）。所有策略均继承 `RiskAwareStrategy`，有统一的熔断保护。

### 1.2 核心问题

1. **策略类型单一**：趋势策略占 5/8，均值回归只有 Grid 一个，缺乏对市场微结构的利用
2. **参数静态**：所有策略参数在初始化时固定，不会根据市场状态自动调整
3. **单时间框架**：所有策略只看当前 K 线（4h），没有利用更高时间框架的趋势信息
4. **无成交量分析**：Donchian 突破没有成交量确认，RSI 没有成交量背离检测
5. **策略间无协同**：MultiStrategyRunner 已支持多策略并行，但策略之间没有信息共享

---

## 二、增强方案

### 2.1 新增策略

#### 2.1.1 均值回归策略 — BollingerBand Strategy

**文件**：`src/strategy/bollinger_band.py`
**Registry key**：`"bb"`
**类型**：均值回归

**原理**：价格触及 BB 下轨 + RSI < 35 时买入，触及上轨 + RSI > 65 时卖出。BB 带宽收窄时（波动率压缩）暂停交易，等待突破。

**核心参数**：

| 参数 | 类型 | 默认值 | 安全范围 | 说明 |
|------|------|--------|----------|------|
| `bb_period` | int | 20 | 10-50 | BB 计算周期 |
| `bb_std` | float | 2.0 | 1.0-3.0 | 标准差倍数 |
| `rsi_period` | int | 14 | 5-30 | RSI 周期 |
| `rsi_oversold` | float | 35.0 | 20-50 | RSI 超卖阈值 |
| `rsi_overbought` | float | 65.0 | 50-80 | RSI 超买阈值 |
| `bandwidth_pause` | float | 0.02 | 0-0.1 | BB 带宽低于此值暂停 |

**与 Grid 的互补**：Grid 是固定区间，BB 是自适应区间。Grid 在区间边界固定，BB 随波动率自动调整。

**实现要点**：
- 继承 `RiskAwareStrategy`，复用熔断逻辑
- 增量计算 BB（用 rolling mean + rolling std 的增量更新）
- `PARAM_SCHEMA` 定义完整，支持 EvolutionEngine 自动进化

**验收标准**：
- [ ] 回测 BTC/USDT 4h，年化 > 12%，最大回撤 < 18%
- [ ] 在震荡市（MarketClassifier RANGING）中跑赢 BuyHold
- [ ] 代码覆盖率 > 90%

#### 2.1.2 成交量加权策略 — VWAP Strategy

**文件**：`src/strategy/vwap_strategy.py`
**Registry key**：`"vwap"`
**类型**：趋势/均值回归混合

**原理**：计算滚动 VWAP（成交量加权平均价格），价格在 VWAP 之上且 VWAP 斜率向上时做多，价格在 VWAP 之下且斜率向下时观望/清仓。配合成交量突增确认。

**核心参数**：

| 参数 | 类型 | 默认值 | 安全范围 | 说明 |
|------|------|--------|----------|------|
| `vwap_period` | int | 20 | 5-50 | VWAP 滚动窗口 |
| `slope_period` | int | 5 | 3-20 | VWAP 斜率计算窗口 |
| `volume_surge_ratio` | float | 1.5 | 1.0-3.0 | 成交量突增倍数阈值 |
| `min_slope` | float | 0.0 | -0.01-0.01 | 最小斜率阈值 |

**验收标准**：
- [ ] 回测 BTC/USDT 4h，年化 > 10%
- [ ] 在趋势市中与 RSI 策略表现相近
- [ ] 代码覆盖率 > 90%

#### 2.1.3 动量突破策略 — MomentumBreakout Strategy

**文件**：`src/strategy/momentum_breakout.py`
**Registry key**：`"momentum"`
**类型**：趋势

**原理**：价格突破 N 日高点 + 成交量 > M 倍均量 + ADX > 阈值 时买入。三重过滤减少假突破。价格跌破 trailing stop 时卖出。

**核心参数**：

| 参数 | 类型 | 默认值 | 安全范围 | 说明 |
|------|------|--------|----------|------|
| `breakout_period` | int | 20 | 5-50 | 突破回看周期 |
| `volume_multiplier` | float | 2.0 | 1.0-5.0 | 成交量突增倍数 |
| `adx_threshold` | float | 25.0 | 15-40 | ADX 趋势强度阈值 |
| `trailing_stop_atr` | float | 2.0 | 1.0-4.0 | 移动止损 ATR 倍数 |

**与 Donchian 的区别**：Donchian 只看价格突破，Momentum 增加了成交量和 ADX 两重确认，假突破率更低。

**验收标准**：
- [ ] 回测 BTC/USDT 4h，年化 > 15%，假突破率 < 40%
- [ ] 在强趋势市中跑赢 Donchian
- [ ] 代码覆盖率 > 90%

### 2.2 多时间框架过滤器（MTF Filter）

**文件**：`src/strategy/mtf_filter.py`

**设计**：装饰器模式，套在任何现有策略上，增加高时间框架的趋势确认。

```python
class MTFWrapper(Strategy):
    """多时间框架过滤器包装器。

    包装任意策略，在低时间框架（如 4h）出信号时，
    检查高时间框架（如 1d）的趋势方向是否一致。
    不一致时抑制信号。
    """
    def __init__(
        self,
        inner: Strategy,
        high_tf_data: pd.DataFrame,  # 高时间框架数据
        trend_ema_period: int = 50,  # 高 TF 趋势判断 EMA 周期
        require_alignment: bool = True,  # 是否要求方向一致
    ):
        ...

    def on_bar(self, data, current_time):
        # 1. 调用 inner.on_bar() 获取低 TF 信号
        signal = self.inner.on_bar(data, current_time)
        # 2. 获取当前高 TF 趋势方向
        high_tf_trend = self._get_high_tf_trend(current_time)
        # 3. 如果方向不一致，抑制信号
        if self._should_filter(signal, high_tf_trend):
            return None
        return signal
```

**集成方式**：
- `MultiStrategyRunner` 的 `StrategyConfig` 增加 `high_tf_data` 字段
- `BacktestEngine` 不需要改动，MTFWrapper 对外仍是 Strategy

**验收标准**：
- [ ] RSI + MTF 回测，胜率提升 > 5%
- [ ] 交易笔数减少 < 30%（过滤不应过度）
- [ ] 代码覆盖率 > 90%

### 2.3 波动率自适应参数切换

**文件**：`src/strategy/adaptive_params.py`

**设计**：利用 `MarketClassifier` 的输出，动态调整策略参数。

```python
class AdaptiveParamManager:
    """根据市场状态自动调整策略参数。

    维护一组「状态→参数映射」表，当 MarketClassifier 检测到
    市场状态变化时，自动更新策略参数。
    """

    # 示例：RSI 策略在不同市场状态下的参数
    PARAM_PRESETS = {
        "rsi": {
            MarketState.TRENDING_UP: {
                "oversold": 40, "overbought": 80,  # 趋势中放宽阈值
            },
            MarketState.RANGING: {
                "oversold": 30, "overbought": 70,  # 震荡中用标准值
            },
            MarketState.VOLATILE: {
                "oversold": 25, "overbought": 75,  # 高波动中收紧
            },
            MarketState.TRENDING_DOWN: {
                "oversold": 20, "overbought": 60,  # 下跌趋势中更保守
            },
        },
        # 其他策略类似...
    }

    def update_if_needed(self, strategy, market_state: MarketState):
        """如果市场状态变化，更新策略参数。"""
        ...
```

**与 EvolutionEngine 的关系**：
- EvolutionEngine 做的是"长期参数优化"（Walk-Forward）
- AdaptiveParamManager 做的是"短期参数切换"（实时市场状态）
- 两者互补：EvolutionEngine 找到基线参数，AdaptiveParamManager 在基线附近微调

**验收标准**：
- [ ] RSI 策略 + 自适应回测，年化提升 > 8%（对比静态参数）
- [ ] 参数切换频率 < 每周 3 次（避免过度切换）
- [ ] 代码覆盖率 > 85%

### 2.4 成交量增强

**文件**：修改 `src/strategy/donchian_channel.py`、`src/strategy/rsi_momentum.py`

**改动**：

1. **Donchian 突破 + 成交量确认**：突破时成交量 > N 倍均量才确认信号
2. **RSI 成交量背离检测**：价格创新低但 RSI 未创新低，且成交量放大 → 看涨背离

```python
# Donchian 增强示例
def on_bar(self, data, current_time):
    ...
    # 原逻辑：价格突破 N 日高点
    if close > upper_channel:
        # 新增：成交量确认
        vol_ma = data['volume'].rolling(20).mean().iloc[-1]
        if volume > vol_ma * self.volume_multiplier:
            return 'BUY'
    ...
```

**参数新增**：

| 策略 | 新参数 | 默认值 | 说明 |
|------|--------|--------|------|
| Donchian | `volume_multiplier` | 1.5 | 成交量突增倍数 |
| RSI | `enable_volume_divergence` | True | 启用成交量背离检测 |

**验收标准**：
- [ ] Donchian + 成交量确认回测，假突破率下降 > 15%
- [ ] 现有测试全部通过

### 2.5 策略组合管理器

**文件**：`src/strategy/portfolio_manager.py`

**设计**：在 MultiStrategyRunner 之上增加一层，负责策略间的资金分配和风险协调。

```python
class PortfolioManager:
    """策略组合管理器。

    职责：
    1. 根据市场状态动态分配资金给各策略
    2. 监控策略间相关性，避免同向重仓
    3. 组合级风险控制（总仓位、总回撤）
    """

    def __init__(
        self,
        strategies: Dict[str, Strategy],
        total_capital: float,
        max_correlation: float = 0.7,  # 策略间最大允许相关性
    ):
        ...

    def allocate_capital(self, market_state: MarketState) -> Dict[str, float]:
        """根据市场状态分配资金比例。

        - TRENDING_UP: 趋势策略 70%, 震荡策略 20%, 基准 10%
        - RANGING: 震荡策略 60%, 趋势策略 30%, 基准 10%
        - VOLATILE: 各策略均分，但总仓位降低 50%
        - TRENDING_DOWN: 仅持有基准 + 轻仓趋势
        """
        ...

    def check_correlation(self, strategy_a, strategy_b, lookback=20):
        """检查两个策略最近 N 笔交易的相关性。"""
        ...
```

**与 MultiStrategyRunner 的关系**：
- MultiStrategyRunner 负责"执行"：按 bar 顺序处理各策略
- PortfolioManager 负责"决策"：决定资金怎么分配、哪些策略启用
- PortfolioManager 的输出是 MultiStrategyRunner 的输入

**验收标准**：
- [ ] 组合回测（3 策略），夏普比率 > 任一单策略
- [ ] 组合最大回撤 < 最差单策略的 80%

---

## 三、实施计划

### Phase A1：新策略开发（2 周）

| 任务 | 预计工时 | 依赖 |
|------|---------|------|
| BB 均值回归策略 | 3 天 | 无 |
| VWAP 策略 | 3 天 | 无 |
| 动量突破策略 | 4 天 | 需要 ADX 计算（已有） |
| 策略测试 | 2 天 | 策略完成 |
| 注册到 registry | 0.5 天 | 测试通过 |

### Phase A2：策略增强（1.5 周）

| 任务 | 预计工时 | 依赖 |
|------|---------|------|
| MTF 过滤器 | 3 天 | 无 |
| Donchian 成交量增强 | 1 天 | 无 |
| RSI 成交量背离 | 2 天 | 无 |
| 自适应参数管理器 | 3 天 | MarketClassifier |
| 集成测试 | 1.5 天 | 全部完成 |

### Phase A3：组合管理（1.5 周）

| 任务 | 预计工时 | 依赖 |
|------|---------|------|
| PortfolioManager 核心 | 3 天 | MultiStrategyRunner |
| 资金分配算法 | 2 天 | PortfolioManager |
| 相关性监控 | 2 天 | PortfolioManager |
| 组合回测验证 | 2 天 | 全部完成 |
| 前端策略对比页面 | 1.5 天 | API 完成 |

**总工时**：约 5 周

---

## 四、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 新策略过拟合 | 中 | 高 | Monte Carlo 验证 + 参数稳定性测试 |
| MTF 过滤过度 | 中 | 中 | 监控交易笔数减少比例，< 30% |
| 自适应参数频繁切换 | 低 | 中 | 增加最小切换间隔（如 24h） |
| PortfolioManager 复杂度 | 中 | 中 | 先做简单版，逐步增加功能 |

---

## 五、成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| 策略数量 | 8 | 11+ |
| 均值回归策略 | 1 (Grid) | 2 (Grid + BB) |
| 趋势策略胜率 | ~55% | > 60%（MTF 过滤后） |
| 组合夏普比率 | 单策略最高 ~1.5 | 组合 > 1.8 |
| 策略适应性 | 静态参数 | 自动适应 4 种市场状态 |

---

## 六、依赖关系图

```
BB 策略 ──┐
VWAP 策略 ─┤
动量突破 ──┼──→ Registry 注册 ──→ PortfolioManager ──→ 前端对比页面
           │
MTF 过滤器 ─┤
成交量增强 ─┤
           │
自适应参数 ──┴──→ MarketClassifier（已有）
```

---

*方案 A 结束*
