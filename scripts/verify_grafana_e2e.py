"""Phase 5 Grafana 端到端验证脚本（临时）。

走真实生产路径：MetricsCollector.snapshot() -> to_records() -> MetricsWriter -> DB。
生成过去 1 小时的若干时序点，供 Grafana 面板渲染验证。

运行前需设 TIMESCALE_PASSWORD=changeme（对齐 docker-compose 默认）。
"""

from datetime import datetime, timedelta, timezone

from src.monitor.metrics_collector import MetricsCollector
from src.monitor.metrics_writer import MetricsWriter
from src.utils.database import db


def build_runner_result(total_value: float, trades: int, realized: float) -> dict:
    """构造一个最小 runner_result，使 total_value 等于给定值（持仓为空、全现金）。"""
    initial = 10000.0
    return {
        "statistics": {
            "initial_balance": initial,
            "current_balance": total_value,
            "positions": {},
            "total_trades": trades,
            "total_cost": trades * 1.5,
        },
        "realized_pnl": realized,
        "open_lots": {},
    }


def main() -> None:
    collector = MetricsCollector()
    now = datetime.now(timezone.utc)

    # 12 个点，每 5 分钟一个，账户价值缓慢上行
    for i in range(12):
        ts = now - timedelta(minutes=5 * (11 - i))
        value = 10000.0 + i * 35.0          # 10000 -> 10385
        trades = i                           # 累计成交
        realized = i * 4.0
        rr = build_runner_result(value, trades, realized)
        collector.snapshot(rr, current_prices={}, risk_manager=None, timestamp=ts)

    records = collector.to_records()
    # risk_state 默认 N/A（无 RiskManager），给前几条标几个状态便于看分类
    for r in records[:3]:
        r["risk_state"] = "NORMAL"
    records[-1]["risk_state"] = "NORMAL"

    writer = MetricsWriter(db=db)
    n = writer.write_records(records)
    print(f"wrote {n} records")

    # 回读确认
    rows = db.execute_query(
        "SELECT count(*), min(timestamp), max(timestamp), max(total_value) "
        "FROM monitor_metrics"
    )
    print("db check:", rows)
    db.close()


if __name__ == "__main__":
    main()
