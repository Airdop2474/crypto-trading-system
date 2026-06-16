"""src/main.py 入口分发测试（覆盖各 MODE 分支）。"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

import src.main as main_mod


@pytest.mark.parametrize("mode", ["backtest", "paper", "live"])
def test_main_known_modes(monkeypatch, mode):
    monkeypatch.setenv("MODE", mode)
    main_mod.main()  # 不应抛异常


def test_main_unknown_mode_exits(monkeypatch):
    monkeypatch.setenv("MODE", "nonsense")
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 1
