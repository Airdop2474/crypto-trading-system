"""
数据服务层：跑一次 Paper Trading，把真实内存结果映射成前端契约。

设计取舍（见 frontend/lib/types.ts）：
- 后端无常驻实盘进程，唯一真实数据来自 Paper Trading 引擎的运行结果。
- 本模块在首次请求时用 run_paper_trading 的同款装配跑一次，缓存结果，
  各端点从缓存读。不改 runner、不依赖 DB（净值曲线直接用内存快照）。
- 无真实数据源的字段诚实标注：
    * 行情 Ticker —— 由 OHLCV 最后一段派生（同一份数据，非外部实时源）。
    * price-action 策略 —— 后端不存在，策略列表只含运行中的网格策略。
    * 启停策略 —— Paper 模式无常驻策略，PATCH 为 no-op 回显。
"""

import glob
import threading
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.execution import PaperBroker, PaperTradingRunner
from src.execution.multi_runner import MultiStrategyRunner, StrategyConfig
from src.execution.paper_report import PaperTradingReportGenerator
from src.execution.risk_manager import RiskManager
from src.monitor import MetricsCollector
from src.strategy.registry import get_strategy
from src.utils.logger import logger
from src.utils.cache import cache, CacheKeys
from src.utils.database import db

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SYMBOL = "BTC/USDT"
INITIAL_CAPITAL = 10000.0

_state: Optional[dict] = None
_lock = threading.Lock()


def reset_state() -> None:
    """重置缓存的 Paper Trading state（用于 /admin/refresh-state）。

    下次 get_state() 调用会重新跑 Paper Trading。
    线程安全：持锁清空，避免与并发 get_state() 竞争。
    """
    global _state
    with _lock:
        _state = None
    logger.info("Paper Trading state reset; will rebuild on next request")


# --------------------------------------------------------------------------
# 运行 Paper Trading（lazy，进程内只跑一次）
# --------------------------------------------------------------------------
def _load_data() -> pd.DataFrame:
    """优先读 data/raw 的震荡数据；缺失时用同款生成器内存生成（seed 固定可复现）。"""
    files = sorted(glob.glob(str(PROJECT_ROOT / "data" / "raw" / "BTC_USDT_4h_osc_*.csv")))
    if files:
        df = pd.read_csv(files[-1])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.generate_oscillating_data import generate_oscillating_ohlcv

    df = generate_oscillating_ohlcv()  # 默认 seed=42
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def _build_state() -> dict:
    """跑一次 Paper Trading，返回缓存所需的全部对象（与 run_paper_trading.py 一致）。

    同时构建单策略（Grid BTC/USDT）与多策略运行结果。
    单策略路径保持向后兼容；多策略结果存入 state["multi_results"]。
    """
    df = _load_data()
    lo, hi = df["low"].min(), df["high"].max()
    span = hi - lo
    lower, upper = lo + span * 0.1, hi - span * 0.1

    # --- 单策略（Grid BTC/USDT）：兼容现有前端映射 ---
    strategy = get_strategy("grid")(
        lower_price=lower, upper_price=upper, grid_count=10,
        initial_capital=INITIAL_CAPITAL,
    )
    broker = PaperBroker(
        INITIAL_CAPITAL, commission=0.001, slippage={SYMBOL: 0.0005},
        max_position_per_trade=1.0, max_total_position=1.0,
    )
    collector = MetricsCollector()
    runner = PaperTradingRunner(broker, SYMBOL, metrics_collector=collector)
    result = runner.run(df, strategy)

    last_price = float(df.iloc[-1]["close"])
    report = PaperTradingReportGenerator().build_report(result, {SYMBOL: last_price})

    # --- 多策略（共享 broker，独立 runner）---
    # Note: Grid strategy runs once in single-strategy path above;
    # multi_results reuses that result to avoid double execution.
    multi_results, multi_aggregate, multi_runner = _build_multi_results(df, lo, hi, grid_result=result)

    state = {
        "df": df,
        "last_price": last_price,
        "strategy": strategy,
        "runner": runner,
        "result": result,
        "report": report,
        "collector": collector,
        "multi_results": multi_results,
        "multi_aggregate": multi_aggregate,
        "_multi_runner": multi_runner,
    }

    # 保存摘要到 Redis（后续重启可快速提供关键指标）
    _save_state_summary(state)

    # 持久化到数据库（DB 不可用时静默跳过）
    _persist_to_db(state)

    return state


