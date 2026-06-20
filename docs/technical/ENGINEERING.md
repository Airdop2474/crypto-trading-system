# 加密货币交易系统 - 工程开发文档

**项目名称：** Crypto Trading System  
**版本：** v0.1 → v2.0（方案 C+）  
**创建日期：** 2026-06-12  
**更新日期：** 2026-06-13

---

## ⚠️ 重要更新（2026-06-13）

**本文档已更新关键架构设计（方案 C+）：**

### 核心架构变更

1. **Broker 三层架构** ⭐
   - Paper Broker（Phase 4，最完善）
   - Exchange Broker（Phase 5-6，交易所接口）
   - Live Broker（Phase 7+，实盘执行）

2. **API 层迁移** ⭐
   - 前端已从 Streamlit 迁移到 FastAPI API 层（18 REST 端点 + WebSocket 实时推送）
   - 仪表盘迁移到 Next.js 16（React 19 + SWR + shadcn/ui）

3. **Signal 状态管理** ⭐
   - NO_SIGNAL（正常等待）
   - NO_TRADE（策略拒绝）
   - PAUSE（系统暂停）

4. **验收标准调整** ⭐
   - Phase 1-3：系统可信度优先（不看收益）
   - Phase 6：无严重风控事故 + 回撤可控（不要求不亏损）

**详细说明见下文"三层 Broker 架构"章节。**

**完整规划请查看：**
- `FINAL_PLAN_APPROVED.md` - 最终批准方案
- `ROADMAP_UPDATE.md` - 最新路线图

---

## 📌 文档定位与现状映射（2026-06-20）

> **本文档是 Phase 0 的"从零构建"设计蓝图，不是当前系统的现状说明。** 下文中以"创建 `xxx`"形式给出的代码块多为设计示意，文件名/结构与实际实现存在出入。**当前系统的权威说明请以代码和以下专题文档为准：**
>
> | 主题 | 权威来源 |
> |------|---------|
> | API 接口（18 端点 + WebSocket） | `docs/reference/API_REFERENCE.md` |
> | 数据库 Schema（实际 ORM 模型） | `docs/technical/DATABASE_SCHEMA.md` |
> | 环境变量（权威清单 + 溯源） | `docs/reference/ENV_VARIABLE_REFERENCE.md` |
> | 策略目录（8 策略） | `docs/reference/STRATEGY_CATALOG.md` |
> | 部署 | `docs/DEPLOYMENT.md` |
> | 前端架构 | `docs/technical/FRONTEND_ARCHITECTURE.md` |
>
> **蓝图文件名 → 实际模块对照（下文出现的示意文件并不存在）：**
>
> | 本文档中的示意文件 | 实际状态 |
> |-------------------|---------|
> | `scripts/init_database.py` | 不存在；初始化由 docker compose 挂载 `config/sql/01_monitor_metrics.sql` 自动完成 |
> | `scripts/download_data.py` | 不存在；数据管道入口是 `scripts/run_data_pipeline.py` |
> | `scripts/backup_database.sh` | 不存在；备份策略未落地（设计示意） |
> | `config/alerts.yaml` | 不存在；告警逻辑硬编码在 `src/monitor/alert_manager.py` |
> | `src/data/database.py` | 实际为 `src/utils/database.py` |
> | `src/agent/interface.py` / `src/agent/trigger.py` | 不存在；Agent 分析在 `src/agent/analyzer.py`（纯规则、只分析不执行） |
> | `streamlit run src/monitor/dashboard.py` | 已弃用；监控走 FastAPI + Next.js 仪表盘 + Grafana |
>
> 依赖列表（§1.3）中的 `streamlit==1.30.0` 等版本号亦为蓝图初值，实际以项目根 `requirements.txt` 为准。

---

## 一、开发环境配置

### 1.1 系统要求

**操作系统：**
- Windows 10/11 (当前开发环境)
- Linux (生产环境推荐)
- macOS (可选)

**硬件要求：**
- CPU: 4 核心以上
- 内存: 8GB 以上（推荐 16GB）
- 磁盘: 50GB 可用空间（用于历史数据）
- 网络: 稳定网络连接（延迟 < 100ms）

### 1.2 开发工具安装

#### 1.2.1 Python 环境

```bash
# 检查 Python 版本（需要 3.13+）
python --version

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 升级 pip
pip install --upgrade pip
```

#### 1.2.2 数据库安装

**方案 A：Docker 安装（推荐）**

```bash
# 安装 Docker Desktop (Windows)
# 下载: https://www.docker.com/products/docker-desktop/

# 启动 TimescaleDB
docker run -d --name timescaledb \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=your_secure_password \
  -e POSTGRES_DB=crypto_trading \
  -v timescaledb_data:/var/lib/postgresql/data \
  timescale/timescaledb:latest-pg16

# 启动 Redis
docker run -d --name redis \
  -p 6379:6379 \
  -v redis_data:/data \
  redis:latest redis-server --appendonly yes
```

**方案 B：本地安装**

```bash
# PostgreSQL + TimescaleDB
# Windows: 下载安装包
# https://www.timescale.com/download

# Redis
# Windows: 使用 WSL 或下载预编译版本
# https://github.com/microsoftarchive/redis/releases
```

#### 1.2.3 监控工具（可选）

```bash
# Grafana
docker run -d --name=grafana \
  -p 3000:3000 \
  -v grafana_data:/var/lib/grafana \
  grafana/grafana-oss

# 访问: http://localhost:3000
# 默认账号: admin / admin
```

### 1.3 Python 依赖安装

创建 `requirements.txt`:

