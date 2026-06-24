"""
实时纸盘数据聚合器。

从 daemon state 文件（data/paper_daemon_state_{mode}_{strategy}.json）读取
各策略的运行状态，聚合后提供与 service.py 相同格式的数据，
供纵览仪表盘 / 持仓与资产 / 订单成交三个页面使用。

优先级：live_paper > replay_paper > testnet_live
无 state 文件时返回 None，调用方回退到 _build_state() 预跑数据。
"""

import json
import math
from pathlib import Path
from typing import Optional

from src.utils.logger import logger
from src.utils.config import config as _cfg

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"

# 优先检查的模式顺序
_MODE_PRIORITY = ["live_paper", "replay_paper", "testnet_live"]


def _is_mode_running(mode: str) -> bool:
    """检查指定模式是否正在运行（通过 mode_manager 状态）。"""
    try:
        from src.api.mode_manager import mode_manager, ModeStatus
        st = mode_manager._modes.get(mode)
        if st:
            return st.status in (ModeStatus.RUNNING, ModeStatus.STOPPING)
    except Exception:
        pass
    return False


def _find_active_mode() -> Optional[str]:
    """找到有 daemon state 文件的模式（按优先级）。"""
    for mode in _MODE_PRIORITY:
        files = sorted(_DATA_DIR.glob(f"paper_daemon_state_{mode}_*.json"))
        if files:
            return mode
    return None


def _load_all_states() -> list[dict]:
    """加载当前活跃模式的所有策略 state 文件。"""
    mode = _find_active_mode()
    if not mode:
        return []

    files = sorted(_DATA_DIR.glob(f"paper_daemon_state_{mode}_*.json"))
    states = []
    for sf in files:
        try:
            raw = json.loads(sf.read_text(encoding="utf-8"))
            if raw.get("strategy_name"):
                states.append(raw)
        except Exception as e:
            logger.debug(f"读取 state 文件失败 {sf.name}: {e}")
    return states


def has_live_data() -> bool:
    """是否存在实时纸盘数据。"""
    return len(_load_all_states()) > 0


def _get_last_price(states: list[dict]) -> float:
    """从 state 文件获取最新价格（用 risk.prev_close）。"""
    for s in states:
        price = s.get("risk", {}).get("prev_close")
        if price and float(price) > 0:
            return float(price)
    # 回退：从最后一笔订单取价
    for s in states:
        orders = s.get("broker", {}).get("orders", [])
        if orders:
            return float(orders[-1].get("price", 50000))
    return 50000.0


def _get_symbol(states: list[dict]) -> str:
    for s in states:
        sym = s.get("symbol")
        if sym:
            return sym
    return "BTC/USDT"


# ---------------------------------------------------------------------------
# 对外接口：与 service.py 函数返回格式一致
# ---------------------------------------------------------------------------

def account_summary() -> Optional[dict]:
    states = _load_all_states()
    if not states:
        return None

    last_price = _get_last_price(states)
    total_balance = sum(float(s.get("broker", {}).get("balance", 0)) for s in states)
    total_initial = sum(float(s.get("initial_capital", 10000)) for s in states)
    total_realized = sum(float(s.get("runner", {}).get("realized_pnl", 0)) for s in states)

    # 聚合持仓量
    total_position_amount = 0.0
    total_position_cost = 0.0
    for s in states:
        lots = s.get("runner", {}).get("lots", {})
        for lot in lots.values():
            amt = float(lot.get("amount", 0))
            total_position_amount += amt
            total_position_cost += amt * float(lot.get("cost_price", 0))

    position_value = total_position_amount * last_price
    total_equity = total_balance + position_value
    total_pnl = total_equity - total_initial

    return {
        "totalEquity": round(total_equity, 2),
        "availableBalance": round(total_balance, 2),
        "positionValue": round(position_value, 2),
        "unrealizedPnl": round(position_value - total_position_cost, 2) if total_position_amount > 0 else 0.0,
        "todayPnl": round(total_realized, 2),
        "todayPnlPct": round(total_realized / total_initial * 100, 2) if total_initial else 0.0,
        "totalPnl": round(total_pnl, 2),
        "totalPnlPct": round(total_pnl / total_initial * 100, 2) if total_initial else 0.0,
    }


