"""
管理端点处理器（API Token 保护）

从 app.py 分离，集中管理所有 /admin/* 端点的实现逻辑。
app.py 导入本模块并用 `@app.xxx` 注册路由，保持装饰器（限流、鉴权）在 app.py 中。
"""

import shutil
from pathlib import Path as _P
from typing import Literal

from fastapi import HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import text as sa_text

from src.api import service
from src.utils.database import db as _db
from src.utils.cache import cache


def admin_refresh_state():
    """重置 Paper Trading state 缓存，下次请求会重新跑 Paper Trading。"""
    service.reset_state()
    return {
        "status": "ok",
        "message": "State reset. Next request will rebuild Paper Trading state.",
    }


def admin_build_status():
    """Paper Trading 状态构建进度（返回是否就绪/构建中/错误）。"""
    return service.get_build_status()


def admin_clear_cache(confirm: bool = Query(False)):
    """全面重置：清空数据库所有表 + Redis 缓存 + 本地数据文件 + 内存 state。

    防护：需要 ?confirm=true 查询参数作为二次确认，防止误触。
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="二次确认：请添加 ?confirm=true 查询参数以确认清除所有数据",
        )

    warnings: list[str] = []
    db_rows_cleared = 0
    try:
        if _db.engine is not None:
            tables = ["orders", "closed_trades", "open_positions",
                       "risk_events", "audit_log", "strategy_evolutions",
                       "strategy_runs"]
            with _db.engine.connect() as conn:
                for t in tables:
                    count = conn.execute(sa_text(f"SELECT COUNT(*) FROM {t}")).scalar()
                    db_rows_cleared += int(count)
                conn.execute(sa_text(
                    "TRUNCATE strategy_runs, orders, closed_trades, "
                    "open_positions, risk_events, audit_log, "
                    "strategy_evolutions CASCADE"
                ))
                conn.commit()
            try:
                with _db.engine.connect() as conn:
                    conn.execute(sa_text("TRUNCATE monitor_metrics"))
                    conn.commit()
            except Exception as e:
                logger.debug(f"TRUNCATE monitor_metrics 失败（非致命）: {e}")
        else:
            warnings.append("数据库未初始化（engine is None）")
    except Exception as e:
        logger.warning(f"DB truncate failed (non-fatal): {e}")
        warnings.append(f"数据库清空失败：{type(e).__name__}")

    cleared = cache.clear("*")
    files_cleared = 0
    data_dir = _P("data")
    # 删除所有 paper daemon 检查点（含带 mode/strategy 后缀的文件）
    for f in data_dir.glob("paper_daemon_state*.json"):
        if f.exists():
            try:
                f.unlink()
                files_cleared += 1
            except OSError as e:
                warnings.append(f"删除 {f.name} 失败：{e}")
    # 兼容旧的无后缀 tmp 文件
    for f in [data_dir / "paper_daemon_state.json.tmp"]:
        if f.exists():
            try:
                f.unlink()
                files_cleared += 1
            except OSError as e:
                warnings.append(f"删除 {f.name} 失败：{e}")
    for d in [data_dir / "reports" / "paper", data_dir / "reports" / "paper" / "daily",
              data_dir / "reports" / "backtest", data_dir / "reports" / "test",
              data_dir / "reports" / "test_paper", data_dir / "reports" / "agent",
              data_dir / "raw", data_dir / "mode_states"]:
        if d.is_dir():
            for f in d.iterdir():
                if f.is_file():
                    try:
                        f.unlink()
                        files_cleared += 1
                    except OSError as e:
                        warnings.append(f"删除 {f.name} 失败：{e}")
                elif f.is_dir():
                    try:
                        shutil.rmtree(f)
                        files_cleared += 1
                    except OSError as e:
                        warnings.append(f"删除目录 {f.name} 失败：{e}")
    reports_dir = data_dir / "reports"
    if reports_dir.is_dir():
        for f in reports_dir.iterdir():
            if f.is_file():
                try:
                    f.unlink()
                    files_cleared += 1
                except OSError:
                    pass

    service.reset_state()

    msg_parts = []
    if db_rows_cleared > 0:
        msg_parts.append(f"{db_rows_cleared} DB rows")
    if cleared > 0:
        msg_parts.append(f"{cleared} cache keys")
    if files_cleared > 0:
        msg_parts.append(f"{files_cleared} local files")
    if not msg_parts:
        msg_parts.append("nothing to clear (already clean)")
    message = f"Full reset: {', '.join(msg_parts)} cleared."
    if warnings:
        message += f" Warnings: {'; '.join(warnings)}"

    return {
        "status": "ok" if not warnings else "ok_with_warnings",
        "cleared_keys": cleared, "db_rows_cleared": db_rows_cleared,
        "files_cleared": files_cleared, "message": message,
    }


def admin_start_trading():
    """手动启动 Paper Trading，生成订单/仓位数据。"""
    service.activate()
    service.get_state()
    return {"status": "ok", "message": "Paper Trading started"}


def admin_emergency_stop():
    """远程急停：触发全局 RiskManager.emergency_stop()，停止所有策略交易。"""
    state = service.get_state()
    multi_runner = state.get("_multi_runner")
    if multi_runner is None:
        raise HTTPException(503, "多策略引擎未初始化")
    risk_manager = getattr(multi_runner, "risk_manager", None)
    if risk_manager is None:
        raise HTTPException(503, "RiskManager 未注入")

    prev_state = getattr(risk_manager, "state", "UNKNOWN")
    risk_manager.emergency_stop("remote emergency-stop via API")
    logger.warning(f"远程急停已触发：{prev_state} -> STOPPED")

    # 发送告警通知
    try:
        from src.monitor.alert_hub import alert_manager
        alert_manager.emit(
            "CRITICAL", "api",
            f"远程急停已触发: {prev_state} -> STOPPED (via API)",
        )
    except Exception as e:
        logger.debug(f"急停告警发送失败（非致命）: {e}")

    from pathlib import Path as _Path
    signal_file = _Path("data/.emergency_stop")
    try:
        signal_file.parent.mkdir(parents=True, exist_ok=True)
        signal_file.write_text("1", encoding="utf-8")
    except OSError as e:
        logger.warning(f"急停信号文件写入失败：{e}")

    return {
        "ok": True, "previous_state": prev_state, "current_state": "STOPPED",
        "message": "全局急停已触发，所有策略交易已停止。需通过 reset() 恢复。",
    }


class CleanupRequest(BaseModel):
    scope: Literal["all", "runs", "evolutions"] = "all"
    keepLatest: bool = False


def admin_data_cleanup(body: CleanupRequest):
    """清理历史测试数据（运行记录 / 进化记录 / 审计日志）"""
    return service.cleanup_data(scope=body.scope, keep_latest=body.keepLatest)