```txt
# 核心依赖
ccxt==4.2.0                 # 交易所接口
pandas==2.2.0               # 数据处理
numpy==1.26.0               # 数值计算
python-dotenv==1.0.0        # 环境变量

# 数据库
sqlalchemy==2.0.25          # ORM
psycopg2-binary==2.9.9      # PostgreSQL
redis==5.0.1                # Redis 客户端
alembic==1.13.0             # 数据库迁移

# 技术指标
pandas-ta==0.3.14b          # 技术分析指标
# ta-lib  # 需要单独编译安装

# 回测
backtesting==0.3.3          # 回测框架

# Web 框架
streamlit==1.30.0           # 控制台
plotly==5.18.0              # 可视化
fastapi==0.109.0            # API 服务
uvicorn==0.27.0             # ASGI 服务器

# 数据验证
pydantic==2.5.0             # 数据模型验证
pydantic-settings==2.1.0    # 配置管理

# 日志
loguru==0.7.2               # 日志管理

# 测试
pytest==7.4.4               # 测试框架
pytest-asyncio==0.23.3      # 异步测试
pytest-cov==4.1.0           # 覆盖率
faker==22.0.0               # 测试数据生成

# 类型检查和代码质量
mypy==1.8.0                 # 类型检查
black==23.12.1              # 代码格式化
flake8==7.0.0               # 代码检查
isort==5.13.2               # import 排序

# 其他
python-dateutil==2.8.2      # 日期处理
pytz==2023.3                # 时区
requests==2.31.0            # HTTP 请求
websocket-client==1.7.0     # WebSocket
schedule==1.2.0             # 任务调度
```

安装依赖：

```bash
pip install -r requirements.txt
```

**注意：TA-Lib 需要单独安装**

```bash
# Windows: 下载预编译 wheel
# https://github.com/cgohlke/talib-build/releases
pip install TA_Lib-0.4.28-cp311-cp311-win_amd64.whl

# Linux:
sudo apt-get install ta-lib
pip install ta-lib

# macOS:
brew install ta-lib
pip install ta-lib
```

---

## 二、项目初始化

### 2.1 创建项目结构

```bash
# 在项目根目录执行
mkdir -p src/{data,strategy,execution,backtest,monitor,agent,utils}
mkdir -p tests/{unit,integration}
mkdir -p scripts config data/{historical,reports} logs docs
```

### 2.2 环境变量配置

创建 `.env` 文件：

```bash
# 数据库配置
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_DB=crypto_trading
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password

# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# 交易所 API（测试网）
BINANCE_API_KEY=your_testnet_api_key
BINANCE_API_SECRET=your_testnet_api_secret
BINANCE_TESTNET=true

# 日志配置
LOG_LEVEL=INFO
LOG_PATH=./logs

# AI Agent
HERMES_API_KEY=your_hermes_key
HERMES_API_URL=https://api.hermes.ai/v1

# 风控参数（变量名以 src/utils/config.py 为准）
MAX_POSITION_SIZE=0.20
MAX_DAILY_LOSS=0.02          # 策略级 2%；账户级 RiskManager 默认 3%
MAX_CONSECUTIVE_LOSSES=5
```

**安全提示：** 将 `.env` 添加到 `.gitignore`

### 2.3 Git 配置

创建 `.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# 数据文件
data/
*.csv
*.pkl
*.h5

# 日志
logs/
*.log

# 配置
.env
*.local.yaml

# IDE
.vscode/
.idea/
*.swp

# 测试
.pytest_cache/
.coverage
htmlcov/

# 数据库
*.db
*.sqlite

# 临时文件
*.tmp
.DS_Store
```

初始化 Git：

```bash
git init
git add .
git commit -m "Initial commit: Project structure"
```

---

## 三、数据库设计

### 3.1 TimescaleDB Schema

#### 3.1.1 K线数据表

```sql
-- 创建 K线数据表
CREATE TABLE ohlcv (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    open NUMERIC(20, 8) NOT NULL,
    high NUMERIC(20, 8) NOT NULL,
    low NUMERIC(20, 8) NOT NULL,
    close NUMERIC(20, 8) NOT NULL,
    volume NUMERIC(20, 8) NOT NULL,
    PRIMARY KEY (time, symbol, timeframe)
);

-- 转换为 hypertable
SELECT create_hypertable('ohlcv', 'time');

-- 创建索引
CREATE INDEX idx_ohlcv_symbol_time ON ohlcv (symbol, time DESC);

-- 设置数据压缩（保留最近30天，压缩更早数据）
ALTER TABLE ohlcv SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,timeframe'
);

SELECT add_compression_policy('ohlcv', INTERVAL '30 days');
```

#### 3.1.2 技术指标表

```sql
CREATE TABLE indicators (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    indicator_name VARCHAR(50) NOT NULL,
    value NUMERIC(20, 8),
    metadata JSONB,
    PRIMARY KEY (time, symbol, timeframe, indicator_name)
);

SELECT create_hypertable('indicators', 'time');
CREATE INDEX idx_indicators_symbol_time ON indicators (symbol, indicator_name, time DESC);
```

#### 3.1.3 实时Tick数据表（可选）

```sql
CREATE TABLE ticks (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    price NUMERIC(20, 8) NOT NULL,
    volume NUMERIC(20, 8) NOT NULL,
    side VARCHAR(4),  -- 'buy' or 'sell'
    PRIMARY KEY (time, symbol)
);

SELECT create_hypertable('ticks', 'time');

-- 设置数据保留策略（只保留7天）
SELECT add_retention_policy('ticks', INTERVAL '7 days');
```

### 3.2 PostgreSQL Schema

#### 3.2.1 账户资金表

