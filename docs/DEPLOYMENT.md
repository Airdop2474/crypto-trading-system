# 部署指南

**文档版本：** v1.0  
**创建日期：** 2026-06-20  
**状态：** ✅ 基于 `install.cmd` / `docker-compose.yml` / `Dockerfile` 生成  
**适用阶段：** Paper Trading (Phase 4-5)  

---

## 1. 前置要求

| 组件 | 最低版本 | 用途 | 安装链接 |
|------|----------|------|----------|
| **Python** | 3.13+ | 核心交易系统、策略引擎、API 服务 | https://python.org |
| **Node.js** | 18+ | 前端仪表盘 (Next.js) | https://nodejs.org |
| **Docker Desktop** | 24+ | 基础设施服务 (TimescaleDB + Redis + Grafana) | https://docker.com |
| **Git** | 2.x | 版本管理（可选） | https://git-scm.com |

### 验证安装

```bash
python --version    # 应显示 Python 3.13.x 或更高
node --version      # 应显示 v18.x 或更高
docker --version    # 应显示 Docker version 24.x 或更高
```

---

## 2. 环境配置

### 2.1 克隆项目

```bash
git clone <repository-url> crypto-trading-system
cd crypto-trading-system
```

### 2.2 创建 .env 文件

```bash
# 从模板复制
cp .env.example .env

# 编辑 .env，至少填入以下值：
#   POSTGRES_PASSWORD=changeme
#   REDIS_PASSWORD=changeme
#   GRAFANA_ADMIN_PASSWORD=admin
#   TIMESCALE_PASSWORD=changeme
#   API_TOKEN=<your-random-token>
```

### 2.3 创建前端环境变量

```bash
# 从模板复制
cp frontend/.env.local.example frontend/.env.local

# 默认值即可使用（后端 localhost:8000）
# 如需修改：编辑 NEXT_PUBLIC_API_BASE 和 NEXT_PUBLIC_API_TOKEN
```

---

## 3. 快速开始（一键安装）

### Windows

```cmd
install.cmd
```

此脚本自动执行：
1. 检查 Python / Node.js / Docker
2. 从 `.env.example` 创建 `.env`（如不存在）
3. 安装 Python 依赖 (`pip install -r requirements.txt`)
4. 安装前端依赖 (`npm install --legacy-peer-deps`)
5. 启动 Docker 基础设施 (`docker compose up -d`)
6. 在独立窗口启动后端 (port 8000) 和前端 (port 3001)
7. 等待前端就绪后打开浏览器

### macOS / Linux

`install.cmd` 使用 Windows 批处理语法，需手动执行以下步骤：

```bash
# 1. 创建 .env
cp .env.example .env
# 编辑 .env 填入密码和 API_TOKEN

# 2. 安装依赖
pip install -r requirements.txt
cd frontend && npm install --legacy-peer-deps && cd ..

# 3. 启动基础设施
docker compose up -d

# 4. 分别在两个终端启动后端和前端
PYTHONPATH=. python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000
cd frontend && npm run dev -- --port 3001
```

---

## 4. Docker Compose 部署

### 4.1 服务架构

```
                      crypto_trading_network (bridge)
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
   ┌──────▼──────┐   ┌────────▼───────┐   ┌───────▼──────┐
   │ timescaledb │   │     redis      │   │   grafana    │
   │   :5432     │   │    :6379       │   │   :3000      │
   │ (internal)  │   │  (internal)    │   │  (host:3000) │
   └──────┬──────┘   └────────┬───────┘   └──────────────┘
          │                    │
   ┌──────▼────────────────────▼──────┐
   │        trading_system            │
   │   :8000 (host:8000)              │
   │   uvicorn src.api.app:app        │
   └──────────────────────────────────┘
```

### 4.2 启动与停止

```bash
# 启动所有基础设施服务
docker compose up -d

# 查看服务状态
docker compose ps
# 期望输出：4 个服务 (timescaledb, redis, grafana, trading_system) 均为 "Up" 或 "healthy"

# 查看日志
docker compose logs -f trading_system

# 停止（保留数据）
docker compose stop

# 停止并移除容器（保留数据卷）
docker compose down

# ⚠️ 完全清理（删除所有数据）
docker compose down -v
```