def positions() -> Optional[list[dict]]:
    states = _load_all_states()
    if not states:
        return None

    last_price = _get_last_price(states)
    symbol = _get_symbol(states)

    # 聚合所有策略的 lots 为净持仓
    total_amount = 0.0
    total_cost = 0.0
    for s in states:
        lots = s.get("runner", {}).get("lots", {})
        for lot in lots.values():
            amt = float(lot.get("amount", 0))
            total_amount += amt
            total_cost += amt * float(lot.get("cost_price", 0))

    if total_amount <= 0:
        return []

    avg_cost = total_cost / total_amount if total_amount > 0 else 0
    upnl = total_amount * (last_price - avg_cost)
    return [{
        "id": "pos-btc-usdt",
        "symbol": symbol,
        "side": "buy",
        "size": round(total_amount, 8),
        "entryPrice": round(avg_cost, 2),
        "markPrice": round(last_price, 2),
        "leverage": 1,
        "margin": round(total_cost, 2),
        "unrealizedPnl": round(upnl, 2),
        "unrealizedPnlPct": round(upnl / total_cost * 100, 2) if total_cost else 0.0,
        "liquidationPrice": 0.0,
        "strategyName": "multi-strategy",
    }]


def assets() -> Optional[list[dict]]:
    states = _load_all_states()
    if not states:
        return None

    last_price = _get_last_price(states)
    total_balance = sum(float(s.get("broker", {}).get("balance", 0)) for s in states)

    total_amount = 0.0
    for s in states:
        lots = s.get("runner", {}).get("lots", {})
        for lot in lots.values():
            total_amount += float(lot.get("amount", 0))

    btc_value = total_amount * last_price
    total_value = total_balance + btc_value or 1.0

    out = [{
        "asset": "USDT",
        "total": round(total_balance, 4),
        "available": round(total_balance, 4),
        "inOrder": 0.0,
        "valueUsdt": round(total_balance, 2),
        "allocationPct": round(total_balance / total_value * 100, 2) if total_value else 0.0,
    }]
    if total_amount > 0:
        out.append({
            "asset": "BTC",
            "total": round(total_amount, 8),
            "available": round(total_amount, 8),
            "inOrder": 0.0,
            "valueUsdt": round(btc_value, 2),
            "allocationPct": round(btc_value / total_value * 100, 2) if total_value else 0.0,
        })
    return out


def multi_strategy_result(strategy_id: str) -> Optional[dict]:
    """获取单个策略的运行结果（用于策略详情页）。

    返回格式与前端 MultiStrategyResult 类型对齐：
        statistics: { initial_balance, current_balance, total_trades,
                      total_commission, total_slippage, total_cost, positions }
        open_lots: Record[str, number]
        closed_trades: [{ tag, time, profit }]
        trade_history: [{ order_id, timestamp, symbol, side, order_type,
                          amount, price, commission, slippage, tag, status }]
        signals: []
        realized_pnl: float
    """
    states = _load_all_states()
    if not states:
        return None

    for s in states:
        strat_name = s.get("strategy_name", "unknown")
        symbol = s.get("symbol", "BTC/USDT")
        sid = f"{strat_name}-{symbol.lower().replace('/', '-')}"
        if sid != strategy_id:
            continue

        initial = float(s.get("initial_capital", 10000))
        realized = float(s.get("runner", {}).get("realized_pnl", 0))
        closed = s.get("runner", {}).get("closed_trades", [])
        lots = s.get("runner", {}).get("lots", {})
        balance = float(s.get("broker", {}).get("balance", 0))
        last_price = _get_last_price(states)

        # 统计
        total_commission = sum(
            float(o.get("commission", 0))
            for o in s.get("broker", {}).get("orders", [])
        )
        total_slippage = 0.0  # PaperBroker 滑点已计入 commission

        # open_lots: Record[str, number]
        open_lots = {}
        for tag, lot in lots.items():
            amt = float(lot.get("amount", 0))
            if amt > 0:
                open_lots[tag] = amt

        # closed_trades: [{ tag, time, profit }]
        closed_trades = []
        for t in closed:
            closed_trades.append({
                "tag": str(t.get("tag", "")),
                "time": str(t.get("time", "")),
                "profit": float(t.get("profit", 0)),
            })

        # trade_history: BrokerOrder 格式
        trade_history = []
        for o in s.get("broker", {}).get("orders", []):
            trade_history.append({
                "order_id": o.get("order_id", ""),
                "timestamp": str(o.get("timestamp", "")),
                "symbol": o.get("symbol", symbol),
                "side": o.get("side", ""),
                "order_type": o.get("order_type", "market"),
                "amount": float(o.get("amount", 0)),
                "price": float(o.get("price", 0)),
                "commission": float(o.get("commission", 0)),
                "slippage": 0.0,
                "tag": o.get("tag", ""),
                "status": "filled",
            })

        # positions: 当前持仓量（用于 statistics）
        positions = {tag: amt for tag, amt in open_lots.items()}

        return {
            "symbol": symbol,
            "statistics": {
                "initial_balance": initial,
                "current_balance": round(balance, 2),
                "total_trades": len(trade_history),
                "total_commission": round(total_commission, 4),
                "total_slippage": round(total_slippage, 4),
                "total_cost": round(total_commission + total_slippage, 4),
                "positions": positions,
            },
            "trade_history": trade_history,
            "signals": [],
            "open_lots": open_lots,
            "realized_pnl": round(realized, 2),
            "closed_trades": closed_trades,
        }

    return None


