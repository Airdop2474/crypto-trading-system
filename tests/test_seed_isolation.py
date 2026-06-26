"""
Regression tests for the random_seed=42 hardcoded-seed bug.

These tests guard against the bug class where Monte Carlo simulation was
seeded with a fixed value (random_seed=42), causing:
1. Identical Monte Carlo results across multiple runs of the same strategy
2. Identical Monte Carlo results across different strategies (cross-contamination)

The original bug lived at src/backtest/strategy_evaluator.py:200 where
MonteCarloSimulator(n_simulations=1000, random_seed=42) was hardcoded.
The fix removed the seed argument so each run/strategy gets independent
randomness drawn from OS entropy.

A related residual issue was the default seed=42 in
scripts/generate_oscillating_data.py:generate_oscillating_ohlcv, which is
also fixed (seed defaults to None now).
"""

import numpy as np
import pandas as pd
import pytest

from src.backtest.monte_carlo import MonteCarloSimulator
from src.backtest.strategy_evaluator import StrategyEvaluator
from src.strategy.registry import STRATEGY_REGISTRY


def _make_trades(profits: list) -> list:
    """Construct trade records matching the pattern in tests/test_monte_carlo.py.

    MonteCarloSimulator._trade_bootstrap requires each trade to carry a
    ``type`` field in {"SELL", "LIQUIDATE"} and a numeric ``profit`` field.
    """
    return [{"type": "SELL", "profit": p} for p in profits]