### 4.3 服务端口

| 服务 | 端口 | URL |
|------|------|-----|
| 后端 API | 8000 | http://localhost:8000 |
| API 文档 (Swagger) | 8000 | http://localhost:8000/docs |
| 前端仪表盘 | 3001 | http://localhost:3001 |
| Grafana 监控 | 3000 | http://localhost:3000 (admin/admin) |
| TimescaleDB | 5432 | `localhost:5432` |
| Redis | 6379 | `localhost:6379` |

> **端口 3000 被 Grafana 占用**，前端开发服务器使用 3001。

### 4.4 数据卷

| 卷名 | 挂载路径 | 内容 |
|------|----------|------|
| `timescaledb_data` | `/var/lib/postgresql/data` | 数据库文件 |
| `redis_data` | `/data` | Redis AOF 持久化 |
| `grafana_data` | `/var/lib/grafana` | Grafana 配置与面板 |
| (bind mount) | `./logs:/app/logs` | 应用日志 |
| (bind mount) | `./data:/app/data` | 交易数据与报告 |
| (bind mount) | `./config:/app/config` | 配置文件 |

---

## 5. 前端部署

### 5.1 开发模式

```bash
cd frontend
npm install --legacy-peer-deps

# 开发服务器（端口 3001，热重载）
npm run dev -- --port 3001
```

### 5.2 生产构建

```bash
cd frontend
npm install --legacy-peer-deps
npm run build       # 输出到 frontend/.next/

# 生产运行
npm start -- --port 3001
```

### 5.3 环境变量

前端需要 `frontend/.env.local`：

```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000    # 后端地址
NEXT_PUBLIC_API_TOKEN=<your-token>            # 须与后端 API_TOKEN 一致
```

---

## 6. 验证步骤

### 6.1 环境检查

```bash
python scripts/check_environment.py
```

### 6.2 基础设施健康

```bash
docker compose ps
# 确认 4 个服务均为 healthy

# 测试后端 API
curl http://localhost:8000/health
# 期望：{"status": "ok", ...}

# 测试 Grafana
curl http://localhost:3000/api/health
# 期望：返回健康状态 JSON
```

### 6.3 运行 Paper Trading

```bash
# 生成模拟数据
python scripts/generate_oscillating_data.py

# 运行 Paper Trading（单次）
python scripts/run_paper_trading.py

# 60 天连续运行（Windows）
start_paper_60d.bat

# 60 天连续运行（手动）
python scripts/run_paper_trading_daemon.py --days 60 --no-db
```

### 6.4 全量测试

```bash
python -m pytest -p no:asyncio -q
# 基线：~472 passed / ~475 total
```

### 6.5 Grafana 端到端验证

```bash
export TIMESCALE_PASSWORD=<your-password>
python scripts/verify_grafana_e2e.py
```

### 6.6 风控验证

```bash
python scripts/verify_risk_controls.py
```

### 6.7 上线前全面检查

```bash
python scripts/preflight_check.py
```

---

## 7. 常见问题

### Q1: `docker compose up -d` 报错 "POSTGRES_PASSWORD must be set in .env"

**原因：** `.env` 文件缺少 `POSTGRES_PASSWORD`。

**解决：**
```bash
echo "POSTGRES_PASSWORD=changeme" >> .env
```

### Q2: 后端启动后 `curl localhost:8000/health` 连接被拒绝

**原因：** Python 依赖未安装或数据库未就绪。

**解决：**
```bash
pip install -r requirements.txt
docker compose up -d  # 确保数据库已启动
python -m uvicorn src.api.app:app --port 8000
```

### Q3: 前端页面显示 "无法加载数据"

**原因：** 后端 API 未运行，或 `API_TOKEN` 不一致。

**解决：**
1. 确认后端运行：`curl http://localhost:8000/health`
2. 确认 `frontend/.env.local` 中 `NEXT_PUBLIC_API_TOKEN` 与后端 `.env` 中 `API_TOKEN` 一致
3. 检查浏览器控制台是否有 CORS 错误

