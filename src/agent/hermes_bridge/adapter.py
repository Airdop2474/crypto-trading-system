"""Hermes 桥接 — 推送系统事件给 Hermes，接收 Hermes 分析结果。

通信方式：
1. 文件 IPC：写 JSON 事件到 data/hermes_events/（Hermes skill 可监听此目录）
2. HTTP 回调：Hermes POST /agent/hermes/callback 返回分析结果

Hermes CLI 检测：自动查找 HERMES_HOME 环境变量或 PATH 中的 `hermes`。
不可用时静默跳过所有推送，不影响系统主流程。
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from src.agent.memory import MemoryKind, get_memory_store

# ---------------------------------------------------------------------------
# Hermes 检测
# ---------------------------------------------------------------------------
HERMES_HOME = Path(os.environ.get("HERMES_HOME", ""))
EVENT_DIR = Path("data/hermes_events")

_HERMES_AVAILABLE = False
_events_enabled = True  # 默认开启，模拟盘数据可关闭

_hermes_bin_path = HERMES_HOME / "venv" / "Scripts" / "hermes.exe"
if _hermes_bin_path.exists():
    _HERMES_AVAILABLE = True
else:
    import shutil
    if shutil.which("hermes"):
        _HERMES_AVAILABLE = True


def hermes_available() -> bool:
    return _HERMES_AVAILABLE


def set_events_enabled(enabled: bool) -> None:
    """开关 Hermes 事件推送。

    模拟盘/生成数据跑批时设为 False，避免大量无意义事件。
    真实交易/人工分析时设为 True。
    """
    global _events_enabled
    _events_enabled = enabled
    logger.debug(f"Hermes events {'enabled' if enabled else 'disabled'}")


def events_enabled() -> bool:
    return _events_enabled


# ---------------------------------------------------------------------------
# 事件写入
# ---------------------------------------------------------------------------

def _write_event(kind: str, payload: dict) -> str:
    """写一条事件到文件（Hermes 通过 skill 监控此目录）。"""
    if not _events_enabled:
        return ""
    EVENT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = EVENT_DIR / f"{kind}_{ts}.json"
    event = {
        "source": "crypto_trading_system",
        "kind": kind,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(event, ensure_ascii=False, default=str), encoding="utf-8")
    logger.debug(f"Hermes 事件已写入: {path.name}")
    return path.name


def push_analysis_request(task: str, strategy_id: str, strategy_name: str, data: dict) -> Optional[str]:
    """推送分析请求给 Hermes（异步，不阻塞）。"""
    if not _HERMES_AVAILABLE:
        return None
    return _write_event("analysis_request", {
        "task": task,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "data": data,
        "callback_url": "http://localhost:8000/agent/hermes/callback",
    })


def push_trade_closed(trade: dict) -> Optional[str]:
    """推送一笔平仓给 Hermes。"""
    if not _HERMES_AVAILABLE:
        return None
    return _write_event("trade_closed", {
        "strategy_id": trade.get("strategy_id", ""),
        "profit": trade.get("profit", 0),
        "symbol": trade.get("symbol", ""),
        "close_time": str(trade.get("time", "")),
    })


def push_risk_event(event_type: str, reason: str, state: str) -> Optional[str]:
    """推送风控事件给 Hermes。"""
    if not _HERMES_AVAILABLE:
        return None
    return _write_event("risk_triggered", {
        "type": event_type,
        "reason": reason,
        "state": state,
    })


def push_daily_summary(summary: dict) -> Optional[str]:
    """推送日结摘要给 Hermes。"""
    if not _HERMES_AVAILABLE:
        return None
    return _write_event("daily_summary", summary)


def push_evolution_completed(evo_result: dict) -> Optional[str]:
    """推送进化完成事件给 Hermes。"""
    if not _HERMES_AVAILABLE:
        return None
    return _write_event("evolution_completed", {
        "strategy_id": evo_result.get("strategy_id", ""),
        "old_sharpe": evo_result.get("old_metrics", {}).get("sharpe_ratio", 0),
        "new_sharpe": evo_result.get("new_metrics", {}).get("sharpe_ratio", 0),
        "guardrail_passed": evo_result.get("guardrail_passed", False),
        "applied": evo_result.get("applied", False),
    })


# ---------------------------------------------------------------------------
# 回调处理（Hermes → 我们的系统）
# ---------------------------------------------------------------------------

_callback_results: Dict[str, dict] = {}
_callback_lock = threading.Lock()


def handle_callback(body: dict) -> dict:
    """处理 Hermes 回调，将分析结果写入 MemoryStore。

    Hermes 侧调用：POST /agent/hermes/callback
    {
        "event_id": "...",
        "status": "completed",
        "summary": "...",
        "details": {...},
        "task": "backtest",
        "strategy_id": "..."
    }
    """
    event_id = body.get("event_id", "")
    status = body.get("status", "error")

    with _callback_lock:
        _callback_results[event_id] = body

    if status == "completed":
        try:
            store = get_memory_store()
            store.store(
                MemoryKind.ANALYSIS,
                content={
                    "source": "hermes",
                    "task": body.get("task", ""),
                    "summary": body.get("summary", ""),
                    "details": body.get("details", {}),
                },
                tags=[body.get("strategy_id", ""), body.get("task", ""), "hermes"],
                source="hermes",
            )
            logger.info(f"Hermes 分析结果已存储: {event_id}")
        except Exception as e:
            logger.warning(f"Hermes 回调存储失败: {e}")

    return {"ok": True, "event_id": event_id}


def get_callback_result(event_id: str) -> Optional[dict]:
    """查询 Hermes 回调结果（前端轮询用）。"""
    with _callback_lock:
        return _callback_results.get(event_id)


def get_status() -> dict:
    """Hermes 连接状态（前端用）。"""
    return {
        "available": _HERMES_AVAILABLE,
        "hermes_home": str(HERMES_HOME) if HERMES_HOME.exists() else "",
        "event_dir": str(EVENT_DIR),
        "pending_events": len(list(EVENT_DIR.glob("*.json"))) if EVENT_DIR.exists() else 0,
        "completed_analyses": len(_callback_results),
    }


__all__ = [
    "hermes_available",
    "push_analysis_request",
    "push_trade_closed",
    "push_risk_event",
    "push_daily_summary",
    "push_evolution_completed",
    "handle_callback",
    "get_callback_result",
    "get_status",
]