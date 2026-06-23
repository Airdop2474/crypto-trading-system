#!/usr/bin/env bash
# ============================================================
# Crypto Trading System - 交互式一键启动
# 在 VPS 上运行：bash start.sh
# ============================================================
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ============================================================
# 工具函数
# ============================================================
print_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════╗"
    echo "║       Crypto Trading System - 交互式启动              ║"
    echo "╚═══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "\n${BLUE}━━━ $1 ━━━${NC}"
}

print_ok() {
    echo -e "${GREEN}  ✓ $1${NC}"
}

print_warn() {
    echo -e "${YELLOW}  ⚠ $1${NC}"
}

print_err() {
    echo -e "${RED}  ✗ $1${NC}"
}

# 读取输入（带默认值）
# 用法: read_input "提示信息" "默认值"
read_input() {
    local prompt="$1"
    local default="$2"
    local input
    if [ -n "$default" ]; then
        read -p "$(echo -e "  ${CYAN}${prompt}${NC} [${default}]: ")" input
        echo "${input:-$default}"
    else
        read -p "$(echo -e "  ${CYAN}${prompt}${NC}: ")" input
        echo "$input"
    fi
}

# 读取密码（不回显）
read_password() {
    local prompt="$1"
    local input
    read -s -p "$(echo -e "  ${CYAN}${prompt}${NC}: ")" input
    echo
    echo "$input"
}

# 读取 Y/N
read_yn() {
    local prompt="$1"
    local default="${2:-y}"
    local input
    if [ "$default" = "y" ]; then
        read -p "$(echo -e "  ${CYAN}${prompt}${NC} [Y/n]: ")" input
        case "${input:-Y}" in
            [Yy]*) return 0 ;;
            *) return 1 ;;
        esac
    else
        read -p "$(echo -e "  ${CYAN}${prompt}${NC} [y/N]: ")" input
        case "${input:-N}" in
            [Yy]*) return 0 ;;
            *) return 1 ;;
        esac
    fi
}

# ============================================================
# 主流程
# ============================================================
print_banner

# ---- Step 0: 环境检查 ----
print_step "Step 0: 环境检查"

# 检查 Docker
if ! command -v docker &> /dev/null; then
    print_err "Docker 未安装"
    echo -e "  请先运行: ${YELLOW}bash deploy.sh${NC}"
    exit 1
fi
print_ok "Docker: $(docker --version)"

# 检查 .env
if [ ! -f .env ]; then
    print_err ".env 文件不存在"
    echo -e "  请先运行: ${YELLOW}bash deploy.sh${NC}"
    exit 1
fi
print_ok ".env 配置文件存在"

# 检查后端是否运行
check_backend() {
    curl -sf http://localhost:8000/health > /dev/null 2>&1
}

if ! check_backend; then
    print_warn "后端服务未运行，正在启动..."
    docker compose up -d
    echo -n "  等待后端启动"
    for i in $(seq 1 30); do
        if check_backend; then
            echo ""
            print_ok "后端服务已启动"
            break
        fi
        echo -n "."
        sleep 2
        if [ $i -eq 30 ]; then
            echo ""
            print_err "后端启动超时，请检查: docker compose logs trading_system"
            exit 1
        fi
    done
else
    print_ok "后端服务运行中"
fi

# 读取 API_TOKEN
API_TOKEN=$(grep -E "^API_TOKEN=" .env | cut -d'=' -f2-)
if [ -z "$API_TOKEN" ]; then
    print_err "无法读取 API_TOKEN，请检查 .env"
    exit 1
fi

# API 调用函数
api_get() {
    local path="$1"
    curl -sf -H "X-API-Token: $API_TOKEN" "http://localhost:8000${path}" 2>/dev/null
}

api_post() {
    local path="$1"
    local data="$2"
    curl -sf -X POST -H "X-API-Token: $API_TOKEN" \
         -H "Content-Type: application/json" \
         -d "$data" \
         "http://localhost:8000${path}" 2>/dev/null
}

# ---- Step 1: 选择运行模式 ----
print_step "Step 1: 选择运行模式"

echo -e "  ${CYAN}1)${NC} 实时纸盘 (live_paper)    — 实时行情，模拟撮合"
echo -e "  ${CYAN}2)${NC} 回放纸盘 (replay_paper)  — 历史数据回放"
echo -e "  ${CYAN}3)${NC} Testnet 实盘 (testnet_live) — Binance testnet 真实下单"

mode_choice=$(read_input "选择模式 (1-3)" "1")
case $mode_choice in
    1) MODE="live_paper" ;;
    2) MODE="replay_paper" ;;
    3) MODE="testnet_live" ;;
    *) print_err "无效选择"; exit 1 ;;
