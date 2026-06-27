#!/usr/bin/env bash
# ============================================================
# VPS 一键部署脚本
# 用法：在 VPS 上执行 bash deploy.sh
# ============================================================
set -e

echo "=========================================="
echo "  Crypto Trading System - VPS 部署"
echo "=========================================="

# 1. 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "[1/6] 安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
else
    echo "[1/6] Docker 已安装: $(docker --version)"
fi

# 检查 Docker Compose
if ! docker compose version &> /dev/null; then
    echo "安装 Docker Compose 插件..."
    apt-get update && apt-get install -y docker-compose-plugin
fi

# 2. 克隆代码
REPO_URL="https://github.com/Airdop2474/crypto-trading-system.git"
INSTALL_DIR="/root/crypto-trading-system"

if [ -d "$INSTALL_DIR" ]; then
    echo "[2/6] 更新已有代码..."
    cd "$INSTALL_DIR"
    git pull origin master
else
    echo "[2/6] 克隆代码到 $INSTALL_DIR ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. 创建 .env 文件
if [ ! -f .env ]; then
    echo "[3/6] 创建 .env 配置文件..."
    cp .env.example .env

    # 生成随机密码
    PG_PASS=$(openssl rand -hex 16)
    REDIS_PASS=$(openssl rand -hex 16)
    GRAFANA_PASS=$(openssl rand -hex 16)
    API_TOKEN=$(openssl rand -hex 16)

    sed -i "s/CHANGE_ME_NOW/$PG_PASS/g" .env
    sed -i "s/your_secure_password/$PG_PASS/g" .env
    sed -i "s/change-me-to-a-random-token/$API_TOKEN/g" .env
    sed -i "s|redis://:CHANGE_ME_NOW@localhost:6379/0|redis://:$REDIS_PASS@localhost:6379/0|g" .env

    echo ""
    echo "  ==========================================="
    echo "  .env 已生成，请编辑填入以下内容："
    echo "  ==========================================="
    echo "  nano $INSTALL_DIR/.env"
    echo ""
    echo "  必填项："
    echo "    BINANCE_API_KEY    - Binance testnet API key"
    echo "    BINANCE_SECRET     - Binance testnet secret"
    echo "    API_TOKEN          - 已自动生成: $API_TOKEN"
    echo ""
    echo "  填好后重新运行: bash deploy.sh"
    echo "  ==========================================="
    exit 0
else
    echo "[3/6] .env 已存在"
fi

# 4. 构建并启动服务
echo "[4/6] 构建 Docker 镜像并启动服务..."
docker compose build
docker compose up -d

# 5. 等待服务就绪
echo "[5/6] 等待服务启动..."
sleep 10
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "  后端服务已就绪"
        break
    fi
    sleep 2
    if [ $i -eq 30 ]; then
        echo "  [警告] 后端服务未就绪，检查日志: docker compose logs trading_system"
    fi
done

# 6. 构建前端（可选）
echo "[6/6] 前端部署说明："
echo "  前端需单独构建部署，推荐方式："
echo "  1. 本地构建: cd frontend && npm install && npm run build"
echo "  2. 用 nginx 托管 frontend/.next/ 静态文件"
echo "  3. 或用 Vercel/Cloudflare Pages 托管"
echo ""
echo "  前端 .env.local 需配置:"
echo "    NEXT_PUBLIC_API_BASE=http://<VPS_IP>:8000"
echo "    NEXT_PUBLIC_API_TOKEN=<与 .env 中 API_TOKEN 一致>"

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo "  后端 API:  http://$(hostname -I | awk '{print $1}'):8000"
echo "  Grafana:   http://$(hostname -I | awk '{print $1}'):3000"
echo ""
echo "  常用命令:"
echo "    查看状态: docker compose ps"
echo "    查看日志: docker compose logs -f trading_system"
echo "    重启服务: docker compose restart"
echo "    停止服务: docker compose down"
echo "=========================================="
