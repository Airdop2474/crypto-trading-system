"""
质量报告生成器

将质量检查结果生成 Markdown 格式报告
"""

from pathlib import Path
from typing import Dict
from datetime import datetime

from src.utils.logger import logger


class ReportGenerator:
    """质量报告生成器"""

    def __init__(self, report_dir: str = "data/reports"):
        """
        初始化报告生成器

        参数：
            report_dir: 报告保存目录
        """
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def generate_markdown(
        self,
        results: Dict,
        symbol: str,
        timeframe: str,
    ) -> Path:
        """
        生成 Markdown 格式报告

        参数：
            results: 质量检查结果
            symbol: 交易对
            timeframe: 时间周期

        返回：
            报告文件路径
        """
        lines = []

        # 标题
        lines.append("# 数据质量检查报告")
        lines.append("")
        lines.append(f"**交易对：** {symbol}  ")
        lines.append(f"**时间周期：** {timeframe}  ")
        lines.append(f"**检查时间：** {results['check_time']}  ")
        lines.append(f"**记录数量：** {results['record_count']}  ")
        lines.append("")

        # 总结
        summary = results["summary"]
        status = "通过" if summary["all_passed"] else "失败"
        status_icon = "PASS" if summary["all_passed"] else "FAIL"

        lines.append("## 总体结果")
        lines.append("")
        lines.append(f"**状态：** {status_icon} ({status})  ")
        lines.append(f"**通过：** {summary['passed']}/{summary['total_checks']}  ")
        lines.append(f"**失败：** {summary['failed']}/{summary['total_checks']}  ")
        lines.append("")

        # 检查详情表格
        lines.append("## 检查详情")
        lines.append("")
        lines.append("| 检查项 | 状态 | 详情 |")
        lines.append("|--------|------|------|")

        check_names = {
            "time_continuity": "时间连续性",
            "time_uniqueness": "时间唯一性",
            "price_logic": "价格逻辑性",
            "price_reasonability": "价格合理性",
            "volume_reasonability": "成交量合理性",
            "data_completeness": "数据完整性",
            "data_version": "数据版本",
        }

        for check_id, check_name in check_names.items():
            if check_id in results["checks"]:
                check = results["checks"][check_id]
                status = "PASS" if check.get("passed", False) else "FAIL"
                detail = self._format_check_detail(check_id, check)
                lines.append(f"| {check_name} | {status} | {detail} |")

        lines.append("")

        # 数据版本信息
        if "data_version" in results["checks"]:
            version = results["checks"]["data_version"]
            lines.append("## 数据版本")
            lines.append("")
            lines.append(f"**算法：** {version.get('algorithm', 'N/A')}  ")
            lines.append(f"**哈希：** `{version.get('hash', 'N/A')}`  ")
            lines.append("")

        # 失败详情（如果有）
        if not summary["all_passed"]:
            lines.append("## 失败详情")
            lines.append("")
            for check_id, check in results["checks"].items():
                if not check.get("passed", False):
                    lines.append(f"### {check_names.get(check_id, check_id)}")
                    lines.append("")
                    lines.extend(self._format_failure_detail(check_id, check))
                    lines.append("")

        # 验收标准
        lines.append("## 验收标准")
        lines.append("")
        lines.append("根据 DATA_QUALITY_STANDARD.md：")
        lines.append("")
        lines.append("- 缺口数量 = 0")
        lines.append("- 重复数量 = 0")
        lines.append("- 异常K线 < 0.1%")
        lines.append("- 数据完整（无空值）")
        lines.append("- 有 SHA256 版本记录")
        lines.append("")

        # 页脚
        lines.append("---")
        lines.append("")
        lines.append(f"*报告生成时间：{datetime.now().isoformat()}*")

        # 保存报告
        content = "\n".join(lines)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        symbol_safe = symbol.replace("/", "_")
        filename = f"quality_report_{symbol_safe}_{timeframe}_{timestamp}.md"
        report_path = self.report_dir / filename

        report_path.write_text(content, encoding="utf-8")
        logger.info(f"Markdown report saved to {report_path}")

        return report_path

    def _format_check_detail(self, check_id: str, check: Dict) -> str:
        """格式化检查详情（用于表格）"""
        if check_id == "time_continuity":
            return f"{check.get('gap_count', 0)} 个缺口"
        elif check_id == "time_uniqueness":
            return f"{check.get('duplicate_count', 0)} 个重复"
        elif check_id == "price_logic":
            return f"{check.get('invalid_count', 0)} 个无效行"
        elif check_id == "price_reasonability":
            ratio = check.get("abnormal_ratio", 0)
            return f"{check.get('abnormal_count', 0)} 个异常 ({ratio:.2%})"
        elif check_id == "volume_reasonability":
            zero = check.get("zero_volume_count", 0)
            abnormal = check.get("abnormal_volume_count", 0)
            return f"{zero} 零成交量, {abnormal} 异常值"
        elif check_id == "data_completeness":
            return f"{check.get('total_nulls', 0)} 个空值"
        elif check_id == "data_version":
            hash_str = check.get("hash", "")
            return f"{hash_str[:16]}..." if hash_str else "N/A"
        return "N/A"

    def _format_failure_detail(self, check_id: str, check: Dict) -> list:
        """格式化失败详情"""
        lines = []

        if check_id == "time_continuity" and check.get("gaps"):
            lines.append("发现以下时间缺口：")
            lines.append("")
            for gap in check["gaps"][:5]:
                lines.append(f"- 位置 {gap['position']}: "
                            f"{gap['before']} → {gap['after']}")

        elif check_id == "time_uniqueness" and check.get("duplicates"):
            lines.append("发现以下重复时间戳：")
            lines.append("")
            for dup in check["duplicates"][:5]:
                lines.append(f"- {dup['timestamp']}: {dup['count']} 次")

        elif check_id == "price_logic" and check.get("invalid_rows"):
            lines.append("发现以下价格逻辑错误：")
            lines.append("")
            for row in check["invalid_rows"][:5]:
                violations = ", ".join(row["violations"])
                lines.append(f"- 索引 {row['index']}: {violations}")

        elif check_id == "price_reasonability" and check.get("abnormal_rows"):
            lines.append("发现以下异常价格波动：")
            lines.append("")
            for row in check["abnormal_rows"][:5]:
                lines.append(f"- 索引 {row['index']}: "
                            f"涨跌幅 {row['change_pct']:.2%}")

        elif check_id == "data_completeness" and check.get("null_counts"):
            lines.append("发现以下空值：")
            lines.append("")
            for col, count in check["null_counts"].items():
                if count > 0:
                    lines.append(f"- {col}: {count} 个空值")

        return lines


# 导出
__all__ = ["ReportGenerator"]
