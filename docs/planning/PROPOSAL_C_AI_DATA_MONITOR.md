# 方案 C：AI/数据/监控智能化方案

**文档版本**：v1.0
**创建日期**：2026-06-25
**状态**：草案
**目标**：从"规则分析"进化到"智能决策辅助"，从"OHLCV"进化到"多维数据融合"，从"被动查看"进化到"主动推送"

---

## 一、背景与问题

### 1.1 现状

**AI/Agent 层**：
- `TradingAnalyzer`：5 种分析类型（回测解释、失败归因、风险检查、参数敏感性、每周复盘），纯规则，无 LLM
- `EvolutionEngine`：Walk-Forward 搜索 → 安全校验 → LLM 解读 → 自动应用
- `LLMClient`：支持 OpenAI/本地 LLM，用于进化引擎的解读
- `AuditLog`：审计日志

**数据层**：
- 仅 OHLCV 数据（Binance，ccxt）
- `QualityChecker`：7 项数据质量检查
- `MarketClassifier`：基于 ADX/ATR/EMA 的 4 种市场状态分类

**监控层**：
- `MetricsCollector`：Prometheus 指标采集
- `AlertManager`：告警管理（硬编码规则）
- Grafana 仪表盘：系统监控
- Next.js 前端：业务监控

### 1.2 核心问题

1. **数据维度单一**：只有价格和成交量，缺乏情绪、链上、衍生品数据
2. **Agent 分析无 LLM**：TradingAnalyzer 是纯规则，没有利用 LLM 的推理能力
3. **无 Monte Carlo 验证**：回测结果只有点估计，没有置信区间
4. **进化引擎无过拟合检测**：Walk-Forward 只看 Sharpe 提升，没有参数稳定性分析
5. **告警被动**：只有 Grafana 告警，没有 Telegram/Discord 推送
6. **无交易日志**：每笔交易只有数字记录，没有自然语言解释

---

## 二、升级方案

### 2.1 多维数据融合

#### 2.1.1 链上数据集成

**文件**：新建 `src/data/onchain.py`

**数据源**：CryptoQuant API（免费 tier 可用）

**关键指标**：

| 指标 | 含义 | 信号 |
|------|------|------|
| 交易所净流入 | 大量 BTC 流入交易所 | 卖压增加，利空 |
| 交易所净流出 | 大量 BTC 流出交易所 | 卖压减少，利好 |
| 巨鲸地址数 | 持有 > 1000 BTC 的地址数 | 增加 = 看多 |
| 矿工持仓变化 | 矿工卖出/持有 | 卖出 = 短期利空 |

```python
class OnChainDataSource:
    """链上数据源。

    使用 CryptoQuant API 获取交易所流入/流出、巨鲸数据。
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.cryptoquant.com/v1"

    def get_exchange_netflow(
        self,
        symbol: str = "BTC",
        days: int = 30,
    ) -> pd.DataFrame:
        """获取交易所净流入数据。"""
        ...

    def get_whale_addresses(
        self,
        symbol: str = "BTC",
        days: int = 30,
    ) -> pd.DataFrame:
        """获取巨鲸地址数据。"""
        ...
```

**集成方式**：
- `MarketClassifier` 增加链上数据输入
- 链上信号作为策略的额外过滤器

**验收标准**：
- [ ] 链上数据每日自动更新
- [ ] 数据延迟 < 1 小时

#### 2.1.2 恐惧贪婪指数

**文件**：新建 `src/data/sentiment.py`

**数据源**：Alternative.me API（免费）

```python
class FearGreedIndex:
    """恐惧贪婪指数数据源。

    反向指标：极度恐惧时逐步建仓，极度贪婪时逐步减仓。
    """

    API_URL = "https://api.alternative.me/fng/"

    def get_current(self) -> Dict[str, Any]:
        """获取当前恐惧贪婪指数。"""
        ...

    def get_historical(self, days: int = 30) -> pd.DataFrame:
        """获取历史恐惧贪婪指数。"""
        ...

    def get_signal(self) -> str:
        """获取交易信号。

        返回：
            'BUY': 极度恐惧（指数 < 25）
            'SELL': 极度贪婪（指数 > 75）
            'HOLD': 中性
        """
        ...
```

