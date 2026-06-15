"""
日志系统

使用 loguru 提供统一的日志接口
"""

import sys
from pathlib import Path

from loguru import logger


def setup_logger(
    log_dir: str = "logs",
    log_level: str = "INFO",
    rotation: str = "100 MB",
    retention: str = "30 days",
) -> None:
    """
    配置日志系统

    参数：
        log_dir: 日志目录
        log_level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        rotation: 日志轮转大小
        retention: 日志保留时间
    """
    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 移除默认的 handler
    logger.remove()

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

    logger.info(f"Logger initialized. Level: {log_level}, Log dir: {log_dir}")


# 导出 logger 实例
__all__ = ["logger", "setup_logger"]
