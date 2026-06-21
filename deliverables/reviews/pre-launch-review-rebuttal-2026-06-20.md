# 上线审查报告复核意见

**日期**: 2026-06-20  
**复核范围**: `deliverables/gstack/pre-launch-check-full-2026-06-20.md`  
**复核方式**: 逐项对照项目源码验证每一条发现的准确性和定位

---

## 总体评价

报告整体质量较高，7 项 CRITICAL 中 5 项完全准确、1 项部分准确、1 项存在定性夸大。12 项 HIGH 全部经代码验证属实。结论"No-Go"是合理的，但个别严重度分级和描述需要修正。此外，复核中发现了 2 项报告遗漏的重要问题。

---

## 一、CRITICAL 逐项复核

### R-01 前端认证头缺失 — ✅ 完全准确

`frontend/lib/api.ts` 的 `get<T>()`、`updateStrategyStatus()`（PATCH）、`createGridStrategy()`（POST）均不携带 `X-API-Token`。SWR fetcher（`components/swr-provider.tsx`）只设置 `Accept` 头。前端 WebSocket 连接（`hooks/use-tickers-ws.ts`）也不传 `?token=`。后端 18 个端点中确实有 15 个通过 `Security(verify_api_token)` 强制认证，"15/18"的计数准确。

**小修正**: "前端全量 403"稍有过度——`/health` 和 `/market/tickers` 两个公开端点不会 403，但前端对这两个端点没有封装调用函数，所以实际影响不大。

### R-02 全 API 零速率限制 — ✅ 完全准确

`src/api/app.py` 无任何限速中间件或装饰器。`requirements.txt` 中也没有 `slowapi`、`limits` 等包。CCXT 客户端的 `enableRateLimit` 仅控制出站交易所调用，与入站 API 无关。

### R-03 WebSocket 异常静默吞没 — ✅ 完全准确

`src/api/app.py` 第 155-158 行：

```python
except WebSocketDisconnect:
    pass
except Exception:
    pass
```

`WebSocketDisconnect` 的 pass 是惯例无害，但 `except Exception: pass` 确实会吞掉所有非预期异常（序列化错误、数据源异常、代码 bug 等），导致生产问题完全不可观测。`finally` 块正确清理了资源，但零日志输出意味着运维无法排查问题。

### R-04 RiskManager reset() TOCTOU 与脆弱状态恢复 — ⚠️ 部分准确，需修正

**TOCTOU 说法不准确。** `reset()` 的完整逻辑在 `with self._lock:` 内执行（第 247 行），不存在对外的 TOCTOU 窗口。所有并发方法（`can_trade`、`record_fill`、`resume` 等）同样需要获取同一把锁，访问是完全序列化的。

**脆弱状态恢复说法准确，但报告遗漏了更严重的问题：**

1. `_init_state()` 将所有字段清零后，`reset()` 手动恢复三个防抖计数器（`_reset_count`、`_last_reset_time`、`_reset_window_start`）。未来如果新增防抖字段而忘记在 `reset()` 中 save/restore，该字段会在每次 reset 时被静默清零——这个设计确实是脆弱的。

2. **报告未提到的更严重问题**: `_init_state()` 会将 `peak_equity` 重置为 `capital_base`、`cumulative_pnl` 重置为 0。这意味着每次 reset 后，最大回撤熔断器会"失忆"——一个已经亏损 14%（接近 15% 熔断线）的策略，reset 后再亏 14%，熔断器只会记录 14% 而非真实的 ~28% 累计回撤。这对交易安全是实质性威胁。

**建议**: 将此项的 TOCTOU 描述修正为"锁内脆弱状态恢复 + 回撤熔断失忆"，补充 `peak_equity`/`cumulative_pnl` 在 reset 后被清零的安全隐患。严重度维持 CRITICAL 不变。

### R-05 WebSocket token 通过 URL query 传递 — ✅ 完全准确

`src/api/app.py` 第 128 行 `ws.query_params.get("token")` 确认 token 在 URL 中传递。值得肯定的是，比较操作使用了 `secrets.compare_digest`（常数时间），防护了时序攻击。但 token 出现在服务器日志、代理日志、浏览器历史中是事实，对交易系统来说这是凭证泄露风险。

### R-06 Docker Python 版本不匹配 — ⚠️ 定性夸大，建议降级为 HIGH

**"项目要求 Python 3.13"这一说法缺乏依据。** 经过检查：

- `Dockerfile` 两个阶段均使用 `python:3.11-slim-bookworm`
- `pyproject.toml` 的 black `target-version` 是 `py311`，mypy `python_version` 是 `3.11`
- `requirements.txt` 无 `requires-python` 约束
- 项目中不存在 `setup.py`、`setup.cfg`、`.python-version` 文件

项目的所有正式配置都指向 Python 3.11 且内部一致。"3.13"来源似乎是开发者本地运行环境或 QA 报告中的描述，但这并非项目正式要求。

**更准确的描述应为**: "开发者本地环境运行 Python 3.13，但 Docker 镜像和配置锁定 3.11，两者间可能存在行为差异（如新语法特性、stdlib 变更）。"

