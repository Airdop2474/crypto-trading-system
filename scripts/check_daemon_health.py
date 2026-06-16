#!/usr/bin/env python3
"""
Paper Trading 守护进程运行健康巡检（60 天值守期自动核验工具）。

给 60 天连续运行守护进程（run_paper_trading_daemon.py）配一个旁路巡检：
读它的状态检查点 + 每日报告目录，核验运行是否健康——

  - 检查点存在且可解析
  - 风控状态：STOPPED → FAIL（紧急停止，需人工 reset）；PAUSED → WARN（等待 resume）
  - 检查点新鲜度：mtime 超过阈值未更新 → WARN（疑似守护进程已停）
  - .resume 标志存在 → WARN（已申请人工恢复，下一轮自动解除）
  - 日报连续无缺口 + 数量对账（份数应 == day_count，日期不得跳缺）

assess_health() 为纯函数（无 I/O），供 CLI 与 CI 复用；CLI 负责采集输入。

用法：
    python scripts/check_daemon_health.py
    python scripts/check_daemon_health.py --state-file data/paper_daemon_state.json \\
        --report-dir data/reports/paper/daily --max-checkpoint-age-hours 12
退出码：0=无 FAIL（健康，可能含 WARN）；1=存在 FAIL。
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.execution import ACTIVE, PAUSED, STOPPED  # noqa: E402


def _ok(name, detail=""):
    return {"name": name, "status": "PASS", "detail": detail}


def _warn(name, detail=""):
    return {"name": name, "status": "WARN", "detail": detail}


def _fail(name, detail=""):
    return {"name": name, "status": "FAIL", "detail": detail}


def _date_gaps(dates):
    """返回 [min..max] 区间内缺失的日期（dates 已去重排序）。"""
    if len(dates) < 2:
        return []
    gaps = []
    cur = dates[0]
    end = dates[-1]
    present = set(dates)
    while cur <= end:
        if cur not in present:
            gaps.append(cur)
        cur += timedelta(days=1)
    return gaps


def assess_health(state, report_dates, checkpoint_age_hours,
                  resume_flag_present, max_age_hours=12.0,
                  error_rate_threshold=0.2):
    """
    评估守护进程运行健康。纯函数、无 I/O。

    参数：
        state:                检查点 dict；None 表示 state-file 缺失/解析失败
        report_dates:         日报日期列表（datetime.date）
        checkpoint_age_hours: 检查点 mtime 距今小时数；None 表示取不到
        resume_flag_present:  <state-file>.resume 是否存在
        max_age_hours:        新鲜度阈值（超过即 WARN）
        error_rate_threshold: exchange 模式下单错误率 WARN 阈值

    返回：(ok: bool, checks: list[{name,status,detail}])
          ok = 不含任何 FAIL。
    """
    checks = []

    if state is None:
        checks.append(_fail("检查点存在", "state-file 不存在或无法解析"))
        return False, checks
    day_count = state.get("day_count", 0)
    checks.append(_ok("检查点存在", f"day_count={day_count}, "
                                    f"last_bar_ts={state.get('last_bar_ts')}"))

    # 风控状态
    rk = state.get("risk", {})
    rstate = rk.get("state")
    extra = f"连亏{rk.get('consecutive_losses')}/API失败{rk.get('api_failures')}"
    if rstate == STOPPED:
        checks.append(_fail("风控状态", "STOPPED（紧急停止，需人工 reset）"))
    elif rstate == PAUSED:
        checks.append(_warn("风控状态", f"PAUSED（已熔断，等待人工 resume）；{extra}"))
    elif rstate == ACTIVE:
        checks.append(_ok("风控状态", f"ACTIVE；{extra}"))
    else:
        checks.append(_warn("风控状态", f"未知状态 {rstate!r}"))

    # 人工恢复标志
    if resume_flag_present:
        checks.append(_warn("人工恢复标志",
                            ".resume 存在（守护进程下一轮将自动恢复并删除）"))

    # 检查点新鲜度
    if checkpoint_age_hours is None:
        checks.append(_warn("检查点新鲜度", "无法获取 mtime"))
    elif checkpoint_age_hours > max_age_hours:
        checks.append(_warn("检查点新鲜度",
                            f"{checkpoint_age_hours:.1f}h 未更新"
                            f"（阈值 {max_age_hours:.0f}h，疑似守护进程已停）"))
    else:
        checks.append(_ok("检查点新鲜度",
                          f"{checkpoint_age_hours:.1f}h 内有更新"))

    # 日报数量对账（每次跨日写一份，份数应等于 day_count）
    n = len(report_dates)
    if n != day_count:
        checks.append(_fail("日报数量对账",
                            f"日报 {n} 份 ≠ day_count {day_count}（疑有缺失/多余）"))
    else:
        checks.append(_ok("日报数量对账", f"{n} 份 == day_count"))

    # 日报连续无缺口
    uniq = sorted(set(report_dates))
    gaps = _date_gaps(uniq)
    if gaps:
        shown = ", ".join(g.isoformat() for g in gaps[:5])
        more = "" if len(gaps) <= 5 else f" 等 {len(gaps)} 天"
        checks.append(_fail("日报连续无缺口", f"缺失日期: {shown}{more}"))
    elif n:
        checks.append(_ok("日报连续无缺口",
                          f"{uniq[0].isoformat()}..{uniq[-1].isoformat()} 共 {n} 份连续"))
    else:
        checks.append(_warn("日报连续无缺口", "暂无日报（尚未跨日）"))

    # exchange 模式特有：卡单 + 下单错误率（靠 broker 含 unconfirmed 键区分；
    # paper 形态无此键则跳过，向后兼容。持仓漂移已由 daemon 实时熔断→风控状态覆盖。）
    broker = state.get("broker", {})
    if isinstance(broker, dict) and "unconfirmed" in broker:
        stuck = broker.get("unconfirmed") or []
        if stuck:
            checks.append(_warn("卡单（未确认订单）",
                                f"{len(stuck)} 笔待确认订单，疑似卡单需人工处理"))
        else:
            checks.append(_ok("卡单（未确认订单）", "无未确认订单"))

        errors = broker.get("errors", 0)
        trades = len(broker.get("ledger", []))
        rate = errors / max(1, errors + trades)
        if rate > error_rate_threshold:
            checks.append(_warn("下单错误率",
                                f"{rate:.0%}（errors={errors}, fills={trades}）"
                                f"> 阈值 {error_rate_threshold:.0%}"))
        else:
            checks.append(_ok("下单错误率",
                              f"{rate:.0%}（errors={errors}, fills={trades}）"))

    ok = all(c["status"] != "FAIL" for c in checks)
    return ok, checks


# ------------------------------- CLI 输入采集 -------------------------------

def _collect_report_dates(report_dir):
    """从 daily_<sym>_<YYYY-MM-DD>.json 文件名解析日期。"""
    dates = []
    for f in Path(report_dir).glob("daily_*_*.json"):
        token = f.stem.rsplit("_", 1)[-1]
        try:
            dates.append(date.fromisoformat(token))
        except ValueError:
            continue
    return dates


def _checkpoint_age_hours(state_path):
    if not state_path.exists():
        return None
    mtime = datetime.fromtimestamp(state_path.stat().st_mtime)
    return (datetime.now() - mtime).total_seconds() / 3600.0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="守护进程运行健康巡检")
    p.add_argument("--state-file", default="data/paper_daemon_state.json")
    p.add_argument("--report-dir", default="data/reports/paper/daily")
    p.add_argument("--max-checkpoint-age-hours", type=float, default=12.0)
    p.add_argument("--max-order-error-rate", type=float, default=0.2,
                   help="exchange 模式下单错误率 WARN 阈值")
    args = p.parse_args(argv)

    state_path = Path(args.state_file)
    state = None
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = None

    report_dates = _collect_report_dates(args.report_dir)
    age = _checkpoint_age_hours(state_path)
    resume_present = Path(str(state_path) + ".resume").exists()

    ok, checks = assess_health(state, report_dates, age, resume_present,
                               max_age_hours=args.max_checkpoint_age_hours,
                               error_rate_threshold=args.max_order_error_rate)

    print("=" * 72)
    print("守护进程运行健康巡检")
    print("=" * 72)
    for c in checks:
        print(f"  [{c['status']}] {c['name']}")
        print(f"         {c['detail']}")
    warns = sum(1 for c in checks if c["status"] == "WARN")
    fails = sum(1 for c in checks if c["status"] == "FAIL")
    print("-" * 72)
    print(f"结论：{'健康' if ok else '存在 FAIL'}（WARN {warns} / FAIL {fails}）")
    print("=" * 72)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
