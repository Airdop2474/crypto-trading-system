"""
数据库连接管理

支持 PostgreSQL/TimescaleDB 和 Redis
"""

import os
import threading
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from redis import Redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

from src.utils.logger import logger
from src.utils.config import config


class DatabaseManager:
    """数据库管理器"""

    def __init__(self):
        """初始化数据库连接"""
        self._engine = None
        self._session_factory = None
        self._redis_client = None
        self._pg_connection = None
        self._pg_lock = threading.Lock()

    def init_postgres(self) -> None:
        """初始化 PostgreSQL 连接"""
        try:
            # SQLAlchemy 引擎
            self._engine = create_engine(
                config.DATABASE_URL,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,  # 连接前检查
                echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            )
            self._session_factory = sessionmaker(bind=self._engine)
            logger.info("PostgreSQL engine initialized")

            # psycopg2 连接（用于批量操作）
            self._pg_connection = psycopg2.connect(
                host=config.TIMESCALE_HOST,
                port=config.TIMESCALE_PORT,
                user=config.TIMESCALE_USER,
                password=config.TIMESCALE_PASSWORD,
                database=config.TIMESCALE_DATABASE,
            )
            logger.info("PostgreSQL connection established")

        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL: {e}")
            raise

    def init_redis(self) -> None:
        """初始化 Redis 连接"""
        try:
            self._redis_client = Redis.from_url(
                config.REDIS_URL,
                decode_responses=True,
            )
            # 测试连接
            self._redis_client.ping()
            logger.info("Redis connection established")

        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            raise

    @contextmanager
    def get_session(self) -> Session:
        """
        获取 SQLAlchemy Session（上下文管理器）

        使用示例：
            with db.get_session() as session:
                result = session.query(Model).all()
        """
        if not self._session_factory:
            self.init_postgres()

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _ensure_pg_connection(self) -> None:
        """确保 psycopg2 连接可用，断线则重连。

        psycopg2 连接的 .closed 为非 0 表示已关闭（如网络中断、服务端超时）。
        裸连接没有 SQLAlchemy 的 pool_pre_ping，需手动检测并重建。
        """
        if self._pg_connection is None or self._pg_connection.closed != 0:
            if self._pg_connection is not None:
                logger.warning("PostgreSQL connection lost, reconnecting...")
            self.init_postgres()

    @contextmanager
    def get_cursor(self, dict_cursor: bool = True):
        """
        获取 psycopg2 Cursor（上下文管理器）

        参数：
            dict_cursor: 是否返回字典格式结果

        使用示例：
            with db.get_cursor() as cursor:
                cursor.execute("SELECT * FROM table")
                results = cursor.fetchall()

        线程安全：通过 _pg_lock 保护裸 psycopg2 连接的并发访问。
        """
        with self._pg_lock:
            self._ensure_pg_connection()

            cursor_factory = RealDictCursor if dict_cursor else None
            cursor = self._pg_connection.cursor(cursor_factory=cursor_factory)

            try:
                yield cursor
                self._pg_connection.commit()
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                # 连接级故障：标记关闭，下次调用触发重连
                self._safe_close_pg()
                raise
            except Exception:
                self._pg_connection.rollback()
                raise
            finally:
                if self._pg_connection is not None and self._pg_connection.closed == 0:
                    cursor.close()

    def _safe_close_pg(self) -> None:
        """安全关闭裸连接，置空以触发下次重连。"""
        try:
            if self._pg_connection is not None:
                self._pg_connection.close()
        except Exception as e:
            logger.debug(f"关闭 PG 连接失败（非致命）: {e}")
        finally:
            self._pg_connection = None

    def execute_query(self, query: str, params: Optional[tuple] = None) -> list:
        """
        执行查询并返回结果

        参数：
            query: SQL 查询语句
            params: 参数（防止 SQL 注入）

        返回：
            查询结果列表
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def execute_many(self, query: str, data: list) -> None:
        """
        批量执行 SQL

        参数：
            query: SQL 语句
            data: 数据列表

        使用示例：
            query = "INSERT INTO table (col1, col2) VALUES (%s, %s)"
            data = [(val1, val2), (val3, val4), ...]
            db.execute_many(query, data)
        """
        with self.get_cursor() as cursor:
            cursor.executemany(query, data)

    @property
    def redis(self) -> Redis:
        """获取 Redis 客户端"""
        if not self._redis_client:
            self.init_redis()
        return self._redis_client

    @property
    def engine(self):
        """获取 SQLAlchemy engine（可能为 None）。"""
        return self._engine

    def is_postgres_available(self) -> bool:
        """快速检测 PostgreSQL 是否可用（布尔值，供 service 层 DB 优先回退判断）。"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() is not None
        except Exception:
            return False

    def test_connection(self) -> dict:
        """
        测试数据库连接

        返回：
            连接状态字典
        """
        status = {
            "postgres": False,
            "redis": False,
        }

        # 测试 PostgreSQL
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                status["postgres"] = result is not None
                logger.info("PostgreSQL connection OK")
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")

        # 测试 Redis
        try:
            self.redis.ping()
            status["redis"] = True
            logger.info("Redis connection OK")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")

        return status

    def close(self) -> None:
        """关闭所有连接"""
        if self._pg_connection:
            self._pg_connection.close()
            logger.info("PostgreSQL connection closed")

        if self._redis_client:
            self._redis_client.close()
            logger.info("Redis connection closed")

        if self._engine:
            self._engine.dispose()
            logger.info("SQLAlchemy engine disposed")


# 全局数据库实例
db = DatabaseManager()

# 导出
__all__ = ["DatabaseManager", "db"]
