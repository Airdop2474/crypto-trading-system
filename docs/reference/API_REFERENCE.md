# API 参考文档

**文档版本**：v1.0
**创建日期**：2026-06-20
**信息来源**：源码交叉验证 — `src/api/app.py`、`src/api/service.py`、`src/api/ws_feed.py`、`deliverables/qa-report-pre-launch.md`
**状态**：✅ 准确（与源码一致）

---

## 概述

Crypto Trading System 提供基于 **FastAPI** 的 REST API 和 **WebSocket** 实时行情推送。所有端点（除 `/health` 和 `/market/tickers` 外）均需要 **X-API-Token** 认证。

**Base URL**：`http://localhost:8000`

**全局速率限制**：50 req/s（slowapi），Agent 类端点额外限制 10 req/min

---

## 认证机制

### X-API-Token Header

```
X-API-Token: <your_token>
```

- 使用 `secrets.compare_digest()` 进行恒定时间比较（防时序攻击）
- 认证失败返回 `403 Forbidden`
- `API_TOKEN` 未配置时返回 `503 Service Unavailable`
- 配置位置：环境变量 `API_TOKEN`，通过 `src/utils/config.py` 读取

### WebSocket 认证

WebSocket 不使用 URL query parameter 传 token。客户端需在连接建立后，**首条 JSON 消息**发送认证：

```json
{"type": "auth", "token": "<your_token>"}
```

- 10 秒认证超时
- 认证失败返回 `{"error": "Invalid token"}` 并关闭连接（code 4001）
- `API_TOKEN` 未配置时返回 `{"error": "Server not configured"}` 并关闭（code 4001）

---

## 安全响应头

所有 HTTP 响应自动注入：

| Header | Value |
|--------|-------|
| `Content-Security-Policy` | `default-src 'self'` |
| `Strict-Transport-Security` | `max-age=31536000` |

CORS 允许来源（开发环境）：

```
http://localhost:3000, http://127.0.0.1:3000
http://localhost:3001, http://127.0.0.1:3001
```

生产环境应收紧 CORS 来源。

---

## 端点清单

### 系统健康

---

#### `GET /health`

- **认证**：❌ 不需要
- **描述**：基本健康检查，仅返回 `{"status":"ok"}`
- **请求参数**：无
- **响应**：
  ```json
  {"status": "ok"}
  ```
- **测试覆盖**：✅ 已测试
- **速率限制**：全局 50 req/s

---

#### `GET /health/detailed`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：详细健康状态（WebSocket 连接数、缓存后端类型等）
- **请求参数**：无
- **响应**：
  ```json
  {
    "status": "ok",
    "ws_connected": true,
    "ws_clients": 3,
    "cache_backend": "redis",
    "cache_available": true
  }
  ```
- **测试覆盖**：❌ 未测试
- **速率限制**：全局 50 req/s

---

### 账户与行情

---

#### `GET /account/summary`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：账户总览（余额、总盈亏、已实现盈亏、未实现盈亏）
- **请求参数**：无
- **响应**：
  ```json
  {
    "total_equity": 10234.56,
    "cash": 8500.00,
    "total_pnl": 234.56,
    "total_pnl_pct": 2.35,
    "realized_pnl": 180.00,
    "unrealized_pnl": 54.56
  }
  ```
- **测试覆盖**：✅ shape + 对账
- **速率限制**：全局 50 req/s

---

#### `GET /market/tickers`

- **认证**：❌ 不需要
- **描述**：当前行情快照。优先使用 WebSocket 实时缓存，回退到 REST 轮询
- **请求参数**：无
- **响应**：
  ```json
  {
    "BTC/USDT": {"bid": 67432.50, "ask": 67435.20, "last": 67433.80, "change": 1.25},
    "ETH/USDT": {"bid": 3456.80, "ask": 3457.50, "last": 3457.10, "change": -0.45}
  }
  ```
- **测试覆盖**：✅ + 离线回退
- **速率限制**：全局 50 req/s

---

### 策略管理

---

#### `GET /strategies`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：获取所有策略列表及实时状态
- **请求参数**：无
- **响应**：
  ```json
  [
    {
      "id": "grid-btc-usdt-65000",
      "name": "Grid BTC/USDT",
      "type": "grid",
      "symbol": "BTC/USDT",
      "status": "running",
      "pnl": 125.50,
      "pnlPct": 1.26,
      "runningDays": 45
    }
  ]
  ```
- **测试覆盖**：✅
- **速率限制**：全局 50 req/s

---

