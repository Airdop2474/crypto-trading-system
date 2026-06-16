"""监控指标写库（Phase 5）。

把 MetricsCollector 的展平时序写入 monitor_metrics 表，供 Grafana 读取。
打通"内存指标 → DB"链路。

设计要点：
- 用参数化 SQL（%s 占位），列名为静态常量、非用户输入，无注入风险。
- 依赖 DatabaseManager.execute_many；DB 可注入，便于单测（不连真实库）。
"""

from typing import List, Optional

from src.monitor.metrics_collector import MetricsCollector
from src.utils.database import db as default_db
from src.utils.logger import logger


class MetricsWriter:
    """把指标记录写入 monitor_metrics 表。"""

    TABLE = "monitor_metrics"
    COLUMNS = [
        "timestamp",
        "total_value",
        "total_return",
        "realized_pnl",
        "total_trades",
        "risk_state",
        "consecutive_losses",
    ]

    def __init__(self, db=None):
        """
        参数：
            db: DatabaseManager（默认用全局实例）。可注入便于测试。
        """
        self.db = db if db is not None else default_db

    def _insert_query(self) -> str:
        cols = ", ".join(self.COLUMNS)
        placeholders = ", ".join(["%s"] * len(self.COLUMNS))
        return f"INSERT INTO {self.TABLE} ({cols}) VALUES ({placeholders})"

    def write_records(self, records: List[dict]) -> int:
        """
        写入一批展平记录（MetricsCollector.to_records() 格式）。

        返回：写入条数。空输入返回 0、不触库。
        """
        if not records:
            return 0

        data = [tuple(r.get(c) for c in self.COLUMNS) for r in records]
        self.db.execute_many(self._insert_query(), data)
        logger.info(f"Wrote {len(data)} metric records to {self.TABLE}")
        return len(data)

    def write_collector(self, collector: MetricsCollector) -> int:
        """直接写入采集器累积的全部快照。"""
        return self.write_records(collector.to_records())


__all__ = ["MetricsWriter"]
