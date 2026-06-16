# Phase 7 — 守护进程接 testnet（真实执行）

> 状态：**Stage 0-4 代码全部完成（2026-06-17，提交 `2d22db9`/`37eec03`/`3cdca6a`/`283fc80`/`e7f2e75`/`4e5ac52`/`1ef1132`，已推送，基线 313 passed）**。
> **唯一剩余=真机 testnet 验证（人工，见文末成功标准）**——本会话环境无网未跑。
> 前置已就绪：ExchangeBroker（testnet 实测打通，查余额/下单/查回/撤单全 PASS，提交 `7b506a3`）、
> `testnet_smoke.py`、`.env` 已配 testnet key。

## 背景与范围

把 `run_paper_trading_daemon.py` 从 **PaperBroker 模拟**升级为可选 **ExchangeBroker(testnet) 真实下单**。
这是 Phase 7 的第一步（testnet 真实执行）；真金白银的 Live 仍在 LIVE_TRADING_CHECKLIST 门禁之后，**本规划不碰主网**。

### 核心矛盾（为什么是重写不是接线）

`PaperTradingRunner` 深度耦合 PaperBroker 的「即时成交 + 本地记账」模型，ExchangeBroker 是「异步成交 + 状态在交易所」：

| 维度 | PaperBroker | ExchangeBroker(testnet) |
|---|---|---|
| 成交 | 即时、已知价，`status=="filled"` | 异步，`open`/部分成交/被过滤器拒 |
| 价/量 | 调用方给定 | 交易所决定（真实成交价量） |
| 账务 | 本地 lots + 本地手续费/滑点 | 余额/持仓在交易所端，真实手续费 |
| 检查点 | 序列化 broker.balance/positions/orders | broker 无本地状态，须从交易所对账 |
| 续跑 | **逐位一致**（确定性） | **做不到**（真实成交非确定） |

runner 硬耦合点（`src/execution/paper_trading_runner.py`）：
- `place_order(BrokerOrder(...), timestamp=time)` —— ExchangeBroker 无 `timestamp` 参
- 判 `result.status != "filled"` —— 交易所返 `open`/`closed`
- 读 `broker.commission` / `broker.slippage` / `broker.initial_balance` / `broker.get_statistics()` / `broker.get_trade_history()` —— ExchangeBroker 全无
- 守护进程检查点序列化 `broker.balance/positions/orders/order_id_counter` —— ExchangeBroker 全无

## 已定决策（用户 2026-06-17 拍板）

1. **v1 用市价单**：近即时，简化 fill 确认。代价吃 taker 费 + 滑点。限价网格留 v2。
2. **完整重构**（非 shim）：runner 解耦出窄 broker 协议，账务内移；不给 ExchangeBroker 硬塞假 commission/get_statistics。干净但风险高 → 靠 paper 全测试不回归兜底，小步改。
3. **明确放弃**：testnet 模式**不保证续跑逐位一致**（真实成交不可复现）。写进文档与检查点注释，不假装成立。
4. **账务归属**：runner 继续维护 tag→lots（网格需分档；交易所只知净持仓），但成交价/量来自**真实订单结果**；每 bar 用 `get_position` 与本地净持仓对账，漂移超阈值→熔断。

## 分阶段实施（每阶段独立验证，paper 路径全程不破）

### Stage 0 — spike & 定调（不动 daemon）✅ 完成（2026-06-17）
- 扩 `testnet_smoke.py`：`--market-spike` 跑极小市价买 + 卖回，纯函数 `extract_fill`
  （优先 place 结果、回退查单）抽出成交价量。+4 单测。
- **实测结论**：币安 testnet **市价单在 place_order 返回里直接带成交价量**（来源=`place`）。
  买 0.0003 BTC@65849 / 卖回@65849.4，持仓平复。
- **对 Stage 1 的影响**：市价单**无需轮询循环**——下单即拿到真实成交。`place_and_confirm`
  对市价单可同步返回；轮询/超时逻辑只在将来 v2 限价单才需要。
- 验证：testnet 实跑全 PASS；基线 261→265 passed。

### Stage 1 — 执行适配层（可单测，不接 daemon）✅ 完成（2026-06-17，提交见下）
- 新增 `src/execution/exchange_execution.py`：
  - `ExchangeExecutor.size_order`：`amount_to_precision` + 最小下单量/`minNotional` 守卫
    （从 ccxt market limits 读）。**实测硬化**：`amount_to_precision` 对低于精度的极小量
    会抛 `ccxt.InvalidOrder`，已 try/except 归一成 rejected 不冒泡。
  - `place_and_confirm(symbol, side, amount, ref_price, order_type)`：size→下单→确认，
    返回归一化 `filled`/`partial`/`timeout`/`rejected` + 真实价量。市价单走同步取价
    （Stage0 结论），轮询/超时分支为 v2 限价单预留（注入 `_clock`/`_sleep` 便于测试不真睡）。
  - `extract_fill` 从 scripts 移到 src（修正依赖方向，scripts 复用）。
- 验证：`tests/unit/test_exchange_execution.py` 13 用例（sizing 4 + place_and_confirm 5
  含 timeout/partial/拒单 + extract_fill 3 + 精度异常回归）。**真机复验**：testnet 市价
  买/卖回均 filled、极小量优雅 rejected。基线 265→**278**。

