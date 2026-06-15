"""交易系统主入口"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from src.utils.logger import logger, setup_logger

# 加载环境变量
load_dotenv()

# 初始化日志
setup_logger(
    log_dir=os.getenv("LOG_PATH", "./logs"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
)


def main() -> None:
    """主函数"""
    mode = os.getenv("MODE", "backtest")

    logger.info(f"Starting Crypto Trading System in {mode} mode")

    if mode == "backtest":
        logger.info("Backtest mode - Use scripts/run_backtest.py")
    elif mode == "paper":
        logger.info("Paper trading mode - Implementation in progress")
    elif mode == "live":
        logger.warning("Live trading mode - Use with caution!")
    else:
        logger.error(f"Unknown mode: {mode}")
        sys.exit(1)

    logger.info("System started successfully")


if __name__ == "__main__":
    main()
