# 数据质量标准

**文档版本：** v1.0  
**创建日期：** 2026-06-13  
**状态：** ✅ 已批准

---

## 目的

本文档定义 Phase 1（数据可信闭环）的数据质量标准和验收要求。

**核心原则：** 如果数据不可审计，后续所有收益指标都不可靠。

---

## 强制数据质量检查（7项）

### 1. 时间连续性检查

**定义：** K线时间戳必须连续，不允许缺口。

**检查方法：**
```python
def check_time_continuity(df: pd.DataFrame, timeframe: str) -> dict:
    """
    检查时间连续性
    
    返回：
    {
        'passed': bool,
        'gaps': list,  # 缺口位置
        'gap_count': int
    }
    """
    expected_delta = {
        '1m': pd.Timedelta(minutes=1),
        '5m': pd.Timedelta(minutes=5),
        '1h': pd.Timedelta(hours=1),
        '4h': pd.Timedelta(hours=4),
        '1d': pd.Timedelta(days=1),
    }
    
    time_diff = df['timestamp'].diff()
    gaps = df[time_diff > expected_delta[timeframe]]
    
    return {
        'passed': len(gaps) == 0,
        'gaps': gaps['timestamp'].tolist(),
        'gap_count': len(gaps)
    }
```

**验收标准：**
- ✅ 缺口数量 = 0
- ❌ 任何缺口都不可接受

**异常处理：**
- 发现缺口 → 重新下载该时间段数据
- 如果交易所数据本身有缺口 → 标记跳过，记录到日志

### 2. 时间唯一性检查

**定义：** 每个时间戳只能出现一次，不允许重复K线。

**检查方法：**
```python
def check_time_uniqueness(df: pd.DataFrame) -> dict:
    """
    检查时间唯一性
    
    返回：
    {
        'passed': bool,
        'duplicates': list,
        'duplicate_count': int
    }
    """
    duplicates = df[df['timestamp'].duplicated(keep=False)]
    
    return {
        'passed': len(duplicates) == 0,
        'duplicates': duplicates['timestamp'].tolist(),
        'duplicate_count': len(duplicates)
    }
```

**验收标准：**
- ✅ 重复数量 = 0

**异常处理：**
- 发现重复 → 保留最后一条，删除其他
- 记录到异常日志

### 3. 价格逻辑性检查

**定义：** OHLC 必须满足逻辑关系。

**规则：**
```python
High >= max(Open, Close)
Low <= min(Open, Close)
High >= Low
Open, High, Low, Close > 0
```

**检查方法：**
```python
def check_price_logic(df: pd.DataFrame) -> dict:
    """
    检查价格逻辑性
    
    返回：
    {
        'passed': bool,
        'invalid_rows': list,
        'invalid_count': int,
        'error_types': dict
    }
    """
    errors = []
    
    # High >= max(O, C)
    invalid_high = df[df['high'] < df[['open', 'close']].max(axis=1)]
    if len(invalid_high) > 0:
        errors.append(('high_too_low', invalid_high.index.tolist()))
    
    # Low <= min(O, C)
    invalid_low = df[df['low'] > df[['open', 'close']].min(axis=1)]
    if len(invalid_low) > 0:
        errors.append(('low_too_high', invalid_low.index.tolist()))
    
    # High >= Low
    invalid_hl = df[df['high'] < df['low']]
    if len(invalid_hl) > 0:
        errors.append(('high_less_than_low', invalid_hl.index.tolist()))
    
    # 价格必须 > 0
    invalid_price = df[(df['open'] <= 0) | (df['high'] <= 0) | 
                       (df['low'] <= 0) | (df['close'] <= 0)]
    if len(invalid_price) > 0:
        errors.append(('non_positive_price', invalid_price.index.tolist()))
    
    return {
        'passed': len(errors) == 0,
        'errors': errors,
        'invalid_count': sum(len(e[1]) for e in errors)
    }
```

**验收标准：**
- ✅ 逻辑性错误 = 0

**异常处理：**
- 发现逻辑错误 → 标记为异常K线
- 重新下载该时间段数据
- 如果重新下载仍然异常 → 标记跳过，不用于回测

### 4. 价格合理性检查

**定义：** 单根K线的涨跌幅不应超过合理范围。

**规则：**
```python
# BTC/ETH 主流币
单K线涨跌幅 < 50%（极端情况）

涨跌幅 = abs(close - open) / open
```

