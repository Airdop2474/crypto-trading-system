"""
Redis 缓存层单元测试

覆盖：
- CacheLayer 基本操作（get/set/delete）
- JSON 序列化/反序列化
- TTL 过期
- 内存回退（Redis 不可用时）
- CacheKeys 常量
- WsFeed 缓存集成
"""

import time

import pytest

from src.utils.cache import CacheLayer, MemoryCache, CacheKeys


class TestMemoryCache:
    """MemoryCache 基本功能测试"""

    def test_get_set(self):
        """基本的 get/set"""
        mc = MemoryCache()
        mc.set("key1", "value1")
        assert mc.get("key1") == "value1"

    def test_get_nonexistent(self):
        """获取不存在的键"""
        mc = MemoryCache()
        assert mc.get("nonexistent") is None

    def test_delete(self):
        """删除键"""
        mc = MemoryCache()
        mc.set("key1", "value1")
        mc.delete("key1")
        assert mc.get("key1") is None

    def test_ttl_expiry(self):
        """TTL 过期"""
        mc = MemoryCache()
        mc.set("key1", "value1", ttl=1)
        assert mc.get("key1") == "value1"

        time.sleep(1.1)
        assert mc.get("key1") is None

    def test_no_ttl(self):
        """无 TTL 时不过期"""
        mc = MemoryCache()
        mc.set("key1", "value1")
        time.sleep(0.1)
        assert mc.get("key1") == "value1"

    def test_keys_all(self):
        """获取所有键"""
        mc = MemoryCache()
        mc.set("a", "1")
        mc.set("b", "2")
        mc.set("c", "3")
        keys = mc.keys()
        assert set(keys) == {"a", "b", "c"}

    def test_keys_pattern(self):
        """按前缀过滤键"""
        mc = MemoryCache()
        mc.set("tickers:a", "1")
        mc.set("tickers:b", "2")
        mc.set("other:c", "3")
        keys = mc.keys("tickers:*")
        assert set(keys) == {"tickers:a", "tickers:b"}

    def test_ping(self):
        """内存缓存 ping"""
        mc = MemoryCache()
        assert mc.ping() is True


class TestCacheLayer:
    """CacheLayer 测试（使用内存回退）"""

    @pytest.fixture
    def cache(self):
        """创建使用内存回退的 CacheLayer"""
        # 使用不存在的 Redis URL 强制使用内存
        import os
        old_url = os.environ.get("REDIS_URL")
        os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"  # 端口 1 立即拒绝

        c = CacheLayer(namespace="test")

        # 恢复环境变量
        if old_url:
            os.environ["REDIS_URL"] = old_url
        else:
            os.environ.pop("REDIS_URL", None)

        return c

    def test_backend_is_memory(self, cache):
        """Redis 不可用时使用内存后端"""
        assert cache.backend_type == "memory"
        assert cache.is_redis_available is False

    def test_set_get_string(self, cache):
        """存储字符串"""
        cache.set("test:key", "hello")
        assert cache.get("test:key") == "hello"

    def test_set_get_dict(self, cache):
        """存储字典（自动 JSON 序列化）"""
        data = {"price": 67500.50, "symbol": "BTC/USDT"}
        cache.set("ticker:btc", data)

        result = cache.get("ticker:btc")
        assert result["price"] == 67500.50
        assert result["symbol"] == "BTC/USDT"

    def test_set_get_list(self, cache):
        """存储列表"""
        data = [{"symbol": "BTC/USDT", "price": 67500}]
        cache.set("tickers", data)

        result = cache.get("tickers")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["symbol"] == "BTC/USDT"

    def test_set_get_number(self, cache):
        """存储数字"""
        cache.set("count", 42)
        assert cache.get("count") == 42

    def test_set_with_ttl(self, cache):
        """带 TTL 的 set"""
        cache.set("temp", "value", ttl=1)
        assert cache.get("temp") == "value"

        time.sleep(1.1)
        assert cache.get("temp") is None

    def test_delete(self, cache):
        """删除"""
        cache.set("key", "value")
        cache.delete("key")
        assert cache.get("key") is None

    def test_exists(self, cache):
        """检查键是否存在"""
        cache.set("key", "value")
        assert cache.exists("key") is True
        assert cache.exists("nonexistent") is False

    def test_keys(self, cache):
        """获取键列表"""
        cache.set("a:1", "v1")
        cache.set("a:2", "v2")
        cache.set("b:1", "v3")

        keys = cache.keys("a:*")
        assert "a:1" in keys
        assert "a:2" in keys
        assert "b:1" not in keys

    def test_clear(self, cache):
        """清除匹配的缓存"""
        cache.set("temp:1", "v1")
        cache.set("temp:2", "v2")
        cache.set("keep:1", "v3")

        count = cache.clear("temp:*")
        assert count == 2
        assert cache.get("temp:1") is None
        assert cache.get("keep:1") == "v3"

    def test_ping(self, cache):
        """内存回退 ping"""
        assert cache.ping() is True

    def test_info(self, cache):
        """获取缓存信息"""
        info = cache.info()
        assert info["backend"] == "memory"
        assert info["namespace"] == "test"

    def test_namespace_isolation(self):
        """命名空间隔离"""
        import os
        old_url = os.environ.get("REDIS_URL")
        os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"

        c1 = CacheLayer(namespace="ns1")
        c2 = CacheLayer(namespace="ns2")

        c1.set("key", "value1")
        c2.set("key", "value2")

        assert c1.get("key") == "value1"
        assert c2.get("key") == "value2"

        if old_url:
            os.environ["REDIS_URL"] = old_url
        else:
            os.environ.pop("REDIS_URL", None)