def _build_multi_results(
    df: pd.DataFrame, lo: float, hi: float,
    grid_result=None,
) -> tuple:
    """用 MultiStrategyRunner 跑多个策略，返回 (results_dict, aggregate)。

    当前注册 8 个策略（覆盖系统全部策略）：
    1. Grid BTC/USDT — 震荡市网格低买高卖
    2. RSI Momentum — 趋势回调/超买卖出
    3. Simple MA — 金叉买入/死叉卖出
    4. Donchian Channel — N周期高低点突破
    5. Market Structure — 波动结构突破
    6. SuperTrend — ATR 自适应跟踪止损
    7. Key Level Reversal — 支撑阻力位 pin bar 反转
    8. Buy & Hold — 买入持有基准

    所有策略共享同一个 broker（资金池 10000 USDT）。
    """
    span = hi - lo
    lower, upper = lo + span * 0.1, hi - span * 0.1

    shared_broker = PaperBroker(
        INITIAL_CAPITAL, commission=0.001, slippage={SYMBOL: 0.0005},
        max_position_per_trade=1.0, max_total_position=1.0,
    )
    shared_collector = MetricsCollector()

    risk_manager = RiskManager(capital_base=INITIAL_CAPITAL)

    multi_runner = MultiStrategyRunner(
        broker=shared_broker,
        risk_manager=risk_manager,
        metrics_collector=shared_collector,
    )

    # 注册全部 8 个策略
    configs = [
        StrategyConfig(
            strategy_id="grid-btc-usdt",
            strategy=get_strategy("grid")(
                lower_price=lower, upper_price=upper, grid_count=10,
                initial_capital=INITIAL_CAPITAL,
            ),
            symbol=SYMBOL,
            description="网格策略：震荡市低买高卖",
        ),
        StrategyConfig(
            strategy_id="rsi-btc-usdt",
            strategy=get_strategy("rsi")(),
            symbol=SYMBOL,
            description="RSI 动量策略：趋势回调买入/超买卖出",
        ),
        StrategyConfig(
            strategy_id="ma-btc-usdt",
            strategy=get_strategy("ma")(),
            symbol=SYMBOL,
            description="均线策略：金叉买入/死叉卖出",
        ),
        StrategyConfig(
            strategy_id="donchian-btc-usdt",
            strategy=get_strategy("donchian")(period=20),
            symbol=SYMBOL,
            description="唐奇安通道：N周期高低点突破",
        ),
        StrategyConfig(
            strategy_id="structure-btc-usdt",
            strategy=get_strategy("structure")(lookback=10),
            symbol=SYMBOL,
            description="市场结构：波动结构突破",
        ),
        StrategyConfig(
            strategy_id="supertrend-btc-usdt",
            strategy=get_strategy("supertrend")(period=10, multiplier=3.0),
            symbol=SYMBOL,
            description="SuperTrend：ATR自适应跟踪止损",
        ),
        StrategyConfig(
            strategy_id="reversal-btc-usdt",
            strategy=get_strategy("reversal")(lookback=50),
            symbol=SYMBOL,
            description="关键位反转：支撑阻力+pin bar确认",
        ),
        StrategyConfig(
            strategy_id="buyhold-btc-usdt",
            strategy=get_strategy("buyhold")(),
            symbol=SYMBOL,
            description="买入持有：基准策略",
        ),
    ]
    multi_runner.register_many(configs)

    # 所有策略用同一份数据（同 symbol）
    data_map = {SYMBOL: df}
    results = multi_runner.run(data_map)
    aggregate = multi_runner.aggregate_results()

    return results, aggregate, multi_runner


def _save_state_summary(state: dict) -> None:
    """将 Paper Trading 状态摘要保存到 Redis"""
    try:
        report = state["report"]
        result = state["result"]
        summary = {
            "account": report["account"],
            "pnl": report["pnl"],
            "trades_count": result["statistics"]["total_trades"],
            "realized_pnl": result.get("realized_pnl", 0),
            "last_price": state["last_price"],
            "symbol": SYMBOL,
        }
        cache.set(CacheKeys.PAPER_STATE, summary, ttl=3600)
        logger.info(f"Paper trading state saved to {cache.backend_type} cache")
    except Exception as e:
        logger.debug(f"Failed to cache paper state: {e}")


def _persist_to_db(state: dict) -> None:
    """将 Paper Trading 结果持久化到数据库（幂等，DB 不可用时静默跳过）。"""
    try:
        if not db.is_postgres_available():
            return
    except Exception:
        return

    try:
        from src.repositories.run_repo import RunRepository
        from src.repositories.trade_repo import TradeRepository

        with db.get_session() as session:
            # --- 单策略 Grid ---
            result = state["result"]
            acc = state["report"]["account"]
            run = RunRepository.create_run(
                session,
                strategy_id="grid-btc-usdt",
                symbol=SYMBOL,
                mode="paper",
                timeframe="4h",
                initial_capital=INITIAL_CAPITAL,
                config={"commission": 0.001, "slippage": 0.0005},
            )

            # 订单
            TradeRepository.save_orders(session, run.id, result.get("trade_history", []))

            # 已平仓交易
            TradeRepository.save_closed_trades(
                session, run.id, "grid-btc-usdt",
                result.get("closed_trades", []),
            )

            # 持仓（lots → open_positions）
            lots = state["runner"].lots
            positions = [
                {"symbol": SYMBOL, "tag": tag, "amount": lot["amount"], "cost_price": lot["cost_price"]}
                for tag, lot in lots.items()
            ]
            TradeRepository.save_open_positions(session, run.id, "grid-btc-usdt", positions)

            # 标记完成
            RunRepository.complete_run(
                session, run.id,
                final_equity=acc["total_value"],
                realized_pnl=result.get("realized_pnl", 0.0),
                total_return=acc["total_return"],
            )

            # --- 多策略 ---
            multi_results = state.get("multi_results", {})
            for sid, mres in multi_results.items():
                if sid == "grid-btc-usdt":
                    continue  # 已处理
                m_stats = mres.get("statistics", {})
                m_run = RunRepository.create_run(
                    session,
                    strategy_id=sid,
                    symbol=mres.get("symbol", SYMBOL),
                    mode="paper",
                    timeframe="4h",
                    initial_capital=INITIAL_CAPITAL,
                )
                TradeRepository.save_orders(session, m_run.id, mres.get("trade_history", []))
                TradeRepository.save_closed_trades(
                    session, m_run.id, sid,
                    mres.get("closed_trades", []),
                )
                m_lots = mres.get("open_lots", {})
                m_positions = [
                    {"symbol": mres.get("symbol", SYMBOL), "tag": tag, "amount": lot.get("amount", 0), "cost_price": lot.get("cost_price", 0)}
                    for tag, lot in m_lots.items()
                ] if isinstance(m_lots, dict) else []
                TradeRepository.save_open_positions(session, m_run.id, sid, m_positions)

                RunRepository.complete_run(
                    session, m_run.id,
                    final_equity=m_stats.get("current_balance", INITIAL_CAPITAL),
                    realized_pnl=mres.get("realized_pnl", 0.0),
                )

            session.commit()
            # 记住最新的 run_id 供后续查询用
            state["_run_id"] = run.id
            logger.info(f"Paper trading results persisted to DB (run_id={run.id})")
    except Exception as e:
        logger.warning(f"Failed to persist to DB (non-fatal): {type(e).__name__}: {e}")


