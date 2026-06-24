"""Paper Trading 守护进程测试（回放模式，确定性）。

覆盖：N 份日报、断点续跑==连续运行（end state 一致）、人工恢复机制。
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from scripts.run_paper_trading_daemon import PaperTradingDaemon, main, parse_args


def _run(state, reports, days, extra=None):
    argv = ["--replay", "generate", "--days", str(days), "--no-db",
            "--state-file", str(state), "--report-dir", str(reports)]
    if extra:
        argv += extra
    return main(argv)


def _run_csv(state, reports, csv_path, days, extra=None):
    """用指定 CSV 回放（用于 resume 测试，确保续跑时有真正的新 bar）。"""
    argv = ["--replay", str(csv_path), "--days", str(days), "--no-db",
            "--state-file", str(state), "--report-dir", str(reports)]
    if extra:
        argv += extra
    return main(argv)


def _md_count(reports):
    return len(list(Path(reports).glob("*.md")))


def _ckpt(state):
    return json.loads(Path(state).read_text(encoding="utf-8"))


def test_replay_produces_n_daily_reports(tmp_path):
    state = tmp_path / "st.json"
    reports = tmp_path / "daily"
    rc = _run(state, reports, days=4)
    assert rc == 0
    assert _md_count(reports) == 4
    assert state.exists()
    assert _ckpt(state)["day_count"] == 4


def test_resume_equals_continuous(tmp_path):
    # 生成固定 4 天 CSV，切出前 2 天 CSV，确保续跑时有真正的新 bar
    from scripts.generate_mock_data import generate_mock_ohlcv
    from datetime import datetime, timedelta
    end = datetime(2026, 6, 24)
    start = end - timedelta(days=4)
    df_full = generate_mock_ohlcv(
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        timeframe="4h",
        initial_price=50000.0,
        market_type="oscillating",
    )
    csv_full = tmp_path / "full.csv"
    df_full.to_csv(csv_full, index=False)

    # 前 2 天 CSV（timestamp <= start+2d）
    df_half = df_full[df_full["timestamp"] <= (start + timedelta(days=2)).strftime("%Y-%m-%d")].copy()
    csv_half = tmp_path / "half.csv"
    df_half.to_csv(csv_half, index=False)

    # 连续跑到 4 天
    s_cont = tmp_path / "cont.json"
    r_cont = tmp_path / "cont_daily"
    _run_csv(s_cont, r_cont, csv_full, days=4)
    cont = _ckpt(s_cont)

    # 分两段：先 2 天，再用同 state 续到 4 天
    s_split = tmp_path / "split.json"
    r_split = tmp_path / "split_daily"
    _run_csv(s_split, r_split, csv_half, days=2)
    mid = _ckpt(s_split)
    assert mid["day_count"] == 2
    _run_csv(s_split, r_split, csv_full, days=4)  # resume
    split = _ckpt(s_split)

    # 续跑结果必须与连续运行逐位一致（证明不重复、不丢、不重启）
    assert split["day_count"] == 4
    assert _md_count(r_split) == 4
    assert split["broker"]["balance"] == pytest.approx(cont["broker"]["balance"])
    assert split["broker"]["order_id_counter"] == cont["broker"]["order_id_counter"]
    assert split["runner"]["realized_pnl"] == pytest.approx(cont["runner"]["realized_pnl"])
    assert len(split["runner"]["closed_trades"]) == len(cont["runner"]["closed_trades"])


def test_manual_resume_clears_pause(tmp_path):
    # 直接驱动恢复机制：构造守护进程，手动置暂停 + 放 resume 标志
    args = parse_args(["--replay", "generate", "--state-file",
                       str(tmp_path / "st.json"), "--report-dir", str(tmp_path / "d")])
    d = PaperTradingDaemon(args)
    d._build(40000.0, 60000.0)  # 装配 strategy/risk

    d.risk.emergency_stop("test")  # STOPPED 也算需恢复
    d.risk.state = "PAUSED"
    d.strategy.paused = True
    d.resume_flag.write_text("go", encoding="utf-8")

    d._check_resume()

    assert d.risk.can_trade()         # 风控回到 ACTIVE
    assert d.strategy.paused is False  # 策略级熔断也解除
    assert not d.resume_flag.exists()  # 标志已消费


def test_fresh_ignores_old_checkpoint(tmp_path):
    state = tmp_path / "st.json"
    reports = tmp_path / "daily"
    _run(state, reports, days=3)
    assert _ckpt(state)["day_count"] == 3
    # --fresh 应忽略旧检查点，从头重跑到 2 天（day_count 回到 2 而非 5）
    _run(state, reports, days=2, extra=["--fresh"])
    assert _ckpt(state)["day_count"] == 2


def _live_seed(n_days):
    """生成 n_days×6 根 4h bar（含跨多日），供 live 冷启动种子测试。"""
    import numpy as np
    periods = n_days * 6
    times = pd.date_range("2026-01-01", periods=periods, freq="4h")
    closes = 100 + 5 * np.sin(np.arange(periods) / 3.0)
    return pd.DataFrame({
        "timestamp": times, "open": closes,
        "high": closes + 1, "low": closes - 1,
        "close": closes, "volume": [100.0] * periods,
    })


def test_live_cold_start_seed_is_warmup_only(tmp_path):
    """live 冷启动：种子（多日历史）只用于定区间，不回填交易/日报/day_count。"""
    args = parse_args(["--days", "60", "--no-db",
                       "--state-file", str(tmp_path / "st.json"),
                       "--report-dir", str(tmp_path / "d")])
    d = PaperTradingDaemon(args)
    seed = _live_seed(n_days=10)  # 60 根、跨 10 天历史

    d._seed_live_warmup(seed)
    # 种子末根成为「已见」基线
    assert d.last_bar_ts == str(seed.iloc[-1]["timestamp"])
    # 初次消费同一份种子 → 全部 <= last，零回填
    d._consume_new_bars()
    assert d.day_count == 0
    assert _md_count(tmp_path / "d") == 0
    assert d.runner.lots == {}


def test_live_new_bar_after_seed_is_processed(tmp_path):
    """启动后真实到达的新 bar 会被处理（day_count 只随真实新 bar 推进）。"""
    args = parse_args(["--days", "60", "--no-db",
                       "--state-file", str(tmp_path / "st.json"),
                       "--report-dir", str(tmp_path / "d")])
    d = PaperTradingDaemon(args)
    seed = _live_seed(n_days=10)
    d._seed_live_warmup(seed)

    # 追加一根种子之后的新 bar，重新喂入 → 只处理这一根
    new_ts = seed.iloc[-1]["timestamp"] + pd.Timedelta(hours=4)
    new_row = {"timestamp": new_ts, "open": 103.0, "high": 104.0,
               "low": 102.0, "close": 103.0, "volume": 100.0}
    d._history = pd.concat([seed, pd.DataFrame([new_row])], ignore_index=True)
    d._consume_new_bars()
    assert d.last_bar_ts == str(new_ts)  # 推进到新 bar


# ---- bar 校验测试 ----

class TestBarValidation:
    """_validate_bar 静态方法测试"""

    _validate = staticmethod(PaperTradingDaemon._validate_bar)

    def _bar(self, **kw):
        base = {"open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}
        base.update(kw)
        return base

    def test_valid_bar(self):
        assert self._validate(self._bar()) is True

    def test_missing_field(self):
        bar = {"open": 100, "high": 110}  # missing low, close
        assert self._validate(bar) is False

    def test_price_zero(self):
        assert self._validate(self._bar(close=0)) is False

    def test_price_negative(self):
        assert self._validate(self._bar(low=-5)) is False

    def test_high_below_low(self):
        assert self._validate(self._bar(high=80, low=90)) is False

    def test_open_outside_range(self):
        assert self._validate(self._bar(open=120)) is False  # open > high

    def test_close_outside_range(self):
        assert self._validate(self._bar(close=85)) is False  # close < low

    def test_negative_volume(self):
        assert self._validate(self._bar(volume=-1)) is False

    def test_zero_volume_ok(self):
        assert self._validate(self._bar(volume=0)) is True
