#!/usr/bin/env bash
# ============================================================
# 数据库自动备份脚本
# 用法：加到 crontab 每日执行
#   0 3 * * * /root/crypto-trading-system/scripts/backup_db.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_DIR/backups"
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

# 从 .env 读取数据库配置
if [ -f "$PROJECT_DIR/.env" ]; then
    source "$PROJECT_DIR/.env"
fi

DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${POSTGRES_DB:-crypto_trading}"
DB_PASSWORD="${POSTGRES_PASSWORD:-}"
DB_CONTAINER="crypto_trading_db"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/db_${TIMESTAMP}.sql.gz"

echo "[$(date)] 开始备份 $DB_NAME ..."

# 通过 docker exec 执行 pg_dump，压缩输出
docker exec "$DB_CONTAINER" \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl 2>/dev/null | \
    gzip > "$BACKUP_FILE"

if [ -s "$BACKUP_FILE" ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] 备份成功: $BACKUP_FILE ($SIZE)"
else
    echo "[$(date)] 备份失败: 文件为空" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

# 清理超过保留期的备份
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +$RETENTION_DAYS -delete
echo "[$(date)] 已清理 ${RETENTION_DAYS} 天前的旧备份"

# 统计当前备份数量
COUNT=$(find "$BACKUP_DIR" -name "db_*.sql.gz" | wc -l)
echo "[$(date)] 当前共 $COUNT 个备份文件"