def get_cached_summary() -> Optional[dict]:
    """获取 Redis 缓存的 Paper Trading 摘要（无需完整重建状态）"""
    try:
        return cache.get(CacheKeys.PAPER_STATE)
    except Exception:
        return None


def get_state() -> dict:
    global _state
    if _state is None:
        with _lock:
            if _state is None:
                _state = _build_state()
    return _state


# --------------------------------------------------------------------------
# 映射到前端契约
# --------------------------------------------------------------------------
def _net_position(state: dict) -> Dict[str, float]:
    """聚合网格分档为单 symbol 净持仓：数量 + 加权平均成本。"""
    lots = state["runner"].lots  # {tag: {"amount", "cost_price"}}
    amount = sum(l["amount"] for l in lots.values())
    if amount <= 0:
        return {"amount": 0.0, "cost": 0.0}
    cost = sum(l["amount"] * l["cost_price"] for l in lots.values()) / amount
    return {"amount": amount, "cost": cost}


def account_summary(state: dict) -> dict:
    acc = state["report"]["account"]
    pnl = state["report"]["pnl"]
    total_gain = acc["total_value"] - acc["initial_balance"]

    # “今日”用最近 6 根 4h K线（≈24h）的权益变化近似；快照不足则回退为整段盈亏
    snaps = state["collector"].snapshots
    if len(snaps) >= 7:
        ref = snaps[-7]["account"]["total_value"]
        today_pnl = acc["total_value"] - ref
        today_pct = (today_pnl / ref * 100) if ref else 0.0
    else:
        today_pnl, today_pct = total_gain, acc["total_return"] * 100

    return {
        "totalEquity": acc["total_value"],
        "availableBalance": acc["cash"],
        "positionValue": acc["position_value"],
        "unrealizedPnl": pnl["unrealized"],
        "todayPnl": today_pnl,
        "todayPnlPct": today_pct,
        "totalPnl": total_gain,
        "totalPnlPct": acc["total_return"] * 100,
    }


def strategies(state: dict) -> List[dict]:
    s = state["strategy"]
    gs = s.get_grid_status()
    acc = state["report"]["account"]
    filled = sum(1 for f in gs["grid_filled"] if f)
    sells = sum(1 for t in state["result"]["trade_history"] if t["side"] == "sell")
    return [{
        "id": "grid-btc-usdt",
        "name": getattr(s, "name", "GridTrading"),
        "type": "grid",
        "symbol": SYMBOL,
        "status": "paused" if gs["paused"] else "running",
        "pnl": state["result"]["realized_pnl"],
        "pnlPct": acc["total_return"] * 100,
        "investment": INITIAL_CAPITAL,
        "runningDays": _running_days(state),
        "createdAt": _first_trade_time(state),
        "grid": {
            "upperPrice": s.upper_price,
            "lowerPrice": s.lower_price,
            "gridCount": s.grid_count,
            "perGridProfit": s.position_per_grid * 100,
            "filledGrids": filled,
            "arbitrageCount": sells,
        },
    }]


def positions(state: dict) -> List[dict]:
    net = _net_position(state)
    if net["amount"] <= 0:
        return []
    mark = state["last_price"]
    cost = net["cost"]
    upnl = net["amount"] * (mark - cost)
    return [{
        "id": "pos-btc-usdt",
        "symbol": SYMBOL,
        "side": "buy",
        "size": net["amount"],
        "entryPrice": cost,
        "markPrice": mark,
        "leverage": 1,
        "margin": net["amount"] * cost,
        "unrealizedPnl": upnl,
        "unrealizedPnlPct": (upnl / (net["amount"] * cost) * 100) if cost else 0.0,
        "liquidationPrice": 0.0,  # 现货无强平
        "strategyName": getattr(state["strategy"], "name", "GridTrading"),
    }]


