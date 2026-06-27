# 策略分批运行计划

> 适用环境：RackNerd VPS（1 vCPU / 2GB RAM）
> 目标：49 个策略分批运行，**每批 3 个策略**，避免内存溢出导致 VPS 崩溃
> 教训：8 个策略同时跑会导致 VPS 崩溃，每批必须控制在 3-4 个以内
>
> **当前配置**：timeframe = `1h`，days = `20`（1h 周期 20 天 ≈ 480 根 K 线）
> **参数调整方案**：保持 K 线根数不变（策略 PARAM_SCHEMA 默认值不修改），1h 周期下信号频率约为 4h 的 4 倍，便于在 20 天内积累足够交易样本

---

## 一、资源约束（实测）

| 项目 | 数值 |
|---|---|
| VPS 规格 | 1 vCPU / 2GB RAM |
| 已占用（4 个基础容器） | ~1.2GB |
| 剩余可用 | ~800MB |
| 每策略 daemon 实例 | ~50-100MB（_history DataFrame + broker state + Python 进程开销） |
| **安全线** | **每批 3 个策略**（实测 8 个崩溃） |
| 风险线 | 4 个策略（接近上限） |
| 崩溃线 | 5+ 个策略（1vCPU 2GB 不可承受） |

### 实测记录

| 批次 | 策略数 | 结果 |
|---|---|---|
| 批次 1（原计划） | 8 个 | ❌ VPS 崩溃，页面连不上 |

---

## 二、批次总览（新方案：每批 3 个）

共 17 批跑完 49 个策略，每批 3 个（最后一批 1 个）。

| 批次 | 策略数 | 类型 | 复杂度 | 预估内存 |
|---|---|---|---|---|
| 批次 01 | 3 | 核心基准 | 轻-中 | ~200MB |
| 批次 02 | 3 | 核心趋势 | 中 | ~200MB |
| 批次 03 | 3 | 趋势突破 | 中 | ~200MB |
| 批次 04 | 3 | K 线形态 | 轻 | ~150MB |
| 批次 05 | 3 | K 线形态 | 轻 | ~150MB |
| 批次 06 | 3 | K 线形态 | 轻 | ~150MB |
| 批次 07 | 3 | K 线形态 | 轻 | ~150MB |
| 批次 08 | 3 | 时间过滤 | 轻 | ~150MB |
| 批次 09 | 3 | 量能统计 | 轻 | ~150MB |
| 批次 10 | 3 | 复合共振 | 中 | ~200MB |
| 批次 11 | 3 | 复合共振 | 中 | ~200MB |
| 批次 12 | 3 | 复合共振 | 中 | ~200MB |
| 批次 13 | 3 | 收缩/突破 | 中 | ~200MB |
| 批次 14 | 3 | 动量/形态 | 轻 | ~150MB |
| 批次 15 | 3 | 重型策略 | 重 | ~300MB |
| 批次 16 | 3 | 重型+剩余 | 中-重 | ~250MB |
| 批次 17 | 1 | 剩余 | 中 | ~100MB |

---

## 三、批次详情

### 批次 01：核心基准（推荐先跑）

**目的**：建立基准对比，验证系统能跑通。

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `grid` | 网格 | 震荡套利 | 重型（默认策略） |
| 2 | `buyhold` | 买入持有 | 基准对比 | 轻型 |
| 3 | `structure` | 市场结构 | 突破 | 轻型 |

