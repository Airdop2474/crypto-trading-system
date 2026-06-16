"""testnet 冒烟的纯函数测试（scripts/testnet_smoke.py）。

集成步骤需 testnet 凭据无法离线测；这里只测安全限价单参数计算 + 护栏逻辑。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from scripts.testnet_smoke import extract_fill, main, safe_limit_order_params


class _Res:
    def __init__(self, filled_price=None, filled_amount=None):
        self.filled_price = filled_price
        self.filled_amount = filled_amount


def test_safe_limit_below_market_and_notional():
    price, amount = safe_limit_order_params(60000.0, notional=20.0, factor=0.5)
    assert price == 30000.0          # 半价，挂着不会成交
    assert amount * price == pytest.approx(20.0)  # 名义额对齐


def test_safe_limit_custom_factor():
    price, _ = safe_limit_order_params(100.0, factor=0.3)
    assert price == 30.0


def test_safe_limit_rejects_bad_price():
    with pytest.raises(ValueError):
        safe_limit_order_params(0.0)


def test_safe_limit_rejects_bad_factor():
    with pytest.raises(ValueError):
        safe_limit_order_params(100.0, factor=1.5)  # 不低于市价 = 可能成交


def test_extract_fill_prefers_place_result():
    p, a, src = extract_fill(_Res(filled_price=100.0, filled_amount=0.5))
    assert (p, a, src) == (100.0, 0.5, "place")


def test_extract_fill_falls_back_to_status():
    p, a, src = extract_fill(_Res(), {"average": 101.0, "filled": 0.3})
    assert (p, a, src) == (101.0, 0.3, "status")


def test_extract_fill_status_uses_price_when_no_average():
    p, a, src = extract_fill(_Res(), {"price": 102.0, "filled": 0.2})
    assert (p, a, src) == (102.0, 0.2, "status")


def test_extract_fill_none_when_nothing():
    assert extract_fill(_Res(), None) == (None, None, "none")
    assert extract_fill(_Res(), {"average": 0, "filled": 0}) == (None, None, "none")


def test_main_refuses_when_not_testnet(monkeypatch):
    """护栏：BINANCE_TESTNET=false 必须拒绝（exit 2），绝不碰主网。"""
    from src.utils.config import config
    monkeypatch.setattr(config, "BINANCE_TESTNET", False)
    monkeypatch.setattr(config, "BINANCE_API_KEY", "k")
    monkeypatch.setattr(config, "BINANCE_SECRET", "s")
    assert main([]) == 2


def test_main_refuses_without_keys(monkeypatch):
    from src.utils.config import config
    monkeypatch.setattr(config, "BINANCE_TESTNET", True)
    monkeypatch.setattr(config, "BINANCE_API_KEY", "")
    monkeypatch.setattr(config, "BINANCE_SECRET", "")
    assert main([]) == 2