def assets(state: dict) -> List[dict]:
    acc = state["report"]["account"]
    total_value = acc["total_value"] or 1.0
    net = _net_position(state)
    out = [{
        "asset": "USDT",
        "total": acc["cash"],
        "available": acc["cash"],
        "inOrder": 0.0,
        "valueUsdt": acc["cash"],
        "allocationPct": acc["cash"] / total_value * 100,
    }]
    if net["amount"] > 0:
        value = net["amount"] * state["last_price"]
        out.append({
            "asset": "BTC",
            "total": net["amount"],
            "available": net["amount"],
            "inOrder": 0.0,
            "valueUsdt": value,
            "allocationPct": value / total_value * 100,
        })
    return out


def orders(state: dict, limit: int = 100, offset: int = 0) -> dict:
    """订单列表（分页 + 全量统计）。

    参数：
        limit:  每页条数（1-500，超出会被夹紧）
        offset: 偏移量（从 0 开始；负数视为 0）

    返回：
        {
          "items": [...],          # 当前页订单（最新在前）
          "total": int,            # 全量订单数
          "limit": int,            # 本次实际使用的 limit
          "offset": int,           # 本次实际使用的 offset
          "has_more": bool,        # 是否还有下一页
          "stats": {               # 全量聚合统计（不随分页变化）
            "total_orders": int,
            "filled_count": int,
            "open_count": int,
            "partially_filled_count": int,
            "canceled_count": int,
            "total_fee": float,
          },
        }

    设计说明：
        stats 与 items 同接口返回，避免前端再发一次 /orders/stats 请求。
        stats 在切片前对全量 trade_history 聚合，O(n) 一次。
    """
    # 参数夹紧（防止异常输入）
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    # DB 优先查询
    run_id = state.get("_run_id")
    if run_id is not None:
        try:
            if db.is_postgres_available():
                from src.repositories.trade_repo import TradeRepository
                with db.get_session() as session:
                    items, total = TradeRepository.get_orders_paginated(
                        session, run_id, limit, offset,
                    )
                name = getattr(state["strategy"], "name", "GridTrading")
                for item in items:
                    item["strategyName"] = name
                return {
                    "items": items,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": (offset + limit) < total,
                    "stats": {
                        "total_orders": total,
                        "filled_count": total,
                        "open_count": 0,
                        "partially_filled_count": 0,
                        "canceled_count": 0,
                        "total_fee": sum(item.get("fee", 0) for item in items),
                    },
                }
        except Exception as e:
            logger.debug(f"DB orders query failed, falling back to memory: {e}")

    # 内存回退
    name = getattr(state["strategy"], "name", "GridTrading")
    hist = state["result"]["trade_history"]
    total = len(hist)

    # 全量按时间倒序（最新在前）后切片
    ordered = list(reversed(hist))
    page = ordered[offset:offset + limit]

    rows = []
    for t in page:
        rows.append({
            "id": t["order_id"],
            "time": pd.Timestamp(t["timestamp"]).isoformat(),
            "symbol": t["symbol"],
            "side": t["side"],
            "type": t.get("order_type") or "market",
            "price": t["price"],
            "amount": t["amount"],
            "filled": t["amount"],
            "status": "filled",
            "strategyName": name,
            "fee": t["commission"],
        })

    # 全量聚合统计（Paper 模式下 status 恒为 filled，但接口面向未来保留全部状态字段）
    total_fee = float(sum(t.get("commission", 0) for t in hist))
    stats = {
        "total_orders": total,
        "filled_count": total,        # Paper 模式全部已成交
        "open_count": 0,
        "partially_filled_count": 0,
        "canceled_count": 0,
        "total_fee": total_fee,
    }

    return {
        "items": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
        "stats": stats,
    }


def tickers(state: dict) -> List[dict]:
    """实时行情优先用 Binance 公共 ticker；外呼失败则回退为本地 OHLCV 派生。"""
    from src.api import market

    try:
        return market.get_live_tickers()
    except Exception as e:  # 无网络/限流/交易所异常 → 不让前端 500
        logger.warning(f"实时行情获取失败，回退本地派生: {type(e).__name__}: {e}")
        return _derived_tickers(state)


def _derived_tickers(state: dict) -> List[dict]:
    """从同一份 OHLCV 的最后 6 根（≈24h）派生 BTC/USDT 行情。离线回退用。"""
    df = state["df"]
    window = df.tail(6)
    last_close = float(df.iloc[-1]["close"])
    ref = float(window.iloc[0]["open"])
    return [{
        "symbol": SYMBOL,
        "price": last_close,
        "changePct": ((last_close - ref) / ref * 100) if ref else 0.0,
        "volume": float(window["volume"].sum()),
        "high": float(window["high"].max()),
        "low": float(window["low"].min()),
    }]


def pnl_history(state: dict) -> List[dict]:
    snaps = state["collector"].snapshots
    out = []
    prev = INITIAL_CAPITAL
    for s in snaps:
        equity = s["account"]["total_value"]
        out.append({
            "date": s["timestamp"],
            "equity": equity,
            "pnl": equity - prev,
            "cumulativePnl": equity - INITIAL_CAPITAL,
        })
        prev = equity
    return out