```bash
API_TOKEN=$(grep "^API_TOKEN=" /root/crypto-trading-system/.env | cut -d= -f2- | tr -d '[:space:]')

curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["grid","buyhold","structure"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 02：核心趋势

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `ma` | 均线 | 趋势跟踪 | 中型 |
| 2 | `macd` | MACD | 趋势跟踪 | 中型 |
| 3 | `rsi` | RSI 动量 | 动量反转 | 中型 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["ma","macd","rsi"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 03：趋势突破

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `donchian` | 唐奇安 | 趋势突破 | 中型 |
| 2 | `supertrend` | 超级趋势 | 趋势跟踪 | 中型 |
| 3 | `reversal` | 关键位反转 | 分位+ATR | 中型 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["donchian","supertrend","reversal"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 04：K 线形态 A

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `closebreak` | 收盘突破 | 突破 | 轻 |
| 2 | `pullback` | 回踩突破 | 突破回踩 | 轻 |
| 3 | `ampbreak` | 幅度突破 | 突破 | 轻 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["closebreak","pullback","ampbreak"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 05：K 线形态 B

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `strongmom` | 强势收盘动量 | 动量 | 轻 |
| 2 | `purekeylvl` | 纯关键位反转 | 反转 | 轻 |
| 3 | `bigbar` | 大实体 | K 线形态 | 轻 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["strongmom","purekeylvl","bigbar"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 06：K 线形态 C

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `pinsmall` | Pin 小实体 | K 线形态 | 轻 |
| 2 | `morningstar` | 晨星 | K 线形态 | 轻 |
| 3 | `threesoldiers` | 三兵 | K 线形态 | 轻 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["pinsmall","morningstar","threesoldiers"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 07：K 线形态 D

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `wicksweep` | 影线扫损 | K 线形态 | 轻 |
| 2 | `confakeout` | 连续假突 | 计数 | 轻 |
| 3 | `bullengulfseq` | 阳包阴序列 | 形态序列 | 轻 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["wicksweep","confakeout","bullengulfseq"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 08：时间过滤

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `sessionfilter` | 时段过滤 | 时间过滤 | 轻 |
| 2 | `dayofweek` | 周内效应 | 时间过滤 | 轻 |
| 3 | `monthpos` | 月内位置 | 时间过滤 | 轻 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["sessionfilter","dayofweek","monthpos"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 09：量能统计

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `volbreakout` | 放量突破 | 量能 | 轻 |
| 2 | `volpricediv` | 量价背离 | 量能 | 轻 |
| 3 | `closemonotonic` | 收盘单调 | 统计 | 轻 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["volbreakout","volpricediv","closemonotonic"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 10：复合共振 A

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `confluence` | 多信号共振 | 多角度投票 | 中 |
| 2 | `weightedvote` | 加权投票 | 加权投票 | 中 |
| 3 | `mtfconfluence` | 多周期共振 | 多周期 | 中 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["confluence","weightedvote","mtfconfluence"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 11：复合共振 B

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `multiwinkey` | 多窗口关键位 | 多窗口 | 中 |
| 2 | `tfdivergence` | 周期背离 | 多周期 | 中 |
| 3 | `masterslave` | 主从 | 主辅信号 | 中 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["multiwinkey","tfdivergence","masterslave"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 12：复合共振 C

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `requiredcat` | 必含项 | 双确认 | 中 |
| 2 | `dualbreakout` | 双窗口突破 | 双窗口 | 中 |
| 3 | `multilevel` | 多级突破 | 双窗口 | 中 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["requiredcat","dualbreakout","multilevel"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 13：收缩/突破

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `squeeze` | 持续收缩突破 | 多窗口 | 中 |
| 2 | `qualitysqz` | 质量突破 | 双窗口 | 中 |
| 3 | `shortlongsqz` | 短长期收缩 | 多窗口 | 中 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["squeeze","qualitysqz","shortlongsqz"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 14：动量/形态

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `consmomentum` | 连续动量 | 连续同向 | 轻 |
| 2 | `accmomentum` | 递增动量 | 实体递增 | 轻 |
| 3 | `insidechain` | 内含线链 | 形态链 | 轻 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["consmomentum","accmomentum","insidechain"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 15：重型策略 A（单独跑）

**警告**：重型策略资源占用高，单独跑并密切监控。

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `composite` | 复合趋势 | 6 指标组合 | 重 |
| 2 | `priceaction` | 价格行为学 | 三层框架 | 重 |
| 3 | `bollinger` | 布林带均值回归 | 多指标 | 重 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["composite","priceaction","bollinger"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 16：剩余 A

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `decaykey` | 降权关键位 | 状态字典 | 轻 |
| 2 | `takerbuyratio` | 主动买盘比 | 量能 | 轻 |
| 3 | `hlexpansion` | 高低点扩散 | 统计 | 轻 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["decaykey","takerbuyratio","hlexpansion"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

### 批次 17：剩余 B（最后 1 个）

| 序号 | key | 中文名 | 风格 | 复杂度 |
|---|---|---|---|---|
| 1 | `closedist` | 收盘分布 | 统计 | 轻 |

```bash
curl -X POST http://localhost:8000/modes/live_paper/start \
  -H "X-API-Token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["closedist"],
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days": 20
  }'
