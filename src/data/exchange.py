"""交易所接口封装.

使用 ccxt 统一的交易所接口
"""

from typing import Any, Optional

import ccxt
import pandas as pd

from src.utils.config import config
from src.utils.binance_proxy import apply_proxy_to_ccxt
from src.utils.logger import logger


class ExchangeClient:
    """交易所客户端"""

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        testnet: bool = True,
    ):
        """
        初始化交易所客户端

        参数：
            exchange_id: 交易所ID（binance, okex, etc.）
            api_key: API Key（可选，只读取数据不需要）
            secret: Secret（可选）
            testnet: 是否使用测试网
        """
        self.exchange_id = exchange_id
        self.testnet = testnet

        # 初始化交易所
        exchange_class = getattr(ccxt, exchange_id)

        # 配置参数
        params: dict[str, Any] = {
            "enableRateLimit": True,  # 启用限流保护
        }

        # 如果提供了 API Key
        if api_key is not None and api_key != "" and secret is not None and secret != "":
            params["apiKey"] = api_key
            params["secret"] = secret

        # 测试网配置（Binance）
        if testnet and exchange_id == "binance":
            # 如果只是获取历史/公开数据，使用主网（不需要 API Key）
            # 但若提供了 API Key，必须切换到测试网端点，否则凭据会发往主网
            params["options"] = {"defaultType": "spot"}  # 现货，不是期货

        self.exchange = exchange_class(params)

        # 有凭据的 testnet 必须切换 sandbox 端点，防止测试网 Key 发往主网
        if testnet and api_key is not None and api_key != "" and secret is not None and secret != "":
            self.exchange.set_sandbox_mode(True)

        # 反代中转：美国 IP 被地域限制（HTTP 451），通过 Cloudflare Worker 反代绕过
        # 公开数据（无凭据）走主网 /main；有凭据的 testnet 走 /testnet
        is_public = (api_key is None or api_key == "")
        apply_proxy_to_ccxt(self.exchange, testnet=testnet, public=is_public)

        logger.info(
            f"Exchange client initialized: {exchange_id} "
            f"(testnet={testnet})"
        )

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        获取 OHLCV 数据

        参数：
            symbol: 交易对（如 'BTC/USDT'）
            timeframe: 时间周期（1m, 5m, 15m, 1h, 4h, 1d）
            since: 起始时间戳（毫秒）
            limit: 返回数量限制

        返回：
            DataFrame with columns: [timestamp, open, high, low, close, volume]
        """
        try:
            logger.debug(
                f"Fetching OHLCV: {symbol} {timeframe} "
                f"since={since} limit={limit}"
            )

            # 获取数据
            ohlcv = self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=since,
                limit=limit,
            )

            # 转换为 DataFrame
            df = pd.DataFrame(
                ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )

            # 转换时间戳（毫秒 -> datetime）
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

            logger.info(
                f"Fetched {len(df)} candles for {symbol} {timeframe}"
            )

            return df

        except Exception as e:
            logger.error(f"Failed to fetch OHLCV: {e}")
            raise

    def fetch_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        获取指定日期范围的 OHLCV 数据

        参数：
            symbol: 交易对
            timeframe: 时间周期
            start_date: 开始日期（'YYYY-MM-DD'）
            end_date: 结束日期（'YYYY-MM-DD'）

        返回：
            完整的 OHLCV DataFrame
        """
        try:
            # 转换日期为时间戳（统一按 UTC 解析，与 ccxt 返回的 UTC 时间戳一致）
            start_ts = int(pd.Timestamp(start_date, tz="UTC").timestamp() * 1000)
            end_ts = int(pd.Timestamp(end_date, tz="UTC").timestamp() * 1000)

            logger.info(
                f"Fetching {symbol} {timeframe} "
                f"from {start_date} to {end_date}"
            )

            all_data = []
            current_ts = start_ts
            prev_last_ts = None

            # 分批获取（每次最多 1000 条）
            while current_ts < end_ts:
                batch = self.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    since=current_ts,
                    limit=1000,
                )

                if batch.empty:
                    break

                # 最后一条数据的时间戳（毫秒）
                last_ts = int(batch.iloc[-1]["timestamp"].timestamp() * 1000)

                # 防止死循环：若时间戳未前进（交易所重复返回同批数据），停止
                # 在 append 之前检查，避免把重复批次混入造成时间戳重复
                if prev_last_ts is not None and last_ts <= prev_last_ts:
                    break
                prev_last_ts = last_ts

                all_data.append(batch)

                # 下一批从最后一条数据之后开始
                current_ts = last_ts + 1

            # 合并所有数据
            if all_data:
                df = pd.concat(all_data, ignore_index=True)
                # 过滤超出范围的数据
                df = df[
                    (df["timestamp"] >= pd.to_datetime(start_date))
                    & (df["timestamp"] <= pd.to_datetime(end_date))
                ]

                logger.info(f"Total fetched: {len(df)} candles")
                return df
            else:
                logger.warning("No data fetched")
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"Failed to fetch OHLCV range: {e}")
            raise

    def get_exchange_info(self, symbol: str) -> dict[str, Any]:
        """
        获取交易对信息

        参数：
            symbol: 交易对

        返回：
            交易对信息字典
        """
        try:
            markets = self.exchange.load_markets()
            if symbol in markets:
                return dict(markets[symbol])
            else:
                raise ValueError(f"Symbol {symbol} not found")

        except Exception as e:
            logger.error(f"Failed to get exchange info: {e}")
            raise

    def test_connection(self) -> bool:
        """
        测试交易所连接

        返回：
            是否连接成功
        """
        try:
            # 尝试获取服务器时间
            self.exchange.fetch_time()
            logger.info(f"Exchange {self.exchange_id} connection OK")
            return True

        except Exception as e:
            logger.error(f"Exchange {self.exchange_id} connection failed: {e}")
            return False


# 便捷函数：创建默认的 Binance 客户端
def create_binance_client(testnet: bool = True, public: bool = False) -> ExchangeClient:
    """
    创建 Binance 客户端

    参数：
        testnet: 是否使用测试网
        public: 仅取公开行情时置 True —— 不带任何凭据。公开数据无需签名，
                且若把 testnet key 传给主网会被拒（-2008 Invalid Api-Key）。

    返回：
        ExchangeClient 实例
    """
    return ExchangeClient(
        exchange_id="binance",
        api_key=None if public else (config.BINANCE_API_KEY or None),
        secret=None if public else (config.BINANCE_SECRET or None),
        testnet=testnet,
    )


# 导出
__all__ = ["ExchangeClient", "create_binance_client"]
