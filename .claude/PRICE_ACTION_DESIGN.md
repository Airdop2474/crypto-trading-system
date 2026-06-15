# 价格行为交易系统设计方案

## 方案对比

### 方案 1：独立策略
**优点：**
- ✅ 直接集成到现有框架
- ✅ 可以回测验证
- ✅ 实盘部署简单
- ✅ 执行速度快

**缺点：**
- ❌ 规则固定，不够灵活
- ❌ 需要手动调参
- ❌ 难以适应市场变化

### 方案 2：作为 AI Agent Skill
**优点：**
- ✅ AI 动态分析，更智能
- ✅ 可以学习和适应
- ✅ 处理复杂形态
- ✅ 结合多种信息源

**缺点：**
- ❌ 响应速度慢（API调用）
- ❌ Token 成本高
- ❌ 依赖外部服务
- ❌ 实时交易不适用

---

## ⭐ 推荐方案：混合模式

**最佳实践：策略框架 + AI 辅助**

```
┌─────────────────────────────────────────────┐
│           价格行为交易系统                    │
├─────────────────────────────────────────────┤
│                                             │
│  【基础层】Price Action Strategy            │
│   ├─ K线形态识别（本地快速）                 │
│   ├─ 支撑阻力位计算                         │
│   ├─ 趋势判断                               │
│   └─ 基础交易信号                           │
│                                             │
│           ↓ (提供数据)                      │
│                                             │
│  【AI 增强层】/price-action-analyze Skill   │
│   ├─ 深度分析形态组合                       │
│   ├─ 市场情绪判断                           │
│   ├─ 风险评估                               │
│   └─ 信号质量评分                           │
│                                             │
│           ↓ (优化决策)                      │
│                                             │
│  【执行层】Trade Execution                  │
│   └─ 结合两层信息做最终决策                 │
│                                             │
└─────────────────────────────────────────────┘
```

---

## 实施计划

### Phase 1: 基础价格行为策略（2周）

#### 1.1 K线形态识别模块
```python
# src/strategy/price_action/patterns.py

class CandlePatternDetector:
    """K线形态识别器"""
    
    def detect_pin_bar(self, df: pd.DataFrame) -> pd.Series:
        """
        Pin Bar (针形线)识别
        - 长上影线或下影线（至少是实体的2-3倍）
        - 小实体
        - 强烈的反转信号
        """
        pass
    
    def detect_engulfing(self, df: pd.DataFrame) -> pd.Series:
        """
        吞没形态识别
        - 看涨吞没：大阳线完全包住前一根阴线
        - 看跌吞没：大阴线完全包住前一根阳线
        """
        pass
    
    def detect_doji(self, df: pd.DataFrame) -> pd.Series:
        """
        十字星识别
        - 开盘价 ≈ 收盘价
        - 上下影线较长
        - 犹豫和潜在反转信号
        """
        pass
    
    def detect_hammer(self, df: pd.DataFrame) -> pd.Series:
        """锤子线识别"""
        pass
    
    def detect_shooting_star(self, df: pd.DataFrame) -> pd.Series:
        """流星线识别"""
        pass
```

#### 1.2 支撑阻力识别
```python
# src/strategy/price_action/support_resistance.py

class SupportResistanceDetector:
    """支撑阻力位识别"""
    
    def find_swing_points(self, df: pd.DataFrame, 
                         window: int = 5) -> dict:
        """
        识别波段高点和低点
        返回: {'highs': [...], 'lows': [...]}
        """
        pass
    
    def identify_levels(self, swing_points: dict, 
                       tolerance: float = 0.002) -> dict:
        """
        聚类形成支撑阻力位
        tolerance: 2% 容差认为是同一价格区域
        """
        pass
    
    def check_breakout(self, current_price: float, 
                      levels: dict) -> str:
        """
        检查突破
        返回: 'support_break', 'resistance_break', 'none'
        """
        pass
```

