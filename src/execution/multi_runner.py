"""
多策略并行运行框架

核心设计：
- 多个 (strategy, symbol) 组合各自拥有独立的 PaperTradingRunner
- 所有 Runner 共享同一个 Broker（现金池共享，持仓按 symbol 隔离）
- 每根 bar 按注册顺序依次处理，信号独立生成、独立成交
- 风控是全局的：任一策略触发风控暂停所有交易

与现有架构的关系：
- PaperTradingRunner 是单策略运行器，负责"策略 → Broker"循环
- MultiStrategyRunner 是编排层，管理多个 Runner 的生命周期
- 当只有一个策略时，行为与直接使用 PaperTradingRunner 完全一致

线程安全说明：
- 当前为单线程顺序执行（bar-by-bar），不存在并发竞争
- 未来如需并行，需在 Broker 层加锁
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.execution.paper_trading_runner import (
    ExecutionConfig,
    PaperTradingRunner,
    RunnerBroker,
)
from src.strategy.base import Strategy
from src.utils.logger import logger


@dataclass(frozen=True)
class StrategyConfig:
    """单个策略的注册配置。

    属性：
        strategy_id: 策略唯一标识（用于 API 过滤、状态持久化）
        strategy: 策略实例
        symbol: 交易对（如 'BTC/USDT'）
        enabled: 是否启用（False 则跳过该策略，不注册到 runner）
        max_allocation: 该策略最大资金占比（0-1），0 表示不限
        description: 策略描述
    """

    strategy_id: str
    strategy: Strategy
    symbol: str
    enabled: bool = True
    max_allocation: float = 0.0
    description: str = ""


@dataclass
class StrategySlot:
    """单个策略在运行时的完整上下文。"""

    config: StrategyConfig
    runner: PaperTradingRunner
    # 该策略的累计已实现盈亏
    realized_pnl: float = 0.0
    # 该策略处理的 bar 数
    bars_processed: int = 0


class MultiStrategyRunner:
    """多策略并行编排器。

    核心流程（每根 bar）：
    1. 对每个已启用的 StrategySlot：
       a. 用该策略的 symbol 对应的 OHLCV 数据调用 runner.process_bar()
       b. runner 内部完成"信号生成 + Broker 成交"
    2. 风控检查（共享 RiskManager）在所有策略之间生效
    3. 返回所有策略的聚合结果

    共享 Broker 的关键：所有 runner 共用同一个 broker 实例，
    现金池共享。持仓按 symbol 隔离（broker.get_position(symbol)）。
    """

    def __init__(
        self,
        broker: RunnerBroker,
        risk_manager=None,
        metrics_collector=None,
        exec_config: Optional[ExecutionConfig] = None,
    ):
        self.broker = broker
        self.risk_manager = risk_manager
        self.metrics_collector = metrics_collector
        self.exec_config = exec_config
        # 策略槽位（按注册顺序）
        self._slots: List[StrategySlot] = []
        # strategy_id -> slot 索引（快速查找）
        self._index: Dict[str, int] = {}
        # 实时模式 pending 信号追踪（process_bar 用）
        self._pending_map: Dict[str, object] = {}

    def register(self, config: StrategyConfig) -> None:
        """注册一个策略。

        参数：
            config: 策略配置

        异常：
            ValueError: strategy_id 重复
        """
        if config.strategy_id in self._index:
            raise ValueError(f"Strategy '{config.strategy_id}' already registered")

        if not config.enabled:
            logger.info(f"MultiRunner: skip disabled strategy '{config.strategy_id}'")
            return

        runner = PaperTradingRunner(
            broker=self.broker,
            symbol=config.symbol,
            risk_manager=self.risk_manager,
            metrics_collector=self.metrics_collector,
            exec_config=self.exec_config,
        )

        slot = StrategySlot(config=config, runner=runner)
        idx = len(self._slots)
        self._slots.append(slot)
        self._index[config.strategy_id] = idx

        logger.info(
            f"MultiRunner: registered '{config.strategy_id}' "
            f"({config.strategy.name} on {config.symbol})"
        )

    def register_many(self, configs: List[StrategyConfig]) -> None:
        """批量注册多个策略。"""
        for cfg in configs:
            self.register(cfg)

    @property
    def slots(self) -> List[StrategySlot]:
        """所有已注册且启用的策略槽位。"""
        return list(self._slots)

    @property
    def strategy_ids(self) -> List[str]:
        """所有已注册策略的 ID。"""
        return [s.config.strategy_id for s in self._slots]

    def get_slot(self, strategy_id: str) -> Optional[StrategySlot]:
        """按 ID 获取策略槽位。"""
        idx = self._index.get(strategy_id)
        return self._slots[idx] if idx is not None else None

    def run(
        self,
        data_map: Dict[str, pd.DataFrame],
    ) -> Dict[str, dict]:
        """批量回放：所有策略按时间同步逐 bar 推进。

        参数：
            data_map: {symbol: DataFrame} 每个策略的 symbol 对应的 OHLCV 数据。
                      同一 symbol 的多策略共享同一份数据。

        返回：
            {strategy_id: result_dict} 每个策略的运行结果。
        """
        # 重置所有 runner 状态
        for slot in self._slots:
            slot.runner.lots = {}
            slot.runner.realized_pnl = 0.0
            slot.runner.closed_trades = []
            slot.config.strategy.reset()
            slot.realized_pnl = 0.0
            slot.bars_processed = 0

        # 找到所有 symbol 数据中最长的序列长度
        max_len = 0
        for slot in self._slots:
            df = data_map.get(slot.config.symbol)
            if df is not None:
                max_len = max(max_len, len(df))

        if max_len == 0:
            logger.warning("MultiRunner: no data for any strategy")
            return {s.config.strategy_id: s.runner._build_result([]) for s in self._slots}

        # 按时间索引同步推进
        # 策略可能用不同 symbol，但 bar 数不同；按索引对齐
        pending_map: Dict[str, object] = {s.config.strategy_id: None for s in self._slots}
        signals_logs: Dict[str, list] = {s.config.strategy_id: [] for s in self._slots}

        for bar_idx in range(max_len):
            for slot in self._slots:
                df = data_map.get(slot.config.symbol)
                if df is None or bar_idx >= len(df):
                    continue

                bar = df.iloc[bar_idx]
                historical = df.iloc[max(0, bar_idx - 500): bar_idx + 1]
                pending = pending_map[slot.config.strategy_id]

                new_pending = slot.runner.process_bar(
                    bar, historical, slot.config.strategy, pending
                )
                pending_map[slot.config.strategy_id] = new_pending

                if new_pending:
                    signals_logs[slot.config.strategy_id].append(
                        {"time": bar["timestamp"], "signal": new_pending}
                    )

                slot.bars_processed += 1

        # 构建结果
        results = {}
        for slot in self._slots:
            result = slot.runner._build_result(signals_logs[slot.config.strategy_id])
            slot.realized_pnl = slot.runner.realized_pnl
            results[slot.config.strategy_id] = result

        return results

    def process_bar(
        self,
        bar: pd.Series,
        historical: pd.DataFrame,
        current_time,
    ) -> Dict[str, object]:
        """处理单根 bar（实时模式用）。

        对每个策略，如果 symbol 匹配当前 bar 的 symbol，则调用其 runner。
        多 symbol 场景下需要外部为每个 symbol 分别调用。

        参数：
            bar: 单根 K 线数据
            historical: 截至当前 bar 的历史数据
            current_time: 当前时间

        返回：
            {strategy_id: new_pending_signal} 各策略的新 pending 信号
        """
        results = {}
        symbol = bar.get("_symbol", "")
        current_price = float(bar.get("close", 0))

        for slot in self._slots:
            if slot.config.symbol != symbol:
                continue

            # max_allocation 预算校验（0 表示不限）
            alloc = slot.config.max_allocation
            if alloc > 0 and current_price > 0:
                try:
                    broker_balance = self.broker.get_balance()
                    positions_value = sum(
                        amt * current_price
                        for amt in self.broker.positions.values()
                    )
                    total_value = broker_balance + positions_value
                    if total_value > 0:
                        slot_position = sum(
                            lot["amount"] for lot in slot.runner.lots.values()
                        )
                        slot_value = slot_position * current_price
                        if slot_value / total_value > alloc:
                            logger.warning(
                                f"Strategy '{slot.config.strategy_id}' exceeds "
                                f"max_allocation {alloc:.0%}: "
                                f"{slot_value / total_value:.1%} > {alloc:.0%}, skipping bar"
                            )
                            slot.bars_processed += 1
                            results[slot.config.strategy_id] = self._pending_map.get(
                                slot.config.strategy_id
                            )
                            continue
                except Exception as e:
                    logger.debug(f"max_allocation check failed for '{slot.config.strategy_id}': {e}")

            pending = self._pending_map.get(slot.config.strategy_id)
            try:
                new_pending = slot.runner.process_bar(
                    bar, historical, slot.config.strategy, pending,
                )
            except Exception as e:
                # P0-4: 单策略崩溃隔离——跳过该策略，继续处理其他策略
                logger.error(
                    f"Strategy '{slot.config.strategy_id}' crashed in process_bar: "
                    f"{type(e).__name__}: {e}",
                    exc_info=True,
                )
                if self.risk_manager is not None:
                    try:
                        self.risk_manager._log_event(
                            "WARNING",
                            f"strategy_crash:{slot.config.strategy_id}:"
                            f"{type(e).__name__}:{e}",
                        )
                    except Exception:
                        pass  # _log_event 内部错误不应影响其他策略
                self._pending_map[slot.config.strategy_id] = pending  # 保持旧 pending
                slot.bars_processed += 1
                results[slot.config.strategy_id] = pending
                continue

            self._pending_map[slot.config.strategy_id] = new_pending
            slot.bars_processed += 1
            results[slot.config.strategy_id] = new_pending

        return results

    def aggregate_results(self) -> dict:
        """聚合所有策略的运行时状态。

        返回：
            聚合后的账户与策略摘要。
        """
        total_realized_pnl = 0.0
        total_closed_trades = 0
        total_bars = 0
        strategy_summaries = []

        for slot in self._slots:
            total_realized_pnl += slot.runner.realized_pnl
            total_closed_trades += len(slot.runner.closed_trades)
            total_bars += slot.bars_processed

            lots_amount = sum(l["amount"] for l in slot.runner.lots.values())
            strategy_summaries.append({
                "strategy_id": slot.config.strategy_id,
                "symbol": slot.config.symbol,
                "strategy_name": slot.config.strategy.name,
                "realized_pnl": slot.runner.realized_pnl,
                "open_lots": len(slot.runner.lots),
                "open_position": lots_amount,
                "closed_trades": len(slot.runner.closed_trades),
                "bars_processed": slot.bars_processed,
            })

        return {
            "total_realized_pnl": total_realized_pnl,
            "total_closed_trades": total_closed_trades,
            "total_bars_processed": total_bars,
            "strategies_count": len(self._slots),
            "strategies": strategy_summaries,
        }

    def update_strategy_params(self, strategy_id: str, new_params: Dict) -> bool:
        """热替换运行中策略的参数。

        更新策略实例属性 + 重置指标缓存状态（_init_*_state），
        保留持仓/风控状态。下一根 bar 即生效。

        参数:
            strategy_id: 策略 ID
            new_params: 新参数 dict（仅包含需要更新的参数）

        返回:
            True 如果成功更新，False 如果策略未找到
        """
        slot = self.get_slot(strategy_id)
        if slot is None:
            logger.warning(f"update_strategy_params: '{strategy_id}' not found")
            return False

        strategy = slot.config.strategy
        old_params = dict(strategy.parameters) if hasattr(strategy, "parameters") else {}

        # 1. 更新策略实例属性
        for key, value in new_params.items():
            if hasattr(strategy, key):
                setattr(strategy, key, value)

        # 2. 更新 parameters dict
        if hasattr(strategy, "parameters"):
            strategy.parameters.update(new_params)

        # 3. 重置策略指标缓存（不影响持仓/风控）
        #    各策略命名约定：_init_grid_state, _init_rsi_state, _init_ma_state 等
        for attr_name in dir(strategy):
            if attr_name.startswith("_init_") and attr_name.endswith("_state") and callable(getattr(strategy, attr_name)):
                try:
                    getattr(strategy, attr_name)()
                    logger.debug(f"Called {attr_name}() on '{strategy_id}'")
                except Exception as e:
                    logger.warning(f"Failed to call {attr_name}() on '{strategy_id}': {e}")
                break  # 只调用第一个匹配的方法

        logger.info(
            f"Strategy '{strategy_id}' params updated: "
            f"{old_params} -> {dict(strategy.parameters)}"
        )
        return True

    # ---- 结果分析工具 ----

    @staticmethod
    def comparison_table(
        results: Dict[str, dict],
        title: str = "Strategy Comparison",
    ) -> str:
        """生成多策略对比表。

        参数：
            results: {strategy_id: result_dict}，每个 result 需包含
                     total_return, metrics(含 sharpe_ratio, max_drawdown, win_rate)

        返回：
            格式化的对比表字符串。
        """
        if not results:
            return "No results to compare."

        rows = []
        for sid, res in results.items():
            metrics = res.get("metrics", {})
            rows.append({
                "Strategy": sid,
                "Return": res.get("total_return", 0.0),
                "Sharpe": metrics.get("sharpe_ratio", 0.0),
                "MaxDD": metrics.get("max_drawdown", 0.0),
                "WinRate": metrics.get("win_rate", 0.0),
                "Trades": res.get("total_trades", 0),
            })

        df = pd.DataFrame(rows)
        df = df.sort_values("Return", ascending=False)

        lines = [f"\n{'=' * 80}",
                 f"  {title}",
                 f"{'=' * 80}",
                 f"  {'Strategy':<12} {'Return':>10} {'Sharpe':>8} {'MaxDD':>10} {'WinRate':>8} {'Trades':>7}",
                 f"  {'-' * 58}"]

        for _, row in df.iterrows():
            lines.append(
                f"  {row['Strategy']:<12} "
                f"{row['Return']:>10.2%} "
                f"{row['Sharpe']:>8.2f} "
                f"{row['MaxDD']:>10.2%} "
                f"{row['WinRate']:>8.2%} "
                f"{int(row['Trades']):>7}"
            )

        lines.append(f"  {'=' * 58}")
        return "\n".join(lines)

    @staticmethod
    def correlation_matrix(equity_curves: Dict[str, pd.Series]) -> str:
        """计算策略权益曲线之间的相关性矩阵。

        参数：
            equity_curves: {strategy_id: equity_series}，每个 series 为
                           策略在各 bar 的权益值。

        返回：
            格式化的相关性矩阵字符串。
        """
        if len(equity_curves) < 2:
            return "Need at least 2 strategies to compute correlation."

        ids = sorted(equity_curves.keys())
        df_equity = pd.DataFrame({sid: equity_curves[sid] for sid in ids})

        # 计算日收益率相关性
        returns = df_equity.pct_change().dropna()
        corr = returns.corr()

        lines = [f"\n  Strategy Correlation Matrix",
                 f"  {'-' * 40}"]
        header = "  " + "".join(f"{sid:>8}" for sid in ids)
        lines.append(header)

        for sid_i in ids:
            row_vals = "".join(f"{corr.loc[sid_i, sid_j]:>8.3f}" for sid_j in ids)
            lines.append(f"  {sid_i:<8}{row_vals}")

        return "\n".join(lines)

    @staticmethod
    def comparison_table_backtest(
        results: Dict[str, dict],
        title: str = "Strategy Comparison",
    ) -> str:
        """BacktestEngine 结果对比表（兼容 BacktestEngine.run 输出格式）。

        与 comparison_table 的区别：result 是 BacktestEngine 的直接返回，
        不含 metrics 包装层。
        """
        if not results:
            return "No results to compare."

        rows = []
        for sid, res in results.items():
            metrics = res.get("metrics", {})
            rows.append({
                "Strategy": sid,
                "Return": res.get("total_return", 0.0),
                "Sharpe": metrics.get("sharpe_ratio", 0.0),
                "MaxDD": metrics.get("max_drawdown", 0.0),
                "WinRate": metrics.get("win_rate", 0.0),
                "Trades": res.get("total_trades", 0),
            })

        df = pd.DataFrame(rows)
        df = df.sort_values("Return", ascending=False)

        lines = [f"\n{'=' * 80}",
                 f"  {title}",
                 f"{'=' * 80}",
                 f"  {'Strategy':<12} {'Return':>10} {'Sharpe':>8} {'MaxDD':>10} {'WinRate':>8} {'Trades':>7}",
                 f"  {'-' * 58}"]

        for _, row in df.iterrows():
            lines.append(
                f"  {row['Strategy']:<12} "
                f"{row['Return']:>10.2%} "
                f"{row['Sharpe']:>8.2f} "
                f"{row['MaxDD']:>10.2%} "
                f"{row['WinRate']:>8.2%} "
                f"{int(row['Trades']):>7}"
            )

        lines.append(f"  {'=' * 58}")
        return "\n".join(lines)
