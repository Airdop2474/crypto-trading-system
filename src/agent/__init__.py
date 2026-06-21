"""
AI Agent 分析模块

提供交易分析与策略进化能力：
- TradingAnalyzer: 5种分析类型（回测/归因/风险/敏感性/周报）
- AuditLog: AI 调用审计日志
- EvolutionEngine: 策略参数自动进化引擎
- LLMClient: LLM 抽象层（OpenAI/Anthropic/本地回退）
- EvolutionGuardrails: 进化安全阈值校验
"""

from src.agent.analyzer import TradingAnalyzer
from src.agent.audit_log import AuditLog
from src.agent.evolution_engine import EvolutionEngine
from src.agent.llm_client import LLMClient
from src.agent.evolution_guardrails import EvolutionGuardrails

__all__ = [
    "TradingAnalyzer",
    "AuditLog",
    "EvolutionEngine",
    "LLMClient",
    "EvolutionGuardrails",
]
