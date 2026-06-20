# 数据库 Schema 参考

**文档版本：** v1.0  
**创建日期：** 2026-06-20  
**状态：** ✅ 基于实际源码生成  
**对应门禁：** `DATA_QUALITY_STANDARD.md`

---

## 1. 技术选型

| 组件 | 选型 | 版本 | 用途 |
|------|------|------|------|
| **主数据库** | TimescaleDB (PostgreSQL 扩展) | 2.17.0-pg16 | 时序业务数据、监控指标存储 |
| **缓存** | Redis | 7.4-alpine | 实时行情缓存、会话状态 |
| **Python ORM** | SQLAlchemy | `create_engine()` + `sessionmaker()` (见 `src/utils/database.py`) | 对象关系映射，连接池管理 |
| **裸连接** | psycopg2 | (通过 `requirements.txt` 锁定) | 批量操作、裸查询 |

### 选择依据

- **TimescaleDB**：K 线数据天然是时序数据；hypertable 自动按时间分片，查询性能优于普通 PG 表。
- **Redis**：WebSocket 实时行情推送、缓存 TTL 天然适合。
- **双连接策略**：SQLAlchemy 管理 ORM / 连接池；psycopg2 裸连接处理批量 `executemany`（避免 ORM overhead）。

---

## 2. 表 Schema

### 2.1 `monitor_metrics`（监控指标表）

**来源文件：** `config/sql/01_monitor_metrics.sql`（Docker 首次启动自动执行）

```sql
CREATE TABLE IF NOT EXISTS monitor_metrics (
    timestamp           TIMESTAMPTZ      NOT NULL,
    total_value         DOUBLE PRECISION NOT NULL,
    total_return        DOUBLE PRECISION NOT NULL,
    realized_pnl        DOUBLE PRECISION NOT NULL,
    total_trades        INTEGER          NOT NULL,
    risk_state          TEXT,
    consecutive_losses  INTEGER
);

-- 转为 TimescaleDB hypertable，按 timestamp 7 天分片
SELECT create_hypertable('monitor_metrics', 'timestamp', if_not_exists => TRUE);
```

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `timestamp` | `TIMESTAMPTZ` | NOT NULL | 指标记录时间（UTC） |
| `total_value` | `DOUBLE PRECISION` | NOT NULL | 账户总权益 (USDT) |
| `total_return` | `DOUBLE PRECISION` | NOT NULL | 累计收益率 |
| `realized_pnl` | `DOUBLE PRECISION` | NOT NULL | 已实现盈亏 |
| `total_trades` | `INTEGER` | NOT NULL | 累计成交笔数 |
| `risk_state` | `TEXT` | 可空 | 风控状态：`ACTIVE` / `PAUSED` / `STOPPED` |
| `consecutive_losses` | `INTEGER` | 可空 | 连续亏损笔数 |

**时序配置：**
- 扩展：`CREATE EXTENSION IF NOT EXISTS timescaledb`
- Hypertable 分片键：`timestamp`
- 默认 chunk 间隔：7 天（TimescaleDB 默认值）

**数据来源：** `src/execution/paper_trading_runner.py` 结束时调用 `MetricsCollector.to_records()` 展平写入。Grafana 面板直接查询此表。

---

### 2.2 ORM 模型表（SQLAlchemy 管理）

⚠️ **待验证：** 以下表由 SQLAlchemy ORM 模型定义自动创建。当前源码中 ORM 模型定义位于何处需进一步确认（可能在 `src/models/` 或 `src/utils/models.py`，当前 Glob 未发现独立 models 目录）。以下为基于 `src/api/service.py` 查询逻辑的推断：

| 推断表名 | 用途 | 推断依据 |
|----------|------|----------|
| `strategies` | 策略定义与状态 | `service.py` 查询 "策略列表" |
| `positions` | 当前持仓 | `service.py` 查询 "持仓" |
| `orders` | 历史订单 | `service.py` 查询 "订单与成交" |
| `account_snapshots` | 账户快照 | `service.py` 查询 "账户摘要" |

> **⚠️ 以上 4 表为推断**，实际 ORM 模型定义需核实 `src/models/` 或等价模块后更新。

---

### 2.3 `data_versions` 元数据表（设计文档引用）