```sql
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    account_type VARCHAR(20) NOT NULL,  -- 'testnet', 'paper', 'live'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE account_balances (
    id SERIAL PRIMARY KEY,
    account_id INTEGER REFERENCES accounts(id),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    currency VARCHAR(10) NOT NULL,
    total NUMERIC(20, 8) NOT NULL,
    available NUMERIC(20, 8) NOT NULL,
    locked NUMERIC(20, 8) NOT NULL DEFAULT 0
);

CREATE INDEX idx_balance_account_time ON account_balances (account_id, timestamp DESC);
```

#### 3.2.2 订单表

```sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    account_id INTEGER REFERENCES accounts(id),
    exchange_order_id VARCHAR(100) UNIQUE,
    symbol VARCHAR(20) NOT NULL,
    order_type VARCHAR(20) NOT NULL,  -- 'limit', 'market', 'stop_loss'
    side VARCHAR(10) NOT NULL,        -- 'buy', 'sell'
    price NUMERIC(20, 8),
    amount NUMERIC(20, 8) NOT NULL,
    filled NUMERIC(20, 8) DEFAULT 0,
    status VARCHAR(20) NOT NULL,      -- 'open', 'filled', 'canceled', 'failed'
    strategy_id INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    filled_at TIMESTAMPTZ,
    metadata JSONB
);

CREATE INDEX idx_orders_account_time ON orders (account_id, created_at DESC);
CREATE INDEX idx_orders_status ON orders (status) WHERE status = 'open';
```

#### 3.2.3 交易记录表

```sql
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    account_id INTEGER REFERENCES accounts(id),
    order_id INTEGER REFERENCES orders(id),
    exchange_trade_id VARCHAR(100),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    price NUMERIC(20, 8) NOT NULL,
    amount NUMERIC(20, 8) NOT NULL,
    fee NUMERIC(20, 8) DEFAULT 0,
    fee_currency VARCHAR(10),
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB
);

CREATE INDEX idx_trades_account_time ON trades (account_id, executed_at DESC);
```

#### 3.2.4 策略配置表

```sql
CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    strategy_type VARCHAR(50) NOT NULL,
    description TEXT,
    parameters JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE strategy_instances (
    id SERIAL PRIMARY KEY,
    strategy_id INTEGER REFERENCES strategies(id),
    account_id INTEGER REFERENCES accounts(id),
    symbol VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'running',  -- 'running', 'paused', 'stopped'
    started_at TIMESTAMPTZ DEFAULT NOW(),
    stopped_at TIMESTAMPTZ
);
```

#### 3.2.5 Agent 分析报告表

```sql
CREATE TABLE agent_reports (
    id SERIAL PRIMARY KEY,
    report_type VARCHAR(50) NOT NULL,  -- 'daily', 'weekly', 'alert', 'optimization'
    trigger_type VARCHAR(50) NOT NULL, -- 'scheduled', 'threshold', 'manual'
    analysis_period_start TIMESTAMPTZ NOT NULL,
    analysis_period_end TIMESTAMPTZ NOT NULL,
    agent_name VARCHAR(50) NOT NULL,   -- 'hermes', 'openclaw'
    raw_response TEXT,
    parsed_recommendations JSONB,
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'reviewed', 'applied', 'rejected'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(100)
);

CREATE INDEX idx_reports_created ON agent_reports (created_at DESC);
CREATE INDEX idx_reports_status ON agent_reports (status);
```

#### 3.2.6 系统日志表

```sql
CREATE TABLE system_logs (
    id SERIAL PRIMARY KEY,
    level VARCHAR(10) NOT NULL,      -- 'DEBUG', 'INFO', 'WARNING', 'ERROR'
    module VARCHAR(100),
    message TEXT NOT NULL,
    exception TEXT,
    context JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_logs_level_time ON system_logs (level, created_at DESC);
CREATE INDEX idx_logs_module ON system_logs (module, created_at DESC);

-- 自动清理旧日志（保留30天）
CREATE OR REPLACE FUNCTION cleanup_old_logs()
RETURNS void AS $$
BEGIN
    DELETE FROM system_logs WHERE created_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;
```

### 3.3 初始化脚本（示例）

> **注意：** 数据管道的实际入口是 `scripts/run_data_pipeline.py`（含数据下载、质量检查、入库一体化流程）。以下代码仅为数据库 Schema 初始化的示意实现。

创建 `scripts/init_database.py`（示例）:

```python
"""数据库初始化脚本"""
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def init_database():
    """初始化数据库表结构"""
    db_url = (
        f"postgresql://{os.getenv('POSTGRES_USER')}:"
        f"{os.getenv('POSTGRES_PASSWORD')}@"
        f"{os.getenv('POSTGRES_SERVER')}:"
        f"{os.getenv('POSTGRES_PORT')}/"
        f"{os.getenv('POSTGRES_DB')}"
    )
    
    engine = create_engine(db_url)
    
    # 读取 SQL 文件
    sql_dir = Path(__file__).parent.parent / "config" / "sql"
    
    with engine.connect() as conn:
        # 启用 TimescaleDB 扩展
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb;"))
        
        # 执行初始化脚本
        for sql_file in sorted(sql_dir.glob("*.sql")):
            print(f"Executing {sql_file.name}...")
            with open(sql_file) as f:
                conn.execute(text(f.read()))
        
        conn.commit()
    
    print("✓ Database initialized successfully!")

if __name__ == "__main__":
    init_database()
```

---

## 四、核心模块开发指南

### 4.1 数据层开发

#### 4.1.1 交易所连接器

创建 `src/data/exchange.py`:

