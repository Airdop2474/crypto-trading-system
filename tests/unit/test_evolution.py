"""
Evolution 模块单元测试

覆盖：
- ParamGridBuilder 参数搜索空间生成
- EvolutionGuardrails 安全校验（6 道防线）
- EvolutionThresholds 默认阈值
- EvolutionResult 序列化
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from src.agent.param_grid_builder import ParamGridBuilder
from src.agent.evolution_guardrails import EvolutionGuardrails, EvolutionThresholds
from src.agent.evolution_engine import EvolutionResult


# ========================================================================
# ParamGridBuilder
# ========================================================================

class DummyStrategy:
    """模拟策略类（带 PARAM_SCHEMA）"""
    PARAM_SCHEMA = {
        "grid_count": {"type": int, "min": 5, "max": 30},
        "position_per_grid": {"type": float, "min": 0.02, "max": 0.15},
        "atr_period": {"type": int, "min": 7, "max": 21},
        "enable_filters": {"type": bool},
        "max_consecutive_losses": {"type": int, "min": 1, "max": 10},
    }


class PriceDummyStrategy:
    """含价格参数的策略类"""
    PARAM_SCHEMA = {
        "lower_price": {"type": float, "min": 10000},
        "upper_price": {"type": float, "min": 20000},
        "grid_count": {"type": int, "min": 3, "max": 30},
    }


class EmptySchemaStrategy:
    PARAM_SCHEMA = {}


class TestParamGridBuilder:

    def test_build_grid_excludes_skip_params(self):
        """SKIP_PARAMS 中的参数不应出现在 grid 中"""
        builder = ParamGridBuilder(resolution=3)
        grid = builder.build_grid(DummyStrategy)

        assert "enable_filters" not in grid
        assert "max_consecutive_losses" not in grid

    def test_build_grid_linspace_int_params(self):
        """int 类型参数生成整数序列"""
        builder = ParamGridBuilder(resolution=3)
        grid = builder.build_grid(DummyStrategy)

        assert "grid_count" in grid
        assert all(isinstance(v, int) for v in grid["grid_count"])
        assert len(grid["grid_count"]) <= 3
        assert min(grid["grid_count"]) >= 5
        assert max(grid["grid_count"]) <= 30

    def test_build_grid_linspace_float_params(self):
        """float 类型参数生成浮点序列"""
        builder = ParamGridBuilder(resolution=3)
        grid = builder.build_grid(DummyStrategy)

        assert "position_per_grid" in grid
        assert all(isinstance(v, float) for v in grid["position_per_grid"])
        assert min(grid["position_per_grid"]) >= 0.02
        assert max(grid["position_per_grid"]) <= 0.15

    def test_build_grid_bool_params_excluded(self):
        """bool 类型参数不参与搜索"""
        builder = ParamGridBuilder()
        grid = builder.build_grid(DummyStrategy)
        assert "enable_filters" not in grid

    def test_build_grid_price_params_with_data(self):
        """价格类参数使用数据分位数"""
        data = pd.DataFrame({
            "close": [100, 150, 200, 250, 310, 360, 410, 460, 510, 560] * 10,
        })
        builder = ParamGridBuilder(resolution=5)
        grid = builder.build_grid(PriceDummyStrategy, data)

        assert "lower_price" in grid
        assert "upper_price" in grid
        # lower_price 最高值不应超过 upper_price 最低值
        assert max(grid["lower_price"]) <= min(grid["upper_price"])

    def test_build_grid_price_params_no_data(self):
        """无数据时价格类参数返回空列表"""
        builder = ParamGridBuilder()
        grid = builder.build_grid(PriceDummyStrategy)

        assert "lower_price" not in grid or grid["lower_price"] == []
        assert "upper_price" not in grid or grid["upper_price"] == []

    def test_build_grid_empty_schema(self):
        """空 PARAM_SCHEMA 返回空 dict"""
        builder = ParamGridBuilder()
        grid = builder.build_grid(EmptySchemaStrategy)
        assert grid == {}

    def test_build_grid_open_range_no_max(self):
        """只有 min 没有 max 的参数：自动推导上限"""
        strategy = type("OpenRangeStrategy", (), {
            "PARAM_SCHEMA": {
                "lookback": {"type": int, "min": 5},
                "threshold": {"type": float, "min": 0.1},
            }
        })
        builder = ParamGridBuilder(resolution=3)
        grid = builder.build_grid(strategy)

        assert "lookback" in grid
        assert min(grid["lookback"]) >= 5
        assert "threshold" in grid
        assert min(grid["threshold"]) >= 0.1

    def test_cap_combinations(self):
        """组合数超限时缩减最大维度"""
        builder = ParamGridBuilder(resolution=10, max_combinations=50)
        strategy = type("BigStrategy", (), {
            "PARAM_SCHEMA": {
                "a": {"type": int, "min": 1, "max": 10},
                "b": {"type": int, "min": 1, "max": 10},
                "c": {"type": int, "min": 1, "max": 10},
            }
        })
        # 3 params × 10 each = 1000 combos > 50, should be reduced
        grid = builder.build_grid(strategy)

        total = 1
        for vals in grid.values():
            total *= len(vals)
        assert total <= builder.max_combinations


# ========================================================================
# EvolutionGuardrails
# ========================================================================

class TestEvolutionGuardrails:

    def make_wf_df(self, sharpes=None, drawdowns=None, trades=None):
        """构造 walk_forward 结果 DataFrame"""
        n = 3 if sharpes is None else len(sharpes)
        return pd.DataFrame({
            "window": list(range(n)),
            "in_sample_return": [0.1] * n,
            "out_sample_return": [0.08] * n,
            "out_sample_sharpe": sharpes or [0.8, 1.0, 1.2],
            "out_sample_max_drawdown": drawdowns or [0.05, 0.06, 0.07],
            "out_sample_trades": trades or [15, 20, 18],
        })

    def test_validate_all_pass(self):
        """全部校验通过"""
        guardrails = EvolutionGuardrails(
            EvolutionThresholds(
                min_sharpe_improvement=0.0,
                max_drawdown_limit=0.15,
                min_total_trades=10,
                min_oos_windows=2,
            )
        )
        wf_df = self.make_wf_df()

        passed, reasons = guardrails.validate(
            strategy_class=DummyStrategy,
            new_params={"grid_count": 15, "position_per_grid": 0.08},
            walk_forward_df=wf_df,
            current_sharpe=0.5,
        )

        assert passed is True
        assert len(reasons) == 0

    def test_validate_rejects_when_paused(self):
        """风控非 ACTIVE 时直接拒绝"""
        guardrails = EvolutionGuardrails()
        passed, reasons = guardrails.validate(
            strategy_class=DummyStrategy,
            new_params={"grid_count": 10},
            walk_forward_df=self.make_wf_df(),
            current_sharpe=0.5,
            risk_manager_state="PAUSED",
        )

        assert passed is False
        assert any("风控" in r for r in reasons)

    def test_validate_rejects_params_out_of_range(self):
        """参数超出 PARAM_SCHEMA 范围时拒绝"""
        guardrails = EvolutionGuardrails()
        passed, reasons = guardrails.validate(
            strategy_class=DummyStrategy,
            new_params={"grid_count": 100},
            walk_forward_df=self.make_wf_df(),
            current_sharpe=0.5,
        )

        assert passed is False
        assert any("100" in r for r in reasons)

    def test_validate_rejects_low_sharpe_improvement(self):
        """Sharpe 提升不足时拒绝"""
        guardrails = EvolutionGuardrails(
            EvolutionThresholds(min_sharpe_improvement=0.50, max_drawdown_limit=0.50)
        )
        wf_df = self.make_wf_df(sharpes=[0.55, 0.60, 0.65])

        passed, reasons = guardrails.validate(
            strategy_class=DummyStrategy,
            new_params={"grid_count": 10},
            walk_forward_df=wf_df,
            current_sharpe=0.5,  # target = 0.5 * 1.5 = 0.75, avg = 0.6 < 0.75
        )

        assert passed is False
        assert any("Sharpe" in r for r in reasons)

    def test_validate_rejects_excessive_drawdown(self):
        """OOS 回撤超过上限时拒绝"""
        guardrails = EvolutionGuardrails(
            EvolutionThresholds(max_drawdown_limit=0.10)
        )
        wf_df = self.make_wf_df(drawdowns=[0.05, 0.08, 0.15])

        passed, reasons = guardrails.validate(
            strategy_class=DummyStrategy,
            new_params={"grid_count": 10},
            walk_forward_df=wf_df,
            current_sharpe=0.5,
        )

        assert passed is False
        assert any("回撤" in r for r in reasons)

    def test_validate_rejects_few_trades(self):
        """交易笔数不足时拒绝"""
        guardrails = EvolutionGuardrails(
            EvolutionThresholds(min_total_trades=20)
        )
        wf_df = self.make_wf_df(trades=[5, 8, 6])

        passed, reasons = guardrails.validate(
            strategy_class=DummyStrategy,
            new_params={"grid_count": 10},
            walk_forward_df=wf_df,
            current_sharpe=0.5,
        )

        assert passed is False
        assert any("交易" in r for r in reasons)

    def test_validate_rejects_few_passing_windows(self):
        """通过窗口数不足时拒绝"""
        guardrails = EvolutionGuardrails(
            EvolutionThresholds(min_oos_windows=3, max_drawdown_limit=0.05)
        )
        wf_df = self.make_wf_df(drawdowns=[0.04, 0.06, 0.04])

        passed, reasons = guardrails.validate(
            strategy_class=DummyStrategy,
            new_params={"grid_count": 10},
            walk_forward_df=wf_df,
            current_sharpe=0.5,
        )

        assert passed is False
        assert any("窗口" in r for r in reasons)

    def test_validate_empty_wf_df(self):
        """空 walk_forward 数据时拒绝"""
        guardrails = EvolutionGuardrails()
        passed, reasons = guardrails.validate(
            strategy_class=DummyStrategy,
            new_params={},
            walk_forward_df=pd.DataFrame(),
            current_sharpe=0.5,
        )

        assert passed is False

    def test_validate_none_wf_df(self):
        """None walk_forward 数据时拒绝"""
        guardrails = EvolutionGuardrails()
        passed, reasons = guardrails.validate(
            strategy_class=DummyStrategy,
            new_params={},
            walk_forward_df=None,
            current_sharpe=0.5,
        )

        assert passed is False


# ========================================================================
# EvolutionThresholds
# ========================================================================

class TestEvolutionThresholds:

    def test_default_values(self):
        """默认阈值在合理范围内"""
        t = EvolutionThresholds()
        assert 0 <= t.min_sharpe_improvement <= 1.0
        assert 0 < t.max_drawdown_limit <= 1.0
        assert 0 < t.max_oos_degradation <= 10.0
        assert t.min_total_trades >= 1
        assert t.min_oos_windows >= 1

    def test_custom_values(self):
        """自定义阈值生效"""
        t = EvolutionThresholds(
            min_sharpe_improvement=0.20,
            max_drawdown_limit=0.10,
            min_total_trades=5,
            min_oos_windows=1,
        )
        assert t.min_sharpe_improvement == 0.20
        assert t.max_drawdown_limit == 0.10
        assert t.min_total_trades == 5
        assert t.min_oos_windows == 1


# ========================================================================
# EvolutionResult
# ========================================================================

class TestEvolutionResult:

    def test_to_dict_serialization(self):
        """EvolutionResult 可序列化为 dict"""
        result = EvolutionResult(
            strategy_id="grid-test",
            strategy_name="Grid",
            old_params={"grid_count": 10},
            new_params={"grid_count": 15},
            old_metrics={"sharpe_ratio": 0.5},
            new_metrics={"sharpe_ratio": 0.8},
            guardrail_passed=True,
            guardrail_reasons=[],
            llm_interpretation={
                "summary": "improved",
                "confidence": 0.8,
                "recommendation": "apply",
            },
            applied=True,
            timestamp="2026-06-22T00:00:00",
            walk_forward_windows=3,
        )

        d = result.to_dict()
        assert d["strategy_id"] == "grid-test"
        assert d["guardrail_passed"] is True
        assert d["applied"] is True

    def test_llm_provider_none(self):
        """LLM 未启用时返回 'none'"""
        result = EvolutionResult(
            strategy_id="test", strategy_name="Test",
            old_params={}, new_params=None,
            old_metrics={}, new_metrics=None,
            guardrail_passed=False, guardrail_reasons=["error"],
            llm_interpretation=None, applied=False,
            timestamp="now", walk_forward_windows=0,
        )
        assert result.llm_provider == "none"
        assert result.llm_summary is None
        assert result.llm_confidence is None

    def test_llm_provider_present(self):
        """LLM 已用时正确返回 provider"""
        result = EvolutionResult(
            strategy_id="test", strategy_name="Test",
            old_params={}, new_params={},
            old_metrics={}, new_metrics={},
            guardrail_passed=True, guardrail_reasons=[],
            llm_interpretation={
                "provider": "openai",
                "summary": "good",
                "confidence": 0.9,
            },
            applied=True,
            timestamp="now", walk_forward_windows=1,
        )
        assert result.llm_provider == "openai"
        assert result.llm_summary == "good"
        assert result.llm_confidence == 0.9