**建议**: 降级为 HIGH。如果要升级，方向应该是将 Docker 统一到与本地开发一致的 3.13，或者反过来让开发者使用 3.11——但不应以"项目要求 3.13"为由标记为 CRITICAL。

### R-07 前端零测试覆盖 — ✅ 完全准确

`frontend/` 目录下不存在任何测试文件（`*.test.*`、`*.spec.*`、`__tests__/`），`package.json` 无 `test` 脚本，devDependencies 中无任何测试框架（jest、vitest、testing-library 等）。对于加密交易系统的用户界面，这确实是重大风险。

---

## 二、HIGH 逐项复核

12 项 HIGH 发现**全部经代码验证属实**，具体确认：

| 项 | 验证结果 | 补充说明 |
|---|---|---|
| R-08 无 CSP | ✅ 准确 | 全项目无 CSP 相关代码，无任何安全响应头中间件 |
| R-09 无 HSTS | ✅ 准确 | 同上 |
| R-10 Health 泄露内部状态 | ✅ 准确 | 第 82-90 行暴露 `ws_connected`、`ws_clients`、`cache_backend`，无认证 |
| R-11 API_TOKEN 未配置返回 500 | ✅ 准确 | 第 71-74 行明确 `HTTP_500_INTERNAL_SERVER_ERROR`，docstring 说明是有意为之（fail-secure）。是否算 bug 可以商榷，但 503 确实是更规范的做法 |
| R-12 record_fill() 缺锁保护 | ✅ 准确 | 第 146 行 `with self._lock:` 仅保护 `profit = trade.get("profit")` 一行，后续 `daily_pnl`、`cumulative_pnl`、`consecutive_losses` 修改及熔断检查全部在锁外——**这是缩进错误** |
| R-13 Decimal(str(float)) | ✅ 准确 | 第 133-136 行及后续多处使用此模式，实际风险可控但非最佳实践 |
| R-14 多策略路径缺 RiskManager | ✅ 准确 | `service.py` 第 141-144 行 `MultiStrategyRunner` 构造未传 `risk_manager`，`None` 传播到所有子 Runner |
| R-15 BuyAndHold 未继承 RiskAwareStrategy | ✅ 准确 | 其余 7 个策略均继承 `RiskAwareStrategy`，唯独 `BuyAndHoldStrategy` 直接继承 `Strategy` |
| R-16 CORS 允许 localhost | ✅ 准确 | 第 45-53 行硬编码 4 个 localhost 源，注释承认"生产应收紧"但未实现环境条件逻辑 |
| R-17 verify_api_token() 无测试 | ✅ 准确 | 无对应测试文件 |
| R-18 .env 文件存在 | ✅ 准确 | 文件存在但为占位值，已在 `.gitignore` 中排除，风险可控 |
| R-19 trading_system 服务被注释 | ✅ 准确 | `docker-compose.yml` 第 66-82 行全部注释，`docker-compose up` 不会启动应用 |

---

## 三、报告遗漏的重要问题

复核中发现 2 项报告未覆盖的值得关注问题：

### 新增 1: psycopg2 原始连接非线程安全（建议 HIGH）

`src/utils/database.py` 的 `DatabaseManager` 持有单个 `psycopg2` 连接（`self._pg_connection`），`get_cursor()` 上下文管理器从该连接生成游标但未加锁。如果 `MetricsWriter.write_records()` 和其他数据库操作并发执行（API 服务器是异步/多线程环境），psycopg2 会抛出 `InterfaceError` 或产生数据损坏。SQLAlchemy 引擎有正确的连接池（`pool_size=5`），但原始连接路径完全绕过了池化机制。

### 新增 2: 仓位限制常量为 100%（建议 MEDIUM）

`src/constants.py` 第 20-21 行 `MAX_POSITION_PER_TRADE = 1.0`（100%）、`MAX_TOTAL_POSITION = 1.0`（100%），`service.py` 初始化 PaperBroker 时直接传入这些值。虽然当前是模拟交易，但这些常量如果被 live 配置沿用，意味着单笔交易可以使用全部资金。

---

## 四、修正后的结论

| 原报告 | 复核意见 |
|---|---|
| 7 CRITICAL | **6 CRITICAL**（R-06 降级为 HIGH） |
| 12 HIGH | **14 HIGH**（R-06 从 CRITICAL 降入 + 新增 psycopg2 线程安全 + 仓位限制） |
| No-Go | **维持 No-Go** — 6 项 CRITICAL 仍构成上线阻塞 |

### 关键修正建议

1. **R-04**: 删除 "TOCTOU" 描述，修正为"锁内脆弱状态恢复 + 回撤熔断失忆"，补充 `peak_equity`/`cumulative_pnl` 在 reset 后被清零的安全隐患
2. **R-06**: 降级为 HIGH，修正描述为"开发者本地 Python 3.13 与 Docker 镜像 3.11 不一致"，所有正式项目配置均指向 3.11
3. **P0 行动项 #6**: 从"Dockerfile 统一到 3.13"改为"确认项目目标 Python 版本并统一所有环境"，负责人不变，预估不变
4. **新增 P1 行动项**: 为 `DatabaseManager` 原始连接添加线程安全保护（加锁或迁移到 SQLAlchemy 连接池）

---

> 复核完成。报告主体可靠，建议按上述修正调整后作为上线决策依据。