def orders(limit: int = 100, offset: int = 0) -> Optional[dict]:
    states = _load_all_states()
    if not states:
        return None

    # 合并所有策略的 orders
    all_orders = []
    for s in states:
        strat_name = s.get("strategy_name", "unknown")
        for o in s.get("broker", {}).get("orders", []):
            all_orders.append({
                "id": o.get("order_id", ""),
                "time": str(o.get("timestamp", "")),
                "symbol": o.get("symbol", "BTC/USDT"),
                "side": o.get("side", ""),
                "type": o.get("order_type", "market"),
                "price": float(o.get("price", 0)),
                "amount": float(o.get("amount", 0)),
                "filled": float(o.get("amount", 0)),
                "fee": float(o.get("commission", 0)),
                "status": o.get("status", "filled"),
                "strategyName": strat_name,
            })

    # 按时间倒序
    all_orders.sort(key=lambda x: x["time"], reverse=True)
    total = len(all_orders)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    page = all_orders[offset:offset + limit]
    total_fee = sum(o["fee"] for o in all_orders)

    return {
        "items": page,
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
            "total_fee": round(total_fee, 2),
        },
    }


def risk_metrics() -> Optional[dict]:
    states = _load_all_states()
    if not states:
        return None

    last_price = _get_last_price(states)
    total_balance = sum(float(s.get("broker", {}).get("balance", 0)) for s in states)
    total_initial = sum(float(s.get("initial_capital", 10000)) for s in states)
    total_realized = sum(float(s.get("runner", {}).get("realized_pnl", 0)) for s in states)

    total_amount = 0.0
    total_cost = 0.0
    for s in states:
        lots = s.get("runner", {}).get("lots", {})
        for lot in lots.values():
            amt = float(lot.get("amount", 0))
            total_amount += amt
            total_cost += amt * float(lot.get("cost_price", 0))

    current_equity = total_balance + total_amount * last_price
    peak_equity = max(
        float(s.get("risk", {}).get("peak_equity", 0)) for s in states
    ) if states else current_equity

    # 当前回撤
    if peak_equity > 0:
        current_dd = (current_equity - peak_equity) / peak_equity * 100
    else:
        current_dd = 0.0

    # 最大回撤（用 peak_equity 估算）
    max_dd = min(current_dd, 0.0)

    # 从 closed_trades 构建简易权益曲线计算 sharpe
    all_trades = []
    for s in states:
        for t in s.get("runner", {}).get("closed_trades", []):
            all_trades.append(float(t.get("profit", 0)))

    # 简易 sharpe：基于平仓盈亏序列
    if len(all_trades) >= 2:
        import numpy as np
        arr = np.array(all_trades)
        std = float(arr.std())
        sharpe = float(arr.mean() / std * math.sqrt(len(arr))) if std > 0 else 0.0
        # 负盈亏序列
        downside = arr[arr < 0]
        downside_std = float(downside.std()) if len(downside) > 0 else 0.0
        sortino = float(arr.mean() / downside_std * math.sqrt(len(arr))) if downside_std > 0 else 0.0
        volatility = float(std * math.sqrt(len(arr)) / total_initial * 100) if total_initial else 0.0
    else:
        sharpe = 0.0
        sortino = 0.0
        volatility = 0.0

    annual_return = (total_realized / total_initial * 100) if total_initial else 0.0

    return {
        "max_drawdown": max_dd / 100,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "volatility": round(volatility, 2),
        "annual_return": round(annual_return, 2),
        "current_drawdown": round(current_dd, 2),
        "equity_peak": round(peak_equity, 2),
        "equity_current": round(current_equity, 2),
        "max_drawdown_duration": 0,
    }


