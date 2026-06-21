"""结构化日志（JSON sink + environment 字段）单元测试。

验证 setup_logger 的可选 JSON 结构化输出：
- json_logs=True 时产出可解析的单行 JSON 日志，且带 environment 字段。
- json_logs=False（默认开发态）时不产出 JSON 文件，行为与原先一致。

用临时目录，避免污染真实 logs/。测试末尾把 logger 复位回默认开发配置。
"""

import sys
import json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.utils.logger import logger, setup_logger


@pytest.fixture(autouse=True)
def _restore_logger():
    """每个用例后把 logger 复位为默认开发配置，避免串扰其他测试。"""
    yield
    setup_logger(log_dir="logs", log_level="ERROR", json_logs=False)


def _read_json_lines(log_dir: Path):
    files = list(log_dir.glob("app_json_*.log"))
    lines = []
    for f in files:
        lines.extend(
            json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()
        )
    return lines


class TestStructuredLogging:
    def test_json_sink_emits_parseable_records(self, tmp_path):
        setup_logger(
            log_dir=str(tmp_path), log_level="DEBUG",
            json_logs=True, environment="staging",
        )
        logger.info("structured-hello")

        records = _read_json_lines(tmp_path)
        assert records, "应产出至少一条 JSON 日志"
        msgs = [r["record"]["message"] for r in records]
        assert "structured-hello" in msgs

    def test_environment_field_present(self, tmp_path):
        setup_logger(
            log_dir=str(tmp_path), log_level="DEBUG",
            json_logs=True, environment="production",
        )
        logger.info("env-check")

        records = _read_json_lines(tmp_path)
        target = [r for r in records if r["record"]["message"] == "env-check"]
        assert target, "应找到 env-check 记录"
        # loguru serialize 把 bind 的 extra 放在 record.extra
        assert target[0]["record"]["extra"].get("environment") == "production"

    def test_json_disabled_by_default_produces_no_json_file(self, tmp_path):
        setup_logger(
            log_dir=str(tmp_path), log_level="DEBUG",
            json_logs=False, environment="development",
        )
        logger.info("plain-only")

        assert _read_json_lines(tmp_path) == []
        # 普通文本日志仍应产出
        assert list(tmp_path.glob("app_*.log")), "文本日志文件应存在"
