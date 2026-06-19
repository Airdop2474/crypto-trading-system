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
from src.monitor import MetricsCollector
from src.strategy.grid_trading import GridTradingStrategy
from src.strategy.rsi_momentum import RSIMomentumStrategy
from src.strategy.simple_ma import SimpleMAStrategy
from src.utils.logger import logger
from src.utils.cache import cache, CacheKeys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SYMBOL = "BTC/USDT"
INITIAL_CAPITAL = 10000.0

_state: Optional[dict] = None
_lock = threading.Lock()


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
    strategy = GridTradingStrategy(
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
    multi_results, multi_aggregate = _build_multi_results(df, lo, hi, grid_result=result)

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
    }

    # 保存摘要到 Redis（后续重启可快速提供关键指标）
    _save_state_summary(state)

    return state


def _build_multi_results(
    df: pd.DataFrame, lo: float, hi: float,
    grid_result=None,
) -> tuple:
    """用 MultiStrategyRunner 跑多个策略，返回 (results_dict, aggregate)。

    当前注册 3 个策略：
    1. Grid BTC/USDT（与单策略路径相同参数）
    2. RSI Momentum BTC/USDT
    3. SimpleMA BTC/USDT

    所有策略共享同一个 broker（资金池 10000 USDT）。
    """
    span = hi - lo
    lower, upper = lo + span * 0.1, hi - span * 0.1

    shared_broker = PaperBroker(
        INITIAL_CAPITAL, commission=0.001, slippage={SYMBOL: 0.0005},
        max_position_per_trade=1.0, max_total_position=1.0,
    )
    shared_collector = MetricsCollector()

    multi_runner = MultiStrategyRunner(
        broker=shared_broker,
        metrics_collector=shared_collector,
    )

    # 注册策略
    configs = [
        StrategyConfig(
            strategy_id="grid-btc-usdt",
            strategy=GridTradingStrategy(
                lower_price=lower, upper_price=upper, grid_count=10,
                initial_capital=INITIAL_CAPITAL,
            ),
            symbol=SYMBOL,
            description="网格策略：震荡市低买高卖",
        ),
        StrategyConfig(
            strategy_id="rsi-btc-usdt",
            strategy=RSIMomentumStrategy(),
            symbol=SYMBOL,
            description="RSI 动量策略：趋势回调买入/超买卖出",
        ),
        StrategyConfig(
            strategy_id="sma-btc-usdt",
            strategy=SimpleMAStrategy(),
            symbol=SYMBOL,
            description="均线策略：金叉买入/死叉卖出",
        ),
    ]
    multi_runner.register_many(configs)

    # 所有策略用同一份数据（同 symbol）
    data_map = {SYMBOL: df}
    results = multi_runner.run(data_map)
    aggregate = multi_runner.aggregate_results()

    return results, aggregate


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


def orders(state: dict, limit: int = 100) -> List[dict]:
    name = getattr(state["strategy"], "name", "GridTrading")
    hist = state["result"]["trade_history"]
    rows = []
    for t in reversed(hist[-limit:]):  # 最新在前
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
    return rows


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