esac
print_ok "已选模式: $MODE"

# 检查当前模式状态
current_status=$(api_get "/modes/${MODE}/status" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")
if [ "$current_status" = "running" ]; then
    print_warn "模式 ${MODE} 当前正在运行"
    if read_yn "是否先停止当前运行？" "y"; then
        echo -e "  正在停止..."
        api_post "/modes/${MODE}/stop" "{}" > /dev/null 2>&1 || true
        sleep 3
        print_ok "已停止"
    else
        print_warn "跳过启动（模式已在运行）"
        exit 0
    fi
fi

# ---- Step 2: 交易参数 ----
print_step "Step 2: 交易参数配置"

SYMBOL=$(read_input "交易对" "BTC/USDT")

echo -e "  可选周期: 1m, 5m, 15m, 1h, 4h, 1d"
TIMEFRAME=$(read_input "K线周期" "4h")

DAYS=$(read_input "运行天数 (1-365)" "60")

INITIAL=$(read_input "初始资金 (USDT)" "10000")

if [ "$MODE" = "live_paper" ] || [ "$MODE" = "testnet_live" ]; then
    POLL=$(read_input "轮询间隔 (秒, 10-600)" "60")
else
    POLL=60
fi

# ---- Step 3: 策略选择 ----
print_step "Step 3: 策略选择"

ALL_STRATEGIES=("grid" "rsi" "ma" "buyhold" "donchian" "structure" "supertrend" "reversal" "priceaction" "bollinger" "macd" "composite")
STRATEGY_LABELS=("网格" "RSI动量" "均线" "买入持有" "唐奇安" "市场结构" "超级趋势" "关键反转" "价格行为" "布林带" "MACD" "综合趋势")

echo -e "  ${CYAN}0)${NC} 全部策略 (12个)"
for i in "${!ALL_STRATEGIES[@]}"; do
    num=$((i + 1))
    echo -e "  ${CYAN}${num})${NC} ${ALL_STRATEGIES[$i]} (${STRATEGY_LABELS[$i]})"
done

strat_choice=$(read_input "选择策略 (逗号分隔，如 1,3,5 或 0=全部)" "0")

if [ "$strat_choice" = "0" ]; then
    SELECTED_STRATS=("${ALL_STRATEGIES[@]}")
else
    SELECTED_STRATS=()
    IFS=',' read -ra indices <<< "$strat_choice"
    for idx in "${indices[@]}"; do
        idx=$(echo "$idx" | xargs) # trim
        if [[ "$idx" =~ ^[0-9]+$ ]] && [ "$idx" -ge 1 ] && [ "$idx" -le 12 ]; then
            SELECTED_STRATS+=("${ALL_STRATEGIES[$((idx-1))]}")
        else
            print_warn "忽略无效选择: $idx"
        fi
    done
fi

if [ ${#SELECTED_STRATS[@]} -eq 0 ]; then
    print_err "未选择任何策略"
    exit 1
fi

print_ok "已选策略: ${SELECTED_STRATS[*]}"

# ---- Step 4: 回放模式额外参数 ----
MARKET_TYPE="oscillating"
REPLAY_CSV=""
if [ "$MODE" = "replay_paper" ]; then
    print_step "Step 4: 回放参数"
    echo -e "  市场类型:"
    echo -e "    ${CYAN}1)${NC} oscillating (震荡)"
    echo -e "    ${CYAN}2)${NC} trending (趋势)"
    echo -e "    ${CYAN}3)${NC} random (随机)"
    echo -e "    ${CYAN}4)${NC} bullish (牛市)"
    echo -e "    ${CYAN}5)${NC} bearish (熊市)"
    mt_choice=$(read_input "选择市场类型 (1-5)" "1")
    case $mt_choice in
        1) MARKET_TYPE="oscillating" ;;
        2) MARKET_TYPE="trending" ;;
        3) MARKET_TYPE="random" ;;
        4) MARKET_TYPE="bullish" ;;
        5) MARKET_TYPE="bearish" ;;
        *) MARKET_TYPE="oscillating" ;;
    esac
    REPLAY_CSV="generate"
fi

# ---- Step 5: 确认 ----
print_step "Step 5: 确认配置"

echo -e "  ${YELLOW}┌─────────────────────────────────────────┐${NC}"
echo -e "  ${YELLOW}│ 模式:     ${NC}$MODE"
echo -e "  ${YELLOW}│ 交易对:   ${NC}$SYMBOL"
echo -e "  ${YELLOW}│ 周期:     ${NC}$TIMEFRAME"
echo -e "  ${YELLOW}│ 天数:     ${NC}$DAYS"
echo -e "  ${YELLOW}│ 初始资金: ${NC}$INITIAL USDT"
if [ "$MODE" != "replay_paper" ]; then
    echo -e "  ${YELLOW}│ 轮询:     ${NC}${POLL}s"
