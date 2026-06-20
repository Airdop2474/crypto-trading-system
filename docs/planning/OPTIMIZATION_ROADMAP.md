# 系统优化路线图 — 面向交易代码专家

**文档版本：** v1.0  
**创建日期：** 2026-06-20  
**状态：** ✅ 待执行  
**目标读者：** 交易代码专家（负责修复与优化实施）

---

## 背景

当前系统已完成 Phase 1-3（数据管线 → 回测引擎 → 网格策略），代码总量 ~4600 行，47 个测试文件，架构基线扎实。在进入 Phase 4（纸面交易验证）和后续策略扩展之前，积累了一定量的技术债和架构缺陷需要集中修复。

本文档按**优先级排序**列出所有优化项，每项包含：问题描述 → 影响 → 目标方案 → 验收标准。

---

## 🔴 P0 — 必须修复（阻塞后续扩展）

### P0-1: 策略熔断逻辑重复（代码重复 3 份）

**文件：**
- `src/strategy/simple_ma.py`
- `src/strategy/rsi_momentum.py`
- `src/strategy/grid_trading.py`

**问题：** `on_fill()` 中的连亏计数、日亏熔断、PAUSE 状态管理逻辑在三份策略中**完全相同**。新增第 4、第 5 个策略时只能复制粘贴，技术债指数增长。

**影响：**
- 任何熔断逻辑变更需同时改 3+ 处
- 容易遗漏，产生行为不一致
- 新增策略门槛高

**目标方案：**

```python
# src/strategy/risk_aware.py (新建)
class RiskAwareStrategy(Strategy):
    """
    自带熔断的策略基类。
    子类无需再实现 on_fill 的连亏/日亏/累计回撤逻辑。
    """
    def __init__(self,
                 max_consecutive_losses: int = 3,
                 max_daily_loss_pct: float = -0.02):
        super().__init__()
        self._max_consecutive_losses = max_consecutive_losses
        self._max_daily_loss_pct = max_daily_loss_pct
        self._consecutive_losses = 0
        self._day_start_balance = None
        self._paused = False
    
    def on_fill(self, trade):
        """统一熔断逻辑"""
        # 累计回撤检测（来自 RiskManager）
        if self._account.total_return < -0.15:
            self._paused = True
            raise CircuitBreaker("累计回撤超过15%")
        
        # 连亏检测
        if trade['pnl'] < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self._max_consecutive_losses:
                self._paused = True
                raise CircuitBreaker(f"连续亏损{self._max_consecutive_losses}笔")
        else:
            self._consecutive_losses = 0
        
        # 日亏熔断
        # ... (统一实现)
    
    def _is_paused(self) -> bool:
        """子类在 on_bar 开头调用"""
        return self._paused
```

**验收标准：**
- [ ] 新建 `src/strategy/risk_aware.py`
- [ ] GridTrading、RSIMomentum、SimpleMA 继承 `RiskAwareStrategy`，删除各自的 `on_fill` 熔断代码
- [ ] 新增策略时只需继承，零行熔断代码
- [ ] 全部 47 个现有测试仍然通过

---

### P0-2: 策略注册表/自动发现

**文件：**
- `scripts/run_backtest.py`（硬编码 import + dict 映射）
- 各回测/纸面交易脚本

**问题：** 新增策略后必须在多个脚本中手动添加 import 和映射，容易遗漏。

**目标方案：**

```python
# src/strategy/registry.py (新建)
from src.strategy.base import Strategy
from src.strategy.grid_trading import GridTradingStrategy
from src.strategy.rsi_momentum import RSIMomentumStrategy
from src.strategy.simple_ma import SimpleMAStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "grid": GridTradingStrategy,
    "rsi": RSIMomentumStrategy,
    "ma": SimpleMAStrategy,
    "buyhold": BuyAndHoldStrategy,
}

def get_strategy(name: str) -> type[Strategy]:
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY)}")
    return STRATEGY_REGISTRY[name]

def list_strategies() -> list[str]:
    return list(STRATEGY_REGISTRY.keys())
```

**同步修改：**
- `scripts/run_backtest.py` — 用 `--strategy grid` 替代硬编码
- `scripts/run_paper_60d.py` — 同上
- CLI 入口统一使用 `get_strategy(name)`