```

---

## 四、通用操作命令

### 0. 提取 API_TOKEN

```bash
API_TOKEN=$(grep "^API_TOKEN=" /root/crypto-trading-system/.env | cut -d= -f2- | tr -d '[:space:]')
echo "API_TOKEN: $API_TOKEN"
```

### 1. 查看当前运行状态

```bash
cd /root/crypto-trading-system
docker compose ps
curl -s http://localhost:8000/health
curl -s http://localhost:8000/health/detailed -H "X-API-Token: $API_TOKEN"
```

### 2. 查看运行中的策略

```bash
curl -s http://localhost:8000/modes/status -H "X-API-Token: $API_TOKEN"
```

### 3. 停止当前批次

```bash
curl -X POST http://localhost:8000/modes/stop \
  -H "X-API-Token: $API_TOKEN"
sleep 5
curl -s http://localhost:8000/modes/status -H "X-API-Token: $API_TOKEN"
```

### 4. 资源监控

```bash
docker stats --no-stream
free -m
```

### 5. 日志查看

```bash
docker compose logs paper_daemon --tail 30
docker compose logs paper_daemon --tail 50 | grep -E "Error|451|启动|registered"
```

---

## 五、批次运行流程（每批）

### Step 1：启动前检查

```bash
# 确认服务健康
curl -s http://localhost:8000/health

# 确认无其他策略运行
curl -s http://localhost:8000/modes/status -H "X-API-Token: $API_TOKEN"

# 记录基线内存
free -m | grep Mem
```

### Step 2：启动批次

```bash
# 执行对应批次的启动命令（见上文）
```

### Step 3：启动后验证（10 秒内）

```bash
sleep 10
docker compose ps
curl -s http://localhost:8000/modes/status -H "X-API-Token: $API_TOKEN"
docker stats --no-stream
```

### Step 4：运行中监控（5 分钟后）

```bash
# 资源占用
docker stats --no-stream
free -m

# 策略是否正常产出信号
docker compose logs paper_daemon --tail 30 | grep -E "signal|trade|order"
```

### Step 5：停止批次（运行 N 天后）

```bash
curl -X POST http://localhost:8000/modes/stop -H "X-API-Token: $API_TOKEN"
sleep 5
curl -s http://localhost:8000/modes/status -H "X-API-Token: $API_TOKEN"
```

---

## 六、观察记录模板

### 批次运行记录

| 批次 | 启动时间 | 策略数 | 初始内存 | 5 分钟后内存 | 1 小时后内存 | CPU 平均 | 状态 |
|---|---|---|---|---|---|---|---|
| 01 | | 3 | | | | | |
| 02 | | 3 | | | | | |
| 03 | | 3 | | | | | |
| 04 | | 3 | | | | | |
| 05 | | 3 | | | | | |
| 06 | | 3 | | | | | |
| 07 | | 3 | | | | | |
| 08 | | 3 | | | | | |
| 09 | | 3 | | | | | |
| 10 | | 3 | | | | | |
| 11 | | 3 | | | | | |
| 12 | | 3 | | | | | |
| 13 | | 3 | | | | | |
| 14 | | 3 | | | | | |
| 15 | 3 | | | | | | |
| 16 | | 3 | | | | | |
| 17 | | 1 | | | | | |

### 策略表现记录（按批次填写）

#### 批次 01 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| grid | 网格 | | | | | |
| buyhold | 买入持有 | | | | | |
| structure | 市场结构 | | | | | |

#### 批次 02 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| ma | 均线 | | | | | |
| macd | MACD | | | | | |
| rsi | RSI 动量 | | | | | |

#### 批次 03 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| donchian | 唐奇安 | | | | | |
| supertrend | 超级趋势 | | | | | |
| reversal | 关键位反转 | | | | | |

#### 批次 04 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| closebreak | 收盘突破 | | | | | |
| pullback | 回踩突破 | | | | | |
| ampbreak | 幅度突破 | | | | | |

#### 批次 05 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| strongmom | 强势收盘动量 | | | | | |
| purekeylvl | 纯关键位反转 | | | | | |
| bigbar | 大实体 | | | | | |

#### 批次 06 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| pinsmall | Pin 小实体 | | | | | |
| morningstar | 晨星 | | | | | |
| threesoldiers | 三兵 | | | | | |

#### 批次 07 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| wicksweep | 影线扫损 | | | | | |
| confakeout | 连续假突 | | | | | |
| bullengulfseq | 阳包阴序列 | | | | | |

#### 批次 08 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| sessionfilter | 时段过滤 | | | | | |
| dayofweek | 周内效应 | | | | | |
| monthpos | 月内位置 | | | | | |

#### 批次 09 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| volbreakout | 放量突破 | | | | | |
| volpricediv | 量价背离 | | | | | |
| closemonotonic | 收盘单调 | | | | | |

#### 批次 10 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| confluence | 多信号共振 | | | | | |
| weightedvote | 加权投票 | | | | | |
| mtfconfluence | 多周期共振 | | | | | |

#### 批次 11 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| multiwinkey | 多窗口关键位 | | | | | |
| tfdivergence | 周期背离 | | | | | |
| masterslave | 主从 | | | | | |

#### 批次 12 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| requiredcat | 必含项 | | | | | |
| dualbreakout | 双窗口突破 | | | | | |
| multilevel | 多级突破 | | | | | |

#### 批次 13 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| squeeze | 持续收缩突破 | | | | | |
| qualitysqz | 质量突破 | | | | | |
| shortlongsqz | 短长期收缩 | | | | | |

#### 批次 14 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| consmomentum | 连续动量 | | | | | |
| accmomentum | 递增动量 | | | | | |
| insidechain | 内含线链 | | | | | |

#### 批次 15 表现（重型）

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| composite | 复合趋势 | | | | | |
| priceaction | 价格行为学 | | | | | |
| bollinger | 布林带均值回归 | | | | | |

#### 批次 16 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| decaykey | 降权关键位 | | | | | |
| takerbuyratio | 主动买盘比 | | | | | |
| hlexpansion | 高低点扩散 | | | | | |

#### 批次 17 表现

| key | 中文名 | 总交易数 | 胜率 | P&L | 最大回撤 | 备注 |
|---|---|---|---|---|---|---|
| closedist | 收盘分布 | | | | | |

---

## 七、异常处理

### VPS 崩溃（页面连不上）

```bash
# 1. 本地 ping 测试
ping 192.210.197.57