```python
"""交易所接口封装"""
import ccxt
from typing import Optional, List
import pandas as pd
from loguru import logger

class ExchangeConnector:
    """统一交易所接口"""
    
    def __init__(self, exchange_id: str, api_key: str = None, 
                 api_secret: str = None, testnet: bool = False):
        self.exchange_id = exchange_id
        exchange_class = getattr(ccxt, exchange_id)
        
        config = {
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        }
        
        if testnet:
            config['urls'] = {'api': exchange_class.urls.get('test', {})}
        
        self.exchange = exchange_class(config)
    
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h',
                    since: Optional[int] = None, 
                    limit: int = 1000) -> pd.DataFrame:
        """获取K线数据"""
        try:
            data = self.exchange.fetch_ohlcv(
                symbol, timeframe, since, limit
            )
            df = pd.DataFrame(
                data, 
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV: {e}")
            raise
    
    def fetch_balance(self) -> dict:
        """获取账户余额"""
        return self.exchange.fetch_balance()
    
    def create_order(self, symbol: str, order_type: str, side: str,
                    amount: float, price: Optional[float] = None) -> dict:
        """创建订单"""
        try:
            return self.exchange.create_order(
                symbol, order_type, side, amount, price
            )
        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            raise
```

#### 4.1.2 数据存储模块

创建 `src/data/database.py`:

```python
"""数据库操作模块"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pandas as pd
from typing import Optional
import os

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        db_url = (
            f"postgresql://{os.getenv('POSTGRES_USER')}:"
            f"{os.getenv('POSTGRES_PASSWORD')}@"
            f"{os.getenv('POSTGRES_SERVER')}:"
            f"{os.getenv('POSTGRES_PORT')}/"
            f"{os.getenv('POSTGRES_DB')}"
        )
        self.engine = create_engine(db_url, pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
    
    def save_ohlcv(self, df: pd.DataFrame, symbol: str, timeframe: str):
        """保存K线数据"""
        df_copy = df.copy()
        df_copy['symbol'] = symbol
        df_copy['timeframe'] = timeframe
        df_copy.to_sql('ohlcv', self.engine, if_exists='append', 
                      index=True, index_label='time')
    
    def load_ohlcv(self, symbol: str, timeframe: str,
                   start: Optional[str] = None, 
                   end: Optional[str] = None) -> pd.DataFrame:
        """加载K线数据"""
        query = f"""
            SELECT time, open, high, low, close, volume
            FROM ohlcv
            WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
        """
        if start:
            query += f" AND time >= '{start}'"
        if end:
            query += f" AND time <= '{end}'"
        query += " ORDER BY time"
        
        df = pd.read_sql(query, self.engine, index_col='time')
        return df
```

### 4.2 策略层开发

#### 4.2.1 策略基类

创建 `src/strategy/base.py`:

```python
"""策略基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import pandas as pd

@dataclass
class Signal:
    """交易信号"""
    action: str  # 'buy', 'sell', 'close'
    price: float
    amount: float
    timestamp: pd.Timestamp
    reason: str = ""

class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, symbol: str, timeframe: str, parameters: dict):
        self.symbol = symbol
        self.timeframe = timeframe
        self.parameters = parameters
        self.position = 0  # 当前持仓
    
    @abstractmethod
    def on_bar(self, bar: pd.Series) -> Optional[Signal]:
        """处理新K线"""
        pass
    
    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        pass
    
    def calculate_position_size(self, signal: Signal, 
                               balance: float) -> float:
        """计算仓位大小"""
        # 默认使用固定比例
        return balance * self.parameters.get('position_pct', 0.1)
    
    def should_stop_loss(self, current_price: float, 
                         entry_price: float) -> bool:
        """检查是否需要止损"""
        if self.position > 0:  # 多头
            loss_pct = (entry_price - current_price) / entry_price
            return loss_pct > self.parameters.get('stop_loss_pct', 0.15)
        return False
```

#### 4.2.2 网格交易策略

创建 `src/strategy/grid_trading.py`:

```python
"""网格交易策略"""
from .base import BaseStrategy, Signal
import pandas as pd
from typing import Optional, List

class GridTradingStrategy(BaseStrategy):
    """网格交易策略实现"""
    
    def __init__(self, symbol: str, timeframe: str, parameters: dict):
        super().__init__(symbol, timeframe, parameters)
        self.grid_levels = self._calculate_grid_levels()
        self.active_orders = []
    
    def _calculate_grid_levels(self) -> List[float]:
        """计算网格价格"""
        lower_price = self.parameters['lower_price']
        upper_price = self.parameters['upper_price']
        num_grids = self.parameters['num_grids']
        
        step = (upper_price - lower_price) / (num_grids - 1)
        return [lower_price + i * step for i in range(num_grids)]
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """网格策略不需要复杂指标"""
        return df
    
    def on_bar(self, bar: pd.Series) -> Optional[Signal]:
        """处理新价格"""
        current_price = bar['close']
        
        # 检查是否触及网格线
        for i, grid_price in enumerate(self.grid_levels):
            if abs(current_price - grid_price) / grid_price < 0.001:
                # 价格接近网格线
                if i < len(self.grid_levels) // 2:
                    # 下半部分网格：买入
                    return Signal(
                        action='buy',
                        price=grid_price,
                        amount=self._calculate_grid_amount(),
                        timestamp=bar.name,
                        reason=f"Grid buy at level {i}"
                    )
                else:
                    # 上半部分网格：卖出
                    if self.position > 0:
                        return Signal(
                            action='sell',
                            price=grid_price,
                            amount=self._calculate_grid_amount(),
                            timestamp=bar.name,
                            reason=f"Grid sell at level {i}"
                        )
        return None
    
    def _calculate_grid_amount(self) -> float:
        """计算每格交易量"""
        total_amount = self.parameters['total_amount']
        return total_amount / self.parameters['num_grids']
```

