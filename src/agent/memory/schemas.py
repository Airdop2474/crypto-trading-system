"""
记忆系统 — 数据模型

定义 MemoryStore 使用的全部数据结构和枚举类型。
纯数据类，不依赖数据库或外部服务。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryKind(str, Enum):
    """记忆类型枚举"""
    ANALYSIS = "analysis"         # AI 分析结论
    TRADE = "trade"               # 已平仓交易
    EVOLUTION = "evolution"       # 策略参数进化
    FEEDBACK = "feedback"         # 人类反馈
    RISK = "risk"                 # 风控事件
    DAILY = "daily"               # 日结摘要


@dataclass
class MemoryEntry:
    """一条记忆"""
    kind: MemoryKind
    content: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    source: str = ""
    memory_id: str = ""
    score: float = 1.0
    feedback_count: int = 0
    feedback_avg_score: float = 0.0
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if not self.memory_id:
            import uuid
            self.memory_id = str(uuid.uuid4())


@dataclass
class SearchQuery:
    """检索请求"""
    query: str = ""
    kind: Optional[MemoryKind] = None
    tags: Optional[List[str]] = None
    limit: int = 10
    min_score: float = 0.0


@dataclass
class SearchResult:
    """检索结果"""
    entry: MemoryEntry
    similarity: float = 0.0  # 语义相似度 0-1
    matched_tags: List[str] = field(default_factory=list)


@dataclass
class FeedbackRecord:
    """一条人类反馈"""
    memory_id: str
    score: int  # 1-5
    note: str = ""
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


# 检索用常量
DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT = 100
MIN_FEEDBACK_SCORE = 1
MAX_FEEDBACK_SCORE = 5