#### `GET /strategies/{strategy_id}/status`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：获取单个策略状态（暂无独立 GET，此端点返回策略状态）
- **路径参数**：`strategy_id` — 策略 ID（如 `grid-btc-usdt-65000`）
- **测试覆盖**：⚠️ 仅 PATCH echo 测试

---

#### `PATCH /strategies/{strategy_id}/status`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：更新策略运行状态（start/pause/stop）
- **路径参数**：`strategy_id` — 策略 ID
- **请求体**：
  ```json
  {"status": "paused"}
  ```
  可选值：`running`、`paused`、`stopped`
- **响应**：
  ```json
  {
    "strategy_id": "grid-btc-usdt-65000",
    "status": "paused",
    "previous_status": "running"
  }
  ```
- **测试覆盖**：✅ echo 测试
- **速率限制**：全局 50 req/s

---

#### `POST /strategies/create-grid`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：创建新的网格交易策略（返回策略元数据，引擎已运行）
- **请求体**：
  ```json
  {
    "symbol": "BTC/USDT",
    "lowerPrice": 65000.0,
    "upperPrice": 68000.0,
    "gridCount": 10,
    "investment": 10000.0
  }
  ```
  | 字段 | 类型 | 必填 | 约束 | 说明 |
  |------|------|------|------|------|
  | `symbol` | string | 否 | 默认 `BTC/USDT` | 交易对 |
  | `lowerPrice` | float | ✅ | 必须 < `upperPrice` | 网格下界 |
  | `upperPrice` | float | ✅ | 必须 > `lowerPrice` | 网格上界 |
  | `gridCount` | int | 否 | 3–50，默认 10 | 网格数量 |
  | `investment` | float | 否 | 默认 10000 | 投入资金 |
- **响应**：
  ```json
  {
    "id": "grid-btc-usdt-65000",
    "name": "Grid BTC/USDT",
    "type": "grid",
    "symbol": "BTC/USDT",
    "status": "running",
    "pnl": 0.0,
    "pnlPct": 0.0,
    "investment": 10000.0,
    "runningDays": 0,
    "createdAt": "2026-06-20T12:00:00",
    "grid": {
      "upperPrice": 68000.0,
      "lowerPrice": 65000.0,
      "gridCount": 10,
      "perGridProfit": 0.46,
      "filledGrids": 0,
      "arbitrageCount": 0
    }
  }
  ```
- **错误**：`400` — `lowerPrice >= upperPrice` 或 `gridCount` 不在 3–50 范围
- **测试覆盖**：❌ 未测试
- **速率限制**：全局 50 req/s

---

### 持仓与资产

---

#### `GET /positions`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：获取当前所有持仓
- **请求参数**：无
- **响应**：
  ```json
  [
    {
      "symbol": "BTC/USDT",
      "side": "long",
      "quantity": 0.015,
      "entry_price": 67100.00,
      "current_price": 67433.80,
      "unrealized_pnl": 5.01,
      "unrealized_pnl_pct": 0.50
    }
  ]
  ```
- **测试覆盖**：❌ 未测试
- **速率限制**：全局 50 req/s

---

#### `GET /assets`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：获取当前资产分布
- **请求参数**：无
- **响应**：
  ```json
  [
    {"asset": "USDT", "free": 8500.00, "locked": 0},
    {"asset": "BTC", "free": 0.015, "locked": 0}
  ]
  ```
- **测试覆盖**：❌ 未测试
- **速率限制**：全局 50 req/s

---

### 订单

---

#### `GET /orders`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：获取订单历史（含已成交、已取消）
- **请求参数**：无
- **响应**：
  ```json
  [
    {
      "id": "ord-001",
      "symbol": "BTC/USDT",
      "side": "buy",
      "type": "limit",
      "quantity": 0.005,
      "price": 67100.00,
      "status": "filled",
      "timestamp": "2026-06-20T11:30:00"
    }
  ]
  ```
- **测试覆盖**：✅
- **速率限制**：全局 50 req/s

---

### 分析

---

#### `GET /analytics/pnl-history`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：获取盈亏历史时间序列数据
- **请求参数**：无
- **响应**：
  ```json
  [
    {"date": "2026-06-19", "pnl": 12.50, "cumulative_pnl": 234.56},
    {"date": "2026-06-20", "pnl": -5.00, "cumulative_pnl": 229.56}
  ]
  ```
- **测试覆盖**：✅
- **速率限制**：全局 50 req/s

---

#### `GET /analytics/strategy-performance`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：各策略性能指标对比
- **请求参数**：无
- **响应**：
  ```json
  [
    {
      "strategy": "GridTrading",
      "total_return": 2.35,
      "sharpe_ratio": 1.42,
      "max_drawdown": -4.20,
      "win_rate": 0.68,
      "total_trades": 142
    }
  ]
  ```
