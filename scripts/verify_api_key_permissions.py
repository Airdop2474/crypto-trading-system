#!/usr/bin/env python3
"""
API Key 权限校验（接 Binance Demo/实盘前置门禁）。

把 LIVE_TRADING_CHECKLIST 里只有伪代码的 verify_api_key_permissions() 做成
真实代码：连交易所查 API Key 受限项，断言安全策略——

  必须满足（违反 = FAIL）：
    - 禁止提币（enableWithdrawals = False）        ← 资金安全，最关键
    - 禁止合约（enableFutures = False）
    - 允许现货交易（enableSpotAndMarginTrading=True）← 否则没法下现货单
    - 允许读取（enableReading = True）             ← 否则查不了账户
  建议满足（违反 = WARN）：
    - 已开 IP 白名单（ipRestrict = True）
    - 未单独开杠杆（enableMargin = False；注意 Binance 把现货与杠杆耦合在
      enableSpotAndMarginTrading 一个开关里，无法只关杠杆而保留现货）

assess_api_key_permissions() 纯函数（无网络），供 CLI/CI 复用；
连接器 fetch_restrictions() 走 ccxt Binance sapiGetAccountApiRestrictions。

用法：
    python scripts/verify_api_key_permissions.py            # 用 .env 里的 key
退出码：0=无 FAIL（WARN 不阻断）；1=存在 FAIL；2=无法连接/查询。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def _ok(name, detail=""):
    return {"name": name, "status": "PASS", "detail": detail}


def _warn(name, detail=""):
    return {"name": name, "status": "WARN", "detail": detail}


def _fail(name, detail=""):
    return {"name": name, "status": "FAIL", "detail": detail}


def _truthy(v):
    """Binance/ccxt 返回的布尔可能是 bool 或 'true'/'false' 字符串，统一成 bool。"""
    if isinstance(v, str):
        return v.strip().lower() == "true"
    return bool(v)


def assess_api_key_permissions(restrictions):
    """
    评估 API Key 权限是否符合安全策略。纯函数、无网络。

    参数：restrictions: dict，交易所返回的 API 限制项
    返回：(ok: bool, checks: list[{name,status,detail}])，ok = 不含 FAIL。
    """
    r = restrictions or {}
    checks = []

    # —— 必须满足 ——
    if _truthy(r.get("enableWithdrawals")):
        checks.append(_fail("禁止提币", "enableWithdrawals=True（高危！必须关闭）"))
    else:
        checks.append(_ok("禁止提币", "enableWithdrawals=False"))

    if _truthy(r.get("enableFutures")):
        checks.append(_fail("禁止合约", "enableFutures=True（必须关闭）"))
    else:
        checks.append(_ok("禁止合约", "enableFutures=False"))

    if _truthy(r.get("enableSpotAndMarginTrading")):
        checks.append(_ok("允许现货交易", "enableSpotAndMarginTrading=True"))
    else:
        checks.append(_fail("允许现货交易",
                            "enableSpotAndMarginTrading=False（无法下现货单）"))

    if _truthy(r.get("enableReading")):
        checks.append(_ok("允许读取账户", "enableReading=True"))
    else:
        checks.append(_fail("允许读取账户", "enableReading=False（无法查账户/持仓）"))

    # —— 建议满足 ——
    if _truthy(r.get("ipRestrict")):
        checks.append(_ok("IP 白名单", "ipRestrict=True"))
    else:
        checks.append(_warn("IP 白名单", "ipRestrict=False（建议绑定 IP 白名单）"))

    if _truthy(r.get("enableMargin")):
        checks.append(_warn("未单独开杠杆",
                            "enableMargin=True（Binance 现货/杠杆耦合，留意风险）"))

    ok = all(c["status"] != "FAIL" for c in checks)
    return ok, checks


# ------------------------------- 连接器 -------------------------------

def fetch_restrictions(exchange):
    """走 ccxt Binance 私有端点查 API Key 受限项。需要有效 key/secret。"""
    return exchange.sapiGetAccountApiRestrictions()


def _build_exchange():
    """用 .env 的 key/secret + testnet 标志构造交易所（复用 ExchangeBroker 的
    sandbox 修复，确保 testnet 真正打到 testnet endpoint）。"""
    from src.execution.exchange_broker import ExchangeBroker
    from src.utils.config import config

    broker = ExchangeBroker(
        api_key=config.BINANCE_API_KEY,
        secret=config.BINANCE_SECRET,
        testnet=config.BINANCE_TESTNET,
    )
    return broker.exchange, config.BINANCE_TESTNET


def main(argv=None) -> int:
    from src.utils.config import config
    from src.utils.logger import setup_logger

    setup_logger(log_level="ERROR")

    if not config.BINANCE_API_KEY or not config.BINANCE_SECRET:
        print("[拒绝] 未配置 BINANCE_API_KEY / BINANCE_SECRET（在 .env 填入后重试）")
        return 2

    exchange, testnet = _build_exchange()
    print("=" * 72)
    print(f"API Key 权限校验（testnet={testnet}）")
    print("=" * 72)
    try:
        restrictions = fetch_restrictions(exchange)
    except Exception as e:
        print(f"[拒绝] 查询权限失败：{type(e).__name__}: {e}")
        return 2

    ok, checks = assess_api_key_permissions(restrictions)
    for c in checks:
        print(f"  [{c['status']}] {c['name']}")
        print(f"         {c['detail']}")
    fails = sum(1 for c in checks if c["status"] == "FAIL")
    warns = sum(1 for c in checks if c["status"] == "WARN")
    print("-" * 72)
    print(f"结论：{'权限合规' if ok else '存在违规项，禁止用于交易'}"
          f"（WARN {warns} / FAIL {fails}）")
    print("=" * 72)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
