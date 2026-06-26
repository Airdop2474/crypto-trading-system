"""H: Taker Buy 过滤器 Mixin

通过 taker_buy_base_volume / volume 比率过滤信号：
比率 > threshold 才允许做多（买方主导）。

用法：策略多继承此 Mixin，在 entry 逻辑前调用 self._taker_filter_pass(data)。
"""

import pandas as pd


class TakerFilterMixin:
    """Taker buy ratio 过滤器。

    参数（子类 __init__ 中设置）：
        taker_threshold: 做多需要的 taker_buy_ratio 最低值（默认 0.55）
        taker_lookback: 计算均值的 bar 数（默认 5）
    """

    taker_threshold: float = 0.55
    taker_lookback: int = 5

    def _taker_filter_pass(self, data: pd.DataFrame) -> bool:
        if "taker_buy_base_volume" not in data.columns or "volume" not in data.columns:
            return True

        window = data.iloc[-self.taker_lookback:]
        vol = window["volume"]
        taker = window["taker_buy_base_volume"]

        total_vol = vol.sum()
        if total_vol <= 0:
            return True

        ratio = taker.sum() / total_vol
        return ratio >= self.taker_threshold