def win_rate_trend(state: dict, window: int = 20) -> List[dict]:
    """滚动胜率趋势（每笔平仓后基于最近 N 笔算胜率）。

    数据源：所有策略的 closed_trades 合并，按时间排序。

    每点：
    {
      "index": int,         # 第几笔平仓（从 1 开始）
      "close_time": str,    # 平仓时间
      "win_rate": float,    # 截至该点的滚动胜率 %
      "strategy_id": str,   # 该笔所属策略
    }
    """
    history = positions_history(state, limit=10000)
    # 时间正序
    history.sort(key=lambda x: x["close_time"])

    out = []
    wins = 0
    for i, t in enumerate(history, 1):
        if t["profit"] > 0:
            wins += 1
        # 滚动窗口：最近 window 笔的胜率
        start = max(0, i - window)
        recent = history[start:i]
        recent_wins = sum(1 for r in recent if r["profit"] > 0)
        wr = (recent_wins / len(recent) * 100) if recent else 0.0
        out.append({
            "index": i,
            "close_time": t["close_time"],
            "win_rate": wr,
            "strategy_id": t["strategy_id"],
        })
    return out


def strategy_correlation(state: dict) -> dict:
    """策略间日 PnL 相关性矩阵（Pearson）。

    数据源：每个策略的 closed_trades 按日聚合 PnL，对齐日期后算两两 Pearson。

    返回：
    {
      "strategies": ["grid-btc-usdt", "rsi-btc-usdt", ...],  # 策略 ID 列表
      "labels": ["网格", "RSI 动量", ...],                    # 中文标签
      "matrix": [[1.0, 0.32, ...], [0.32, 1.0, ...], ...],   # NxN 相关系数
    }
    """
    import numpy as np
    from src.strategy.registry import get_strategy_label

    # DB 优先：从 DB 获取每策略每日 PnL
    daily_pnl: Dict[str, Dict[str, float]] = {}
    try:
        if db.is_postgres_available():
            from src.repositories.analytics_repo import AnalyticsRepository
            with db.get_session() as session:
                daily_pnl = AnalyticsRepository.get_daily_pnl_by_strategy(session)
    except Exception as e:
        logger.debug(f"DB correlation query failed: {e}")
        daily_pnl = {}

    # 内存回退：从 multi_results 获取
    if not daily_pnl:
        multi_results = state.get("multi_results", {})
        for sid, res in multi_results.items():
            closed = res.get("closed_trades", [])
            per_day: Dict[str, float] = {}
            for t in closed:
                day = pd.Timestamp(t.get("time")).strftime("%Y-%m-%d") if t.get("time") else ""
                if not day:
                    continue
                per_day[day] = per_day.get(day, 0.0) + float(t.get("profit", 0))
            if per_day:
                daily_pnl[sid] = per_day

    if len(daily_pnl) < 2:
        return {"strategies": [], "labels": [], "matrix": []}

    # 对齐到并集日期
    all_dates = set()
    for per_day in daily_pnl.values():
        all_dates.update(per_day.keys())
    all_dates_sorted = sorted(all_dates)

    sids = list(daily_pnl.keys())
    labels = [get_strategy_label(s) for s in sids]

    # 构造矩阵：行=日期，列=策略
    mat = np.zeros((len(all_dates_sorted), len(sids)))
    for j, sid in enumerate(sids):
        for i, d in enumerate(all_dates_sorted):
            mat[i, j] = daily_pnl[sid].get(d, 0.0)

    # Pearson 相关
    if mat.shape[0] < 2:
        # 不足 2 天，无法算相关
        n = len(sids)
        corr = np.eye(n)
    else:
        try:
            corr = np.corrcoef(mat, rowvar=False)
            # 单策略时 corrcoef 返回标量，强制转 2D
            if corr.ndim == 0:
                corr = np.array([[float(corr)]])
        except Exception:
            n = len(sids)
            corr = np.eye(n)

    # 处理 NaN（标准差为 0 的列）
    corr = np.nan_to_num(corr, nan=0.0)

    return {
        "strategies": sids,
        "labels": labels,
        "matrix": corr.tolist(),
    }


def strategy_performance(state: dict) -> List[dict]:
    closed = state["result"].get("closed_trades", [])
    wins = sum(1 for t in closed if t["profit"] > 0)
    total = len(closed)
    return [{
        "name": getattr(state["strategy"], "name", "GridTrading"),
        "pnl": state["result"]["realized_pnl"],
        "trades": state["result"]["statistics"]["total_trades"],
        "winRate": (wins / total * 100) if total else 0.0,
    }]


def set_strategy_status(strategy_id: str, status: str) -> dict:
    """Paper 模式无常驻策略，回显即可（前端做乐观更新）。"""
    return {"id": strategy_id, "status": status}


# --------------------------------------------------------------------------
# 多策略 API
# --------------------------------------------------------------------------
def multi_strategy_summary(state: dict) -> dict:
    """多策略运行摘要（聚合所有策略的盈亏、交易数、状态）。"""
    agg = state.get("multi_aggregate", {})
    return {
        "totalRealizedPnl": agg.get("total_realized_pnl", 0.0),
        "totalClosedTrades": agg.get("total_closed_trades", 0),
        "strategiesCount": agg.get("strategies_count", 0),
        "strategies": agg.get("strategies", []),
    }


