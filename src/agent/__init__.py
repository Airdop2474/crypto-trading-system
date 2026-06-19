"""
AI Agent 分析模块

提供交易分析能力（只分析，不自动执行）：
- TradingAnalyzer: 5种分析类型（回测/归因/风险/敏感性/周报）
- AuditLog: AI 调用审计日志
"""

from src.agent.analyzer import TradingAnalyzer
from src.agent.audit_log import AuditLog

__all__ = ["TradingAnalyzer", "AuditLog"]