- **测试覆盖**：✅
- **速率限制**：全局 50 req/s

---

### 多策略

---

#### `GET /multi/summary`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：多策略聚合摘要 — 总盈亏、总交易数、各策略运行状态
- **请求参数**：无
- **响应**：
  ```json
  {
    "total_pnl": 345.67,
    "total_trades": 890,
    "active_strategies": 6,
    "paused_strategies": 2,
    "strategies": [
      {"id": "grid-btc-usdt-65000", "name": "Grid BTC/USDT", "status": "running", "pnl": 125.50}
    ]
  }
  ```
- **测试覆盖**：❌ 未测试
- **速率限制**：全局 50 req/s

---

#### `GET /multi/details`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：每个策略的详细运行结果（性能指标 + 交易历史摘要）
- **请求参数**：无
- **响应**：
  ```json
  [
    {
      "strategy_id": "grid-btc-usdt-65000",
      "name": "Grid BTC/USDT",
      "total_return": 2.35,
      "sharpe": 1.42,
      "max_drawdown": -4.20,
      "win_rate": 0.68,
      "trade_count": 142,
      "status": "running"
    }
  ]
  ```
- **测试覆盖**：❌ 未测试
- **速率限制**：全局 50 req/s

---

#### `GET /multi/strategy/{strategy_id}`

- **认证**：✅ 需要 `X-API-Token`
- **描述**：获取单个策略的完整运行结果
- **路径参数**：`strategy_id` — 策略 ID
- **响应**：策略运行详情对象
- **错误**：`404` — 策略不存在
- **测试覆盖**：❌ 未测试
- **速率限制**：全局 50 req/s

---

### AI Agent（只分析，不执行）

---

#### `POST /agent/analyze`

- **认证**：✅ 需要 `X-API-Token`
- **速率限制**：10 req/min（严格限制，防洪水攻击）
- **描述**：触发 AI 分析任务。AI **只分析不执行任何交易决策**
- **请求体**：
  ```json
  {
    "task": "backtest",
    "phase": "Phase 6"
  }
  ```
  | 字段 | 类型 | 必填 | 说明 |
  |------|------|------|------|
  | `task` | Literal | ✅ | `backtest`、`trade_attribution`、`risk_checklist`、`param_sensitivity`、`weekly_review` |
  | `phase` | string | 否 | 默认 `Phase 6`，当前阶段标识 |
- **响应**：根据 task 类型返回分析报告
  - `backtest` → 回测报告
  - `weekly_review` → 周回报
  - `trade_attribution` → 失败交易归因
  - `risk_checklist` → 风控清单
  - `param_sensitivity` → 参数敏感性报告
- **测试覆盖**：❌ 未测试
- **安全**：task 字段使用 `Literal` 约束，防止注入

---

#### `GET /agent/audit-logs`

- **认证**：✅ 需要 `X-API-Token`
- **速率限制**：10 req/min
- **描述**：获取 AI 分析审计日志
- **查询参数**：

  | 参数 | 类型 | 必填 | 默认值 | 说明 |
  |------|------|------|--------|------|
  | `task` | string | 否 | — | 按任务类型过滤 |
  | `limit` | int | 否 | 50 | 返回条数上限 |
- **响应**：
  ```json
  [
    {
      "id": "log-001",
      "task": "backtest",
      "timestamp": "2026-06-20T12:00:00",
      "summary": "Grid strategy backtest analysis",
      "recommendations": ["Increase grid count to 15"]
    }
  ]
  ```
- **测试覆盖**：❌ 未测试

---

#### `GET /agent/adoption-rate`

- **认证**：✅ 需要 `X-API-Token`
- **速率限制**：10 req/min
- **描述**：获取 AI 建议采纳率统计
- **查询参数**：

  | 参数 | 类型 | 必填 | 默认值 | 说明 |
  |------|------|------|--------|------|
  | `task` | string | 否 | — | 按任务类型过滤 |
- **响应**：
  ```json
  {
    "total_suggestions": 45,
    "adopted": 32,
    "rejected": 8,
    "pending": 5,
    "adoption_rate": 0.71
  }
  ```
- **测试覆盖**：❌ 未测试

---

### WebSocket

---

#### `WS /ws/tickers`

- **认证**：✅ 首条消息认证 `{"type":"auth","token":"..."}`
- **描述**：实时行情推送。连接后立即发送当前 ticker 快照，此后每当 Binance 推送更新时广播
- **连接限制**：最多 50 个并发客户端（超额返回 `{"error":"Too many connections"}`，code 4002）
- **认证超时**：10 秒
- **心跳**：30 秒无数据时发送 `{"type":"ping"}`
- **消息格式**（与 `GET /market/tickers` 相同）：
  ```json
  {
    "BTC/USDT": {"bid": 67432.50, "ask": 67435.20, "last": 67433.80, "change": 1.25}
  }
  ```
