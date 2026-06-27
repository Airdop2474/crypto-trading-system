"""
策略配置持久化

将用户在"全部策略"页面配置的参数持久化到 JSON 文件，
供 Paper Trading 守护进程在启动时加载。
"""

import json
from pathlib import Path
from typing import Optional

from src.utils.logger import logger
from src.utils.file_io import atomic_write_json, safe_read_json

_STRATEGY_CONFIG_PATH = Path("data/strategy_configs.json")


def _load() -> dict[str, dict]:
    """读取全部策略配置。"""
    if not _STRATEGY_CONFIG_PATH.exists():
        return {}
    data = safe_read_json(_STRATEGY_CONFIG_PATH, default={})
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, dict]) -> None:
    """写入全部策略配置（原子写）。"""
    atomic_write_json(_STRATEGY_CONFIG_PATH, data)


def get_strategy_config(strategy_type: str) -> Optional[dict]:
    """获取指定策略的保存配置。"""
    return _load().get(strategy_type)


def get_all_strategy_configs() -> dict[str, dict]:
    """获取全部策略配置。"""
    return _load()


def update_strategy_config(strategy_type: str, params: dict) -> dict:
    """更新指定策略配置并持久化。"""
    data = _load()
    if strategy_type not in data:
        data[strategy_type] = {}
    data[strategy_type].update(params)
    _save(data)
    logger.info(f"策略 [{strategy_type}] 配置已保存: {params}")
    return data[strategy_type]


def delete_strategy_config(strategy_type: str) -> bool:
    """删除指定策略配置并持久化。"""
    data = _load()
    if strategy_type not in data:
        return False
    del data[strategy_type]
    _save(data)
    logger.info(f"策略 [{strategy_type}] 配置已删除")
    return True


def rename_strategy_config(old_name: str, new_name: str) -> bool:
    """重命名策略配置的 key（保留参数值）。"""
    data = _load()
    if old_name not in data:
        return False
    data[new_name] = data.pop(old_name)
    _save(data)
    logger.info(f"策略配置 [{old_name}] 已重命名为 [{new_name}]")
    return True
