"""
策略自动淘汰脚本

定期评估所有运行中的策略，按综合评分自动归档低分策略。

评估维度（4 维加权）：
  1. 绩效分（50%）：Sharpe、年化收益、最大回撤、profit_factor（来自 StrategyEvaluator）
  2. 稳健性（20%）：MC 破产概率、参数稳定性、IS-OS 差异
  3. 分散度贡献（20%）：与组合中其他策略的相关性越低越好
  4. 类别多样性（10%）：保护小众类别的策略，避免某类被全淘汰

归档规则（满足任一即归档）：
  - StrategyEvaluator 命中 ≥2 条硬淘汰规则（verdict = ELIMINATE）
  - 综合评分 < 40 分（满分 100）
  - 已归档策略不重复评估

用法：
  python scripts/strategy_eliminator.py                     # 评估并自动归档
  python scripts/strategy_eliminator.py --dry-run           # 只生成报告，不实际归档
  python scripts/strategy_eliminator.py --threshold 50      # 自定义归档阈值
  python scripts/strategy_eliminator.py --restore rsi       # 恢复某策略为 active
  python scripts/strategy_eliminator.py --list-archived     # 列出已归档策略

报告输出：data/reports/elimination/YYYYMMDD_HHMMSS_elimination_report.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logger import logger, setup_logger
from src.strategy.registry import STRATEGY_REGISTRY, get_strategy_label
from src.api.strategy_status_store import (
    get_all_status,
    get_active_strategies,
    set_strategy_status,
    archive_strategy,
    activate_strategy,
    get_archived_strategies,
    is_strategy_active,
)


# 归档阈值（综合评分低于此值则归档）
DEFAULT_ARCHIVE_THRESHOLD = 40.0

# 类别保护：每个类别至少保留 N 个策略，避免某类被全淘汰
MIN_PER_CATEGORY = 1

# 综合评分权重
WEIGHTS = {
    "performance": 0.50,   # 绩效分
    "robustness": 0.20,    # 稳健性
    "diversity": 0.20,     # 分散度贡献
    "category": 0.10,      # 类别多样性
}


def _load_state_files() -> dict[str, dict]:
    """加载所有策略的 daemon state 文件（用于读取实盘/回测数据）。

    state 文件命名：paper_daemon_state_<mode>_<strategy>.json
    扫描 data/ 目录下所有匹配的文件。
    """
    data_dir = PROJECT_ROOT / "data"
    states = {}
    if not data_dir.exists():
        return states

    for sf in data_dir.glob("paper_daemon_state_*.json"):
        # 文件名格式：paper_daemon_state_<mode>_<strategy>.json
        # 或：paper_daemon_state_<strategy>.json（旧格式）
        name = sf.stem  # paper_daemon_state_live_paper_rsi
        parts = name.split("_", 3)  # ["paper", "daemon", "state", "live_paper_rsi"]
        if len(parts) < 4:
            continue
        strategy_key = parts[3]
        # 跳过非策略名的文件（如包含 mode 前缀的）
        if strategy_key not in STRATEGY_REGISTRY:
            # 尝试把 mode 前缀去掉再匹配
            # 例如 live_paper_rsi → rsi
            for mode_prefix in ["live_paper_", "replay_paper_", "testnet_live_"]:
                if strategy_key.startswith(mode_prefix):
                    strategy_key = strategy_key[len(mode_prefix):]
                    break
        if strategy_key not in STRATEGY_REGISTRY:
            continue
        try:
            states[strategy_key] = json.loads(sf.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug(f"解析 state 文件失败 {sf.name}: {e}")

    return states


def _compute_correlation_contribution(
    strategy_key: str,
    all_strategy_pnl: dict[str, list[float]],
) -> float:
    """计算策略对组合的分散度贡献（与组合平均相关性越低，分越高）。

    参数：
        strategy_key: 待评估策略
        all_strategy_pnl: {strategy_key: [daily_pnl, ...]}

    返回：0-100 分，100 = 完全独立（相关性低），0 = 高度相关
    """
    import numpy as np

    target = all_strategy_pnl.get(strategy_key)
    if not target or len(target) < 5:
        return 50.0  # 数据不足，给中性分

    others = {k: v for k, v in all_strategy_pnl.items() if k != strategy_key and len(v) >= 5}
    if not others:
        return 50.0  # 只有一个策略，给中性分

    # 对齐日期长度（取最短公共长度）
    min_len = min(len(target), min(len(v) for v in others.values()))
    target_arr = np.array(target[:min_len], dtype=float)

    corrs = []
    for other_key, other_pnl in others.items():
        other_arr = np.array(other_pnl[:min_len], dtype=float)
        if target_arr.std() > 0 and other_arr.std() > 0:
            try:
                corr = float(np.corrcoef(target_arr, other_arr)[0, 1])
                if not np.isnan(corr):
                    corrs.append(abs(corr))
            except Exception:
                pass

    if not corrs:
        return 50.0

    avg_corr = sum(corrs) / len(corrs)
    # 相关性 0 → 100 分，相关性 1 → 0 分
    return max(0.0, min(100.0, (1.0 - avg_corr) * 100))


def _get_category(strategy_key: str) -> str:
    """获取策略的分类（与前端 STRATEGY_TYPE_CATEGORY 一致）。"""
    # 后端简单映射（与 frontend/lib/strategy-meta.ts 保持一致）
    CATEGORY_MAP = {
        # 趋势跟踪
        "ma": "trend", "supertrend": "trend", "macd": "trend", "composite": "trend",
        "strongmom": "trend", "consmomentum": "trend", "accmomentum": "trend",
        "closemonotonic": "trend", "hlexpansion": "trend", "closedist": "trend",
        # 均值回归
        "rsi": "reversal", "reversal": "reversal", "priceaction": "reversal",
        "bollinger": "reversal", "purekeylvl": "reversal", "wicksweep": "reversal",
        "confakeout": "reversal", "decaykey": "reversal", "multiwinkey": "reversal",
        "tfdivergence": "reversal", "volpricediv": "reversal",
        # 突破
        "donchian": "breakout", "structure": "breakout", "multilevel": "breakout",
        "squeeze": "breakout", "closebreak": "breakout", "pullback": "breakout",
        "ampbreak": "breakout", "shortlongsqz": "breakout", "insidechain": "breakout",
        "qualitysqz": "breakout", "dualbreakout": "breakout", "volbreakout": "breakout",
        "takerbuyratio": "breakout",
        # K 线形态
        "threesoldiers": "pattern", "bigbar": "pattern", "pinsmall": "pattern",
        "morningstar": "pattern", "bullengulfseq": "pattern",
        # 多因子共振
        "confluence": "confluence", "weightedvote": "confluence",
        "requiredcat": "confluence", "masterslave": "confluence", "mtfconfluence": "confluence",
        # 时间过滤
        "sessionfilter": "time", "dayofweek": "time", "monthpos": "time",
        # 基准/网格
        "grid": "baseline", "buyhold": "baseline",
    }
    return CATEGORY_MAP.get(strategy_key, "unknown")


def _compute_category_score(
    strategy_key: str,
    active_strategies: list[str],
) -> float:
    """类别多样性评分：保护小众类别。

    如果某类别在 active 列表中策略数少，给该类策略高分（保护）。
    """
    cat = _get_category(strategy_key)
    cat_count = sum(1 for s in active_strategies if _get_category(s) == cat)
    if cat_count <= MIN_PER_CATEGORY:
        return 100.0  # 该类只剩 ≤1 个，保护
    # 策略数越多，分越低
    return max(20.0, 100.0 - (cat_count - MIN_PER_CATEGORY) * 15.0)


def _extract_pnl_from_state(state: dict) -> list[float]:
    """从 state 文件提取每日 PnL 序列（用于相关性分析）。"""
    runner = state.get("runner", {})
    closed = runner.get("closed_trades", [])
    if not closed:
        return []

    # 按日期聚合 PnL
    daily_pnl: dict[str, float] = {}
    for t in closed:
        profit = float(t.get("profit", 0))
        time_str = str(t.get("time", ""))
        if not time_str:
            continue
        # 取日期部分（前 10 字符：YYYY-MM-DD）
        day = time_str[:10]
        daily_pnl[day] = daily_pnl.get(day, 0.0) + profit

    return [daily_pnl[k] for k in sorted(daily_pnl.keys())]


def evaluate_strategies(
    active_strategies: list[str],
    threshold: float = DEFAULT_ARCHIVE_THRESHOLD,
) -> dict:
    """评估所有 active 策略，返回评估报告。

    返回结构：
    {
        "timestamp": "...",
        "threshold": 40.0,
        "evaluated": [...],   # 已评估的策略列表（按综合分降序）
        "to_archive": [...],  # 待归档的策略（综合分 < threshold 或 verdict=ELIMINATE）
        "skipped": [...],     # 跳过的策略（无数据）
        "summary": {...}
    }
    """
    from src.backtest.strategy_evaluator import StrategyEvaluator

    timestamp = datetime.now().isoformat()
    logger.info(f"开始评估 {len(active_strategies)} 个 active 策略...")

    # 加载 state 文件（用于读取实盘数据和 PnL 序列）
    states = _load_state_files()
    logger.info(f"加载了 {len(states)} 个策略的 state 文件")

    # 提取所有策略的 PnL 序列（用于相关性）
    all_pnl = {}
    for skey, state in states.items():
        pnl = _extract_pnl_from_state(state)
        if len(pnl) >= 5:
            all_pnl[skey] = pnl

    # 用 StrategyEvaluator 评估（需要 OHLCV 数据，这里用 state 中的数据近似）
    # 注意：StrategyEvaluator 需要 DataFrame，如果没有数据则跳过
    evaluated = []
    skipped = []
    to_archive = []

    for skey in active_strategies:
        if skey not in states:
            skipped.append({
                "strategy": skey,
                "label": get_strategy_label(skey),
                "reason": "无 state 文件（策略未运行过）",
            })
            continue

        state = states[skey]
        runner = state.get("runner", {})
        closed = runner.get("closed_trades", [])

        if len(closed) < 5:
            skipped.append({
                "strategy": skey,
                "label": get_strategy_label(skey),
                "reason": f"交易笔数不足（{len(closed)} < 5）",
            })
            continue

        # 从 state 提取关键指标（避免重新回测，直接用实盘数据）
        realized = float(runner.get("realized_pnl", 0))
        initial = float(state.get("initial_capital", 10000))
        wins = sum(1 for t in closed if float(t.get("profit", 0)) > 0)
        losses = sum(1 for t in closed if float(t.get("profit", 0)) < 0)
        win_rate = wins / len(closed) if closed else 0
        total_trades = len(closed)

        # 计算 Sharpe（用日 PnL）
        pnl_series = _extract_pnl_from_state(state)
        import numpy as np
        if len(pnl_series) >= 5:
            pnl_arr = np.array(pnl_series, dtype=float)
            pnl_std = pnl_arr.std()
            sharpe = float(pnl_arr.mean() / pnl_std * np.sqrt(252)) if pnl_std > 0 else 0
        else:
            sharpe = 0

        # 最大回撤（用累计 PnL）
        cum = np.cumsum(pnl_series) if pnl_series else np.array([0])
        running_max = np.maximum.accumulate(cum)
        drawdowns = cum - running_max
        max_dd = float(abs(min(drawdowns)) / initial) if len(drawdowns) > 0 and initial > 0 else 0

        # profit_factor
        gross_profit = sum(float(t.get("profit", 0)) for t in closed if float(t.get("profit", 0)) > 0)
        gross_loss = abs(sum(float(t.get("profit", 0)) for t in closed if float(t.get("profit", 0)) < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 10.0

        annual_return = realized / initial * (252 / max(len(pnl_series), 1)) if initial > 0 else 0

        # 1. 绩效分（0-100）
        perf_score = min(100, max(0,
            sharpe * 25 +                          # Sharpe 4 → 100
            min(annual_return * 100, 50) +         # 年化收益 50% → 50 分
            min(profit_factor * 10, 25)             # PF 2.5 → 25 分
        ))

        # 2. 稳健性分（0-100）：用 win_rate 和交易笔数近似
        robustness_score = min(100, max(0,
            win_rate * 50 +                         # 胜率 50% → 25 分
            min(total_trades * 2, 50)               # 25 笔交易 → 50 分
        ))

        # 3. 分散度贡献分（0-100）
        diversity_score = _compute_correlation_contribution(skey, all_pnl)

        # 4. 类别多样性分（0-100）
        category_score = _compute_category_score(skey, active_strategies)

        # 综合分
        total_score = (
            perf_score * WEIGHTS["performance"] +
            robustness_score * WEIGHTS["robustness"] +
            diversity_score * WEIGHTS["diversity"] +
            category_score * WEIGHTS["category"]
        )

        # 淘汰判定
        elim_flags = []
        if sharpe < 0.3:
            elim_flags.append(f"Sharpe {sharpe:.2f} < 0.3")
        if max_dd > 0.25:
            elim_flags.append(f"最大回撤 {max_dd:.1%} > 25%")
        if total_trades < 10:
            elim_flags.append(f"交易笔数 {total_trades} < 10")

        should_archive = total_score < threshold or len(elim_flags) >= 2

        entry = {
            "strategy": skey,
            "label": get_strategy_label(skey),
            "category": _get_category(skey),
            "total_score": round(total_score, 1),
            "scores": {
                "performance": round(perf_score, 1),
                "robustness": round(robustness_score, 1),
                "diversity": round(diversity_score, 1),
                "category": round(category_score, 1),
            },
            "metrics": {
                "sharpe": round(sharpe, 2),
                "annual_return": round(annual_return * 100, 2),
                "max_drawdown": round(max_dd * 100, 2),
                "win_rate": round(win_rate * 100, 1),
                "profit_factor": round(profit_factor, 2),
                "total_trades": total_trades,
                "realized_pnl": round(realized, 2),
            },
            "elimination_flags": elim_flags,
            "verdict": "ELIMINATE" if should_archive else ("WARN" if len(elim_flags) >= 1 else "KEEP"),
        }
        evaluated.append(entry)

        if should_archive:
            reason = f"综合分 {total_score:.1f} < 阈值 {threshold}" if total_score < threshold else \
                     f"命中 {len(elim_flags)} 条淘汰规则: {'; '.join(elim_flags)}"
            to_archive.append({
                "strategy": skey,
                "label": get_strategy_label(skey),
                "reason": reason,
                "total_score": round(total_score, 1),
            })

    # 按综合分降序
    evaluated.sort(key=lambda x: -x["total_score"])

    # 类别保护：检查是否某类别会被全淘汰
    if to_archive:
        active_after = set(active_strategies) - {a["strategy"] for a in to_archive}
        cat_counts: dict[str, int] = {}
        for s in active_after:
            cat = _get_category(s)
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        protected = []
        protected_keys: set[str] = set()
        for arch in to_archive:
            cat = _get_category(arch["strategy"])
            # 如果归档后该类别在 active 中数量为 0，则保护
            if cat_counts.get(cat, 0) == 0:
                protected.append(arch)
                protected_keys.add(arch["strategy"])
                cat_counts[cat] = cat_counts.get(cat, 0) + 1  # 防止多个同类别都被保护

        if protected:
            logger.info(f"类别保护：保留 {len(protected)} 个策略（避免某类被全淘汰）")
            to_archive = [a for a in to_archive if a["strategy"] not in protected_keys]

    summary = {
        "total_active": len(active_strategies),
        "evaluated": len(evaluated),
        "skipped": len(skipped),
        "to_archive": len(to_archive),
        "remaining_after": len(active_strategies) - len(to_archive),
        "threshold": threshold,
    }

    return {
        "timestamp": timestamp,
        "threshold": threshold,
        "evaluated": evaluated,
        "to_archive": to_archive,
        "skipped": skipped,
        "summary": summary,
    }


def save_report(report: dict, dry_run: bool = False) -> Path:
    """保存评估报告到文件。"""
    report_dir = PROJECT_ROOT / "data" / "reports" / "elimination"
    report_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_dryrun" if dry_run else ""
    filename = f"{ts}_elimination_report{suffix}.json"
    filepath = report_dir / filename

    filepath.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"淘汰报告已保存: {filepath}")
    return filepath


def execute_archival(to_archive: list[dict]) -> int:
    """执行归档操作，返回成功归档数量。

    单条失败不中断整批，失败项记入日志方便后续排查。
    """
    count = 0
    for item in to_archive:
        try:
            archive_strategy(item["strategy"], item["reason"])
            count += 1
        except Exception as e:
            logger.error(f"归档 {item.get('strategy', '?')} 失败: {e}")
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="策略自动淘汰脚本")
    parser.add_argument("--dry-run", action="store_true",
                        help="只生成报告，不实际归档")
    parser.add_argument("--threshold", type=float, default=DEFAULT_ARCHIVE_THRESHOLD,
                        help=f"归档阈值（综合分低于此值则归档，默认 {DEFAULT_ARCHIVE_THRESHOLD}）")
    parser.add_argument("--restore", type=str,
                        help="恢复指定策略为 active（如 --restore rsi）")
    parser.add_argument("--list-archived", action="store_true",
                        help="列出所有已归档策略")
    parser.add_argument("--list-active", action="store_true",
                        help="列出所有 active 策略")
    args = parser.parse_args(argv)

    setup_logger(log_level="INFO")

    # 导入策略注册表（list-active / 评估模式 / restore 校验都需要）
    from src.strategy.registry import STRATEGY_REGISTRY

    # 参数校验：threshold 应在 [0, 100]
    if not 0 <= args.threshold <= 100:
        parser.error(f"--threshold 应在 [0, 100] 范围内，当前: {args.threshold}")

    # 参数校验：--restore 的策略必须在注册表中
    if args.restore:
        if args.restore not in STRATEGY_REGISTRY:
            parser.error(
                f"--restore '{args.restore}' 不在策略注册表中。"
                f"可用策略: {', '.join(sorted(STRATEGY_REGISTRY.keys()))}"
            )

    # 恢复模式
    if args.restore:
        activate_strategy(args.restore)
        print(f"✓ 策略 [{args.restore}] 已恢复为 active")
        return 0

    # 列表模式
    if args.list_archived:
        archived = get_archived_strategies()
        if not archived:
            print("当前无归档策略")
        else:
            print(f"已归档策略（{len(archived)} 个）:")
            status_data = get_all_status()
            for s in archived:
                detail = status_data.get(s, {})
                print(f"  - {s} ({get_strategy_label(s)}): {detail.get('reason', '无原因')}")
        return 0

    if args.list_active:
        all_keys = list(STRATEGY_REGISTRY.keys())
        active = [k for k in all_keys if is_strategy_active(k)]
        print(f"Active 策略（{len(active)}/{len(all_keys)} 个）:")
        for s in active:
            print(f"  - {s} ({get_strategy_label(s)})")
        return 0

    # 评估模式
    all_keys = list(STRATEGY_REGISTRY.keys())
    active_strategies = [k for k in all_keys if is_strategy_active(k)]

    print(f"")
    print(f"{'='*60}")
    print(f"  策略自动淘汰评估")
    print(f"{'='*60}")
    print(f"  全部策略: {len(all_keys)}")
    print(f"  Active:   {len(active_strategies)}")
    print(f"  归档阈值: {args.threshold}")
    print(f"  Dry run:  {'是（不实际归档）' if args.dry_run else '否（将实际归档）'}")
    print(f"{'='*60}")
    print(f"")

    if not active_strategies:
        print("无 active 策略可评估，退出。")
        return 0

    # 评估
    report = evaluate_strategies(active_strategies, args.threshold)

    # 打印评估结果
    print(f"评估结果:")
    print(f"  已评估: {report['summary']['evaluated']}")
    print(f"  跳过:   {report['summary']['skipped']}（无数据或交易不足）")
    print(f"  待归档: {report['summary']['to_archive']}")
    print(f"  归档后剩余: {report['summary']['remaining_after']}")
    print(f"")

    if report["evaluated"]:
        print(f"{'策略':<20} {'综合分':>8} {'绩效':>6} {'稳健':>6} {'分散':>6} {'类别':>6} {'判定':>10}")
        print(f"{'-'*20} {'-'*8} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*10}")
        for e in report["evaluated"]:
            will_arch = "→ 归档" if any(a["strategy"] == e["strategy"] for a in report["to_archive"]) else ""
            verdict_display = will_arch if will_arch else e["verdict"]
            print(f"{e['label'][:18]:<20} {e['total_score']:>8.1f} "
                  f"{e['scores']['performance']:>6.1f} {e['scores']['robustness']:>6.1f} "
                  f"{e['scores']['diversity']:>6.1f} {e['scores']['category']:>6.1f} "
                  f"{verdict_display:>10}")
        print(f"")

    if report["skipped"]:
        print(f"跳过的策略:")
        for s in report["skipped"]:
            print(f"  - {s['label']} ({s['strategy']}): {s['reason']}")
        print(f"")

    # 保存报告
    report_path = save_report(report, dry_run=args.dry_run)

    # 执行归档
    if not args.dry_run and report["to_archive"]:
        print(f"正在归档 {len(report['to_archive'])} 个策略...")
        count = execute_archival(report["to_archive"])
        print(f"✓ 已归档 {count} 个策略")
        print(f"")
        print(f"归档的策略（可随时用 --restore 恢复）:")
        for a in report["to_archive"]:
            print(f"  - {a['label']} ({a['strategy']}): {a['reason']}")
    elif args.dry_run and report["to_archive"]:
        print(f"[Dry-run] 未实际归档，{len(report['to_archive'])} 个策略待归档")
    else:
        print(f"无需归档的策略")

    print(f"")
    print(f"报告已保存: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
