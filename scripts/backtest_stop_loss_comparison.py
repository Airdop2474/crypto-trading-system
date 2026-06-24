#!/usr/bin/env python3
"""
12 策略止损对照回测

对每个策略执行两次回测：
1. 无止损（baseline）
2. 有止损（stop_loss）

对比指标：
- 总收益 / 年化收益
- 最大回撤
- Sharpe Ratio
- 交易笔数
- 止损触发次数

出口标准（v3 Phase 1）：
- Sharpe 下降 > 30% → 该策略止损方案返工
- 最大回撤下降 < 15% → 止损未起效，重检查参数

用法：
    python scripts/backtest_stop_loss_comparison.py
    python scripts/backtest_stop_loss_comparison.py --strategy rsi ma
    python scripts/backtest_stop_loss_comparison.py --days 365
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# 确保项目根目录在 path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np

from src.utils.logger import logger
from src.strategy.registry import STRATEGY_REGISTRY
from src.strategy.stop_configs import get_stop_config, STRATEGY_STOP_CONFIGS
from src.data.exchange import fetch_ohlcv


def run_backtest(strategy_name: str, with_stop: bool, symbol: str = "BTC/USDT",
                 timeframe: str = "4h", days: int = 365) -> dict:
    """运行单个策略回测

    返回：回测结果摘要
    """
    from src.backtest.engine import BacktestEngine
    from src.execution.paper_broker import PaperBroker

    # 获取策略类
    strategy_cls = STRATEGY_REGISTRY.get(strategy_name)
    if strategy_cls is None:
        return {"error": f"Unknown strategy: {strategy_name}"}

    # 获取止损配置
    stop_config = get_stop_config(strategy_name) if with_stop else None

    # 创建策略实例
    try:
        # 尝试带 stop_loss_config 参数
        strategy = strategy_cls(
            initial_capital=10000.0,
            stop_loss_config=stop_config,
        )
    except TypeError:
        # 如果策略不接受 stop_loss_config，用旧方式
        strategy = strategy_cls(initial_capital=10000.0)

    # 获取数据
    try:
        data = fetch_ohlcv(symbol=symbol, timeframe=timeframe, days=days)
    except Exception as e:
        return {"error": f"Failed to fetch data: {e}"}

    if data is None or len(data) < 50:
        return {"error": f"Insufficient data: {len(data) if data is not None else 0} bars"}

    # 运行回测
    try:
        broker = PaperBroker(
            initial_balance=10000.0,
            commission=0.001,
            slippage_pct=0.0005,
        )
        engine = BacktestEngine(strategy=strategy, broker=broker)
        result = engine.run(data)

        # 提取关键指标
        stats = result.get("statistics", {})
        return {
            "strategy": strategy_name,
            "with_stop": with_stop,
            "total_return": stats.get("total_return", 0),
            "annual_return": stats.get("annual_return", 0),
            "max_drawdown": stats.get("max_drawdown", 0),
            "sharpe_ratio": stats.get("sharpe_ratio", 0),
            "total_trades": stats.get("total_trades", 0),
            "win_rate": stats.get("win_rate", 0),
            "final_balance": stats.get("final_balance", 10000),
        }
    except Exception as e:
        logger.error(f"Backtest failed for {strategy_name}: {e}")
        return {"error": str(e)}


def compare_strategy(strategy_name: str, symbol: str, timeframe: str, days: int) -> dict:
    """对照回测单个策略"""
    print(f"\n{'='*60}")
    print(f"  策略: {strategy_name}")
    print(f"{'='*60}")

    # 无止损
    print(f"  [1/2] 回测无止损版...")
    baseline = run_backtest(strategy_name, with_stop=False, symbol=symbol,
                           timeframe=timeframe, days=days)

    # 有止损
    print(f"  [2/2] 回测有止损版...")
    with_stop = run_backtest(strategy_name, with_stop=True, symbol=symbol,
                            timeframe=timeframe, days=days)

    if "error" in baseline:
        print(f"  ✗ 基线回测失败: {baseline['error']}")
        return {"strategy": strategy_name, "error": baseline["error"]}
    if "error" in with_stop:
        print(f"  ✗ 止损回测失败: {with_stop['error']}")
        return {"strategy": strategy_name, "error": with_stop["error"]}

    # 对比
    sharpe_base = baseline.get("sharpe_ratio", 0)
    sharpe_stop = with_stop.get("sharpe_ratio", 0)
    mdd_base = abs(baseline.get("max_drawdown", 0))
    mdd_stop = abs(with_stop.get("max_drawdown", 0))

    sharpe_change = ((sharpe_stop - sharpe_base) / abs(sharpe_base) * 100) if sharpe_base != 0 else 0
    mdd_change = ((mdd_stop - mdd_base) / mdd_base * 100) if mdd_base > 0 else 0

    # 出口标准检查
    verdict = "PASS"
    issues = []

    if sharpe_base > 0 and sharpe_change < -30:
        verdict = "FAIL"
        issues.append(f"Sharpe 下降 {sharpe_change:.1f}% > 30%")

    if mdd_base > 0 and mdd_change > -15:
        verdict = "WARN"
        issues.append(f"最大回撤仅下降 {abs(mdd_change):.1f}% < 15%")

    result = {
        "strategy": strategy_name,
        "baseline": baseline,
        "with_stop": with_stop,
        "sharpe_change_pct": round(sharpe_change, 1),
        "mdd_change_pct": round(mdd_change, 1),
        "verdict": verdict,
        "issues": issues,
    }

    # 打印结果
    print(f"\n  {'指标':<20} {'无止损':>12} {'有止损':>12} {'变化':>10}")
    print(f"  {'-'*56}")
    print(f"  {'总收益':.<20} {baseline['total_return']:>12.2%} {with_stop['total_return']:>12.2%} {(with_stop['total_return']-baseline['total_return'])*100:>9.1f}%")
    print(f"  {'最大回撤':.<20} {mdd_base:>12.2%} {mdd_stop:>12.2%} {mdd_change:>9.1f}%")
    print(f"  {'Sharpe':.<20} {sharpe_base:>12.2f} {sharpe_stop:>12.2f} {sharpe_change:>9.1f}%")
    print(f"  {'交易笔数':.<20} {baseline['total_trades']:>12} {with_stop['total_trades']:>12} {with_stop['total_trades']-baseline['total_trades']:>9}")
    print(f"  {'胜率':.<20} {baseline['win_rate']:>12.1%} {with_stop['win_rate']:>12.1%}")

    verdict_emoji = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠"}[verdict]
    print(f"\n  {verdict_emoji} 结论: {verdict}")
    if issues:
        for issue in issues:
            print(f"    → {issue}")

    return result


def main():
    parser = argparse.ArgumentParser(description="12 策略止损对照回测")
    parser.add_argument("--strategy", nargs="*", help="指定策略（默认全部）")
    parser.add_argument("--symbol", default="BTC/USDT", help="交易对")
    parser.add_argument("--timeframe", default="4h", help="K线周期")
    parser.add_argument("--days", type=int, default=365, help="回测天数")
    parser.add_argument("--output", default=None, help="输出 JSON 文件路径")
    args = parser.parse_args()

    strategies = args.strategy or list(STRATEGY_STOP_CONFIGS.keys())

    print(f"{'='*60}")
    print(f"  12 策略止损对照回测")
    print(f"  交易对: {args.symbol} | 周期: {args.timeframe} | 天数: {args.days}")
    print(f"  策略数: {len(strategies)}")
    print(f"{'='*60}")

    results = []
    for s in strategies:
        try:
            result = compare_strategy(s, args.symbol, args.timeframe, args.days)
            results.append(result)
        except Exception as e:
            print(f"\n  ✗ {s} 回测异常: {e}")
            results.append({"strategy": s, "error": str(e)})

    # 汇总
    print(f"\n{'='*60}")
    print(f"  汇总")
    print(f"{'='*60}")
    print(f"  {'策略':<15} {'Sharpe变化':>10} {'回撤变化':>10} {'结论':>6}")
    print(f"  {'-'*45}")

    pass_count = 0
    fail_count = 0
    warn_count = 0

    for r in results:
        if "error" in r:
            print(f"  {r['strategy']:<15} {'ERROR':>10} {'':>10} {'✗':>6}")
            fail_count += 1
            continue

        verdict = r.get("verdict", "?")
        emoji = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠"}.get(verdict, "?")
        print(f"  {r['strategy']:<15} {r.get('sharpe_change_pct', 0):>9.1f}% {r.get('mdd_change_pct', 0):>9.1f}% {emoji:>6}")

        if verdict == "PASS":
            pass_count += 1
        elif verdict == "FAIL":
            fail_count += 1
        elif verdict == "WARN":
            warn_count += 1

    print(f"\n  通过: {pass_count} | 警告: {warn_count} | 失败: {fail_count}")

    # 保存结果
    output_path = args.output or str(PROJECT_ROOT / "data" / "stop_loss_comparison.json")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  结果已保存: {output_path}")


if __name__ == "__main__":
    main()
