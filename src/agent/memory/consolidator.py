"""
记忆维护器 — 定时衰减、去重、清理

由后台定时任务调用（如每日一次），防止记忆库无限膨胀。
"""

from datetime import datetime, timezone
from typing import List

from loguru import logger

from src.agent.memory.schemas import MemoryKind, SearchQuery, SearchResult
from src.agent.memory.store import get_memory_store


class MemoryConsolidator:
    """记忆库维护。"""

    def __init__(self, decay_rate: float = 0.95, prune_threshold: float = 0.1, merge_threshold: float = 0.95):
        self._store = get_memory_store()
        self.decay_rate = decay_rate
        self.prune_threshold = prune_threshold
        self.merge_threshold = merge_threshold

    def run_once(self) -> dict:
        """执行一轮维护，返回统计。

        维护内容：
        1. 衰减：所有记忆 score *= decay_rate（旧记忆自然降权）
        2. 修剪：删除 score < prune_threshold 的记忆
        3. 去重：content 完全相同的合并（保留最新）
        """
        stats = {"decayed": 0, "pruned": 0, "deduped": 0}

        # 从 DB 获取所有记忆（JSON 回退不维护）
        from src.utils.database import db
        if not db.is_postgres_available():
            logger.info("MemoryConsolidator: DB 不可用，跳过维护")
            return stats

        try:
            with db.get_session() as session:
                # 1. 衰减（对旧记忆降权）
                session.execute(db.text("""
                    UPDATE agent_memories
                    SET score = score * :rate,
                        updated_at = NOW()
                    WHERE created_at < :cutoff AND score > :min_score
                """), {
                    "rate": self.decay_rate,
                    "cutoff": datetime.now(timezone.utc),
                    "min_score": self.prune_threshold,
                })
                stats["decayed"] = session.rowcount if hasattr(session, 'rowcount') else 0

                # 2. 清理低分噪声
                result = session.execute(db.text("""
                    DELETE FROM agent_memories
                    WHERE score < :threshold
                """), {"threshold": self.prune_threshold})
                stats["pruned"] = result.rowcount

                # 3. 去重（content 完全相同的保留最早的）
                result = session.execute(db.text("""
                    DELETE FROM agent_memories a USING agent_memories b
                    WHERE a.id < b.id
                      AND a.content::text = b.content::text
                      AND a.kind = b.kind
                """))
                stats["deduped"] = result.rowcount

                session.commit()
        except Exception as e:
            logger.warning(f"MemoryConsolidator 维护失败: {type(e).__name__}: {e}")

        if any(v > 0 for v in stats.values()):
            logger.info(f"MemoryConsolidator: {stats}")
        return stats