fi
echo -e "  ${YELLOW}│ 策略:     ${NC}${SELECTED_STRATS[*]}"
if [ "$MODE" = "replay_paper" ]; then
    echo -e "  ${YELLOW}│ 市场类型: ${NC}$MARKET_TYPE"
fi
echo -e "  ${YELLOW}└─────────────────────────────────────────┘${NC}"

if ! read_yn "确认启动？" "y"; then
    echo -e "  ${YELLOW}已取消${NC}"
    exit 0
fi

# ---- Step 6: 启动 ----
print_step "Step 6: 启动中..."

# 构造 JSON
STRATS_JSON=$(printf '%s\n' "${SELECTED_STRATS[@]}" | python3 -c "
import sys, json
strats = [line.strip() for line in sys.stdin if line.strip()]
print(json.dumps(strats))
")

PAYLOAD=$(python3 -c "
import json
data = {
    'symbol': '$SYMBOL',
    'timeframe': '$TIMEFRAME',
    'days': int('$DAYS'),
    'initialCapital': float('$INITIAL'),
    'pollSeconds': int('$POLL'),
    'fresh': True,
    'strategies': $STRATS_JSON,
    'marketType': '$MARKET_TYPE',
}
if '$REPLAY_CSV':
    data['replayCsv'] = '$REPLAY_CSV'
print(json.dumps(data))
")

echo -e "  正在启动 ${MODE}..."

RESULT=$(api_post "/modes/${MODE}/start" "$PAYLOAD" 2>&1)

if echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if 'status' in d else 1)" 2>/dev/null; then
    PIDS=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); pids=d.get('pid',[]); print(','.join(str(p) for p in pids) if isinstance(pids,list) else pids)" 2>/dev/null || echo "?")
    print_ok "启动成功！"
    echo -e "  模式: ${GREEN}$MODE${NC}"
    echo -e "  PID:  ${GREEN}$PIDS${NC}"
    echo -e "  策略数: ${GREEN}${#SELECTED_STRATS[@]}${NC}"
else
    print_err "启动失败"
    echo -e "  响应: $RESULT"
    exit 1
fi

# ---- Step 7: 后续提示 ----
print_step "完成"

echo -e "  ${GREEN}系统已启动，正在后台运行${NC}"
echo ""
echo -e "  ${CYAN}常用命令:${NC}"
echo -e "    查看状态:   ${YELLOW}bash start.sh status${NC}"
echo -e "    查看日志:   ${YELLOW}docker compose logs -f trading_system${NC}"
echo -e "    停止运行:   ${YELLOW}bash start.sh stop${NC}"
echo -e "    重新启动:   ${YELLOW}bash start.sh${NC}"
echo ""
echo -e "  ${CYAN}访问地址:${NC}"
VPS_IP=$(hostname -I | awk '{print $1}')
echo -e "    后端 API:  ${YELLOW}http://${VPS_IP}:8000${NC}"
echo -e "    Grafana:   ${YELLOW}http://${VPS_IP}:3000${NC}"

# ============================================================
# 子命令处理
# ============================================================
case "${1:-}" in
    status)
        echo -e "\n${BLUE}━━━ 运行状态 ━━━${NC}"
        api_get "/modes" | python3 -c "
import sys, json
modes = json.load(sys.stdin)
for m in modes:
    status = m.get('status', '?')
    pids = m.get('pid', [])
    pid_str = ','.join(str(p) for p in pids) if isinstance(pids, list) else (str(pids) if pids else '-')
    symbol = '─'
    if status == 'running':
        symbol = '●'
    elif status == 'idle':
        symbol = '○'
    elif status == 'error':
        symbol = '✗'
    print(f'  {symbol} {m[\"mode\"]:15s} {status:8s} PID: {pid_str}')
" 2>/dev/null || echo "  无法获取状态"
        ;;
    stop)
        echo -e "\n${BLUE}━━━ 停止所有运行模式 ━━━${NC}"
        for mode in live_paper replay_paper testnet_live; do
            status=$(api_get "/modes/${mode}/status" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
            if [ "$status" = "running" ]; then
                echo -e "  停止 ${mode}..."
                api_post "/modes/${mode}/stop" "{}" > /dev/null 2>&1 || true
                print_ok "${mode} 已停止"
            fi
        done
        echo -e "  ${GREEN}完成${NC}"
        ;;
esac
