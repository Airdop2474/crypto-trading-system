#!/usr/bin/env python3
"""
实盘启动门禁入口（double-confirmation gate）。

【重要 / 诚实声明】
Live Broker（真实下单）属于 Phase 7+，尚未实现。本脚本只实现 *启动前门禁*：
以代码强制校验所有可自动验证的前置条件 + 人工双重确认（YES/YES），全部通过
后仍会因"无 Live Broker 可接"而硬性拒绝启动（raise LiveTradingNotReady）。
即——门禁是真的、能拦；交易动作目前不存在，不会假装在跑。

设计：
  - verify_live_trading_checklist() 纯函数、无 I/O、无副作用，可单测/供 CI 复用。
    复用 preflight_check 的可自动验证项，但把"安全开关"换成与实盘相反的极性
    （preflight 要求 LIVE_TRADING_ENABLED=False 作为安全默认；实盘启动要求 =True）。
  - start_live_trading() 负责交互式双重确认，input/print 可注入便于测试。

用法：
    python scripts/start_live_trading.py
退出码：1=门禁未过或用户取消；2=门禁全过但 Live Broker 未实现（Phase 7+）。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from scripts.preflight_check import (  # noqa: E402
    _fail,
    _ok,
    check_broker_layers,
    check_core_deps,
    check_gate_docs,
    check_python_version,
    check_risk_controls,
    check_risk_params,
)


class LiveTradingBlocked(Exception):
    """门禁未通过或用户取消，拒绝启动实盘。"""


class LiveTradingNotReady(Exception):
    """门禁全过 + 已双重确认，但 Live Broker（真实下单）尚未实现（Phase 7+）。"""


def check_live_switch_enabled():
    """实盘启动要求 LIVE_TRADING_ENABLED=true（与 preflight 安全默认相反）。"""
    from src.utils.config import config

    live = config.LIVE_TRADING_ENABLED
    detail = f"LIVE_TRADING_ENABLED={live}"
    if live is True:
        return _ok("实盘开关已显式开启", detail)
    return _fail("实盘开关已显式开启", detail + "（须在 .env 设 true 方可实盘）")


# 实盘启动门禁项：复用 preflight 可自动验证项，但安全开关换成"要求开启"。
LIVE_GATE_CHECKS = [
    check_live_switch_enabled,
    check_python_version,
    check_core_deps,
    check_risk_params,
    check_gate_docs,
    check_broker_layers,
    check_risk_controls,
]


def verify_live_trading_checklist():
    """
    运行所有可自动验证的实盘门禁。

    返回：(all_passed: bool, results: list[{name,status,detail}])
    纯函数、无交互、无副作用——供 start_live_trading() 与 CI 复用。
    """
    results = []
    for fn in LIVE_GATE_CHECKS:
        try:
            results.append(fn())
        except Exception as e:  # 单项异常不应让整张门禁崩溃，记为 FAIL
            results.append(_fail(fn.__name__, f"EXCEPTION {type(e).__name__}: {e}"))
    all_passed = all(r["status"] == "PASS" for r in results)
    return all_passed, results


def start_live_trading(confirm_fn=input, echo=print):
    """
    实盘启动入口（双重确认门禁）。

    流程（对应 LIVE_TRADING_CHECKLIST「实盘开关 / 双重确认」）：
      1. 自动门禁 verify_live_trading_checklist() 必须全过，否则 raise LiveTradingBlocked
      2. 第一次人工确认（输入 YES）
      3. 第二次（最终警告）人工确认（输入 YES）
      4. 全部通过后——因无 Live Broker（Phase 7+）——raise LiveTradingNotReady

    参数：
        confirm_fn: 读取用户确认的函数（默认 input；测试可注入）
        echo:       输出函数（默认 print；测试可静音）
    """
    echo("=" * 72)
    echo("实盘启动门禁（start_live_trading）")
    echo("=" * 72)

    passed, results = verify_live_trading_checklist()
    for r in results:
        echo(f"  [{r['status']}] {r['name']}")
        echo(f"         {r['detail']}")
    if not passed:
        failed = [r["name"] for r in results if r["status"] != "PASS"]
        raise LiveTradingBlocked(f"门禁未通过：{', '.join(failed)}")

    echo("\n自动门禁全部通过。⚠️  即将进入实盘交易，使用真实资金，存在亏损风险。")
    if confirm_fn("确认启动实盘交易？(YES/no): ") != "YES":
        raise LiveTradingBlocked("用户取消（第一次确认未输入 YES）")

    echo("⚠️  最后确认：这将以真实资金下单，且不可自动撤回。")
    if confirm_fn("最后确认 (YES/no): ") != "YES":
        raise LiveTradingBlocked("用户取消（最终确认未输入 YES）")

    # 门禁 + 双重确认均通过，但 Live Broker 尚未实现（Phase 7+）——硬性拒绝。
    raise LiveTradingNotReady(
        "门禁与双重确认均通过，但 Live Broker（真实下单）属于 Phase 7+，尚未实现，"
        "拒绝启动。请勿绕过此拦截。"
    )


def main() -> int:
    from src.utils.logger import setup_logger

    setup_logger(log_level="ERROR")
    try:
        start_live_trading()
    except LiveTradingBlocked as e:
        print(f"\n[拒绝启动] {e}")
        return 1
    except LiveTradingNotReady as e:
        print(f"\n[拒绝启动] {e}")
        return 2
    return 0  # 不可达：成功路径目前必然 raise LiveTradingNotReady


if __name__ == "__main__":
    sys.exit(main())