**验收标准**：
- [ ] 恐惧贪婪指数每小时更新
- [ ] 信号生成逻辑有单元测试

#### 2.1.3 资金费率

**文件**：扩展 `src/data/exchange.py`

**数据源**：Binance Futures API（免费）

```python
# exchange.py 新增方法
def get_funding_rate(
    self,
    symbol: str = "BTCUSDT",
    limit: int = 100,
) -> pd.DataFrame:
    """获取永续合约资金费率。

    正费率过高 → 多头过热 → 可能回调
    负费率 → 空头过热 → 可能反弹
    """
    ...
```

**验收标准**：
- [ ] 资金费率数据每 8 小时更新（Binance 结算周期）
- [ ] 数据存储到 TimescaleDB

### 2.2 AI/Agent 增强

#### 2.2.1 Monte Carlo 模拟

**文件**：新建 `src/backtest/monte_carlo.py`

**设计**：在回测结果基础上，随机打乱交易顺序 N 次，计算收益分布的置信区间。

```python
class MonteCarloSimulator:
    """Monte Carlo 模拟器。

    回答："这个策略的最差情况有多差？"
    """

    def __init__(
        self,
        n_simulations: int = 1000,
        confidence_levels: List[float] = [0.05, 0.25, 0.50, 0.75, 0.95],
    ):
        self.n_simulations = n_simulations
        self.confidence_levels = confidence_levels

    def simulate(
        self,
        trades: List[Dict],
        initial_capital: float,
    ) -> Dict[str, Any]:
        """运行 Monte Carlo 模拟。

        参数：
            trades: 交易记录列表（包含 profit 字段）
            initial_capital: 初始资金

        返回：
            {
                "median_return": float,
                "confidence_intervals": {5%: float, 95%: float},
                "worst_case_return": float,
                "best_case_return": float,
                "probability_of_loss": float,
                "var_95": float,  # 95% VaR
                "cvar_95": float, # 95% CVaR
            }
        """
        results = []
        for _ in range(self.n_simulations):
            # 随机打乱交易顺序
            shuffled = np.random.permutation(trades)
            equity = initial_capital
            peak = initial_capital
            max_dd = 0

            for trade in shuffled:
                equity += trade['profit']
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd

            results.append({
                'final_equity': equity,
                'total_return': (equity - initial_capital) / initial_capital,
                'max_drawdown': max_dd,
            })

        # 计算统计量
        returns = [r['total_return'] for r in results]
        drawdowns = [r['max_drawdown'] for r in results]

        return {
            'median_return': np.median(returns),
            'confidence_intervals': {
                level: np.percentile(returns, level * 100)
                for level in self.confidence_levels
            },
            'worst_case_return': np.min(returns),
            'best_case_return': np.max(returns),
            'probability_of_loss': np.mean([1 for r in returns if r < 0]) / len(returns),
            'var_95': np.percentile(returns, 5),
            'cvar_95': np.mean([r for r in returns if r <= np.percentile(returns, 5)]),
            'median_max_drawdown': np.median(drawdowns),
            'worst_max_drawdown': np.max(drawdowns),
        }
```

**验收标准**：
- [ ] 模拟 1000 次 < 5 秒
- [ ] 输出包含 VaR 和 CVaR
- [ ] 代码覆盖率 > 90%

#### 2.2.2 参数稳定性评分

**文件**：新建 `src/backtest/robustness.py`

**设计**：对每个策略的参数做微扰测试，评估参数稳健性。

```python
class ParameterRobustnessAnalyzer:
    """参数稳定性分析器。

    参数变化 ±10% 时，收益变化有多大？
    变化小 = 参数稳健 = 好策略
    变化大 = 过拟合风险
    """

    def __init__(
        self,
        perturbation_pct: float = 0.10,  # 微扰幅度 10%
        n_samples: int = 20,             # 每个参数的采样点数
    ):
        self.perturbation_pct = perturbation_pct
        self.n_samples = n_samples

    def analyze(
        self,
        strategy_class,
        base_params: Dict[str, Any],
        data: pd.DataFrame,
    ) -> Dict[str, Any]:
        """分析参数稳定性。

        返回：
            {
                "stability_score": float (0-1, 1 = 最稳健),
                "param_sensitivity": {param: float},
                "worst_param": str,
                "recommendation": str,
            }
        """
        ...
```

