"""交易所 RunnerBroker 适配层（Phase 7 Stage 3）

把 ExchangeExecutor（Stage 1：sizing + 市价单同步确认真实价量）适配成
PaperTradingRunner 期望的 RunnerBroker 协议（Stage 2 定义），让守护进程能用
`--broker exchange` 在 testnet 真实下单，而 runner 主循环代码不变。

与 PaperBroker 的根本差异：余额/持仓是交易所端真实状态（每次查询），成交价量
由交易所决定。本适配器自维护一个**本地成交账本**（ExchangeBroker 没有
get_statistics/get_trade_history），只为 report/metrics 复用现有形态。

明确放弃：exchange 模式不保证续跑逐位一致（真实成交不可复现）。

边界：不接 daemon（那是 Stage 3b）；纯靠 FakeExchange 注入可离线单测。
"""
from typing import List, Optional

import pandas as pd

from src.execution.broker import Order, OrderResult
from src.utils.logger import logger


class ExchangeUnavailable(RuntimeError):
    """交易所在构造适配器时不可达（查余额/持仓失败）。

    真实下单 broker 不能带着错误的对账基线继续运行，否则 delta 对账会失真、
    可能误触发漂移熔断。故构造期连接失败直接抛此异常，由调用方明确拒绝启动。
    """


def assess_position_drift(real_pos, initial_pos, local_net, abs_tol, rel_tol):
    """对账：交易所真实净持仓变化是否与本地账本净持仓一致。

    testnet 账户开跑前本就有底仓（如 BTC 1.0），故按 **delta** 比较：
    交易所侧增量 (real - initial) 应约等于本地 lots 净持仓 local_net。

    返回 (ok, drift)；drift = |(real-initial) - local_net|。
    ok = drift <= max(abs_tol, rel_tol*|local_net|)。
    """
    drift = abs((real_pos - initial_pos) - local_net)
    tol = max(abs_tol, rel_tol * abs(local_net))
    return drift <= tol, drift


