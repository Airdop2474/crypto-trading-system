"""
策略配置持久化（strategy_config_store）单元测试

覆盖：
- 空配置（文件不存在）
- update_strategy_config：新增 / 更新 / 部分合并
- get_strategy_config / get_all_strategy_configs：读取 / 缺失 key
- delete_strategy_config：删除存在 / 不存在 key
- rename_strategy_config：重命名存在 / 不存在 key、参数保留
- 损坏文件处理：JSON 解析失败不抛异常

每个测试通过 monkeypatch 把 _STRATEGY_CONFIG_PATH 指向 tmp_path 下的独立文件，
避免测试间状态污染。
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.utils.logger import setup_logger

setup_logger(log_level="ERROR")  # 压低 info/warning 日志噪声

from src.api import strategy_config_store as store


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    """每个测试用独立的配置文件，避免测试间状态污染。"""
    file = tmp_path / "strategy_configs.json"
    monkeypatch.setattr(store, "_STRATEGY_CONFIG_PATH", file)
    return file


# --------------------------------------------------------------------------
# 1. 空配置
# --------------------------------------------------------------------------
def test_get_returns_none_when_file_missing(cfg_path):
    """文件不存在时 get_strategy_config 返回 None。"""
    assert not cfg_path.exists()
    assert store.get_strategy_config("grid") is None


def test_get_all_returns_empty_dict_when_file_missing(cfg_path):
    """文件不存在时 get_all_strategy_configs 返回 {}。"""
    assert not cfg_path.exists()
    assert store.get_all_strategy_configs() == {}


# --------------------------------------------------------------------------
# 2. 更新配置 (update_strategy_config)
# --------------------------------------------------------------------------
def test_update_creates_file(cfg_path):
    """新增策略配置后文件被创建。"""
    assert not cfg_path.exists()
    result = store.update_strategy_config("grid", {"upperPrice": 100})
    assert cfg_path.exists(), "配置文件应被创建"
    assert result == {"upperPrice": 100}
    # 文件内容应为合法 JSON
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data == {"grid": {"upperPrice": 100}}


def test_update_preserves_other_keys(cfg_path):
    """更新已有策略配置时保留其他 key（其他策略不受影响）。"""
    store.update_strategy_config("grid", {"upperPrice": 100, "lowerPrice": 50})
    store.update_strategy_config("macd", {"fast": 12})
    # 再次更新 grid，macd 应原样保留
    store.update_strategy_config("grid", {"gridCount": 10})
    all_cfg = store.get_all_strategy_configs()
    assert all_cfg["macd"] == {"fast": 12}
    # grid 旧字段 lowerPrice 仍在
    assert all_cfg["grid"]["lowerPrice"] == 50
    assert all_cfg["grid"]["gridCount"] == 10


def test_update_partial_merge_not_overwrite(cfg_path):
    """部分更新：仅传入部分字段时合并而非整体覆盖。"""
    store.update_strategy_config("grid", {"upperPrice": 100, "lowerPrice": 50})
    # 只更新 upperPrice，lowerPrice 必须保留
    returned = store.update_strategy_config("grid", {"upperPrice": 200})
    cfg = store.get_strategy_config("grid")
    assert cfg == {"upperPrice": 200, "lowerPrice": 50}
    # 返回值应为合并后的完整字典
    assert returned == {"upperPrice": 200, "lowerPrice": 50}


# --------------------------------------------------------------------------
# 3. 读取配置 (get_strategy_config / get_all_strategy_configs)
# --------------------------------------------------------------------------
def test_get_reads_saved_config(cfg_path):
    """正确读取已保存的配置。"""
    store.update_strategy_config("grid", {"upperPrice": 100, "gridCount": 10})
    cfg = store.get_strategy_config("grid")
    assert cfg == {"upperPrice": 100, "gridCount": 10}


def test_get_missing_key_returns_none(cfg_path):
    """读取不存在的 key 返回 None。"""
    store.update_strategy_config("grid", {"upperPrice": 100})
    assert store.get_strategy_config("nonexistent") is None


def test_get_all_reads_all_configs(cfg_path):
    """get_all 返回全部策略配置。"""
    store.update_strategy_config("grid", {"upperPrice": 100})
    store.update_strategy_config("macd", {"fast": 12})
    all_cfg = store.get_all_strategy_configs()
    assert set(all_cfg.keys()) == {"grid", "macd"}
    assert all_cfg["grid"] == {"upperPrice": 100}
    assert all_cfg["macd"] == {"fast": 12}


# --------------------------------------------------------------------------
# 4. 删除配置 (delete_strategy_config)
# --------------------------------------------------------------------------
def test_delete_existing_returns_true(cfg_path):
    """删除存在的 key 返回 True。"""
    store.update_strategy_config("grid", {"upperPrice": 100})
    assert store.delete_strategy_config("grid") is True


def test_delete_removes_key_from_file(cfg_path):
    """删除后文件中该 key 消失，其他 key 保留。"""
    store.update_strategy_config("grid", {"upperPrice": 100})
    store.update_strategy_config("macd", {"fast": 12})
    assert store.delete_strategy_config("grid") is True
    all_cfg = store.get_all_strategy_configs()
    assert "grid" not in all_cfg
    assert "macd" in all_cfg
    assert all_cfg["macd"] == {"fast": 12}


def test_delete_missing_returns_false(cfg_path):
    """删除不存在的 key 返回 False。"""
    assert store.delete_strategy_config("nonexistent") is False


# --------------------------------------------------------------------------
# 5. 重命名 (rename_strategy_config)
# --------------------------------------------------------------------------
def test_rename_existing_returns_true(cfg_path):
    """重命名存在的 key 返回 True。"""
    store.update_strategy_config("grid", {"upperPrice": 100})
    assert store.rename_strategy_config("grid", "grid-v2") is True


def test_rename_preserves_params_and_swaps_keys(cfg_path):
    """重命名后旧 key 消失、新 key 存在、参数完整保留。"""
    params = {"upperPrice": 100, "lowerPrice": 50, "gridCount": 10}
    store.update_strategy_config("grid", params)
    assert store.rename_strategy_config("grid", "grid-v2") is True
    all_cfg = store.get_all_strategy_configs()
    assert "grid" not in all_cfg          # 旧 key 消失
    assert "grid-v2" in all_cfg           # 新 key 存在
    assert all_cfg["grid-v2"] == params   # 参数保留


def test_rename_missing_returns_false(cfg_path):
    """重命名不存在的 key 返回 False。"""
    assert store.rename_strategy_config("nonexistent", "new") is False


# --------------------------------------------------------------------------
# 6. 损坏文件处理
# --------------------------------------------------------------------------
def test_corrupt_file_returns_empty_dict(cfg_path):
    """JSON 解析失败时 get_all 返回空字典，不抛异常。"""
    cfg_path.write_text("{ this is not valid json ", encoding="utf-8")
    assert cfg_path.exists()
    # 不抛异常
    assert store.get_all_strategy_configs() == {}
    # 基于（空）字典，get 也应返回 None
    assert store.get_strategy_config("grid") is None
