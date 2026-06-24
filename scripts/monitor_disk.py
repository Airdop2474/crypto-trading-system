#!/usr/bin/env python3
"""
磁盘监控 — 检查磁盘使用率，超过阈值发 Telegram 告警

用法（加到 crontab，每 10 分钟执行）：
    */10 * * * * /usr/bin/python3 /opt/crypto-trading-system/scripts/monitor_disk.py

阈值可通过环境变量 DISK_ALERT_THRESHOLD 配置，默认 85%
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.telegram_notifier import notifier
from src.utils.logger import logger


THRESHOLD = float(os.getenv("DISK_ALERT_THRESHOLD", "85"))


def check_disk() -> tuple[float, float, str]:
    """检查磁盘使用率

    返回：(使用率百分比, 总容量GB, 挂载点)
    """
    # 检查项目所在分区
    path = str(PROJECT_ROOT)
    total, used, free = shutil.disk_usage(path)
    usage_pct = (used / total) * 100
    total_gb = total / (1024 ** 3)
    return usage_pct, total_gb, path


def check_docker_disk() -> float:
    """检查 Docker 占用的磁盘空间（近似）"""
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "system", "df", "--format", "{{.Size}}"],
            capture_output=True, text=True, timeout=10,
        )
        # 粗略解析
        lines = result.stdout.strip().split("\n")
        total_str = lines[0] if lines else "0B"
        return 0.0  # 只做参考，不精确
    except Exception:
        return 0.0


def main():
    usage_pct, total_gb, path = check_disk()

    if usage_pct >= THRESHOLD:
        alert_text = (
            f"磁盘空间告警!\n\n"
            f"• 使用率: {usage_pct:.1f}% (阈值: {THRESHOLD:.0f}%)\n"
            f"• 总容量: {total_gb:.1f} GB\n"
            f"• 路径: {path}\n"
            f"• 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"建议操作:\n"
            f"  docker system prune -f\n"
            f"  rm -rf backups/db_*.sql.gz (保留最新)"
        )
        logger.warning(alert_text)
        notifier.send_warning_sync(alert_text)
        print(f"[WARNING] 磁盘使用率 {usage_pct:.1f}% >= {THRESHOLD:.0f}%")
        sys.exit(1)
    else:
        logger.info(f"磁盘使用率正常: {usage_pct:.1f}% / {THRESHOLD:.0f}%")
        print(f"[OK] 磁盘使用率 {usage_pct:.1f}% (总 {total_gb:.1f}GB)")
        sys.exit(0)


if __name__ == "__main__":
    main()
