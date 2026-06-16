"""守护进程 exchange 模式装配/护栏/漂移/检查点测试（离线，FakeExchange 注入）。

不触网：硬护栏拒启、注入装配、持仓漂移熔断、exchange 检查点序列化 + 重启对账。
真实 testnet 端到端由人工跑（见 plan 验证段）。
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from scripts.run_paper_trading_daemon import PaperTradingDaemon, parse_args
from src.execution.exchange_broker import ExchangeBroker


class FakeExchange:
    """市价单全成 + 余额/持仓/查单可配的交易所替身。"""

    def __init__(self, *, usdt_free=10000.0, base_free=1.0, order_status=None):
        self.usdt_free = usdt_free
        self.base_free = base_free
        self._order_status = order_status

    def amount_to_precision(self, symbol, amount):
        return f"{float(amount):.5f}"

    def price_to_precision(self, symbol, price):
        return f"{float(price):.2f}"

    def market(self, symbol):
        return {"limits": {"amount": {"min": 0.0001}, "cost": {"min": 5.0}}}

    def create_order(self, symbol, type, side, amount, price):
        return {"id": "OID", "status": "closed",
                "average": 65000.0, "filled": float(f"{amount:.5f}")}

    def fetch_order(self, order_id, symbol=None):
        return self._order_status

    def fetch_balance(self):
        return {"USDT": {"free": self.usdt_free},
                "BTC": {"free": self.base_free}}


def _exchange_daemon(tmp_path, monkeypatch, fake, **cfg):
    """构造 exchange 模式守护进程：放行 testnet 护栏 + 注入 FakeExchange 后端。"""
    monkeypatch.setattr("src.utils.config.config.BINANCE_TESTNET", True)
    monkeypatch.setattr("src.utils.config.config.BINANCE_API_KEY", "k")
    monkeypatch.setattr("src.utils.config.config.BINANCE_SECRET", "s")
    args = parse_args(["--broker", "exchange", "--no-db",
                       "--state-file", str(tmp_path / "st.json"),
                       "--report-dir", str(tmp_path / "d")])
    d = PaperTradingDaemon(args)
    monkeypatch.setattr(d, "_make_exchange_broker",
                        lambda: ExchangeBroker(exchange=fake))
    return d


# ---- flag 默认 ----

def test_broker_defaults_to_paper():
    assert parse_args([]).broker == "paper"


# ---- 硬护栏：仅允许 testnet ----

def test_exchange_refuses_when_not_testnet(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.config.config.BINANCE_TESTNET", False)
    args = parse_args(["--broker", "exchange",
                       "--state-file", str(tmp_path / "st.json")])
    d = PaperTradingDaemon(args)
    with pytest.raises(SystemExit, match="testnet"):
        d._build(40000.0, 60000.0)


def test_exchange_refuses_without_keys(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.config.config.BINANCE_TESTNET", True)
    monkeypatch.setattr("src.utils.config.config.BINANCE_API_KEY", "")
    args = parse_args(["--broker", "exchange",
                       "--state-file", str(tmp_path / "st.json")])
    d = PaperTradingDaemon(args)
    with pytest.raises(SystemExit, match="API_KEY"):
        d._build(40000.0, 60000.0)


# ---- 注入装配 ----

def test_exchange_build_wires_adapter_and_config(tmp_path, monkeypatch):
    fake = FakeExchange(usdt_free=8000.0, base_free=2.0)
    d = _exchange_daemon(tmp_path, monkeypatch, fake)
    d._build(40000.0, 60000.0)
    from src.execution.exchange_runner_broker import ExchangeRunnerBroker
    assert isinstance(d.broker, ExchangeRunnerBroker)
    # runner 注入了显式 ExecutionConfig（initial_balance 来自真实余额快照）
    assert d.runner.exec_cfg.initial_balance == 8000.0
    assert d.broker.initial_position == 2.0


# ---- 持仓漂移熔断 ----

def test_drift_triggers_emergency_stop(tmp_path, monkeypatch):
    fake = FakeExchange(base_free=1.0)
    d = _exchange_daemon(tmp_path, monkeypatch, fake)
    d._build(40000.0, 60000.0)
    d.runner.lots = {1: {"amount": 0.01, "cost_price": 65000.0}}
    fake.base_free = 1.5  # 交易所多了 0.5（卡单后成交等），本地只记 0.01
    d._reconcile_drift()
    assert d.risk.state == "STOPPED"


def test_no_drift_keeps_active(tmp_path, monkeypatch):
    fake = FakeExchange(base_free=1.0)
    d = _exchange_daemon(tmp_path, monkeypatch, fake)
    d._build(40000.0, 60000.0)
    d.runner.lots = {1: {"amount": 0.01, "cost_price": 65000.0}}
    fake.base_free = 1.01  # delta 0.01 == 本地净持仓
    d._reconcile_drift()
    assert d.risk.can_trade()


# ---- 检查点（exchange 分支）----

def test_checkpoint_serializes_adapter_ledger(tmp_path, monkeypatch):
    fake = FakeExchange()
    d = _exchange_daemon(tmp_path, monkeypatch, fake)
    d._build(40000.0, 60000.0)
    d._checkpoint()
    st = json.loads((tmp_path / "st.json").read_text(encoding="utf-8"))
    assert set(st["broker"]) == {"ledger", "unconfirmed", "errors",
                                 "initial_balance", "initial_position"}


def test_restore_refuses_when_unconfirmed_still_open(tmp_path, monkeypatch):
    # 写一份带未确认订单的检查点，重启时该订单仍 open → 拒绝静默续跑
    fake = FakeExchange(order_status={"status": "open"})
    d = _exchange_daemon(tmp_path, monkeypatch, fake)
    d._build(40000.0, 60000.0)
    d.broker._unconfirmed = ["X1"]
    d._checkpoint()

    d2 = _exchange_daemon(tmp_path, monkeypatch, fake)
    with pytest.raises(SystemExit, match="未确认订单"):
        d2._restore()