def pnl_history() -> Optional[list[dict]]:
    """从 closed_trades 构建权益曲线。"""
    states = _load_all_states()
    if not states:
        return None

    total_initial = sum(float(s.get("initial_capital", 10000)) for s in states)

    # 合并所有策略的 closed_trades，按时间排序
    all_trades = []
    for s in states:
        strat = s.get("strategy_name", "unknown")
        for t in s.get("runner", {}).get("closed_trades", []):
            all_trades.append({
                "time": str(t.get("time", "")),
                "profit": float(t.get("profit", 0)),
                "strategy": strat,
            })
    all_trades.sort(key=lambda x: x["time"])

    # 构建累计权益曲线
    out = []
    equity = total_initial
    for t in all_trades:
        equity += t["profit"]
        out.append({
            "date": t["time"],
            "equity": round(equity, 2),
            "pnl": round(t["profit"], 2),
            "cumulativePnl": round(equity - total_initial, 2),
        })
    return out


def strategy_performance() -> Optional[list[dict]]:
    states = _load_all_states()
    if not states:
        return None

    from src.strategy.registry import get_strategy_label

    out = []
    for s in states:
        strat_name = s.get("strategy_name", "unknown")
        closed = s.get("runner", {}).get("closed_trades", [])
        wins = sum(1 for t in closed if float(t.get("profit", 0)) > 0)
        total = len(closed)
        realized = float(s.get("runner", {}).get("realized_pnl", 0))
        out.append({
            "name": get_strategy_label(strat_name) or strat_name,
            "pnl": round(realized, 2),
            "trades": total,
            "winRate": round(wins / total * 100, 2) if total else 0.0,
        })
    return out


def strategies() -> Optional[list[dict]]:
    states = _load_all_states()
    if not states:
        return None

    from src.strategy.registry import get_strategy_label

    # 判断当前模式是否在运行
    active_mode = _find_active_mode()
    mode_running = _is_mode_running(active_mode) if active_mode else False

    out = []
    for s in states:
        strat_name = s.get("strategy_name", "unknown")
        symbol = s.get("symbol", "BTC/USDT")
        initial = float(s.get("initial_capital", 10000))
        realized = float(s.get("runner", {}).get("realized_pnl", 0))
        closed = s.get("runner", {}).get("closed_trades", [])
        day_count = int(s.get("day_count", 0))
        paused = bool(s.get("strategy", {}).get("paused", False))
        risk_state = s.get("risk", {}).get("state", "unknown")

        # 模式未运行时，状态显示 stopped
        if not mode_running:
            status = "stopped"
        elif paused:
            status = "paused"
        elif risk_state == "ACTIVE":
            status = "running"
        else:
            status = risk_state.lower()

        out.append({
            "id": f"{strat_name}-{symbol.lower().replace('/', '-')}",
            "name": get_strategy_label(strat_name) or strat_name,
            "type": strat_name,
            "symbol": symbol,
            "status": status,
            "pnl": round(realized, 2),
            "pnlPct": round(realized / initial * 100, 2) if initial else 0.0,
            "investment": initial,
            "runningDays": day_count,
            "createdAt": "",
        })
    return out


def multi_strategy_summary() -> Optional[dict]:
    states = _load_all_states()
    if not states:
        return None

    total_realized = sum(float(s.get("runner", {}).get("realized_pnl", 0)) for s in states)
    total_trades = sum(len(s.get("runner", {}).get("closed_trades", [])) for s in states)

    from src.strategy.registry import get_strategy_label
    strat_list = []
    for s in states:
        strat_name = s.get("strategy_name", "unknown")
        realized = float(s.get("runner", {}).get("realized_pnl", 0))
        strat_list.append({
            "name": get_strategy_label(strat_name) or strat_name,
            "pnl": round(realized, 2),
        })

    return {
        "totalRealizedPnl": round(total_realized, 2),
        "totalClosedTrades": total_trades,
        "strategiesCount": len(states),
        "strategies": strat_list,
    }