# 2. SSH 尝试
ssh -p 14159 root@192.210.197.57

# 3. SSH 连不上 → 用 RackNerd VNC 控制台登录
#    - 重启 VPS: reboot
#    - 重启后停止 paper_daemon:
cd /root/crypto-trading-system
docker compose stop paper_daemon
docker compose up -d timescaledb redis grafana trading_system
```

### 内存告警（>1.8GB）

```bash
# 立即停止当前批次
curl -X POST http://localhost:8000/modes/stop -H "X-API-Token: $API_TOKEN"

# 查看内存
free -m

# 清理 Redis 缓存
docker compose exec redis redis-cli FLUSHALL

# 如果内存仍紧张，重启服务
docker compose restart
```

### Binance API 451

```bash
# 测试容器内能否访问 Binance
docker compose exec trading_system curl -s -o /dev/null -w "HTTP %{http_code}\n" -m 10 https://api.binance.com/api/v3/ping

# 期望 200，如果是 451：
# 1. 检查 Clash 是否运行：ps aux | grep mihomo
# 2. 检查 docker-compose.yml 是否配了 HTTP_PROXY
# 3. 检查 Clash allow-lan 是否开启
```

### 策略启动失败

```bash
# 查看错误日志
docker compose logs paper_daemon --tail 50 | grep -A 5 "Error"

# 常见原因：
# 1. 451 → VPN 代理未生效
# 2. 数据库连接失败 → 检查 .env 密码
# 3. 策略 key 拼错 → 对照本计划的 key 列表
# 4. 内存不足 → 减少策略数到 2 个
```

### 策略无信号产出

```bash
# 查看策略是否真的在运行
curl -s http://localhost:8000/modes/status -H "X-API-Token: $API_TOKEN"

# 查看 daemon 是否在拉 K 线
docker compose logs paper_daemon --tail 30 | grep -E "fetch_ohlcv|bar|tick"

