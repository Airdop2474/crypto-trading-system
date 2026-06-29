"""
数据库连接管理

支持 PostgreSQL/TimescaleDB 和 Redis
"""

import os
from typing import Optional
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

        并发：从 SQLAlchemy 连接池获取连接，无锁，多线程可并发调用。
        """
        if not self._engine:
            self.init_postgres()

        conn = self._engine.raw_connection()
        try:
            cursor_factory = RealDictCursor if dict_cursor else None
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()
        finally:
            conn.close()  # 归还连接池

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
