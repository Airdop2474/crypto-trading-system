"""ReportGenerator（数据质量报告）单元测试，覆盖通过/失败详情分支。"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from src.data.report_generator import ReportGenerator


def _passing_results():
    return {
        "check_time": "2024-01-01T00:00:00",
        "record_count": 500,
        "summary": {"all_passed": True, "passed": 7, "failed": 0, "total_checks": 7},
        "checks": {
            "time_continuity": {"passed": True, "gap_count": 0},
            "time_uniqueness": {"passed": True, "duplicate_count": 0},
            "price_logic": {"passed": True, "invalid_count": 0},
            "price_reasonability": {"passed": True, "abnormal_count": 0, "abnormal_ratio": 0.0},
            "volume_reasonability": {"passed": True, "zero_volume_count": 0, "abnormal_volume_count": 0},
            "data_completeness": {"passed": True, "total_nulls": 0},
            "data_version": {"passed": True, "algorithm": "SHA256", "hash": "abcdef0123456789aa"},
        },
    }


def _failing_results():
    return {
        "check_time": "2024-01-01T00:00:00",
        "record_count": 10,
        "summary": {"all_passed": False, "passed": 3, "failed": 4, "total_checks": 7},
        "checks": {
            "time_continuity": {"passed": False, "gap_count": 2,
                                "gaps": [{"position": 3, "before": "t1", "after": "t2"}]},
            "time_uniqueness": {"passed": False, "duplicate_count": 1,
                                "duplicates": [{"timestamp": "t1", "count": 2}]},
            "price_logic": {"passed": False, "invalid_count": 1,
                            "invalid_rows": [{"index": 5, "violations": ["high<low"]}]},
            "price_reasonability": {"passed": False, "abnormal_count": 1, "abnormal_ratio": 0.1,
                                    "abnormal_rows": [{"index": 6, "change_pct": 0.5}]},
            "data_completeness": {"passed": False, "total_nulls": 2,
                                  "null_counts": {"close": 2, "open": 0}},
        },
    }


def test_generate_markdown_passing(tmp_path):
    gen = ReportGenerator(report_dir=str(tmp_path))
    p = gen.generate_markdown(_passing_results(), "BTC/USDT", "4h")
    assert p.exists()
    txt = p.read_text(encoding="utf-8")
    assert "数据质量检查报告" in txt
    assert "PASS (通过)" in txt
    assert "数据版本" in txt
    assert "BTC_USDT" in p.name


def test_generate_markdown_failing_details(tmp_path):
    gen = ReportGenerator(report_dir=str(tmp_path))
    p = gen.generate_markdown(_failing_results(), "ETH/USDT", "1h")
    txt = p.read_text(encoding="utf-8")
    assert "FAIL (失败)" in txt
    assert "失败详情" in txt
    assert "时间缺口" in txt          # _format_failure_detail 各分支
    assert "重复时间戳" in txt
    assert "价格逻辑错误" in txt
    assert "异常价格波动" in txt
    assert "空值" in txt