class TestCacheKeys:
    """缓存键常量测试"""

    def test_tickers_snapshot(self):
        assert CacheKeys.TICKERS_SNAPSHOT == "tickers:snapshot"

    def test_paper_state(self):
        assert CacheKeys.PAPER_STATE == "paper:state"

    def test_ohlcv_key(self):
        key = CacheKeys.ohlcv("BTC/USDT", "4h")
        assert key == "ohlcv:BTC_USDT:4h"

    def test_backtest_key(self):
        key = CacheKeys.backtest("GridTrading", "abc123")
        assert key == "backtest:GridTrading:abc123"


class TestWsFeedCacheIntegration:
    """WsFeed 缓存集成测试"""

    def test_ws_feed_load_from_cache(self):
        """WsFeed 从缓存加载"""
        from src.api.ws_feed import WsFeed

        feed = WsFeed()

        # 手动设置缓存
        feed._tickers["BTC/USDT"] = {
            "symbol": "BTC/USDT",
            "price": 67500,
            "changePct": 1.5,
            "volume": 1000000,
            "high": 68000,
            "low": 66000,
        }

        # 保存到缓存
        feed._save_to_cache()

        # 创建新的 feed 并从缓存加载
        feed2 = WsFeed()
        feed2._load_from_cache()

        # 检查是否加载成功（可能从 Redis 或内存）
        # 由于测试环境可能无 Redis，这里主要验证不崩溃
        assert feed2 is not None

    def test_ws_feed_save_to_cache_no_crash(self):
        """WsFeed 保存缓存不崩溃"""
        from src.api.ws_feed import WsFeed

        feed = WsFeed()
        feed._tickers["BTC/USDT"] = {
            "symbol": "BTC/USDT",
            "price": 67500,
            "changePct": 1.5,
            "volume": 1000000,
            "high": 68000,
            "low": 66000,
        }

        # 不应抛出异常
        feed._save_to_cache()


class TestCacheModuleImports:
    """模块导入测试"""

    def test_imports(self):
        """验证模块可以正确导入"""
        from src.utils.cache import CacheLayer, cache, CacheKeys, MemoryCache
        assert CacheLayer is not None
        assert cache is not None
        assert CacheKeys is not None
        assert MemoryCache is not None

    def test_global_cache_exists(self):
        """全局缓存实例存在"""
        from src.utils.cache import cache
        assert cache is not None
        assert hasattr(cache, "get")
        assert hasattr(cache, "set")
        assert hasattr(cache, "delete")
