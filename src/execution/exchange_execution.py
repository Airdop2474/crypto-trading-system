"""
执行适配层（Phase 7 Stage 1）

把"策略要买/卖多少"安全地落到交易所：精度取整 + minNotional 守卫 + 下单后确认
真实成交，并把交易所语义归一化成 runner 期望的成交结果。

边界：不接 daemon、不碰 runner（那是 Stage 2/3）；只封装 ExchangeBroker 之上的
下单确认细节，纯可单测（FakeExchange 注入，不触网）。

Stage 0 实测：币安 testnet 市价单 place_order 即返回成交价量，故市价路径同步确认、
无需轮询；轮询/超时分支为将来 v2 限价单预留。
"""

import time

from src.execution.broker import Order, OrderResult
from src.utils.logger import logger


def extract_fill(place_result, order_status=None):
    """从下单结果（+ 可选查单结果）提取真实成交价/量。纯函数。

    优先用 place_result.filled_price/filled_amount（市价单 Stage0 实测即有），
    缺失则回退 order_status 的 average/price + filled。
    返回 (price, amount, source)，source ∈ {place, status, none}。
    """
    p = getattr(place_result, "filled_price", None)
    a = getattr(place_result, "filled_amount", None)
    if p and a:
        return float(p), float(a), "place"
    if order_status:
        sp = order_status.get("average") or order_status.get("price")
        sa = order_status.get("filled")
        if sp and sa:
            return float(sp), float(sa), "status"
    return None, None, "none"


class ExchangeExecutor:
    """ExchangeBroker 之上的下单确认适配器（v1 市价单）。"""

    FULL_FILL_TOL = 0.99  # 成交量 ≥ 请求量的 99% 视作全成

    def __init__(self, broker, *, poll_seconds=1.0, timeout=30.0,
                 _clock=time.monotonic, _sleep=time.sleep):
        """
        参数：
            broker: ExchangeBroker 实例
            poll_seconds/timeout: 限价/慢成交时的轮询间隔与超时（市价单用不到）
            _clock/_sleep: 注入时钟与睡眠，便于测试超时分支不真睡
        """
        self.broker = broker
        self.exchange = broker.exchange
        self.poll_seconds = poll_seconds
        self.timeout = timeout
        self._clock = _clock
        self._sleep = _sleep

    def size_order(self, symbol, amount, ref_price):
        """精度取整 + 最小下单量/minNotional 守卫。

        返回 (amount_rounded, ok, reason)。ok=False 时不应下单。
        """
        # ccxt amount_to_precision 对低于最小精度的量会抛 InvalidOrder（实测 testnet），
        # 归一成 rejected 而非让异常冒出。
        try:
            amount_r = float(self.exchange.amount_to_precision(symbol, amount))
        except Exception as e:
            return 0.0, False, f"数量低于交易所精度：{type(e).__name__}"
        if amount_r <= 0:
            return 0.0, False, "数量取整后为 0"
        market = self.exchange.market(symbol) or {}
        limits = market.get("limits", {}) or {}
        min_amt = (limits.get("amount") or {}).get("min")
        if min_amt and amount_r < min_amt:
            return amount_r, False, f"数量 {amount_r} < 最小下单量 {min_amt}"
        min_cost = (limits.get("cost") or {}).get("min")
        notional = amount_r * ref_price
        if min_cost and notional < min_cost:
            return amount_r, False, f"名义额 {notional:.4f} < minNotional {min_cost}"
        return amount_r, True, ""

    def place_and_confirm(self, symbol, side, amount, ref_price, order_type="market"):
        """下单并确认成交。

        返回 OrderResult，status ∈ {filled, partial, timeout, rejected}：
            - rejected：sizing 不过 或 交易所拒单（无 order_id）
            - filled/partial：拿到真实成交价量，按 FULL_FILL_TOL 判全/部分
            - timeout：下单成功但 timeout 内未确认成交（调用方决定撤单/重试）
        """
        amount_r, ok, reason = self.size_order(symbol, amount, ref_price)
        if not ok:
            logger.warning(f"sizing 拒单 {symbol} {side} {amount}: {reason}")
            return OrderResult(order_id=None, status="rejected", reason=reason)

        price_arg = ref_price
        if order_type == "limit":
            price_arg = float(self.exchange.price_to_precision(symbol, ref_price))

        res = self.broker.place_order(
            Order(symbol, side, amount_r, price_arg, order_type))
        if res.order_id is None:
            return OrderResult(order_id=None, status="rejected",
                               reason=res.reason or res.status)

        price, filled, _src = self._confirm(res)
        if price is None:
            return OrderResult(order_id=res.order_id, status="timeout",
                               reason=f"{self.timeout}s 内未确认成交")
        status = "filled" if filled >= amount_r * self.FULL_FILL_TOL else "partial"
        return OrderResult(order_id=res.order_id, status=status,
                           filled_price=price, filled_amount=filled)

    def _confirm(self, place_result):
        """取成交价量：先用下单返回（市价单同步即有），缺则轮询查单到超时。

        返回 (price, amount, source)；超时返回 (None, None, "timeout")。
        """
        price, amount, src = extract_fill(place_result)
        if price is not None:
            return price, amount, src
        deadline = self._clock() + self.timeout
        while self._clock() < deadline:
            status = self.broker.get_order_status(place_result.order_id)
            price, amount, src = extract_fill(place_result, status)
            if price is not None and status and \
                    status.get("status") in ("closed", "filled"):
                return price, amount, src
            self._sleep(self.poll_seconds)
        return None, None, "timeout"


__all__ = ["ExchangeExecutor", "extract_fill"]
