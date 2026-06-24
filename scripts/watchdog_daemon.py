#!/usr/bin/env python3
"""
daemon 看门狗 — 独立于 daemon 运行，定期检查 daemon 是否存活

用法（加到 crontab，每 5 分钟执行）：
    */5 * * * * /usr/bin/python3 /opt/crypto-trading-system/scripts/watchdog_daemon.py

功能：
1. 检查 paper_daemon 容器是否在运行
2. 检查 daemon state 文件是否在更新（超过 10 分钟未更新 = 假死）
3. 异常时通过 Telegram 发送 CRITICAL 通知
4. 正常时不发通知（避免刷屏）
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta

# 确保能导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.telegram_notifier import notifier
from src.utils.logger import logger


# 配置
DAEMON_CONTAINER = "crypto_trading_paper_daemon"
STATE_DIR = PROJECT_ROOT / "data" / "mode_states"
STALE_THRESHOLD_MINUTES = 10  # state 文件超过 10 分钟未更新 = 假死


def check_container_running() -> bool:
    """检查 daemon 容器是否在运行"""
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", DAEMON_CONTAINER],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() == "true"
    except Exception as e:
        logger.error(f"检查容器状态失败: {e}")
        return False


def check_state_fresh() -> tuple[bool, str]:
    """检查 daemon state 文件是否在更新

    返回：(是否新鲜, 描述信息)
    """
    if not STATE_DIR.exists():
        return False, f"state 目录不存在: {STATE_DIR}"

    state_files = list(STATE_DIR.glob("*.json"))
    if not state_files:
        return False, "无 state 文件"

    now = datetime.now()
    stale_files = []
    newest_time = None

    for f in state_files:
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if newest_time is None or mtime > newest_time:
                newest_time = mtime

            age_minutes = (now - mtime).total_seconds() / 60
            if age_minutes > STALE_THRESHOLD_MINUTES:
                stale_files.append(f"{f.name} ({age_minutes:.0f}分钟前)")
        except Exception:
            pass

    if stale_files:
        return False, f"state 文件过期: {', '.join(stale_files)}"

    if newest_time:
        age = (now - newest_time).total_seconds() / 60
        return True, f"最新 state 更新于 {age:.1f} 分钟前"

    return True, "state 正常"


def main():
    """主检查逻辑"""
    logger.info("watchdog: 开始检查 daemon 状态...")

    issues = []

    # 1. 检查容器
    if not check_container_running():
        issues.append(f"容器 {DAEMON_CONTAINER} 未运行或不存在")

    # 2. 检查 state 文件新鲜度
    fresh, desc = check_state_fresh()
    if not fresh:
        issues.append(desc)

    # 3. 发送告警
    if issues:
        alert_text = "daemon 异常!\n\n" + "\n".join(f"• {i}" for i in issues)
        alert_text += f"\n\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        logger.error(alert_text)
        notifier.send_critical_sync(alert_text)
        print(f"[ALERT] {alert_text}")
        sys.exit(1)
    else:
        logger.info(f"watchdog: daemon 正常 ({desc})")
        print(f"[OK] daemon 正常 ({desc})")
        sys.exit(0)


if __name__ == "__main__":
    main()
