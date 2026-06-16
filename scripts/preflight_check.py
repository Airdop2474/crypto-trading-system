#!/usr/bin/env python3
"""
实盘前门禁自检（preflight）——汇总所有“可自动验证”的门禁项，出一张总表。

跑齐能机器验证的检查并给退出码（全过 0，否则 1）。**重要：自检通过 ≠ 可以
实盘**——LIVE_TRADING_CHECKLIST 里大量门禁是时间/人工轨道（60 天连续运行、
连续 3 周无故障、签风险确认书、资金 ≤$500 等），无法脚本验证，本脚本会单列
为 MANUAL 提醒人工核验。

用法：
    python scripts/preflight_check.py            # 含测试套件+覆盖率
    python scripts/preflight_check.py --skip-tests
"""

import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

REQUIRED_DOCS = [
    "DATA_QUALITY_STANDARD.md",
    "BACKTEST_VALIDATION.md",
    "STRATEGY_ASSUMPTIONS.md",
    "AI_USAGE_BOUNDARIES.md",
    "LIVE_TRADING_CHECKLIST.md",
    "OPERATIONS_MANUAL.md",
    "TROUBLESHOOTING.md",
]

# 人工/时间轨道门禁（无法脚本验证，单列提醒）
MANUAL_GATES = [
    "§1 Paper Trading 连续运行 60 天，每日摘要齐全",
    "§3 连续 3 周无系统故障、无数据缺口",
    "API Key 权限受限（只读+现货，禁提币/杠杆/合约）",
    "初始资金 ≤ $500，且为可承受损失",
    "用户风险确认书已签署",
    "实盘双重确认开关（人工 YES/YES）",
]

COVERAGE_MIN = 80.0


def _ok(name, detail=""):
    return {"name": name, "status": "PASS", "detail": detail}


def _fail(name, detail=""):
    return {"name": name, "status": "FAIL", "detail": detail}


# ---- 可自动验证的检查（fast，无子进程；供脚本与 CI 共用）----

def check_python_version():
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 11)
    d = f"{v.major}.{v.minor}.{v.micro}"
    return _ok("Python ≥ 3.11", d) if ok else _fail("Python ≥ 3.11", d)


def check_core_deps():
    missing = []
    for mod in ["ccxt", "pandas", "numpy", "fastapi", "uvicorn",
                "psycopg2", "sqlalchemy", "loguru"]:
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    if missing:
        return _fail("核心依赖可导入", f"缺失: {', '.join(missing)}")
    return _ok("核心依赖可导入", "全部就绪")


def check_safety_switches():
    from src.utils.config import config
    live = config.LIVE_TRADING_ENABLED
    testnet = config.BINANCE_TESTNET
    ok = (live is False) and (testnet is True)
    detail = f"LIVE_TRADING_ENABLED={live}, BINANCE_TESTNET={testnet}"
    return _ok("实盘安全开关", detail) if ok else _fail("实盘安全开关", detail)


def check_risk_params():
    from src.utils.config import config
    problems = []
    if not (0 < config.MAX_DAILY_LOSS <= 0.03):
        problems.append(f"MAX_DAILY_LOSS={config.MAX_DAILY_LOSS}(应 ≤0.03)")
    if not (0 < config.MAX_POSITION_SIZE <= 0.20):
        problems.append(f"MAX_POSITION_SIZE={config.MAX_POSITION_SIZE}(应 ≤0.20)")
    if not (0 < config.MAX_TOTAL_POSITION <= 0.60):
        problems.append(f"MAX_TOTAL_POSITION={config.MAX_TOTAL_POSITION}(应 ≤0.60)")
    if not (0 < config.MAX_CONSECUTIVE_LOSSES <= 5):
        problems.append(f"MAX_CONSECUTIVE_LOSSES={config.MAX_CONSECUTIVE_LOSSES}(应 ≤5)")
    if problems:
        return _fail("风控参数符合清单", "; ".join(problems))
    return _ok("风控参数符合清单",
               f"日亏{config.MAX_DAILY_LOSS:.0%}/连亏{config.MAX_CONSECUTIVE_LOSSES}/"
               f"总仓{config.MAX_TOTAL_POSITION:.0%}")


