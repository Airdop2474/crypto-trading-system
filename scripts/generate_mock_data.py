#!/usr/bin/env python3
"""
离线测试 - 使用模拟数据

当无法连接到交易所时使用
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logger, logger


def generate_mock_ohlcv(
    start_date: str,
    end_date: str,
    timeframe: str = "4h",
    initial_price: float = 50000.0,
) -> pd.DataFrame:
    """
    生成模拟的 OHLCV 数据

    参数：
        start_date: 开始日期
        end_date: 结束日期
        timeframe: 时间周期
        initial_price: 初始价格

    返回：
        OHLCV DataFrame
    """
    # 解析时间间隔
    timeframe_map = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
    }

    delta = timeframe_map.get(timeframe, timedelta(hours=4))

    # 生成时间序列
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)

    timestamps = []
    current = start
    while current <= end:
        timestamps.append(current)
        current += delta

    n = len(timestamps)

    # 生成价格数据（随机游走）
    np.random.seed(42)  # 固定随机种子，保证可复现

    # 价格变化率（模拟市场波动）
    returns = np.random.normal(0.0001, 0.02, n)  # 均值0.01%，标准差2%
    prices = initial_price * np.exp(np.cumsum(returns))

    # 生成 OHLCV
    data = []
    for i, (timestamp, close) in enumerate(zip(timestamps, prices)):
        # 生成 open, high, low
        volatility = close * 0.01  # 1% 波动
        open_price = close + np.random.normal(0, volatility * 0.5)
        high = max(open_price, close) + abs(np.random.normal(0, volatility))
        low = min(open_price, close) - abs(np.random.normal(0, volatility))

        # 成交量（随机）
        volume = np.random.uniform(100, 1000)

        data.append({
            "timestamp": timestamp,
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": round(volume, 2),
        })

    df = pd.DataFrame(data)
    return df


def main():
    """主函数"""
    setup_logger(log_level="INFO")

    print("=" * 60)
    print("Offline Test - Using Mock Data")
    print("=" * 60)

    try:
        # 生成模拟数据
        print("\n[1] Generating mock OHLCV data...")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        df = generate_mock_ohlcv(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            timeframe="4h",
            initial_price=50000.0,
        )

        print(f"    Generated {len(df)} records")
        print(f"    Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

        # 保存数据
        print("\n[2] Saving mock data to CSV...")
        data_dir = Path("data/raw")
        data_dir.mkdir(parents=True, exist_ok=True)

        symbol_safe = "BTC_USDT"
        start_str = df["timestamp"].min().strftime("%Y%m%d")
        end_str = df["timestamp"].max().strftime("%Y%m%d")
        filename = f"{symbol_safe}_4h_{start_str}_{end_str}.csv"
        file_path = data_dir / filename

        df.to_csv(file_path, index=False)
        print(f"    Saved to: {file_path}")

        # 保存元数据
        print("\n[3] Saving metadata...")
        import hashlib

        data_string = df.to_csv(index=False)
        data_hash = hashlib.sha256(data_string.encode()).hexdigest()

        metadata = {
            "download_time": datetime.now().isoformat(),
            "symbol": "BTC/USDT",
            "timeframe": "4h",
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "file_path": str(file_path),
            "data_hash": data_hash,
            "record_count": len(df),
        }

        metadata_file = data_dir / "metadata.csv"
        df_meta = pd.DataFrame([metadata])

        if metadata_file.exists():
            df_existing = pd.read_csv(metadata_file)
            df_meta = pd.concat([df_existing, df_meta], ignore_index=True)

        df_meta.to_csv(metadata_file, index=False)
        print(f"    Metadata saved")
        print(f"    Hash: {data_hash[:16]}...")

        # 显示数据预览
        print("\n[4] Data preview:")
        print(df.head(10).to_string())

        # 统计信息
        print("\n[5] Statistics:")
        print(f"    Min price: {df['low'].min():.2f}")
        print(f"    Max price: {df['high'].max():.2f}")
        print(f"    Avg volume: {df['volume'].mean():.2f}")

        print("\n" + "=" * 60)
        print("SUCCESS: Mock data generated and saved!")
        print("=" * 60)
        print("\nFiles created:")
        print(f"  - {file_path}")
        print(f"  - {metadata_file}")
        print("\nNext step:")
        print("  - Continue with Day 3: Quality checker")
        print("  - Use this mock data for testing")

        return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
