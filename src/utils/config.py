"""
配置管理

从环境变量和配置文件加载配置
"""

import os
import sys
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv


class Config:
    """配置类"""

    def __init__(self, env_file: Optional[str] = None):
        """
        初始化配置

        参数：
            env_file: .env 文件路径（默认使用项目根目录的 .env）
        """
        # 加载环境变量
        if env_file:
            load_dotenv(env_file)
        else:
            # 查找项目根目录的 .env 文件
            current_dir = Path(__file__).resolve().parent
            project_root = current_dir.parent.parent
            env_path = project_root / ".env"
            if env_path.exists():
                load_dotenv(env_path)

        # ============================================
        # 数据库配置
        # ============================================
        self.DATABASE_URL = os.getenv("DATABASE_URL", "")
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
        # REDIS_URL 优先；若未设置但 REDIS_PASSWORD 存在，自动构造带密码的 URL
        raw_redis_url = os.getenv("REDIS_URL", "")
        if raw_redis_url:
            self.REDIS_URL = raw_redis_url
        elif self.REDIS_PASSWORD:
            self.REDIS_URL = f"redis://:{self.REDIS_PASSWORD}@localhost:6379/0"
        else:
            self.REDIS_URL = "redis://localhost:6379/0"

        # TimescaleDB 详细配置
        self.TIMESCALE_HOST = os.getenv("TIMESCALE_HOST", "localhost")
        self.TIMESCALE_PORT = int(os.getenv("TIMESCALE_PORT", "5432"))
        self.TIMESCALE_USER = os.getenv("TIMESCALE_USER", "postgres")
        self.TIMESCALE_PASSWORD = os.getenv("TIMESCALE_PASSWORD", "")
        self.TIMESCALE_DATABASE = os.getenv("TIMESCALE_DATABASE", "crypto_trading")

        # ============================================
        # 交易所 API 配置
        # ============================================
        self.BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
        self.BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")
        self.BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        # API Token for frontend auth
        self.API_TOKEN = os.getenv("API_TOKEN", "")

        # ============================================
        # 实盘控制（重要！）
        # ============================================
        self.LIVE_TRADING_ENABLED = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"

        # ============================================
        # 风控参数
        # ============================================
        self.MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.02"))  # 2%
        self.MAX_POSITION_SIZE = float(os.getenv("MAX_POSITION_SIZE", "0.20"))  # 20%
        self.MAX_TOTAL_POSITION = float(os.getenv("MAX_TOTAL_POSITION", "0.60"))  # 60%
        self.MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "5"))

        # ============================================
        # Phase 1 配置
        # ============================================
        self.DATA_START_DATE = os.getenv("DATA_START_DATE", "2023-01-01")
        self.DATA_END_DATE = os.getenv("DATA_END_DATE", "2024-12-31")
        self.DATA_SYMBOLS = os.getenv("DATA_SYMBOLS", "BTC/USDT,ETH/USDT").split(",")
        self.DATA_TIMEFRAME = os.getenv("DATA_TIMEFRAME", "4h")

        # ============================================
        # 应用配置
        # ============================================
        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.TIMEZONE = os.getenv("TIMEZONE", "UTC")
        self.DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    def validate(self, strict: bool = False) -> tuple[bool, list[str]]:
        """
        验证配置

        参数：
            strict: 为 True 时，严重错误会直接 sys.exit(1)

        返回：
            (是否通过, 错误列表)
        """
        errors: List[str] = []
        critical: List[str] = []

        # API Token 必须设置（任何环境都需要前端 API 认证）
        if not self.API_TOKEN:
            critical.append("API_TOKEN 未设置 - API 认证不可用")

        # 检查必需的配置
        if self.ENVIRONMENT == "production":
            if not self.BINANCE_API_KEY:
                critical.append("BINANCE_API_KEY 未设置")
            if not self.BINANCE_SECRET:
                critical.append("BINANCE_SECRET 未设置")
            if not self.TIMESCALE_PASSWORD:
                critical.append("TIMESCALE_PASSWORD 未设置")
            if self.TIMESCALE_PASSWORD == "your_secure_password":
                critical.append("TIMESCALE_PASSWORD 仍为默认值")

        # 检查风控参数范围
        if not 0 < self.MAX_DAILY_LOSS <= 0.10:
            errors.append(f"MAX_DAILY_LOSS 超出合理范围: {self.MAX_DAILY_LOSS}")

        if not 0 < self.MAX_POSITION_SIZE <= 0.50:
            errors.append(f"MAX_POSITION_SIZE 超出合理范围: {self.MAX_POSITION_SIZE}")

        if not 0 < self.MAX_TOTAL_POSITION <= 1.0:
            errors.append(f"MAX_TOTAL_POSITION 超出合理范围: {self.MAX_TOTAL_POSITION}")

        # 安全检查
        if self.LIVE_TRADING_ENABLED and self.ENVIRONMENT == "development":
            critical.append("⚠️  开发环境不应启用实盘交易！")

        # 关键错误应立即阻止启动
        if critical:
            for err in critical:
                import logging
                logging.getLogger(__name__).error(f"[CONFIG CRITICAL] {err}")
            if strict:
                sys.exit(1)

        return len(errors) == 0 and len(critical) == 0, errors + critical

    def __repr__(self) -> str:
        """返回配置的字符串表示（隐藏敏感信息）"""
        return (
            f"Config(\n"
            f"  ENVIRONMENT={self.ENVIRONMENT}\n"
            f"  DATABASE_URL={self._mask_url(self.DATABASE_URL)}\n"
            f"  REDIS_URL={self._mask_url(self.REDIS_URL)}\n"
            f"  BINANCE_TESTNET={self.BINANCE_TESTNET}\n"
            f"  LIVE_TRADING_ENABLED={self.LIVE_TRADING_ENABLED}\n"
            f"  DATA_SYMBOLS={self.DATA_SYMBOLS}\n"
            f"  API_TOKEN={'***' if self.API_TOKEN else '(not set)'}\n"
            f"  BINANCE_API_KEY={'***' if self.BINANCE_API_KEY else '(not set)'}\n"
            f")"
        )

    @staticmethod
    def _mask_url(url: str) -> str:
        """隐藏 URL 中的密码"""
        if "@" in url:
            parts = url.split("@")
            if ":" in parts[0]:
                user_pass = parts[0].split(":")
                return f"{user_pass[0]}:****@{parts[1]}"
        return url


# 全局配置实例
config = Config()

# 导出
__all__ = ["Config", "config"]
