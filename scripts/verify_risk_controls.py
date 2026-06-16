#!/usr/bin/env python3
"""
风控门禁验证脚本（LIVE_TRADING_CHECKLIST.md §2 风控测试）

一次性跑完 6 个熔断/恢复场景，逐项打印 PASS/FAIL，并以退出码反映总体结果
（全过 0，否则 1），作为实盘前的可重复门禁证据。

用法：
    python scripts/verify_risk_controls.py

对应清单（§2）：
    1. 日亏损限制（3%）触发
    2. 连续亏损熔断（5 笔）触发
    3. 数据异常熔断
    4. API 失败熔断
    5. 人工恢复流程
    6. 紧急停止机制
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.execution.risk_manager import RiskManager, ACTIVE, PAUSED, STOPPED

CAPITAL = 10000.0


def _rm():
    return RiskManager(
        capital_base=CAPITAL,
        max_daily_loss=0.03,
        max_consecutive_losses=5,
        max_api_failures=3,
    )


def _loss(amount, day="2024-01-01"):
    return {"profit": -abs(amount), "time": day}


def _win(amount, day="2024-01-01"):
    return {"profit": abs(amount), "time": day}


# ---- 6 个场景：每个返回 (passed: bool, detail: str) ----

def s1_daily_loss():
    rm = _rm()
    rm.record_fill(_loss(200))          # 2% 未触发
    active_before = rm.can_trade()
    rm.record_fill(_loss(150))          # 累计 350 = 3.5% >= 3%
    ok = active_before and rm.is_paused()
    return ok, f"2%后 active={active_before}, 3.5%后 state={rm.state}"


def s2_consecutive_losses():
    rm = _rm()
    for _ in range(4):
        rm.record_fill(_loss(1))        # 4 笔未到阈值（且金额小，不触发日亏损）
    active_before = rm.can_trade()
    rm.record_fill(_loss(1))            # 第 5 笔
    ok = active_before and rm.is_paused()
    return ok, f"4笔后 active={active_before}, 5笔后 state={rm.state}, consec={rm.consecutive_losses}"


def s3_data_anomaly():
    rm = _rm()
    rm.record_data_anomaly("gap > 60min")
    ok = rm.is_paused()
    return ok, f"state={rm.state}"


def s4_api_failure():
    rm = _rm()
    rm.record_api_failure()
    rm.record_api_failure()
    active_before = rm.can_trade()      # 2 次未到阈值
    rm.record_api_failure()            # 第 3 次
    ok = active_before and rm.is_paused()
    return ok, f"2次后 active={active_before}, 3次后 state={rm.state}"


def s5_manual_recovery():
    rm = _rm()
    rm.record_data_anomaly()           # -> PAUSED
    resumed = rm.resume()              # PAUSED -> ACTIVE
    back_active = rm.can_trade()
    # STOPPED 不能 resume
    rm.emergency_stop()
    cannot = rm.resume() is False and rm.is_stopped()
    ok = resumed and back_active and cannot
    return ok, f"resume={resumed}, back_active={back_active}, stopped不可resume={cannot}"


def s6_emergency_stop():
    rm = _rm()
    rm.emergency_stop("manual")
    stopped = rm.is_stopped()
    # 熔断不能把 STOPPED 降级
    rm.record_data_anomaly()
    still_stopped = rm.is_stopped()
    rm.reset()                          # 完全重置
    back = rm.can_trade()
    ok = stopped and still_stopped and back
    return ok, f"stopped={stopped}, 熔断不降级={still_stopped}, reset后active={back}"


SCENARIOS = [
    ("§2.1 日亏损限制(3%)触发", s1_daily_loss),
    ("§2.2 连续亏损熔断(5笔)触发", s2_consecutive_losses),
    ("§2.3 数据异常熔断", s3_data_anomaly),
    ("§2.4 API 失败熔断", s4_api_failure),
    ("§2.5 人工恢复流程", s5_manual_recovery),
    ("§2.6 紧急停止机制", s6_emergency_stop),
]


def run_all():
    """运行全部场景，返回 [{name, passed, detail}]。供脚本与测试共用。"""
    results = []
    for name, fn in SCENARIOS:
        try:
            passed, detail = fn()
        except Exception as e:  # 防御：场景内异常视为失败
            passed, detail = False, f"EXCEPTION {type(e).__name__}: {e}"
        results.append({"name": name, "passed": passed, "detail": detail})
    return results


def main() -> int:
    from src.utils.logger import setup_logger
    setup_logger(log_level="ERROR")  # 压低风控 warning 噪声

    print("=" * 70)
    print("风控门禁验证（LIVE_TRADING_CHECKLIST §2）")
    print("=" * 70)

    results = run_all()
    for r in results:
        tag = "PASS" if r["passed"] else "FAIL"
        print(f"[{tag}] {r['name']}")
        print(f"       {r['detail']}")

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print("-" * 70)
    print(f"结果：{passed}/{total} 通过")
    print("=" * 70)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