def _make_oscillating_ohlcv(bars: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate oscillating OHLCV data (sine wave + noise) that produces trades
    for trend-following strategies like MarketStructure and SuperTrend.

    Mirrors the logic of scripts/generate_oscillating_data.generate_oscillating_ohlcv
    but constructed inline to avoid import-path dependencies on the scripts package.

    A fixed seed is used so the data reliably triggers strategy signals across
    test runs. The non-determinism under test lives in the Monte Carlo simulator
    (no random_seed), not in the data generation.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=bars, freq="4h")
    center = 50000.0
    amplitude_pct = 0.10
    num_cycles = 8.0
    noise_pct = 0.01

    t = np.linspace(0, num_cycles * 2 * np.pi, bars)
    base = center * (1 + amplitude_pct * np.sin(t))
    noise = rng.normal(0, center * noise_pct, bars)
    closes = base + noise

    opens = np.empty(bars)
    opens[0] = closes[0]
    opens[1:] = closes[:-1]

    wick = np.abs(rng.normal(0, center * noise_pct * 0.5, bars))
    highs = np.maximum(opens, closes) + wick
    lows = np.minimum(opens, closes) - wick
    volumes = rng.uniform(100, 1000, bars)

    return pd.DataFrame({
        "timestamp": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


@pytest.fixture(scope="module")
def oscillating_ohlcv():
    """500-bar oscillating OHLCV data shared across tests in this module.

    The sine-wave oscillation triggers MarketStructure and SuperTrend signals,
    so these strategies produce ~34 trades each — enough for Monte Carlo to
    yield non-empty percentiles. A fixed seed guarantees the data always
    produces trades; the MC non-determinism comes from the unseeded simulator.
    """
    return _make_oscillating_ohlcv(bars=500, seed=42)


class TestSeedIsolation:
    """Regression tests for the random_seed=42 hardcoded-seed bug."""

    def test_monte_carlo_simulator_nondeterministic_without_seed(self):
        """MonteCarloSimulator without a random_seed produces different results
        across two instances run on the same trades.

        The bug previously forced ``random_seed=42`` so every run produced
        bit-identical percentiles. With the fix (no seed), OS entropy feeds
        the RNG and at least one of the key percentiles must differ.
        """
        # 50 mixed win/loss trades — enough that bootstrap percentiles vary
        # across independent RNG streams.
        profits = [100, -50, 200, -30, 150, -80, 50, -20, 300, -100,
                   80, -40, 120, -60, 90, -30, 200, -80, 150, -50,
                   110, -55, 220, -35, 160, -85, 60, -25, 310, -110,
                   85, -45, 125, -65, 95, -35, 205, -85, 155, -55,
                   115, -60, 225, -40, 165, -90, 65, -30, 315, -115]
        trades = _make_trades(profits)

        mc1 = MonteCarloSimulator(n_simulations=1000)
        result1 = mc1.run(
            trades=trades, initial_capital=10000, method="trade_bootstrap"
        )

        mc2 = MonteCarloSimulator(n_simulations=1000)
        result2 = mc2.run(
            trades=trades, initial_capital=10000, method="trade_bootstrap"
        )

        # At least one MC metric must differ — the bug made them exactly equal.
        assert (
            result1.return_p5 != result2.return_p5
            or result1.max_dd_p95 != result2.max_dd_p95
            or result1.ruin_probability != result2.ruin_probability
        ), (
            "Monte Carlo results are identical across unseeded runs — "
            "fixed-seed regression detected. "
            f"run1: p5={result1.return_p5}, dd95={result1.max_dd_p95}, "
            f"ruin={result1.ruin_probability}; "
            f"run2: p5={result2.return_p5}, dd95={result2.max_dd_p95}, "
            f"ruin={result2.ruin_probability}"
        )

    def test_strategy_evaluator_nondeterministic_across_runs(self, oscillating_ohlcv):
        """StrategyEvaluator produces different Monte Carlo metrics across two
        evaluate_single() calls on the same strategy.

        This is the key regression for the original bug at
        strategy_evaluator.py:200 where the MonteCarloSimulator was seeded
        with 42, making every run of every strategy deterministic.
        """
        evaluator = StrategyEvaluator(
            data=oscillating_ohlcv, initial_capital=10000, n_mc_simulations=1000
        )

        # "structure" (MarketStructureStrategy) produces ~34 trades on the
        # oscillating sine-wave data, giving Monte Carlo enough SELL trades
        # to compute meaningful percentiles.
        strategy_name = "structure"
        assert strategy_name in STRATEGY_REGISTRY, (
            f"{strategy_name} not in STRATEGY_REGISTRY: "
            f"{list(STRATEGY_REGISTRY)}"
        )

        result1 = evaluator.evaluate_single(strategy_name)
        result2 = evaluator.evaluate_single(strategy_name)

        # Guard against false positives from zero-trade empty MC results.
        assert result1.total_trades > 0, (
            f"Strategy '{strategy_name}' produced 0 trades on oscillating data; "
            "test cannot validate MC non-determinism without trades."
        )

        # At least one MC metric must differ across the two runs.
        assert (
            result1.mc_return_p5 != result2.mc_return_p5
            or result1.mc_max_dd_p95 != result2.mc_max_dd_p95
            or result1.mc_ruin_prob != result2.mc_ruin_prob
        ), (
            "StrategyEvaluator MC results identical across runs — "
            "random_seed=42 regression detected. "
            f"run1: p5={result1.mc_return_p5}, dd95={result1.mc_max_dd_p95}, "
            f"ruin={result1.mc_ruin_prob}; "
            f"run2: p5={result2.mc_return_p5}, dd95={result2.mc_max_dd_p95}, "
            f"ruin={result2.mc_ruin_prob}"
        )

    def test_different_strategies_get_different_mc_results(self, oscillating_ohlcv):
        """Two different strategies evaluated with the same StrategyEvaluator
        instance produce different Monte Carlo metrics.

        The original shared seed=42 made all 12 strategies emit identical MC
        percentiles. With independent RNG streams per evaluate_single() call,
        distinct strategies must not collide on all three metrics at once.
        """
        evaluator = StrategyEvaluator(
            data=oscillating_ohlcv, initial_capital=10000, n_mc_simulations=1000
        )

        # "structure" (MarketStructureStrategy) and "supertrend"
        # (SuperTrendStrategy) both produce ~34 trades on the oscillating
        # data — similar trade counts make this the exact scenario the
        # shared-seed bug contaminated.
        strategy_a = "structure"
        strategy_b = "supertrend"
        assert strategy_a in STRATEGY_REGISTRY, (
            f"{strategy_a} not in STRATEGY_REGISTRY: {list(STRATEGY_REGISTRY)}"
        )
        assert strategy_b in STRATEGY_REGISTRY, (
            f"{strategy_b} not in STRATEGY_REGISTRY: {list(STRATEGY_REGISTRY)}"
        )

        result_a = evaluator.evaluate_single(strategy_a)
        result_b = evaluator.evaluate_single(strategy_b)

        # Guard against false positives from zero-trade empty MC results.
        assert result_a.total_trades > 0, (
            f"Strategy '{strategy_a}' produced 0 trades on oscillating data; "
            "test cannot validate cross-strategy MC isolation without trades."
        )
        assert result_b.total_trades > 0, (
            f"Strategy '{strategy_b}' produced 0 trades on oscillating data; "
            "test cannot validate cross-strategy MC isolation without trades."
        )

        # At least one MC metric must differ between the two strategies.
        assert (
            result_a.mc_return_p5 != result_b.mc_return_p5
            or result_a.mc_max_dd_p95 != result_b.mc_max_dd_p95
            or result_a.mc_ruin_prob != result_b.mc_ruin_prob
        ), (
            "Two different strategies produced identical MC results — "
            "cross-strategy seed contamination regression detected. "
            f"{strategy_a}: p5={result_a.mc_return_p5}, "
            f"dd95={result_a.mc_max_dd_p95}, ruin={result_a.mc_ruin_prob}; "
            f"{strategy_b}: p5={result_b.mc_return_p5}, "
            f"dd95={result_b.mc_max_dd_p95}, ruin={result_b.mc_ruin_prob}"
        )
