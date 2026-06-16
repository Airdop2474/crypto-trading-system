# Phase 6 §1 — 60 天 Paper Trading 连续运行守护进程

## 目标
把"跑一遍历史 CSV"（`run_paper_trading.py`）升级为**可连续运行 60 天的模拟盘守护
进程**：每根 bar 收盘 → 取数 → 跑策略 → PaperBroker 成交 → 落库 → 跨日出摘要；
**崩溃/重启能续跑**（状态检查点）。对应 LIVE_TRADING_CHECKLIST §1。

双模（用户已定）：
- **实时**（默认）：每根 4h bar 收盘从 Binance 拉真实 OHLCV，真连续跑 60 天。
- **回放**（`--replay`）：历史/生成数据加速跑完 60 天（几分钟），产 60 份日报，用于验证/演练。

## 关键设计

### 无前视一致性（与回测/批量逐位一致）
批量 runner 模型：bar t 出信号 → bar t+1 开盘成交。守护进程不能预知未来 bar，
故用 **pending_signal**：新 bar 到达时①先按本 bar 开盘价执行上一根的 pending 信号
②再用含本 bar 的历史算新信号存为 pending。成交价/时间与批量逐位一致。

### 复用 runner 逐 bar 逻辑（小重构）
`PaperTradingRunner` 抽出 `process_bar(bar, historical, strategy, pending_signal) -> new_signal`：
执行 pending → 算新信号 → 采集快照；`run()` 改为循环调用 `process_bar`。
**批量行为不变**，靠现有 210 测试（含 test_api 全链路 paper trading）保证不回归；
若任一测试因重构变动，回退为守护进程内独立实现（不动 runner）。

### 守护进程 `scripts/run_paper_trading_daemon.py`
- CLI：`--days 60 --symbol BTC/USDT --timeframe 4h --initial 10000`
  `--replay [csv路径|generate] --state-file ... --report-dir ... --poll-seconds 60 --fresh`
- 装配同 `run_paper_trading`：GridTradingStrategy + PaperBroker（放宽仓位上限） +
  MetricsCollector + **RiskManager** + PaperTradingRunner。
- **取数**：实时 = `ExchangeClient.fetch_ohlcv(symbol, timeframe, limit)` 轮询，
  按 timestamp 前进识别"新收盘 bar"，维护增长 history（预热若干根供指标）；
  回放 = 读 CSV 或 `generate_oscillating_ohlcv()`，逐 bar 瞬时推进。
- **每 bar 循环**：process_bar → 新增 `closed_trades` 喂 `risk_manager.record_fill`
  → 风控 PAUSE 则记事件、继续快照但停止交易（等人工恢复） → 跨日写日报 → 落库
  （best-effort，DB 不可用不致命，同 run_paper_trading） → 写检查点。
- **日报**：bar 日期翻天 → `PaperTradingReportGenerator.generate(snapshot,{symbol:close})`
  写 `data/reports/paper/daily/`，日计数 +1；满 `--days` 天停止。
- **人工恢复**（§1：暂停后需人工恢复）：循环检测 resume 标志文件
  `<state-file>.resume` 存在 → `risk_manager.resume()` 并删标志；否则保持 PAUSED。

### 状态检查点（崩溃/重启续跑）
每 bar 写 JSON：broker(balance/positions/orders)、runner(lots/realized_pnl/closed_trades)、
strategy(grid_filled/paused/consecutive_losses/daily_pnl)、risk(state/计数)、
day_count/current_day/last_bar_ts/pending_signal/history 尾部。
启动时若 state-file 存在 → 恢复全部状态，从 last_bar_ts 之后续跑（不重复成交/不丢进度）。
`--fresh` 强制忽略旧检查点重开。

## 改动清单
1. `src/execution/paper_trading_runner.py`：抽 `process_bar`，`run()` 改为调用它。
2. `scripts/run_paper_trading_daemon.py`（新）：守护进程 + 双模 + 检查点 + 风控接线 + 日报。
3. `tests/unit/test_paper_trading_daemon.py`（新）：回放模式验证。

## 成功标准（可验证，全走回放模式）
1. 回放跑 N 天（小数据）：产出 **N 份日报**、检查点文件存在、退出码 0。
2. **断点续跑**：跑一半中断 → 用同 state-file 重启 → 完成剩余天数，日报总数正确、
   账户状态连续（不重复成交）。
3. **风控暂停+人工恢复**：注入连亏触发 PAUSE → 写 resume 标志 → 恢复 ACTIVE 继续。
4. 既有基线不回归：`pytest -p no:asyncio -q` 仍全绿（重构后 ≥210 + 新用例）。
5. 实时模式：本会话**只验证启动与首 bar 处理路径**（不可能实跑 60 天）；用很短
   `--days`/mock fetch 验证实时分支不报错。

## 明确不做
- 不接真实下单（仍 PaperBroker 模拟；真实交易=Live Broker，Phase 7+）。
- 不做 Web 控制台/进程管理器（systemd/nssm 由运维侧负责，文档提一句即可）。
- 不改 §1 的人工判定（每日人工审阅、60 份摘要的人工核验仍属人工轨道）。

## 待确认
- 实时数据源用 **Binance 主网公共 OHLCV**（真实价格，无需 key），可接受？
  （testnet 行情不真实；仅模拟盘记账、不下真单，故用主网公共数据取价。）