`DATA_QUALITY_STANDARD.md` 设计了一组数据版本表（`ohlcv_data` + `data_versions`），但当前代码中未见对应 ORM 模型或 SQL 迁移脚本。**状态：设计已完成，代码未落地。**

---

## 3. Redis 缓存结构

**连接配置：** 由 `config.REDIS_URL` 指定（格式：`redis://[:password]@host:port/db`）  
**客户端：** `redis-py`（`DatabaseManager._redis_client`，`decode_responses=True`）  
**连接测试：** `redis_client.ping()` 在 `init_redis()` 中执行

### 已知 Key 模式（基于源码追踪）

| Key 模式 | 类型 | TTL | 用途 |
|----------|------|-----|------|
| `ticker:{symbol}` | String (JSON) | 待验证 | 实时行情缓存（`src/api/ws_feed.py` 写入，API 端点读取） |
| `ws:subscriptions` | Set | 无 | WebSocket 客户端订阅列表 |
| `cache:*` | 由 `src/utils/cache.py` 管理 | 可配置 | 通用缓存（带熔断器保护） |

> ⚠️ Redis key 完整清单待验证：`src/api/service.py` 和 `src/utils/cache.py` 可能定义额外 key，需进一步审计。

---

## 4. 连接参数来源

### 4.1 TimescaleDB

| 参数 | 环境变量 | 默认值 | 使用位置 |
|------|----------|--------|----------|
| Host | `TIMESCALE_HOST` | `localhost` | `database.py:48` → `psycopg2.connect(host=...)` |
| Port | `TIMESCALE_PORT` | `5432` | `database.py:49` |
| User | `TIMESCALE_USER` | `postgres` | `database.py:50` |
| Password | `TIMESCALE_PASSWORD` | 空字符串 | `database.py:51` |
| Database | `TIMESCALE_DATABASE` | `crypto_trading` | `database.py:52` |
| URL (SQLAlchemy) | `DATABASE_URL` | 空字符串 | `database.py:37` → `create_engine(config.DATABASE_URL, ...)` |

### 4.2 Redis

| 参数 | 环境变量 | 默认值 | 使用位置 |
|------|----------|--------|----------|
| URL | `REDIS_URL` | 自动构造（见下方逻辑） | `database.py:63` → `Redis.from_url(config.REDIS_URL)` |
| Password | `REDIS_PASSWORD` | 空字符串 | 用于自动构造 `REDIS_URL`（如未设置 `REDIS_URL`） |

**REDIS_URL 构造逻辑**（`config.py:41-47`）：
1. 如果 `REDIS_URL` 已设置 → 直接使用
2. 否则如果 `REDIS_PASSWORD` 存在 → `redis://:{REDIS_PASSWORD}@localhost:6379/0`
3. 否则 → `redis://localhost:6379/0`

### 4.3 Docker Compose 层

Docker Compose 通过 `.env` 文件注入，容器间网络通信：

| 服务 | 容器内访问方式 | 
|------|--------------|
| TimescaleDB | `timescaledb:5432`（compose DNS） |
| Redis | `redis:6379` |
| Grafana → TimescaleDB | `timescaledb:5432`（通过 `config/grafana/datasources/timescaledb.yml`，密码从 `POSTGRES_PASSWORD` 注入） |

---

## 5. 数据库初始化流程

```
docker compose up -d
  └─ timescaledb 容器启动
       └─ /docker-entrypoint-initdb.d/ 自动挂载 ./config/sql/
            └─ 01_monitor_metrics.sql 执行
                 ├─ CREATE EXTENSION timescaledb
                 ├─ CREATE TABLE monitor_metrics
                 └─ SELECT create_hypertable(...)
```

- **幂等性**：`IF NOT EXISTS` / `if_not_exists => TRUE` 确保重复执行安全
- **首次启动**：数据卷为空时自动建表
- **已有数据卷**：不会重跑，需手动补建（见 `TROUBLESHOOTING.md` 故障 5）

---

## 6. 线程安全

`DatabaseManager` 通过 `threading.Lock`（`_pg_lock`）保护裸 psycopg2 连接的并发访问。SQLAlchemy 的 `Session` 通过 `scoped_session` 模式保证线程安全（每个线程独立 Session）。

---

**文档状态：** ✅ 基于源码生成  
**待验证项：** 4 个 ORM 推断表需代码确认；Redis key 完整清单  
**更新日期：** 2026-06-20
