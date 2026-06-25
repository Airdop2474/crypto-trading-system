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
    strategies: list[str] = ["grid"]
    market_type: str = "oscillating"


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
    # 多策略并行：每个策略一个子进程
    processes: list[asyncio.subprocess.Process] = field(default_factory=list)
    pids: list[int] = field(default_factory=list)
    _reader_tasks: list[asyncio.Task] = field(default_factory=list)
    _waiter_tasks: list[asyncio.Task] = field(default_factory=list)


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

        # 构建命令（每策略一条）
        commands = self._build_commands(mode, params)

        # 启动子进程（每策略一个，并行运行）
        st.processes = []
        st.pids = []
        st._reader_tasks = []
        st._waiter_tasks = []
        try:
            for cmd in commands:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(PROJECT_ROOT),
                )
                st.processes.append(proc)
                st.pids.append(proc.pid)
                st._reader_tasks.append(asyncio.create_task(self._read_output(proc, mode)))
                st._waiter_tasks.append(asyncio.create_task(self._wait_for_exit(proc, mode)))
                logger.info(f"模式 [{key}] 策略子进程已启动, PID={proc.pid}, 命令={' '.join(cmd)}")
        except Exception as e:
            logger.error(f"启动子进程失败 [{key}]: {e}")
            # 清理已启动的进程
            for p in st.processes:
                try:
                    p.kill()
                except Exception as e:
                    logger.debug(f"清理进程失败 (pid={getattr(p, 'pid', '?')}): {e}")
            st.processes = []
            return {"error": f"启动子进程失败: {e}"}

        # 更新状态（兼容旧字段：process/pid 指向第一个子进程）
        st.status = ModeStatus.RUNNING
        st.process = st.processes[0] if st.processes else None
        st.pid = st.pids[0] if st.pids else None
        st.started_at = datetime.now(timezone.utc)
        st.exit_code = None
        st.last_log_line = None
        st.params = params.model_dump()

        # 持久化
        self._save_mode_state(key)

        return self._status_dict(key)

    async def stop_mode(self, mode: RunningMode) -> dict:
        """停止指定模式，优雅退出。"""
        key = mode.value
        st = self._modes[key]

        if st.status != ModeStatus.RUNNING or not st.processes:
            return {"error": f"模式 '{key}' 当前未在运行"}

        st.status = ModeStatus.STOPPING
        logger.info(f"模式 [{key}] 正在停止, PIDs={st.pids}")

        # 终止所有子进程
        for proc in st.processes:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass

        # 等待所有子进程退出
        for proc in st.processes:
            try:
                await asyncio.wait_for(proc.wait(), timeout=_STOP_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning(f"模式 [{key}] 子进程超时未退出, 强制终止")
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

        st.status = ModeStatus.IDLE
        st.process = None
        st.pid = None
        st.processes = []
        st.pids = []
        st.started_at = None
        self._clear_mode_state(key)

        logger.info(f"模式 [{key}] 已停止")
        return self._status_dict(key)

    def get_status(self, mode: RunningMode) -> dict:
        return self._status_dict(mode.value)

    def get_all_status(self) -> list[dict]:
        return [self._status_dict(m.value) for m in RunningMode]

    def get_result(self, mode: RunningMode) -> dict:
        """读取某模式最近一次运行的結果摘要（来自 daemon 检查点文件）。

        daemon 子进程每根 bar 都会原子写入 data/paper_daemon_state_{mode}[_{strategy}].json，
        本方法聚合这些文件，返回收益/交易数/胜率/天数/风控状态等前端可展示的指标。
        """
        key = mode.value
        st = self._modes[key]
        status_dict = self._status_dict(key)

        # glob 匹配该 mode 的所有检查点（单策略 + 多策略各一个文件）
        data_dir = PROJECT_ROOT / "data"
        state_files = sorted(data_dir.glob(f"paper_daemon_state_{key}*.json"))

        if not state_files:
            # 无检查点：从启动参数取默认值（停止后 params 可能已清空）
            initial = 10000.0
            symbol = "BTC/USDT"
            if st.params:
                try:
                    initial = float(st.params.get("initial_capital", 10000.0))
                except (TypeError, ValueError):
                    pass
                symbol = st.params.get("symbol", "BTC/USDT")
            return {
                "mode": key,
                "mode_status": status_dict["status"],
                "exit_code": status_dict["exitCode"],
                "available": False,
                "symbol": symbol,
                "initial_capital": initial,
                "realized_pnl": 0.0,
                "total_return_pct": 0.0,
                "final_balance": initial,
                "total_trades": 0,
                "win_count": 0,
                "loss_count": 0,
                "win_rate": 0.0,
                "day_count": 0,
                "last_bar_ts": None,
                "risk_state": "unknown",
                "strategy_paused": False,
                "strategies": [],
                "recent_trades": [],
            }

        strategies: list[dict] = []
        recent_trades: list[dict] = []
        total_realized = 0.0
        total_balance = 0.0
        total_trades = 0
        total_wins = 0
        total_losses = 0
        total_initial = 0.0  # 所有策略初始资金之和
        day_count = 0
        latest_ts: str | None = None
        # 模式已停止时，state 文件中的 risk.state 仍是 ACTIVE，需覆盖为 STOPPED
        risk_state = "STOPPED" if st.status not in (ModeStatus.RUNNING, ModeStatus.STOPPING) else "unknown"
        strategy_paused = False
        # symbol 从第一个 state 文件取（同一 mode 下一致）
        symbol = "BTC/USDT"
        initial = 10000.0

        prefix = f"paper_daemon_state_{key}"
        for sf in state_files:
            try:
                raw = json.loads(sf.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug(f"解析 state 文件失败 {sf.name}: {e}")
                continue

            # 跳过没有 strategy_name 的旧格式文件（避免显示 default 策略）
            if not raw.get("strategy_name"):
                continue

            # symbol 从第一个 state 文件取
            if sf is state_files[0]:
                symbol = raw.get("symbol", symbol)

            # 每个策略的初始资金累加（各策略独立 10000，汇总需相加）
            s_initial = 10000.0
            try:
                s_initial = float(raw.get("initial_capital", 10000.0))
            except (TypeError, ValueError):
                pass
            total_initial += s_initial

            runner = raw.get("runner", {})
            broker = raw.get("broker", {})
            risk = raw.get("risk", {})
            strat = raw.get("strategy", {})
            closed = runner.get("closed_trades", []) or []
            realized = float(runner.get("realized_pnl", 0.0))
            balance = float(broker.get("balance", 0.0))
            wins = sum(1 for t in closed if float(t.get("profit", 0)) > 0)
            losses = sum(1 for t in closed if float(t.get("profit", 0)) < 0)
            s_day = int(raw.get("day_count", 0))
            s_ts = raw.get("last_bar_ts")

            # 策略名：state 文件 strategy_name 字段（已由上方 continue 保证非空）
            strat_name = raw.get("strategy_name", "default")

            # 模式已停止时，state 文件中的 risk.state 仍是 ACTIVE，需覆盖为 STOPPED
            mode_stopped = st.status not in (ModeStatus.RUNNING, ModeStatus.STOPPING)
            s_risk_state = "STOPPED" if mode_stopped else risk.get("state", "unknown")

            strategies.append({
                "strategy": strat_name,
                "initial_capital": round(s_initial, 2),
                "realized_pnl": round(realized, 2),
                "return_pct": round(realized / s_initial * 100, 2) if s_initial else 0.0,
                "total_trades": len(closed),
                "win_count": wins,
                "loss_count": losses,
                "win_rate": round(wins / len(closed) * 100, 2) if closed else 0.0,
                "final_balance": round(balance, 2),
                "day_count": s_day,
                "last_bar_ts": s_ts,
                "risk_state": s_risk_state,
                "strategy_paused": bool(strat.get("paused", False)),
            })

            total_realized += realized
            total_balance += balance
            total_trades += len(closed)
            total_wins += wins
            total_losses += losses
            day_count = max(day_count, s_day)
            if s_ts and (latest_ts is None or str(s_ts) > str(latest_ts)):
                latest_ts = str(s_ts)
            if not mode_stopped and risk.get("state"):
                risk_state = risk.get("state", risk_state)
            strategy_paused = strategy_paused or bool(strat.get("paused", False))

            for t in closed[-5:]:
                recent_trades.append({
                    "strategy": strat_name,
                    "tag": str(t.get("tag", "")),
                    "time": str(t.get("time", "")),
                    "profit": round(float(t.get("profit", 0.0)), 2),
                })

        recent_trades = recent_trades[-10:]

        return {
            "mode": key,
            "mode_status": status_dict["status"],
            "exit_code": status_dict["exitCode"],
            "available": True,
            "symbol": symbol,
            "initial_capital": round(total_initial, 2),
            "realized_pnl": round(total_realized, 2),
            "total_return_pct": round(total_realized / total_initial * 100, 2) if total_initial else 0.0,
            "final_balance": round(total_balance, 2),
            "total_trades": total_trades,
            "win_count": total_wins,
            "loss_count": total_losses,
            "win_rate": round(total_wins / total_trades * 100, 2) if total_trades else 0.0,
            "day_count": day_count,
            "last_bar_ts": latest_ts,
            "risk_state": risk_state,
            "strategy_paused": strategy_paused,
            "strategies": strategies,
            "recent_trades": recent_trades,
        }

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

    def _build_commands(self, mode: RunningMode, params: ModeParams) -> list[list[str]]:
        """为每个策略构建一条独立命令（多策略并行，避免串行阻塞）。"""
        py = sys.executable
        scripts = PROJECT_ROOT / "scripts"
        base = [py, str(scripts / "run_paper_trading_daemon.py")]

        common_args = [
            "--symbol", params.symbol,
            "--timeframe", params.timeframe,
            "--days", str(params.days),
            "--initial", str(params.initial_capital),
        ]

        mode_args: list[str] = []
        if mode == RunningMode.REPLAY_PAPER:
            csv_arg = params.replay_csv or "generate"
            mode_args.extend(["--replay", csv_arg, "--market-type", params.market_type])
            mode_args.extend(["--max-bar-drop-pct", "0.50"])
            mode_args.append("--fresh")
        elif mode == RunningMode.LIVE_PAPER:
            mode_args.extend(["--poll-seconds", str(params.poll_seconds)])
        elif mode == RunningMode.TESTNET_LIVE:
            mode_args.extend(["--broker", "exchange", "--poll-seconds", str(params.poll_seconds)])

        if params.fresh and mode != RunningMode.REPLAY_PAPER:
            mode_args.append("--fresh")

        commands: list[list[str]] = []
        for strat in params.strategies:
            state_file = str(PROJECT_ROOT / "data" / f"paper_daemon_state_{mode.value}_{strat}.json")
            args = common_args + ["--state-file", state_file] + mode_args + ["--strategy", strat]
            commands.append(base + args)
        return commands

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
        """等待子进程退出，所有子进程退出后才更新状态。"""
        key = mode.value
        try:
            code = await proc.wait()
            st = self._modes[key]
            # 从进程列表中移除已退出的进程
            if proc in st.processes:
                idx = st.processes.index(proc)
                st.processes.remove(proc)
                if idx < len(st.pids):
                    st.pids.pop(idx)
            # 只在未被 stop_mode 主动停止时更新状态
            if st.status == ModeStatus.RUNNING:
                if not st.processes:
                    # 所有子进程已退出
                    st.status = ModeStatus.IDLE if code == 0 else ModeStatus.ERROR
                    st.exit_code = code
                    st.process = None
                    st.pid = None
                    st.started_at = None
                    self._clear_mode_state(key)
                    logger.info(f"模式 [{key}] 所有子进程已退出, 最后 code={code}")
                else:
                    logger.info(f"模式 [{key}] 子进程退出 (剩余 {len(st.processes)}), code={code}")
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
            "pid": st.pids if st.pids else st.pid,
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
        except Exception as e:
            logger.debug(f"_load_mode_state({key}) 读取失败: {e}")
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