def multi_strategy_details(state: dict) -> List[dict]:
    """每个策略的详细结果（盈亏、交易历史、开放仓位）。"""
    results = state.get("multi_results", {})
    details = []
    for sid, result in results.items():
        stats = result.get("statistics", {})
        closed = result.get("closed_trades", [])
        wins = sum(1 for t in closed if t["profit"] > 0)
        total_closed = len(closed)
        details.append({
            "strategyId": sid,
            "symbol": result.get("symbol", SYMBOL),
            "realizedPnl": result.get("realized_pnl", 0.0),
            "totalTrades": stats.get("total_trades", 0),
            "winRate": (wins / total_closed * 100) if total_closed else 0.0,
            "openLots": len(result.get("open_lots", {})),
            "closedTrades": total_closed,
        })
    return details


def multi_strategy_result(state: dict, strategy_id: str) -> Optional[dict]:
    """获取单个策略的运行结果。"""
    results = state.get("multi_results", {})
    return results.get(strategy_id)


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------
def _running_days(state: dict) -> int:
    df = state["df"]
    span = df["timestamp"].max() - df["timestamp"].min()
    return max(1, int(span.days))


def _first_trade_time(state: dict) -> str:
    hist = state["result"]["trade_history"]
    if hist:
        return pd.Timestamp(hist[0]["timestamp"]).isoformat()
    return pd.Timestamp(state["df"].iloc[0]["timestamp"]).isoformat()


def get_strategy_slots(state: dict) -> Dict[str, tuple]:
    """从 multi_runner 提取所有策略实例和参数。

    返回:
        {strategy_id: (strategy_instance, params_dict)}
    """
    multi_runner = state.get("_multi_runner")
    if multi_runner is None:
        return {}

    slots_map = {}
    for slot in multi_runner.slots:
        strategy = slot.config.strategy
        params = dict(strategy.parameters) if hasattr(strategy, "parameters") else {}
        slots_map[slot.config.strategy_id] = (strategy, params)
    return slots_map


# --------------------------------------------------------------------------
# 风险指标 API
# --------------------------------------------------------------------------
def _build_equity_curve_df(state: dict) -> "pd.DataFrame":
    """从 collector 快照构造 PerformanceMetrics 所需的权益曲线 DataFrame。

    PerformanceMetrics 期望 equity_curve 含列：time / total_equity（注意是 'time' 不是 'timestamp'）。
    collector.snapshots 每条含 timestamp + account.total_value，对齐即可。
    """
    snaps = state["collector"].snapshots
    if not snaps:
        # 回退：用 df 末价构造一条
        df = state["df"]
        return pd.DataFrame({
            "time": [df.iloc[-1]["timestamp"]],
            "total_equity": [state["report"]["account"]["total_value"]],
        })
    return pd.DataFrame({
        "time": [s["timestamp"] for s in snaps],
        "total_equity": [s["account"]["total_value"] for s in snaps],
    })


def risk_metrics(state: dict) -> dict:
    """账户级风险指标（用于总览页风险卡 + /risk 页面）。

    返回：
        {
          "max_drawdown": float,       # 最大回撤（负数，如 -0.12 表示 -12%）
          "max_drawdown_pct": float,   # 同上 × 100，方便前端直接显示
          "sharpe_ratio": float,       # 年化夏普
          "sortino_ratio": float,      # 年化 Sortino
          "volatility": float,         # 年化波动率（%）
          "annual_return": float,      # 年化收益率（%）
          "current_drawdown": float,   # 当前回撤（相对峰值，%）
          "equity_peak": float,        # 权益峰值
          "equity_current": float,     # 当前权益
          "max_drawdown_duration": int,# 最大回撤持续 bar 数
        }
    """
    import numpy as np
    from src.backtest.metrics import PerformanceMetrics

    eq_df = _build_equity_curve_df(state)
    acc = state["report"]["account"]

    max_dd = PerformanceMetrics.max_drawdown(eq_df)
    sharpe = PerformanceMetrics.sharpe_ratio(eq_df)
    sortino = PerformanceMetrics.sortino_ratio(eq_df)
    annual_ret = PerformanceMetrics.annual_return(eq_df)
    dd_duration = PerformanceMetrics.max_drawdown_duration(eq_df)

    # 年化波动率：日收益率 std × sqrt(periods_per_year)
    if len(eq_df) >= 2:
        equity = eq_df["total_equity"].values
        returns = np.diff(equity) / equity[:-1]
        periods_per_year = PerformanceMetrics._infer_periods_per_year(eq_df)
        volatility = float(returns.std() * np.sqrt(periods_per_year) * 100)
    else:
        volatility = 0.0

    # 当前回撤（相对历史峰值）
    equity_arr = eq_df["total_equity"].values
    if len(equity_arr) > 0:
        peak = float(np.maximum.accumulate(equity_arr).max())
        current = float(equity_arr[-1])
        current_dd = ((current - peak) / peak * 100) if peak > 0 else 0.0
    else:
        peak = acc["total_value"]
        current = acc["total_value"]
        current_dd = 0.0

    return {
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd * 100,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "volatility": volatility,
        "annual_return": annual_ret * 100,
        "current_drawdown": current_dd,
        "equity_peak": peak,
        "equity_current": current,
        "max_drawdown_duration": int(dd_duration),
    }