# 某些策略本身信号稀少（如 morningstar 可能几天才一次），属正常
```

---

## 八、批次总结模板

### 批次 ___ 总结

- **运行时间**：____ 年 __ 月 __ 日 ~ ____ 年 __ 月 __ 日
- **运行天数**：___ 天
- **策略数**：___ 个
- **总交易数**：___ 笔
- **整体 P&L**：___%
- **最佳策略**：____（P&L ___%）
- **最差策略**：____（P&L ___%）
- **资源占用峰值**：内存 ___MB / CPU ___%
- **异常事件**：____________________
- **是否进入下一批**：是 / 否
- **备注**：____________________

---

## 九、附录：所有 49 个策略完整清单

| # | key | 中文名 | 批次 | 复杂度 |
|---|---|---|---|---|
| 1 | grid | 网格 | 01 | 重 |
| 2 | buyhold | 买入持有 | 01 | 轻 |
| 3 | structure | 市场结构 | 01 | 轻 |
| 4 | ma | 均线 | 02 | 中 |
| 5 | macd | MACD | 02 | 中 |
| 6 | rsi | RSI 动量 | 02 | 中 |
| 7 | donchian | 唐奇安 | 03 | 中 |
| 8 | supertrend | 超级趋势 | 03 | 中 |
| 9 | reversal | 关键位反转 | 03 | 中 |
| 10 | closebreak | 收盘突破 | 04 | 轻 |
| 11 | pullback | 回踩突破 | 04 | 轻 |
| 12 | ampbreak | 幅度突破 | 04 | 轻 |
| 13 | strongmom | 强势收盘动量 | 05 | 轻 |
| 14 | purekeylvl | 纯关键位反转 | 05 | 轻 |
| 15 | bigbar | 大实体 | 05 | 轻 |
| 16 | pinsmall | Pin 小实体 | 06 | 轻 |
| 17 | morningstar | 晨星 | 06 | 轻 |
| 18 | threesoldiers | 三兵 | 06 | 轻 |
| 19 | wicksweep | 影线扫损 | 07 | 轻 |
| 20 | confakeout | 连续假突 | 07 | 轻 |
| 21 | bullengulfseq | 阳包阴序列 | 07 | 轻 |
| 22 | sessionfilter | 时段过滤 | 08 | 轻 |
| 23 | dayofweek | 周内效应 | 08 | 轻 |
| 24 | monthpos | 月内位置 | 08 | 轻 |
| 25 | volbreakout | 放量突破 | 09 | 轻 |
| 26 | volpricediv | 量价背离 | 09 | 轻 |
| 27 | closemonotonic | 收盘单调 | 09 | 轻 |
| 28 | confluence | 多信号共振 | 10 | 中 |
| 29 | weightedvote | 加权投票 | 10 | 中 |
| 30 | mtfconfluence | 多周期共振 | 10 | 中 |
| 31 | multiwinkey | 多窗口关键位 | 11 | 中 |
| 32 | tfdivergence | 周期背离 | 11 | 中 |
| 33 | masterslave | 主从 | 11 | 中 |
| 34 | requiredcat | 必含项 | 12 | 中 |
| 35 | dualbreakout | 双窗口突破 | 12 | 中 |
| 36 | multilevel | 多级突破 | 12 | 中 |
| 37 | squeeze | 持续收缩突破 | 13 | 中 |
| 38 | qualitysqz | 质量突破 | 13 | 中 |
| 39 | shortlongsqz | 短长期收缩 | 13 | 中 |
| 40 | consmomentum | 连续动量 | 14 | 轻 |
| 41 | accmomentum | 递增动量 | 14 | 轻 |
| 42 | insidechain | 内含线链 | 14 | 轻 |
| 43 | composite | 复合趋势 | 15 | 重 |
| 44 | priceaction | 价格行为学 | 15 | 重 |
| 45 | bollinger | 布林带均值回归 | 15 | 重 |
| 46 | decaykey | 降权关键位 | 16 | 轻 |
| 47 | takerbuyratio | 主动买盘比 | 16 | 轻 |
| 48 | hlexpansion | 高低点扩散 | 16 | 轻 |
| 49 | closedist | 收盘分布 | 17 | 轻 |

---

**文档版本**：v2.0（修订版）
**创建日期**：2026-06-27
**修订日期**：2026-06-27（8 策略崩溃后改为每批 3 个）
**适用 VPS**：RackNerd 1vCPU / 2GB RAM
**教训**：1vCPU 2GB 最多跑 3-4 个策略，8 个会导致 VPS 崩溃
