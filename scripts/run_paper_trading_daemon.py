#!/usr/bin/env python3
"""
Paper Trading 连续运行守护进程（LIVE_TRADING_CHECKLIST §1）

把单次批量回测升级为可连续运行 N 天（默认 60）的模拟盘：每根 bar 收盘 →
取数 → 跑网格策略 → PaperBroker 成交 → 风控 → 落库 → 跨日出日报；崩溃/重启
可凭状态检查点续跑（不丢进度、不重复成交）。

双模：
  实时（默认）：每根 4h bar 收盘从 Binance 拉真实 OHLCV，真连续运行。
  回放（--replay）：历史/生成数据加速跑完，用于验证/演练。

用法：
  python scripts/run_paper_trading_daemon.py --replay generate --days 5
  python scripts/run_paper_trading_daemon.py --days 60          # 实时
  人工恢复（风控暂停后）：创建文件 <state-file>.resume

不下真实订单（仍 PaperBroker 模拟）；真实交易=Live Broker，Phase 7+。
"""

import argparse
import glob
import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.execution import PaperBroker, PaperTradingRunner, RiskManager
from src.execution.paper_report import PaperTradingReportGenerator
from src.monitor import MetricsCollector, MetricsWriter
from src.strategy.base import Order as StrategyOrder
from src.strategy.grid_trading import GridTradingStrategy
from src.utils.logger import logger, setup_logger

WARMUP = 30  # 预热 bar 数：定网格区间 + 喂指标，不作为交易 bar


# ----------------------------- pending 信号序列化 -----------------------------

def _ser_pending(p):
    if p is None:
        return None
    if isinstance(p, str):
        return {"k": "s", "v": p}
    if isinstance(p, list):
        return {"k": "o", "v": [{"side": o.side, "tag": o.tag,
                                 "fraction": o.fraction} for o in p]}
    return None


def _deser_pending(d):
    if not d:
        return None
    if d["k"] == "s":
        return d["v"]
    return [StrategyOrder(side=x["side"], tag=x["tag"], fraction=x["fraction"])
            for x in d["v"]]


# --------------------------------- 守护进程 ---------------------------------