### 4.3 回测框架开发

#### 4.3.1 回测引擎

创建 `src/backtest/engine.py`:

```python
"""回测引擎"""
import pandas as pd
from typing import List, Dict
from ..strategy.base import BaseStrategy, Signal
from .metrics import PerformanceMetrics

class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, initial_balance: float = 10000,
                 commission: float = 0.001,
                 slippage: float = 0.0005):
        self.initial_balance = initial_balance
        self.commission = commission
        self.slippage = slippage
        self.trades = []
        self.equity_curve = []
    
    def run(self, strategy: BaseStrategy, data: pd.DataFrame) -> Dict:
        """运行回测"""
        balance = self.initial_balance
        position = 0
        entry_price = 0
        
        # 计算指标
        data = strategy.calculate_indicators(data)
        
        for timestamp, bar in data.iterrows():
            # 生成信号
            signal = strategy.on_bar(bar)
            
            if signal:
                if signal.action == 'buy' and position == 0:
                    # 买入
                    actual_price = signal.price * (1 + self.slippage)
                    cost = actual_price * signal.amount
                    fee = cost * self.commission
                    
                    if balance >= cost + fee:
                        position = signal.amount
                        entry_price = actual_price
                        balance -= (cost + fee)
                        
                        self.trades.append({
                            'timestamp': timestamp,
                            'action': 'buy',
                            'price': actual_price,
                            'amount': signal.amount,
                            'fee': fee,
                            'balance': balance
                        })
                
                elif signal.action == 'sell' and position > 0:
                    # 卖出
                    actual_price = signal.price * (1 - self.slippage)
                    revenue = actual_price * position
                    fee = revenue * self.commission
                    
                    balance += (revenue - fee)
                    pnl = (actual_price - entry_price) * position - fee
                    
                    self.trades.append({
                        'timestamp': timestamp,
                        'action': 'sell',
                        'price': actual_price,
                        'amount': position,
                        'fee': fee,
                        'balance': balance,
                        'pnl': pnl,
                        'pnl_pct': pnl / (entry_price * position)
                    })
                    
                    position = 0
                    entry_price = 0
            
            # 记录资产曲线
            total_value = balance
            if position > 0:
                total_value += position * bar['close']
            
            self.equity_curve.append({
                'timestamp': timestamp,
                'balance': balance,
                'position_value': position * bar['close'] if position > 0 else 0,
                'total_value': total_value
            })
        
        # 计算性能指标
        metrics = PerformanceMetrics.calculate(
            self.trades, 
            self.equity_curve,
            self.initial_balance
        )
        
        return {
            'trades': self.trades,
            'equity_curve': self.equity_curve,
            'metrics': metrics
        }
```

#### 4.3.2 性能指标

创建 `src/backtest/metrics.py`:

```python
"""性能指标计算"""
import pandas as pd
import numpy as np
from typing import List, Dict

class PerformanceMetrics:
    """性能指标计算"""
    
    @staticmethod
    def calculate(trades: List[Dict], equity_curve: List[Dict],
                 initial_balance: float) -> Dict:
        """计算所有指标"""
        df_trades = pd.DataFrame(trades)
        df_equity = pd.DataFrame(equity_curve)
        
        # 总收益
        final_value = df_equity['total_value'].iloc[-1]
        total_return = (final_value - initial_balance) / initial_balance
        
        # 年化收益
        days = (df_equity['timestamp'].iloc[-1] - 
                df_equity['timestamp'].iloc[0]).days
        annual_return = (1 + total_return) ** (365 / days) - 1
        
        # 最大回撤
        df_equity['peak'] = df_equity['total_value'].cummax()
        df_equity['drawdown'] = (df_equity['total_value'] - df_equity['peak']) / df_equity['peak']
        max_drawdown = df_equity['drawdown'].min()
        
        # 夏普比率（假设无风险利率 3%）
        returns = df_equity['total_value'].pct_change().dropna()
        sharpe = (returns.mean() * 365 - 0.03) / (returns.std() * np.sqrt(365))
        
        # 交易统计
        winning_trades = df_trades[df_trades['pnl'] > 0] if 'pnl' in df_trades.columns else pd.DataFrame()
        win_rate = len(winning_trades) / len(df_trades) if len(df_trades) > 0 else 0
        
        avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0
        losing_trades = df_trades[df_trades['pnl'] < 0] if 'pnl' in df_trades.columns else pd.DataFrame()
        avg_loss = abs(losing_trades['pnl'].mean()) if len(losing_trades) > 0 else 0
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0
        
        return {
            'total_return': total_return,
            'annual_return': annual_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_trades': len(df_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades)
        }
```

### 4.4 Agent 集成开发

#### 4.4.1 Agent 接口适配

创建 `src/agent/interface.py`:

```python
"""Agent 接口适配层"""
import requests
from typing import Dict, Optional
from loguru import logger
import os

class AgentInterface:
    """AI Agent 统一接口"""
    
    def __init__(self, agent_type: str = 'hermes'):
        self.agent_type = agent_type
        self.api_key = os.getenv(f'{agent_type.upper()}_API_KEY')
        self.api_url = os.getenv(f'{agent_type.upper()}_API_URL')
    
    def analyze_performance(self, data: Dict) -> str:
        """分析策略表现"""
        prompt = self._build_analysis_prompt(data)
        
        try:
            response = requests.post(
                f"{self.api_url}/analyze",
                headers={'Authorization': f'Bearer {self.api_key}'},
                json={'prompt': prompt, 'data': data},
                timeout=60
            )
            response.raise_for_status()
            return response.json()['analysis']
        except Exception as e:
            logger.error(f"Agent analysis failed: {e}")
            return None
    
    def _build_analysis_prompt(self, data: Dict) -> str:
        """构建分析提示词"""
        prompt = f"""
        你是一个专业的量化交易分析师。请分析以下交易系统的表现：
        
        ## 性能指标
        - 总收益率: {data['metrics']['total_return']:.2%}
        - 年化收益率: {data['metrics']['annual_return']:.2%}
        - 最大回撤: {data['metrics']['max_drawdown']:.2%}
        - 夏普比率: {data['metrics']['sharpe_ratio']:.2f}
        - 胜率: {data['metrics']['win_rate']:.2%}
        - 总交易次数: {data['metrics']['total_trades']}
        
        ## 交易历史
        {self._format_recent_trades(data.get('trades', []))}
        
        请从以下维度分析：
        1. 策略表现评估（优势和劣势）
        2. 风险分析（回撤、波动率）
        3. 参数优化建议（具体参数值）
        4. 异常交易识别
        5. 改进优先级排序
        
        请以 JSON 格式返回分析结果：
        {{
            "summary": "总体评价",
            "strengths": ["优势1", "优势2"],
            "weaknesses": ["劣势1", "劣势2"],
            "recommendations": [
                {{"parameter": "参数名", "current": 值, "suggested": 值, "reason": "原因"}}
            ],
            "risk_level": "low/medium/high",
            "priority_actions": ["行动1", "行动2"]
        }}
        """
        return prompt
    
    def _format_recent_trades(self, trades: list, limit: int = 10) -> str:
        """格式化最近交易记录"""
        recent = trades[-limit:] if len(trades) > limit else trades
        formatted = []
        for t in recent:
            formatted.append(
                f"- {t['timestamp']}: {t['action']} "
                f"@ {t['price']:.2f}, "
                f"PnL: {t.get('pnl', 0):.2f}"
            )
        return "\n".join(formatted)
```

#### 4.4.2 触发器系统

创建 `src/agent/trigger.py`:

```python
"""Agent 触发器系统"""
import schedule
from datetime import datetime
from typing import Callable
from loguru import logger

class TriggerSystem:
    """Agent 分析触发器"""
    
    def __init__(self):
        self.triggers = []
    
    def add_scheduled_trigger(self, interval: str, callback: Callable):
        """添加定时触发器"""
        if interval == 'daily':
            schedule.every().day.at("00:00").do(callback)
        elif interval == 'weekly':
            schedule.every().monday.at("00:00").do(callback)
        elif interval.endswith('h'):
            hours = int(interval[:-1])
            schedule.every(hours).hours.do(callback)
        
        logger.info(f"Scheduled trigger added: {interval}")
    
    def add_threshold_trigger(self, metric: str, threshold: float, 
                             callback: Callable):
        """添加阈值触发器"""
        self.triggers.append({
            'type': 'threshold',
            'metric': metric,
            'threshold': threshold,
            'callback': callback
        })
    
    def check_thresholds(self, current_metrics: dict):
        """检查阈值触发"""
        for trigger in self.triggers:
            if trigger['type'] == 'threshold':
                metric = trigger['metric']
                if metric in current_metrics:
                    if current_metrics[metric] > trigger['threshold']:
                        logger.warning(
                            f"Threshold triggered: {metric} = "
                            f"{current_metrics[metric]} > {trigger['threshold']}"
                        )
                        trigger['callback'](current_metrics)
    
    def run_pending(self):
        """运行待执行的任务"""
        schedule.run_pending()
```

---

## 五、开发流程和规范

### 5.1 Git 工作流

**分支策略：**

```
main (生产分支)
  ├── develop (开发分支)
  │    ├── feature/grid-strategy
  │    ├── feature/backtest-engine
  │    └── feature/agent-integration
  └── hotfix/critical-bug
```

**提交规范：**

```bash
# 格式
<type>(<scope>): <subject>

# 类型
feat: 新功能
fix: Bug 修复
docs: 文档更新
style: 代码格式
refactor: 重构
test: 测试
chore: 构建/工具

# 示例
feat(strategy): Add grid trading strategy
fix(backtest): Fix commission calculation error
docs(api): Update exchange connector documentation
```

### 5.2 代码规范

**Python 代码风格：**

```python
# 使用类型注解
def fetch_data(symbol: str, limit: int = 100) -> pd.DataFrame:
    pass

# 使用 docstring
def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算技术指标
    
    Args:
        df: 包含 OHLCV 的 DataFrame
    
    Returns:
        添加了指标列的 DataFrame
    """
    pass

# 使用 dataclass
from dataclasses import dataclass

@dataclass
class TradeSignal:
    action: str
    price: float
    amount: float
    timestamp: datetime

# 错误处理
try:
    result = risky_operation()
except SpecificException as e:
    logger.error(f"Operation failed: {e}")
    raise
```

**格式化工具配置：**

创建 `pyproject.toml`:

```toml
[tool.black]
line-length = 100
target-version = ['py311']

[tool.isort]
profile = "black"
line_length = 100

[tool.mypy]
python_version = "3.13"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

### 5.3 测试规范

**测试文件结构：**

```
tests/
├── unit/
│   ├── test_exchange.py
│   ├── test_strategy.py
│   └── test_metrics.py
├── integration/
│   ├── test_backtest_flow.py
│   └── test_database.py
└── conftest.py
```

**单元测试示例：**

创建 `tests/unit/test_metrics.py`:

```python
"""性能指标单元测试"""
import pytest
import pandas as pd
from src.backtest.metrics import PerformanceMetrics