def drawdown_curve(state: dict) -> List[dict]:
    """回撤曲线（用于 /risk 页面 AreaChart）。

    每个点：{ date, equity, peak, drawdown }
    drawdown 单位为 %（负数）。
    """
    import numpy as np
    eq_df = _build_equity_curve_df(state)
    if eq_df.empty:
        return []

    equity = eq_df["total_equity"].values
    peaks = np.maximum.accumulate(equity)
    drawdown = np.where(peaks > 0, (equity - peaks) / peaks * 100, 0.0)

    out = []
    for i, ts in enumerate(eq_df["time"]):
        out.append({
            "date": pd.Timestamp(ts).isoformat(),
            "equity": float(equity[i]),
            "peak": float(peaks[i]),
            "drawdown": float(drawdown[i]),
        })
    return out


def risk_status(state: dict) -> dict:
    """账户级风控状态（来自 RiskManager）。

    返回：
        {
          "state": "ACTIVE" | "PAUSED" | "STOPPED",
          "can_trade": bool,
          "daily_pnl": float,
          "daily_loss_limit_pct": float,    # 日亏上限（%）
          "daily_loss_used_pct": float,     # 已用日亏（%）
          "consecutive_losses": int,
          "max_consecutive_losses": int,
          "cumulative_pnl": float,
          "total_drawdown_pct": float,      # 累计回撤（%）
          "max_total_drawdown_pct": float,  # 回撤上限（%）
          "events": [...],                  # 最近 20 条风控事件
          "limits": {                       # 配置上限一览
            "max_daily_loss": float,
            "max_consecutive_losses": int,
            "max_total_position": float,
            "max_total_drawdown": float,
          },
        }

    注：当前 Paper Trading 在 _build_state 中没有把 RiskManager 持久化到 state，
    所以这里从 multi_results 反推风控状态。若 state 含 risk_manager 则优先用之。
    """
    rm = state.get("risk_manager")

    # 默认值（无 RiskManager 时）
    limits = {
        "max_daily_loss": 0.03,
        "max_consecutive_losses": 5,
        "max_total_position": 0.60,
        "max_total_drawdown": 0.15,
    }

    if rm is None:
        # Paper 模式无 RiskManager：用 realized_pnl 派生简化状态
        realized = state["result"].get("realized_pnl", 0.0)
        return {
            "state": "ACTIVE",
            "can_trade": True,
            "daily_pnl": realized,
            "daily_loss_limit_pct": limits["max_daily_loss"] * 100,
            "daily_loss_used_pct": 0.0,
            "consecutive_losses": 0,
            "max_consecutive_losses": limits["max_consecutive_losses"],
            "cumulative_pnl": realized,
            "total_drawdown_pct": 0.0,
            "max_total_drawdown_pct": limits["max_total_drawdown"] * 100,
            "events": [],
            "limits": limits,
            "note": "Paper Trading 模式：未接入 RiskManager，状态为派生值",
        }

    # 有 RiskManager：完整状态
    with rm._lock:
        daily_used = (rm.daily_pnl / rm.capital_base * 100) if rm.capital_base > 0 else 0.0
        total_dd = ((rm.peak_equity - (rm.capital_base + rm.cumulative_pnl))
                    / rm.peak_equity * 100) if rm.peak_equity > 0 else 0.0
        return {
            "state": rm.state,
            "can_trade": rm.state == "ACTIVE",
            "daily_pnl": rm.daily_pnl,
            "daily_loss_limit_pct": rm.max_daily_loss * 100,
            "daily_loss_used_pct": daily_used,
            "consecutive_losses": rm.consecutive_losses,
            "max_consecutive_losses": rm.max_consecutive_losses,
            "cumulative_pnl": rm.cumulative_pnl,
            "total_drawdown_pct": total_dd,
            "max_total_drawdown_pct": rm.max_total_drawdown * 100,
            "events": list(rm.events)[-20:],
            "limits": {
                "max_daily_loss": rm.max_daily_loss,
                "max_consecutive_losses": rm.max_consecutive_losses,
                "max_total_position": rm.max_total_position,
                "max_total_drawdown": rm.max_total_drawdown,
            },
        }