**集成方式**：
- `EvolutionEngine` 在进化后自动运行稳定性分析
- 稳定性评分 < 0.5 时拒绝自动应用

**验收标准**：
- [ ] 分析 5 个参数 < 30 秒
- [ ] 稳定性评分与人工判断一致率 > 80%

#### 2.2.3 LLM 市场日报

**文件**：新建 `src/agent/daily_report.py`

**设计**：每天收盘后用 LLM 自动生成市场日报。

```python
class DailyReportGenerator:
    """LLM 市场日报生成器。

    每天收盘后自动生成：
    1. 今日行情摘要
    2. 各策略表现
    3. 明日关注点
    4. 风险提示
    """

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def generate(
        self,
        market_data: Dict[str, pd.DataFrame],
        strategy_performance: Dict[str, Dict],
        risk_metrics: Dict[str, float],
    ) -> Dict[str, Any]:
        """生成日报。

        返回：
            {
                "date": str,
                "market_summary": str,
                "strategy_performance": str,
                "tomorrow_focus": str,
                "risk_alerts": List[str],
                "overall_sentiment": str,
            }
        """
        prompt = self._build_prompt(
            market_data, strategy_performance, risk_metrics
        )
        response = self.llm_client.analyze(prompt)
        return self._parse_response(response)
```

**验收标准**：
- [ ] 日报每天自动生成
- [ ] 日报内容准确、有洞察力

#### 2.2.4 自然语言交易日志

**文件**：新建 `src/agent/trade_journal.py`

**设计**：每笔交易自动生成人话解释。

```python
class TradeJournal:
    """自然语言交易日志。

    每笔交易自动生成解释：
    "在 BTC 66500 处买入，因为 RSI(14)=28 处于超卖区间，
     且价格在 EMA50 上方，趋势过滤通过。"
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client

    def explain_trade(
        self,
        trade: Dict,
        strategy: Strategy,
        market_state: MarketState,
    ) -> str:
        """生成交易解释。

        如果有 LLM，使用 LLM 生成自然语言解释。
        否则使用模板生成。
        """
        if self.llm_client:
            return self._explain_with_llm(trade, strategy, market_state)
        else:
            return self._explain_with_template(trade, strategy, market_state)

    def _explain_with_template(
        self,
        trade: Dict,
        strategy: Strategy,
        market_state: MarketState,
    ) -> str:
        """模板解释（无需 LLM）。"""
        side = "买入" if trade['side'] == 'BUY' else "卖出"
        price = trade['price']
        symbol = trade['symbol']
        reason = self._get_signal_reason(trade, strategy)

        return (
            f"在 {symbol} {price:.2f} 处{side}。"
            f"策略：{strategy.name}。"
            f"信号原因：{reason}。"
            f"市场状态：{market_state.value}。"
        )
```

**集成方式**：
- `BacktestEngine` 和 `PaperTradingRunner` 在记录交易时调用 `TradeJournal.explain_trade()`
- 日志存储到数据库的 `trade_notes` 字段

**验收标准**：
- [ ] 每笔交易都有自然语言解释
- [ ] 解释准确反映策略信号逻辑

### 2.3 策略组合优化器

**文件**：新建 `src/backtest/portfolio_optimizer.py`

**设计**：给定 N 个策略的历史表现，计算最优资金分配比例。