### Stage 2 — broker 无关 runner（**最高风险**）✅ 完成（2026-06-17，提交 `3cdca6a`）
- **方案：只搬 config（用户拍板，非完整 ledger 内移）**。新增 `ExecutionConfig`（frozen：
  commission/slippage/initial_balance）+ `from_broker()` 快照 + `RunnerBroker`（`typing.Protocol`：
  get_balance/get_position/place_order(...,timestamp=)/get_statistics/get_trade_history，
  **刻意不继承 BrokerInterface，故 ExchangeBroker 不受影响**）。
- runner sizing/profit 改读 `self.exec_cfg`，主循环不再读 broker 内部经济参数；新增可选
  `exec_config=` 注入口（默认 from_broker，故所有现有调用点不变）。get_statistics/
  get_trade_history 暂仍走 broker 协议（完整账本内移留待将来）。
- 验证：paper 路径 **bit-for-bit 不变（278）**，+2 测试→280。daemon 检查点仍直接序列化
  PaperBroker.balance/positions/orders（paper 专属，Stage 3 才分支）。

### Stage 3 — daemon testnet 模式 ✅ 完成（offline 部分；提交 `283fc80` 3a + `e7f2e75` 3b）
- 3a `src/execution/exchange_runner_broker.py`：`ExchangeRunnerBroker` 把 `ExchangeExecutor`
  适配成 RunnerBroker 协议。place_order 经 place_and_confirm：filled/partial→记本地账本并
  **归一为 filled**（携真实 filled_amount，partial 剩余不重试靠对账兜底）、timeout→记
  `_unconfirmed`、rejected→原样返回。get_balance/get_position 透传真实交易所；statistics/
  history 走本地账本。构造时快照 `initial_balance/initial_position`（**testnet 有底仓，对账按
  delta**）。纯函数 `assess_position_drift`。+11 离线测（FakeExchange）。
- 3b daemon `--broker {paper,exchange}`（默认 paper）+ `--drift-abs/--drift-rel`；`_build` 分流、
  `_make_exchange_broker()` 注入缝；**硬护栏强制 `BINANCE_TESTNET=true`+配 key 否则拒启**；
  每 bar `_reconcile_drift`→超阈值 `risk.emergency_stop`；检查点按模式分支（exchange 存
  `adapter.state_dict()`，**paper 段逐字不变**，`test_resume_equals_continuous` 仍绿证明）；
  重启对 `_unconfirmed` 查交易所，仍挂单→`SystemExit` 拒绝静默续跑。+8 离线测。基线 **299**。
- **真机 testnet 验证=人工**（见文末「剩余」），本会话环境无网未跑。

### Stage 4 — 安全与运维 ✅ 完成（offline 部分；提交 `4e5ac52` 4a + `1ef1132` 4b）
- 硬护栏「强制 testnet」已在 3b 完成。4a 新增 `src/execution/order_guard.py` `OrderRateGuard`：
  单笔名义额上限/最小间隔/日订单数（RISK_CONTROLS：0.20/300s/10）。**间隔按 bar ts（下单
  决策周期）判**——同一 bar 多笔 grid lot 视作一次决策全放行（用户拍板）；单笔上限+日订单数
  逐单。接进 ExchangeRunnerBroker（可选 `guard=`）+ `_errors` 计数，state_dict 增 errors。
  daemon 加 `--max-position-per-trade/--min-trade-interval/--max-trades-per-day`。
- 4b 健康巡检 `check_daemon_health.py` `assess_health` 扩 exchange 核验（靠 broker 含
  `unconfirmed` 键区分，paper 形态跳过、向后兼容）：卡单（unconfirmed 非空→WARN）、下单
  错误率（errors/(errors+fills) 超 `--max-order-error-rate` 默认 0.2→WARN）。持仓漂移已由
  daemon 实时熔断→风控状态 FAIL 覆盖，离线不重复判。
- +14 测试。基线 **313 passed**。testnet 短程 shakedown=人工（见文末「剩余」）。

### 不在本规划内
- 限价网格执行（v2）。
- 真实主网/Live Broker（Phase 7+ 后续 + LIVE_TRADING_CHECKLIST 全门禁）。

## 主要风险
- **Stage 2 回归**：动 runner 可能破坏 paper 逐位一致 → 全测试兜底 + 小步。
- **部分成交/卡单**：市价单通常全成，但须处理 timeout/partial，否则账务漂移。
- **过滤器拒单**：minNotional/LOT_SIZE/PERCENT_PRICE，sizing 层先过滤。
- **限频**：下单 + 轮询放大请求量，enableRateLimit 已开但需留意。
- **ExchangeBroker 现状**：place_order 用市价时 price 传 None 已支持；查单/撤单 symbol 已修（`7b506a3`）。

## 成功标准（整体）
1. ⏳ **人工待验**：`python scripts/run_paper_trading_daemon.py --broker exchange --timeframe 1m --days 1 --min-trade-interval 30 --no-db` 能在 testnet 真实下单、成交、对账、出日报；核对 ① testnet 端订单存在 ② 余额/持仓按 delta 对得上账本 ③ 超单笔上限/日订单数被拒并计 errors ④ 制造漂移触发熔断 ⑤ `python scripts/check_daemon_health.py` 卡单/高错误率 WARN。
2. ✅ paper 路径零回归：全测试 313 + `test_resume_equals_continuous` 逐位一致全绿。
3. ✅ 崩溃重启从交易所对账续跑（`_unconfirmed` 仍挂单→拒绝静默续跑）；检查点注释写明 exchange 非逐位一致。
4. ✅ 安全护栏：非 testnet 拒启（3b）；订单级风控参数（单笔/间隔/日订单数）生效（4a）。
