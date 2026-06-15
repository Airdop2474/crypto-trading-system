# 快速参考指南

## 📋 常用命令速查

### 环境管理
```bash
# 激活虚拟环境
source venv/bin/activate          # Linux/Mac
venv\Scripts\activate             # Windows

# 安装依赖
pip install -r requirements.txt

# 更新依赖
pip freeze > requirements.txt
```

### Docker 管理
```bash
# 启动所有服务
docker-compose up -d

# 停止所有服务
docker-compose down

# 查看日志
docker-compose logs -f timescaledb
docker-compose logs -f redis

# 重启服务
docker-compose restart timescaledb
```

### 数据库操作
```bash
# 连接数据库
docker exec -it crypto_trading_db psql -U postgres -d crypto_trading

# 备份数据库
docker exec crypto_trading_db pg_dump -U postgres crypto_trading > backup.sql

# 恢复数据库
docker exec -i crypto_trading_db psql -U postgres crypto_trading < backup.sql
```

### 开发工作流
```bash
# 1. 运行验证脚本
python scripts/quick_start.py

# 2. 初始化数据库
python scripts/init_database.py

# 3. 下载历史数据
python scripts/download_data.py --symbol BTC/USDT --days 365

# 4. 运行回测
python scripts/run_backtest.py --strategy grid

# 5. 启动监控面板
streamlit run src/monitor/dashboard.py
```

### 测试
```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/unit/test_metrics.py

# 生成覆盖率报告
pytest --cov=src --cov-report=html

# 查看覆盖率
open htmlcov/index.html           # Mac
start htmlcov/index.html          # Windows
```

### 代码质量
```bash
# 格式化代码
black src/ tests/
isort src/ tests/

# 检查代码
python scripts/check_code_style.py
flake8 src/
mypy src/

# 一键检查和格式化
black . && isort . && flake8 src/ && pytest
```

### Git 工作流
```bash
# 创建功能分支
git checkout -b feature/grid-strategy

# 提交代码
git add .
git commit -m "feat(strategy): Add grid trading strategy"

# 推送分支
git push origin feature/grid-strategy

# 合并到 develop
git checkout develop
git merge feature/grid-strategy
```

---

## 📁 关键文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| 环境变量 | `.env` | 数据库、API密钥配置 |
| 依赖列表 | `requirements.txt` | Python包依赖 |
| 主程序 | `src/main.py` | 系统入口 |
| 日志配置 | `src/utils/logger.py` | 日志设置 |
| 数据库脚本 | `config/sql/` | SQL初始化脚本 |
| 策略配置 | `config/strategies/` | 策略参数配置 |
| 测试数据 | `data/historical/` | 历史K线数据 |
| 回测报告 | `data/reports/` | 回测结果报告 |
| 日志文件 | `logs/app.log` | 运行日志 |

---

## 🔧 配置优先级

### 必须配置
- ✅ `.env` 文件（从 `.env.example` 复制）
- ✅ 数据库密码（POSTGRES_PASSWORD）
- ✅ 交易所测试网 API Key

### 推荐配置
- ⭐ AI Agent API Key（后期使用）
- ⭐ 日志级别（LOG_LEVEL）
- ⭐ 风控参数（STOP_LOSS_PCT 等）

### 可选配置
- 📍 Grafana 告警
- 📍 Telegram 通知
- 📍 OKX 交易所（备用）

---

## 🚨 故障排查速查

### 问题：无法连接数据库
```bash
# 检查服务状态
docker ps | grep timescaledb

# 查看日志
docker logs crypto_trading_db

# 重启服务
docker-compose restart timescaledb
```

### 问题：依赖安装失败
```bash
# 升级 pip
pip install --upgrade pip

# 单独安装问题包
pip install package_name --no-cache-dir

# TA-Lib 特殊处理
# Windows: 下载 whl 文件安装
# Linux: sudo apt-get install ta-lib
```

### 问题：交易所 API 限流
```python
# 在代码中添加延迟
import time
time.sleep(1)  # 每次请求后等待1秒

# 或在 ccxt 中配置
exchange.rateLimit = 2000  # 2秒
```

---

## 📊 性能指标说明

| 指标 | 英文 | 说明 | 理想值 |
|------|------|------|--------|
| 总收益率 | Total Return | 期间总收益 | > 0 |
| 年化收益率 | Annual Return | 年化后的收益 | 20-40% |
| 最大回撤 | Max Drawdown | 最大跌幅 | < 25% |
| 夏普比率 | Sharpe Ratio | 风险调整收益 | > 1.5 |
| 胜率 | Win Rate | 盈利交易占比 | > 50% |
| 盈亏比 | Profit Factor | 平均盈利/平均亏损 | > 1.5 |

---

## 🔗 有用的链接

### 文档
- [项目策划](PROJECT_PLAN.md)
- [工程文档](ENGINEERING.md)
- [设置总结](PROJECT_SETUP_SUMMARY.md)

### 外部资源
- [ccxt 文档](https://docs.ccxt.com/)
- [Binance API](https://binance-docs.github.io/apidocs/)
- [TimescaleDB 文档](https://docs.timescale.com/)
- [Streamlit 文档](https://docs.streamlit.io/)

### 学习资源
- [量化交易入门](https://www.quantstart.com/)
- [TA-Lib 指标说明](https://ta-lib.org/)

---

**提示：** 将此文件加入书签，开发时随时查阅！