def test_calculate_total_return():
    """测试总收益计算"""
    trades = [
        {'timestamp': '2024-01-01', 'pnl': 100},
        {'timestamp': '2024-01-02', 'pnl': -50},
        {'timestamp': '2024-01-03', 'pnl': 200},
    ]
    equity_curve = [
        {'timestamp': pd.Timestamp('2024-01-01'), 'total_value': 10000},
        {'timestamp': pd.Timestamp('2024-01-03'), 'total_value': 10250},
    ]
    
    metrics = PerformanceMetrics.calculate(trades, equity_curve, 10000)
    
    assert metrics['total_return'] == pytest.approx(0.025, rel=0.01)
    assert metrics['total_trades'] == 3

def test_max_drawdown():
    """测试最大回撤计算"""
    equity_curve = [
        {'timestamp': pd.Timestamp('2024-01-01'), 'total_value': 10000},
        {'timestamp': pd.Timestamp('2024-01-02'), 'total_value': 12000},
        {'timestamp': pd.Timestamp('2024-01-03'), 'total_value': 9000},
        {'timestamp': pd.Timestamp('2024-01-04'), 'total_value': 11000},
    ]
    
    metrics = PerformanceMetrics.calculate([], equity_curve, 10000)
    
    assert metrics['max_drawdown'] < -0.2  # 超过20%回撤
```

**运行测试：**

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/unit/test_metrics.py

# 生成覆盖率报告
pytest --cov=src --cov-report=html

# 查看覆盖率
open htmlcov/index.html
```

### 5.4 日志规范

创建 `src/utils/logger.py`:

```python
"""日志配置"""
from loguru import logger
import sys

def setup_logger(log_level: str = "INFO", log_file: str = "./logs/app.log"):
    """配置日志"""
    # 移除默认处理器
    logger.remove()
    
    # 控制台输出
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>"
    )
    
    # 文件输出
    logger.add(
        log_file,
        rotation="100 MB",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
               "{name}:{function}:{line} | {message}"
    )
    
    return logger
```

**使用示例：**

```python
from src.utils.logger import setup_logger

logger = setup_logger()

logger.info("System started")
logger.warning("High drawdown detected")
logger.error("Failed to connect to exchange", exception=True)
```

---

## 六、部署和运维

### 6.1 生产环境配置

**Docker 部署（推荐）：**

创建 `Dockerfile`:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 运行
CMD ["python", "-m", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

创建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  timescaledb:
    image: timescale/timescaledb:2.17.0-pg16
    container_name: crypto_trading_db
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set in .env}
      POSTGRES_DB: ${POSTGRES_DB:-crypto_trading}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
    volumes:
      - timescaledb_data:/var/lib/postgresql/data
      - ./config/sql:/docker-entrypoint-initdb.d
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
  
  redis:
    image: redis:7.4-alpine
    container_name: crypto_trading_redis
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD:?REDIS_PASSWORD must be set in .env}
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    ports:
      - "${REDIS_PORT:-6379}:6379"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  grafana:
    image: grafana/grafana-oss:10.4.12
    container_name: crypto_trading_grafana
    environment:
      - GF_SECURITY_ADMIN_USER=${GRAFANA_ADMIN_USER:-admin}
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD must be set in .env}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./config/grafana:/etc/grafana/provisioning
    ports:
      - "3000:3000"
    depends_on:
      - timescaledb
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--spider", "--timeout=3", "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
  
  trading_system:
    build: .
    container_name: crypto_trading_app
    depends_on:
      timescaledb:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file:
      - .env
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
      - ./config:/app/config
    ports:
      - "8000:8000"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    command: python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000

volumes:
  timescaledb_data:
  redis_data:
  grafana_data:

networks:
  default:
    name: crypto_trading_network
```

### 6.2 监控和告警

**Grafana 仪表盘配置：**

创建 `config/grafana/dashboard.json`:

```json
{
  "dashboard": {
    "title": "Crypto Trading System",
    "panels": [
      {
        "title": "Account Balance",
        "targets": [
          {
            "expr": "SELECT total_value FROM equity_curve ORDER BY time DESC LIMIT 1"
          }
        ]
      },
      {
        "title": "Daily PnL",
        "targets": [
          {
            "expr": "SELECT SUM(pnl) as daily_pnl FROM trades WHERE DATE(executed_at) = CURRENT_DATE"
          }
        ]
      },
      {
        "title": "Win Rate (7d)",
        "targets": [
          {
            "expr": "SELECT COUNT(*) FILTER(WHERE pnl > 0) * 100.0 / COUNT(*) FROM trades WHERE executed_at > NOW() - INTERVAL '7 days'"
          }
        ]
      }
    ]
  }
}
```

**告警规则：**

创建 `config/alerts.yaml`:

```yaml
alerts:
  - name: high_drawdown
    condition: current_drawdown > 0.15
    action: send_notification
    channels: [email, telegram]
  
  - name: daily_loss_limit
    condition: daily_loss_pct > 0.05
    action: stop_trading
    channels: [email, sms]
  
  - name: api_error_rate
    condition: error_rate_1h > 0.1
    action: pause_strategy
    channels: [email]
  
  - name: low_balance
    condition: available_balance < 100
    action: send_notification
    channels: [email]
```

### 6.3 备份策略

**数据库备份脚本：**

创建 `scripts/backup_database.sh`:

```bash
#!/bin/bash

# 配置
BACKUP_DIR="./backups/$(date +%Y%m%d)"
DB_NAME="crypto_trading"
DB_USER="postgres"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
echo "Starting database backup..."
pg_dump -U $DB_USER -h localhost $DB_NAME | gzip > $BACKUP_DIR/db_backup.sql.gz

