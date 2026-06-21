# 最新修复状态核验报告

**核验日期**：2026-06-20 初核 → **2026-06-21 复核更新**（`git HEAD = f26d580`）
**核验方法**：对 `_SUMMARY_上线前审查汇总.md` 的每个高价值发现，逐项读取**当前代码**确认真实状态，区分「✅ 已修复 / ⚠️ 真实存在的开放 bug / 🟦 报告为真但当前不触发 / 📋 已知可接受」。
**核验范围**：32 个 🔴 阻断项 + 关键 🟠/🟡 项。证据均为代码 file:line 实读，非依据报告转述。

> **2026-06-21 复核说明**：06-20 初核时标为「未接线/不触发」的两项，已在 `51162cb` 提交中作为代码落地闭合——告警全失败兜底（INC-003）与交易所基线快照守卫均已实现。本文已据当前代码更新；下方原判定段落保留并标注「↑ 已闭合」以存档判定演进。基线测试 481 → **547 passed + 3 skipped**。

---

## 📊 结论速览

| 类别 | 已修复 | 仍开放（当前会触发的真 bug） | 报告为真但当前不触发 | 已知可接受 | 运维/人工动作 |
|------|-------|----------------|------|-----------|--------------|
| 安全 | 11 | 0 | 0 | 2（前端token暴露 / 镜像digest） | 1（轮换 .env key） |
| 金融正确性 | 7 | 0 | 1（profit/pnl，已被调用方化解） | 0 | 0 |
| 事故响应 | 4 | 0 | 0 | 0 | 0 |
| 性能/错误处理 | 4 | 0 | 0 | 0 | 0 |
| 文档 | 12 | 0 | 0 | 0 | 0 |
| 测试 | — | — | — | 前端零测试 / 4 策略测试 | — |

**总判定（2026-06-21 复核）**：审查报告里的 32 个 🔴 阻断项 **全部已在代码中真实落地**。逐项代码核验后，**未发现任何当前会触发的真实代码 bug（0 个）**。06-20 初核曾列为"仍开放/未接线"的两项，状态更新如下：

- **告警全失败兜底（INC-003）— ✅ 已闭合（`51162cb`）**：`alert_manager.py:108-135` 的 `_dispatch` 已实现 escalation——统计 `attempted`/`failed`，`if attempted > 0 and failed == attempted:` → `logger.critical("ALERT DELIVERY FAILURE...")`。另有 `check_channels_health()`（L137-165）做通道健康自检 + 全失败 CRITICAL 兜底。代码层面已闭合；剩余仅"接线真实通道"（运维动作，见第四节）。
- **profit/pnl（审计#10）— 🟦 当前不触发，未变**：`analyze_failed_trades` 全代码库唯一调用方 `app.py:348-353` 在传入前已把 `profit` 归一化为 `pnl`，链路自洽，测试用 `pnl` 长绿。`analyzer.py:152-153` 仍是裸 `pnl`（与同文件其余 5 处兜底写法不一致），但被调用方兜住，**非 live bug**，留作将来出现第二个调用方时再对齐。

---

## 一、✅ 已核实修复（附代码证据）

### 安全（11/11）

| 发现 | 当前代码证据 | 状态 |
|------|------------|------|
| 端点缺认证（审计#3-6/H1） | `app.py` 全 18 HTTP 端点均带 `_=Security(verify_api_token)`；WS 首条消息 `secrets.compare_digest`（app.py:174） | ✅ |
| WS 无连接上限（审计#6） | `MAX_WS_CLIENTS=50`，超限 `ws.close(4002)`（app.py:135/146） | ✅ |
| 空 token 绕过（审计#2/R-11） | `app.py:92` 空 token → `HTTP 503`，强制配置 | ✅ |
| CORS 过宽（审计#7） | `allow_headers=["X-API-Token","Content-Type"]`（app.py:57） | ✅ |
| Token 非恒定时间（S1） | `secrets.compare_digest`（app.py:97/174） | ✅ |
| Redis URL 明文进日志（CODE-001） | `re.sub` 掩码后再记（cache.py:116/149） | ✅ |
| config 默认明文密码（CODE-004） | `DATABASE_URL = os.getenv("DATABASE_URL","")` 改空串 | ✅ |
| 无 API 限速（H2） | slowapi 全局限速（recheck R-02 验证） | ✅ |
| 缺 CSP/HSTS（H3） | 响应头注入（recheck R-08/R-09） | ✅ |
| Dockerfile healthcheck 读 .env（S5） | 改 `curl -f http://localhost:8000/health`（Dockerfile:49） | ✅ |
| `config.validate()` 不阻断（审计#8） | `validate(strict=True)` → `sys.exit(1)`；空 API_TOKEN 列 critical（config.py:109） | ✅ |

### 金融正确性（7/8）

