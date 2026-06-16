"""实盘启动门禁入口的契约测试（scripts/start_live_trading.py）。

覆盖：默认安全开关关闭→门禁拦截；live 开关开启时的双重确认三条路径
（双 YES→NotReady、第一次非 YES→Blocked、第二次非 YES→Blocked）。
不触网、不下单。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from scripts import start_live_trading as slt
from scripts.start_live_trading import (
    LiveTradingBlocked,
    LiveTradingNotReady,
    check_live_switch_enabled,
    start_live_trading,
    verify_live_trading_checklist,
)


def _silent(*_a, **_k):
    pass


def test_live_switch_check_polarity(monkeypatch):
    """实盘开关：关→FAIL，开→PASS（与 preflight 安全默认相反）。"""
    from src.utils.config import config

    monkeypatch.setattr(config, "LIVE_TRADING_ENABLED", False)
    assert check_live_switch_enabled()["status"] == "FAIL"

    monkeypatch.setattr(config, "LIVE_TRADING_ENABLED", True)
    assert check_live_switch_enabled()["status"] == "PASS"


def test_verify_returns_bool_and_results():
    passed, results = verify_live_trading_checklist()
    assert isinstance(passed, bool)
    assert len(results) == len(slt.LIVE_GATE_CHECKS)
    assert all({"name", "status", "detail"} <= set(r) for r in results)


def test_default_env_blocks_before_confirmation(monkeypatch):
    """默认 LIVE_TRADING_ENABLED 关闭：门禁不过，应在任何确认提示前就拦截。"""
    from src.utils.config import config

    monkeypatch.setattr(config, "LIVE_TRADING_ENABLED", False)

    def _no_prompt(_msg):  # 一旦被调用即说明门禁没拦住，直接失败
        raise AssertionError("门禁未通过却仍向用户索要确认")

    with pytest.raises(LiveTradingBlocked):
        start_live_trading(confirm_fn=_no_prompt, echo=_silent)


def _force_gate_pass(monkeypatch):
    """绕过环境，强制自动门禁全过，以便单独测双重确认流程。"""
    monkeypatch.setattr(
        slt, "verify_live_trading_checklist", lambda: (True, [])
    )


def test_double_yes_reaches_not_ready(monkeypatch):
    """门禁全过 + 双 YES：因 Live Broker 未实现，应 raise LiveTradingNotReady。"""
    _force_gate_pass(monkeypatch)
    answers = iter(["YES", "YES"])

    with pytest.raises(LiveTradingNotReady):
        start_live_trading(confirm_fn=lambda _m: next(answers), echo=_silent)


def test_first_confirmation_no_blocks(monkeypatch):
    _force_gate_pass(monkeypatch)
    with pytest.raises(LiveTradingBlocked):
        start_live_trading(confirm_fn=lambda _m: "no", echo=_silent)


def test_second_confirmation_no_blocks(monkeypatch):
    _force_gate_pass(monkeypatch)
    answers = iter(["YES", "no"])
    with pytest.raises(LiveTradingBlocked):
        start_live_trading(confirm_fn=lambda _m: next(answers), echo=_silent)
