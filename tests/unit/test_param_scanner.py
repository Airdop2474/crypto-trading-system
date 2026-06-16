"""ParameterScanner 单元测试：网格搜索 / 敏感性分析 / 稳定性。"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
import pytest

from src.backtest.param_scanner import ParameterScanner
from src.strategy.simple_ma import SimpleMAStrategy


def _ohlcv(n=30):
    rng = np.random.default_rng(0)
    ts = pd.date_range("2024-01-01", periods=n, freq="4h")
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({
        "timestamp": ts,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": rng.uniform(10, 100, n),
    })


def test_grid_search_returns_row_per_combo():
    sc = ParameterScanner()
    df = sc.grid_search(
        _ohlcv(), SimpleMAStrategy,
        {"short_window": [2, 3], "long_window": [4, 5]},
    )
    assert len(df) == 4
    assert {"short_window", "long_window", "total_return", "total_trades"}.issubset(df.columns)


def test_sensitivity_analysis_and_stability():
    sc = ParameterScanner()
    res = sc.sensitivity_analysis(
        _ohlcv(), SimpleMAStrategy,
        base_params={"short_window": 3, "long_window": 10},
        test_param="short_window",
        variations=[-0.2, 0, 0.2],
    )
    assert "variation" in res.columns
    stab = sc.analyze_stability(res)
    assert "stable" in stab and "max_deviation" in stab
    assert stab["parameter"] == "short_window"


def test_sensitivity_rejects_unknown_param():
    sc = ParameterScanner()
    with pytest.raises(ValueError):
        sc.sensitivity_analysis(
            _ohlcv(), SimpleMAStrategy,
            base_params={"short_window": 3}, test_param="missing",
        )


def test_analyze_stability_edge_cases():
    sc = ParameterScanner()
    assert sc.analyze_stability(pd.DataFrame())["stable"] is False
    # 有结果但无 variation==0 的基准
    no_base = pd.DataFrame({"variation": [0.1], "total_return": [0.05], "parameter": ["x"]})
    assert sc.analyze_stability(no_base)["stable"] is False