#### 1.3 价格行为策略
```python
# src/strategy/price_action_strategy.py

class PriceActionStrategy(BaseStrategy):
    """价格行为交易策略"""
    
    def __init__(self, symbol: str, timeframe: str, parameters: dict):
        super().__init__(symbol, timeframe, parameters)
        self.pattern_detector = CandlePatternDetector()
        self.sr_detector = SupportResistanceDetector()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算指标"""
        # 识别K线形态
        df['pin_bar'] = self.pattern_detector.detect_pin_bar(df)
        df['engulfing'] = self.pattern_detector.detect_engulfing(df)
        df['doji'] = self.pattern_detector.detect_doji(df)
        
        # 识别支撑阻力
        swing_points = self.sr_detector.find_swing_points(df)
        levels = self.sr_detector.identify_levels(swing_points)
        df['near_support'] = self._is_near_level(df['close'], levels['support'])
        df['near_resistance'] = self._is_near_level(df['close'], levels['resistance'])
        
        return df
    
    def on_bar(self, bar: pd.Series) -> Optional[Signal]:
        """生成交易信号"""
        # 看涨信号：Pin Bar + 在支撑位
        if bar['pin_bar'] == 1 and bar['near_support']:
            return Signal(
                action='buy',
                price=bar['close'],
                amount=self.calculate_position_size(bar, 'buy'),
                timestamp=bar.name,
                reason="Bullish Pin Bar at Support"
            )
        
        # 看跌信号：Pin Bar + 在阻力位
        if bar['pin_bar'] == -1 and bar['near_resistance']:
            return Signal(
                action='sell',
                price=bar['close'],
                amount=self.position,
                timestamp=bar.name,
                reason="Bearish Pin Bar at Resistance"
            )
        
        return None
```

### Phase 2: AI 分析 Skill（1周）

#### 2.1 创建 `/price-action-analyze` Skill

**功能：**
1. 接收当前市场数据和识别到的形态
2. 深度分析形态质量和市场环境
3. 评估交易信号的可靠性
4. 提供风险评估和建议

**使用场景：**
- 回测后分析为什么某些信号失败
- 实盘前评估当前信号质量
- 优化策略参数
- 生成交易报告

```python
# .claude/skills/price-action-analyze/SKILL.md

## Description

Analyzes price action patterns using AI to evaluate signal quality,
assess market context, and provide trading recommendations.

## When to Use

- After backtest to understand why signals failed/succeeded
- Before live trading to evaluate current setup
- Weekly to review price action strategy performance
- To get AI insights on complex patterns

## Instructions

### Step 1: Collect Data

```python
# 收集最近的K线和形态数据
data = {
    'symbol': 'BTC/USDT',
    'timeframe': '4h',
    'current_price': 45000,
    'recent_candles': df.tail(50),  # 最近50根K线
    'detected_patterns': {
        'pin_bar': True,
        'at_support': True,
        'trend': 'uptrend'
    },
    'support_resistance': {
        'support': [44500, 43800],
        'resistance': [46000, 47200]
    }
}
```

### Step 2: Call AI Agent

```python
from src.agent.interface import AgentInterface

agent = AgentInterface(agent_type='hermes')

prompt = f"""
分析以下价格行为交易信号：

市场：{data['symbol']} {data['timeframe']}
当前价格：${data['current_price']}

检测到的形态：
- Pin Bar: {data['detected_patterns']['pin_bar']}
- 位置：支撑位 {data['support_resistance']['support'][0]}
- 趋势：{data['detected_patterns']['trend']}

请从以下角度分析：
1. 形态质量评分（1-10）
2. 市场环境评估（适合做多/做空/观望）
3. 风险因素识别
4. 入场建议（价格、止损、止盈）
5. 信号可靠性（高/中/低）

返回 JSON 格式。
"""

analysis = agent.analyze_price_action(prompt, schema=PRICE_ACTION_SCHEMA)
```

### Step 3: Output Result

```python
print(f"📊 价格行为分析报告")
print(f"信号质量: {analysis['pattern_quality']}/10")
print(f"市场环境: {analysis['market_context']}")
print(f"建议操作: {analysis['recommendation']}")
print(f"止损位: ${analysis['stop_loss']}")
print(f"止盈位: ${analysis['take_profit']}")
```
```

#### 2.2 Agent 提示词模板

