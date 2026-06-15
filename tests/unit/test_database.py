"""DatabaseManager psycopg2 裸连接重连测试。

不连真实数据库：用假连接 + patch init_postgres 验证重连逻辑。
"""

import psycopg2
import pytest

from src.utils.database import DatabaseManager


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.closed = False

    def execute(self, *a, **k):
        if self.conn._raise_on_execute:
            raise self.conn._raise_on_execute

    def fetchone(self):
        return (1,)

    def close(self):
        self.closed = True


class FakeConn:
    """模拟 psycopg2 连接：closed 标志可控。"""

    def __init__(self):
        self.closed = 0
        self.committed = False
        self.rolled_back = False
        self._raise_on_execute = None

    def cursor(self, cursor_factory=None):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = 1


def _attach(db, conn):
    """把 init_postgres 替换为安装给定假连接。"""
    def fake_init():
        db._pg_connection = conn
    db.init_postgres = fake_init


def test_reconnects_when_connection_closed():
    """连接 closed=1 时，get_cursor 触发重连到新的健康连接。"""
    db = DatabaseManager()

    stale = FakeConn()
    stale.closed = 1  # 已断
    fresh = FakeConn()  # init produces 健康连接

    def fake_init():
        db._pg_connection = fresh

    db.init_postgres = fake_init
    db._pg_connection = stale  # 起始为已断连接

    with db.get_cursor() as cur:
        cur.execute("SELECT 1")

    # 重连后用的是新的活连接
    assert db._pg_connection is fresh
    assert fresh.committed is True


def test_operational_error_drops_connection_for_next_reconnect():
    """OperationalError → 连接被关闭置空，下次调用重连。"""
    db = DatabaseManager()
    conn = FakeConn()
    conn._raise_on_execute = psycopg2.OperationalError("server closed")
    _attach(db, conn)
    db._pg_connection = conn

    with pytest.raises(psycopg2.OperationalError):
        with db.get_cursor() as cur:
            cur.execute("SELECT 1")

    # 故障后连接被置空，下次会重连
    assert db._pg_connection is None


def test_normal_error_rolls_back_keeps_connection():
    """普通异常 → rollback，连接保留（非连接级故障）。"""
    db = DatabaseManager()
    conn = FakeConn()
    conn._raise_on_execute = ValueError("bad sql")
    _attach(db, conn)
    db._pg_connection = conn

    with pytest.raises(ValueError):
        with db.get_cursor() as cur:
            cur.execute("SELECT 1")

    assert conn.rolled_back is True
    assert db._pg_connection is conn  # 未置空


def test_healthy_connection_not_reinitialized():
    """连接健康（closed=0）时不重连。"""
    db = DatabaseManager()
    conn = FakeConn()
    init_calls = {"n": 0}

    def fake_init():
        init_calls["n"] += 1
        db._pg_connection = conn

    db.init_postgres = fake_init
    db._pg_connection = conn  # 健康连接已就位

    with db.get_cursor() as cur:
        cur.execute("SELECT 1")

    assert init_calls["n"] == 0  # 未触发重连
    assert conn.committed is True
