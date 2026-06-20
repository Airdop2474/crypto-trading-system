"""
数据下载器

下载历史 OHLCV 数据并保存到文件
"""

from pathlib import Path
from typing import List, Optional
import pandas as pd
import numpy as np
from datetime import datetime
import hashlib
import time

from src.data.exchange import ExchangeClient, create_binance_client
from src.utils.logger import logger


class DataDownloader:
    """数据下载器"""

    def __init__(
        self,
        exchange_client: Optional[ExchangeClient] = None,
        data_dir: str = "data/raw",
    ):
        """
        初始化数据下载器

        参数：
            exchange_client: 交易所客户端（默认使用 Binance）
            data_dir: 数据保存目录
        """
        # 历史 OHLCV 是公开数据，无需凭据——用 public=True 走主网拉真实数据，
        # 避免 testnet=True + 有凭据时 set_sandbox_mode 把数据源切到 testnet
        self.exchange = exchange_client or create_binance_client(
            testnet=False, public=True
        )
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"DataDownloader initialized. Data dir: {self.data_dir}")

    def download(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        save_format: str = "csv",
    ) -> pd.DataFrame:
        """
        下载并保存数据

        参数：
            symbol: 交易对（如 'BTC/USDT'）
            timeframe: 时间周期（1h, 4h, 1d）
            start_date: 开始日期（'YYYY-MM-DD'）
            end_date: 结束日期（'YYYY-MM-DD'）
            save_format: 保存格式（'csv' or 'parquet'）

        返回：
            下载的数据 DataFrame
        """
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = 2 ** attempt
                    logger.info(f"Retry {attempt}/{max_retries} in {delay}s...")
                    time.sleep(delay)

                logger.info(
                    f"Downloading {symbol} {timeframe} "
                    f"from {start_date} to {end_date}"
                )

                # 下载数据
                df = self.exchange.fetch_ohlcv_range(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                )

                if df.empty:
                    logger.warning("No data downloaded")
                    return df

                # 保存数据
                file_path = self._save_data(
                    df=df,
                    symbol=symbol,
                    timeframe=timeframe,
                    format=save_format,
                )

                # 生成数据版本记录
                data_hash = self._calculate_hash(df)
                self._save_metadata(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    file_path=file_path,
                    data_hash=data_hash,
                    record_count=len(df),
                )

                logger.info(
                    f"✅ Downloaded and saved {len(df)} records to {file_path}"
                )
                logger.info(f"   Data hash (SHA256): {data_hash[:16]}...")

                return df

            except Exception as e:
                last_error = e
                logger.warning(f"Download attempt {attempt+1}/{max_retries} failed: {e}")
                continue

        logger.error(f"Download failed after {max_retries} attempts: {last_error}")
        if last_error is not None:
            raise last_error
        else:
            raise RuntimeError("Download failed with unknown error")

    def download_multiple(
        self,
        symbols: List[str],
        timeframe: str,
        start_date: str,
        end_date: str,
        save_format: str = "csv",
    ) -> dict:
        """
        下载多个交易对的数据

        参数：
            symbols: 交易对列表
            timeframe: 时间周期
            start_date: 开始日期
            end_date: 结束日期
            save_format: 保存格式

        返回：
            {symbol: DataFrame} 字典。

            契约：返回字典的 key 恒为传入的全部 symbols。
            - value 为 DataFrame：下载成功（可能为空 DataFrame，表示该区间无数据）
            - value 为 None：该 symbol 下载失败（已记录 error 日志）
            单个 symbol 失败不影响其余 symbol，调用方需自行检查 None。
        """
        results = {}
        failed = []

        for symbol in symbols:
            try:
                df = self.download(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    save_format=save_format,
                )
                results[symbol] = df

            except Exception as e:
                logger.error(f"Failed to download {symbol}: {e}")
                results[symbol] = None
                failed.append(symbol)

        succeeded = len(symbols) - len(failed)
        logger.info(
            f"download_multiple: {succeeded}/{len(symbols)} succeeded"
            + (f", failed: {failed}" if failed else "")
        )
        return results

    def _save_data(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        format: str = "csv",
    ) -> Path:
        """
        保存数据到文件

        参数：
            df: 数据 DataFrame
            symbol: 交易对
            timeframe: 时间周期
            format: 文件格式

        返回：
            文件路径
        """
        # 文件名：BTC_USDT_4h_20230101_20231231.csv
        symbol_safe = symbol.replace("/", "_")
        start_date = df["timestamp"].min().strftime("%Y%m%d")
        end_date = df["timestamp"].max().strftime("%Y%m%d")

        filename = f"{symbol_safe}_{timeframe}_{start_date}_{end_date}.{format}"
        file_path = self.data_dir / filename

        # 保存文件
        if format == "csv":
            df.to_csv(file_path, index=False)
        elif format == "parquet":
            df.to_parquet(file_path, index=False)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.debug(f"Data saved to {file_path}")
        return file_path

    def _calculate_hash(self, df: pd.DataFrame) -> str:
        """
        计算数据的 SHA256 哈希（列级增量，避免全量 CSV 序列化）

        参数：
            df: 数据 DataFrame

        返回：
            SHA256 哈希字符串
        """
        h = hashlib.sha256()
        # 按列哈希，避免全量序列化——比 df.to_csv() 快 10-50x
        for col in ["timestamp", "open", "high", "low", "close", "volume"]:
            h.update(str(len(df)).encode())
            h.update(col.encode())
            vals = df[col].values
            if vals.dtype.kind == "f":
                # Round floats to 6 decimal places for consistent hashing
                h.update(np.round(vals.astype(np.float64), 6).tobytes())
            elif vals.dtype.kind == "M":
                h.update(vals.astype(np.int64).tobytes())
            else:
                h.update(vals.tobytes())
        return h.hexdigest()

    def _save_metadata(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        file_path: Path,
        data_hash: str,
        record_count: int,
    ) -> None:
        """
        保存数据元信息

        参数：
            symbol: 交易对
            timeframe: 时间周期
            start_date: 开始日期
            end_date: 结束日期
            file_path: 数据文件路径
            data_hash: 数据哈希
            record_count: 记录数量
        """
        metadata_file = self.data_dir / "metadata.csv"

        # 创建元数据记录
        metadata = {
            "download_time": datetime.now().isoformat(),
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "file_path": str(file_path),
            "data_hash": data_hash,
            "record_count": record_count,
        }

        # 追加单行到元数据文件（避免每次全量读写，O(1) 而非 O(n²)）
        # 仅当文件不存在时写表头，已存在则纯追加
        df_meta = pd.DataFrame([metadata])
        write_header = not metadata_file.exists()
        df_meta.to_csv(metadata_file, mode="a", header=write_header, index=False)
        logger.debug(f"Metadata saved to {metadata_file}")

    def load_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        从文件加载数据

        参数：
            symbol: 交易对
            timeframe: 时间周期
            start_date: 可选的日期过滤
            end_date: 可选的日期过滤

        返回：
            数据 DataFrame
        """
        try:
            # 查找匹配的文件
            symbol_safe = symbol.replace("/", "_")
            pattern = f"{symbol_safe}_{timeframe}_*.csv"
            files = list(self.data_dir.glob(pattern))

            if not files:
                logger.warning(f"No data file found for {symbol} {timeframe}")
                return pd.DataFrame()

            # 使用最新的文件
            latest_file = sorted(files)[-1]
            logger.info(f"Loading data from {latest_file}")

            df = pd.read_csv(latest_file)
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            # 日期过滤
            if start_date:
                df = df[df["timestamp"] >= pd.to_datetime(start_date)]
            if end_date:
                df = df[df["timestamp"] <= pd.to_datetime(end_date)]

            logger.info(f"Loaded {len(df)} records")
            return df

        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            raise


# 导出
__all__ = ["DataDownloader"]