**验收标准：**
- [ ] `src/strategy/registry.py` 存在
- [ ] `scripts/run_backtest.py --strategy rsi` 直接运行
- [ ] `python -c "from src.strategy.registry import list_strategies; print(list_strategies())"` 输出所有策略名

---

### P0-3: 网格参数配置欠拟合验证

**文件：** `src/strategy/grid_trading.py`

**问题：** `DEV_LOG.md` 记录 10 网格回测收益 **-11.10%**，虽然可能在趋势行情中正常，但缺少对网格参数的敏感性分析——无法判断是策略本身问题还是参数问题。

**目标方案：**

新建 `scripts/grid_parameter_sweep.py`：

```python
"""
网格参数敏感性扫描
- 网格数: 5 / 10 / 15 / 20
- 区间幅度: 10% / 15% / 20%
- 每档仓位: 3% / 5% / 8% / 10%
每种组合在 BTC/USDT 过去 12 个月（分月）回测
输出 heatmap 矩阵
"""
```

**输出物：**
- 参数 × 月份收益热力图
- 最佳参数组合推荐
- 识别策略失效月份（趋势市场）

**验收标准：**
- [ ] 脚本可运行，生成参数扫描报告
- [ ] 至少 3×4×4 = 48 组组合在 12 个月数据上完成
- [ ] 确认负收益原因是参数还是市场环境

---

## 🟡 P1 — 建议修复（2 周内完成）

### P1-1: `multi_runner.py` 功能补全

**文件：** `src/execution/multi_runner.py`

**当前状态：** 骨架存在，功能不完整。

**需要补全的能力：**

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 多策略并行回测 | 高 | `Runner(mode="backtest", strategies=[...])` |
| 结果对比表 | 高 | 收益率、夏普、最大回撤、胜率 横向对比 |
| 资金池隔离 | 高 | 每个策略独立资金账户 |
| 策略相关性矩阵 | 中 | 日收益序列的相关性分析 |
| 组合优化建议 | 低 | 等权 vs 风险平价 vs 最小方差 |

**验收标准：**
- [ ] `python scripts/run_multi.py --strategies grid,rsi` 输出对比表
- [ ] 各策略资金独立，互不影响
- [ ] 输出包含相关性矩阵

---

### P1-2: 跨模块工具函数去重

**文件：**
- `src/backtest/engine.py` — 滑点/手续费计算
- `src/execution/paper_broker.py` — 滑点/手续费计算（重复）

**问题：** 两处都实现了 `_apply_slippage()` 和 `_apply_commission()`，逻辑相同但独立维护。

**目标方案：**

```python
# src/utils/trading.py (新建)
def apply_slippage(price: float, slippage_pct: float, side: str) -> float:
    """统一滑点计算"""
    direction = 1 if side.upper() == "BUY" else -1
    return price * (1 + direction * slippage_pct)

def apply_commission(capital: float, rate: float) -> float:
    """统一手续费计算"""
    return capital * (1 - rate)
```

**验收标准：**
- [ ] `src/utils/trading.py` 存在
- [ ] BacktestEngine 和 PaperBroker 都引用此文件
- [ ] 相关测试通过

---

### P1-3: 策略参数 Schema 定义

**问题：** 策略参数散落在各 `__init__` 中，无统一校验，AI 自动调参时无 Schema 可参考。

**目标方案：**

```python
# 在 GridTradingStrategy 中添加
GRID_PARAM_SCHEMA = {
    "grid_num": {"type": int, "min": 5, "max": 30, "default": 10},
    "boundary_offset": {"type": float, "min": 0.05, "max": 0.30, "default": 0.10},
    "position_per_grid": {"type": float, "min": 0.02, "max": 0.15, "default": 0.10},
    "max_consecutive_losses": {"type": int, "min": 2, "max": 10, "default": 3},
}
```

**验收标准：**
- [ ] 每个策略类都有类属性 `PARAM_SCHEMA`
- [ ] `Strategy.__init__` 增加可选参数校验 `validate_params(kwargs, schema)`
- [ ] 参数越界时抛清晰异常

---

### P1-4: 网格击穿后持仓处理

