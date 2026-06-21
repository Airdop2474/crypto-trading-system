"""
运行模式管理器：通过 asyncio 子进程管理四种运行模式的生命周期。

四种模式：
  data_download  — 从 Binance 下载 OHLCV 数据并生成质量报告
  replay_paper   — 历史/生成数据加速回放纸盘交易
  live_paper     — 实时轮询 Binance 行情，模拟纸盘交易
  testnet_live   — 在 Binance Testnet 上下真实市价单

安全规则：
  - 三个交易模式互斥（同时只能跑一个），数据下载不受限
  - Testnet 模式硬检查：BINANCE_TESTNET=true + API Key/Secret 存在
  - 防止重复启动
"""

import asyncio
import json
import os
import sys
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = PROJECT_ROOT / "data" / "mode_states"
TRADING_MODES = {"replay_paper", "live_paper", "testnet_live"}
_STOP_TIMEOUT = 15  # 秒：等待子进程优雅退出
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------
class RunningMode(str, Enum):
    DATA_DOWNLOAD = "data_download"
    REPLAY_PAPER = "replay_paper"
    LIVE_PAPER = "live_paper"
    TESTNET_LIVE = "testnet_live"


class ModeStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


# ---------------------------------------------------------------------------
# 参数模型
# ---------------------------------------------------------------------------
class ModeParams(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "4h"
    days: int = Field(default=60, ge=1, le=365)
    initial_capital: float = Field(default=10000.0, ge=100, le=1_000_000)
    poll_seconds: int = Field(default=60, ge=10, le=600)
    replay_csv: str | None = None
    fresh: bool = False


# ---------------------------------------------------------------------------
# 内部状态
# ---------------------------------------------------------------------------
@dataclass
class _ModeState:
    status: ModeStatus = ModeStatus.IDLE
    process: asyncio.subprocess.Process | None = None
    pid: int | None = None
    started_at: datetime | None = None
    exit_code: int | None = None
    last_log_line: str | None = None
    params: dict | None = None
    _reader_task: asyncio.Task | None = None
    _waiter_task: asyncio.Task | None = None


# ---------------------------------------------------------------------------
# ModeManager
# ---------------------------------------------------------------------------
class ModeManager:
    def __init__(self):
        self._modes: dict[str, _ModeState] = {
            m.value: _ModeState() for m in RunningMode
        }
        STATE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------
    async def start_mode(self, mode: RunningMode, params: ModeParams) -> dict:
        """启动指定模式，返回状态或错误。"""
        key = mode.value

        # 防止重复启动
        st = self._modes[key]
        if st.status in (ModeStatus.RUNNING, ModeStatus.STOPPING):
            return {"error": f"模式 '{key}' 当前状态为 {st.status.value}，无法启动"}

        # 互斥检查
        mutex_err = self._check_mutual_exclusion(key)
        if mutex_err:
            return {"error": mutex_err}

        # Testnet 硬检查
        if mode == RunningMode.TESTNET_LIVE:
            from src.utils.config import config
            if not config.BINANCE_TESTNET:
                return {"error": "BINANCE_TESTNET 必须为 true 才能启动 Testnet 模式"}
            if not config.BINANCE_API_KEY or config.BINANCE_API_KEY == "your_binance_testnet_key":
                return {"error": "BINANCE_API_KEY 未配置或仍为占位符"}
            if not config.BINANCE_SECRET or config.BINANCE_SECRET == "your_binance_testnet_secret":
                return {"error": "BINANCE_SECRET 未配置或仍为占位符"}

        # 构建命令
        cmd = self._build_command(mode, params)

        # 启动子进程
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
            )
        except Exception as e:
            logger.error(f"启动子进程失败 [{key}]: {e}")
            return {"error": f"启动子进程失败: {e}"}

        # 更新状态
        st.status = ModeStatus.RUNNING
        st.process = proc
        st.pid = proc.pid
        st.started_at = datetime.now(timezone.utc)
        st.exit_code = None
        st.last_log_line = None
        st.params = params.model_dump()

        # 持久化
        self._save_mode_state(key)

        # 启动日志读取 + 进程等待协程
        st._reader_task = asyncio.create_task(self._read_output(proc, mode))
        st._waiter_task = asyncio.create_task(self._wait_for_exit(proc, mode))

        logger.info(f"模式 [{key}] 已启动, PID={proc.pid}, 命令={' '.join(cmd)}")
        return self._status_dict(key)

    async def stop_mode(self, mode: RunningMode) -> dict:
        """停止指定模式，优雅退出。"""
        key = mode.value
        st = self._modes[key]

        if st.status != ModeStatus.RUNNING or st.process is None:
            return {"error": f"模式 '{key}' 当前未在运行"}

        st.status = ModeStatus.STOPPING
        logger.info(f"模式 [{key}] 正在停止, PID={st.pid}")

        # 发送终止信号
        try:
            st.process.terminate()
        except ProcessLookupError:
            pass

        # 等待退出
        try:
            await asyncio.wait_for(st.process.wait(), timeout=_STOP_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"模式 [{key}] 超时未退出, 强制终止")
            try:
                st.process.kill()
            except ProcessLookupError:
                pass

        st.status = ModeStatus.IDLE
        st.process = None
        st.pid = None
        st.started_at = None
        self._clear_mode_state(key)

        logger.info(f"模式 [{key}] 已停止")
        return self._status_dict(key)

    def get_status(self, mode: RunningMode) -> dict:
        return self._status_dict(mode.value)

    def get_all_status(self) -> list[dict]:
        return [self._status_dict(m.value) for m in RunningMode]

    async def recover_on_startup(self):
        """API 启动时恢复：检查磁盘上的状态文件，标记孤儿进程。"""
        for mode in RunningMode:
            key = mode.value
            state = self._load_mode_state(key)
            if not state or state.get("status") != "running":
                continue
            pid = state.get("pid")
            if pid and self._pid_alive(pid):
                logger.warning(f"模式 [{key}] 有孤儿进程 PID={pid}，标记为 ERROR")
                self._modes[key].status = ModeStatus.ERROR
                self._modes[key].exit_code = -1
                self._modes[key].pid = pid
                self._modes[key].started_at = (
                    datetime.fromisoformat(state["started_at"])
                    if state.get("started_at") else None
                )
                self._modes[key].params = state.get("params")
            else:
                logger.info(f"模式 [{key}] 的旧进程 PID={pid} 已不存在，重置为 idle")
                self._clear_mode_state(key)

    async def stop_all(self):
        """优雅停止所有运行中的模式（lifespan shutdown 调用）。"""
        for mode in RunningMode:
            st = self._modes[mode.value]
            if st.status == ModeStatus.RUNNING and st.process is not None:
                try:
                    st.process.terminate()
                except ProcessLookupError:
                    pass
        # 等待所有进程退出
        for mode in RunningMode:
            st = self._modes[mode.value]
            if st.process is not None:
                try:
                    await asyncio.wait_for(st.process.wait(), timeout=_STOP_TIMEOUT)
                except asyncio.TimeoutError:
                    try:
                        st.process.kill()
                    except ProcessLookupError:
                        pass
                st.status = ModeStatus.IDLE
                st.process = None
                self._clear_mode_state(mode.value)
        logger.info("所有运行模式已停止")

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _check_mutual_exclusion(self, key: str) -> str | None:
        if key not in TRADING_MODES:
            return None
        for m in TRADING_MODES:
            if m != key and self._modes[m].status == ModeStatus.RUNNING:
                return f"交易模式 '{m}' 正在运行中，请先停止它"
        return None

    def _build_command(self, mode: RunningMode, params: ModeParams) -> list[str]:
        py = sys.executable
        scripts = PROJECT_ROOT / "scripts"

        if mode == RunningMode.DATA_DOWNLOAD:
            return [py, str(scripts / "run_data_pipeline.py")]

        base = [py, str(scripts / "run_paper_trading_daemon.py")]
        state_file = str(PROJECT_ROOT / "data" / f"paper_daemon_state_{mode.value}.json")

        args = [
            "--symbol", params.symbol,
            "--timeframe", params.timeframe,
            "--days", str(params.days),
            "--initial", str(params.initial_capital),
            "--state-file", state_file,
        ]

        if mode == RunningMode.REPLAY_PAPER:
            csv_arg = params.replay_csv or "generate"
            args.extend(["--replay", csv_arg])
        elif mode == RunningMode.LIVE_PAPER:
            args.extend(["--poll-seconds", str(params.poll_seconds)])
        elif mode == RunningMode.TESTNET_LIVE:
            args.extend([
                "--broker", "exchange",
                "--poll-seconds", str(params.poll_seconds),
            ])

        if params.fresh:
            args.append("--fresh")

        return base + args

    async def _read_output(self, proc: asyncio.subprocess.Process, mode: RunningMode):
        """逐行读取子进程 stdout，广播到日志系统。"""
        from src.api.ws_logs import ws_logs
        key = mode.value
        try:
            assert proc.stdout is not None
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                line = _ANSI_RE.sub("", raw.decode("utf-8", errors="replace")).rstrip("\n")
                self._modes[key].last_log_line = line
                await ws_logs.broadcast(mode, line)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[{key}] 日志读取异常: {e}")

    async def _wait_for_exit(self, proc: asyncio.subprocess.Process, mode: RunningMode):
        """等待子进程退出，更新状态。"""
        key = mode.value
        try:
            code = await proc.wait()
            st = self._modes[key]
            # 只在未被 stop_mode 主动停止时更新状态
            if st.status == ModeStatus.RUNNING:
                st.status = ModeStatus.IDLE if code == 0 else ModeStatus.ERROR
                st.exit_code = code
                st.process = None
                st.pid = None
                st.started_at = None
                self._clear_mode_state(key)
                logger.info(f"模式 [{key}] 子进程退出, code={code}")
        except asyncio.CancelledError:
            pass

    def _status_dict(self, key: str) -> dict:
        st = self._modes[key]
        uptime = None
        if st.status == ModeStatus.RUNNING and st.started_at:
            uptime = int((datetime.now(timezone.utc) - st.started_at).total_seconds())
        return {
            "mode": key,
            "status": st.status.value,
            "pid": st.pid,
            "startedAt": st.started_at.isoformat() if st.started_at else None,
            "uptimeSeconds": uptime,
            "exitCode": st.exit_code,
            "lastLogLine": st.last_log_line,
            "params": st.params,
        }

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def _save_mode_state(self, key: str):
        st = self._modes[key]
        path = STATE_DIR / f"{key}.json"
        data = {
            "mode": key,
            "status": st.status.value,
            "pid": st.pid,
            "started_at": st.started_at.isoformat() if st.started_at else None,
            "params": st.params,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_mode_state(self, key: str) -> dict | None:
        path = STATE_DIR / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _clear_mode_state(self, key: str):
        path = STATE_DIR / f"{key}.json"
        if path.exists():
            path.unlink()

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        """检查 PID 是否存活（跨平台）。"""
        try:
            if sys.platform == "win32":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (OSError, ProcessLookupError):
            return False


# 模块级单例
mode_manager = ModeManager()
