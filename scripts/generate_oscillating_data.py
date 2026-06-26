#!/usr/bin/env python3
"""
生成震荡区间行情数据（用于网格策略验证）

网格策略适合横盘震荡市场。当前真实数据（43 行下跌趋势）不适合，
此脚本生成区间内正弦波动 + 噪声的合成数据，便于做有意义的回测验证。

生成的数据满足 7 项质量检查：时间连续、唯一、OHLC 逻辑、
无异常波动、成交量非零、无空值。
"""

import sys
from pathlib import Path
from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logger, logger


def generate_oscillating_ohlcv(
    start_date: str = "2024-01-01",
    bars: int = 500,
    timeframe: str = "4h",
    center_price: float = 50000.0,
    amplitude_pct: float = 0.10,
    num_cycles: float = 8.0,
    noise_pct: float = 0.01,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """
    生成区间震荡的 OHLCV 数据

    参数：
        start_date: 起始日期
        bars: K 线数量
        timeframe: 周期（决定时间间隔）
        center_price: 区间中枢价格
        amplitude_pct: 振幅占中枢比例（如 0.10 = ±10%）
        num_cycles: 整个序列包含的完整震荡周期数
        noise_pct: 每根 K 线噪声幅度占价格比例
        seed: 随机种子（可复现）

    返回：
        OHLCV DataFrame
    """
    timeframe_map = {
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
    }
    delta = timeframe_map.get(timeframe, timedelta(hours=4))

    rng = np.random.default_rng(seed)
    start = pd.to_datetime(start_date)
    timestamps = [start + i * delta for i in range(bars)]

    # 正弦震荡的收盘价 + 噪声（区间内）
    t = np.linspace(0, num_cycles * 2 * np.pi, bars)
    base = center_price * (1 + amplitude_pct * np.sin(t))
    noise = rng.normal(0, center_price * noise_pct, bars)
    closes = base + noise

    rows = []
    prev_close = closes[0]
    for ts, close in zip(timestamps, closes):
        # open = 上一根 close（连续），首根用自身
        open_price = prev_close
        # high/low 包住 open 和 close，加少量随机上下影线
        wick = abs(rng.normal(0, center_price * noise_pct * 0.5))
        high = max(open_price, close) + wick
        low = min(open_price, close) - wick
        volume = rng.uniform(100, 1000)

        rows.append({
            "timestamp": ts,
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": round(volume, 2),
        })
        prev_close = close

    return pd.DataFrame(rows)


def main():
    setup_logger(log_level="INFO")

    df = generate_oscillating_ohlcv()
    logger.info(f"Generated {len(df)} oscillating bars")
    logger.info(
        f"Price range: {df['low'].min():.2f} - {df['high'].max():.2f}, "
        f"mean close: {df['close'].mean():.2f}"
    )

    data_dir = Path("data/raw")
    data_dir.mkdir(parents=True, exist_ok=True)

    start_str = df["timestamp"].min().strftime("%Y%m%d")
    end_str = df["timestamp"].max().strftime("%Y%m%d")
    file_path = data_dir / f"BTC_USDT_4h_osc_{start_str}_{end_str}.csv"
    df.to_csv(file_path, index=False)
    logger.info(f"Saved to {file_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