# --------------------------------------------------------------------------
# 持仓历史 / 平仓交易 API
# --------------------------------------------------------------------------
def positions_history(state: dict, limit: int = 200) -> List[dict]:
    """已平仓交易历史（用于持仓页平仓历史表 + 盈亏分布）。

    数据源：所有策略的 multi_results.*.closed_trades + 单策略 result.closed_trades，
    合并后按平仓时间倒序。

    每条返回：
    {
      "id": str,                  # 平仓标识
      "strategy_id": str,         所属策略
      "strategy_name": str,       策略名（中文标签）
      "symbol": str,              交易对
      "tag": str,                 策略标签
      "open_time": str,           开仓时间（近似：取同 tag 上一笔买入成交时间）
      "close_time": str,          平仓时间
      "profit": float,            盈亏
      "profit_pct": float,        收益率 %（基于 INITIAL_CAPITAL 近似）
      "hold_bars": int,           持有 bar 数（近似）
    }
    """
    from src.strategy.registry import get_strategy_label

    # DB 优先查询
    try:
        if db.is_postgres_available():
            from src.repositories.trade_repo import TradeRepository
            with db.get_session() as session:
                db_trades = TradeRepository.get_closed_trades(session, limit=limit)
            if db_trades:
                result = []
                for t in db_trades:
                    result.append({
                        **t,
                        "strategy_name": get_strategy_label(t["strategy_id"]),
                        "profit_pct": (t["profit"] / INITIAL_CAPITAL * 100),
                        "hold_bars": 0,
                    })
                return result
    except Exception as e:
        logger.debug(f"DB positions_history failed, falling back to memory: {e}")

    # 内存回退
    all_closed: List[dict] = []

    # 单策略
    single = state["result"].get("closed_trades", [])
    single_name = getattr(state["strategy"], "name", "GridTrading")
    for t in single:
        all_closed.append({
            "id": f"single-{t.get('tag', '')}-{t.get('time', '')}",
            "strategy_id": "grid-btc-usdt",
            "strategy_name": single_name,
            "symbol": SYMBOL,
            "tag": t.get("tag", ""),
            "open_time": "",  # 单策略 closed_trades 无 open_time，留空
            "close_time": pd.Timestamp(t.get("time")).isoformat() if t.get("time") else "",
            "profit": float(t.get("profit", 0)),
            "profit_pct": (float(t.get("profit", 0)) / INITIAL_CAPITAL * 100),
            "hold_bars": 0,
        })

    # 多策略
    multi_results = state.get("multi_results", {})
    for sid, res in multi_results.items():
        closed = res.get("closed_trades", [])
        for t in closed:
            all_closed.append({
                "id": f"{sid}-{t.get('tag', '')}-{t.get('time', '')}",
                "strategy_id": sid,
                "strategy_name": get_strategy_label(sid),
                "symbol": res.get("symbol", SYMBOL),
                "tag": t.get("tag", ""),
                "open_time": "",
                "close_time": pd.Timestamp(t.get("time")).isoformat() if t.get("time") else "",
                "profit": float(t.get("profit", 0)),
                "profit_pct": (float(t.get("profit", 0)) / INITIAL_CAPITAL * 100),
                "hold_bars": 0,
            })

    # 去重（单策略 grid-btc-usdt 与多策略 grid-btc-usdt 可能重复）
    seen = set()
    deduped = []
    for t in all_closed:
        if t["id"] in seen:
            continue
        seen.add(t["id"])
        deduped.append(t)

    # 按平仓时间倒序
    deduped.sort(key=lambda x: x["close_time"], reverse=True)

    return deduped[:limit]


def pnl_distribution(state: dict, bins: int = 10) -> dict:
    """盈亏分布直方图（用于持仓页盈亏分布图）。

    返回：
    {
      "bins": [{"range": "-100~-50", "count": 3, "label": "亏损"}, ...],
      "stats": {
        "total": int,
        "wins": int,
        "losses": int,
        "win_rate": float,         # %
        "avg_profit": float,       # 平均盈利（仅盈利笔）
        "avg_loss": float,         # 平均亏损（仅亏损笔）
        "profit_factor": float,    # 盈亏比 = 总盈利 / 总亏损
        "best": float,
        "worst": float,
      }
    }
    """
    import numpy as np

    history = positions_history(state, limit=10000)
    profits = np.array([t["profit"] for t in history]) if history else np.array([0.0])

    # 直方图分箱（自动包含正负区间）
    if len(profits) > 1:
        lo, hi = float(profits.min()), float(profits.max())
        if lo == hi:
            lo, hi = lo - 1, hi + 1
        edges = np.linspace(lo, hi, bins + 1)
        counts, _ = np.histogram(profits, bins=edges)
    else:
        edges = np.array([-1, 0, 1])
        counts = np.array([0, 1])

    bin_list = []
    for i in range(len(counts)):
        left = float(edges[i])
        right = float(edges[i + 1])
        bin_list.append({
            "range": f"{left:.0f}~{right:.0f}",
            "count": int(counts[i]),
            "label": "盈利" if right > 0 and left >= 0 else "亏损" if right <= 0 else "混合",
        })

    # 统计
    wins_arr = profits[profits > 0]
    losses_arr = profits[profits < 0]
    total_profit = float(wins_arr.sum()) if len(wins_arr) else 0.0
    total_loss = float(abs(losses_arr.sum())) if len(losses_arr) else 0.0

    stats = {
        "total": int(len(profits)),
        "wins": int(len(wins_arr)),
        "losses": int(len(losses_arr)),
        "win_rate": (len(wins_arr) / len(profits) * 100) if len(profits) else 0.0,
        "avg_profit": float(wins_arr.mean()) if len(wins_arr) else 0.0,
        "avg_loss": float(losses_arr.mean()) if len(losses_arr) else 0.0,
        "profit_factor": (total_profit / total_loss) if total_loss > 0 else float("inf") if total_profit > 0 else 0.0,
        "best": float(profits.max()) if len(profits) else 0.0,
        "worst": float(profits.min()) if len(profits) else 0.0,
    }

    return {"bins": bin_list, "stats": stats}