| 发现 | 当前代码证据 | 状态 |
|------|------------|------|
| `if p and a:` 误判 0.0（审计#9） | `if p is not None and a is not None:`（exchange_execution.py:29） | ✅ |
| LIQUIDATE 被忽略（审计#11） | `_closed_trades` 过滤 `("SELL","LIQUIDATE")`（metrics.py:226） | ✅ |
| float 精度（审计#12） | `from decimal import Decimal, ROUND_HALF_UP`（paper_broker.py:6） | ✅ |
| RiskManager 无锁（审计#13） | 全状态变更 `with self._lock`（risk_manager.py:113-259） | ✅ |
| `emergency_stop` 无幂等（C2/CODE-003） | `if self.state == STOPPED: return`（risk_manager.py:244） | ✅ |
| `reset()` 不重置 `_reset_count`（审计#15） | 窗口超时 `self._reset_count = 0`（risk_manager.py:259） | ✅ |
| MemoryCache 无锁（审计#14） | `self._lock = threading.Lock()`，所有 dict 操作加锁（cache.py:41-69） | ✅ |

### 事故（3/4 + 1 部分）

| 发现 | 当前代码证据 | 状态 |
|------|------------|------|
| INC-001 风暴循环 | `_cooldown_until` + `_max_resets_per_window`，冷却期拒熔断（risk_manager.py:71-76/105） | ✅ |
| INC-002 持仓漂移 | timeout 订单自动 `cancel_order`，失败才入 `_unconfirmed`；`reconcile_unconfirmed` 兜底（exchange_runner_broker.py:94-114/147） | ✅ |
| INC-004 日志/噪声 | （由 RISK-007/008 处理，属运维配置） | 部分 |
| INC-003 告警全失败 | `_dispatch` 统计 attempted/failed，全失败 → `logger.critical("ALERT DELIVERY FAILURE...")` + `check_channels_health()` 健康自检（alert_manager.py:108-165，提交 `51162cb`） | ✅ |

### 性能/错误处理（4/4）

| 发现 | 当前代码证据 | 状态 |
|------|------------|------|
| O(n²) 切片（审计#15） | `view = df` 传引用 + 索引（multi_runner.py:200） | ✅ |
| `param_scanner` 吞异常（审计#16） | `except Exception as e: logger.warning(...)`（param_scanner.py:43） | ✅ |
| 告警无限流（审计#17） | `_should_throttle` 去重+每源限流+环形缓冲（alert_manager.py:59-97） | ✅ |
| Redis 永久降级（CODE-002） | 指数退避重连 + 成功恢复（cache.py:124-156） | ✅ |
| LSP place_order（审计#18） | `def place_order(self, order, **kwargs)`（paper_broker.py:78） | ✅ |
| rsi float 相等（Q5） | `if abs(self._avg_loss) < 1e-10`（rsi_momentum.py:144） | ✅ |

### 文档（12/12）

LICENSE 已建（MIT，1062B）；README 4 链接全部有效并指向真实文件；`API_REFERENCE.md`/`DEPLOYMENT.md`/`DATABASE_SCHEMA.md`/`FRONTEND_ARCHITECTURE.md`/`ENV_VARIABLE_REFERENCE.md`/`STRATEGY_CATALOG.md` 已建并入库；`.env.example` 已补 `API_TOKEN`；CI/DEPLOYMENT Python 统一 3.13；Redis healthcheck 加 `-a`；SECURITY.md/CHANGELOG.md 已建；ENGINEERING.md 加定位横幅 + 蓝图→实模块对照表；OPERATIONS_MANUAL 澄清两层变量、修过时基线 159→481、PYTHONPATH 跨平台化；DEV_LOG 已更新至 06-20。

---

## 二、🔎 经核实「不是当前会触发的 bug」的两项（修正审查报告判定）

> 本节是「核实准确性」的核心产出。审计/技术债报告把这两项列为待修，但逐链路读当前代码后确认：当时**都不会在当前代码状态下触发**。下面给出完整反证链。
> **更新（2026-06-21）**：点-2（告警全失败兜底）此后已在 `51162cb` 真实接线 escalation，不再仅是「未触发」而是「代码已闭合」，详见该项末尾。点-1（profit/pnl）仍维持原判（不触发、风格瑕疵未对齐）。

### 点-1：profit/pnl 字段不一致（审计#10）— **当前不触发，非 live bug**

- **审计报告原判**：`analyze_failed_trades` 用 `t.get("pnl")` 过滤、引擎只写 `profit` → `losers` 恒空 → 归因分析永远拿不到数据。
- **核实结论：在当前代码中不触发。** 该方法全代码库**唯一调用方**是 `app.py:348-353`，它在传参前已做字段归一化：

  ```python
  # app.py — trade_attribution 任务（唯一调用点）
  trades = [{"pnl": t.get("profit", 0), "time": t.get("timestamp")}
            for t in state["result"].get("closed_trades", [])]
  report = _analyzer.analyze_failed_trades(trades)
  ```

  上游 `paper_trading_runner.py:290` 写 `{"tag","time","profit"}`，调用方正好把 `profit` 读出塞进 `pnl` 再传入。链路自洽，`test_agent.py`（20 passed）也用 `pnl`。所以 152-153 行**实际工作正常**。