**文件：** `src/strategy/grid_trading.py`

**问题：** 当价格完全突破网格区间上限或下限后，已经持有的档位仓位没有被清理逻辑。可能造成：
- 突破上沿后所有仓位已卖出（OK），但网格不再生成新信号
- 突破下沿后持仓浮亏卡死

**目标方案：**

```python
def _check_boundary_breach(self, current_price):
    """检查价格是否完全击穿网格"""
    if current_price > self.upper_price * 1.05:
        # 突破上沿：清仓所有剩余买单，转观望
        return StrategyAction.PAUSE, "价格突破网格上沿5%，暂停交易"
    if current_price < self.lower_price * 0.95:
        # 突破下沿：评估是否需要市价止损
        return StrategyAction.LIQUIDATE, "价格突破网格下沿5%，建议清仓"
    return StrategyAction.CONTINUE, None
```

**验收标准：**
- [ ] 回测中网格击穿后不再产生新订单
- [ ] 下沿击穿后触发 `LIQUIDATE` 动作（由执行层决定是否平仓）
- [ ] 相关测试用例覆盖击穿场景

---

## 🟢 P2 — 优化增强（Phase 4 期间）

### P2-1: 集成测试补充

**当前：** 47 个单元测试，缺少端到端集成测试。

**需要补充：**
- [ ] 回测引擎 vs 纸面交易一致性测试（同一数据、同一策略，结果偏差 <1%）
- [ ] 多策略并行无状态污染测试
- [ ] 数据下载 → 质量检查 → 回测 全链路测试
- [ ] Binance testnet 连通性冒烟测试

---

### P2-2: 策略选择辅助仪表盘

**目标：** 让系统能在开盘前自动判断：当前市场适合跑网格还是趋势策略。

```python
# src/monitor/market_classifier.py (新建)
def classify_market(df: pd.DataFrame) -> str:
    """
    基于近 20 天数据分析市场状态：
    Returns: 'trending_up' | 'trending_down' | 'ranging' | 'volatile'
    """
    # EMA20 vs EMA50 斜率
    # ADX 判断趋势强度
    # 布林带宽度判断波动率
    ...
```

---

### P2-3: 性能优化

| 项 | 当前 | 目标 |
|----|------|------|
| 回测 1 年 4h 数据耗时 | 未测量 | 标记基准 |
| 数据下载缓存 | 每次都从 ccxt 拉 | 本地缓存 + 增量更新 |
| 日志级别 | 统一 | 回测 INFO、实盘 WARNING |

---

## 📋 汇总清单

| ID | 项 | 优先级 | 预估工时 | 文件 |
|----|----|--------|----------|------|
| P0-1 | RiskAwareStrategy 基类 | 🔴 P0 | 2h | `src/strategy/risk_aware.py` |
| P0-2 | 策略注册表 | 🔴 P0 | 1h | `src/strategy/registry.py` |
| P0-3 | 网格参数敏感性扫描 | 🔴 P0 | 3h | `scripts/grid_parameter_sweep.py` |
| P1-1 | multi_runner 补全 | 🟡 P1 | 4h | `src/execution/multi_runner.py` |
| P1-2 | 工具函数去重 | 🟡 P1 | 1h | `src/utils/trading.py` |
| P1-3 | 参数 Schema | 🟡 P1 | 2h | 各策略文件 |
| P1-4 | 网格击穿处理 | 🟡 P1 | 2h | `src/strategy/grid_trading.py` |
| P2-1 | 集成测试 | 🟢 P2 | 4h | `tests/integration/` |
| P2-2 | 市场分类器 | 🟢 P2 | 3h | `src/monitor/market_classifier.py` |
| P2-3 | 性能基准 | 🟢 P2 | 2h | 各模块 |

**总计预估：** ~24 工时

---

## 执行建议

1. **先 P0 后 P1** — P0 的三项直接阻塞后续所有策略扩展
2. **P0-1 和 P0-2 可以并行** — 分别由不同开发者负责
3. **P0-3 是独立脚本** — 不影响核心代码，可后台跑
4. **每完成一项立即跑全量测试** — 47 个测试必须全部通过

---

**文档状态：** ✅ 已批准  
**下一步：** 交由交易代码专家按优先级执行
