"""
日志系统

使用 loguru 提供统一的日志接口
"""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def setup_logger(
    log_dir: str = "logs",
    log_level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "7 days",
    json_logs: Optional[bool] = None,
    environment: Optional[str] = None,
) -> None:
    """
    配置日志系统

    参数：
        log_dir: 日志目录
        log_level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        rotation: 日志轮转大小
        retention: 日志保留时间
        json_logs: 是否额外输出 JSON 结构化日志（供 ELK/Loki 采集）。
            None（默认）时读 config.ENVIRONMENT：production 自动开启，其余关闭。
        environment: 注入每条 JSON 日志的 environment 字段。None 时取 config.ENVIRONMENT。
    """
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level.upper() not in valid_levels:
        raise ValueError(
            f"Invalid log_level: '{log_level}'. Must be one of {valid_levels}"
        )

    # environment / json 开关：未显式传入则读 config（延迟导入避免循环依赖）
    if environment is None or json_logs is None:
        try:
            from src.utils.config import config
            env = environment if environment is not None else config.ENVIRONMENT
            enable_json = json_logs if json_logs is not None else (
                config.ENVIRONMENT == "production"
            )
        except Exception:
            env = environment or "development"
            enable_json = bool(json_logs)
    else:
        env = environment
        enable_json = json_logs

    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 移除默认的 handler
    logger.remove()

    # 注入 environment 字段到所有日志记录（JSON sink 的 extra 会带上）
    logger.configure(extra={"environment": env})

    # 添加控制台输出（带颜色）
    logger.add(
        sys.stdout,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 添加文件输出（所有日志）
    logger.add(
        log_path / "app_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
    )

    # 添加错误日志文件
    logger.add(
        log_path / "error_{time:YYYY-MM-DD}.log",
        level="ERROR",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | {message}\n{exception}"
        ),
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
    )

    # JSON 结构化日志（可选，供 ELK/Loki 采集）。serialize=True 输出单行 JSON，
    # extra.environment 随每条记录带出，便于多环境日志聚合检索。
    if enable_json:
        logger.add(
            log_path / "app_json_{time:YYYY-MM-DD}.log",
            level="DEBUG",
            serialize=True,
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
        )

    logger.info(f"Logger initialized. Level: {log_level}, Log dir: {log_dir}")


# 导出 logger 实例
__all__ = ["logger", "setup_logger"]
