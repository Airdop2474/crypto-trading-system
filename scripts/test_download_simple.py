#!/usr/bin/env python3
"""
简单的数据下载测试
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.utils.logger import setup_logger, logger


def main():
    """主函数"""
    # 设置日志
    setup_logger(log_level="INFO")

    print("=" * 60)
    print("Simple Data Download Test")
    print("=" * 60)

    try:
        # 初始化下载器
        print("\n[1] Initializing downloader...")
        downloader = DataDownloader()
        print("    OK: Downloader initialized")

        # 测试连接
        print("\n[2] Testing exchange connection...")
        if downloader.exchange.test_connection():
            print("    OK: Exchange connected")
        else:
            print("    FAIL: Cannot connect to exchange")
            return 1

        # 下载数据
        print("\n[3] Downloading BTC/USDT 4h data (last 7 days)...")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        print(f"    Start date: {start_date.strftime('%Y-%m-%d')}")
        print(f"    End date: {end_date.strftime('%Y-%m-%d')}")

        df = downloader.download(
            symbol="BTC/USDT",
            timeframe="4h",
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            save_format="csv",
        )

        if df.empty:
            print("    WARNING: No data downloaded")
            return 1

        print(f"\n    SUCCESS: Downloaded {len(df)} records")
        print(f"    Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

        # 显示前几行
        print("\n    First 5 rows:")
        print(df.head().to_string())

        # 检查文件
        print("\n[4] Checking saved files...")
        data_dir = Path("data/raw")
        csv_files = list(data_dir.glob("BTC_USDT_4h_*.csv"))

        if csv_files:
            print(f"    OK: Found {len(csv_files)} CSV file(s)")
            for f in csv_files:
                print(f"      - {f.name}")
        else:
            print("    WARNING: No CSV files found")

        # 检查元数据
        metadata_file = data_dir / "metadata.csv"
        if metadata_file.exists():
            import pandas as pd
            meta = pd.read_csv(metadata_file)
            print(f"\n    Metadata records: {len(meta)}")
            if len(meta) > 0:
                latest = meta.iloc[-1]
                print(f"    Latest entry:")
                print(f"      Symbol: {latest['symbol']}")
                print(f"      Timeframe: {latest['timeframe']}")
                print(f"      Records: {latest['record_count']}")
                print(f"      Hash: {latest['data_hash'][:16]}...")

        print("\n" + "=" * 60)
        print("SUCCESS: Data download test passed!")
        print("=" * 60)
        print("\nNext step:")
        print("  - Check data/raw/ directory for CSV files")
        print("  - Check logs/ directory for log files")
        print("  - Continue with Day 3: Quality checker")

        return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
