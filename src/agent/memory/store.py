"""
MemoryStore — 长期记忆存储核心

两层存储：
1. PostgreSQL + pgvector（主存储）：支持语义搜索
2. JSON 文件（回退）：DB 不可用时降级运行

所有公共方法线程安全。
"""

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.agent.memory.schemas import (
    MAX_FEEDBACK_SCORE,
    MAX_SEARCH_LIMIT,
    MIN_FEEDBACK_SCORE,
    DEFAULT_SEARCH_LIMIT,
    FeedbackRecord,
    MemoryEntry,
    MemoryKind,
    SearchQuery,
    SearchResult,
)
from src.agent.memory.vector import get_embedder
from src.utils.database import db

# JSON 回退文件路径
MEMORY_FILE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "memory" / "memories.json"


class MemoryStore:
    """长期记忆存储。"""

    def __init__(self, use_json_fallback: bool = True):
        self._lock = threading.Lock()
        self._embedder = get_embedder()
        self._use_json = use_json_fallback
        if use_json_fallback:
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------

    def store(
        self,
        kind: MemoryKind,
        content: Dict[str, Any],
        tags: Optional[List[str]] = None,
        source: str = "",
    ) -> str:
        """写入一条记忆，自动生成 embedding。

        返回记忆 ID。
        """
        entry = MemoryEntry(
            kind=kind,
            content=content,
            tags=tags or [],
            source=source,
        )

        # 生成 embedding（静默失败 = 空向量，不影响主流程）
        embedding = self._embedder.generate(content)

        # 写入 DB
        if db.is_postgres_available():
            try:
                return self._store_db(entry, embedding)
            except Exception as e:
                logger.warning(f"记忆 DB 写入失败，回退 JSON: {type(e).__name__}: {e}")

        # JSON 回退
        if self._use_json:
            return self._store_json(entry)
        return entry.memory_id

    def feedback(self, memory_id: str, score: int, note: str = "") -> bool:
        """记录人类对某条记忆的反馈评分（1-5）。"""
        score = max(MIN_FEEDBACK_SCORE, min(MAX_FEEDBACK_SCORE, score))
        fb = FeedbackRecord(memory_id=memory_id, score=score, note=note)

        if db.is_postgres_available():
            try:
                return self._feedback_db(fb)
            except Exception as e:
                logger.warning(f"反馈 DB 写入失败，回退 JSON: {type(e).__name__}: {e}")

        return self._feedback_json(fb)

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------

    def search(self, query: SearchQuery) -> List[SearchResult]:
        """语义搜索记忆。

        支持：语义相似度 + 类型过滤 + 标签过滤 + 最低分数。
        """
        if db.is_postgres_available():
            try:
                return self._search_db(query)
            except Exception as e:
                logger.warning(f"记忆 DB 查询失败，回退 JSON: {type(e).__name__}: {e}")

        return self._search_json(query)

    def get(
        self,
        kind: Optional[MemoryKind] = None,
        tags: Optional[List[str]] = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> List[MemoryEntry]:
        """按类型/标签获取最近的记忆（无语义搜索）。"""
        q = SearchQuery(kind=kind, tags=tags, limit=min(limit, MAX_SEARCH_LIMIT))
        results = self.search(q)
        return [r.entry for r in results]

    def delete(self, memory_id: str) -> bool:
        """删除一条记忆。"""
        if db.is_postgres_available():
            try:
                return self._delete_db(memory_id)
            except Exception as e:
                logger.warning(f"记忆 DB 删除失败: {type(e).__name__}: {e}")
        return self._delete_json(memory_id)

    # ------------------------------------------------------------------
    # DB 实现
    # ------------------------------------------------------------------

    def _store_db(self, entry: MemoryEntry, embedding: List[float]) -> str:
        embedding_json = json.dumps(embedding) if embedding else "[]"
        tags_sql = "{" + ",".join(entry.tags) + "}" if entry.tags else "{}"

        with db.get_session() as session:
            session.execute(
                db.text("""
                    INSERT INTO agent_memories (id, kind, content, embedding, tags, score, source, created_at)
                    VALUES (:id, :kind, :content, :embedding::vector, :tags, :score, :source, :created_at)
                """),
                {
                    "id": entry.memory_id,
                    "kind": entry.kind.value,
                    "content": json.dumps(entry.content, ensure_ascii=False, default=str),
                    "embedding": embedding_json,
                    "tags": tags_sql,
                    "score": entry.score,
                    "source": entry.source,
                    "created_at": entry.created_at,
                },
            )
            session.commit()
        return entry.memory_id

    def _search_db(self, query: SearchQuery) -> List[SearchResult]:
        has_embedding = self._embedder.available and query.query
        embedding = self._embedder.generate({"query": query.query}) if has_embedding else []

        with db.get_session() as session:
            # 有 embedding → 语义搜索 + 标签过滤
            if has_embedding and embedding:
                emb_json = json.dumps(embedding)
                conditions = ["1=1"]
                params: Dict[str, Any] = {
                    "limit": min(query.limit, MAX_SEARCH_LIMIT),
                    "embedding": emb_json,
                }
                if query.kind:
                    conditions.append("kind = :kind")
                    params["kind"] = query.kind.value
                if query.tags:
                    conditions.append("tags && :tags")
                    params["tags"] = "{" + ",".join(query.tags) + "}"

                where = " AND ".join(conditions)
                rows = session.execute(
                    db.text(f"""
                        SELECT id, kind, content, tags, score, source, feedback_count,
                               feedback_avg_score, created_at,
                               1 - (embedding <=> :embedding::vector) AS sim
                        FROM agent_memories
                        WHERE {where} AND score >= :min_score
                        ORDER BY sim DESC
                        LIMIT :limit
                    """),
                    {**params, "min_score": query.min_score},
                ).fetchall()
            else:
                # 无 embedding → 按时间倒序 + 标签过滤
                conditions = ["score >= :min_score"]
                params: Dict[str, Any] = {
                    "limit": min(query.limit, MAX_SEARCH_LIMIT),
                    "min_score": query.min_score,
                }
                if query.kind:
                    conditions.append("kind = :kind")
                    params["kind"] = query.kind.value
                if query.tags:
                    conditions.append("tags && :tags")
                    params["tags"] = "{" + ",".join(query.tags) + "}"

                where = " AND ".join(conditions)
                rows = session.execute(
                    db.text(f"""
                        SELECT id, kind, content, tags, score, source, feedback_count,
                               feedback_avg_score, created_at, 0.0 AS sim
                        FROM agent_memories
                        WHERE {where}
                        ORDER BY created_at DESC
                        LIMIT :limit
                    """),
                    params,
                ).fetchall()

        results = []
        for row in rows:
            entry = MemoryEntry(
                kind=MemoryKind(row.kind),
                content=json.loads(row.content) if isinstance(row.content, str) else row.content,
                tags=list(row.tags) if row.tags else [],
                source=row.source or "",
                memory_id=row.id,
                score=float(row.score) if row.score else 1.0,
                feedback_count=int(row.feedback_count) if row.feedback_count else 0,
                feedback_avg_score=float(row.feedback_avg_score) if row.feedback_avg_score else 0.0,
                created_at=row.created_at,
            )
            results.append(SearchResult(entry=entry, similarity=float(row.sim) if row.sim else 0.0))

        return results

    def _feedback_db(self, fb: FeedbackRecord) -> bool:
        with db.get_session() as session:
            result = session.execute(
                db.text("""
                    UPDATE agent_memories
                    SET feedback_count = feedback_count + 1,
                        feedback_avg_score = (feedback_avg_score * feedback_count + :score) / (feedback_count + 1),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": fb.memory_id, "score": fb.score},
            )
            session.commit()
            return result.rowcount > 0

    def _delete_db(self, memory_id: str) -> bool:
        with db.get_session() as session:
            result = session.execute(
                db.text("DELETE FROM agent_memories WHERE id = :id"),
                {"id": memory_id},
            )
            session.commit()
            return result.rowcount > 0

    # ------------------------------------------------------------------
    # JSON 回退实现
    # ------------------------------------------------------------------

    def _load_json(self) -> List[dict]:
        if not MEMORY_FILE.exists():
            return []
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_json(self, data: List[dict]) -> None:
        MEMORY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )

    def _store_json(self, entry: MemoryEntry) -> str:
        with self._lock:
            data = self._load_json()
            data.append({
                "id": entry.memory_id,
                "kind": entry.kind.value,
                "content": entry.content,
                "tags": entry.tags,
                "score": entry.score,
                "source": entry.source,
                "feedback_count": entry.feedback_count,
                "feedback_avg_score": entry.feedback_avg_score,
                "created_at": entry.created_at.isoformat(),
            })
            # 只保留最近 1000 条
            if len(data) > 1000:
                data = data[-1000:]
            self._save_json(data)
        return entry.memory_id

    def _search_json(self, query: SearchQuery) -> List[SearchResult]:
        with self._lock:
            data = self._load_json()

        matched = []
        for item in data:
            if query.kind and item.get("kind") != query.kind.value:
                continue
            if query.tags:
                item_tags = set(item.get("tags", []))
                if not item_tags.intersection(query.tags):
                    continue
            if item.get("score", 1.0) < query.min_score:
                continue
            entry = MemoryEntry(
                kind=MemoryKind(item["kind"]),
                content=item["content"],
                tags=item.get("tags", []),
                source=item.get("source", ""),
                memory_id=item["id"],
                score=item.get("score", 1.0),
                feedback_count=item.get("feedback_count", 0),
                feedback_avg_score=item.get("feedback_avg_score", 0.0),
                created_at=datetime.fromisoformat(item["created_at"]) if item.get("created_at") else None,
            )
            matched_tags = query.tags or []
            found = [t for t in matched_tags if t in entry.tags]
            matched.append(SearchResult(entry=entry, matched_tags=found))

        # 按时间倒序
        matched.sort(key=lambda r: r.entry.created_at or datetime.min, reverse=True)
        return matched[: query.limit]

    def _feedback_json(self, fb: FeedbackRecord) -> bool:
        with self._lock:
            data = self._load_json()
            for item in data:
                if item["id"] == fb.memory_id:
                    item["feedback_count"] = item.get("feedback_count", 0) + 1
                    old_avg = item.get("feedback_avg_score", 0.0)
                    old_cnt = item["feedback_count"] - 1
                    item["feedback_avg_score"] = (old_avg * old_cnt + fb.score) / item["feedback_count"] if item["feedback_count"] > 0 else float(fb.score)
                    self._save_json(data)
                    return True
        return False

    def _delete_json(self, memory_id: str) -> bool:
        with self._lock:
            data = self._load_json()
            before = len(data)
            data = [d for d in data if d["id"] != memory_id]
            if len(data) < before:
                self._save_json(data)
                return True
        return False


# 全局单例
_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store