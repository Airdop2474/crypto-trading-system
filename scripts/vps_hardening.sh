#!/usr/bin/env bash
# ============================================================
# VPS 安全加固脚本（crypto-trading-system v1.0）
# 用法：在 VPS 上以 root 执行
#   bash scripts/vps_hardening.sh
# 功能：
#   1. iptables 防火墙（开 2222/8000/3000，其余 INPUT DROP）
#   2. fail2ban 防暴力破解（sshd jail）
#   3. SSH 加固（Port 2222 + MaxStartups）
#   4. Docker 加速器（可选，国内网络）
# 幂等：可重复执行，已配置的规则不重复添加
# ============================================================
set -e

echo "=========================================="
echo "  Crypto Trading System - VPS 安全加固"
echo "=========================================="

# ---------- 1. iptables 防火墙 ----------
echo "[1/4] 配置 iptables 防火墙..."

# 检查是否已安装 iptables-persistent
if ! dpkg -l | grep -q iptables-persistent; then
    echo "  安装 iptables-persistent（规则持久化）..."
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq iptables-persistent netfilter-persistent
fi

# 幂等：先检查是否已有我们的标记规则，避免重复添加
if ! iptables -C INPUT -m comment --comment "crypto-trading-system-v1" 2>/dev/null; then
    echo "  添加 iptables 规则..."

    # 允许本地回环
    iptables -A INPUT -i lo -j ACCEPT -m comment --comment "crypto-trading-system-v1"

    # 允许已建立连接
    iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT \
        -m comment --comment "crypto-trading-system-v1"

    # 允许 SSH（端口 2222，防止把自己锁在外面）
    iptables -A INPUT -p tcp --dport 2222 -j ACCEPT \
        -m comment --comment "crypto-trading-system-v1"

    # 允许后端 API（8000）
    iptables -A INPUT -p tcp --dport 8000 -j ACCEPT \
        -m comment --comment "crypto-trading-system-v1"

    # 允许 Grafana（3000）
    iptables -A INPUT -p tcp --dport 3000 -j ACCEPT \
        -m comment --comment "crypto-trading-system-v1"

    # 其余 INPUT 默认 DROP（注意：先确保 SSH 端口已开，否则会断连）
    iptables -P INPUT DROP
    iptables -P FORWARD DROP

    # 持久化规则
    netfilter-persistent save
    echo "  iptables 规则已配置并持久化"
else
    echo "  iptables 规则已存在，跳过"
fi

# ---------- 2. fail2ban 防暴力破解 ----------
echo "[2/4] 配置 fail2ban..."

if ! command -v fail2ban-client &> /dev/null; then
    echo "  安装 fail2ban..."
    apt-get install -y -qq fail2ban
fi

# 配置 sshd jail（幂等：覆盖写入）
cat > /etc/fail2ban/jail.d/sshd.local <<'EOF'
# crypto-trading-system v1.0 - SSH 暴力破解防护
[sshd]
enabled = true
port = 2222
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
EOF

systemctl enable fail2ban
systemctl restart fail2ban
echo "  fail2ban 已配置（sshd jail: maxretry=3, bantime=3600s）"

# ---------- 3. SSH 加固 ----------
echo "[3/4] 配置 SSH 加固..."

SSHD_CONFIG="/etc/ssh/sshd_config"
SSHD_BACKUP="/etc/ssh/sshd_config.bak.v1"

# 备份原配置（仅首次）
if [ ! -f "$SSHD_BACKUP" ]; then
    cp "$SSHD_CONFIG" "$SSHD_BACKUP"
    echo "  已备份原配置到 $SSHD_BACKUP"
fi

# 幂等修改 SSH 配置
update_sshd() {
    local key=$1
    local value=$2
    if grep -qE "^#?\s*${key}\s+" "$SSHD_CONFIG"; then
        sed -i "s/^#*\s*${key}\s.*/${key} ${value}/" "$SSHD_CONFIG"
    else
        echo "${key} ${value}" >> "$SSHD_CONFIG"
    fi
}

update_sshd "Port" "2222"
update_sshd "PermitRootLogin" "yes"
update_sshd "MaxStartups" "100:30:200"
update_sshd "PasswordAuthentication" "yes"
update_sshd "PubkeyAuthentication" "yes"

# 重启 SSH（如果当前不是 2222 端口连接，这次重启不影响已建立的连接）
systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null || true
echo "  SSH 已加固（Port=2222, MaxStartups=100:30:200）"

# ---------- 4. Docker 加速器（国内网络，可选）----------
echo "[4/4] 检查 Docker 加速器..."

DAEMON_JSON="/etc/docker/daemon.json"
if [ ! -f "$DAEMON_JSON" ] || ! grep -q "registry-mirrors" "$DAEMON_JSON"; then
    echo "  配置 Docker 加速器（国内镜像源）..."
    mkdir -p /etc/docker
    cat > "$DAEMON_JSON" <<'EOF'
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me"
  ],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
    systemctl daemon-reload
    systemctl restart docker
    echo "  Docker 加速器已配置"
else
    echo "  Docker 加速器已存在，跳过"
fi

echo ""
echo "=========================================="
echo "  VPS 加固完成"
echo "=========================================="
echo "  iptables:  仅放行 2222/8000/3000"
echo "  fail2ban:  sshd jail 已启用"
echo "  SSH:       Port=2222, MaxStartups=100:30:200"
echo "  Docker:    加速器 + 日志轮转已配置"
echo ""
echo "  验证命令:"
echo "    iptables -L INPUT -n --line-numbers"
echo "    fail2ban-client status sshd"
echo "    ssh -p 2222 root@<VPS_IP>"
echo "=========================================="
