"""
策略 AI 进化引擎

闭环流水线：搜索空间生成 → Walk-Forward 搜索 → 安全校验 → LLM 解读 → 自动应用。
由前端 Agent 页面手动触发，满足安全阈值时自动替换运行中策略的参数。
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import pandas as pd
from loguru import logger

from src.agent.param_grid_builder import ParamGridBuilder
from src.agent.evolution_guardrails import EvolutionGuardrails, EvolutionThresholds
from src.agent.llm_client import LLMClient
from src.backtest.param_scanner import ParameterScanner
from src.strategy.registry import STRATEGY_REGISTRY
from src.utils.config import config as _cfg


# ------------------------------------------------------------------
# 数据结构
# ------------------------------------------------------------------

@dataclass
class EvolutionResult:
    """单次进化的完整结果。"""

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

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 dict（供 API 响应 / DB 写入）。"""
        d = asdict(self)
        return d

    @property
    def llm_provider(self) -> str:
        if self.llm_interpretation:
            return self.llm_interpretation.get("provider", "local")
        return "none"

    @property
    def llm_summary(self) -> Optional[str]:
        if self.llm_interpretation:
            return self.llm_interpretation.get("summary")
        return None

    @property
    def llm_confidence(self) -> Optional[float]:
        if self.llm_interpretation:
            return self.llm_interpretation.get("confidence")
        return None


# ------------------------------------------------------------------
# 引擎
# ------------------------------------------------------------------

