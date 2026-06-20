"""
回测报告生成器

将回测引擎结果生成结构化报告（JSON）和可读报告（Markdown）。
遵循 BACKTEST_VALIDATION.md 的报告格式：元信息、性能指标、成本分析。

只记录真实可得的数据，不编造验证字段（可复现性原则）。
"""

import json
import uuid
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

import pandas as pd

from src.utils.logger import logger


class BacktestReportGenerator:
    """回测报告生成器"""

    def __init__(self, report_dir: str = "data/reports/backtest"):
        """
        初始化报告生成器

        参数：
            report_dir: 报告保存目录
        """
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def build_report(
        self,
        results: Dict,
        strategy,
        data: Optional[pd.DataFrame] = None,
        cost_model: Optional[Dict] = None,
    ) -> Dict:
        """
        从回测结果构建结构化报告字典

        参数：
            results: 回测引擎结果
            strategy: 策略实例（取名称与参数）
            data: 可选，原始 OHLCV 数据（用于计算 SHA256 版本）
            cost_model: 可选，成本模型（手续费/滑点率）

        返回：
            报告字典
        """
        if not results.get("success"):
            raise ValueError("Cannot build report from unsuccessful backtest")

        equity_curve = results["equity_curve"]
        metrics = results.get("metrics", {})

        report = {
            "backtest_id": str(uuid.uuid4()),
            "metadata": self._build_metadata(
                results, strategy, equity_curve, data, cost_model
            ),
            "performance": self._build_performance(results, metrics),
            "cost_analysis": self._build_cost_analysis(results),
        }
        return report

    def _build_metadata(
        self, results, strategy, equity_curve, data, cost_model
    ) -> Dict:
        """构建元信息（可复现性）"""
        period = {"start": None, "end": None}
        if equity_curve:
            period["start"] = pd.Timestamp(equity_curve[0]["time"]).isoformat()
            period["end"] = pd.Timestamp(equity_curve[-1]["time"]).isoformat()

        data_version = "N/A"
        if data is not None and not data.empty:
            data_version = hex(pd.util.hash_pandas_object(data).sum())

        return {
            "run_time": datetime.now().isoformat(),
            "data_version": data_version,
            "strategy_name": getattr(strategy, "name", "Unknown"),
            "parameters": dict(getattr(strategy, "parameters", {})),
            "period": period,
            "initial_balance": results["initial_capital"],
            "cost_model": cost_model or {},
        }

    @staticmethod
    def _build_performance(results, metrics) -> Dict:
        """构建性能指标段"""
        return {
            "total_return": results["total_return"],
            "annual_return": metrics.get("annual_return", 0.0),
            "max_drawdown": metrics.get("max_drawdown", 0.0),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
            "win_rate": metrics.get("win_rate", 0.0),
            "profit_factor": metrics.get("profit_factor", 0.0),
            "avg_trade": metrics.get("avg_trade", 0.0),
            "total_trades": results["total_trades"],
            "final_equity": results["final_equity"],
        }

    @staticmethod
    def _build_cost_analysis(results) -> Dict:
        """从交易记录真实汇总成本"""
        trades = results["trades"]
        total_commission = sum(t.get("commission", 0.0) for t in trades)
        total_slippage = sum(t.get("slippage", 0.0) for t in trades)
        total_cost = total_commission + total_slippage
        initial = results["initial_capital"]
        cost_pct = total_cost / initial if initial > 0 else 0.0

        return {
            "total_commission": total_commission,
            "total_slippage": total_slippage,
            "total_cost": total_cost,
            "cost_percentage": cost_pct,
        }

    def save_json(self, report: Dict) -> Path:
        """保存 JSON 报告，返回路径"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = report["metadata"]["strategy_name"]
        path = self.report_dir / f"backtest_{name}_{timestamp}.json"
        path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        logger.info(f"Backtest JSON report saved to {path}")
        return path

    def render_markdown(self, report: Dict) -> str:
        """将报告字典渲染为 Markdown 文本"""
        meta = report["metadata"]
        perf = report["performance"]
        cost = report["cost_analysis"]

        lines = [
            "# 回测报告",
            "",
            f"**回测 ID：** `{report['backtest_id']}`  ",
            f"**策略：** {meta['strategy_name']}  ",
            f"**运行时间：** {meta['run_time']}  ",
            f"**回测区间：** {meta['period']['start']} → {meta['period']['end']}  ",
            f"**初始资金：** ${meta['initial_balance']:,.2f}  ",
            f"**数据版本：** `{meta['data_version'][:16]}...`  "
            if meta["data_version"] != "N/A"
            else "**数据版本：** N/A  ",
            "",
            "## 策略参数",
            "",
        ]

        if meta["parameters"]:
            lines.append("| 参数 | 值 |")
            lines.append("|------|-----|")
            for k, v in meta["parameters"].items():
                lines.append(f"| {k} | {v} |")
        else:
            lines.append("（无记录）")
        lines.append("")

        # 性能指标
        lines.extend([
            "## 性能指标",
            "",
            "| 指标 | 值 |",
            "|------|-----|",
            f"| 总收益率 | {perf['total_return']:.2%} |",
            f"| 年化收益率 | {perf['annual_return']:.2%} |",
            f"| 最大回撤 | {perf['max_drawdown']:.2%} |",
            f"| 夏普比率 | {perf['sharpe_ratio']:.2f} |",
            f"| 胜率 | {perf['win_rate']:.2%} |",
            f"| 盈亏比 | {perf['profit_factor']:.2f} |",
            f"| 平均每笔盈亏 | ${perf['avg_trade']:,.2f} |",
            f"| 交易笔数 | {perf['total_trades']} |",
            f"| 最终权益 | ${perf['final_equity']:,.2f} |",
            "",
            "## 成本分析",
            "",
            "| 项目 | 金额 |",
            "|------|------|",
            f"| 总手续费 | ${cost['total_commission']:,.2f} |",
            f"| 总滑点 | ${cost['total_slippage']:,.2f} |",
            f"| 总成本 | ${cost['total_cost']:,.2f} |",
            f"| 成本占比 | {cost['cost_percentage']:.2%} |",
            "",
            "---",
            "",
            f"*报告生成时间：{datetime.now().isoformat()}*",
        ])

        return "\n".join(lines)

    def save_markdown(self, report: Dict) -> Path:
        """保存 Markdown 报告，返回路径"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = report["metadata"]["strategy_name"]
        path = self.report_dir / f"backtest_{name}_{timestamp}.md"
        path.write_text(self.render_markdown(report), encoding="utf-8")
        logger.info(f"Backtest Markdown report saved to {path}")
        return path

    def generate(
        self,
        results: Dict,
        strategy,
        data: Optional[pd.DataFrame] = None,
        cost_model: Optional[Dict] = None,
    ) -> Dict:
        """
        一站式：构建报告并保存 JSON + Markdown

        返回：
            {"report": dict, "json_path": Path, "markdown_path": Path}
        """
        report = self.build_report(results, strategy, data, cost_model)
        return {
            "report": report,
            "json_path": self.save_json(report),
            "markdown_path": self.save_markdown(report),
        }


# 导出
__all__ = ["BacktestReportGenerator"]
