"""
上下文构建器 — 从记忆库检索相关信息，拼成 LLM prompt 上下文。

每次分析/进化请求时调用，将相关历史记忆注入 prompt 头部，
让 LLM 感知历史上下文。
"""

from typing import Any, Dict, List, Optional

from src.agent.memory.schemas import MemoryKind, SearchQuery, SearchResult
from src.agent.memory.store import get_memory_store


class ContextBuilder:
    """从记忆库构建 LLM 上下文。"""

    def __init__(self):
        self._store = get_memory_store()

    def build_analysis_context(
        self,
        strategy_id: str,
        task: str,
        limit: int = 8,
    ) -> str:
        """为分析任务构建上下文文本。

        检索策略：
        1. 同类分析历史（同一 strategy_id + task）
        2. 该策略最近交易结果
        3. 该策略的人类反馈

        返回格式化的上下文文本，空字符串表示无上下文。
        """
        parts = []

        # 1. 同类分析历史
        analysis = self._store.search(SearchQuery(
            query=f"analysis of {strategy_id} {task}",
            kind=MemoryKind.ANALYSIS,
            tags=[strategy_id, task],
            limit=3,
        ))
        if analysis:
            parts.append(self._fmt_section("相关历史分析", analysis))

        # 2. 最近交易结果
        trades = self._store.search(SearchQuery(
            query=f"recent trades {strategy_id}",
            kind=MemoryKind.TRADE,
            tags=[strategy_id],
            limit=5,
        ))
        if trades:
            parts.append(self._fmt_section("最近交易", trades))

        # 3. 人类反馈
        feedbacks = self._store.search(SearchQuery(
            query=f"feedback on {strategy_id}",
            kind=MemoryKind.FEEDBACK,
            tags=[strategy_id],
            limit=3,
        ))
        if feedbacks:
            parts.append(self._fmt_section("历史反馈", feedbacks))

        return "\n\n".join(parts) if parts else ""

    def build_evolution_context(
        self,
        strategy_id: str,
        strategy_key: str,
        limit: int = 3,
    ) -> str:
        """为策略进化构建上下文。

        检索：
        1. 同类策略的进化历史
        2. 该类策略的人类反馈
        """
        parts = []

        evos = self._store.search(SearchQuery(
            query=f"evolution of {strategy_key} strategy",
            kind=MemoryKind.EVOLUTION,
            tags=[strategy_key],
            limit=limit,
        ))
        if evos:
            parts.append(self._fmt_section("历史参数进化", evos))

        return "\n\n".join(parts) if parts else ""

    def build_daily_context(self, tags: Optional[List[str]] = None) -> str:
        """为日结/周报构建上下文。"""
        parts = []

        daily = self._store.search(SearchQuery(
            query="recent daily summaries",
            kind=MemoryKind.DAILY,
            tags=tags,
            limit=5,
        ))
        if daily:
            parts.append(self._fmt_section("近期日结摘要", daily))

        risks = self._store.search(SearchQuery(
            query="recent risk events",
            kind=MemoryKind.RISK,
            tags=tags,
            limit=3,
        ))
        if risks:
            parts.append(self._fmt_section("近期风控事件", risks))

        return "\n\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_section(title: str, results: List[SearchResult]) -> str:
        lines = [f"[{title}]"]
        for r in results:
            entry = r.entry
            ts = entry.created_at.strftime("%Y-%m-%d %H:%M") if entry.created_at else "?"
            tags = " ".join(f"#{t}" for t in entry.tags[:3])
            score_info = f" (评分:{entry.feedback_avg_score:.1f}/反馈{entry.feedback_count}次)" if entry.feedback_count > 0 else ""
            lines.append(f"  - [{ts}] {tags}{score_info}")
            # 取内容摘要（前 2 个字段）
            summary = " | ".join(str(v)[:80] for v in list(entry.content.values())[:2])
            lines.append(f"    {summary}")
        return "\n".join(lines)
