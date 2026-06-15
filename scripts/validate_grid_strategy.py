#!/usr/bin/env python3
"""
Phase 3 网格策略验证（可复现）

完整验证流程：
1. 加载震荡区间数据（先运行 generate_oscillating_data.py 生成）
2. 数据质量检查（7 项）
3. 网格策略回测
4. 生成回测报告（JSON + Markdown）
5. 参数敏感性测试（grid_count ±20%）

验收标准（BACKTEST_VALIDATION.md / STRATEGY_ASSUMPTIONS.md）：
- 数据质量 7/7 通过
- 震荡市场收益 > 0
- 最大回撤 < 20%
- 参数 ±20% 收益变化 < 50%，无方向反转
"""

import sys
import glob
from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.quality_checker import DataQualityChecker
from src.backtest.engine import BacktestEngine
from src.backtest.param_scanner import ParameterScanner
from src.backtest.report_generator import BacktestReportGenerator
from src.strategy.grid_trading import GridTradingStrategy
from src.utils.logger import setup_logger, logger


def load_oscillating_data() -> pd.DataFrame:
    """加载最新的震荡数据文件"""
    files = sorted(glob.glob("data/raw/BTC_USDT_4h_osc_*.csv"))
    if not files:
        raise FileNotFoundError(
            "未找到震荡数据，请先运行 scripts/generate_oscillating_data.py"
        )
    df = pd.read_csv(files[-1])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def main() -> int:
    setup_logger(log_level="WARNING")  # 降噪，只看验证结果

    print("=" * 60)
    print("Phase 3: Grid Strategy Validation")
    print("=" * 60)

    # 1. 加载数据
    df = load_oscillating_data()
    print(f"\n[1] Data loaded: {len(df)} bars")
    print(f"    Range: ${df['low'].min():.2f} - ${df['high'].max():.2f}")

    # 2. 质量检查
    q = DataQualityChecker("4h").check_all(df)
    passed = q["summary"]["passed"]
    total = q["summary"]["total_checks"]
    print(f"\n[2] Quality check: {passed}/{total} "
          f"({'PASS' if q['summary']['all_passed'] else 'FAIL'})")
    if not q["summary"]["all_passed"]:
        print("    ERROR: data quality failed, aborting")
        return 1

    # 3. 回测
    lo, hi = df["low"].min(), df["high"].max()
    pr = hi - lo
    lower, upper = lo + pr * 0.1, hi - pr * 0.1
    strategy = GridTradingStrategy(
        lower_price=lower, upper_price=upper, grid_count=10
    )
    engine = BacktestEngine(10000.0, commission=0.001, slippage=0.0005)
    results = engine.run(data=df, strategy=strategy)
    m = results["metrics"]

    print(f"\n[3] Backtest:")
    print(f"    Return:    {results['total_return']:>8.2%}  "
          f"(criterion: > 0   -> "
          f"{'PASS' if results['total_return'] > 0 else 'FAIL'})")
    print(f"    Max DD:    {m['max_drawdown']:>8.2%}  "
          f"(criterion: > -20% -> "
          f"{'PASS' if m['max_drawdown'] > -0.20 else 'FAIL'})")
    print(f"    Sharpe:    {m['sharpe_ratio']:>8.2f}")
    print(f"    Win rate:  {m['win_rate']:>8.2%}")
    print(f"    Trades:    {results['total_trades']:>8}")

    # 4. 报告
    gen = BacktestReportGenerator()
    out = gen.generate(
        results, strategy, data=df,
        cost_model={"commission": 0.001, "slippage": 0.0005},
    )
    print(f"\n[4] Report generated:")
    print(f"    JSON: {out['json_path']}")
    print(f"    MD:   {out['markdown_path']}")

    # 5. 参数敏感性
    scanner = ParameterScanner(10000.0, 0.001, 0.0005)
    base = {"lower_price": lower, "upper_price": upper, "grid_count": 10}
    sens = scanner.sensitivity_analysis(df, GridTradingStrategy, base, "grid_count")
    stab = scanner.analyze_stability(sens)
    returns = sens["total_return"].tolist()
    reversal = any(a * b < 0 for a in returns for b in returns)

    print(f"\n[5] Sensitivity (grid_count +/-20%):")
    print(f"    Returns: {[f'{r:.2%}' for r in returns]}")
    print(f"    Stable:  {stab['stable']} (max_dev={stab['max_deviation']:.3f}, "
          f"criterion: < 0.5)")
    print(f"    Direction reversal: {reversal} "
          f"(criterion: False -> {'PASS' if not reversal else 'FAIL'})")

    print("\n" + "=" * 60)
    print("Validation completed")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