class ExchangeRunnerBroker:
    """ExchangeExecutor → RunnerBroker 协议适配器（v1 市价单）。"""

    def __init__(self, executor, symbol: str, commission: float = 0.001,
                 guard=None):
        """
        参数：
            executor: ExchangeExecutor 实例
            symbol: 交易对（如 'BTC/USDT'）
            commission: 计入账本的手续费率（仅用于成本统计/报表）
            guard: 可选 OrderRateGuard，下单前节流（单笔上限/间隔/日订单数）
        """
        self.executor = executor
        self.broker = executor.broker  # 底层 ExchangeBroker（查单/撤单/查询）
        self.symbol = symbol
        self.commission = commission
        self.guard = guard
        self._ledger: List[dict] = []
        self._unconfirmed: List[str] = []
        self._errors = 0  # 拒单/超时累计（护栏拒、sizing 拒、未确认）
        # 阶段3 路径统一：限价单挂单队列（跨 bar 存活，与 PaperBroker.pending_orders 对齐）
        # 每条记录：{order_id, client_order_id, symbol, side, amount, limit_price,
        #            placed_at, max_pending_bars, bars_held, _tag}
        self._pending_limits: List[dict] = []
        # 挂单的 side/_tag 记录（runner._check_pending_limit_orders 通过 get_order_status 查）
        # key=order_id, value={"side":..., "_tag":..., "order_type":...}
        self._pending_order_records: dict = {}
        # 开跑基线：testnet 账户的现有现金/底仓，对账按 delta 扣掉。
        # 交易所不可达时拒绝带坏基线启动（坏基线会让 delta 对账误判、误触发漂移熔断）。
        try:
            self.initial_balance = self.get_balance()
            self.initial_position = self.get_position(symbol)
        except Exception as e:
            raise ExchangeUnavailable(
                f"初始化基线快照失败（交易所不可达），拒绝启动 {symbol}: "
                f"{type(e).__name__}: {e}"
            ) from e

    # ---- 查询（透传真实交易所状态）----

    def get_balance(self) -> float:
        return self.broker.get_balance()

    def get_position(self, symbol: str) -> float:
        return self.broker.get_position(symbol)

    @property
    def pending_orders(self) -> List[dict]:
        """挂单队列（与 PaperBroker.pending_orders 对齐，让 runner 的 hasattr 判断通过）。

        返回 _pending_limits 的引用，供 runner 检查 `if not self.broker.pending_orders`。
        """
        return self._pending_limits

    # ---- 下单（经 executor 做 sizing + 真实成交确认）----

    def place_order(self, order: Order, timestamp=None) -> OrderResult:
        """下单并确认真实成交。支持 market/limit/stop_limit 类型。

        timestamp 仅记账本（成交时刻由交易所定）。

        阶段3 路径统一：限价单（order_type=limit 且 limit_price 非 None）走
        place_limit_no_wait 只挂不确认，入 _pending_limits 队列跨 bar 存活，
        每 bar 由 check_pending_orders 查询状态——与 PaperBroker 语义对齐。
        市价单/stop_limit 继续走 place_and_confirm 同步确认。
        """
        if self.guard is not None:
            ok, reason = self.guard.check(order.amount * order.price, timestamp)
            if not ok:
                self._errors += 1
                logger.warning(f"下单护栏拒单 {order.symbol} {order.side} "
                               f"{order.amount}: {reason}")
                return OrderResult(order_id=None, status="rejected", reason=reason)

        # 阶段3：限价单走挂单队列路径（跨 bar 存活）
        if order.order_type == "limit" and order.limit_price is not None:
            return self._place_limit_order(order, timestamp)

        # 市价单 / stop_limit 走同步确认路径
        order_type = order.order_type if order.order_type in ("market", "limit") else "market"
        extra_kwargs = {}
        if order.order_type == "stop_limit" and order.stop_price is not None:
            # 交易所 stop-limit：先触发再以 limit_price 挂单
            extra_kwargs["stop_price"] = order.stop_price
            extra_kwargs["price"] = order.limit_price or order.price
            order_type = "limit"  # 交易所层用 limit + stop_price

        res = self.executor.place_and_confirm(
            order.symbol, order.side, order.amount, order.price,
            order_type=order_type, **extra_kwargs,
            client_order_id=order.client_order_id,
        )
        if res.status in ("filled", "partial"):
            self._record_fill(res, order.side, timestamp)
            if self.guard is not None:
                self.guard.record(timestamp)
            # partial 归一成 filled：携真实 filled_amount 交给 runner 记账。
            # 市价单 partial 罕见，剩余不重试，靠每 bar 对账兜底。
            return OrderResult(
                order_id=res.order_id, status="filled",
                filled_price=res.filled_price, filled_amount=res.filled_amount,
                client_order_id=res.client_order_id,
            )
        # pending_query：下单请求发出但响应丢失（网络错误），订单可能已成交。
        # 不立即重试（会重复下单），入对账队列等下一 bar 用 clientOrderId 查询。
        if res.status == "pending_query":
            if res.client_order_id:
                self._unconfirmed.append(res.client_order_id)
                logger.warning(
                    f"订单待对账（网络错误，可能已成交）"
                    f" {order.symbol} {order.side} {order.amount}: "
                    f"clientOrderId={res.client_order_id}"
                )
            else:
                # 无 client_order_id 无法对账，记错误但不入队（无法幂等查询）
                logger.error(
                    f"订单网络错误且无 client_order_id，无法对账: "
                    f"{order.symbol} {order.side} {order.amount}"
                )
            return res
        self._errors += 1
        if res.status == "timeout":
            # 下单成功但未确认成交：尝试取消订单，避免未确认订单累积导致对账漂移
            if res.order_id is not None:
                try:
                    cancelled = self.cancel_order(res.order_id)
                    if cancelled:
                        logger.warning(
                            f"timeout 订单 {res.order_id} 已取消 "
                            f"({order.symbol} {order.side} {order.amount})"
                        )
                    else:
                        # 取消失败（可能已部分成交）→ 入待确认列表，对账兜底
                        self._unconfirmed.append(res.order_id)
                        logger.warning(
                            f"timeout 订单 {res.order_id} 取消失败，待对账: "
                            f"{order.symbol} {order.side} {order.amount}"
                        )
                except Exception:
                    self._unconfirmed.append(res.order_id)
                    logger.warning(
                        f"timeout 订单 {res.order_id} 取消异常，待对账: "
                        f"{order.symbol} {order.side} {order.amount}"
                    )
            else:
                logger.warning(
                    f"下单未确认成交（无order_id）：{order.symbol} {order.side} {order.amount}"
                )
        return res  # timeout / rejected：原样返回，runner 不记账

    def _place_limit_order(self, order: Order, timestamp=None) -> OrderResult:
        """限价单挂单路径（阶段3 路径统一）。

        调 place_limit_no_wait 只挂不确认：
        - filled：交易所同步成交（罕见）→ 记账本 + 返 filled
        - pending：挂单成功 → 入 _pending_limits 队列，返 pending（runner 标 tag）
        - rejected/pending_query：原样返回
        """
        res = self.executor.place_limit_no_wait(
            order.symbol, order.side, order.amount,
            limit_price=order.limit_price, ref_price=order.price,
            client_order_id=order.client_order_id,
        )
        if res.status == "filled":
            self._record_fill(res, order.side, timestamp)
            if self.guard is not None:
                self.guard.record(timestamp)
            return res
        if res.status == "pending":
            # 入挂单队列，等 check_pending_orders 每 bar 查询
            self._pending_limits.append({
                "order_id": res.order_id,
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "side": order.side,
                "amount": order.amount,
                "limit_price": order.limit_price,
                "placed_at": timestamp,
                "max_pending_bars": 6,  # 与 PaperBroker 默认一致（6 bar × 4h = 24h）
                "bars_held": 0,
            })
            # 记录 side 供 runner._check_pending_limit_orders 查询
            self._pending_order_records[res.order_id] = {
                "side": order.side,
                "_tag": None,  # runner 在 place_order 返回 pending 后设置
                "order_type": "limit",
                "symbol": order.symbol,
                "order_id": res.order_id,
            }
            logger.info(
                f"限价单挂单 {order.symbol} {order.side} {order.amount} "
                f"@ {order.limit_price} -> {res.order_id} (pending)"
            )
            return res
        # rejected / pending_query
        if res.status == "pending_query":
            if res.client_order_id:
                self._unconfirmed.append(res.client_order_id)
        else:
            self._errors += 1
        return res

    def _record_fill(self, res: OrderResult, side: str, timestamp) -> None:
        commission_paid = res.filled_amount * res.filled_price * self.commission
        self._ledger.append({
            "order_id": res.order_id,
            "timestamp": timestamp,
            "symbol": self.symbol,
            "side": side,
            "order_type": "market",
            "amount": res.filled_amount,
            "price": res.filled_price,
            "actual_price": res.filled_price,  # 真实成交价已含滑点
            "commission": commission_paid,
            "slippage": 0.0,
            "status": "filled",
        })

    # ---- 撤单/查单（透传，重启对账用）----

    def cancel_order(self, order_id: str) -> bool:
        return self.broker.cancel_order(order_id)

    def get_order_status(self, order_id: str) -> Optional[dict]:
        """查询订单状态。优先返回挂单队列记录（含 side/_tag），否则透传交易所。

        runner._check_pending_limit_orders 用此方法取 side 和 _tag：
        - 挂单成交后，挂单记录里有 side/_tag（place_order 返 pending 时 runner 设置）
        - 透传交易所查单（成交记录）无 _tag，runner fallback 到 LEGACY_TAG
        """
        # 优先查挂单记录（含 _tag）
        rec = self._pending_order_records.get(order_id)
        if rec is not None:
            return rec
        # 回退到交易所查单（已成交订单的明细）
        return self.broker.get_order_status(order_id)

    def set_pending_order_tag(self, order_id: str, tag) -> None:
        """runner 在 place_order 返 pending 后调此方法标记 tag（与 PaperBroker 对齐）。

        runner._buy/_sell 中：order_record = broker.get_order_status(result.order_id);
        order_record["_tag"] = tag。但 exchange 模式的挂单记录是独立 dict，
        需要此方法暴露写权限（直接改 get_order_status 返回的引用）。
        """
        rec = self._pending_order_records.get(order_id)
        if rec is not None:
            rec["_tag"] = tag

    def reconcile_unconfirmed(self) -> List[str]:
        """重启对账：查每个待确认订单，已了结的清掉，仍挂单的返回（调用方拒绝静默续跑）。

        查询失败（如重启后 ExchangeBroker._order_symbols 丢失导致 fetch_order 缺
        symbol）时保守视为仍挂单——宁可拒绝续跑要求人工处理，不可静默丢失未确认订单。
        """
        still_open: List[str] = []
        for oid in list(self._unconfirmed):
            status = self.get_order_status(oid)
            if status is None:
                # 查询失败：用已知 symbol 直接重试（绕过 _order_symbols 缺失问题）
                try:
                    status = self.broker.exchange.fetch_order(oid, self.symbol)
                except Exception:
                    pass
            if status is None:
                # 仍查不到 → 保守视为仍挂单（拒绝静默续跑）
                logger.warning(f"未确认订单 {oid} 查询失败，保守视为仍挂单")
                still_open.append(oid)
            elif status.get("status") in ("open", "pending"):
                still_open.append(oid)
        self._unconfirmed = still_open
        return still_open

    def reconcile_pending(self, timestamp=None) -> None:
        """运行时对账（每 bar 调用）：查询 _unconfirmed 中的订单。

        与 reconcile_unconfirmed 的区别：本方法用于运行时（非重启），
        - 已成交 → 回填账本（_record_fill_from_status）并移出队列
        - 已撤单/已关闭 → 移出队列
        - 仍挂单/查询失败 → 保留队列，下一 bar 继续对账（不阻塞交易）

        查询用 client_order_id（幂等键），交易所按此键返回订单状态。
        """
        if not self._unconfirmed:
            return
        resolved: List[str] = []
        for cid in list(self._unconfirmed):
            status = None
            try:
                # 优先用 clientOrderId 查询（幂等）
                status = self.broker.exchange.fetch_order(cid, self.symbol)
            except Exception:
                # 回退用 order_id 查（兼容旧条目）
                oid = cid if cid.startswith("EX_") or cid.isdigit() else None
                if oid:
                    status = self.get_order_status(oid)
            if status is None:
                # 查询失败（网络仍断）→ 保留，下 bar 再试
                continue
            order_status = status.get("status")
            if order_status in ("closed", "filled"):
                # 已成交：回填账本
                self._record_fill_from_status(status, timestamp)
                resolved.append(cid)
                logger.info(
                    f"对账成功：订单 {cid} 已成交，已回填账本"
                )
            elif order_status in ("canceled", "cancelled", "expired", "rejected"):
                # 已了结（未成交）→ 移出队列
                resolved.append(cid)
                logger.info(f"对账：订单 {cid} 已 {order_status}，移出对账队列")
            # open/pending → 仍挂单，保留队列
        self._unconfirmed = [c for c in self._unconfirmed if c not in resolved]

    def check_pending_orders(self, bar_high: float, bar_low: float,
                             timestamp=None, max_pending_bars: int = 6) -> List[OrderResult]:
        """每 bar 撮合挂单队列（阶段3 路径统一，与 PaperBroker.check_pending_orders 对齐）。

        交易所侧已自动撮合，这里只需用 fetch_order 查状态：
        - 已成交 → _record_fill_from_status 回填账本 + 返 OrderResult(filled)
        - TTL 到期（bars_held >= max_pending_bars 或时间差超限）→ cancel_order + 移出
        - 仍 open → bars_held += 1，保留队列

        bar_high/bar_low 参数仅为接口兼容（exchange 模式不用，交易所自动撮合）。

        返回本 bar 成交的 OrderResult 列表（runner 据此记账）。
        """
        if not self._pending_limits:
            return []

        filled_results: List[OrderResult] = []
        remaining: List[dict] = []
        ttl_seconds = max_pending_bars * 4 * 3600  # 与 PaperBroker 一致

        for pending in self._pending_limits:
            order_id = pending["order_id"]
            cid = pending.get("client_order_id")
            side = pending["side"]
            amount = pending["amount"]
            limit_price = pending["limit_price"]

            # 查询交易所侧订单状态
            status = None
            try:
                # 优先用 client_order_id 查（幂等），回退用 order_id
                key = cid or order_id
                status = self.broker.exchange.fetch_order(key, pending["symbol"])
            except Exception as e:
                logger.warning(f"check_pending_orders 查单失败 {order_id}: {e}")
                # 查询失败：保留队列，下 bar 再试（不递增 bars_held，避免误 TTL）
                remaining.append(pending)
                continue

            order_status = status.get("status") if status else None

            # 已成交 → 回填账本 + 返 filled
            if order_status in ("closed", "filled"):
                # _record_fill_from_status 内部已调 guard.record，不重复调
                self._record_fill_from_status(status, timestamp)
                filled_amount = float(status.get("filled", 0) or 0)
                filled_price = float(status.get("average") or status.get("price") or 0)
                filled_results.append(OrderResult(
                    order_id=order_id, status="filled",
                    filled_price=filled_price, filled_amount=filled_amount,
                    client_order_id=cid,
                ))
                logger.info(
                    f"限价单成交 {pending['symbol']} {side} {filled_amount} "
                    f"@ {filled_price} (order={order_id})"
                )
                # 不放入 remaining；_pending_order_records 保留（get_order_status 查 tag）
                continue

            # 已撤单/过期/拒单 → 移出队列（不记账）
            if order_status in ("canceled", "cancelled", "expired", "rejected"):
                logger.info(f"限价单 {order_id} 已 {order_status}，移出挂单队列")
                # 清理挂单记录
                self._pending_order_records.pop(order_id, None)
                continue

            # 仍 open → 检查 TTL
            pending["bars_held"] = pending.get("bars_held", 0) + 1
            ttl_expired = pending["bars_held"] >= max_pending_bars
            # 双重判断：时间差超限也触发（与 PaperBroker 对齐）
            if not ttl_expired and timestamp is not None and pending.get("placed_at") is not None:
                try:
                    placed = pd.Timestamp(pending["placed_at"])
                    now = pd.Timestamp(timestamp)
                    if (now - placed).total_seconds() > ttl_seconds:
                        ttl_expired = True
                except (TypeError, ValueError):
                    pass  # 时间戳格式不兼容，依赖 bars_held 判断

            if ttl_expired:
                # TTL 到期 → 撤单
                try:
                    cancelled = self.cancel_order(order_id)
                    if cancelled:
                        logger.info(
                            f"限价单 TTL 到期已撤单 {order_id} "
                            f"({side} {amount} @ {limit_price})"
                        )
                    else:
                        # 撤单失败（可能已成交）→ 入 _unconfirmed 对账兜底
                        self._unconfirmed.append(cid or order_id)
                        logger.warning(
                            f"限价单 TTL 撤单失败 {order_id}，入对账队列"
                        )
                except Exception as e:
                    self._unconfirmed.append(cid or order_id)
                    logger.warning(f"限价单 TTL 撤单异常 {order_id}: {e}")
                # 清理挂单记录
                self._pending_order_records.pop(order_id, None)
                continue

            # 仍 open 且未到期 → 保留队列
            remaining.append(pending)

        self._pending_limits = remaining
        return filled_results

    def reconcile_pending_limits(self) -> List[str]:
        """重启对账：把本地 _pending_limits 与交易所侧 open 订单对齐。

        与 reconcile_unconfirmed 的区别：本方法处理限价挂单队列（非网络错误遗留）。
        - 本地有但交易所已成交/撤单 → 回填账本或清除
        - 本地有且交易所仍 open → 保留（可续跑）
        - 查询失败 → 返回该 order_id（保守拒绝静默续跑）

        返回查询失败的 order_id 列表（调用方拒绝静默续跑要求人工处理）。
        """
        if not self._pending_limits:
            return []

        unresolved: List[str] = []
        remaining: List[dict] = []
        for pending in self._pending_limits:
            order_id = pending["order_id"]
            cid = pending.get("client_order_id")
            status = None
            try:
                key = cid or order_id
                status = self.broker.exchange.fetch_order(key, pending["symbol"])
            except Exception:
                pass
            if status is None:
                logger.warning(f"重启对账：限价单 {order_id} 查询失败，保守保留")
                unresolved.append(order_id)
                remaining.append(pending)
                continue
            order_status = status.get("status")
            if order_status in ("closed", "filled"):
                # 重启期间发现已成交 → 回填账本（用 placed_at 作为成交时间近似）
                self._record_fill_from_status(status, pending.get("placed_at"))
                logger.info(f"重启对账：限价单 {order_id} 已成交，回填账本")
                self._pending_order_records.pop(order_id, None)
            elif order_status in ("canceled", "cancelled", "expired", "rejected"):
                logger.info(f"重启对账：限价单 {order_id} 已 {order_status}，清除")
                self._pending_order_records.pop(order_id, None)
            else:
                # 仍 open → 保留续跑
                remaining.append(pending)
        self._pending_limits = remaining
        return unresolved

    def _record_fill_from_status(self, status: dict, timestamp) -> None:
        """从交易所返回的订单状态回填账本（对账路径）。

        与 _record_fill 的区别：_record_fill 用 OrderResult（实时成交），
        本方法用 fetch_order 返回的 dict（对账补录）。
        """
        try:
            filled_amount = float(status.get("filled", 0) or 0)
            filled_price = float(status.get("average") or status.get("price") or 0)
            side = status.get("side", "buy")
            order_id = status.get("id")
            if filled_amount <= 0 or filled_price <= 0:
                logger.warning(f"对账回填：订单 {order_id} 成交量/价为 0，跳过")
                return
            commission_paid = filled_amount * filled_price * self.commission
            self._ledger.append({
                "order_id": order_id,
                "timestamp": timestamp,
                "symbol": self.symbol,
                "side": side,
                "order_type": status.get("type", "market"),
                "amount": filled_amount,
                "price": filled_price,
                "actual_price": filled_price,
                "commission": commission_paid,
                "slippage": 0.0,
                "status": "filled",
                "reconciled": True,  # 标记为对账补录
            })
            if self.guard is not None:
                self.guard.record(timestamp)
        except Exception as e:
            logger.error(f"对账回填账本失败 {status.get('id')}: {e}")

    # ---- 统计（本地账本 + 实时余额/持仓）----

    def get_trade_history(self) -> List[dict]:
        return list(self._ledger)

    def get_statistics(self) -> dict:
        total_commission = sum(o["commission"] for o in self._ledger)
        try:
            current_balance = self.get_balance()
            positions = {self.symbol: self.get_position(self.symbol)}
        except Exception as e:
            # testnet 闪断等瞬态错误：回退到本地账本快照，不崩溃
            logger.warning(f"get_statistics 查询失败，回退本地：{type(e).__name__}: {e}")
            current_balance = self.initial_balance
            positions = {}
        return {
            "initial_balance": self.initial_balance,
            "current_balance": current_balance,
            "total_trades": len(self._ledger),
            "total_commission": total_commission,
            "total_slippage": 0.0,  # 市价真实成交价已含滑点，不单列
            "total_cost": total_commission,
            "positions": positions,
        }

    # ---- 检查点（exchange 模式非逐位一致，仅记账本 + 基线 + 待确认 + 挂单队列）----

    def state_dict(self) -> dict:
        return {
            "ledger": list(self._ledger),
            "unconfirmed": list(self._unconfirmed),
            "errors": self._errors,
            "initial_balance": self.initial_balance,
            "initial_position": self.initial_position,
            # 阶段3：持久化限价挂单队列（丢失 = 交易所侧挂单失控）
            "pending_limits": list(self._pending_limits),
            "pending_order_records": dict(self._pending_order_records),
        }

    def load_state(self, st: dict) -> None:
        self._ledger = list(st.get("ledger", []))
        self._unconfirmed = list(st.get("unconfirmed", []))
        self._errors = st.get("errors", 0)
        self.initial_balance = st["initial_balance"]
        self.initial_position = st["initial_position"]
        # 阶段3：恢复限价挂单队列（旧 checkpoint 无此字段时为空，向后兼容）
        self._pending_limits = list(st.get("pending_limits", []))
        self._pending_order_records = dict(st.get("pending_order_records", {}))


__all__ = ["ExchangeRunnerBroker", "assess_position_drift"]
