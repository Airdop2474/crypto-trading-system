"""Hermes 外部 Agent 桥接

将系统事件推送给 Hermes Agent，接收 Hermes 的分析结果。
Hermes 不可用时静默跳过，不影响系统主流程。
"""

from src.agent.hermes_bridge.adapter import (
    get_callback_result,
    get_status,
    handle_callback,
    hermes_available,
    push_analysis_request,
    push_daily_summary,
    push_evolution_completed,
    push_risk_event,
    push_trade_closed,
    set_events_enabled,
    events_enabled,
)

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
    "set_events_enabled",
    "events_enabled",
]
