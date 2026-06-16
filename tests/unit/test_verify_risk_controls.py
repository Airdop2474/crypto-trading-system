"""把 §2 风控门禁验证脚本纳入 CI：每个场景必须 PASS。"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from scripts.verify_risk_controls import run_all, SCENARIOS


@pytest.mark.parametrize("result", run_all(), ids=[s[0] for s in SCENARIOS])
def test_risk_control_scenario_passes(result):
    assert result["passed"], f"{result['name']} 失败：{result['detail']}"


def test_all_six_scenarios_present():
    assert len(run_all()) == 6
