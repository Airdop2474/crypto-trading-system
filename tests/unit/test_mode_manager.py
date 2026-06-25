"""
ModeManager 单元测试：覆盖运行模式管理器的初始化、互斥检查、状态查询、
Testnet 硬检查、防重复启动、结果查询、命令构建、状态持久化等。

设计原则：
  - 不依赖真实子进程（mock asyncio.create_subprocess_exec）
  - 文件操作用 tmp_path 替代真实路径（monkeypatch STATE_DIR / PROJECT_ROOT）
  - Testnet 配置通过 monkeypatch config 实现
  - 异步测试使用 @pytest.mark.anyio（项目 pyproject.toml 通过 -p no:asyncio
    禁用了 pytest-asyncio，改用 anyio 插件运行 asyncio 后端）
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from src.api import mode_manager as mm_module
from src.api.mode_manager import (
    TRADING_MODES,
    ModeManager,
    ModeParams,
    ModeStatus,
    RunningMode,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
async def _cleanup_mode_tasks(mgr: ModeManager, key: str):
    """取消并清理某模式的后台 reader / waiter 任务，避免事件循环残留。

    先统一 cancel 所有任务，再逐一 await，确保不会有任务在 cancel 之前
    被事件调度执行（避免 waiter 修改状态）。
    """
    st = mgr._modes[key]
    tasks = list(st._reader_tasks) + list(st._waiter_tasks)
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    st._reader_tasks = []
    st._waiter_tasks = []
    st.processes = []
    st.pids = []


def _make_mock_process(pid: int = 99999):
    """构造一个 mock 子进程对象，满足 start_mode / _read_output / _wait_for_exit 的接口。"""
    proc = MagicMock()
    proc.pid = pid
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(return_value=b"")  # EOF → reader 立即退出
    proc.wait = AsyncMock(return_value=0)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return proc


def _arg_value(cmd: list[str], flag: str) -> str | None:
    """从命令参数列表中取出 --flag 后面紧跟的值，找不到返回 None。"""
    if flag in cmd:
        idx = cmd.index(flag)
        if idx + 1 < len(cmd):
            return cmd[idx + 1]
    return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def manager(monkeypatch, tmp_path):
    """Fresh ModeManager，STATE_DIR 和 PROJECT_ROOT 均隔离到 tmp_path。"""
    state_dir = tmp_path / "mode_states"
    monkeypatch.setattr(mm_module, "STATE_DIR", state_dir)
    monkeypatch.setattr(mm_module, "PROJECT_ROOT", tmp_path)
    return ModeManager()


# ===========================================================================
# 1. ModeManager 初始化
# ===========================================================================
class TestModeManagerInit:
    def test_all_modes_idle_after_init(self, manager):
        """初始化后所有模式状态均为 IDLE。"""
        for mode in RunningMode:
            st = manager._modes[mode.value]
            assert st.status == ModeStatus.IDLE, f"{mode.value} 应为 IDLE"

    def test_state_dir_exists_after_init(self, manager, tmp_path):
        """STATE_DIR 目录在初始化后被创建（__init__ 调用 mkdir）。"""
        assert mm_module.STATE_DIR.exists()
        assert mm_module.STATE_DIR == tmp_path / "mode_states"

    def test_modes_dict_has_exactly_three_modes(self, manager):
        """_modes 字典恰好包含 3 个交易模式。"""
        assert set(manager._modes.keys()) == {m.value for m in RunningMode}
        assert len(manager._modes) == 3


# ===========================================================================
# 2. 互斥检查 (_check_mutual_exclusion)
# ===========================================================================
class TestMutualExclusion:
    def test_data_download_not_checked(self, manager):
        """data_download 不在 TRADING_MODES 中，不受互斥限制。"""
        # 即使所有交易模式都在运行，data_download 也不被拦截
        for mode in RunningMode:
            manager._modes[mode.value].status = ModeStatus.RUNNING
        assert manager._check_mutual_exclusion("data_download") is None

    def test_no_conflict_when_all_idle(self, manager):
        """所有模式 IDLE 时，任何交易模式都不受互斥限制。"""
        for mode in RunningMode:
            assert manager._check_mutual_exclusion(mode.value) is None

    def test_replay_running_blocks_live_and_testnet(self, manager):
        """replay_paper 运行时，live_paper 和 testnet_live 被拦截。"""
        manager._modes["replay_paper"].status = ModeStatus.RUNNING

        err_live = manager._check_mutual_exclusion("live_paper")
        assert err_live is not None
        assert "replay_paper" in err_live

        err_testnet = manager._check_mutual_exclusion("testnet_live")
        assert err_testnet is not None
        assert "replay_paper" in err_testnet

        # replay_paper 自身不受自身互斥影响
        assert manager._check_mutual_exclusion("replay_paper") is None

    def test_live_running_blocks_replay_and_testnet(self, manager):
        """live_paper 运行时，replay_paper 和 testnet_live 被拦截。"""
        manager._modes["live_paper"].status = ModeStatus.RUNNING

        assert manager._check_mutual_exclusion("replay_paper") is not None
        assert manager._check_mutual_exclusion("testnet_live") is not None
        assert "live_paper" in manager._check_mutual_exclusion("replay_paper")

    @pytest.mark.anyio
    async def test_start_blocked_when_another_trading_mode_running(self, manager):
        """一个交易模式运行时，通过 start_mode 启动另一个交易模式应返回 error。"""
        manager._modes["replay_paper"].status = ModeStatus.RUNNING

        result = await manager.start_mode(RunningMode.LIVE_PAPER, ModeParams())
        assert "error" in result
        assert "replay_paper" in result["error"]
        # live_paper 应仍为 IDLE（未被启动）
        assert manager._modes["live_paper"].status == ModeStatus.IDLE


# ===========================================================================
# 3. 状态查询 (get_status / get_all_status)
# ===========================================================================
class TestStatusQuery:
    def test_initial_status_fields(self, manager):
        """初始状态返回正确的 status / pid / startedAt 字段。"""
        for mode in RunningMode:
            d = manager.get_status(mode)
            assert d["mode"] == mode.value
            assert d["status"] == "idle"
            assert d["pid"] is None          # 初始无进程
            assert d["startedAt"] is None     # 初始无启动时间
            assert d["uptimeSeconds"] is None
            assert d["exitCode"] is None
            assert d["lastLogLine"] is None
            assert d["params"] is None

    def test_get_all_status_returns_three(self, manager):
        """get_all_status 返回 3 个模式的状态。"""
        all_status = manager.get_all_status()
        assert len(all_status) == 3
        modes_returned = {d["mode"] for d in all_status}
        assert modes_returned == {m.value for m in RunningMode}
        for d in all_status:
            assert d["status"] == "idle"

    def test_status_reflects_running_state(self, manager):
        """手动设置 RUNNING 后，status_dict 反映正确的 pid / startedAt。"""
        key = "replay_paper"
        st = manager._modes[key]
        st.status = ModeStatus.RUNNING
        st.pids = [12345]
        st.pid = 12345
        st.started_at = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

        d = manager.get_status(RunningMode.REPLAY_PAPER)
        assert d["status"] == "running"
        assert d["pid"] == [12345]
        assert d["startedAt"] is not None
        assert d["uptimeSeconds"] is not None  # RUNNING 时计算 uptime


# ===========================================================================
# 4. Testnet 硬检查
# ===========================================================================
class TestTestnetHardCheck:
    @pytest.mark.anyio
    async def test_testnet_disabled_returns_error(self, manager, monkeypatch):
        """BINANCE_TESTNET=False 时启动 testnet 返回 error。"""
        from src.utils.config import config

        monkeypatch.setattr(config, "BINANCE_TESTNET", False)
        monkeypatch.setattr(config, "BINANCE_API_KEY", "some_key")
        monkeypatch.setattr(config, "BINANCE_SECRET", "some_secret")

        result = await manager.start_mode(RunningMode.TESTNET_LIVE, ModeParams())
        assert "error" in result
        assert "BINANCE_TESTNET" in result["error"]

    @pytest.mark.anyio
    async def test_testnet_placeholder_api_key_returns_error(self, manager, monkeypatch):
        """API_KEY 仍为占位符时返回 error。"""
        from src.utils.config import config

        monkeypatch.setattr(config, "BINANCE_TESTNET", True)
        monkeypatch.setattr(config, "BINANCE_API_KEY", "your_binance_testnet_key")
        monkeypatch.setattr(config, "BINANCE_SECRET", "some_secret")

        result = await manager.start_mode(RunningMode.TESTNET_LIVE, ModeParams())
        assert "error" in result
        assert "API_KEY" in result["error"]

    @pytest.mark.anyio
    async def test_testnet_empty_api_key_returns_error(self, manager, monkeypatch):
        """API_KEY 为空时返回 error。"""
        from src.utils.config import config

        monkeypatch.setattr(config, "BINANCE_TESTNET", True)
        monkeypatch.setattr(config, "BINANCE_API_KEY", "")
        monkeypatch.setattr(config, "BINANCE_SECRET", "some_secret")

        result = await manager.start_mode(RunningMode.TESTNET_LIVE, ModeParams())
        assert "error" in result
        assert "API_KEY" in result["error"]

    @pytest.mark.anyio
    async def test_testnet_placeholder_secret_returns_error(self, manager, monkeypatch):
        """SECRET 仍为占位符时返回 error。"""
        from src.utils.config import config

        monkeypatch.setattr(config, "BINANCE_TESTNET", True)
        monkeypatch.setattr(config, "BINANCE_API_KEY", "real_key")
        monkeypatch.setattr(config, "BINANCE_SECRET", "your_binance_testnet_secret")

        result = await manager.start_mode(RunningMode.TESTNET_LIVE, ModeParams())
        assert "error" in result
        assert "SECRET" in result["error"]

    @pytest.mark.anyio
    async def test_testnet_empty_secret_returns_error(self, manager, monkeypatch):
        """SECRET 为空时返回 error。"""
        from src.utils.config import config

        monkeypatch.setattr(config, "BINANCE_TESTNET", True)
        monkeypatch.setattr(config, "BINANCE_API_KEY", "real_key")
        monkeypatch.setattr(config, "BINANCE_SECRET", "")

        result = await manager.start_mode(RunningMode.TESTNET_LIVE, ModeParams())
        assert "error" in result
        assert "SECRET" in result["error"]

    @pytest.mark.anyio
    async def test_testnet_valid_config_starts_successfully(self, manager, monkeypatch):
        """配置完整且有效时，testnet 模式通过硬检查并成功启动（mock 子进程）。"""
        from src.utils.config import config

        monkeypatch.setattr(config, "BINANCE_TESTNET", True)
        monkeypatch.setattr(config, "BINANCE_API_KEY", "real_api_key_abc")
        monkeypatch.setattr(config, "BINANCE_SECRET", "real_secret_xyz")

        proc = _make_mock_process(pid=88888)
        mock_exec = AsyncMock(return_value=proc)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)

        result = await manager.start_mode(RunningMode.TESTNET_LIVE, ModeParams())

        assert "error" not in result
        assert result["status"] == "running"
        assert result["pid"] == [88888]
        assert result["startedAt"] is not None
        assert mock_exec.call_count == 1  # 单策略 → 1 个子进程

        # 清理后台任务
        await _cleanup_mode_tasks(manager, "testnet_live")


# ===========================================================================
# 5. 防止重复启动
# ===========================================================================
class TestPreventDuplicateStart:
    @pytest.mark.anyio
    async def test_start_when_running_returns_error(self, manager):
        """模式 RUNNING 时再次启动返回 error。"""
        manager._modes["replay_paper"].status = ModeStatus.RUNNING

        result = await manager.start_mode(RunningMode.REPLAY_PAPER, ModeParams())
        assert "error" in result
        assert "running" in result["error"].lower() or "RUNNING" in result["error"]

    @pytest.mark.anyio
    async def test_start_when_stopping_returns_error(self, manager):
        """模式 STOPPING 时再次启动返回 error。"""
        manager._modes["live_paper"].status = ModeStatus.STOPPING

        result = await manager.start_mode(RunningMode.LIVE_PAPER, ModeParams())
        assert "error" in result
        assert "stopping" in result["error"].lower() or "STOPPING" in result["error"]

    @pytest.mark.anyio
    async def test_start_when_idle_does_not_return_duplicate_error(self, manager, monkeypatch):
        """模式 IDLE 时启动不返回重复启动 error（使用 mock 子进程）。"""
        proc = _make_mock_process(pid=77777)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))

        result = await manager.start_mode(RunningMode.LIVE_PAPER, ModeParams())
        assert "error" not in result
        assert result["status"] == "running"

        await _cleanup_mode_tasks(manager, "live_paper")


# ===========================================================================
# 6. get_result 无 state 文件
# ===========================================================================
class TestGetResultNoStateFile:
    def test_no_checkpoint_returns_defaults(self, manager):
        """无 checkpoint 文件时返回 available=False 及默认值。"""
        result = manager.get_result(RunningMode.REPLAY_PAPER)

        assert result["available"] is False
        assert result["mode"] == "replay_paper"
        assert result["mode_status"] == "idle"
        assert result["exit_code"] is None
        assert result["symbol"] == "BTC/USDT"
        assert result["initial_capital"] == 10000.0
        assert result["realized_pnl"] == 0.0
        assert result["total_return_pct"] == 0.0
        assert result["final_balance"] == 10000.0
        assert result["total_trades"] == 0
        assert result["win_count"] == 0
        assert result["loss_count"] == 0
        assert result["win_rate"] == 0.0
        assert result["day_count"] == 0
        assert result["last_bar_ts"] is None
        assert result["risk_state"] == "unknown"
        assert result["strategy_paused"] is False
        assert result["strategies"] == []
        assert result["recent_trades"] == []

    def test_no_checkpoint_uses_params_when_set(self, manager):
        """无 checkpoint 但有启动参数时，从 params 取 symbol / initial_capital。"""
        st = manager._modes["live_paper"]
        st.params = {
            "symbol": "ETH/USDT",
            "initial_capital": 50000.0,
        }

        result = manager.get_result(RunningMode.LIVE_PAPER)
        assert result["available"] is False
        assert result["symbol"] == "ETH/USDT"
        assert result["initial_capital"] == 50000.0
        assert result["final_balance"] == 50000.0

    def test_no_checkpoint_for_all_modes(self, manager):
        """所有 3 个模式在无 checkpoint 时都返回 available=False。"""
        for mode in RunningMode:
            result = manager.get_result(mode)
            assert result["available"] is False
            assert result["mode"] == mode.value


# ===========================================================================
# 7. _build_commands
# ===========================================================================
class TestBuildCommands:
    def test_replay_paper_command_structure(self, manager):
        """replay_paper 命令包含正确的参数。"""
        params = ModeParams(
            symbol="BTC/USDT",
            timeframe="4h",
            days=60,
            initial_capital=10000.0,
            market_type="oscillating",
            strategies=["grid"],
        )
        commands = manager._build_commands(RunningMode.REPLAY_PAPER, params)

        assert len(commands) == 1
        cmd = commands[0]

        # 基础命令：python + daemon 脚本
        assert cmd[0] == sys.executable
        assert cmd[1].endswith("run_paper_trading_daemon.py")

        # 公共参数
        assert _arg_value(cmd, "--symbol") == "BTC/USDT"
        assert _arg_value(cmd, "--timeframe") == "4h"
        assert _arg_value(cmd, "--days") == "60"
        assert _arg_value(cmd, "--initial") == "10000.0"

        # replay 特有参数
        assert _arg_value(cmd, "--replay") == "generate"
        assert _arg_value(cmd, "--market-type") == "oscillating"
        assert _arg_value(cmd, "--max-bar-drop-pct") == "0.50"
        assert "--fresh" in cmd  # replay 模式总是添加 --fresh

        # 策略
        assert _arg_value(cmd, "--strategy") == "grid"

        # state-file 包含 mode 和 strategy
        state_file = _arg_value(cmd, "--state-file")
        assert "paper_daemon_state_replay_paper_grid" in state_file

    def test_live_paper_command_structure(self, manager):
        """live_paper 命令包含 --poll-seconds，无 --replay。"""
        params = ModeParams(
            symbol="ETH/USDT",
            timeframe="1h",
            days=30,
            initial_capital=20000.0,
            poll_seconds=120,
            strategies=["grid"],
        )
        commands = manager._build_commands(RunningMode.LIVE_PAPER, params)

        assert len(commands) == 1
        cmd = commands[0]

        assert _arg_value(cmd, "--symbol") == "ETH/USDT"
        assert _arg_value(cmd, "--timeframe") == "1h"
        assert _arg_value(cmd, "--days") == "30"
        assert _arg_value(cmd, "--initial") == "20000.0"
        assert _arg_value(cmd, "--poll-seconds") == "120"
        assert "--replay" not in cmd
        assert "--broker" not in cmd
        assert "--fresh" not in cmd  # fresh=False 时不添加

    def test_testnet_live_command_structure(self, manager):
        """testnet_live 命令包含 --broker exchange 和 --poll-seconds。"""
        params = ModeParams(
            poll_seconds=30,
            strategies=["grid"],
        )
        commands = manager._build_commands(RunningMode.TESTNET_LIVE, params)

        assert len(commands) == 1
        cmd = commands[0]

        assert _arg_value(cmd, "--broker") == "exchange"
        assert _arg_value(cmd, "--poll-seconds") == "30"
        assert "--replay" not in cmd

    def test_multi_strategy_generates_multiple_commands(self, manager):
        """多策略生成多条命令，每条命令的 --strategy 和 --state-file 不同。"""
        params = ModeParams(strategies=["grid", "momentum", "mean_reversion"])
        commands = manager._build_commands(RunningMode.LIVE_PAPER, params)

        assert len(commands) == 3

        strategies_in_cmds = [_arg_value(cmd, "--strategy") for cmd in commands]
        assert strategies_in_cmds == ["grid", "momentum", "mean_reversion"]

        state_files = [_arg_value(cmd, "--state-file") for cmd in commands]
        assert all("live_paper" in sf for sf in state_files)
        assert "grid" in state_files[0]
        assert "momentum" in state_files[1]
        assert "mean_reversion" in state_files[2]

        # 每条命令的公共参数应一致
        for cmd in commands:
            assert _arg_value(cmd, "--symbol") == "BTC/USDT"
            assert _arg_value(cmd, "--poll-seconds") == "60"

    def test_fresh_flag_for_non_replay_modes(self, manager):
        """非 replay 模式下 params.fresh=True 时添加 --fresh。"""
        # live_paper + fresh
        params = ModeParams(fresh=True, strategies=["grid"])
        cmd = manager._build_commands(RunningMode.LIVE_PAPER, params)[0]
        assert "--fresh" in cmd

        # testnet_live + fresh
        cmd = manager._build_commands(RunningMode.TESTNET_LIVE, params)[0]
        assert "--fresh" in cmd

        # fresh=False 时不添加
        params_no_fresh = ModeParams(fresh=False, strategies=["grid"])
        cmd = manager._build_commands(RunningMode.LIVE_PAPER, params_no_fresh)[0]
        assert "--fresh" not in cmd

    def test_replay_csv_overrides_generate(self, manager):
        """replay_paper 模式下 replay_csv 不为空时使用指定 CSV 路径。"""
        params = ModeParams(
            replay_csv="/data/custom.csv",
            strategies=["grid"],
        )
        cmd = manager._build_commands(RunningMode.REPLAY_PAPER, params)[0]
        assert _arg_value(cmd, "--replay") == "/data/custom.csv"

    def test_all_commands_start_with_python_and_script(self, manager):
        """所有命令均以 python 可执行文件和 daemon 脚本开头。"""
        for mode in RunningMode:
            commands = manager._build_commands(mode, ModeParams(strategies=["grid"]))
            for cmd in commands:
                assert cmd[0] == sys.executable
                assert "run_paper_trading_daemon.py" in cmd[1]


# ===========================================================================
# 8. _save_mode_state / _load_mode_state / _clear_mode_state
# ===========================================================================
class TestStatePersistence:
    def test_save_and_load_roundtrip(self, manager):
        """保存后能正确加载所有字段。"""
        key = "replay_paper"
        st = manager._modes[key]
        st.status = ModeStatus.RUNNING
        st.pid = 12345
        st.started_at = datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        st.params = {
            "symbol": "BTC/USDT",
            "initial_capital": 10000.0,
            "strategies": ["grid", "momentum"],
        }

        manager._save_mode_state(key)

        loaded = manager._load_mode_state(key)
        assert loaded is not None
        assert loaded["mode"] == "replay_paper"
        assert loaded["status"] == "running"
        assert loaded["pid"] == 12345
        assert loaded["started_at"] == "2024-06-15T10:30:00+00:00"
        assert loaded["params"]["symbol"] == "BTC/USDT"
        assert loaded["params"]["strategies"] == ["grid", "momentum"]

    def test_save_creates_json_file(self, manager, tmp_path):
        """保存后在 STATE_DIR 下生成 {key}.json 文件。"""
        key = "live_paper"
        st = manager._modes[key]
        st.status = ModeStatus.RUNNING
        st.pid = 99999
        st.started_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        st.params = {"symbol": "ETH/USDT"}

        manager._save_mode_state(key)

        state_file = tmp_path / "mode_states" / f"{key}.json"
        assert state_file.exists()

        # 文件内容是合法 JSON
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["mode"] == "live_paper"

    def test_clear_removes_file(self, manager):
        """清除后状态文件不存在。"""
        key = "testnet_live"
        st = manager._modes[key]
        st.status = ModeStatus.RUNNING
        st.pid = 55555
        st.started_at = datetime(2024, 3, 1, tzinfo=timezone.utc)
        st.params = {"symbol": "BTC/USDT"}

        manager._save_mode_state(key)
        assert manager._load_mode_state(key) is not None  # 文件存在

        manager._clear_mode_state(key)
        assert manager._load_mode_state(key) is None  # 文件已删除

    def test_clear_nonexistent_file_is_noop(self, manager):
        """清除不存在的文件不报错（静默成功）。"""
        # 初始状态无文件
        assert manager._load_mode_state("replay_paper") is None
        # 清除不存在的文件不应抛异常
        manager._clear_mode_state("replay_paper")
        assert manager._load_mode_state("replay_paper") is None

    def test_load_nonexistent_returns_none(self, manager):
        """加载不存在的状态文件返回 None。"""
        for mode in RunningMode:
            assert manager._load_mode_state(mode.value) is None

    def test_save_with_none_started_at(self, manager):
        """started_at 为 None 时保存正确（isoformat 处理 None）。"""
        key = "replay_paper"
        st = manager._modes[key]
        st.status = ModeStatus.IDLE
        st.pid = None
        st.started_at = None
        st.params = None

        manager._save_mode_state(key)
        loaded = manager._load_mode_state(key)
        assert loaded is not None
        assert loaded["started_at"] is None
        assert loaded["pid"] is None
        assert loaded["params"] is None

    def test_roundtrip_all_three_modes(self, manager):
        """对 3 个模式分别保存/加载/清除，验证全流程。"""
        for mode in RunningMode:
            key = mode.value
            st = manager._modes[key]
            st.status = ModeStatus.RUNNING
            st.pid = hash(key) % 100000
            st.started_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
            st.params = {"symbol": key, "initial_capital": 5000.0}

            # 保存 → 加载
            manager._save_mode_state(key)
            loaded = manager._load_mode_state(key)
            assert loaded is not None
            assert loaded["mode"] == key
            assert loaded["status"] == "running"

            # 清除 → 加载返回 None
            manager._clear_mode_state(key)
            assert manager._load_mode_state(key) is None
