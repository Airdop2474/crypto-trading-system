"""
策略状态持久化（归档/启用管理）

独立于 strategy_configs.json（参数存储），本模块只管策略的运行状态：
  - active    : 正常启用，可被 mode_manager 自动启动
  - archived  : 已归档（自动淘汰或手动归档），默认不启动，但用户可显式覆盖
  - disabled  : 手动禁用，语义同 archived（保留两个状态以便区分淘汰来源）

存储位置：data/strategy_status.json
格式：{ "rsi": {"status": "archived", "reason": "Sharpe 0.1 < 阈值 0.3", "archived_at": "2026-06-27T10:00:00"}, ... }

设计原则：
  - 不删除策略，只是标记状态，可随时恢复
  - 独立文件，不污染 strategy_configs.json 的参数数据
  - 未在文件中出现的策略默认为 active
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal

from src.utils.logger import logger
from src.utils.file_io import atomic_write_json, safe_read_json

StrategyStatus = Literal["active", "archived", "disabled"]

_STATUS_PATH = Path("data/strategy_status.json")


def _load() -> dict[str, dict]:
    if not _STATUS_PATH.exists():
        return {}
    data = safe_read_json(_STATUS_PATH, default={})
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, dict]) -> None:
    atomic_write_json(_STATUS_PATH, data)


def get_strategy_status(strategy_type: str) -> StrategyStatus:
    """获取策略状态，未记录则返回 active。"""
    entry = _load().get(strategy_type)
    if not entry:
        return "active"
    return entry.get("status", "active")


def get_strategy_status_detail(strategy_type: str) -> dict:
    """获取策略状态完整信息（含归档原因、时间）。"""
    entry = _load().get(strategy_type)
    if not entry:
        return {"status": "active", "reason": "", "archived_at": ""}
    return {
        "status": entry.get("status", "active"),
        "reason": entry.get("reason", ""),
        "archived_at": entry.get("archived_at", ""),
    }


def get_all_status() -> dict[str, dict]:
    """获取全部策略状态记录。"""
    return _load()


def set_strategy_status(
    strategy_type: str,
    status: StrategyStatus,
    reason: str = "",
) -> dict:
    """设置策略状态并持久化。

    参数：
        strategy_type: 策略短名（如 "rsi"）
        status: active / archived / disabled
        reason: 归档/禁用原因（用于报告与前端展示）
    """
    data = _load()
    data[strategy_type] = {
        "status": status,
        "reason": reason,
        "archived_at": datetime.now().isoformat() if status != "active" else "",
    }
    _save(data)
    logger.info(f"策略 [{strategy_type}] 状态已更新为 {status}" + (f"：{reason}" if reason else ""))
    return data[strategy_type]


def archive_strategy(strategy_type: str, reason: str = "") -> dict:
    """归档策略（快捷方法）。"""
    return set_strategy_status(strategy_type, "archived", reason)


def disable_strategy(strategy_type: str, reason: str = "") -> dict:
    """禁用策略（快捷方法）。"""
    return set_strategy_status(strategy_type, "disabled", reason)


def activate_strategy(strategy_type: str) -> dict:
    """恢复策略为启用状态（快捷方法）。"""
    return set_strategy_status(strategy_type, "active")


def is_strategy_active(strategy_type: str) -> bool:
    """策略是否处于启用状态（active）。archived/disabled 均返回 False。"""
    return get_strategy_status(strategy_type) == "active"


def get_active_strategies(all_keys: list[str]) -> list[str]:
    """从全部策略 key 中筛出 active 的（用于 mode_manager 启动前过滤）。

    参数：
        all_keys: 前端传入的全部要启动的策略 key 列表
    返回：
        过滤掉 archived/disabled 后的策略列表
    """
    status_data = _load()
    return [
        k for k in all_keys
        if status_data.get(k, {}).get("status", "active") == "active"
    ]


def get_archived_strategies() -> list[str]:
    """获取全部已归档/禁用的策略 key（用于报告）。"""
    data = _load()
    return [k for k, v in data.items() if v.get("status") in ("archived", "disabled")]


__all__ = [
    "StrategyStatus",
    "get_strategy_status",
    "get_strategy_status_detail",
    "get_all_status",
    "set_strategy_status",
    "archive_strategy",
    "disable_strategy",
    "activate_strategy",
    "is_strategy_active",
    "get_active_strategies",
    "get_archived_strategies",
]
