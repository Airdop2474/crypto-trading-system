# 故障排查手册

**文档版本：** v1.0
**创建日期：** 2026-06-16
**状态：** ✅ 已批准
**对应门禁：** `LIVE_TRADING_CHECKLIST.md` §5「文档完整 → 故障排查手册」

---

## 目的

汇总系统常见故障的**症状 → 原因 → 解决**，配合 `OPERATIONS_MANUAL.md` 使用。

排查通用第一步：

```bash
python scripts/check_environment.py    # 6 项体检：Python/依赖/.env/配置/DB/目录
docker compose ps                      # 三服务是否 healthy
```

---

## 故障 1：数据库连不上

**症状：** `psycopg2.OperationalError`；`check_environment.py` 报 `PostgreSQL connection failed`。

**原因：** Docker 未起 / `TIMESCALE_*` 配错 / 5432 被占。

**解决：**
```bash
docker compose up -d timescaledb redis
docker compose exec timescaledb pg_isready -U postgres   # 期望 accepting connections
```
确认 `.env` 的 `TIMESCALE_PASSWORD` 与 compose 的 `POSTGRES_PASSWORD`（默认 `changeme`）一致。连接串形如 `postgresql://postgres:changeme@localhost:5432/crypto_trading`。

---

## 故障 2：Grafana 数据源连不上

**症状：** Grafana 面板报 "Data source error" / 认证失败。

**原因（均为已修复的真实坑，提交 `bc984c0`，复发时按此排查）：**
1. grafana 容器未注入 `POSTGRES_*` → 数据源回退到 OS 用户 `grafana` 认证失败。
2. 数据源 yml 用了 Grafana provisioning **不支持**的 `${VAR:-default}` shell 回退语法。

**解决：**
```bash
docker compose logs grafana                               # 看 provisioning 报错
docker compose exec timescaledb psql -U postgres -c "SELECT 1"   # 确认库可达
cat config/grafana/datasources/timescaledb.yml            # 确认是纯 ${VAR}，无 :-default
```
确认 `docker-compose.yml` 的 grafana service 已注入 `POSTGRES_USER/PASSWORD/DB`（当前已注入）。

---

## 故障 3：pytest 启动报 asyncio 冲突

**症状：** 收集阶段报 asyncio 插件冲突 / 用例无法收集。

**原因：** 环境装了 `pytest-asyncio`，与本项目收集器冲突；`pyproject.toml` 未配 `addopts` 自动屏蔽。

**解决：** 每次手动加 `-p no:asyncio`：
```bash
python -m pytest -p no:asyncio -q       # 基线 159 passed
```

---

## 故障 4：`ModuleNotFoundError: No module named 'src'`

**症状：** 直接跑某些入口时 import `src.*` 失败。

**原因：** 项目根不在 `PYTHONPATH`。

**解决：**
```bash
export PYTHONPATH=C:\Github\crypto-trading-system
```
`scripts/` 下脚本多已内部 `sys.path.insert` 项目根；以模块方式运行或新写脚本时仍需设此变量。

---

## 故障 5：`relation "monitor_metrics" does not exist`

**症状：** 落库 / Grafana 查询报表不存在。

**原因：** `config/sql/01_monitor_metrics.sql` 仅在数据卷为空的**首次启动**执行；卷非空首启或表被删则缺失。

**解决（脚本幂等，可重复执行）：**
```bash
docker exec -i crypto_trading_db psql -U postgres -d crypto_trading < config/sql/01_monitor_metrics.sql
# 验证
docker compose exec timescaledb psql -U postgres -d crypto_trading -c "\dt monitor_metrics"
```

---

## 故障 6：风控熔断后系统暂停，不再下单

**症状：** 日志出现 `RiskManager[PAUSE] ... -> PAUSED`，之后无新订单。

**原因：** 触发连续亏损 / 当日亏损 / API 连续失败 / 数据异常之一，状态进入 `PAUSED`（详见 `src/execution/risk_manager.py`）。

**识别与恢复：**
```python
from src.execution.risk_manager import RiskManager  # 运行中的实例

if risk_mgr.is_paused():
    print(risk_mgr.events[-1])     # 取最近事件的 reason
# 确认问题已解决后人工恢复：
risk_mgr.resume()                  # PAUSED -> ACTIVE（重置连亏/API 计数，保留当日盈亏）
```
若处于 `STOPPED`（紧急停止），须先 `risk_mgr.reset()` 回到 `ACTIVE`。实盘恢复须按 `LIVE_TRADING_CHECKLIST.md`「恢复流程」逐项确认，不可自动恢复。

---

## 故障 7：`run_paper_trading.py` 找不到数据

**症状：** `FileNotFoundError` / 提示未找到震荡数据。

**原因：** `data/raw/` 无 `BTC_USDT_4h_osc_*.csv`。

**解决：**
```bash
python scripts/generate_oscillating_data.py
```

---

## 升级路径

- 单点问题 → 对照上表「症状」定位。
- 整体环境可疑 → 重跑 `python scripts/check_environment.py`。
- 基础设施可疑 → `docker compose ps` + `docker compose logs <service>`。
- 仍无法定位 → 保留日志与 `data/reports/` 产出，记录复现步骤后人工介入。

---

**文档状态：** ✅ 已批准
**Phase：** Phase 6（实盘前置）
**更新日期：** 2026-06-16
