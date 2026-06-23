#!/usr/bin/env python3
"""
离线测试 - 使用模拟数据

当无法连接到交易所时使用
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
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
    market_type: str = "oscillating",
) -> pd.DataFrame:
    """
    生成模拟的 OHLCV 数据

    参数：
        start_date: 开始日期
        end_date: 结束日期
        timeframe: 时间周期
        initial_price: 初始价格
        market_type: 市场类型（oscillating=震荡, trending=趋势, black_swan=黑天鹅）

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

    # 根据市场类型选择价格生成器
    if market_type == "trending":
        prices = _trending_prices(initial_price, n)
    elif market_type == "black_swan":
        prices = _black_swan_prices(initial_price, n)
    elif market_type == "random":
        choice = np.random.randint(0, 3)
        if choice == 0:
            prices = _oscillating_prices(initial_price, n)
        elif choice == 1:
            prices = _trending_prices(initial_price, n)
        else:
            prices = _black_swan_prices(initial_price, n)
    else:
        prices = _oscillating_prices(initial_price, n)

    # 生成 OHLCV
    # 动态种子：每次运行产生不同数据，避免回测结果固定可预测
    rng = np.random.RandomState(None)
    data = []
    for i, (timestamp, close) in enumerate(zip(timestamps, prices)):
        volatility = close * 0.015
        open_price = close * (1 + rng.normal(0, 0.005))
        high = max(open_price, close) + abs(float(rng.normal(0, volatility * 0.8)))
        low = min(open_price, close) - abs(float(rng.normal(0, volatility * 0.8)))
        volume = abs(rng.normal(500, 100))

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


def generate_and_save_data(
    symbol: str = "BTC/USDT",
    timeframe: str = "4h",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_price: float = 50000.0,
    n_bars: int = 500,
    market_type: str = "oscillating",
) -> pd.DataFrame:
    """
    生成模拟数据并保存到 data/raw/。

    由 run_data_pipeline.py 在无真实数据时自动调用。

    参数：
        symbol: 交易对（用于文件名）
        timeframe: K 线周期
        start_date: 开始日期（None=用 n_bars 推算）
        end_date: 结束日期（None=现在）
        initial_price: 起始价格
        n_bars: K 线数量
        market_type: 市场类型（oscillating/trending/black_swan）

    返回：
        生成的 DataFrame
    """
    from datetime import datetime, timedelta

    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        # 根据 timeframe 推算起始日期，避免硬编码 4h
        tf_hours = {"15m": 0.25, "1h": 1, "4h": 4, "1d": 24}
        hours_per_bar = tf_hours.get(timeframe, 4)
        start = datetime.now() - timedelta(hours=n_bars * hours_per_bar)
        start_date = start.strftime("%Y-%m-%d")

    df = generate_mock_ohlcv(
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe,
        initial_price=initial_price,
        market_type=market_type,
    )

    if df.empty:
        logger.warning("Mock data generation returned empty DataFrame")
        return df

    # 保存到 CSV
    data_dir = Path("data/raw")
    data_dir.mkdir(parents=True, exist_ok=True)

    safe_symbol = symbol.replace("/", "_").upper()
    start_str = df["timestamp"].min().strftime("%Y%m%d")
    end_str = df["timestamp"].max().strftime("%Y%m%d")
    filename = f"{safe_symbol}_{timeframe}_{start_str}_{end_str}.csv"
    file_path = data_dir / filename

    df.to_csv(file_path, index=False)
    logger.info(f"Mock data saved: {file_path} ({len(df)} bars, {timeframe})")
    return df


# ======================================================================
# 市场类型价格生成器
# ======================================================================

def _oscillating_prices(base: float, n: int) -> list:
    """震荡市场：均值回归 + 周期性波动，确保 RSI/MA 等策略能产生信号"""
    rng = np.random.RandomState(None)
    prices = [base]
    mean = base
    for i in range(1, n):
        # 基础噪声
        ret = rng.normal(0, 0.025)
        # 周期性波动（模拟市场情绪摆动，让 RSI 触及超买超卖）
        ret += 0.015 * np.sin(i / 8)
        # 均值回归
        deviation = (prices[-1] - mean) / mean
        ret -= deviation * 0.08
        prices.append(prices[-1] * (1 + ret))
    return prices


def _trending_prices(base: float, n: int) -> list:
    """趋势市场：ADX > 25，单边走势"""
    rng = np.random.RandomState(None)
    prices = [base]
    drift = 0.002
    for i in range(1, n):
        if i > n // 3:
            drift = 0.004
        if i > n * 2 // 3:
            drift = -0.002
        ret = drift + rng.normal(0, 0.015)
        prices.append(prices[-1] * (1 + ret))
    return prices


def _black_swan_prices(base: float, n: int) -> list:
    """黑天鹅市场：正常 → 暴跌 → 震荡修复"""
    rng = np.random.RandomState(None)
    prices = [base]
    crash_bar = n // 3
    for i in range(1, n):
        if i == crash_bar:
            ret = -0.25 + rng.normal(0, 0.02)
        elif crash_bar < i < crash_bar + 3:
            ret = -0.08 + rng.normal(0, 0.03)
        elif crash_bar + 3 <= i < crash_bar + 8:
            ret = 0.06 + rng.normal(0, 0.03)
        else:
            ret = rng.normal(0, 0.012)
        prices.append(prices[-1] * (1 + ret))
    return prices


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
