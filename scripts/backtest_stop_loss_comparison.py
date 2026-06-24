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
- 胜率

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
import inspect
from pathlib import Path
from datetime import datetime, timedelta

# 确保项目根目录在 path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np

from src.utils.logger import logger
from src.strategy.registry import STRATEGY_REGISTRY
from src.strategy.stop_configs import get_stop_config, STRATEGY_STOP_CONFIGS


def fetch_data(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """从 Binance 获取历史 OHLCV 数据（直接 REST API，绕过 ccxt）"""
    import os
    import requests

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    proxies = {"http": proxy, "https": proxy} if proxy else None
    if proxy:
        logger.info(f"Using proxy: {proxy}")

    # Binance 现货 REST API
    base_url = "https://api.binance.com/api/v3/klines"
    # 转换交易对格式: BTC/USDT -> BTCUSDT
    sym = symbol.replace("/", "")

    end = datetime.utcnow()
    start = end - timedelta(days=days)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    all_data = []
    current_start = start_ms

    while current_start < end_ms:
        params = {
            "symbol": sym,
            "interval": timeframe,
            "startTime": current_start,
            "endTime": end_ms,
            "limit": 1000,
        }
        resp = requests.get(base_url, params=params, proxies=proxies, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            break

        all_data.extend(data)
        current_start = data[-1][0] + 1
        if len(data) < 1000:
            break

    if not all_data:
        raise RuntimeError("No data fetched from Binance")

    # Binance klines 格式: [openTime, open, high, low, close, volume, closeTime, ...]
    df = pd.DataFrame(all_data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    # 去掉仍在形成中的最后一根
    df = df[df["timestamp"] < pd.Timestamp(end, tz="UTC")]
    return df[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def create_strategy(strategy_name: str, stop_config, data: pd.DataFrame):
    """创建策略实例，处理不同策略的构造参数差异"""
    strategy_cls = STRATEGY_REGISTRY[strategy_name]
    sig_params = set(inspect.signature(strategy_cls.__init__).parameters.keys())
    sig_params.discard("self")

    kwargs = {}
    if "initial_capital" in sig_params:
        kwargs["initial_capital"] = 10000.0
    if "stop_loss_config" in sig_params:
        kwargs["stop_loss_config"] = stop_config

    # Grid 需要价格区间
    if strategy_name == "grid":
        warm = data.iloc[:30]
        lo, hi = warm["low"].min(), warm["high"].max()
        span = hi - lo
        kwargs["lower_price"] = lo + span * 0.1
        kwargs["upper_price"] = hi - span * 0.1

    # 过滤 None 值
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    return strategy_cls(**kwargs)


def run_backtest(strategy_name: str, with_stop: bool, data: pd.DataFrame) -> dict:
    """运行单个策略回测

    返回：回测结果摘要
    """
    from src.backtest.engine import BacktestEngine

    stop_config = get_stop_config(strategy_name) if with_stop else None

    try:
        strategy = create_strategy(strategy_name, stop_config, data)
    except Exception as e:
        return {"error": f"Failed to create strategy: {e}"}

    engine = BacktestEngine(initial_capital=10000.0, commission=0.001, slippage=0.0005)
    result = engine.run(data, strategy)

    if not result.get("success"):
        return {"error": result.get("message", "Backtest failed")}

    metrics = result.get("metrics", {})
    return {
        "strategy": strategy_name,
        "with_stop": with_stop,
        "total_return": metrics.get("total_return", 0),
        "annual_return": metrics.get("annual_return", 0),
        "max_drawdown": metrics.get("max_drawdown", 0),
        "sharpe_ratio": metrics.get("sharpe_ratio", 0),
        "total_trades": metrics.get("total_trades", 0),
        "win_rate": metrics.get("win_rate", 0),
        "final_equity": result.get("final_equity", 10000),
    }


def compare_strategy(strategy_name: str, data: pd.DataFrame) -> dict:
    """对照回测单个策略"""
    print(f"\n{'='*60}")
    print(f"  策略: {strategy_name}")
    print(f"{'='*60}")

    print(f"  [1/2] 回测无止损版...")
    baseline = run_backtest(strategy_name, with_stop=False, data=data)

    print(f"  [2/2] 回测有止损版...")
    with_stop = run_backtest(strategy_name, with_stop=True, data=data)

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

    # 一次性获取数据，所有策略共用
    print(f"\n  获取历史数据...")
    try:
        data = fetch_data(args.symbol, args.timeframe, args.days)
    except Exception as e:
        print(f"  ✗ 获取数据失败: {e}")
        return 1

    print(f"  数据: {len(data)} bars, {data.iloc[0]['timestamp']} → {data.iloc[-1]['timestamp']}")

    results = []
    for s in strategies:
        try:
            result = compare_strategy(s, data)
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