def multi_strategy_details() -> Optional[list[dict]]:
    states = _load_all_states()
    if not states:
        return None

    out = []
    for s in states:
        strat_name = s.get("strategy_name", "unknown")
        symbol = s.get("symbol", "BTC/USDT")
        realized = float(s.get("runner", {}).get("realized_pnl", 0))
        closed = s.get("runner", {}).get("closed_trades", [])
        wins = sum(1 for t in closed if float(t.get("profit", 0)) > 0)
        total_closed = len(closed)
        lots = s.get("runner", {}).get("lots", {})
        initial = float(s.get("initial_capital", 10000))

        out.append({
            "strategyId": f"{strat_name}-{symbol.lower().replace('/', '-')}",
            "symbol": symbol,
            "realizedPnl": round(realized, 2),
            "totalTrades": total_closed,
            "winRate": round(wins / total_closed * 100, 2) if total_closed else 0.0,
            "openLots": len(lots),
            "closedTrades": total_closed,
            "initialCapital": initial,
            "returnPct": round(realized / initial * 100, 2) if initial else 0.0,
        })
    return out


def positions_history(limit: int = 200) -> Optional[list[dict]]:
    states = _load_all_states()
    if not states:
        return None

    from src.strategy.registry import get_strategy_label

    all_closed = []
    for s in states:
        strat_name = s.get("strategy_name", "unknown")
        symbol = s.get("symbol", "BTC/USDT")
        initial = float(s.get("initial_capital", 10000))
        for t in s.get("runner", {}).get("closed_trades", []):
            profit = float(t.get("profit", 0))
            all_closed.append({
                "id": f"{strat_name}-{t.get('tag', '')}-{t.get('time', '')}",
                "strategy_id": strat_name,
                "strategy_name": get_strategy_label(strat_name) or strat_name,
                "symbol": symbol,
                "tag": str(t.get("tag", "")),
                "open_time": "",
                "close_time": str(t.get("time", "")),
                "profit": round(profit, 2),
                "profit_pct": round(profit / initial * 100, 2) if initial else 0.0,
                "hold_bars": 0,
            })

    # 按时间倒序
    all_closed.sort(key=lambda x: x["close_time"], reverse=True)
    return all_closed[:limit]


# ---------------------------------------------------------------------------
# AI 分析数据构造：从 daemon state 构造 analyzer 所需的参数格式
# ---------------------------------------------------------------------------

def _build_equity_curve(states: list[dict]) -> list[dict]:
    """从 closed_trades 构建累计权益曲线。"""
    total_initial = sum(float(s.get("initial_capital", 10000)) for s in states)

    all_trades = []
    for s in states:
        for t in s.get("runner", {}).get("closed_trades", []):
            all_trades.append({
                "time": str(t.get("time", "")),
                "profit": float(t.get("profit", 0)),
            })
    all_trades.sort(key=lambda x: x["time"])

    curve = []
    equity = total_initial
    for t in all_trades:
        equity += t["profit"]
        curve.append({"equity": round(equity, 2)})
    return curve