class PaperTradingDaemon:
    def __init__(self, args):
        self.args = args
        self.symbol = args.symbol
        self.state_file = Path(args.state_file)
        self.resume_flag = Path(str(self.state_file) + ".resume")
        self.daily_dir = Path(args.report_dir)
        self.daily_dir.mkdir(parents=True, exist_ok=True)

        self.strategy = None
        self.broker = None
        self.runner = None
        self.risk = None
        self.collector = MetricsCollector()
        self.writer = None

        self.pending = None
        self.day_count = 0
        self.current_day = None
        self.last_bar_ts = None

    # ---- 组件装配（区间来自预热窗口；与 run_paper_trading 一致）----
    def _build(self, lower, upper):
        initial = self.args.initial
        self.strategy = GridTradingStrategy(
            lower_price=lower, upper_price=upper, grid_count=10,
            initial_capital=initial,
        )
        self.broker = PaperBroker(
            initial, commission=0.001, slippage={self.symbol: 0.0005},
            max_position_per_trade=1.0, max_total_position=1.0,
        )
        self.risk = RiskManager(capital_base=initial)
        # runner 持有 risk → process_bar 内 _execute_signal 自动按 can_trade() 门控
        self.runner = PaperTradingRunner(
            self.broker, self.symbol, risk_manager=self.risk,
            metrics_collector=self.collector,
        )

    # ---- 数据源 ----
    def _load_replay_df(self):
        src = self.args.replay
        if src == "generate" or not src:
            sys.path.insert(0, str(project_root))
            from scripts.generate_oscillating_data import generate_oscillating_ohlcv
            df = generate_oscillating_ohlcv()
        else:
            df = pd.read_csv(src)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df.reset_index(drop=True)

    def _fetch_live_df(self):
        from src.data.exchange import create_binance_client
        client = create_binance_client(testnet=False)  # 主网公共行情=真实价格
        df = client.fetch_ohlcv(self.symbol, self.args.timeframe,
                                limit=max(WARMUP + 5, 200))
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        # 丢掉仍在形成中的最后一根（只用已收盘 bar）
        return df.iloc[:-1].reset_index(drop=True)

    # ---- 状态检查点 ----
    def _checkpoint(self):
        st = {
            "version": 1, "symbol": self.symbol,
            "day_count": self.day_count,
            "current_day": self.current_day.isoformat() if self.current_day else None,
            "last_bar_ts": self.last_bar_ts,
            "bounds": {"lower": self.strategy.lower_price,
                       "upper": self.strategy.upper_price},
            "broker": {
                "balance": self.broker.balance,
                "positions": self.broker.positions,
                "orders": self.broker.orders,
                "order_id_counter": self.broker.order_id_counter,
            },
            "runner": {
                "lots": {str(k): v for k, v in self.runner.lots.items()},
                "realized_pnl": self.runner.realized_pnl,
                "closed_trades": self.runner.closed_trades,
            },
            "strategy": {
                "grid_filled": self.strategy.grid_filled,
                "paused": self.strategy.paused,
                "consecutive_losses": self.strategy.consecutive_losses,
                "daily_pnl": self.strategy.daily_pnl,
            },
            "risk": {
                "state": self.risk.state,
                "daily_pnl": self.risk.daily_pnl,
                "consecutive_losses": self.risk.consecutive_losses,
                "api_failures": self.risk.api_failures,
            },
            "pending": _ser_pending(self.pending),
        }
        tmp = Path(str(self.state_file) + ".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False, default=str),
                       encoding="utf-8")
        tmp.replace(self.state_file)  # 原子替换，防写一半崩溃

    def _restore(self):
        st = json.loads(self.state_file.read_text(encoding="utf-8"))
        self._build(st["bounds"]["lower"], st["bounds"]["upper"])
        self.day_count = st["day_count"]
        self.current_day = date.fromisoformat(st["current_day"]) if st["current_day"] else None
        self.last_bar_ts = st["last_bar_ts"]

        b = st["broker"]
        self.broker.balance = b["balance"]
        self.broker.positions = b["positions"]
        self.broker.orders = b["orders"]
        self.broker.order_id_counter = b["order_id_counter"]

        r = st["runner"]
        self.runner.lots = {
            (int(k) if k.lstrip("-").isdigit() else k): v
            for k, v in r["lots"].items()
        }
        self.runner.realized_pnl = r["realized_pnl"]
        self.runner.closed_trades = r["closed_trades"]

        s = st["strategy"]
        self.strategy.grid_filled = s["grid_filled"]
        self.strategy.paused = s["paused"]
        self.strategy.consecutive_losses = s["consecutive_losses"]
        self.strategy.daily_pnl = s["daily_pnl"]

        rk = st["risk"]
        self.risk.state = rk["state"]
        self.risk.daily_pnl = rk["daily_pnl"]
        self.risk.consecutive_losses = rk["consecutive_losses"]
        self.risk.api_failures = rk["api_failures"]

        self.pending = _deser_pending(st["pending"])
        logger.info(f"恢复检查点：day_count={self.day_count}, "
                    f"last_bar_ts={self.last_bar_ts}, state={self.risk.state}")

    # ---- 人工恢复 ----
    def _check_resume(self):
        if self.resume_flag.exists() and (self.risk.is_paused() or self.strategy.paused):
            self.risk.resume()
            # 策略级熔断也一并人工解除（grid 有独立 paused 标志）
            self.strategy.paused = False
            self.strategy.consecutive_losses = 0
            self.resume_flag.unlink(missing_ok=True)
            logger.warning("检测到 resume 标志，风控/策略已人工恢复 -> ACTIVE")

    # ---- 日报 ----
    def _write_daily_report(self, day, last_close):
        result = self.runner._build_result([])
        gen = PaperTradingReportGenerator(report_dir=str(self.daily_dir))
        report = gen.build_report(result, {self.symbol: last_close})
        sym = self.symbol.replace("/", "_")
        (self.daily_dir / f"daily_{sym}_{day.isoformat()}.json").write_text(
            json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")
        (self.daily_dir / f"daily_{sym}_{day.isoformat()}.md").write_text(
            gen.render_markdown(report), encoding="utf-8")
        logger.info(f"日报已出：{day.isoformat()} (第 {self.day_count + 1} 天)")

    # ---- 单 bar 处理 ----
    def _on_bar(self, bar):
        self._check_resume()
        before = len(self.runner.closed_trades)
        # historical：截至本 bar 的全部已见数据
        self.pending = self.runner.process_bar(
            bar, self._history.loc[: bar.name], self.strategy, self.pending
        )
        for t in self.runner.closed_trades[before:]:
            self.risk.record_fill(t)

        day = pd.Timestamp(bar["timestamp"]).date()
        if self.current_day is None:
            self.current_day = day
        elif day != self.current_day:
            self._write_daily_report(self.current_day, float(bar["close"]))
            self.day_count += 1
            self.current_day = day

        self.last_bar_ts = str(bar["timestamp"])
        if self.writer is not None:
            try:
                self.writer.write_collector(self.collector)
                self.collector.snapshots.clear()  # 已落库的清掉，避免重复写
            except Exception as e:
                logger.debug(f"落库跳过（DB 不可用）：{type(e).__name__}")
        self._checkpoint()

    # ---- 主循环 ----
    def run(self):
        resuming = self.state_file.exists() and not self.args.fresh
        if resuming:
            self._restore()
        if not self.args.no_db:
            try:
                self.writer = MetricsWriter()
            except Exception:
                self.writer = None

        if self.args.replay:
            return self._run_replay(resuming)
        return self._run_live(resuming)

    def _run_replay(self, resuming):
        df = self._load_replay_df()
        if not resuming:
            warm = df.iloc[:WARMUP]
            lo, hi = warm["low"].min(), warm["high"].max()
            span = hi - lo
            self._build(lo + span * 0.1, hi - span * 0.1)
        self._history = df
        start = WARMUP
        if resuming and self.last_bar_ts is not None:
            after = df.index[df["timestamp"] > pd.Timestamp(self.last_bar_ts)]
            start = int(after[0]) if len(after) else len(df)

        print(f"[replay] bars {start}..{len(df)-1}, 目标 {self.args.days} 天")
        for i in range(start, len(df)):
            self._on_bar(df.iloc[i])
            if self.day_count >= self.args.days:
                break
        return self._finish()

    def _run_live(self, resuming):
        if not resuming:
            seed = self._fetch_live_df()
            warm = seed.iloc[:WARMUP]
            lo, hi = warm["low"].min(), warm["high"].max()
            span = hi - lo
            self._build(lo + span * 0.1, hi - span * 0.1)
            self._history = seed
        else:
            self._history = self._fetch_live_df()

        print(f"[live] {self.symbol} {self.args.timeframe}，目标 {self.args.days} 天，"
              f"轮询 {self.args.poll_seconds}s（Ctrl+C 停止，可重启续跑）")
        # 处理 seed 中尚未处理的已收盘 bar
        self._consume_new_bars()
        while self.day_count < self.args.days:
            time.sleep(self.args.poll_seconds)
            try:
                self._history = self._fetch_live_df()
            except Exception as e:
                self.risk.record_api_failure(str(e))
                logger.warning(f"取数失败（计入 API 失败）：{type(e).__name__}: {e}")
                continue
            self.risk.record_api_success()
            self._consume_new_bars()
        return self._finish()

    def _consume_new_bars(self):
        last = pd.Timestamp(self.last_bar_ts) if self.last_bar_ts else None
        for i in range(len(self._history)):
            bar = self._history.iloc[i]
            if last is not None and pd.Timestamp(bar["timestamp"]) <= last:
                continue
            if i < WARMUP and last is None:
                continue  # 预热段不交易
            self._on_bar(bar)
            last = pd.Timestamp(bar["timestamp"])
            if self.day_count >= self.args.days:
                break

    def _finish(self):
        print(f"完成：累计 {self.day_count} 天日报，检查点 {self.state_file}")
        return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Paper Trading 连续运行守护进程")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="4h")
    p.add_argument("--initial", type=float, default=10000.0)
    p.add_argument("--replay", nargs="?", const="generate", default=None,
                   help="回放模式；可选 CSV 路径，缺省用 generate 生成数据")
    p.add_argument("--state-file", default="data/paper_daemon_state.json")
    p.add_argument("--report-dir", default="data/reports/paper/daily")
    p.add_argument("--poll-seconds", type=int, default=60)
    p.add_argument("--fresh", action="store_true", help="忽略旧检查点重开")
    p.add_argument("--no-db", action="store_true", help="不落库")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logger(log_level="WARNING")
    return PaperTradingDaemon(args).run()


if __name__ == "__main__":
    sys.exit(main())