- **异常处理**：`WebSocketDisconnect` 正常断开；其他 `Exception` 写入 logger
- **测试覆盖**：❌ 未测试

---

## 端点测试覆盖总览

（数据来自 `qa-report-pre-launch.md` 2026-06-20）

| 端点 | 方法 | 认证 | 测试覆盖 | 状态 |
|------|------|------|----------|------|
| `/health` | GET | ❌ | ✅ | 🟢 |
| `/health/detailed` | GET | ✅ | ❌ | 🔴 |
| `/account/summary` | GET | ✅ | ✅ shape + 对账 | 🟢 |
| `/market/tickers` | GET | ❌ | ✅ + 离线回退 | 🟢 |
| `/strategies` | GET | ✅ | ✅ | 🟢 |
| `/strategies/{id}/status` | PATCH | ✅ | ✅ echo | 🟢 |
| `/strategies/create-grid` | POST | ✅ | ❌ | 🔴 |
| `/positions` | GET | ✅ | ❌ | 🔴 |
| `/assets` | GET | ✅ | ❌ | 🔴 |
| `/orders` | GET | ✅ | ✅ | 🟢 |
| `/analytics/pnl-history` | GET | ✅ | ✅ | 🟢 |
| `/analytics/strategy-performance` | GET | ✅ | ✅ | 🟢 |
| `/multi/summary` | GET | ✅ | ❌ | 🔴 |
| `/multi/details` | GET | ✅ | ❌ | 🔴 |
| `/multi/strategy/{id}` | GET | ✅ | ❌ | 🔴 |
| `/agent/analyze` | POST | ✅ | ❌ | 🔴 |
| `/agent/audit-logs` | GET | ✅ | ❌ | 🔴 |
| `/agent/adoption-rate` | GET | ✅ | ❌ | 🔴 |
| `/ws/tickers` | WS | ✅ | ❌ | 🔴 |

**API 端点测试覆盖率：8/18 (44%)**

---

## 错误码

| 状态码 | 含义 | 触发条件 |
|--------|------|----------|
| `200` | 成功 | — |
| `400` | 请求参数错误 | `lowerPrice >= upperPrice`、`gridCount` 越界 |
| `403` | 认证失败 | 无效/缺失 `X-API-Token` |
| `404` | 资源不存在 | 策略 ID 未找到 |
| `429` | 速率限制 | 超过全局 50 req/s 或 Agent 10 req/min |
| `503` | 服务不可用 | `API_TOKEN` 未配置 |
| `4001` | WebSocket 认证失败 | 无效 token / 超时 / 非法消息 |
| `4002` | WebSocket 连接数超限 | 超过 50 并发 |

---

## 快速上手：curl 示例

```bash
# 1. 健康检查（无需认证）
curl http://localhost:8000/health

# 2. 设置 API Token（替换为实际值）
export API_TOKEN="your_secret_token"

# 3. 获取账户摘要（需要认证）
curl -H "X-API-Token: $API_TOKEN" \
  http://localhost:8000/account/summary

# 4. 获取行情（无需认证）
curl http://localhost:8000/market/tickers

# 5. 获取策略列表
curl -H "X-API-Token: $API_TOKEN" \
  http://localhost:8000/strategies

# 6. 创建网格策略
curl -X POST \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC/USDT","lowerPrice":65000,"upperPrice":68000,"gridCount":10,"investment":10000}' \
  http://localhost:8000/strategies/create-grid

# 7. 暂停策略
curl -X PATCH \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"paused"}' \
  http://localhost:8000/strategies/grid-btc-usdt-65000/status

# 8. 触发 AI 回测分析
curl -X POST \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task":"backtest","phase":"Phase 6"}' \
  http://localhost:8000/agent/analyze

# 9. 查看 AI 审计日志
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/agent/audit-logs?limit=20"

# 10. WebSocket 连接（使用 wscat 或类似工具）
# wscat -c ws://localhost:8000/ws/tickers
# 连接后发送：{"type":"auth","token":"your_secret_token"}
```

---

## 启动方式

```bash
uvicorn src.api.app:app --reload --port 8000
```

启动时自动连接 Binance WebSocket 行情订阅。关闭时优雅断开。

---

**文档结束** — 所有端点信息来自 `src/api/app.py`（2026-06-20 快照）、`deliverables/qa-report-pre-launch.md`。
