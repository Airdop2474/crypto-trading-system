"""
Paper Trading 报告生成器

消费 PaperTradingRunner 的运行结果，生成账户快照报告：
账户价值、已实现/未实现盈亏、成本分析、交易统计。
输出 JSON + Markdown。
"""

import json
from pathlib import Path
from typing import Dict
from datetime import datetime

from src.utils.logger import logger


class PaperTradingReportGenerator:
    """Paper Trading 报告生成器"""

    def __init__(self, report_dir: str = "data/reports/paper"):
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def build_report(self, run_result: Dict, current_prices: Dict[str, float]) -> Dict:
        """
        构建报告字典

        参数：
            run_result: PaperTradingRunner.run() 的返回
            current_prices: {symbol: price} 用于持仓市值估算
        """
        stats = run_result["statistics"]
        symbol = run_result["symbol"]
        trades = run_result["trade_history"]

        initial = stats["initial_balance"]
        cash = stats["current_balance"]
        positions = stats["positions"]

        position_value = sum(
            amt * current_prices.get(sym, 0.0) for sym, amt in positions.items()
        )
        total_value = cash + position_value
        total_return = (total_value - initial) / initial if initial > 0 else 0.0

        realized = run_result.get("realized_pnl", 0.0)
        # 未实现 = 总盈亏 - 已实现
        unrealized = (total_value - initial) - realized

        buy_count = sum(1 for t in trades if t["side"] == "buy")
        sell_count = sum(1 for t in trades if t["side"] == "sell")

        return {
            "generated_at": datetime.now().isoformat(),
            "symbol": symbol,
            "account": {
                "initial_balance": initial,
                "cash": cash,
                "position_value": position_value,
                "total_value": total_value,
                "total_return": total_return,
            },
            "pnl": {
                "realized": realized,
                "unrealized": unrealized,
            },
            "cost_analysis": {
                "total_commission": stats["total_commission"],
                "total_slippage": stats["total_slippage"],
                "total_cost": stats["total_cost"],
            },
            "trades": {
                "total": stats["total_trades"],
                "buy": buy_count,
                "sell": sell_count,
                "open_lots": len(run_result.get("open_lots", {})),
            },
        }

    def render_markdown(self, report: Dict) -> str:
        """渲染为 Markdown 文本"""
        acc = report["account"]
        pnl = report["pnl"]
        cost = report["cost_analysis"]
        tr = report["trades"]

        lines = [
            "# Paper Trading 报告",
            "",
            f"**交易对：** {report['symbol']}  ",
            f"**生成时间：** {report['generated_at']}  ",
            "",
            "## 账户",
            "",
            "| 项目 | 金额 |",
            "|------|------|",
            f"| 初始资金 | ${acc['initial_balance']:,.2f} |",
            f"| 现金 | ${acc['cash']:,.2f} |",
            f"| 持仓市值 | ${acc['position_value']:,.2f} |",
            f"| 总价值 | ${acc['total_value']:,.2f} |",
            f"| 总收益率 | {acc['total_return']:.2%} |",
            "",
            "## 盈亏",
            "",
            "| 类型 | 金额 |",
            "|------|------|",
            f"| 已实现 | ${pnl['realized']:,.2f} |",
            f"| 未实现 | ${pnl['unrealized']:,.2f} |",
            "",
            "## 成本分析",
            "",
            "| 项目 | 金额 |",
            "|------|------|",
            f"| 总手续费 | ${cost['total_commission']:,.2f} |",
            f"| 总滑点 | ${cost['total_slippage']:,.2f} |",
            f"| 总成本 | ${cost['total_cost']:,.2f} |",
            "",
            "## 交易统计",
            "",
            "| 项目 | 数量 |",
            "|------|------|",
            f"| 总成交 | {tr['total']} |",
            f"| 买入 | {tr['buy']} |",
            f"| 卖出 | {tr['sell']} |",
            f"| 未平仓档位 | {tr['open_lots']} |",
            "",
            "---",
            "",
            f"*报告生成时间：{report['generated_at']}*",
        ]
        return "\n".join(lines)

    def generate(self, run_result: Dict, current_prices: Dict[str, float]) -> Dict:
        """构建并保存 JSON + Markdown，返回路径与报告"""
        report = self.build_report(run_result, current_prices)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sym = report["symbol"].replace("/", "_")

        json_path = self.report_dir / f"paper_{sym}_{ts}.json"
        json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        md_path = self.report_dir / f"paper_{sym}_{ts}.md"
        md_path.write_text(self.render_markdown(report), encoding="utf-8")

        logger.info(f"Paper trading report saved: {json_path}, {md_path}")
        return {"report": report, "json_path": json_path, "markdown_path": md_path}


# 导出
__all__ = ["PaperTradingReportGenerator"]
