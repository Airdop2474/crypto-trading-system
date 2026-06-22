#!/usr/bin/env python3
"""
设置 .env 文件中的 LLM 配置。
由 start.bat 调用，确保 LLM_* 变量存在并更新。

用法: python scripts/set_llm_env.py --provider openai --key sk-xxx --url https://... --model deepseek-chat
"""

import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Update LLM config in .env")
    parser.add_argument("--provider", default="", help="LLM provider: openai / anthropic / local")
    parser.add_argument("--key", default="", help="API key")
    parser.add_argument("--url", default="", help="Base URL (empty for default)")
    parser.add_argument("--model", default="", help="Model name (empty for default)")
    args = parser.parse_args()

    env_path = Path(".env")
    if not env_path.exists():
        print("  [X] .env \u6587\u4ef6\u4e0d\u5b58\u5728", file=sys.stderr)
        sys.exit(1)

    content = env_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    # Variables to set
    updates = {
        "LLM_PROVIDER": args.provider,
        "LLM_API_KEY": args.key,
        "LLM_BASE_URL": args.url,
        "LLM_MODEL": args.model,
    }

    # Track which vars already exist in the file
    found = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        for var in updates:
            if stripped.startswith(f"{var}=") or stripped == var:
                found[var] = i

    # Update existing lines or append new ones
    for var, value in updates.items():
        if var in found:
            lines[found[var]] = f"{var}={value}"
        else:
            # Variable doesn't exist, append it
            lines.append(f"{var}={value}")

    # Write back
    result = "\n".join(lines)
    env_path.write_text(result, encoding="utf-8")

    # Print summary
    parts = []
    if args.provider:
        parts.append(f"provider={args.provider}")
    if args.key:
        masked = args.key[:6] + "..." + args.key[-4:] if len(args.key) > 10 else "***"
        parts.append(f"key={masked}")
    if args.url:
        parts.append(f"url={args.url}")
    if args.model:
        parts.append(f"model={args.model}")
    summary = ", ".join(parts) if parts else "(\u7a7a\u503c)"
    print(f"  \u5df2\u5199\u5165 .env: {summary}")


if __name__ == "__main__":
    main()
