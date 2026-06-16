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
from src.execution.paper_report import PaperTradingReportGenerator
from src.monitor import MetricsCollector
from src.strategy.grid_trading import GridTradingStrategy
from src.utils.logger import logger

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
    """跑一次 Paper Trading，返回缓存所需的全部对象（与 run_paper_trading.py 一致）。"""
    df = _load_data()
    lo, hi = df["low"].min(), df["high"].max()
    span = hi - lo
    lower, upper = lo + span * 0.1, hi - span * 0.1

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

    return {
        "df": df,
        "last_price": last_price,
        "strategy": strategy,
        "runner": runner,
        "result": result,
        "report": report,
        "collector": collector,
    }


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
            "type": "limit",
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
    wins, total = _fifo_win_stats(state["result"]["trade_history"])
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
# 辅助
# --------------------------------------------------------------------------
def _fifo_win_stats(trade_history: List[dict]) -> tuple:
    """对单 symbol 成交做 FIFO 配对，估算盈利平仓占比（winRate 近似）。

    网格实际按 tag 平仓，与 FIFO 不完全一致，故为近似值；聚合盈亏仍以
    引擎的 realized_pnl 为准。
    """
    inventory: List[List[float]] = []  # [price, qty]
    wins = total = 0
    for t in sorted(trade_history, key=lambda x: x["timestamp"]):
        price = t.get("actual_price", t["price"])
        qty = t["amount"]
        if t["side"] == "buy":
            inventory.append([price, qty])
            continue
        # sell：FIFO 消耗买入库存，计算成本与盈亏
        remaining, cost_basis = qty, 0.0
        while remaining > 1e-12 and inventory:
            lot = inventory[0]
            take = min(remaining, lot[1])
            cost_basis += take * lot[0]
            lot[1] -= take
            remaining -= take
            if lot[1] <= 1e-12:
                inventory.pop(0)
        if qty > 0:
            total += 1
            if price * qty > cost_basis:
                wins += 1
    return wins, total


def _running_days(state: dict) -> int:
    df = state["df"]
    span = df["timestamp"].max() - df["timestamp"].min()
    return max(1, int(span.days))


def _first_trade_time(state: dict) -> str:
    hist = state["result"]["trade_history"]
    if hist:
        return pd.Timestamp(hist[0]["timestamp"]).isoformat()
    return pd.Timestamp(state["df"].iloc[0]["timestamp"]).isoformat()
