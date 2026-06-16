"""API Key 权限校验纯函数测试（scripts/verify_api_key_permissions.py）。

只测 assess_api_key_permissions 决策逻辑，不触网。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.verify_api_key_permissions import (
    _truthy,
    assess_api_key_permissions,
)

# 合规基线：只读 + 现货，禁提币/合约，已绑 IP
SAFE = {
    "enableReading": True,
    "enableWithdrawals": False,
    "enableSpotAndMarginTrading": True,
    "enableFutures": False,
    "enableMargin": False,
    "ipRestrict": True,
}


def _status(checks, name):
    return next(c["status"] for c in checks if c["name"] == name)


def test_safe_config_passes():
    ok, checks = assess_api_key_permissions(SAFE)
    assert ok
    assert all(c["status"] == "PASS" for c in checks)


def test_withdrawals_enabled_fails():
    ok, checks = assess_api_key_permissions({**SAFE, "enableWithdrawals": True})
    assert not ok
    assert _status(checks, "禁止提币") == "FAIL"


def test_futures_enabled_fails():
    ok, checks = assess_api_key_permissions({**SAFE, "enableFutures": True})
    assert not ok
    assert _status(checks, "禁止合约") == "FAIL"


def test_spot_disabled_fails():
    ok, checks = assess_api_key_permissions(
        {**SAFE, "enableSpotAndMarginTrading": False})
    assert not ok
    assert _status(checks, "允许现货交易") == "FAIL"


def test_reading_disabled_fails():
    ok, checks = assess_api_key_permissions({**SAFE, "enableReading": False})
    assert not ok
    assert _status(checks, "允许读取账户") == "FAIL"


def test_no_ip_restrict_warns_not_fails():
    ok, checks = assess_api_key_permissions({**SAFE, "ipRestrict": False})
    assert ok  # 仅 WARN，不阻断
    assert _status(checks, "IP 白名单") == "WARN"


def test_margin_enabled_warns():
    ok, checks = assess_api_key_permissions({**SAFE, "enableMargin": True})
    assert ok
    assert _status(checks, "未单独开杠杆") == "WARN"


def test_empty_restrictions_fails_required():
    # 缺字段视为 False：提币/合约判为 OK，但现货/读取缺失 → FAIL
    ok, checks = assess_api_key_permissions({})
    assert not ok
    assert _status(checks, "允许现货交易") == "FAIL"
    assert _status(checks, "允许读取账户") == "FAIL"


def test_truthy_coerces_string_booleans():
    assert _truthy("true") is True
    assert _truthy("false") is False
    assert _truthy(True) is True
    assert _truthy(None) is False
