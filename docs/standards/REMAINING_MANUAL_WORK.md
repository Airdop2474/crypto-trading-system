# B 类剩余工作：人工 / 时间轨道清单

> **背景**：截至 2026-06-20，所有**代码层面**能做的工作已完成（Phase 1-6 门禁代码、
> Phase 7 testnet 线 Stage 0-4、本批功能扩展、A 类收尾）。基线 447 passed / 覆盖率 86%。
>
> **剩下的全是 Claude 会话无法代劳的事**——需要真实时间流逝、真机网络、或本人签字决策。
> 本文档把这些"B 类"工作集中记录，供本人在本机按节奏推进。
>
> 关联：`LIVE_TRADING_CHECKLIST.md`（门禁总清单）、`OPERATIONS_MANUAL.md`（操作手册）、
> `TROUBLESHOOTING.md`（故障排查）、`.claude/dev-log/2026-06-20.md`。

---

## 为什么这些只能人工做

- **60 天 / 3 周是真实日历时间**，没有快进。守护进程必须在持久终端真实跑满。
- **Claude 会话进程会随对话结束被杀**，无法托管长运行任务。
- **真机 testnet 验证需要网络 + testnet 凭据**，且要肉眼核对交易所端状态。
- **风险确认书、资金额度是本人决策与签字**，不是代码动作。

---

## B-1　60 天 Paper 连续运行（Phase 6 §1，最优先）

**目标**：模拟盘连续跑满 60 天无系统故障，产出 60 份每日报告，作为实盘门禁的运行证据。

**启动**（本机双击或终端运行）：
```
start_paper_60d.bat
```
实际执行：`python scripts/run_paper_trading_daemon.py --days 60 --no-db`
（BTC/USDT 4h，仅每日报告不落库，日志 Tee 到 `logs/paper_60d_<时间戳>.log`）

**运行须知**：
- **保持窗口开着，别让电脑睡眠**，否则进程死、运行中断。
- `Ctrl+C` 停止。**重跑 `.bat`（不加 `--fresh`）会从检查点续跑**——续跑与连续运行逐位
  一致（已验证）。
- 崩溃后若进入暂停态，按提示放 `.resume` 标志文件人工恢复（见 `OPERATIONS_MANUAL.md`）。

**旁路健康巡检**（另开一个终端，定期跑）：
```
python scripts/check_daemon_health.py
```
核验：检查点新鲜度、风控状态（STOPPED→需人工 reset / PAUSED→等 resume）、日报份数对账
（应 == 运行天数）+ 日期无缺口。退出码 0=无 FAIL / 1=有 FAIL。

**完成判据**（对应 checklist §1）：
- [ ] 连续运行 60 天，无系统故障
- [ ] 每日摘要报告完整（60 份，`data/reports/paper/daily/daily_*.md`）
- [ ] 所有信号和订单可追溯
- [ ] 风控触发记录完整
- [ ] 模拟盘与回测偏差可解释
- [ ] 暂停/恢复机制实跑中再核验一次

---

## B-2　系统稳定性观察（Phase 6 §3）

与 B-1 同期进行，靠 B-1 的运行期观察 + 健康巡检日志佐证。

**完成判据**（checklist §3）：
- [ ] 连续 3 周无系统故障
- [ ] 无数据缺口或异常
- [ ] 无订单执行错误
- [ ] 日志完整可查
- [ ] 监控仪表盘正常（Grafana `http://localhost:3000`，admin/admin）

---

## B-3　Phase 7 真机 testnet 验证（代码已就绪，缺真机实跑）

**目标**：验证 daemon 的 `--broker exchange` 路径在 Binance testnet 上真实下单可信。
代码（Stage 0-4）全部完成且离线测过，**唯一缺真机网络实跑**。

**前置**（`.env` 已建，已填 testnet HMAC key/secret，`BINANCE_TESTNET=true`）：
1. 确认 testnet 凭据仍有效（testnet.binance.vision 拿 key）
2. 跑冒烟连通：
   ```
   python scripts/testnet_smoke.py
   ```
   （安全护栏：非 testnet 会拒启 exit 2；查余额/下半价限价单挂着→查回→撤单，零成交风险）

**真机门禁实跑**：
```
python scripts/run_paper_trading_daemon.py --broker exchange --timeframe 1m --days 1 --min-trade-interval 30 --no-db
```
（`--min-trade-interval 30`：1m shakedown 时避免 300s 间隔挡相邻 bar）

**完成判据**（肉眼核对）：
- [ ] testnet 端订单确实存在
- [ ] 余额/持仓**按 delta** 对得上本地账本（testnet 账户有底仓如 BTC 1.0，必须按差值对账）
- [ ] 出每日报告
- [ ] 超单笔名义上限 / 日订单数被拒并计 errors
- [ ] 手动改持仓能触发漂移熔断（`risk.emergency_stop`）
- [ ] `python scripts/check_daemon_health.py` 能报卡单 / 高错误率 WARN

> **注意**：`verify_api_key_permissions.py` 在 testnet 上 exit 2 是**固有限制非 bug**
> （testnet 无 SAPI apiRestrictions 端点）；权限校验只能在主网真实账户用。

---

## B-4　实盘启动前的人工门禁（Phase 6 §收尾，签字/决策）

这些是纯人工决策，代码侧脚手架已就绪（`scripts/start_live_trading.py` 双重确认入口）。

**完成判据**（checklist §API Key / §资金 / §确认）：
- [ ] API Key 权限受限：禁提币 ❌ / 禁合约 ❌ / 禁杠杆 ❌ / 只留现货+读取
      （主网账户上 `python scripts/verify_api_key_permissions.py` 验证）
- [ ] 初始资金 ≤ **$500**（验证阶段 Month 1-3）
- [ ] 用户风险确认书已签署（checklist §用户风险确认，第 441 行起）
- [ ] 实盘双重确认：`.env` 设 `LIVE_TRADING_ENABLED=true` →
      `python scripts/start_live_trading.py` 走两次人工 YES 确认

> **诚实点**：双重确认全过后，因 **Live Broker（真实主网下单）是 Phase 7+ 尚未实现**，
> `start_live_trading.py` 会硬 `raise LiveTradingNotReady` 拒绝启动（退出码 2）。
> 门禁是真能拦的，但实盘交易动作本身还不存在——见 C 类。

---

## C 类（远期，超出当前范围，仅备注）

- **Live Broker（真实主网下单）**：Phase 7+ 后续。要等本文 B-1~B-4 全过 +
  `LIVE_TRADING_CHECKLIST` 全门禁通过才考虑动工。
- **限价网格执行 = v2**：限价单底层已就绪，但接成网格执行模式要三件一起做（`_grid_orders`
  设 limit_price + 回测引擎加限价撮合 + daemon exchange 限价模式），否则破坏 paper↔回测
  一致性。详见 `.claude/dev-log/2026-06-20.md` Task D 备忘。
- **前端低优先缺口**：启停 PATCH 为 no-op（无常驻策略进程）；price-action 策略后端不存在
  （Phase 7+ 独立研究线，不进实盘主线）。

---

## 推进顺序建议

1. **现在就起 B-1**（60 天 paper），它最耗时、是其他门禁的运行证据来源。
2. B-1 跑起来后，**穿插做 B-3**（testnet 真机验证，半天内可完成）。
3. B-1/B-2 跑满 + B-3 通过后，再处理 B-4 的签字/资金决策。
4. C 类全部等 B 类闭环后再议。
