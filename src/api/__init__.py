"""Web API 层（FastAPI）：把 Paper Trading 引擎的真实运行结果暴露给前端。

数据来源：复用 scripts/run_paper_trading.py 的同款装配，跑一次 Paper
Trading 并缓存内存结果，再映射成 frontend/lib/types.ts 的契约。
不接实时行情/实盘——那些数据源后端尚不存在。
"""

from src.api.app import app

__all__ = ["app"]
