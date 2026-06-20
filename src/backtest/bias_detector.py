"""
前视偏差检测器

检测回测代码和逻辑中的前视偏差
"""

import ast
import re
from typing import Dict, List
from datetime import datetime
import inspect

from src.utils.logger import logger


class BiasDetector:
    """
    前视偏差检测器

    检测常见的前视偏差模式。
    注意：正则匹配存在误报（false positive）风险 —— 字符串/注释/multiline
    上下文可能被错误匹配。建议在 regex 快速扫描后，通过 AST 级别分析
    确认（见 check_strategy_code_ast 方法）。
    """

    # 危险代码模式（正则快速扫描，可能误报，需 AST 确认）
    DANGEROUS_PATTERNS = [
        # iloc[-1] 在 bar-by-bar 模型中是当前已收盘 bar，不是未来数据
        # 降级为 info，仅作提醒而非高风险误报
        (r'\.iloc\[-1\]', '使用当前K线数据（iloc[-1]），bar-by-bar 模型下安全', 'info'),
        (r'\.tail\(1\)', '使用当前K线数据（tail(1)），bar-by-bar 模型下安全', 'info'),
        (r'\.loc\[.*current_time.*\]', '使用当前时间索引数据', 'high'),
        (r'\.shift\(-\d+\)', '使用未来数据（负shift）', 'critical'),
        (r'\.rolling\(.*\)\.mean\(\)\.iloc\[-1\]', '使用包含当前K线的滚动指标', 'medium'),
    ]

    # 建议的安全模式
    SAFE_PATTERNS = [
        r'\.iloc\[-2\]',  # 使用前一根K线
        r'\.iloc\[:-1\]',  # 排除当前K线
        r'\.shift\(\d+\)',  # 向过去shift（正数）
    ]

    def __init__(self):
        """初始化检测器"""
        self.warnings = []

    def check_strategy_code(self, strategy) -> Dict:
        """
        检查策略代码中的前视偏差

        参数：
            strategy: 策略实例

        返回：
            检测结果
        """
        self.warnings = []

        # 获取策略的 on_bar 方法源代码
        try:
            source_code = inspect.getsource(strategy.on_bar)
        except Exception as e:
            logger.warning(f"Cannot get source code: {e}")
            return {
                "success": False,
                "message": "Cannot analyze source code",
            }

        # 检查危险模式
        for pattern, description, severity in self.DANGEROUS_PATTERNS:
            matches = re.finditer(pattern, source_code)
            for match in matches:
                self.warnings.append({
                    "pattern": pattern,
                    "description": description,
                    "severity": severity,
                    "line": source_code[:match.start()].count('\n') + 1,
                })

        # 检查是否使用了安全模式
        has_safe_patterns = any(
            re.search(pattern, source_code)
            for pattern in self.SAFE_PATTERNS
        )

        return {
            "success": True,
            "strategy": strategy.name,
            "has_warnings": len(self.warnings) > 0,
            "warning_count": len(self.warnings),
            "warnings": self.warnings,
            "has_safe_patterns": has_safe_patterns,
        }

    def check_strategy_code_ast(self, strategy) -> Dict:
        """使用 AST 解析精确检测 look-ahead bias（无正则误报）。

        解析策略的 on_bar 源码为 AST，遍历所有节点检测危险模式：
        - Call(func=Attribute(attr='shift'), args=[UnaryOp(USub)])  负 shift
        - 链表切片 [-1] 在 bar-by-bar 中为当前 bar（安全，降级为 info）

        参数：
            strategy: 策略实例

        返回：
            {"success": bool, "warnings": [...], "error": Optional[str]}
        """
        try:
            source_code = inspect.getsource(strategy.on_bar)
        except Exception as e:
            return {"success": False, "warnings": [], "error": str(e)}

        warnings = []
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return {"success": False, "warnings": [], "error": f"Syntax error: {e}"}

        class BiasVisitor(ast.NodeVisitor):
            def visit_Call(self, node):
                # 检测 .shift(-N) 模式
                if isinstance(node.func, ast.Attribute) and node.func.attr == "shift":
                    for arg in node.args:
                        if isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub):
                            warnings.append({
                                "pattern": ".shift(-N)",
                                "description": "使用未来数据（负shift）",
                                "severity": "critical",
                                "line": node.lineno,
                            })
                self.generic_visit(node)

        BiasVisitor().visit(tree)

        return {
            "success": True,
            "warnings": warnings,
            "has_ast_warnings": len(warnings) > 0,
            "error": None,
        }

    def check_backtest_logic(self, results: Dict) -> Dict:
        """
        检查回测逻辑的时间顺序

        参数：
            results: 回测结果

        返回：
            检测结果
        """
        violations = []

        # 检查信号和交易的时间戳
        signals = results.get("signals", [])
        trades = results.get("trades", [])

        # 对于每个交易，检查是否有对应的信号在之前
        for trade in trades:
            trade_time = trade["time"]

            # 找到最近的信号
            prior_signals = [
                s for s in signals
                if s["time"] < trade_time
            ]

            if not prior_signals:
                violations.append({
                    "type": "no_prior_signal",
                    "trade": trade,
                    "message": f"交易 {trade['type']} 在 {trade_time} 没有先前信号",
                })

        # 检查交易时间顺序
        for i in range(len(trades) - 1):
            if trades[i]["time"] >= trades[i + 1]["time"]:
                violations.append({
                    "type": "time_order",
                    "message": f"交易时间顺序错误: {trades[i]['time']} >= {trades[i+1]['time']}",
                })

        return {
            "success": True,
            "has_violations": len(violations) > 0,
            "violation_count": len(violations),
            "violations": violations,
        }

    def check_order_execution(self, results: Dict) -> Dict:
        """
        检查订单执行逻辑

        验证订单是否在信号生成后的下一根K线执行

        参数：
            results: 回测结果

        返回：
            检测结果
        """
        issues = []

        signals = results.get("signals", [])
        trades = results.get("trades", [])
        equity_curve = results.get("equity_curve", [])

        # 为每个 BUY 信号，找到对应的 BUY 交易
        for signal in signals:
            if signal["signal"] == "BUY":
                # 找到信号后的第一笔 BUY 交易
                later_buys = [
                    t for t in trades
                    if t["type"] == "BUY" and t["time"] > signal["time"]
                ]

                if later_buys:
                    buy_trade = later_buys[0]

                    # 检查交易时间是否在信号之后
                    time_diff = (buy_trade["time"] - signal["time"]).total_seconds()

                    # 应该至少间隔一根K线（这里假设4小时 = 14400秒）
                    if time_diff < 3600:  # 少于1小时，可能有问题
                        issues.append({
                            "type": "execution_too_fast",
                            "signal_time": signal["time"],
                            "trade_time": buy_trade["time"],
                            "time_diff_seconds": time_diff,
                            "message": "订单执行过快，可能使用了当前K线价格",
                        })

        return {
            "success": True,
            "has_issues": len(issues) > 0,
            "issue_count": len(issues),
            "issues": issues,
        }

    def generate_report(
        self,
        code_check: Dict,
        logic_check: Dict,
        execution_check: Dict,
    ) -> Dict:
        """
        生成综合检测报告

        参数：
            code_check: 代码检查结果
            logic_check: 逻辑检查结果
            execution_check: 执行检查结果

        返回：
            综合报告
        """
        # 统计问题
        total_warnings = code_check.get("warning_count", 0)
        total_violations = logic_check.get("violation_count", 0)
        total_issues = execution_check.get("issue_count", 0)

        # 严重性分类
        critical_count = sum(
            1 for w in code_check.get("warnings", [])
            if w.get("severity") == "critical"
        )
        high_count = sum(
            1 for w in code_check.get("warnings", [])
            if w.get("severity") == "high"
        )

        # 判断是否通过
        passed = (
            critical_count == 0 and
            total_violations == 0 and
            total_issues == 0
        )

        return {
            "passed": passed,
            "summary": {
                "code_warnings": total_warnings,
                "critical_warnings": critical_count,
                "high_warnings": high_count,
                "logic_violations": total_violations,
                "execution_issues": total_issues,
            },
            "code_check": code_check,
            "logic_check": logic_check,
            "execution_check": execution_check,
            "recommendation": self._get_recommendation(
                critical_count, high_count, total_violations, total_issues
            ),
        }

    def _get_recommendation(
        self,
        critical: int,
        high: int,
        violations: int,
        issues: int,
    ) -> str:
        """生成建议"""
        if critical > 0:
            return "发现严重前视偏差！回测结果不可信，必须修复。"
        elif violations > 0:
            return "发现逻辑违规！请检查回测逻辑。"
        elif issues > 0:
            return "发现执行问题！请检查订单执行时机。"
        elif high > 0:
            return "发现高风险模式，建议人工审查代码。"
        else:
            return "未发现明显的前视偏差，但建议人工复核。"


# 导出
__all__ = ["BiasDetector"]