```python
class PortfolioOptimizer:
    """策略组合优化器。

    使用均值-方差优化或风险平价计算最优资金分配。
    """

    def optimize(
        self,
        strategy_returns: Dict[str, pd.Series],
        method: str = "risk_parity",  # "mean_variance" | "risk_parity" | "equal_weight"
        risk_free_rate: float = 0.0,
    ) -> Dict[str, float]:
        """计算最优资金分配。

        参数：
            strategy_returns: 各策略的收益率序列
            method: 优化方法
            risk_free_rate: 无风险利率

        返回：
            {strategy_name: weight}
        """
        if method == "equal_weight":
            n = len(strategy_returns)
            return {name: 1.0 / n for name in strategy_returns}

        elif method == "risk_parity":
            return self._risk_parity(strategy_returns)

        elif method == "mean_variance":
            return self._mean_variance(strategy_returns, risk_free_rate)

    def _risk_parity(
        self,
        strategy_returns: Dict[str, pd.Series],
    ) -> Dict[str, float]:
        """风险平价：每个策略贡献相等的风险。"""
        # 计算各策略的波动率
        volatilities = {
            name: returns.std()
            for name, returns in strategy_returns.items()
        }

        # 权重与波动率成反比
        inv_vol = {name: 1.0 / vol for name, vol in volatilities.items()}
        total_inv_vol = sum(inv_vol.values())

        return {
            name: iv / total_inv_vol
            for name, iv in inv_vol.items()
        }

    def _mean_variance(
        self,
        strategy_returns: Dict[str, pd.Series],
        risk_free_rate: float,
    ) -> Dict[str, float]:
        """均值-方差优化（Markowitz）。"""
        # 构造协方差矩阵和期望收益向量
        ...
```

**验收标准**：
- [ ] 优化结果在 1 秒内完成
- [ ] 风险平价分配合理（高波动策略权重低）
- [ ] 代码覆盖率 > 85%

### 2.4 告警与通知

#### 2.4.1 Telegram 通知

**文件**：新建 `src/monitor/telegram_notifier.py`

```python
class TelegramNotifier:
    """Telegram 通知器。

    关键事件实时推送：
    - 新开仓/平仓
    - 熔断触发
    - 日收益达到阈值
    - 策略异常
    """

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send_trade_notification(self, trade: Dict) -> None:
        """发送交易通知。"""
        emoji = "🟢" if trade['side'] == 'BUY' else "🔴"
        message = (
            f"{emoji} {trade['side']} {trade['symbol']}\n"
            f"价格: {trade['price']:.2f}\n"
            f"数量: {trade['quantity']:.6f}\n"
            f"策略: {trade['strategy']}\n"
            f"盈亏: {trade.get('profit', 'N/A')}"
        )
        self._send_message(message)

    def send_risk_alert(self, alert: Dict) -> None:
        """发送风控告警。"""
        message = (
            f"⚠️ 风控告警\n"
            f"类型: {alert['type']}\n"
            f"详情: {alert['detail']}\n"
            f"策略: {alert.get('strategy', 'N/A')}"
        )
        self._send_message(message)

    def send_daily_summary(self, summary: Dict) -> None:
        """发送每日汇总。"""
        message = (
            f"📊 每日汇总\n"
            f"日期: {summary['date']}\n"
            f"总收益: {summary['total_pnl']:.2f}\n"
            f"交易笔数: {summary['trade_count']}\n"
            f"胜率: {summary['win_rate']:.1%}"
        )
        self._send_message(message)
```

**验收标准**：
- [ ] 交易通知延迟 < 5 秒
- [ ] 风控告警实时推送
- [ ] 每日汇总定时发送

#### 2.4.2 策略健康度评分

**文件**：新建 `src/monitor/health_score.py`

```python
class StrategyHealthScore:
    """策略健康度评分。

    综合胜率、回撤、夏普、连续亏损等指标，给每个策略一个 0-100 的分数。
    """

    def calculate(
        self,
        metrics: Dict[str, float],
        recent_trades: List[Dict],
    ) -> Dict[str, Any]:
        """计算健康度评分。

        评分维度：
        1. 胜率稳定性（30%）
        2. 回撤控制（25%）
        3. 夏普比率（20%）
        4. 连续亏损（15%）
        5. 交易频率（10%）

        返回：
            {
                "score": int (0-100),
                "grade": str ("A"/"B"/"C"/"D"/"F"),
                "breakdown": {dimension: score},
                "recommendation": str,
            }
        """
        ...
```

**验收标准**：
- [ ] 健康度评分每小时更新
- [ ] 评分与人工判断一致率 > 80%

### 2.5 回测验证增强

#### 2.5.1 样本外验证

**文件**：扩展 `src/backtest/engine.py`