# 备份配置文件
cp -r ./config $BACKUP_DIR/
cp .env $BACKUP_DIR/.env.backup

# 删除30天前的备份
find ./backups -type d -mtime +30 -exec rm -rf {} \;

echo "Backup completed: $BACKUP_DIR"
```

**定时备份：**

```bash
# 添加到 crontab
crontab -e

# 每天凌晨 2 点备份
0 2 * * * /path/to/scripts/backup_database.sh
```

---

## 七、快速开始指南

### 7.1 第一次运行

```bash
# 1. 克隆项目（如果从远程）
git clone <repository-url>
cd crypto-trading-system

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动数据库（Docker）
docker-compose up -d timescaledb redis

# 5. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的配置

# 6. 运行数据管道（下载 + 质量检查 + 入库）
python scripts/run_data_pipeline.py --symbol BTC/USDT --days 365

# 7. 运行回测
python scripts/run_backtest.py --strategy grid --symbol BTC/USDT

# 8. 查看结果
ls data/reports/
```

### 7.2 开发模式运行

```bash
# 启动 FastAPI 后端（开发模式）
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

# 启动 Next.js 16 前端仪表盘（另一个终端）
cd frontend && npm run dev -- --port 3001

# API 文档
# 打开 http://localhost:8000/docs

# 启动模拟盘交易
python scripts/run_paper_trading.py

# 启动实盘交易（谨慎！）
python scripts/run_live_trading.py
```

### 7.3 常用命令

```bash
# 运行测试
pytest tests/

# 代码格式化
black src/ tests/
isort src/ tests/

# 类型检查
mypy src/

# 查看日志
tail -f logs/app.log

# 数据库查询
psql -U postgres -d crypto_trading -c "SELECT COUNT(*) FROM ohlcv;"
```

---

## 八、故障排查

### 8.1 常见问题

**问题 1：无法连接到交易所 API**

```bash
# 检查网络连接
ping api.binance.com

# 检查 API Key
python -c "import ccxt; print(ccxt.binance({'apiKey': 'xxx'}).fetch_ticker('BTC/USDT'))"

# 解决方案：
# - 确认 API Key 正确
# - 检查 IP 白名单
# - 使用代理（如果需要）
```

**问题 2：数据库连接失败**

```bash
# 检查数据库运行状态
docker ps | grep timescaledb

# 测试连接
psql -U postgres -h localhost -d crypto_trading

# 解决方案：
# - 确认数据库已启动
# - 检查 .env 配置
# - 查看数据库日志: docker logs timescaledb
```

**问题 3：回测速度慢**

```python
# 优化建议：
# 1. 使用数据库索引
# 2. 减少技术指标计算
# 3. 使用向量化操作（pandas）
# 4. 考虑 Rust 优化关键路径
```

### 8.2 调试技巧

```python
# 启用详细日志
import os
os.environ['LOG_LEVEL'] = 'DEBUG'

# 使用 IPython 调试
import IPython; IPython.embed()

# 使用 pdb
import pdb; pdb.set_trace()

# 性能分析
import cProfile
cProfile.run('run_backtest()', 'profile_results')
```

---

## 九、后续优化方向

### 9.1 短期优化（1-3 个月）

- [ ] 增加更多技术指标（RSI, MACD, Bollinger Bands）
- [ ] 实现趋势跟踪策略
- [ ] 优化网格策略参数自适应
- [ ] 增加更多交易对支持
- [ ] 完善异常处理和重连机制
- [ ] 增加单元测试覆盖率到 80%
- [ ] 优化 Agent 提示词工程

### 9.2 中期优化（3-6 个月）

- [ ] 实现策略组合管理
- [ ] 增加跨交易所套利策略
- [ ] 使用 Rust 优化性能瓶颈
- [ ] 实现 WebSocket 实时数据流
- [ ] 增加更复杂的风控规则
- [ ] 优化 Agent 自动调参算法
- [ ] 实现 A/B 测试框架

### 9.3 长期优化（6-12 个月）

- [ ] 机器学习预测模型集成
- [ ] 多账户管理
- [ ] 高频交易能力
- [ ] 分布式回测系统
- [ ] 移动端监控 App
- [ ] 社区版本开源

---

## 十、附录

### 10.1 必备技能清单

**必须掌握：**
- [x] Python 基础（类、函数、异常处理）
- [x] Pandas 数据处理
- [x] SQL 基础查询
- [x] Git 版本控制
- [x] Linux 基础命令

**推荐掌握：**
- [ ] Docker 容器化
- [ ] 时间序列数据库（TimescaleDB）
- [ ] WebSocket 编程
- [ ] 异步编程（asyncio）
- [ ] 量化交易基础知识

**加分项：**
- [ ] Rust 编程
- [ ] 机器学习基础
- [ ] 前端开发（React/Vue）
- [ ] 云服务部署（AWS/阿里云）

### 10.2 学习资源

**量化交易：**
- 书籍：《量化交易之路》、《打开量化投资的黑箱》
- 课程：Coursera - Machine Learning for Trading

**技术栈：**
- Python: Real Python (https://realpython.com)
- Pandas: Official Documentation
- ccxt: GitHub Wiki

**社区：**
- QuantConnect Community
- /r/algotrading (Reddit)
- GitHub Awesome Quant

---

**文档版本：** v1.0  
**最后更新：** 2026-06-12  
**维护者：** 开发团队

**下一步行动：**
1. 阅读 PROJECT_PLAN.md 了解整体规划
2. 按照第七章"快速开始指南"搭建环境
3. 运行第一个回测验证系统可用
4. 开始 Phase 1 开发