```python
# .claude/skills/price-action-analyze/prompts/analysis_template.txt

你是一个专业的价格行为交易分析师。

当前市场数据：
- 交易对: {symbol}
- 时间框架: {timeframe}
- 当前价格: {current_price}
- 趋势: {trend}

检测到的形态：
{patterns}

支撑阻力位：
- 支撑: {support_levels}
- 阻力: {resistance_levels}

最近50根K线统计：
- 平均波动: {avg_volatility}
- 成交量变化: {volume_change}

请从专业交易员角度分析：

1. **形态质量评分** (1-10)
   - Pin Bar 的影线/实体比例
   - 位置的战略意义
   - 确认信号的强度

2. **市场环境**
   - 大趋势方向
   - 波动率状态
   - 流动性情况
   - 是否适合交易

3. **风险因素**
   - 可能的假突破
   - 对手盘力量
   - 新闻事件影响
   - 止损被扫的概率

4. **交易建议**
   - 入场价格
   - 止损位置（基于ATR或关键位）
   - 止盈目标（R:R 比例）
   - 仓位大小建议

5. **信号可靠性评级**
   - 高可靠性（>70%胜率预期）
   - 中等可靠性（50-70%）
   - 低可靠性（<50%，建议观望）

请返回结构化的 JSON 格式。
```

---

## 使用流程

### 场景 1：回测开发
```python
# 1. 实现价格行为策略
/strategy-new
  → 选择 "price_action" 模板
  → 生成策略框架

# 2. 运行回测
/trading-backtest
  → 测试 BTC/USDT 过去一年
  → 生成性能报告

# 3. AI 分析失败信号
/price-action-analyze --mode=backtest-review
  → 分析为什么某些 Pin Bar 失败
  → 识别最佳入场时机特征
  → 优化参数建议
```

### 场景 2：实盘辅助
```python
# 1. 策略检测到信号
strategy.on_bar(latest_bar)
  → 检测到：Bullish Pin Bar at Support

# 2. 调用 AI 验证
/price-action-analyze --realtime
  → AI 评估信号质量: 8/10
  → 建议入场: $44,520
  → 止损: $44,100
  → 止盈: $45,800

# 3. 人工最终决策
if ai_score >= 7:
    execute_trade()
```

### 场景 3：周报分析
```python
# 每周运行
/price-action-analyze --weekly-review
  → 分析本周所有信号
  → 成功率统计
  → 改进建议
  → 市场特征总结
```

---

## 优势总结

### 混合模式的优势

✅ **速度与智能兼顾**
- 本地策略快速识别（毫秒级）
- AI 深度分析（按需调用）

✅ **成本可控**
- 基础形态识别不消耗 Token
- 只在关键决策时调用 AI

✅ **可回测验证**
- 策略可以完整回测
- AI 分析可以离线批量处理

✅ **持续优化**
- AI 可以学习历史数据
- 策略参数可以 AI 优化

✅ **风险可控**
- 策略有明确规则
- AI 作为辅助决策，人工最终确认

---

## 实施优先级

### 高优先级（2周内）
1. ✅ 实现基础价格行为策略
   - K线形态识别
   - 支撑阻力计算
   - 基础信号生成

2. ✅ 回测验证
   - 测试历史数据
   - 调整参数
   - 优化规则

### 中优先级（1个月内）
3. ✅ 创建 `/price-action-analyze` Skill
   - 设计 Agent 提示词
   - 实现分析接口
   - 测试效果

4. ✅ 集成到工作流
   - 回测后自动分析
   - 实盘前信号验证

### 低优先级（按需）
5. ⏳ 高级功能
   - 多时间框架分析
   - 形态组合识别
   - 自适应参数

---

## 推荐实施方案

**我的建议：**

**第一步（立即开始）：** 
实现基础价格行为策略，专注于：
- Pin Bar（针形线）
- 支撑阻力位
- 趋势判断

**第二步（回测验证）：**
运行回测，验证策略有效性

**第三步（AI 增强）：**
创建 `/price-action-analyze` Skill，让 Hermes 分析：
- 信号质量
- 市场环境
- 风险评估

**第四步（实盘测试）：**
模拟盘验证，人工监督

这样既有坚实的策略基础，又有 AI 的智能辅助，是最佳组合！

你觉得这个方案怎么样？需要我现在就开始实现基础策略吗？
