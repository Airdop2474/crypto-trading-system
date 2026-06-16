# Phase 6 — ExchangeBroker（交易所接口适配层）

## 背景与范围界定

Phase 6 在路线图里是"小资金实盘(90天+)"，但它**绝大部分是人/流程轨道**，不是写代码：
- 60 天 paper trading 跑通、连续 3 周无故障
- 签署风险确认书、初始资金 ≤ $500、人工双重确认开关
- 90 天验收（无严重风控事故 + 回撤可控）

这些由 `LIVE_TRADING_CHECKLIST.md` 门禁管控，**不是本次能"写"出来的**。

**本次代码交付物 = `ExchangeBroker`**，三层 Broker 架构的中间层。依据：
- `BROKER_ARCHITECTURE.md` §3 明确把 `ExchangeBroker` 标为 **Phase 5-6**，且"只用于查询和测试，不执行真实交易"。
- `src/execution/broker.py:36` 已定义 `BrokerInterface` 抽象接口，`__init__.py` 已宣称"三层架构"，但目前只有 Paper 层。
- `LiveBroker`（真实下单 + 额外风控）是 **Phase 7+**，本次**不做**。

> 一句话：本次把 Paper→**Exchange**→Live 链条的缺失中间层补上，testnet/只读模式，为 Phase 7 实盘留好接口。不碰真实资金路径。

## 成功标准（可验证）

1. `ExchangeBroker(BrokerInterface)` 实现全部 5 个抽象方法，`from src.execution import ExchangeBroker` 可导入。
2. 单元测试全部通过、**不触网**（用 mock 的 ccxt exchange 对象注入），覆盖：余额、持仓、下单成功/资金不足/网络错误、撤单成功失败、查单存在/不存在。
3. 默认 `testnet=True`；在 `LIVE_TRADING_ENABLED != 'true'` 时，`place_order` 走 testnet 不可能误下主网真单（构造期强约束 + 守卫）。
4. 既有基线不回归：`python -m pytest -p no:asyncio -q` 仍全绿（当前 146 passed → 新增后 ≥146 + 新用例）。

## 改动清单（surgical）

1. **新增 `src/execution/exchange_broker.py`**
   - 类 `ExchangeBroker(BrokerInterface)`，构造签名对齐架构文档：
     `__init__(self, exchange_id="binance", api_key=None, secret=None, testnet=True, exchange=None)`
     - `exchange` 形参用于**依赖注入**（测试传 mock；生产留 None 时内部用 ccxt 构造）。这是对架构文档草稿唯一的实质性增强，目的就是可测、不触网。
   - 5 个方法按架构文档 §3 实现，并做硬化：
     - `get_balance` → `fetch_balance()['USDT']['free']`，缺键安全返回 0.0
     - `get_position(symbol)` → base 币种 free，缺键返回 0.0
     - `place_order` → `create_order(...)`，捕获 `ccxt.InsufficientFunds` / `ccxt.NetworkError` / 通用异常，分别返回 `rejected` / `error` 状态的 `OrderResult`（复用 broker.py 的 OrderResult）
     - `cancel_order` / `get_order_status` → try/except 包裹，失败返回 False / None
   - **不实现** `get_total_value`、交易历史等 Paper 专有便利方法（YAGNI；接口没要求）。
   - 日志风格沿用 `from src.utils.logger import logger`。

2. **改 `src/execution/__init__.py`**：导出 `ExchangeBroker`（加 import + `__all__`）。仅加两行。

3. **新增 `tests/unit/test_exchange_broker.py`**
   - 沿用 `test_paper_broker.py` 的头部样板（sys.path 插入、plain pytest 类）。
   - 用一个轻量 `FakeExchange`（普通类，按需抛 `ccxt.InsufficientFunds` 等）注入构造器，**完全离线**。
   - 用例对齐成功标准第 2 条。

## 明确不做（避免范围蔓延）

- ❌ `LiveBroker`（Phase 7+，真实资金）
- ❌ 真正连 Binance testnet 的集成测试（不稳定、触网；如需，后续单独加 `tests/integration` 并标 `@pytest.mark.skipif` 无 key 跳过）
- ❌ 把 `PaperTradingRunner` 改成可切换 broker（架构文档说"逐步替换"，但 runner 改造不在 ExchangeBroker 交付范围；留作后续）
- ❌ 任何门禁/流程文档的勾选（那是人工轨道）

## 验证步骤

1. `python -m pytest -p no:asyncio tests/unit/test_exchange_broker.py -q` → 新用例全绿
2. `python -m pytest -p no:asyncio -q` → 总基线不回归
3. `python -c "from src.execution import ExchangeBroker; print('ok')"` → 导入通过

## 待确认（计划批准时一并定）

- 这次范围是否就锁定在 **ExchangeBroker 适配层**？还是你想把 Phase 6 理解成别的东西（例如：先补 Phase 6 的操作手册/故障排查手册等门禁文档）？
