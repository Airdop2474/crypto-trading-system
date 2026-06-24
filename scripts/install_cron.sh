#!/usr/bin/env bash
# ============================================================
# VPS cron 任务安装脚本
# 安装看门狗、磁盘监控、数据库备份的定时任务
# 用法：bash scripts/install_cron.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${PROJECT_DIR}/.venv/bin/python3"

# 如果没有 venv，用系统 python3
if [ ! -f "$PYTHON" ]; then
    PYTHON=$(which python3)
fi

echo "=========================================="
echo "  安装 cron 定时任务"
echo "=========================================="
echo "  Python: $PYTHON"
echo "  项目目录: $PROJECT_DIR"
echo ""

# 生成 cron 内容
CRON_CONTENT="# Crypto Trading System - 自动化任务
# daemon 看门狗（每 5 分钟）
*/5 * * * * $PYTHON $PROJECT_DIR/scripts/watchdog_daemon.py >> $PROJECT_DIR/logs/watchdog.log 2>&1

# 磁盘监控（每 10 分钟）
*/10 * * * * $PYTHON $PROJECT_DIR/scripts/monitor_disk.py >> $PROJECT_DIR/logs/disk_monitor.log 2>&1

# 数据库备份（每天凌晨 3 点）
0 3 * * * bash $PROJECT_DIR/scripts/backup_db.sh >> $PROJECT_DIR/logs/backup.log 2>&1
"

# 写入临时文件
TEMP_FILE=$(mktemp)
echo "$CRON_CONTENT" > "$TEMP_FILE"

# 合并到现有 crontab（避免重复）
if crontab -l 2>/dev/null | grep -q "watchdog_daemon"; then
    echo "  cron 任务已存在，跳过安装"
    rm -f "$TEMP_FILE"
else
    (crontab -l 2>/dev/null; cat "$TEMP_FILE") | crontab -
    echo "  cron 任务已安装"
    rm -f "$TEMP_FILE"
fi

echo ""
echo "  当前 cron 任务:"
crontab -l 2>/dev/null | grep -A1 "Crypto Trading"

echo ""
echo "=========================================="
echo "  安装完成！"
echo "=========================================="
echo "  查看日志:"
echo "    tail -f $PROJECT_DIR/logs/watchdog.log"
echo "    tail -f $PROJECT_DIR/logs/disk_monitor.log"
echo "    tail -f $PROJECT_DIR/logs/backup.log"
echo ""
echo "  手动测试:"
echo "    $PYTHON $PROJECT_DIR/scripts/watchdog_daemon.py"
echo "    $PYTHON $PROJECT_DIR/scripts/monitor_disk.py"
echo "    bash $PROJECT_DIR/scripts/backup_db.sh"
echo "=========================================="
