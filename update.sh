#!/usr/bin/env bash
# ============================================================
# 一键更新脚本 — git pull + docker compose up -d --build
# 用法：bash update.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  Crypto Trading System - 一键更新"
echo "=========================================="

# 1. 拉取最新代码
echo "[1/4] 拉取最新代码..."
git pull origin master
echo ""

# 2. 重新构建并启动
echo "[2/4] 重新构建 Docker 镜像..."
docker compose build --parallel 2>&1 | tail -5
echo ""

# 3. 重启服务
echo "[3/4] 重启服务..."
docker compose up -d
echo ""

# 4. 检查状态
echo "[4/4] 检查服务状态..."
sleep 5
docker compose ps

echo ""
echo "=========================================="
echo "  更新完成！"
echo "=========================================="
echo "  查看日志: docker compose logs -f trading_system"
echo "=========================================="
