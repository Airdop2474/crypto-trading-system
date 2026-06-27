"""
Redis 缓存层

统一的缓存接口，支持 Redis 和内存回退：
- Redis 可用时使用 Redis（持久化、跨进程共享）
- Redis 不可用时自动回退到内存缓存（开发友好）
- Redis 恢复后自动重连（指数退避 + 定期健康检查）
- JSON 序列化支持复杂对象
- 命名空间隔离不同缓存域
- TTL 过期自动清理

用法：
    from src.utils.cache import cache

    # 基本操作
    cache.set("tickers:btc", {"price": 67500}, ttl=60)
    data = cache.get("tickers:btc")

    # 删除
    cache.delete("tickers:btc")

    # 检查连接
    cache.is_redis_available
"""

import json
import re
import threading
import time
from typing import Any, Dict, Optional, List

from src.utils.config import config
from src.utils.logger import logger


class MemoryCache:
    """内存缓存（Redis 不可用时的回退方案）"""

    def __init__(self):
        self._store: Dict[str, tuple] = {}  # key -> (value, expire_time)
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[str]:
        """获取值，过期则删除"""
        with self._lock:
            if key not in self._store:
                return None

            value, expire_time = self._store[key]
            if expire_time and time.time() > expire_time:
                del self._store[key]
                return None

            return value

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """设置值

        ttl 语义：
        - None：永不过期
        - 0 或负数：视为立即过期（不存储，避免永驻内存）
        - 正数：ttl 秒后过期
        """
        with self._lock:
            if ttl is not None and ttl <= 0:
                # 立即过期：删除已有项，不存储新值
                self._store.pop(key, None)
                return
            expire_time = time.time() + ttl if ttl is not None else None
            self._store[key] = (value, expire_time)

    def delete(self, key: str) -> None:
        """删除值"""
        with self._lock:
            self._store.pop(key, None)

    def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配的键（简单前缀匹配），同步清理已过期项避免内存泄漏"""
        with self._lock:
            now = time.time()
            expired = [
                k for k, (_, exp) in self._store.items()
                if exp is not None and now > exp
            ]
            for k in expired:
                del self._store[k]
            remaining = list(self._store.keys())
            if pattern == "*":
                return remaining
            prefix = pattern.rstrip("*")
            return [k for k in remaining if k.startswith(prefix)]

    def ping(self) -> bool:
        """内存缓存总是可用"""
        return True


class CacheLayer:
    """统一缓存层（Redis + 内存回退）"""

    def __init__(self, namespace: str = "crypto_trading"):
        self._namespace = namespace
        self._redis = None
        self._memory = MemoryCache()
        self._use_redis = False
        # Redis 自动恢复：指数退避重连
        self._reconnect_lock = threading.Lock()
        self._reconnect_backoff = 5       # 初始退避秒数
        self._reconnect_max_backoff = 300  # 最大退避（5分钟）
        self._next_reconnect = 0.0         # 下次允许重连的时间戳
        self._reconnect_timer: Optional[threading.Timer] = None
        # 熔断：连续失败 N 次才禁用 Redis，避免单次抖动就回退内存
        self._redis_failures = 0
        self._max_redis_failures = 3

        # 尝试连接 Redis
        self._init_redis()

    def _init_redis(self) -> None:
        """初始化 Redis 连接"""
        try:
            from redis import Redis

            self._redis = Redis.from_url(
                config.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=3,
            )
            self._redis.ping()
            self._use_redis = True
            # 掩码密码后再记录日志
            masked_url = re.sub(r'://[^:]*:[^@]*@', '://***:***@', config.REDIS_URL)
            logger.info(f"CacheLayer: Redis connected at {masked_url}")
        except Exception as e:
            logger.warning(f"CacheLayer: Redis unavailable, using memory cache: {e}")
            self._use_redis = False
            self._redis = None
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """安排 Redis 重连（指数退避），使用独立线程避免阻塞主流程。"""
        with self._reconnect_lock:
            now = time.time()
            if now < self._next_reconnect:
                return  # 还在退避期内

            self._next_reconnect = now + self._reconnect_backoff
            # 指数退避翻倍，上限 5 分钟
            self._reconnect_backoff = min(self._reconnect_backoff * 2, self._reconnect_max_backoff)

        def _try_reconnect():
            try:
                from redis import Redis
                test_redis = Redis.from_url(
                    config.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=1,
                    socket_timeout=3,
                )
                test_redis.ping()
                with self._reconnect_lock:
                    self._redis = test_redis
                    self._use_redis = True
                    self._reconnect_backoff = 5  # 成功后重置退避
                masked_url = re.sub(r'://[^:]*:[^@]*@', '://***:***@', config.REDIS_URL)
                logger.info(f"CacheLayer: Redis reconnected at {masked_url}")
            except Exception:
                self._schedule_reconnect()

        self._reconnect_timer = threading.Timer(self._reconnect_backoff, _try_reconnect)
        self._reconnect_timer.daemon = True
        self._reconnect_timer.start()

    def _make_key(self, key: str) -> str:
        """生成带命名空间的键"""
        return f"{self._namespace}:{key}"

    @property
    def is_redis_available(self) -> bool:
        """Redis 是否可用"""
        return self._use_redis and self._redis is not None

    @property
    def backend_type(self) -> str:
        """当前缓存后端类型"""
        return "redis" if self._use_redis else "memory"

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值（自动 JSON 反序列化）

        参数：
            key: 缓存键

        返回：
            缓存值，不存在返回 None
        """
        full_key = self._make_key(key)

        try:
            if self._use_redis and self._redis:
                value = self._redis.get(full_key)
            else:
                value = self._memory.get(full_key)

            if value is None:
                return None

            self._redis_failures = 0  # 成功则重置失败计数

            # 尝试 JSON 反序列化
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            logger.warning(f"CacheLayer get error for {key}: {e}")
            # Redis 失败：连续失败计数，达到阈值才回退并调度重连
            self._redis_failures += 1
            if self._use_redis and self._redis_failures >= self._max_redis_failures:
                self._use_redis = False
                self._schedule_reconnect()
            return self._memory.get(full_key)

    def get_raw(self, key: str) -> Optional[str]:
        """获取原始字符串值（不反序列化）"""
        full_key = self._make_key(key)

        try:
            if self._use_redis and self._redis:
                return self._redis.get(full_key)
            else:
                return self._memory.get(full_key)
        except Exception as e:
            logger.warning(f"CacheLayer get_raw error for {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        设置缓存值（自动 JSON 序列化）

        参数：
            key: 缓存键
            value: 缓存值（会被 JSON 序列化）
            ttl: 过期时间（秒），None 表示不过期

        返回：
            是否成功
        """
        full_key = self._make_key(key)

        # JSON 序列化
        if isinstance(value, str):
            serialized = value
        else:
            try:
                serialized = json.dumps(value, ensure_ascii=False, default=str)
            except (TypeError, ValueError) as e:
                logger.error(f"CacheLayer set error: cannot serialize {key}: {e}")
                return False

        try:
            if self._use_redis and self._redis:
                if ttl:
                    self._redis.setex(full_key, ttl, serialized)
                else:
                    self._redis.set(full_key, serialized)
                self._redis_failures = 0  # 成功则重置计数
                return True
            else:
                self._memory.set(full_key, serialized, ttl)
                return True

        except Exception as e:
            logger.warning(f"CacheLayer set error for {key}: {e}")
            # Redis 失败：连续失败计数，达到阈值才回退并调度重连
            self._redis_failures += 1
            if self._use_redis and self._redis_failures >= self._max_redis_failures:
                self._use_redis = False
                self._schedule_reconnect()
            self._memory.set(full_key, serialized, ttl)
            return False

    def delete(self, key: str) -> bool:
        """
        删除缓存值

        参数：
            key: 缓存键

        返回：
            是否成功
        """
        full_key = self._make_key(key)

        try:
            if self._use_redis and self._redis:
                self._redis.delete(full_key)
                return True
            else:
                self._memory.delete(full_key)
                return True

        except Exception as e:
            logger.warning(f"CacheLayer delete error for {key}: {e}")
            return False

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        full_key = self._make_key(key)

        try:
            if self._use_redis and self._redis:
                return bool(self._redis.exists(full_key))
            else:
                return self._memory.get(full_key) is not None
        except Exception:
            return False

    def keys(self, pattern: str = "*") -> List[str]:
        """
        获取匹配的键列表

        参数：
            pattern: 匹配模式（支持 * 通配符）

        返回：
            匹配的键列表（不含命名空间前缀）
        """
        full_pattern = self._make_key(pattern)

        try:
            if self._use_redis and self._redis:
                # 生产环境用 scan_iter 替代 O(N) 阻塞 KEYS
                keys = list(self._redis.scan_iter(full_pattern))
                prefix = f"{self._namespace}:"
                return [k[len(prefix):] if k.startswith(prefix) else k for k in keys]
            else:
                keys = self._memory.keys(full_pattern)
                prefix = f"{self._namespace}:"
                return [k[len(prefix):] if k.startswith(prefix) else k for k in keys]
        except Exception as e:
            logger.warning(f"CacheLayer keys error: {e}")
            return []

    def clear(self, pattern: str = "*") -> int:
        """
        清除匹配的缓存

        参数：
            pattern: 匹配模式

        返回：
            清除的键数量
        """
        keys_to_delete = self.keys(pattern)
        count = 0
        for key in keys_to_delete:
            if self.delete(key):
                count += 1
        return count

    def ping(self) -> bool:
        """测试缓存连接"""
        try:
            if self._use_redis and self._redis:
                return self._redis.ping()
            else:
                return self._memory.ping()
        except Exception:
            return False

    def info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        info = {
            "backend": self.backend_type,
            "namespace": self._namespace,
            "redis_available": self.is_redis_available,
        }

        if self._use_redis and self._redis:
            try:
                redis_info = self._redis.info()
                info["redis_version"] = redis_info.get("redis_version")
                info["used_memory_human"] = redis_info.get("used_memory_human")
            except Exception:
                pass

        return info


# 全局缓存实例
cache = CacheLayer()


# 缓存键常量
class CacheKeys:
    """缓存键常量定义"""

    # WebSocket 行情缓存
    TICKERS_SNAPSHOT = "tickers:snapshot"

    # Paper Trading 状态缓存
    PAPER_STATE = "paper:state"
    PAPER_METRICS = "paper:metrics"

    # OHLCV 数据缓存（key 格式：ohlcv:{symbol}:{timeframe}）
    @staticmethod
    def ohlcv(symbol: str, timeframe: str) -> str:
        return f"ohlcv:{symbol.replace('/', '_')}:{timeframe}"

    # 回测结果缓存（key 格式：backtest:{strategy}:{params_hash}）
    @staticmethod
    def backtest(strategy: str, params_hash: str) -> str:
        return f"backtest:{strategy}:{params_hash}"


# 导出
__all__ = ["CacheLayer", "cache", "CacheKeys", "MemoryCache"]
