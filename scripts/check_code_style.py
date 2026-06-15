#!/usr/bin/env python3
"""Run project code-style checks on changed files or the whole tree."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_DIRS = ("src", "tests", "scripts")
GIT_CMD = ["git", "-c", "safe.directory=*"]


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command from the project root and capture text output."""
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def is_python_file(path_str: str) -> bool:
    """Return True when the path is a Python file inside the project tree."""
    path = Path(path_str)
    return path.suffix == ".py" and any(part in PYTHON_DIRS for part in path.parts)


def get_changed_python_files() -> list[Path]:
    """Collect changed Python files from git status, with a filesystem fallback."""
    status = run_command(GIT_CMD + ["status", "--porcelain"])
    if status.returncode == 0:
        files: list[Path] = []
        for line in status.stdout.splitlines():
            if len(line) < 4:
                continue
            path_str = line[3:].strip()
            if " -> " in path_str:
                path_str = path_str.split(" -> ", maxsplit=1)[1]
            if is_python_file(path_str):
                files.append(Path(path_str))
        deduped = sorted(set(files))
        if deduped:
            return deduped

    files: list[Path] = []
    for directory in PYTHON_DIRS:
        full_dir = PROJECT_ROOT / directory
        if full_dir.exists():
            files.extend(path.relative_to(PROJECT_ROOT) for path in full_dir.rglob("*.py"))
    return sorted(set(files))


def print_section(title: str) -> None:
    """Print a simple section header."""
    print(f"\n[{title}]")


def run_check(label: str, command: list[str]) -> int:
    """Run a style check and print its output."""
    print_section(label)
    print(" ".join(command))
    result = run_command(command)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    if result.returncode == 0:
        print("[OK]")
    else:
        print(f"[FAIL] exit code {result.returncode}")
    return result.returncode


def main() -> int:
    """Run code-style checks."""
    check_all = "--all" in sys.argv[1:]

    if check_all:
        python_files: list[Path] = []
        for directory in PYTHON_DIRS:
            full_dir = PROJECT_ROOT / directory
            if full_dir.exists():
                python_files.extend(
                    path.relative_to(PROJECT_ROOT) for path in full_dir.rglob("*.py")
                )
        python_files = sorted(set(python_files))
    else:
        python_files = get_changed_python_files()

    if not python_files:
        print("No Python files found to check.")
        return 0

    src_files = [path for path in python_files if path.parts and path.parts[0] == "src"]

    print("Code style target files:")
    for path in python_files:
        print(f"  - {path.as_posix()}")

    file_args = [path.as_posix() for path in python_files]
    exit_codes = [
        run_check("black", ["black", "--check", *file_args]),
        run_check("isort", ["isort", "--check-only", *file_args]),
        run_check("flake8", ["flake8", "--max-line-length=100", *file_args]),
    ]

    if src_files:
        exit_codes.append(
            run_check(
                "mypy",
                ["mypy", *(path.as_posix() for path in src_files), "--ignore-missing-imports"],
            )
        )
    else:
        print_section("mypy")
        print("No src/ files selected; skipping mypy.")

    return 0 if all(code == 0 for code in exit_codes) else 1


if __name__ == "__main__":
    sys.exit(main())