### Q4: Grafana 面板无数据

**原因：** `monitor_metrics` 表为空（尚未运行 Paper Trading）或数据源配置问题。

**解决：**
1. 运行一次 `python scripts/run_paper_trading.py` 产生指标
2. 运行 `python scripts/verify_grafana_e2e.py` 验证端到端链路
3. 参考 `TROUBLESHOOTING.md` 故障 2

### Q5: `PYTHONPATH` 未设置导致 `ModuleNotFoundError: No module named 'src'`

**解决：**
```bash
# Windows (CMD)
set PYTHONPATH=%cd%

# Windows (PowerShell)
$env:PYTHONPATH = (Get-Location).Path

# macOS / Linux
export PYTHONPATH=$(pwd)
```

### Q6: pytest 报 "asyncio" 相关错误

**解决：** 必须带 `-p no:asyncio` 参数：
```bash
python -m pytest -p no:asyncio -q
```

---

## 8. 生产注意事项

### 8.1 安全

| 项 | 要求 |
|----|------|
| 数据库密码 | 更换默认 `changeme` |
| `API_TOKEN` | 使用至少 32 字符的随机字符串 |
| Binance API Key | 生产环境使用独立 Key，**禁用提币权限** |
| `.env` 文件 | 不要提交到 Git；限制文件权限 (`chmod 600 .env`) |
| Grafana 密码 | 更换默认 `admin` |

### 8.2 生产环境变量

```bash
ENVIRONMENT=production
LIVE_TRADING_ENABLED=false   # 实盘前保持 false
BINANCE_TESTNET=false         # 实盘时改为 false
DEBUG=false
LOG_LEVEL=INFO                # 或 WARNING（减少日志量）
```

### 8.3 可用性

- **Docker 重启策略：** `restart: unless-stopped`（所有服务）
- **健康检查：** 所有 4 个 Docker 服务均配置了 `healthcheck`
- **数据持久化：** Docker 命名卷确保 `down` 不丢数据
- **`docker compose down -v`：** 仅在明确需要清空数据库时使用

### 8.4 备份

```bash
# 数据库备份
docker exec crypto_trading_db pg_dump -U postgres crypto_trading > backup_$(date +%Y%m%d).sql

# 数据卷备份
docker run --rm -v crypto-trading-system_timescaledb_data:/data -v $(pwd):/backup alpine tar czf /backup/db_volume_backup.tar.gz -C /data .
```

### 8.5 前端生产构建

```bash
cd frontend
npm run build

# 使用 Nginx 反向代理静态文件 + API 代理（示例）
# server {
#     listen 80;
#     location / {
#         proxy_pass http://127.0.0.1:3001;
#     }
#     location /api/ {
#         proxy_pass http://127.0.0.1:8000/;
#     }
# }
```

### 8.6 资源建议

| 组件 | 最低 | 推荐 |
|------|------|------|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 10 GB | 50 GB (SSD) |
| Docker 内存分配 | 4 GB | 6 GB |

---

## 9. 一键启动命令汇总

### 完整启动（Windows）

```cmd
install.cmd
```

### 手动分步启动

```bash
# 1. 环境准备
python scripts/check_environment.py

# 2. 启动基础设施
docker compose up -d

# 3. 生成数据（首次）
python scripts/generate_oscillating_data.py

# 4. 启动后端（新终端）
PYTHONPATH=. python -m uvicorn src.api.app:app --port 8000

# 5. 启动前端（新终端）
cd frontend && npm run dev -- --port 3001

# 6. 打开浏览器
# http://localhost:3001
```

### Paper Trading 60 天连续运行

```cmd
start_paper_60d.bat
```

或手动：

```bash
python scripts/run_paper_trading_daemon.py --days 60 --no-db
```

---

**文档状态：** ✅ 基于源码生成  
**验证：** 所有命令使用源码中实际存在的脚本名和变量名  
**更新日期：** 2026-06-20
