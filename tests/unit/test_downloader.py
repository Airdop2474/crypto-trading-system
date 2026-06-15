"""DataDownloader 健壮性测试（metadata 追加写 + download_multiple 失败契约）。

用假交易所客户端，不触网络。
"""

import pandas as pd
import pytest

from src.data.downloader import DataDownloader


class FakeExchange:
    """假交易所：按 symbol 返回预设数据或抛错。"""

    def __init__(self, responses):
        # responses: {symbol: DataFrame | Exception}
        self.responses = responses
        self.calls = []

    def fetch_ohlcv_range(self, symbol, timeframe, start_date, end_date):
        self.calls.append(symbol)
        resp = self.responses[symbol]
        if isinstance(resp, Exception):
            raise resp
        return resp


def _make_df(n=3):
    ts = pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.5] * n,
            "volume": [10.0] * n,
        }
    )


def test_metadata_appends_without_full_rewrite(tmp_path):
    """两次下载 → metadata.csv 表头只出现一次，累计两行。"""
    df = _make_df()
    ex = FakeExchange({"BTC/USDT": df, "ETH/USDT": df})
    dl = DataDownloader(exchange_client=ex, data_dir=str(tmp_path))

    dl.download("BTC/USDT", "4h", "2026-01-01", "2026-01-02")
    dl.download("ETH/USDT", "4h", "2026-01-01", "2026-01-02")

    meta_file = tmp_path / "metadata.csv"
    assert meta_file.exists()

    meta = pd.read_csv(meta_file)
    # 两行数据，列与单次写入一致（无重复表头行）
    assert len(meta) == 2
    assert list(meta["symbol"]) == ["BTC/USDT", "ETH/USDT"]
    assert set(meta.columns) == {
        "download_time", "symbol", "timeframe", "start_date",
        "end_date", "file_path", "data_hash", "record_count",
    }

    # 原始文本里 "symbol," 表头只出现一次
    raw = meta_file.read_text()
    assert raw.count("download_time,symbol,") == 1


def test_metadata_first_write_has_header(tmp_path):
    """首次写入包含表头。"""
    ex = FakeExchange({"BTC/USDT": _make_df()})
    dl = DataDownloader(exchange_client=ex, data_dir=str(tmp_path))
    dl.download("BTC/USDT", "4h", "2026-01-01", "2026-01-02")

    meta = pd.read_csv(tmp_path / "metadata.csv")
    assert len(meta) == 1
    assert meta.iloc[0]["record_count"] == 3


def test_download_multiple_keys_stable_on_partial_failure(tmp_path):
    """部分失败：返回字典 key 恒为全部 symbol，失败的为 None。"""
    ex = FakeExchange(
        {
            "BTC/USDT": _make_df(),
            "ETH/USDT": RuntimeError("boom"),
            "SOL/USDT": _make_df(),
        }
    )
    dl = DataDownloader(exchange_client=ex, data_dir=str(tmp_path))

    results = dl.download_multiple(
        ["BTC/USDT", "ETH/USDT", "SOL/USDT"], "4h", "2026-01-01", "2026-01-02"
    )

    assert set(results.keys()) == {"BTC/USDT", "ETH/USDT", "SOL/USDT"}
    assert isinstance(results["BTC/USDT"], pd.DataFrame)
    assert results["ETH/USDT"] is None  # 失败 → None
    assert isinstance(results["SOL/USDT"], pd.DataFrame)


def test_download_multiple_all_success(tmp_path):
    ex = FakeExchange({"BTC/USDT": _make_df(), "ETH/USDT": _make_df()})
    dl = DataDownloader(exchange_client=ex, data_dir=str(tmp_path))
    results = dl.download_multiple(
        ["BTC/USDT", "ETH/USDT"], "4h", "2026-01-01", "2026-01-02"
    )
    assert all(isinstance(v, pd.DataFrame) for v in results.values())