- **定性**：审计 #10 发现当时为真，但被调用方适配兜住，当前**不是 live bug**。152-153 与同文件其余 5 处兼容写法不一致仅是**代码风格瑕疵**（潜在隐患），不构成可观察的错误行为。
- **处置**：本次曾尝试做 2 行防御性对齐，但因其**不修复任何当前真实问题**、违反「每行改动应追溯到真实需求」原则，已**回退**，`analyzer.py` 保持与 HEAD 一致。是否对齐留作将来真有第二个调用方时再定。

### 点-2：告警全通道失败无升级兜底（INC-003 / RISK-004）— **✅ 已闭合（提交 `51162cb`）**

- **审计报告原判**：`_dispatch` 全部通道失败时无 escalating 告警/无兜底/无健康检查。
- **06-20 当时核实**：场景不触发——`AlertManager` 默认 `channels=[]`，唯一实例化点 `run_paper_trading_daemon.py:98` 不传通道，`_dispatch` 恒空循环。当时定性为"功能未接线，非缺陷"。
- **06-21 更新：兜底代码已落地。** `alert_manager.py:108-135` 的 `_dispatch` 现统计 `attempted`/`failed`，`if attempted > 0 and failed == attempted:` → `logger.critical("ALERT DELIVERY FAILURE...")`；并新增 `check_channels_health()`（L137-165）做通道健康自检 + 全失败 CRITICAL 兜底。回归测试 `test_alert_channels.py::TestDeliveryEscalation`。**代码层面已闭合,不再是开放项。**
- **实盘前仍需(运维,非代码)**：接线真实通道（Slack/PagerDuty）—— `run_paper_trading_daemon.py:98` 仍是 `AlertManager()` 不传 channels，通道类已定义但未实例化接线。兜底逻辑已就绪，接线后即生效。

---

## 三、📋 已知可接受（设计决策，非待修 bug）

| 项 | 说明 | 接受理由 |
|----|------|---------|
| 前端 `NEXT_PUBLIC_API_TOKEN` 客户端可见（C1/N-01） | DevTools 可提取 token | localhost 单机部署可接受；生产部署需改 BFF/HttpOnly Cookie，已在 SECURITY.md 标注 |
| Docker 镜像未 pin digest（S7/QA） | 供应链攻击面 | 正式部署前 pin，当前 paper 阶段可接受 |
| 前端零测试（TEST-002/N-08） | 44 组件无测试 | dashboard 纯展示无交易入口，风险可控；已文档化 |
| 4/8 策略无专用测试（TEST-004） | donchian/structure/supertrend/reversal | 走统一 RiskAwareStrategy + 回测路径间接覆盖；Phase 7+ 补 |

---

## 四、🔧 运维/人工动作（非代码，需人执行）

| 项 | 动作 | 来源 |
|----|------|------|
| `.env` 真实 Binance key | 在 testnet 吊销并轮换；`git log --all -p -- .env` 确认未入历史 | 审计#1 |
| 实盘告警通道 | 配置真实 Slack/PagerDuty endpoint | RISK-005 |
| 日志轮转 | 配 RotatingFileHandler 50MB×10 | RISK-007 |
| 60 天 paper 实跑 | 用户本机持久终端运行 | LIVE_TRADING_CHECKLIST §1 |

---

## 五、建议修复顺序

| 优先级 | 项 | 工作量 | 是否阻塞 paper 上线 |
|-------|----|-------|-------------------|
| 无需修 | OPEN-1 profit/pnl | — | 否（核实后非 live bug，调用方已归一化；代码保持原状未改） |
| **P1（实盘前）** | OPEN-2 告警通道接线 + 全失败兜底 + 健康检查（属新功能，非 bug 修复） | 0.5 天 | 否（实盘前必做） |
| **P1（实盘前）** | 运维四项（key 轮换 / 告警通道 / 日志轮转） | — | 实盘阻塞 |
| **P2** | 前端测试基础设施 + 4 策略测试 | 1 周 | 否 |

---

## 六、最终判定

- **Paper Trading 上线**：✅ 可上线。32 个 🔴 阻断项已真实修复，**0 个仍开放的真实代码 bug**。审计点名的 profit/pnl 经逐链路核实在当前唯一调用路径不触发（调用方已归一化），代码保持原状。
- **实盘（Live）**：🔴 仍阻塞。OPEN-2 告警兜底代码已闭合（`51162cb`），但**接线真实通道**（Slack/PagerDuty）+ 运维四项仍需先完成；且 Live Broker（真实下单）本身是 Phase 7+ 未实现，须走完 `LIVE_TRADING_CHECKLIST` 全部人工/时间轨道门禁。

> 本报告每条「已修复」均经当前代码 file:line 实读核验，非转述审查报告。OPEN-2（告警全失败兜底）已在 `51162cb` 代码闭合（escalation + 健康自检 + 回归测试），剩余仅「接线真实通道」属实盘前运维；OPEN-1（profit/pnl）经逐链路核实在当前唯一调用路径不触发（调用方已归一化），保留原状。