def build_analysis_data(task: str) -> Optional[dict]:
    """为 AI 分析构造所需数据，无 daemon state 时返回 None。

    返回格式与 app.py 中各 task 分支所需参数对齐：
        backtest:        {"results": dict, "metrics": dict, "strategy_name": str}
        trade_attribution: {"trades": list[dict]}
        weekly_review:   {"paper_report": dict, "trade_history": list}
        risk_checklist:  {"checklist": dict}
        param_sensitivity: {"base_params": dict}
    """
    states = _load_all_states()
    if not states:
        return None

    last_price = _get_last_price(states)
    symbol = _get_symbol(states)
    total_initial = sum(float(s.get("initial_capital", 10000)) for s in states)
    total_balance = sum(float(s.get("broker", {}).get("balance", 0)) for s in states)
    total_realized = sum(float(s.get("runner", {}).get("realized_pnl", 0)) for s in states)

    # 聚合持仓
    total_amount = 0.0
    total_cost = 0.0
    for s in states:
        lots = s.get("runner", {}).get("lots", {})
        for lot in lots.values():
            amt = float(lot.get("amount", 0))
            total_amount += amt
            total_cost += amt * float(lot.get("cost_price", 0))

    position_value = total_amount * last_price
    total_equity = total_balance + position_value
    total_return = (total_equity - total_initial) / total_initial if total_initial else 0.0

    # 合并所有 closed_trades
    all_closed = []
    for s in states:
        for t in s.get("runner", {}).get("closed_trades", []):
            all_closed.append({
                "profit": float(t.get("profit", 0)),
                "time": str(t.get("time", "")),
                "tag": str(t.get("tag", "")),
                "pnl": float(t.get("profit", 0)),
            })

    wins = [t for t in all_closed if t["profit"] > 0]
    losses = [t for t in all_closed if t["profit"] < 0]
    win_rate = len(wins) / len(all_closed) if all_closed else 0.0

    # 合并所有 orders 作为 trade_history
    all_orders = []
    for s in states:
        strat_name = s.get("strategy_name", "unknown")
        for o in s.get("broker", {}).get("orders", []):
            all_orders.append({
                "order_id": o.get("order_id", ""),
                "timestamp": str(o.get("timestamp", "")),
                "symbol": o.get("symbol", symbol),
                "side": o.get("side", ""),
                "price": float(o.get("price", 0)),
                "amount": float(o.get("amount", 0)),
                "commission": float(o.get("commission", 0)),
                "strategy": strat_name,
            })

    # 权益曲线
    equity_curve = _build_equity_curve(states)

    # 简易风险指标
    import numpy as np
    if len(all_closed) >= 2:
        arr = np.array([t["profit"] for t in all_closed])
        std = float(arr.std())
        sharpe = float(arr.mean() / std * np.sqrt(len(arr))) if std > 0 else 0.0
        downside = arr[arr < 0]
        downside_std = float(downside.std()) if len(downside) > 0 else 0.0
        sortino = float(arr.mean() / downside_std * np.sqrt(len(arr))) if downside_std > 0 else 0.0
        gross_profit = sum(t["profit"] for t in wins)
        gross_loss = abs(sum(t["profit"] for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
    else:
        sharpe = 0.0
        sortino = 0.0
        profit_factor = 0.0

    # 最大回撤
    if equity_curve:
        equities = [e["equity"] for e in equity_curve]
        equities.insert(0, total_initial)
        peak = equities[0]
        max_dd = 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
    else:
        max_dd = 0.0

    # peak equity
    peak_equity = max(
        float(s.get("risk", {}).get("peak_equity", total_equity)) for s in states
    ) if states else total_equity

    if task == "backtest":
        results = {
            "total_return": total_return,
            "trades": all_closed,
            "equity_curve": equity_curve,
            "statistics": {
                "total_trades": len(all_closed),
                "total_return": total_return,
            },
            "closed_trades": all_closed,
        }
        metrics = {
            "total_return": total_return,
            "win_rate": win_rate,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown": max_dd,
            "profit_factor": profit_factor,
            "kelly_criterion": 0.0,
        }
        strategy_name = ", ".join(
            s.get("strategy_name", "unknown") for s in states
        )
        return {
            "results": results,
            "metrics": metrics,
            "strategy_name": strategy_name,
        }

    elif task == "trade_attribution":
        return {"trades": all_closed}

    elif task == "weekly_review":
        paper_report = {
            "account": {
                "total_value": round(total_equity, 2),
                "initial_balance": total_initial,
                "cash": round(total_balance, 2),
                "position_value": round(position_value, 2),
                "total_return": total_return,
            },
            "pnl": {
                "realized": round(total_realized, 2),
                "unrealized": round(position_value - total_cost, 2) if total_amount > 0 else 0.0,
            },
            "trades": {
                "total": len(all_orders),
            },
            "cost_analysis": {
                "total_cost": sum(o.get("commission", 0) for o in all_orders),
            },
        }
        return {
            "paper_report": paper_report,
            "trade_history": all_orders,
        }

    elif task == "risk_checklist":
        day_count = max(int(s.get("day_count", 0)) for s in states) if states else 0
        consecutive_losses = max(
            int(s.get("risk", {}).get("consecutive_losses", 0)) for s in states
        ) if states else 0
        return {
            "checklist": {
                "paper_trading_days": day_count,
                "risk_tests_passed": True,
                "api_key_restricted": False,
                "initial_capital": total_initial,
                "max_drawdown": max_dd,
                "consecutive_losses": consecutive_losses,
                "data_quality_score": 1.0,
                "peak_equity": peak_equity,
                "current_equity": total_equity,
            }
        }

    elif task == "param_sensitivity":
        # 从第一个策略取参数
        base_params = {}
        for s in states:
            strat_name = s.get("strategy_name", "grid")
            bounds = s.get("bounds", {})
            if bounds:
                base_params["lower_price"] = bounds.get("lower", 0)
                base_params["upper_price"] = bounds.get("upper", 0)
            base_params["strategy"] = strat_name
            break
        return {"base_params": base_params}

    return None


def pnl_distribution(bins: int = 10) -> Optional[dict]:
    """盈亏分布直方图 + 胜率/盈亏比统计（从实时纸盘 closed_trades）。"""
    states = _load_all_states()
    if not states:
        return None

    import numpy as np

    # 合并所有 closed_trades 的 profit
    profits_list = []
    for s in states:
        for t in s.get("runner", {}).get("closed_trades", []):
            profits_list.append(float(t.get("profit", 0)))

    if not profits_list:
        return {"bins": [], "stats": {
            "total": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "avg_profit": 0.0, "avg_loss": 0.0,
            "profit_factor": 0.0, "best": 0.0, "worst": 0.0,
        }}

    profits = np.array(profits_list)
    bins = max(2, min(bins, 50))

    # 直方图分箱
    if len(profits) > 1:
        lo, hi = float(profits.min()), float(profits.max())
        if lo == hi:
            lo, hi = lo - 1, hi + 1
        edges = np.linspace(lo, hi, bins + 1)
        counts, _ = np.histogram(profits, bins=edges)
    else:
        edges = np.array([min(profits[0] - 1, -1), 0, max(profits[0] + 1, 1)])
        counts = np.array([0, 1]) if profits[0] != 0 else np.array([1, 0])

    bin_list = []
    for i in range(len(counts)):
        left = float(edges[i])
        right = float(edges[i + 1])
        bin_list.append({
            "range": f"{left:.0f}~{right:.0f}",
            "count": int(counts[i]),
            "label": "盈利" if right > 0 and left >= 0 else "亏损" if right <= 0 else "混合",
        })

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
        "profit_factor": (total_profit / total_loss) if total_loss > 0 else (999.99 if total_profit > 0 else 0.0),
        "best": float(profits.max()) if len(profits) else 0.0,
        "worst": float(profits.min()) if len(profits) else 0.0,
    }

    return {"bins": bin_list, "stats": stats}


def portfolio_heat() -> Optional[dict]:
    """读取组合热力（Portfolio Heat）共享文件。

    从 data/portfolio_heat.json 读取所有策略的持仓热力，
    聚合后返回总热力、各策略明细。

    无共享文件时返回 None（调用方可知热力监控未启用）。
    """
    heat_file = _DATA_DIR / "portfolio_heat.json"
    if not heat_file.exists():
        return None

    try:
        data = json.loads(heat_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug(f"读取 portfolio_heat.json 失败: {e}")
        return None

    strategies = data.get("strategies", {})
    if not strategies:
        return None

    from src.risk.portfolio_heat import DEFAULT_MAX_HEAT

    total_heat = sum(float(v.get("heat", 0)) for v in strategies.values())
    max_heat = DEFAULT_MAX_HEAT

    return {
        "total_heat": round(total_heat, 4),
        "max_heat": max_heat,
        "heat_pct": round(total_heat / max_heat * 100, 1) if max_heat > 0 else 0,
        "strategies": {
            k: {
                "heat": round(float(v.get("heat", 0)), 4),
                "position_value": round(float(v.get("position_value", 0)), 2),
                "position_risk": round(float(v.get("position_risk", 0)), 2),
                "updated_at": v.get("updated_at"),
            }
            for k, v in strategies.items()
        },
        "updated_at": data.get("updated_at"),
    }