```python
# BacktestEngine 新增方法
def run_train_test_split(
    self,
    data: pd.DataFrame,
    strategy: Strategy,
    train_ratio: float = 0.7,
) -> Dict[str, Any]:
    """样本外验证。

    在训练集上调参，测试集上验证。
    防止过拟合。
    """
    split_idx = int(len(data) * train_ratio)
    train_data = data.iloc[:split_idx]
    test_data = data.iloc[split_idx:]

    # 在训练集上运行
    train_result = self.run(train_data, strategy)

    # 在测试集上运行（使用训练集的参数）
    test_result = self.run(test_data, strategy)

    return {
        'train': train_result,
        'test': test_result,
        'degradation': self._calculate_degradation(train_result, test_result),
    }
```

#### 2.5.2 随机入场测试

**文件**：新建 `src/backtest/random_entry_test.py`

```python
class RandomEntryTest:
    """随机入场测试。

    保持出场逻辑不变，随机生成入场信号回测。
    如果随机入场都能赚钱，说明收益可能来自市场 beta。
    """

    def run(
        self,
        data: pd.DataFrame,
        strategy: Strategy,
        n_simulations: int = 100,
    ) -> Dict[str, Any]:
        """运行随机入场测试。"""
        ...
```

**验收标准**：
- [ ] 样本外验证结果自动计算
- [ ] 随机入场测试 100 次 < 30 秒

---

## 三、实施计划

### Phase C1：数据扩展（2 周）

| 任务 | 预计工时 | 依赖 |
|------|---------|------|
| 恐惧贪婪指数集成 | 1 天 | 无 |
| 资金费率数据 | 2 天 | Binance API |
| 链上数据集成 | 4 天 | CryptoQuant API |
| 数据存储到 TimescaleDB | 2 天 | 数据源完成 |
| 数据质量检查扩展 | 1 天 | 存储完成 |

### Phase C2：AI 增强（2.5 周）

| 任务 | 预计工时 | 依赖 |
|------|---------|------|
| Monte Carlo 模拟器 | 3 天 | 无 |
| 参数稳定性分析 | 2 天 | ParameterScanner |
| LLM 市场日报 | 3 天 | LLMClient |
| 自然语言交易日志 | 2 天 | LLMClient |
| 策略组合优化器 | 3 天 | 无 |
| 样本外验证 | 2 天 | BacktestEngine |

### Phase C3：监控告警（1.5 周）

| 任务 | 预计工时 | 依赖 |
|------|---------|------|
| Telegram 通知器 | 2 天 | 无 |
| 策略健康度评分 | 2 天 | 无 |
| 集成到 MultiStrategyRunner | 2 天 | 通知器完成 |
| 前端健康度展示 | 2 天 | API 完成 |
| 测试与文档 | 1 天 | 全部完成 |

**总工时**：约 6 周

---

## 四、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 链上数据 API 限流 | 中 | 中 | 缓存 + 降级到本地数据 |
| LLM 生成内容不准确 | 中 | 中 | 所有 LLM 输出标注"需要人工确认" |
| Monte Carlo 模拟过慢 | 低 | 低 | 并行计算 + 采样数可调 |
| Telegram 通知延迟 | 低 | 低 | 异步发送 + 重试机制 |
| 过度依赖外部数据源 | 中 | 高 | 本地缓存 + 降级策略 |

---

## 五、成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| 数据维度 | OHLCV | OHLCV + 链上 + 情绪 + 资金费率 |
| 回测可信度 | 点估计 | Monte Carlo 置信区间 |
| 参数稳健性 | 无评估 | 稳定性评分 0-1 |
| 交易解释 | 无 | 每笔交易有自然语言解释 |
| 告警方式 | Grafana | Grafana + Telegram |
| 日报生成 | 无 | LLM 自动生成 |

---

## 六、依赖关系图

```
恐惧贪婪指数 ──┐
资金费率 ────┤
链上数据 ────┼──→ 数据存储 ──→ MarketClassifier 增强
             │
Monte Carlo ──┤
参数稳定性 ──┼──→ EvolutionEngine 增强
样本外验证 ──┘
             │
LLM 日报 ────┤
交易日志 ────┼──→ LLMClient（已有）
组合优化器 ──┘
             │
Telegram ────┤
健康度评分 ──┼──→ 前端展示
```

---

*方案 C 结束*