class EvolutionEngine:
    """策略进化编排器。"""

    def __init__(
        self,
        data: Dict[str, pd.DataFrame] | None = None,
        audit_log: Any = None,
        llm_client: LLMClient | None = None,
        thresholds: EvolutionThresholds | None = None,
        auto_apply: bool = True,
    ):
        """
        参数:
            data: 行情数据 dict，key 为 symbol（如 "BTC/USDT"）
            audit_log: AuditLog 实例（可选，用于记录审计）
            llm_client: LLMClient 实例（默认自动创建）
            thresholds: 安全阈值（默认 EvolutionThresholds()）
            auto_apply: 是否在通过安全校验后自动应用新参数
        """
        self.data = data or {}
        self.audit_log = audit_log
        self.llm_client = llm_client or LLMClient()
        self.guardrails = EvolutionGuardrails(thresholds)
        self.grid_builder = ParamGridBuilder()
        self.auto_apply = auto_apply

        # ParameterScanner 使用默认配置
        self.scanner = ParameterScanner(
            initial_capital=10000.0,
            commission=0.001,
            slippage=0.001,
        )

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def evolve_strategy(
        self,
        strategy_id: str,
        current_strategy,
        current_params: Dict[str, Any],
        multi_runner: Any = None,
        risk_manager_state: str = "ACTIVE",
    ) -> EvolutionResult:
        """对单个策略执行完整进化流程。

        参数:
            strategy_id: 策略 ID（如 "grid-btc-usdt"）
            current_strategy: 当前运行的策略实例
            current_params: 当前参数 dict
            multi_runner: MultiStrategyRunner 实例（用于热替换）
            risk_manager_state: 风控状态

        返回:
            EvolutionResult
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        strategy_name = getattr(current_strategy, "name", strategy_id)

        # 0. 获取策略类
        strategy_key = self._extract_strategy_key(strategy_id)
        strategy_class = STRATEGY_REGISTRY.get(strategy_key)
        if strategy_class is None:
            return self._make_error_result(
                strategy_id, strategy_name, current_params,
                f"策略类未找到: {strategy_key}", timestamp,
            )

        # 1. 生成搜索空间
        symbol = self._extract_symbol(strategy_id)
        market_data = self.data.get(symbol)
        param_grid = self.grid_builder.build_grid(strategy_class, market_data)

        if not param_grid:
            return self._make_error_result(
                strategy_id, strategy_name, current_params,
                "搜索空间为空（策略无可调参数或 PARAM_SCHEMA 为空）", timestamp,
            )

        logger.info(
            f"[进化] {strategy_id}: 搜索空间 {len(param_grid)} 个参数, "
            f"网格: {{{', '.join(f'{k}: {len(v)} 值' for k, v in param_grid.items())}}}"
        )

        # 2. Walk-Forward 搜索
        try:
            wf_df = self.scanner.walk_forward(
                data=market_data,
                strategy_class=strategy_class,
                param_grid=param_grid,
                n_windows=3,
                in_sample_ratio=0.7,
            )
        except Exception as e:
            logger.error(f"[进化] {strategy_id} walk_forward 失败: {type(e).__name__}: {e}")
            return self._make_error_result(
                strategy_id, strategy_name, current_params,
                f"walk_forward 执行失败: {type(e).__name__}: {e}", timestamp,
            )

        if wf_df is None or wf_df.empty:
            return self._make_error_result(
                strategy_id, strategy_name, current_params,
                "walk_forward 无结果返回", timestamp,
            )

        # 3. 提取最佳参数
        best_params, best_metrics = self._extract_best(wf_df, strategy_class)
        current_metrics = self._estimate_current_metrics(current_strategy, market_data)

        logger.info(
            f"[进化] {strategy_id}: 当前 Sharpe={current_metrics.get('sharpe_ratio', 0):.3f}, "
            f"候选 Sharpe={best_metrics.get('sharpe_ratio', 0):.3f}"
        )

        # 4. 安全校验
        passed, reasons = self.guardrails.validate(
            strategy_class=strategy_class,
            new_params=best_params,
            walk_forward_df=wf_df,
            current_sharpe=current_metrics.get("sharpe_ratio", 0),
            risk_manager_state=risk_manager_state,
        )

        # 5. LLM 解读
        wf_summary = {
            "n_windows": len(wf_df),
            "oos_sharpes": wf_df["out_sample_sharpe"].tolist(),
            "oos_drawdowns": wf_df["out_sample_max_drawdown"].tolist(),
            "oos_trades": wf_df["out_sample_trades"].tolist(),
            "best_params": best_params,
        }

        llm_result = self.llm_client.interpret_evolution(
            strategy_name=strategy_name,
            old_params=current_params,
            new_params=best_params,
            walk_forward_results=wf_summary,
            current_metrics=current_metrics,
            proposed_metrics=best_metrics,
        )
        llm_result["provider"] = self.llm_client.provider

        # 6. 自动应用
        applied = False
        if passed and self.auto_apply and multi_runner is not None:
            applied = self._apply_params(multi_runner, strategy_id, best_params)

        # 7. 审计日志
        audit_id = self._record_audit(
            strategy_id, strategy_name, current_params, best_params,
            current_metrics, best_metrics, passed, applied,
        )

        result = EvolutionResult(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            old_params=current_params,
            new_params=best_params,
            old_metrics=current_metrics,
            new_metrics=best_metrics,
            guardrail_passed=passed,
            guardrail_reasons=reasons,
            llm_interpretation=llm_result,
            applied=applied,
            timestamp=timestamp,
            walk_forward_windows=len(wf_df),
        )

        # 8. 持久化到 DB
        self._persist_to_db(result)

        logger.info(
            f"[进化] {strategy_id} 完成: passed={passed}, applied={applied}, "
            f"confidence={llm_result.get('confidence', '?')}"
        )

        return result

    def evolve_all(
        self,
        slots: list,
        skip: set[str] | None = None,
        multi_runner: Any = None,
        risk_manager_state: str = "ACTIVE",
    ) -> List[EvolutionResult]:
        """批量进化多个策略。

        参数:
            slots: StrategySlot 列表（来自 multi_runner.slots）
            skip: 跳过的策略 key（如 {"buyhold"}）
            multi_runner: MultiStrategyRunner 实例
            risk_manager_state: 风控状态

        返回:
            EvolutionResult 列表
        """
        skip = skip or {"buyhold"}
        results: List[EvolutionResult] = []

        for slot in slots:
            strategy_id = slot.config.strategy_id
            strategy_key = self._extract_strategy_key(strategy_id)

            if strategy_key in skip:
                logger.info(f"[进化] 跳过 {strategy_id} (策略类型: {strategy_key})")
                continue

            strategy = slot.config.strategy
            current_params = dict(strategy.parameters) if hasattr(strategy, "parameters") else {}

            try:
                result = self.evolve_strategy(
                    strategy_id=strategy_id,
                    current_strategy=strategy,
                    current_params=current_params,
                    multi_runner=multi_runner,
                    risk_manager_state=risk_manager_state,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"[进化] {strategy_id} 异常: {type(e).__name__}: {e}")
                results.append(self._make_error_result(
                    strategy_id,
                    getattr(strategy, "name", strategy_id),
                    current_params,
                    f"进化异常: {type(e).__name__}: {e}",
                    datetime.now(timezone.utc).isoformat(),
                ))

        return results

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _extract_strategy_key(self, strategy_id: str) -> str:
        """从 strategy_id 提取策略类型 key。

        "grid-btc-usdt" → "grid"
        "rsi-eth-usdt" → "rsi"
        """
        # 取第一段作为 key
        return strategy_id.split("-")[0]

    def _extract_symbol(self, strategy_id: str) -> str:
        """从 strategy_id 提取交易对。

        "grid-btc-usdt" → "BTC/USDT"
        """
        parts = strategy_id.split("-")
        if len(parts) >= 3:
            return f"{parts[1].upper()}/{parts[2].upper()}"
        return "BTC/USDT"

    def _extract_best(
        self, wf_df: pd.DataFrame, strategy_class
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """从 walk_forward 结果中提取最佳参数和对应指标。"""
        # 按 OOS Sharpe 排名，取最佳窗口
        best_idx = wf_df["out_sample_sharpe"].idxmax()
        best_row = wf_df.loc[best_idx]

        # 提取参数列（排除 walk_forward 的固定输出列）
        fixed_cols = {
            "window", "in_sample_return", "out_sample_return",
            "out_sample_sharpe", "out_sample_max_drawdown", "out_sample_trades",
        }
        param_cols = [c for c in wf_df.columns if c not in fixed_cols]
        best_params = {col: best_row[col] for col in param_cols}

        best_metrics = {
            "sharpe_ratio": float(best_row["out_sample_sharpe"]),
            "max_drawdown": float(best_row["out_sample_max_drawdown"]),
            "total_return": float(best_row["out_sample_return"]),
            "total_trades": int(best_row["out_sample_trades"]),
        }

        return best_params, best_metrics

    def _estimate_current_metrics(
        self, strategy, data: pd.DataFrame | None
    ) -> Dict[str, Any]:
        """用当前参数跑一次回测估算当前指标。"""
        if data is None or data.empty:
            return {"sharpe_ratio": 0, "max_drawdown": 0, "total_return": 0, "total_trades": 0}

        from src.backtest.engine import BacktestEngine

        try:
            params = dict(strategy.parameters) if hasattr(strategy, "parameters") else {}
            # 需要补全 __init__ 必需的非 PARAM_SCHEMA 参数
            strategy_class = type(strategy)
            init_params = self._build_init_params(strategy_class, params)
            fresh_strategy = strategy_class(**init_params)

            engine = BacktestEngine(
                initial_capital=10000.0,
                commission=0.001,
                slippage=0.001,
            )
            result = engine.run(data=data, strategy=fresh_strategy)

            if result.get("success"):
                metrics = result.get("metrics", {})
                return {
                    "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                    "max_drawdown": metrics.get("max_drawdown", 0),
                    "total_return": result.get("total_return", 0),
                    "total_trades": result.get("total_trades", 0),
                }
        except Exception as e:
            logger.warning(f"当前指标估算失败: {type(e).__name__}: {e}")

        return {"sharpe_ratio": 0, "max_drawdown": 0, "total_return": 0, "total_trades": 0}

    def _build_init_params(self, strategy_class, params: Dict[str, Any]) -> Dict[str, Any]:
        """构建策略 __init__ 所需的完整参数。

        PARAM_SCHEMA 中的参数 + 风控默认值。
        """
        init_params = dict(params)

        # 补全风控默认值（PARAM_SCHEMA 中不含这些）
        if "max_consecutive_losses" not in init_params:
            init_params["max_consecutive_losses"] = 3
        if "max_daily_loss" not in init_params:
            init_params["max_daily_loss"] = 0.02
        if "initial_capital" not in init_params:
            init_params["initial_capital"] = 10000.0

        return init_params

    def _apply_params(self, multi_runner, strategy_id: str, new_params: Dict[str, Any]) -> bool:
        """通过 multi_runner 热替换策略参数。"""
        try:
            if hasattr(multi_runner, "update_strategy_params"):
                return multi_runner.update_strategy_params(strategy_id, new_params)
            else:
                logger.warning(
                    f"multi_runner 尚未实现 update_strategy_params()，跳过自动应用"
                )
                return False
        except Exception as e:
            logger.error(f"参数热替换失败: {type(e).__name__}: {e}")
            return False

    def _record_audit(
        self,
        strategy_id: str,
        strategy_name: str,
        old_params: Dict,
        new_params: Dict,
        old_metrics: Dict,
        new_metrics: Dict,
        passed: bool,
        applied: bool,
    ) -> Optional[str]:
        """写入审计日志。"""
        if self.audit_log is None:
            return None

        try:
            audit_id = self.audit_log.record(
                phase="evolution",
                task=f"evolve_{strategy_id}",
                input_summary={
                    "strategy_id": strategy_id,
                    "old_params": old_params,
                    "new_params": new_params,
                },
                output_summary={
                    "old_sharpe": old_metrics.get("sharpe_ratio", 0),
                    "new_sharpe": new_metrics.get("sharpe_ratio", 0),
                    "guardrail_passed": passed,
                    "applied": applied,
                },
                model=self.llm_client.provider,
                tokens_used=0,
                human_approved=applied,
                action_taken="auto_applied" if applied else ("rejected" if not passed else "manual_pending"),
            )
            return audit_id
        except Exception as e:
            logger.warning(f"审计日志写入失败: {type(e).__name__}: {e}")
            return None

    def _persist_to_db(self, result: EvolutionResult) -> None:
        """将进化结果持久化到 strategy_evolutions 表。"""
        try:
            from src.utils.database import db
            if not db.is_postgres_available():
                return

            from src.repositories.evolution_repo import EvolutionRepository
            repo = EvolutionRepository()

            with db.get_session() as session:
                repo.create(session, {
                    "strategy_id": result.strategy_id,
                    "strategy_name": result.strategy_name,
                    "old_params": result.old_params,
                    "new_params": result.new_params,
                    "old_metrics": result.old_metrics,
                    "new_metrics": result.new_metrics,
                    "guardrail_passed": result.guardrail_passed,
                    "guardrail_reasons": result.guardrail_reasons,
                    "llm_provider": result.llm_provider,
                    "llm_summary": result.llm_summary,
                    "llm_confidence": result.llm_confidence,
                    "applied": result.applied,
                    "walk_forward_windows": result.walk_forward_windows,
                })
        except Exception as e:
            # DB 写入失败不影响主流程
            logger.warning(f"进化结果 DB 持久化失败 (非致命): {type(e).__name__}: {e}")

    def _make_error_result(
        self,
        strategy_id: str,
        strategy_name: str,
        current_params: Dict,
        reason: str,
        timestamp: str,
    ) -> EvolutionResult:
        """构建错误/跳过场景的 EvolutionResult。"""
        return EvolutionResult(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            old_params=current_params,
            new_params=None,
            old_metrics={},
            new_metrics=None,
            guardrail_passed=False,
            guardrail_reasons=[reason],
            llm_interpretation=None,
            applied=False,
            timestamp=timestamp,
            walk_forward_windows=0,
        )
