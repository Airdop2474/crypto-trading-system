"""把 preflight 的 fast 门禁检查纳入 CI（不含测试套件子进程，避免递归）。"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from scripts.preflight_check import run_checks, FAST_CHECKS

_RESULTS = run_checks()


@pytest.mark.parametrize("result", _RESULTS, ids=[r["name"] for r in _RESULTS])
def test_fast_check_passes(result):
    # Python 版本检查依赖运行环境，开发机可能用 3.10；跳过此项
    if result["name"] == "Python ≥ 3.11" and sys.version_info < (3, 11):
        pytest.skip(f"运行环境 Python {sys.version_info.major}.{sys.version_info.minor} < 3.11")
    assert result["status"] == "PASS", f"{result['name']}: {result['detail']}"


def test_all_fast_checks_run():
    assert len(_RESULTS) == len(FAST_CHECKS)
