# code-style

Code style and convention checker.

## Description

Verifies code follows project conventions: formatting (black, isort), type hints, docstrings, naming conventions. Only scans changed files to minimize token usage.

## When to Use

- Before committing code
- After implementing features
- Called by /workflow-control for verification

**Trigger:** "check code style", "format code", "lint check"

## Instructions

1. Get changed files from git diff or git status
2. In this repo, prefer `python scripts/check_code_style.py`
3. Run black --check, isort --check, flake8
4. Check for missing docstrings
5. Verify naming conventions
6. Report violations with fix commands

## Examples

User: "check code style"
Assistant: [Runs checks, reports: "src/strategy/rsi.py:23 - missing docstring", provides: "black src/strategy/rsi.py"]
