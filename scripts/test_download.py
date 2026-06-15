#!/usr/bin/env python3
"""
测试数据下载

下载少量数据验证功能
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.utils.logger import setup_logger, logger


def test_download_small():
    """测试下载少量数据"""
    print("\n" + "=" * 60)
    print("Test: Download Small Dataset")
    print("=" * 60)

    # 初始化下载器
    downloader = DataDownloader()

    # 测试连接
    print("\n[1] Testing exchange connection...")
    if downloader.exchange.test_connection():
        print("    OK: Exchange connected")
    else:
        print("    FAIL: Cannot connect to exchange")
        return False

    # 下载 BTC/USDT 最近 7 天的数据（4h）
    print("\n[2] Downloading BTC/USDT 4h data (last 7 days)...")
    try:
        from datetime import datetime, timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        df = downloader.download(
            symbol="BTC/USDT",
            timeframe="4h",
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            save_format="csv",
        )

        print(f"\n    Downloaded: {len(df)} records")
        print(f"    Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        print(f"\n    Data preview:")
        print(df.head())

        # 检查数据文件
        print(f"\n[3] Checking saved files...")
        data_dir = Path("data/raw")
        csv_files = list(data_dir.glob("BTC_USDT_4h_*.csv"))
        print(f"    Found {len(csv_files)} CSV file(s)")

        # 检查元数据
        metadata_file = data_dir / "metadata.csv"
        if metadata_file.exists():
            import pandas as pd
            meta = pd.read_csv(metadata_file)
            print(f"\n    Metadata records: {len(meta)}")
            print(f"    Latest entry:")
            print(f"      Symbol: {meta.iloc[-1]['symbol']}")
            print(f"      Timeframe: {meta.iloc[-1]['timeframe']}")
            print(f"      Records: {meta.iloc[-1]['record_count']}")
            print(f"      Hash: {meta.iloc[-1]['data_hash'][:16]}...")

        return True

    except Exception as e:
        print(f"    FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_load_data():
    """测试加载数据"""
    print("\n" + "=" * 60)
    print("Test: Load Data from File")
    print("=" * 60)

    try:
        downloader = DataDownloader()

        print("\n[1] Loading BTC/USDT 4h data...")
        df = downloader.load_data(
            symbol="BTC/USDT",
            timeframe="4h",
        )

        if df.empty:
            print("    WARNING: No data found")
            print("    Run test_download_small first")
            return False

        print(f"    Loaded: {len(df)} records")
        print(f"    Columns: {df.columns.tolist()}")
        print(f"\n    Data preview:")
        print(df.head())

        return True

    except Exception as e:
        print(f"    FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    # 设置日志
    setup_logger(log_level="INFO")

    print("=" * 60)
    print("Data Download Module Test")
    print("=" * 60)

    results = []

    # 测试 1：下载数据
    results.append(("Download data", test_download_small()))

    # 测试 2：加载数据
    results.append(("Load data", test_load_data()))

    # 总结
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed

    for name, result in results:
        status = "OK" if result else "FAIL"
        print(f"  {status}: {name}")

    print("\n" + "=" * 60)

    if failed == 0:
        print("SUCCESS: All tests passed!")
        print("\nNext step:")
        print("  - Implement data quality checker")
        print("  - Run full quality checks")
        return 0
    else:
        print(f"FAILED: {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
