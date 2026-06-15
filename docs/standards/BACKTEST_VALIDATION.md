# 回测验证标准

**文档版本：** v1.0  
**创建日期：** 2026-06-13  
**状态：** ✅ 已批准

---

## 目的

本文档定义 Phase 2（回测可信闭环）的验证标准和验收要求。

**核心原则：** 早期优先验证回测引擎本身可信，而不是追求收益漂亮。

---

## 必须验证的5个核心问题

### 1. 前视偏差检查

**定义：** 策略在生成信号时，不能使用未来数据。

**常见前视偏差来源：**
- 使用未闭合K线的收盘价
- 使用当日最高价/最低价（事后才知道）
- 使用未来K线计算的指标
- 订单使用当前K线的收盘价成交（应该用下一根K线）

**检查方法：**

```python
# 1. 代码审查检查清单
LOOKHEAD_BIAS_CHECKLIST = [
    '是否使用了 iloc[-1] 或 .tail(1) 的当前K线数据？',
    '指标计算是否只用到 t-1 及之前的数据？',
    '订单价格是否基于 t+1 的开盘价或更晚？',
    '是否有 future warning 或 SettingWithCopyWarning？',
    '是否在循环中正确切片数据？'
]

# 2. 自动检测
def check_lookhead_bias(strategy_code: str) -> dict:
    """
    检测常见的前视偏差模式
    """
    warnings = []
    
    # 检测危险模式
    dangerous_patterns = [
        (r'\.iloc\[-1\]', '使用当前K线数据'),
        (r'\.tail\(1\)', '使用当前K线数据'),
        (r'df\[df\.index == current_time\]', '使用当前时间数据'),
    ]
    
    for pattern, desc in dangerous_patterns:
        if re.search(pattern, strategy_code):
            warnings.append({
                'pattern': pattern,
                'description': desc,
                'severity': 'high'
            })
    
    return {
        'has_warnings': len(warnings) > 0,
        'warnings': warnings
    }

# 3. 回测逻辑验证
def validate_backtest_logic():
    """
    验证回测引擎的事件顺序
    
    正确顺序：
    1. K线 t 闭合
    2. 使用 K线 t 和之前的数据计算指标
    3. 生成信号
    4. K线 t+1 开始
    5. 使用 K线 t+1 的开盘价（或稍后）成交
    """
    assert signal_time < order_time
    assert order_price == next_candle_open or later
```

**验收标准：**
- ✅ 代码审查通过（人工检查）
- ✅ 自动检测无高危警告
- ✅ 订单时间戳 > 信号时间戳
- ✅ **零容忍前视偏差**

---

### 2. 成本模型

**定义：** 手续费和滑点必须真实计入。

**成本参数：**
```python
COST_MODEL = {
    'commission': 0.001,  # 0.1% (Binance 现货 maker/taker 平均)
    'slippage': {
        'BTC/USDT': 0.0005,  # 0.05%
        'ETH/USDT': 0.001,   # 0.1%
    }
}
```

**计算方法：**
```python
def calculate_trade_cost(order: Order, cost_model: dict) -> float:
    """
    计算交易成本
    
    返回：总成本（手续费 + 滑点）
    """
    # 手续费
    commission = order.amount * order.price * cost_model['commission']
    
    # 滑点
    slippage_pct = cost_model['slippage'][order.symbol]
    slippage = order.amount * order.price * slippage_pct
    
    return commission + slippage

# 买入时
actual_buy_price = order.price * (1 + commission + slippage)

# 卖出时
actual_sell_price = order.price * (1 - commission - slippage)
```

**验收标准：**
- ✅ 每笔交易计入手续费
- ✅ 每笔交易计入滑点
- ✅ 成本明细可追溯
- ✅ 回测报告显示总成本
- ✅ **100% 交易计入成本**

---

### 3. 订单成交逻辑

**定义：** 订单成交价格和时间必须合理。

**成交规则：**
```python
class OrderFillLogic:
    """订单成交逻辑（简化版）"""
    
    def can_fill_market_order(self, order: Order, candle: Candle) -> bool:
        """
        市价单：下一根K线开盘价成交
        """
        return True
    
    def get_fill_price_market(self, order: Order, candle: Candle) -> float:
        """
        市价单成交价格
        """
        if order.side == 'buy':
            # 买入：开盘价 + 滑点
            return candle.open * (1 + self.slippage)
        else:
            # 卖出：开盘价 - 滑点
            return candle.open * (1 - self.slippage)
    
    def can_fill_limit_order(self, order: Order, candle: Candle) -> bool:
        """
        限价单：价格触及才成交（简化）
        """
        if order.side == 'buy':
            # 买入限价单：最低价 <= 限价
            return candle.low <= order.price
        else:
            # 卖出限价单：最高价 >= 限价
            return candle.high >= order.price
    
    def get_fill_price_limit(self, order: Order) -> float:
        """
        限价单成交价格
        """
        # 简化：假设按限价成交
        return order.price
```

