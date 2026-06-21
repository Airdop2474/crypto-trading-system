"""
Alembic 迁移环境

使用项目现有的 SQLAlchemy engine（src.utils.database.db），
而非 alembic.ini 中的静态 URL。这样迁移自动跟随运行时配置。
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 将项目根目录加入 sys.path，使 src.models 可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 导入 ORM Base（metadata 包含全部表定义）
from src.models.base import Base

# Alembic Config 对象
config = context.config

# 配置 Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# metadata 供 --autogenerate 使用
target_metadata = Base.metadata


def _get_engine_url() -> str:
    """优先使用项目运行时的 DATABASE_URL，回退到 alembic.ini 中的静态 URL。"""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    # 尝试从 .env 加载
    try:
        from dotenv import load_dotenv
        load_dotenv()
        url = os.getenv("DATABASE_URL")
        if url:
            return url
    except ImportError:
        pass
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL 脚本，不连接数据库。"""
    url = _get_engine_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库并执行迁移。"""
    url = _get_engine_url()
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