**检查方法：**
```python
def check_price_reasonableness(df: pd.DataFrame, 
                               max_change: float = 0.5) -> dict:
    """
    检查价格合理性
    
    参数：
    - max_change: 最大涨跌幅阈值（默认 50%）
    
    返回：
    {
        'passed': bool,
        'anomalies': list,
        'anomaly_count': int
    }
    """
    change_pct = abs(df['close'] - df['open']) / df['open']
    anomalies = df[change_pct > max_change]
    
    return {
        'passed': len(anomalies) == 0,
        'anomalies': anomalies.index.tolist(),
        'anomaly_count': len(anomalies),
        'max_change_observed': change_pct.max()
    }
```

**验收标准：**
- ✅ 异常K线 < 0.1%（允许极少数极端情况）

**异常处理：**
- 标记异常K线
- 人工审查（可能是闪崩、分叉等真实事件）
- 决定是保留还是排除

### 5. 成交量合理性检查

**定义：** 成交量不应为零或异常值。

**规则：**
```python
volume > 0
volume < 10 * median(volume)  # 不超过中位数10倍
```

**检查方法：**
```python
def check_volume_reasonableness(df: pd.DataFrame) -> dict:
    """
    检查成交量合理性
    
    返回：
    {
        'passed': bool,
        'zero_volume_count': int,
        'abnormal_volume_count': int
    }
    """
    zero_volume = df[df['volume'] == 0]
    
    median_volume = df['volume'].median()
    abnormal_volume = df[df['volume'] > 10 * median_volume]
    
    return {
        'passed': len(zero_volume) == 0 and len(abnormal_volume) == 0,
        'zero_volume_count': len(zero_volume),
        'abnormal_volume_count': len(abnormal_volume),
        'median_volume': median_volume
    }
```

**验收标准：**
- ✅ 零成交量K线 = 0
- ⚠️ 异常成交量K线 < 0.1%

### 6. 数据完整性检查

**定义：** 所有必需字段不能为空。

**必需字段：**
```python
REQUIRED_FIELDS = [
    'timestamp',
    'open',
    'high',
    'low',
    'close',
    'volume'
]
```

**检查方法：**
```python
def check_data_completeness(df: pd.DataFrame) -> dict:
    """
    检查数据完整性
    
    返回：
    {
        'passed': bool,
        'missing_fields': dict,
        'null_count': int
    }
    """
    missing_fields = {}
    
    for field in REQUIRED_FIELDS:
        if field not in df.columns:
            missing_fields[field] = 'column_missing'
        else:
            null_count = df[field].isnull().sum()
            if null_count > 0:
                missing_fields[field] = f'{null_count}_nulls'
    
    return {
        'passed': len(missing_fields) == 0,
        'missing_fields': missing_fields,
        'total_nulls': sum(df[f].isnull().sum() for f in REQUIRED_FIELDS if f in df.columns)
    }
```

**验收标准：**
- ✅ 所有字段完整，无 null 值

### 7. 数据版本记录

**定义：** 每个数据集必须有唯一的版本标识，确保可追溯。

**记录内容：**
```python
data_version = {
    'version_id': 'SHA256 hash',
    'source': 'binance',
    'symbol': 'BTC/USDT',
    'timeframe': '4h',
    'start_time': '2023-01-01 00:00:00 UTC',
    'end_time': '2024-12-31 23:59:59 UTC',
    'download_time': '2026-06-13 10:30:00 UTC',
    'row_count': 12000,
    'sha256': 'abc123...'
}
```

**生成方法：**
```python
import hashlib
import json

def generate_data_version(df: pd.DataFrame, metadata: dict) -> str:
    """
    生成数据版本哈希
    
    返回：SHA256 哈希值
    """
    # 数据内容哈希
    data_hash = hashlib.sha256(
        df.to_csv(index=False).encode()
    ).hexdigest()
    
    # 元数据哈希
    meta_hash = hashlib.sha256(
        json.dumps(metadata, sort_keys=True).encode()
    ).hexdigest()
    
    # 组合哈希
    combined_hash = hashlib.sha256(
        f"{data_hash}:{meta_hash}".encode()
    ).hexdigest()
    
    return combined_hash
```

**验收标准：**
- ✅ 每个数据集有唯一 SHA256
- ✅ 回测报告中记录使用的数据版本

---

## 数据修复策略

### 缺口处理规则

**优先级：**
1. **重新下载** - 如果交易所有数据
2. **标记跳过** - 如果交易所本身有缺口
3. **禁止插值** - 不允许自动插值填补

**示例：**
```python
def handle_gap(gap_start, gap_end):
    # 1. 尝试重新下载
    new_data = exchange.fetch_ohlcv(symbol, timeframe, gap_start, gap_end)
    
    if new_data is not None and len(new_data) > 0:
        return 'refetched'
    else:
        # 2. 标记跳过
        mark_as_gap(gap_start, gap_end, reason='exchange_no_data')
        return 'marked_as_gap'
```

