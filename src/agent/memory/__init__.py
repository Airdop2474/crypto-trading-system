"""
记忆系统 — 长期记忆存储与检索

为系统内部 AI 功能提供持久化记忆能力：
- 存储：分析结论、交易结果、进化历史、人类反馈、风控事件
- 检索：语义向量搜索 + 标签过滤 + 时间排序
- 反馈：人类评分强化学习信号
- 维护：定时衰减、去重、修剪

用法：
    from src.agent.memory import MemoryStore, MemoryKind
    store = MemoryStore()
    mid = store.store(MemoryKind.ANALYSIS, {"结论": "..."}, tags=["grid"])
    store.feedback(mid, score=4, note="有用")
    results = store.search(SearchQuery(query="网格策略表现", tags=["grid"]))
"""

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
from src.agent.memory.store import MemoryStore, get_memory_store
from src.agent.memory.context_builder import ContextBuilder
from src.agent.memory.consolidator import MemoryConsolidator
from src.agent.memory.vector import EmbeddingGenerator, get_embedder

__all__ = [
    "MemoryStore",
    "MemoryKind",
    "MemoryEntry",
    "SearchQuery",
    "SearchResult",
    "FeedbackRecord",
    "ContextBuilder",
    "MemoryConsolidator",
    "EmbeddingGenerator",
    "get_memory_store",
    "get_embedder",
]
