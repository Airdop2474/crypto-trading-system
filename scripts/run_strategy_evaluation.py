#!/usr/bin/env python3
"""
12 策略全面评估：Monte Carlo + 参数稳定性 + 淘汰规则

v3 Phase 2 出口标准：
- 12 策略全有评估报告（median P&L / VaR / CVaR / 参数灵敏度 / IS-OS 差异）
- 淘汰规则白皮书发布并 review
- 至少 1 个淘汰建议执行

用法：
    python scripts/run_strategy_evaluation.py --days 180
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.utils.logger import logger
from src.backtest.strategy_evaluator import StrategyEvaluator


def fetch_data(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """从 Binance 获取历史 OHLCV 数据（直接 REST API）"""
    import os
    import requests

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    proxies = {"http": proxy, "https": proxy} if proxy else None
    if proxy:
        logger.info(f"Using proxy: {proxy}")

    base_url = "https://api.binance.com/api/v3/klines"
    sym = symbol.replace("/", "")

    end = datetime.utcnow()
    start = end - timedelta(days=days)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    all_data = []
    current_start = start_ms

    while current_start < end_ms:
        params = {
            "symbol": sym, "interval": timeframe,
            "startTime": current_start, "endTime": end_ms, "limit": 1000,
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

    df = pd.DataFrame(all_data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df = df[df["timestamp"] < pd.Timestamp(end, tz="UTC")]
    return df[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="12 策略全面评估")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="4h")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"  12 策略全面评估")
    print(f"  交易对: {args.symbol} | 周期: {args.timeframe} | 天数: {args.days}")
    print(f"{'='*60}")

    print(f"\n  获取历史数据...")
    data = fetch_data(args.symbol, args.timeframe, args.days)
    print(f"  数据: {len(data)} bars, {data.iloc[0]['timestamp']} → {data.iloc[-1]['timestamp']}")

    print(f"\n  开始评估（每策略含回测 + MC 1000 次 + 参数稳定性）...")
    evaluator = StrategyEvaluator(data, initial_capital=10000.0, n_mc_simulations=1000)
    results = evaluator.evaluate_all()

    # 打印汇总
    print(f"\n{'='*80}")
    print(f"  评估汇总")
    print(f"{'='*80}")
    print(f"  {'策略':<12} {'总分':>6} {'Sharpe':>8} {'回撤':>8} {'MC中位':>8} {'MC破产':>8} {'稳定性':>6} {'交易':>6} {'结论':>10}")
    print(f"  {'-'*80}")

    for r in results:
        print(
            f"  {r.strategy_name:<12} {r.total_score:>6.1f} "
            f"{r.sharpe_ratio:>8.2f} {r.max_drawdown:>8.2%} "
            f"{r.mc_return_median:>8.2%} {r.mc_ruin_prob:>8.1%} "
            f"{r.param_stability:>6.3f} {r.total_trades:>6} "
            f"{r.verdict:>10}"
        )
        if r.elimination_flags:
            for flag in r.elimination_flags:
                print(f"    → {flag}")

    # 统计
    keep = sum(1 for r in results if r.verdict == "KEEP")
    warn = sum(1 for r in results if r.verdict == "WARN")
    elim = sum(1 for r in results if r.verdict == "ELIMINATE")
    print(f"\n  KEEP: {keep} | WARN: {warn} | ELIMINATE: {elim}")

    # 保存结果
    output_path = args.output or str(PROJECT_ROOT / "data" / "strategy_evaluation.json")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in results], f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  结果已保存: {output_path}")


if __name__ == "__main__":
    main()
