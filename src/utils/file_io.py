"""文件 IO 工具：原子写入、安全读取。

原子写入通过"先写临时文件再 os.replace"实现，保证崩溃时不会留下半截文件。
所有 JSON 持久化（策略配置、策略状态、模式状态等）都应使用这里的函数。
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.utils.logger import logger


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """原子写入文本文件。

    流程：在同一目录创建临时文件 → 写入 → fsync → os.replace 覆盖目标。
    os.replace 在同一文件系统上是原子的，崩溃时要么旧文件完整、要么新文件完整。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 在同目录建临时文件，保证 os.replace 是同文件系统操作
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except Exception:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, data: Any, indent: int = 2, ensure_ascii: bool = False) -> None:
    """原子写入 JSON 文件。

    参数：
        path: 目标文件路径
        data: 可 JSON 序列化的对象
        indent: 缩进（默认 2）
        ensure_ascii: 是否转义非 ASCII 字符（默认 False，保留中文）
    """
    content = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
    atomic_write_text(path, content)
    logger.debug(f"原子写入 JSON: {path}")


def safe_read_json(path: Path, default: Any = None) -> Any:
    """安全读取 JSON 文件，失败时返回 default 并记录 warning。

    与 atomic_write_json 配对使用。文件不存在返回 default；
    JSON 解析失败也返回 default（不会抛异常打断调用方）。
    """
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"读取 JSON 失败 {path}: {e}")
        return default


__all__ = ["atomic_write_text", "atomic_write_json", "safe_read_json"]