**验收标准：**
- ✅ 订单不能在信号生成的当根K线成交
- ✅ 市价单在下一根K线开盘价成交
- ✅ 限价单价格触及才成交
- ✅ 成交逻辑可解释

---

### 4. 数据版本和可复现性

**定义：** 同样的数据和参数，必须产生相同的回测结果。

**必须记录：**
```python
backtest_metadata = {
    'backtest_id': 'uuid',
    'run_time': '2026-06-13T10:30:00Z',
    'data_version': 'abc123...',  # 数据集SHA256
    'strategy_name': 'grid_strategy',
    'strategy_version': 'v1.0',
    'parameters': {
        'grid_num': 10,
        'price_range': (40000, 50000),
        'grid_size': 0.02
    },
    'period': {
        'start': '2023-01-01',
        'end': '2024-12-31'
    },
    'cost_model': COST_MODEL,
    'initial_balance': 10000
}
```

**验收标准：**
- ✅ 回测报告包含数据版本（SHA256）
- ✅ 回测报告包含策略参数
- ✅ 相同输入产生相同输出（可重复）
- ✅ 随机数种子固定（如果使用）

---

### 5. 样本内/样本外划分

**定义：** 防止过拟合，必须在样本外测试。

**划分原则：**
```python
# 示例：2年数据
SAMPLE_SPLIT = {
    'train': ('2023-01-01', '2023-12-31'),  # 训练集（样本内）
    'validate': ('2024-01-01', '2024-06-30'),  # 验证集
    'test': ('2024-07-01', '2024-12-31')  # 测试集（样本外）
}

# 优化参数只能用训练集
# 验证参数用验证集
# 最终验收用测试集
```

**Walk-Forward 原则：**
```python
# 更严格的方法：滚动窗口
periods = [
    {'train': '2023-01-01 to 2023-06-30', 'test': '2023-07-01 to 2023-09-30'},
    {'train': '2023-04-01 to 2023-09-30', 'test': '2023-10-01 to 2023-12-31'},
    {'train': '2023-07-01 to 2023-12-31', 'test': '2024-01-01 to 2024-03-31'},
    # ...
]
```

**验收标准：**
- ✅ 明确划分训练集/测试集
- ✅ 测试集结果不能反转（方向改变）
- ✅ 测试集收益允许下降，但 <50%
- ✅ 参数优化只用训练集

---

## 参数敏感性测试

**定义：** 参数小幅变化，结果不应剧烈反转。

**测试方法：**
```python
def sensitivity_test(base_params: dict, vary_param: str, 
                     vary_range: float = 0.2) -> dict:
    """
    参数敏感性测试
    
    参数：
    - base_params: 基准参数
    - vary_param: 要测试的参数名
    - vary_range: 变化幅度（±20%）
    
    返回：敏感性报告
    """
    base_value = base_params[vary_param]
    results = []
    
    # 测试 -20%, -10%, 0%, +10%, +20%
    for pct in [-0.2, -0.1, 0, 0.1, 0.2]:
        test_params = base_params.copy()
        test_params[vary_param] = base_value * (1 + pct)
        
        result = run_backtest(test_params)
        results.append({
            'param_change': pct,
            'param_value': test_params[vary_param],
            'return': result['total_return'],
            'sharpe': result['sharpe_ratio']
        })
    
    # 分析
    returns = [r['return'] for r in results]
    max_change = (max(returns) - min(returns)) / abs(results[2]['return'])
    
    return {
        'param': vary_param,
        'results': results,
        'max_return_change': max_change,
        'passed': max_change < 0.5  # 参数变化±20%，收益变化<50%
    }
```

**验收标准：**
- ✅ 关键参数 ±20%，收益变化 <50%
- ⚠️ 如果变化 >50%，需要解释原因
- ❌ 如果出现方向反转（正收益→负收益），不通过

**必须测试的参数：**
- 网格数量
- 价格区间
- 仓位大小
- 趋势过滤阈值

---

## 性能指标定义

### 必须计算的指标

