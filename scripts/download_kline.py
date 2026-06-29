"""下载 Binance K 线数据到本地 CSV（用于 replay 测试）

用法：
    python scripts/download_kline.py --symbol BTC/USDT --timeframe 1h --days 20
"""
import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path

import ccxt
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--days", type=int, default=20)
    parser.add_argument("--out", default=None, help="输出文件路径，默认 data/{symbol}_{tf}_{days}d.csv")
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else Path(f"data/{args.symbol.replace('/', '_')}_{args.timeframe}_{args.days}d.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    exchange = ccxt.binance()
    since = exchange.parse8601(
        (datetime.utcnow() - timedelta(days=args.days)).strftime("%Y-%m-%dT00:00:00Z")
    )
    all_ohlcv = []
    while since < exchange.milliseconds():
        ohlcv = exchange.fetch_ohlcv(args.symbol, args.timeframe, since, limit=1000)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        since = ohlcv[-1][0] + 1
        time.sleep(0.3)  # 避免触发限流

    df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates("timestamp").set_index("datetime")

    df.to_csv(out_path)
    print(f"下载完成: {len(df)} 根 {args.timeframe} K 线 -> {out_path}")
    print(f"时间范围: {df.index[0]} ~ {df.index[-1]}")
    print(f"价格范围: {df['low'].min():.2f} ~ {df['high'].max():.2f}")


if __name__ == "__main__":
    main()