### 异常K线处理

**策略：**
1. 标记为异常
2. 人工审查
3. 决定保留或排除
4. 记录处理决策

**不允许：**
- ❌ 自动修正价格
- ❌ 删除后不记录
- ❌ 静默插值

---

## 时区和时间规则

### 时区统一

**强制规则：** 所有时间统一使用 UTC

```python
# 存储
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

# 显示（可以转换）
df['timestamp_local'] = df['timestamp'].dt.tz_convert('Asia/Shanghai')
```

### K线闭合规则

**规则：** 策略只能使用已闭合的K线

```python
def is_candle_closed(timestamp, timeframe):
    """
    判断K线是否已闭合
    
    当前时间必须 >= K线结束时间
    """
    candle_end = timestamp + get_timeframe_delta(timeframe)
    return datetime.now(timezone.utc) >= candle_end
```

**回测中：** 自动满足（历史数据都是闭合的）  
**实盘中：** 必须检查K线是否闭合

---

## 数据存储格式

### 数据库表结构

```sql
CREATE TABLE ohlcv_data (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(5) NOT NULL,
    open NUMERIC(20, 8) NOT NULL,
    high NUMERIC(20, 8) NOT NULL,
    low NUMERIC(20, 8) NOT NULL,
    close NUMERIC(20, 8) NOT NULL,
    volume NUMERIC(30, 8) NOT NULL,
    data_version VARCHAR(64) NOT NULL,
    is_anomaly BOOLEAN DEFAULT FALSE,
    anomaly_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(timestamp, symbol, timeframe)
);

CREATE INDEX idx_ohlcv_timestamp ON ohlcv_data(timestamp);
CREATE INDEX idx_ohlcv_symbol ON ohlcv_data(symbol);
CREATE INDEX idx_ohlcv_version ON ohlcv_data(data_version);
```

### 元数据表

```sql
CREATE TABLE data_versions (
    version_id VARCHAR(64) PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(5) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    download_time TIMESTAMPTZ NOT NULL,
    row_count INTEGER NOT NULL,
    quality_check_passed BOOLEAN NOT NULL,
    quality_report JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Phase 1 验收清单

**必须全部通过：**

- [ ] 能下载 BTC/USDT 2年历史数据（1h, 4h, 1d）
- [ ] 能下载 ETH/USDT 2年历史数据（1h, 4h, 1d）
- [ ] 时间连续性检查：0 缺口
- [ ] 时间唯一性检查：0 重复
- [ ] 价格逻辑性检查：0 错误
- [ ] 价格合理性检查：异常K线 <0.1%
- [ ] 成交量合理性检查：0 零成交量
- [ ] 数据完整性检查：所有字段完整
- [ ] 每个数据集有 SHA256 版本记录
- [ ] 数据质量报告自动生成
- [ ] 异常处理规则文档化
- [ ] 时区统一为 UTC
- [ ] 数据可以成功加载到 TimescaleDB

---

## 数据质量报告格式

```json
{
  "version_id": "abc123...",
  "generated_at": "2026-06-13T10:30:00Z",
  "symbol": "BTC/USDT",
  "timeframe": "4h",
  "period": {
    "start": "2023-01-01T00:00:00Z",
    "end": "2024-12-31T23:59:59Z",
    "row_count": 12000
  },
  "quality_checks": {
    "time_continuity": {
      "passed": true,
      "gap_count": 0
    },
    "time_uniqueness": {
      "passed": true,
      "duplicate_count": 0
    },
    "price_logic": {
      "passed": true,
      "invalid_count": 0
    },
    "price_reasonableness": {
      "passed": true,
      "anomaly_count": 5,
      "anomaly_percentage": 0.04
    },
    "volume_reasonableness": {
      "passed": true,
      "zero_volume_count": 0,
      "abnormal_volume_count": 0
    },
    "data_completeness": {
      "passed": true,
      "null_count": 0
    },
    "version_recorded": {
      "passed": true,
      "sha256": "abc123..."
    }
  },
  "overall_passed": true,
  "anomalies": [
    {
      "timestamp": "2024-03-15T08:00:00Z",
      "type": "high_volatility",
      "reason": "Flash crash, price drop 35%",
      "action": "marked_as_anomaly"
    }
  ]
}
```

---

**文档状态：** ✅ 已批准  
**Phase：** Phase 1  
**优先级：** 最高  
**更新日期：** 2026-06-13