def check_gate_docs():
    base = project_root / "docs" / "standards"
    missing = [d for d in REQUIRED_DOCS if not (base / d).exists()]
    if missing:
        return _fail("门禁文档齐全(§5)", f"缺: {', '.join(missing)}")
    return _ok("门禁文档齐全(§5)", f"{len(REQUIRED_DOCS)} 份齐全")


def check_broker_layers():
    try:
        from src.execution import PaperBroker, ExchangeBroker  # noqa: F401
    except Exception as e:
        return _fail("Broker 三层可导入", f"{type(e).__name__}: {e}")
    return _ok("Broker 三层可导入", "Paper + Exchange 就绪")


def check_risk_controls():
    from scripts.verify_risk_controls import run_all
    results = run_all()
    failed = [r["name"] for r in results if not r["passed"]]
    if failed:
        return _fail("§2 风控熔断场景", f"未过: {', '.join(failed)}")
    return _ok("§2 风控熔断场景", f"{len(results)}/{len(results)} 场景 PASS")


FAST_CHECKS = [
    check_python_version,
    check_core_deps,
    check_safety_switches,
    check_risk_params,
    check_gate_docs,
    check_broker_layers,
    check_risk_controls,
]


def run_checks():
    """运行全部 fast 检查，返回 [{name,status,detail}]。供 CI 复用。"""
    out = []
    for fn in FAST_CHECKS:
        try:
            out.append(fn())
        except Exception as e:
            out.append(_fail(fn.__name__, f"EXCEPTION {type(e).__name__}: {e}"))
    return out


# ---- 测试套件 + 覆盖率（子进程，仅 main 调用，避免 CI 递归）----

def run_test_suite():
    cmd = [sys.executable, "-m", "pytest", "-p", "no:asyncio",
           "--cov=src", "--cov-report=term", "-q"]
    proc = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    cov = None
    for line in out.splitlines():
        if line.strip().startswith("TOTAL"):
            for tok in line.split():
                if tok.endswith("%"):
                    try:
                        cov = float(tok.rstrip("%"))
                    except ValueError:
                        pass
    passed = proc.returncode == 0
    cov_ok = cov is not None and cov >= COVERAGE_MIN
    detail = f"pytest_rc={proc.returncode}, coverage={cov}%（门禁 ≥{COVERAGE_MIN:.0f}%）"
    name = "测试套件 + 覆盖率(§4)"
    return _ok(name, detail) if (passed and cov_ok) else _fail(name, detail)


def main() -> int:
    skip_tests = "--skip-tests" in sys.argv
    from src.utils.logger import setup_logger
    setup_logger(log_level="ERROR")

    print("=" * 72)
    print("实盘前门禁自检（preflight）")
    print("=" * 72)

    results = run_checks()
    if not skip_tests:
        print("[..] 运行测试套件 + 覆盖率（数秒）...")
        results.append(run_test_suite())

    print("\n自动验证项：")
    for r in results:
        print(f"  [{r['status']}] {r['name']}")
        print(f"         {r['detail']}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)

    print("\nMANUAL 门禁（脚本无法验证，须人工核验）：")
    for g in MANUAL_GATES:
        print(f"  [MANUAL] {g}")

    print("-" * 72)
    print(f"自动验证：{passed}/{total} 通过")
    all_ok = passed == total
    if all_ok:
        print("结论：自动验证全部通过。[注意] 但这不等于可以实盘——"
              "上面 MANUAL 门禁必须人工逐项确认。")
    else:
        print("结论：存在未通过的自动验证项，禁止进入实盘前置流程。")
    print("=" * 72)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
