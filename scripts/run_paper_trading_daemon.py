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
  python scripts/run_paper_trading_daemon.py --days 60          # 实时（paper 模拟）
  python scripts/run_paper_trading_daemon.py --broker exchange --timeframe 1m --days 1
                                                               # testnet 真实下单
  人工恢复（风控暂停后）：创建文件 <state-file>.resume

--broker paper（默认）：PaperBroker 模拟，崩溃续跑逐位一致。
--broker exchange：Binance testnet 真实市价单（Phase 7 Stage 3），硬护栏强制 testnet；
  成交价量真实、每 bar 对账持仓漂移→熔断；**非逐位一致**。真实主网=Live Broker，Phase 7+。
"""

import argparse
import glob
import json
import signal
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.execution import PaperBroker, PaperTradingRunner, RiskManager
from src.execution.exchange_broker import ExchangeBroker
from src.execution.exchange_execution import ExchangeExecutor
from src.execution.exchange_runner_broker import (
    ExchangeRunnerBroker, assess_position_drift,
)
from src.execution.order_guard import OrderRateGuard
from src.execution.paper_report import PaperTradingReportGenerator
from src.execution.paper_trading_runner import ExecutionConfig
from src.monitor import MetricsCollector, MetricsWriter
from src.monitor.alert_manager import AlertManager, CRITICAL, WARNING
from src.monitor.alert_channels import TelegramChannel
from src.monitor.alert_hub import get_alert_manager
from src.strategy.base import Order as StrategyOrder
from src.strategy.grid_trading import GridTradingStrategy
from src.api.strategy_config_store import get_strategy_config
from src.risk.portfolio_heat import PortfolioHeatManager
from src.utils.logger import logger, setup_logger
from src.utils.telegram_notifier import notifier

WARMUP = 30  # 预热 bar 数：定网格区间 + 喂指标，不作为交易 bar


# ----------------------------- pending 信号序列化 -----------------------------

def _ser_pending(p):
    if p is None:
        return None
    if isinstance(p, str):
        return {"k": "s", "v": p}
    if isinstance(p, list):
        return {"k": "o", "v": [{"side": o.side, "tag": o.tag,
                                 "fraction": o.fraction,
                                 "limit_price": getattr(o, 'limit_price', None)} for o in p]}
    return None


def _deser_pending(d):
    if not d:
        return None
    if d["k"] == "s":
        return d["v"]
    return [StrategyOrder(side=x["side"], tag=x["tag"], fraction=x["fraction"],
                          limit_price=x.get("limit_price"))
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
        self.portfolio_heat = None  # PortfolioHeatManager（跨策略热力协调）
        self.collector = MetricsCollector()
        self.writer = None
        self.alert_mgr = get_alert_manager()  # 共享单例（Telegram + 可选 Webhook）

        self.pending = None
        self.day_count = 0
        self.current_day = None
        self.last_bar_ts = None

        # 对账失败独立计数器——不与 risk.api_failures 共享，避免被
        # _run_live 主循环的 record_api_success() 重置而永远无法累积到阈值
        self._reconcile_failures = 0
        self._max_reconcile_failures = 3
        self._prev_close = None  # 前一根收盘价（闪崩保护用）

    # ---- 组件装配（区间来自预热窗口；与 run_paper_trading 一致）----
    def _build(self, lower, upper):
        from src.utils.config import config as _cfg
        from src.strategy.registry import get_strategy
        initial = self.args.initial
        # self.args.strategy 可能是 list（argparse action="append"）或 str（main 循环中赋值）
        strat_name = self.args.strategy
        if isinstance(strat_name, list):
            strat_name = strat_name[0] if strat_name else "grid"

        # 从持久化配置加载已保存的参数
        saved = get_strategy_config(strat_name) or {}
        _log_saved = f" (已加载保存配置: {saved})" if saved else ""

        if strat_name == "grid":
            # grid 也从 saved 配置加载参数（grid_count / position_per_grid / enable_filters）
            grid_kwargs = dict(
                lower_price=lower, upper_price=upper, grid_count=10,
                initial_capital=initial,
                max_consecutive_losses=_cfg.MAX_CONSECUTIVE_LOSSES,
                max_daily_loss=_cfg.MAX_DAILY_LOSS,
            )
            grid_schema = getattr(GridTradingStrategy, "PARAM_SCHEMA", {})
            for k, v in saved.items():
                if k in grid_schema:
                    grid_kwargs[k] = v
            self.strategy = GridTradingStrategy(**grid_kwargs)
        else:
            # 用保存的参数覆写默认值
            kwargs = dict(initial_capital=initial,
                          max_consecutive_losses=_cfg.MAX_CONSECUTIVE_LOSSES,
                          max_daily_loss=_cfg.MAX_DAILY_LOSS)
            # 只传策略模式中存在的参数
            schema = getattr(get_strategy(strat_name), "PARAM_SCHEMA", {})
            for k, v in saved.items():
                if k in schema:
                    kwargs[k] = v
            # 回放模式：强制关闭趋势过滤等限制性过滤器
            # 模拟数据无明显趋势，趋势过滤会阻止 RSI 超卖买入等信号
            if getattr(self.args, "replay", None):
                if "enable_trend_filter" in schema:
                    kwargs["enable_trend_filter"] = False
            # 只传策略 __init__ 实际接受的参数（如 BuyAndHold 不接受 initial_capital）
            import inspect
            sig_params = set(inspect.signature(get_strategy(strat_name).__init__).parameters.keys())
            sig_params.discard("self")
            kwargs = {k: v for k, v in kwargs.items() if k in sig_params}
            self.strategy = get_strategy(strat_name)(**kwargs)
        logger.info(f"策略 [{strat_name}] 已构建{_log_saved}")
        # P0-2: 风控参数从 .env / config.py 读取，而非硬编码默认值
        self.risk = RiskManager(
            capital_base=initial,
            max_daily_loss=_cfg.MAX_DAILY_LOSS,
            max_consecutive_losses=_cfg.MAX_CONSECUTIVE_LOSSES,
            max_total_position=_cfg.MAX_TOTAL_POSITION,
            max_total_drawdown=_cfg.MAX_TOTAL_DRAWDOWN,
            max_api_failures=_cfg.MAX_API_FAILURES,
        )
        if self.args.broker == "exchange":
            self.broker, exec_config = self._build_exchange_broker()
        else:
            # P0-3: 仓位限制从 config 读取，不再设为 100%
            # 回放模式放宽仓位限制：模拟验证策略逻辑，不受实盘仓位管控约束
            if getattr(self.args, "replay", None):
                max_per_trade = 1.0
                max_total = 1.0
            else:
                max_per_trade = _cfg.MAX_POSITION_SIZE
                max_total = _cfg.MAX_TOTAL_POSITION
            self.broker = PaperBroker(
                initial, commission=0.001, slippage={self.symbol: 0.0005},
                max_position_per_trade=max_per_trade,
                max_total_position=max_total,
            )
            exec_config = None  # None → runner 从 PaperBroker 快照（行为不变）
        # runner 持有 risk → process_bar 内 _execute_signal 自动按 can_trade() 门控
        self.runner = PaperTradingRunner(
            self.broker, self.symbol, risk_manager=self.risk,
            metrics_collector=self.collector, exec_config=exec_config,
        )

        # Portfolio Heat：跨策略风险敞口协调（共享文件 data/portfolio_heat.json）
        self.portfolio_heat = PortfolioHeatManager(
            strategy_name=strat_name,
            state_dir=str(project_root / "data"),
        )
        logger.info(f"PortfolioHeat 已初始化: strategy={strat_name}")

    def _build_exchange_broker(self):
        """构造 testnet 交易所适配链；硬护栏：仅允许 testnet，否则拒启（绝不碰主网）。"""
        from src.utils.config import config
        if not config.BINANCE_TESTNET:
            raise SystemExit(
                "exchange 模式仅允许 testnet：请设 BINANCE_TESTNET=true（拒绝碰主网）")
        if not config.BINANCE_API_KEY or not config.BINANCE_SECRET:
            raise SystemExit(
                "exchange 模式需配 BINANCE_API_KEY / BINANCE_SECRET（在 .env 填 testnet key）")
        exchange_broker = self._make_exchange_broker()
        executor = ExchangeExecutor(exchange_broker)
        adapter = ExchangeRunnerBroker(executor, self.symbol, commission=0.001)
        adapter.guard = OrderRateGuard(
            reference_capital=adapter.initial_balance,
            max_position_per_trade=self.args.max_position_per_trade,
            min_trade_interval=self.args.min_trade_interval,
            max_trades_per_day=self.args.max_trades_per_day,
        )
        exec_config = ExecutionConfig(
            commission=0.001, slippage={self.symbol: 0.0},
            initial_balance=adapter.initial_balance,
        )
        logger.warning(f"exchange 模式（testnet）：起始余额 {adapter.initial_balance} "
                       f"USDT，底仓 {adapter.initial_position} {self.symbol.split('/')[0]}")
        return adapter, exec_config

    def _make_exchange_broker(self):
        """构造 ExchangeBroker（注入缝：测试 monkeypatch 成 FakeExchange 后端）。"""
        from src.utils.config import config
        return ExchangeBroker(
            api_key=config.BINANCE_API_KEY, secret=config.BINANCE_SECRET, testnet=True)

    # ---- 数据源 ----
    def _load_replay_df(self):
        src = self.args.replay
        if src == "generate" or not src:
            sys.path.insert(0, str(project_root))
            market_type = getattr(self.args, "market_type", "oscillating") or "oscillating"
            from scripts.generate_mock_data import generate_mock_ohlcv
            from datetime import datetime, timedelta
            end = datetime.now()
            # 使用用户指定的天数，而非硬编码 30 天
            days = max(1, int(self.args.days or 30))
            start = end - timedelta(days=days)
            df = generate_mock_ohlcv(
                start_date=start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
                timeframe=self.args.timeframe or "4h",
                initial_price=50000.0,
                market_type=market_type,
            )
        else:
            df = pd.read_csv(src)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df.reset_index(drop=True)

    def _fetch_live_df(self):
        from src.data.exchange import create_binance_client
        # 主网公共行情=真实价格；public=True 不带凭据（公开数据无需签名，
        # 且 .env 配的是 testnet key，传给主网会被拒 -2008）。
        client = create_binance_client(testnet=False, public=True)
        df = client.fetch_ohlcv(self.symbol, self.args.timeframe,
                                limit=max(WARMUP + 5, 200))
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        # 丢掉仍在形成中的最后一根（只用已收盘 bar）
        return df.iloc[:-1].reset_index(drop=True)

    # ---- 状态检查点 ----
    def _checkpoint(self, path=None):
        # exchange 模式 broker 无本地余额/持仓/订单，存适配器账本（注释：非逐位一致）；
        # paper 分支字节级保持原样。
        if self.args.broker == "exchange":
            broker_state = self.broker.state_dict()
        else:
            broker_state = {
                "balance": self.broker.balance,
                "positions": self.broker.positions,
                # P1-5: 只保存最近 N 条 + 增量统计
                "orders": self.broker.orders[-self.broker.MAX_ORDERS:],
                "order_id_counter": self.broker.order_id_counter,
                "_total_commission": self.broker._total_commission,
                "_total_slippage": self.broker._total_slippage,
                "_archived_order_count": self.broker._archived_order_count,
            }
        _sn = self.args.strategy
        _sn = _sn[0] if isinstance(_sn, list) and _sn else (_sn if isinstance(_sn, str) else "grid")
        st = {
            "version": 1, "symbol": self.symbol,
            "strategy_name": _sn,
            "initial_capital": self.args.initial,
            "day_count": self.day_count,
            "current_day": self.current_day.isoformat() if self.current_day else None,
            "last_bar_ts": self.last_bar_ts,
            "bounds": {"lower": getattr(self.strategy, 'lower_price', 0.0),
                       "upper": getattr(self.strategy, 'upper_price', 0.0)},
            "broker": broker_state,
            "runner": {
                "lots": {str(k): v for k, v in self.runner.lots.items()},
                "realized_pnl": self.runner.realized_pnl,
                # P1-5: 只保留最近 200 条，避免 checkpoint 文件无限增长
                "closed_trades": self.runner.closed_trades[-200:],
                "closed_trades_total": len(self.runner.closed_trades),
            },
            "strategy": {
                "grid_filled": getattr(self.strategy, 'grid_filled', []),
                "paused": self.strategy._paused,
                "paused_reason": getattr(self.strategy, '_paused_reason', None),
                "consecutive_losses": self.strategy._consecutive_losses,
                "daily_pnl": self.strategy._daily_pnl,
                "auto_resume_count": getattr(self.strategy, '_auto_resume_count', 0),
                "current_day": self.strategy._current_day.isoformat() if getattr(self.strategy, '_current_day', None) else None,
                # 指标内部状态（resume 续跑必需，否则指标被重置导致信号不一致）
                "last_price": getattr(self.strategy, 'last_price', None),
                "ema20": getattr(self.strategy, '_ema20', None),
                "ema50": getattr(self.strategy, '_ema50', None),
                "prev_close_atr": getattr(self.strategy, '_prev_close_atr', None),
                "tr_window": list(self.strategy._tr_window) if getattr(self.strategy, '_tr_window', None) else None,
                "tr_sum": getattr(self.strategy, '_tr_sum', 0.0),
                "anomaly_paused_at": str(self.strategy._anomaly_paused_at) if getattr(self.strategy, '_anomaly_paused_at', None) else None,
            },
            "risk": {
                "state": self.risk.state,
                "daily_pnl": self.risk.daily_pnl,
                "consecutive_losses": self.risk.consecutive_losses,
                "api_failures": self.risk.api_failures,
                "cumulative_pnl": self.risk.cumulative_pnl,
                "peak_equity": self.risk.peak_equity,
                "current_day": self.risk.current_day.isoformat() if self.risk.current_day else None,
                "reconcile_failures": self._reconcile_failures,
                "prev_close": self._prev_close,
                "last_pause_reason": getattr(self.risk, '_last_pause_reason', None),
            },
            "pending": _ser_pending(self.pending),
        }
        target = Path(path) if path else self.state_file
        tmp = Path(str(target) + ".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False, default=str),
                       encoding="utf-8")
        tmp.replace(target)  # 原子替换，防写一半崩溃

    def _restore(self):
        st = json.loads(self.state_file.read_text(encoding="utf-8"))
        self._build(st["bounds"]["lower"], st["bounds"]["upper"])
        self.day_count = st["day_count"]
        self.current_day = date.fromisoformat(st["current_day"]) if st["current_day"] else None
        self.last_bar_ts = st["last_bar_ts"]

        b = st["broker"]
        if self.args.broker == "exchange":
            self.broker.load_state(b)
            still_open = self.broker.reconcile_unconfirmed()
            if still_open:
                raise SystemExit(
                    f"重启发现未确认订单仍挂单 {still_open}：请人工处理后再续跑"
                    f"（exchange 模式非逐位一致）")
        else:
            self.broker.balance = b["balance"]
            self.broker.positions = b["positions"]
            self.broker.orders = b["orders"]
            self.broker.order_id_counter = b["order_id_counter"]
            # P1-5: 恢复增量统计（旧 checkpoint 无这些字段时用默认值）
            self.broker._total_commission = b.get("_total_commission", 0.0)
            self.broker._total_slippage = b.get("_total_slippage", 0.0)
            self.broker._archived_order_count = b.get("_archived_order_count", 0)

        r = st["runner"]
        self.runner.lots = {
            (int(k) if k.lstrip("-").isdigit() else k): v
            for k, v in r["lots"].items()
        }
        self.runner.realized_pnl = r["realized_pnl"]
        self.runner.closed_trades = r["closed_trades"]
        total = r.get("closed_trades_total", len(self.runner.closed_trades))
        if total > len(self.runner.closed_trades):
            logger.info(f"恢复时 closed_trades 已归档：保留最近 {len(self.runner.closed_trades)} / 总计 {total}")

        s = st["strategy"]
        if hasattr(self.strategy, 'grid_filled'):
            self.strategy.grid_filled = s["grid_filled"]
        self.strategy._paused = s["paused"]
        self.strategy._paused_reason = s.get("paused_reason")
        self.strategy._consecutive_losses = s["consecutive_losses"]
        self.strategy._daily_pnl = s["daily_pnl"]
        self.strategy._auto_resume_count = s.get("auto_resume_count", 0)
        self.strategy._current_day = date.fromisoformat(s["current_day"]) if s.get("current_day") else None
        # 恢复指标内部状态（旧 checkpoint 无这些字段时跳过，保持向后兼容）
        if hasattr(self.strategy, 'last_price'):
            self.strategy.last_price = s.get("last_price")
        if hasattr(self.strategy, '_ema20'):
            self.strategy._ema20 = s.get("ema20")
        if hasattr(self.strategy, '_ema50'):
            self.strategy._ema50 = s.get("ema50")
        if hasattr(self.strategy, '_prev_close_atr'):
            self.strategy._prev_close_atr = s.get("prev_close_atr")
        if hasattr(self.strategy, '_tr_window') and s.get("tr_window") is not None:
            from collections import deque
            self.strategy._tr_window = deque(s["tr_window"], maxlen=getattr(self.strategy, '_atr_period', 14))
        if hasattr(self.strategy, '_tr_sum'):
            self.strategy._tr_sum = s.get("tr_sum", 0.0)
        if hasattr(self.strategy, '_anomaly_paused_at') and s.get("anomaly_paused_at"):
            try:
                self.strategy._anomaly_paused_at = pd.Timestamp(s["anomaly_paused_at"])
            except Exception:
                self.strategy._anomaly_paused_at = None

        rk = st["risk"]
        self.risk.state = rk["state"]
        self.risk.daily_pnl = rk["daily_pnl"]
        self.risk.consecutive_losses = rk["consecutive_losses"]
        self.risk.api_failures = rk["api_failures"]
        self.risk.cumulative_pnl = rk.get("cumulative_pnl", 0.0)
        self.risk.peak_equity = rk.get("peak_equity", self.risk.capital_base)
        self.risk.current_day = date.fromisoformat(rk["current_day"]) if rk.get("current_day") else None
        self._reconcile_failures = rk.get("reconcile_failures", 0)
        self._prev_close = rk.get("prev_close")
        self.risk._last_pause_reason = rk.get("last_pause_reason")

        self.pending = _deser_pending(st["pending"])
        logger.info(f"恢复检查点：day_count={self.day_count}, "
                    f"last_bar_ts={self.last_bar_ts}, state={self.risk.state}")

    # ---- 人工恢复 ----
    def _check_resume(self):
        if self.resume_flag.exists() and (self.risk.is_paused() or self.strategy._paused):
            self.risk.resume()
            # 策略级熔断也一并人工解除（grid 有独立 _paused 标志）
            self.strategy._paused = False
            self.strategy._paused_reason = None
            self.strategy._consecutive_losses = 0
            self.strategy._daily_pnl = 0.0
            self.strategy._auto_resume_count = 0
            self.resume_flag.unlink(missing_ok=True)
            logger.warning("检测到 resume 标志，风控/策略已人工恢复 -> ACTIVE")

    # ---- 持仓漂移对账（exchange 模式）----
    def _reconcile_drift(self):
        """交易所真实净持仓（按 delta）vs 本地 lots 净持仓，超阈值→熔断。"""
        try:
            real = self.broker.get_position(self.symbol)
        except Exception as e:
            # testnet 闪断等瞬态错误：独立计数器累积，连续达阈值→紧急停止
            self._reconcile_failures += 1
            logger.warning(
                f"对账查持仓失败（连续 {self._reconcile_failures}/"
                f"{self._max_reconcile_failures}）：{type(e).__name__}: {e}")
            if self._reconcile_failures >= self._max_reconcile_failures:
                self.risk.emergency_stop(
                    f"对账连续失败 {self._reconcile_failures} 次，无法确认持仓安全")
            return
        self._reconcile_failures = 0  # 成功 → 重置
        local_net = sum(lot["amount"] for lot in self.runner.lots.values())
        ok, drift = assess_position_drift(
            real, self.broker.initial_position, local_net,
            abs_tol=self.args.drift_abs, rel_tol=self.args.drift_rel,
        )
        if not ok:
            logger.error(f"持仓漂移 drift={drift:.8f}（real={real}, "
                         f"local_net={local_net}）→ 触发熔断")
            self.risk.emergency_stop(f"持仓漂移 {drift:.8f}")

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

    # ---- 闪崩保护 ----
    def _check_flash_crash(self, bar):
        """单根 bar 跌幅超阈值 → 触发风控 PAUSE，防止闪崩时大量买入。"""
        if self._prev_close is None:
            return
        drop = (self._prev_close - float(bar["close"])) / self._prev_close
        if drop >= self.args.max_bar_drop_pct:
            reason = (f"flash crash: single bar drop {drop:.2%} "
                      f">= {self.args.max_bar_drop_pct:.2%}")
            logger.error(reason)
            self.risk._trip_pause(reason)
            self.strategy._trigger_breaker(reason)
            notifier.send_warning_sync(
                f"闪崩保护触发\n策略: {self.args.strategy}\n"
                f"跌幅: {drop:.2%}\n价格: {self._prev_close:.2f} → {float(bar['close']):.2f}\n"
                f"时间: {bar['timestamp']}"
            )

    # ---- P1-8: 实时数据轻量校验 ----
    @staticmethod
    def _validate_bar(bar) -> bool:
        """校验单根 OHLCV bar 的基本逻辑一致性。

        检查：价格 > 0、high >= low、open/close 在 [low, high] 范围内、volume >= 0。
        返回 True 表示合法，False 表示异常。
        """
        try:
            o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
            v = float(bar.get("volume", 0))
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"bar 字段缺失或类型错误：{e}")
            return False
        if l <= 0 or o <= 0 or h <= 0 or c <= 0:
            logger.warning(f"bar 价格 <= 0: O={o} H={h} L={l} C={c}")
            return False
        if h < l:
            logger.warning(f"bar high < low: H={h} L={l}")
            return False
        if o < l or o > h or c < l or c > h:
            logger.warning(f"bar open/close 超出 [low, high]: O={o} H={h} L={l} C={c}")
            return False
        if v < 0:
            logger.warning(f"bar volume < 0: V={v}")
            return False
        return True

    # ---- 急停信号文件（API 端点触发）----
    _EMERGENCY_STOP_FILE = "data/.emergency_stop"

    def _check_emergency_stop_signal(self) -> bool:
        """检查 API 端点写入的急停信号文件。存在则删除并返回 True。"""
        p = Path(self._EMERGENCY_STOP_FILE)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
            return True
        return False

    # ---- 单 bar 处理 ----
    def _compute_atr(self, period: int = 14) -> float | None:
        """从历史数据计算 ATR（用于 Portfolio Heat 风险估算）。

        ATR = SMA(True Range, period)
        TR = max(H-L, |H-prev_C|, |L-prev_C|)
        """
        df = self._history
        if df is None or len(df) < period + 1:
            return None
        try:
            recent = df.tail(period + 1)
            high = recent["high"].values
            low = recent["low"].values
            close = recent["close"].values
            tr_list = []
            for i in range(1, len(close)):
                tr = max(
                    high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i] - close[i - 1]),
                )
                tr_list.append(tr)
            return sum(tr_list) / len(tr_list) if tr_list else None
        except Exception:
            return None

    def _filter_pending_buy(self):
        """Portfolio Heat 超阈值时，取消 pending 中的 BUY 信号（允许 SELL）。

        信号格式：
        - str: "BUY" / "SELL"
        - List[Order]: Order.side = "buy" / "sell"
        """
        if self.pending is None:
            return

        if isinstance(self.pending, str):
            if self.pending == "BUY":
                logger.warning(
                    f"Portfolio Heat 拒单: 取消 pending BUY 信号 "
                    f"(strategy={self.args.strategy})"
                )
                self.pending = None
            # SELL 信号保留
        elif isinstance(self.pending, list):
            sell_orders = [o for o in self.pending if o.side != "buy"]
            if len(sell_orders) < len(self.pending):
                cancelled = len(self.pending) - len(sell_orders)
                logger.warning(
                    f"Portfolio Heat 拒单: 取消 {cancelled} 个 pending BUY 订单 "
                    f"(strategy={self.args.strategy})"
                )
                self.pending = sell_orders if sell_orders else None

    def _update_portfolio_heat(self, bar):
        """更新本策略的持仓热力到共享文件"""
        if self.portfolio_heat is None:
            return

        current_price = float(bar["close"])
        atr = self._compute_atr()

        # lots 格式: {tag: {"amount": float, "cost_price": float}}
        lots_serializable = {
            str(k): v for k, v in self.runner.lots.items()
        } if self.runner.lots else {}

        self.portfolio_heat.update_position_heat(
            lots=lots_serializable,
            current_price=current_price,
            atr=atr,
            initial_capital=self.args.initial,
        )

    def _on_bar(self, bar):
        try:
            self._on_bar_inner(bar)
        except Exception as e:
            logger.error(
                f"_on_bar 未预期异常: {type(e).__name__}: {e}", exc_info=True)
            # 不触发风控暂停——这是代码 bug，不是市场异常
            # checkpoint 仍然保存，下一根 bar 继续

    def _on_bar_inner(self, bar):
        # P1-8: 实时数据校验——异常 bar 跳过本根，不进入策略
        # 不触发 record_data_anomaly()：单根坏 bar 是 Binance 瞬态问题，
        # 不是系统性数据异常，不应导致永久 PAUSED。
        if not self._validate_bar(bar):
            logger.warning(f"跳过异常 bar: ts={bar.get('timestamp', '?')}")
            return

        # 检查 API 端点发出的急停信号
        if self._check_emergency_stop_signal():
            self.risk.emergency_stop("remote emergency-stop via API signal file")
            logger.warning("收到远程急停信号，RiskManager -> STOPPED")
            notifier.send_critical_sync(
                f"急停触发\n策略: {self.args.strategy}\n原因: 远程 API 急停信号\n时间: {bar['timestamp']}"
            )
            return

        self._check_resume()

        # 日切检测：重置 daily_pnl，daily-loss PAUSE 可自动恢复
        self.risk.check_new_day(bar["timestamp"])

        # 闪崩保护：在信号生成前检查
        self._check_flash_crash(bar)

        # Portfolio Heat 门控：超阈值时取消 pending BUY（允许 SELL 平仓）
        if self.portfolio_heat is not None and self.pending is not None:
            portfolio_heat = self.portfolio_heat.get_portfolio_heat()
            if portfolio_heat > self.portfolio_heat.max_heat:
                self._filter_pending_buy()
                notifier.send_warning_sync(
                    f"Portfolio Heat 超阈值\n策略: {self.args.strategy}\n"
                    f"当前热力: {portfolio_heat:.2%} (阈值: {self.portfolio_heat.max_heat:.2%})\n"
                    f"已拒绝新开仓，仅允许平仓\n时间: {bar['timestamp']}"
                )

        before = len(self.runner.closed_trades)
        # historical：截至本 bar 的全部已见数据
        self.pending = self.runner.process_bar(
            bar, self._history.loc[: bar.name], self.strategy, self.pending
        )
        for t in self.runner.closed_trades[before:]:
            self.risk.record_fill(t)

        # Portfolio Heat：更新本策略持仓热力到共享文件
        self._update_portfolio_heat(bar)

        if self.args.broker == "exchange":
            self._reconcile_drift()

        # 更新前一根收盘价（用于下一根闪崩检测）
        self._prev_close = float(bar["close"])

        day = pd.Timestamp(bar["timestamp"]).date()
        if self.current_day is None:
            self.current_day = day
        elif day != self.current_day:
            self._write_daily_report(self.current_day, float(bar["close"]))
            self.day_count += 1
            self.current_day = day

        self.alert_mgr.check_risk_events(self.risk)
        total_ret = self.runner.realized_pnl / self.args.initial
        self.alert_mgr.check_drawdown(total_ret)

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
        self._install_signal_handlers()
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
        # 数据不足时缩减 warmup（保证有足够 bar 生成日报）
        if start >= len(df):
            start = 0
        if resuming and self.last_bar_ts is not None:
            after = df.index[df["timestamp"] > pd.Timestamp(self.last_bar_ts)]
            if len(after):
                start = int(after[0])
            # else: 无新 bar → start 保持 0，从头重处理（日报按日期覆盖）

        print(f"[replay] bars {start}..{len(df)-1}, 目标 {self.args.days} 天")
        for i in range(start, len(df)):
            self._on_bar(df.iloc[i])
            if self.day_count >= self.args.days:
                break
        return self._finish()

    def _seed_live_warmup(self, seed):
        """live 冷启动：种子仅用于定网格区间 + 提供历史上下文，**不回填交易/日报**。

        把 last_bar_ts 推进到种子末根，使后续 _consume_new_bars 跳过全部已收盘历史，
        day_count 只随启动后真实到达的新 bar 推进——60 天=60 天真实连续运行，
        而非把 200 根种子（~28 天历史）瞬间回填成运行日。
        （replay 模式保留回填语义：那是加速跑历史的本意。）
        """
        warm = seed.iloc[:WARMUP]
        lo, hi = warm["low"].min(), warm["high"].max()
        span = hi - lo
        self._build(lo + span * 0.1, hi - span * 0.1)
        self._history = seed
        self.last_bar_ts = str(seed.iloc[-1]["timestamp"])
        self._checkpoint()  # 持久化预热基线，崩溃可凭此续跑

    def _run_live(self, resuming):
        if not resuming:
            self._seed_live_warmup(self._fetch_live_df())
        else:
            self._history = self._fetch_live_df()

        print(f"[live] {self.symbol} {self.args.timeframe}，目标 {self.args.days} 天，"
              f"轮询 {self.args.poll_seconds}s（Ctrl+C 停止，可重启续跑）")
        # 只处理启动后真实到达的新 bar（冷启动种子已在 _seed_live_warmup 标记为已见）
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


    def _install_signal_handlers(self):
        """Register SIGINT/SIGTERM handlers for graceful exit"""
        def _graceful_exit(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.warning(f"Received {sig_name}, saving checkpoint...")
            try:
                if self.strategy is not None:
                    self._checkpoint()
                    logger.info("Checkpoint saved, exiting gracefully")
            except Exception as e:
                logger.error(f"Failed to save checkpoint on exit: {e}")
            sys.exit(0)
        signal.signal(signal.SIGINT, _graceful_exit)
        signal.signal(signal.SIGTERM, _graceful_exit)

    def _finish(self):
        # 清除 Portfolio Heat 记录（防止已停止策略的热力残留）
        if self.portfolio_heat is not None:
            self.portfolio_heat.clear()
            logger.info(f"Portfolio Heat 已清除: strategy={self.args.strategy}")

        # 回放模式：强制平仓所有未平仓位，使盈亏计入 closed_trades
        if self.args.replay:
            # 先保存未平仓状态（resume 续跑需要——连续运行不会在中途平仓）
            self._checkpoint()

            pos = self.broker.get_position(self.symbol)
            if pos and pos > 0:
                last_bar = self._history.iloc[-1]
                close_price = float(last_bar["close"])
                ts = last_bar["timestamp"]
                runner = self.runner
                # 遍历所有 tag 的 lots 逐个平仓（grid 等多 tag 策略的 lots
                # 存在网格索引 tag 下，_execute_signal("SELL") 用 LEGACY_TAG 找不到）
                if runner.lots:
                    for tag, lot in list(runner.lots.items()):
                        if lot["amount"] > 0:
                            runner._sell(tag, lot["amount"], close_price, ts, self.strategy)
                else:
                    # 无 lots 记账（如 BuyAndHold 返回字符串信号），用 LEGACY_TAG 平仓
                    runner._sell(runner.LEGACY_TAG, pos, close_price, ts, self.strategy)
                logger.info(f"回放结束强制平仓: {pos:.6f} @ {close_price:.2f}")
                # 平仓结果写入 .final 文件（前端读取最终平仓状态），
                # 主 state 文件保留未平仓状态供 resume 续跑
                final_file = Path(str(self.state_file) + ".final")
                self._checkpoint(str(final_file))

        print(f"完成：累计 {self.day_count} 天日报，检查点 {self.state_file}")
        crits = self.alert_mgr.critical_alerts()
        if crits:
            print(f"[ALERT] {len(crits)} CRITICAL alerts")
        return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Paper Trading 连续运行守护进程")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="4h")
    p.add_argument("--initial", type=float, default=10000.0)
    from src.strategy.registry import STRATEGY_REGISTRY
    p.add_argument("--strategy", choices=list(STRATEGY_REGISTRY.keys()), action="append", default=[],
                   help="策略类型（可多次指定以运行多个策略，默认 grid）")
    p.add_argument("--replay", nargs="?", const="generate", default=None,
                   help="回放模式；可选 CSV 路径，缺省用 generate 生成数据")
    p.add_argument("--market-type", default="oscillating",
                   choices=["oscillating", "trending", "black_swan", "random"],
                   help="生成数据的市场类型（仅 --replay generate 时生效）")
    p.add_argument("--state-file", default="data/paper_daemon_state.json")
    p.add_argument("--report-dir", default="data/reports/paper/daily")
    p.add_argument("--poll-seconds", type=int, default=60)
    p.add_argument("--fresh", action="store_true", help="忽略旧检查点重开")
    p.add_argument("--no-db", action="store_true", help="不落库")
    p.add_argument("--broker", choices=["paper", "exchange"], default="paper",
                   help="paper=PaperBroker 模拟（默认）；exchange=testnet 真实下单")
    p.add_argument("--drift-abs", type=float, default=1e-5,
                   help="持仓漂移绝对容差（base 币种数量）")
    p.add_argument("--drift-rel", type=float, default=0.02,
                   help="持仓漂移相对容差（占本地净持仓比例）")
    # exchange 模式订单级护栏（RISK_CONTROLS）；1m shakedown 可调小 --min-trade-interval
    p.add_argument("--max-position-per-trade", type=float, default=0.20,
                   help="单笔名义额占起始资金上限（exchange 模式）")
    p.add_argument("--min-trade-interval", type=int, default=300,
                   help="相邻下单决策最小间隔秒（按 bar 判，exchange 模式）")
    p.add_argument("--max-trades-per-day", type=int, default=10,
                   help="单日订单数上限（exchange 模式）")
    p.add_argument("--max-bar-drop-pct", type=float, default=0.10,
                   help="单根 bar 跌幅熔断阈值（默认 10%%），超过则 PAUSE")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                    help="日志级别（默认 INFO）")
    args = p.parse_args(argv)
    if not args.strategy:
        args.strategy = ["grid"]
    args.strategy = list(dict.fromkeys(args.strategy))
    return args


def main(argv=None) -> int:

    args = parse_args(argv)
    setup_logger(log_level=getattr(args, 'log_level', 'INFO'))

    strategies = args.strategy or ["grid"]
    exit_codes = []

    for i, strat_name in enumerate(strategies):
        # 每个策略运行自己的 daemon 实例
        logger.info(f"[{i+1}/{len(strategies)}] 启动策略: {strat_name}")
        args.strategy = strat_name
        # 每个策略使用独立 state file
        orig_state = args.state_file
        if len(strategies) > 1:
            base, ext = orig_state.rsplit(".", 1)
            args.state_file = f"{base}_{strat_name}.{ext}"
        code = PaperTradingDaemon(args).run()
        exit_codes.append((strat_name, code))
        args.state_file = orig_state

    summary = ", ".join(f"{n}={c}" for n, c in exit_codes)
    logger.info(f"全部策略运行完成: {summary}")
    if all(c == 0 for _, c in exit_codes):
        notifier.send_info_sync(
            f"Daemon 运行完成\n策略: {', '.join(strategies)}\n结果: 全部成功"
        )
    else:
        notifier.send_critical_sync(
            f"Daemon 异常退出\n策略: {', '.join(strategies)}\n结果: {summary}"
        )
    return 0 if all(c == 0 for _, c in exit_codes) else 1


if __name__ == "__main__":
    sys.exit(main())