```python
class PerformanceMetrics:
    """性能指标"""
    
    def calculate_all(self, trades: list, equity_curve: pd.Series) -> dict:
        """
        计算所有性能指标
        """
        return {
            # 收益指标
            'total_return': self.total_return(equity_curve),
            'annual_return': self.annual_return(equity_curve),
            'monthly_returns': self.monthly_returns(equity_curve),
            
            # 风险指标
            'max_drawdown': self.max_drawdown(equity_curve),
            'max_drawdown_duration': self.max_dd_duration(equity_curve),
            'volatility': self.volatility(equity_curve),
            
            # 风险调整收益
            'sharpe_ratio': self.sharpe_ratio(equity_curve),
            'sortino_ratio': self.sortino_ratio(equity_curve),
            'calmar_ratio': self.calmar_ratio(equity_curve),
            
            # 交易统计
            'total_trades': len(trades),
            'win_rate': self.win_rate(trades),
            'avg_win': self.avg_win(trades),
            'avg_loss': self.avg_loss(trades),
            'profit_factor': self.profit_factor(trades),
            'avg_win_loss_ratio': self.avg_win / self.avg_loss,
            
            # 其他
            'max_consecutive_wins': self.max_consecutive_wins(trades),
            'max_consecutive_losses': self.max_consecutive_losses(trades),
        }
```

### 最大回撤计算

```python
def max_drawdown(equity_curve: pd.Series) -> float:
    """
    最大回撤
    
    定义：从峰值到谷值的最大跌幅
    """
    cummax = equity_curve.cummax()
    drawdown = (equity_curve - cummax) / cummax
    return drawdown.min()

# 示例
# 峰值 $12000 → 谷值 $9000
# 回撤 = (9000 - 12000) / 12000 = -0.25 = -25%
```

---

## 回测报告格式

```json
{
  "backtest_id": "uuid",
  "metadata": {
    "run_time": "2026-06-13T10:30:00Z",
    "data_version": "abc123...",
    "strategy": "grid_strategy_v1",
    "parameters": {...},
    "period": {"start": "2023-01-01", "end": "2024-12-31"},
    "initial_balance": 10000
  },
  "performance": {
    "total_return": 0.23,
    "annual_return": 0.115,
    "max_drawdown": -0.18,
    "sharpe_ratio": 1.45,
    "win_rate": 0.62,
    "profit_factor": 1.8,
    "total_trades": 150
  },
  "cost_analysis": {
    "total_commission": 85.50,
    "total_slippage": 42.75,
    "total_cost": 128.25,
    "cost_percentage": 0.0128
  },
  "validation": {
    "lookhead_bias_check": "passed",
    "cost_model_applied": true,
    "sample_out_performance": {
      "train_return": 0.28,
      "test_return": 0.15,
      "degradation": 0.46
    },
    "sensitivity_tests": [
      {"param": "grid_num", "passed": true},
      {"param": "price_range", "passed": true}
    ]
  },
  "trade_log": "path/to/trade_log.csv",
  "equity_curve": "path/to/equity_curve.csv"
}
```

---

## Phase 2 验收清单

**必须全部通过：**

### 前视偏差检查
- [ ] 代码人工审查通过
- [ ] 自动检测无高危警告
- [ ] 订单时间 > 信号时间
- [ ] 使用历史数据成交测试通过

### 成本模型
- [ ] 手续费 0.1% 计入所有交易
- [ ] 滑点计入所有交易
- [ ] 成本明细可查询
- [ ] 回测报告显示总成本

### 订单逻辑
- [ ] 市价单在下一根K线成交
- [ ] 限价单触及价格才成交
- [ ] 成交逻辑有单元测试

### 可复现性
- [ ] 数据版本记录（SHA256）
- [ ] 策略参数记录
- [ ] 相同输入产生相同输出（测试3次）

### 样本划分
- [ ] 明确训练集/测试集
- [ ] 样本外测试：收益不反转
- [ ] 样本外收益下降 <50%

### 参数敏感性
- [ ] 关键参数 ±20% 测试
- [ ] 收益变化 <50%
- [ ] 无方向反转

### 性能指标
- [ ] 所有指标正确计算
- [ ] 最大回撤计算正确
- [ ] 夏普比率计算正确

### 报告
- [ ] 回测报告自动生成
- [ ] 报告包含所有必需信息
- [ ] 交易日志完整
- [ ] 权益曲线可视化

---

## 重要说明

### 早期不看收益

**Phase 2 的目标不是追求高收益，而是验证回测引擎可信。**

收益指标只作为观察指标，不作为验收标准。

**验收重点：**
- ✅ 无前视偏差
- ✅ 成本真实
- ✅ 逻辑可解释
- ✅ 结果可复现

### 蒙特卡洛模拟（中期增强）

蒙特卡洛模拟不是早期必需：
- 可以作为 Phase 3-4 的增强
- 不应阻塞 Phase 2 验收

**简单验证优先：**
1. 前视偏差检查
2. 成本模型
3. 参数敏感性
4. 样本外测试

**复杂验证后置：**
5. 蒙特卡洛（1000次模拟）
6. Bootstrap 置信区间
7. 时间序列交叉验证

---

**文档状态：** ✅ 已批准  
**Phase：** Phase 2  
**优先级：** 最高  
**更新日期：** 2026-06-13
