# 🔒 上线前综合审查报告

**审查日期**：2026-06-20  
**审查方式**：7 位专家并行独立审查  
**审查范围**：全项目 250+ 源文件（后端 150+ Python / 前端 60+ TSX / 配置 15+）

---

## 审查团

| 专家 | 角色 | 审查重点 | 发现问题 |
|------|------|----------|----------|
| 许清楚 | PM | 需求完整性、文档一致性、前端后端对齐 | 7 项（含 7 P0） |
| 高见远 | 架构师 | 交易引擎安全性、前视偏差、并发、熔断 | 15 项（含 4 CRITICAL） |
| 贾思敏 | 前端 | UI 三态、React 性能、无障碍、类型安全 | 62 项（含 12 P0） |
| 贝洛奇 | 后端 | API 限流、错误处理、依赖、测试覆盖 | 17 项（含 2 阻塞） |
| 严过关 | 测试 | 测试套件、边界验证、数据完整性 | 12 项（含 0 P0） |
| 卜宕机 | 运维 | 部署配置、密钥安全、依赖锁定 | 19 项（含 3 CRITICAL） |
| 颜好看 | 设计 | UI 一致性、暗黑模式、反模式检测 | 17 项（含 2 P0） |

---

## 共识发现（被 ≥2 位专家独立确认）

| # | 问题 | 确认专家 | 严重度 |
|---|------|----------|--------|
| 1 | `.env` 含真实 Binance testnet API 密钥 | PM、架构、运维、测试 | 🔴 CRITICAL |
| 2 | Grafana `admin/admin` + PG `changeme` 硬编码 | 架构、运维、测试 | 🔴 CRITICAL |
| 3 | `install.cmd` 文件内容损坏（HTML 页面） | 运维 | 🔴 CRITICAL |
| 4 | `strategy-performance.tsx` 违反 emoji/硬编码色/DRY 红线 | 前端、设计 | 🔴 P0 |
| 5 | `next.config.mjs` `ignoreBuildErrors: true` | 前端、设计、运维 | 🔴 P0 |
| 6 | API 认证未覆盖全部端点（6 个无保护） | 架构 | 🔴 CRITICAL |
| 7 | 策略熔断无自动恢复机制 | 架构 | 🔴 CRITICAL |
| 8 | 前后端策略类型不一致（sma/ma, price-action 无对应） | PM、前端 | 🔴 P0 |
| 9 | mock-data.ts 含禁止交易对（SOL/BNB/XRP/DOGE）+ 杠杆 | PM | 🔴 P0 |
| 10 | `scripts/run_backtest.py` 第 222/224 行 `getattr` 4 参数会 TypeError | 后端 | 🔴 阻塞 |
| 11 | 缺失 Dockerfile，docker-compose 无法构建 | 运维 | 🔴 CRITICAL |
| 12 | Paper Trading 60 天运行零进度 | PM | 🔴 P0 |

---

## 综合评审结论

### ❌ 当前不可上线

**需完成 12 项阻塞修复** 才能进入上线流程。以下是按类别归并后的优先级清单：

### 🔴 P0 / CRITICAL — 必须修复（12 项）

#### 安全（4 项）
| # | 问题 | 修复方案 | 工作量 |
|---|------|----------|--------|
| S1 | .env 含真实 API 密钥 | 轮换 Binance testnet key，加 pre-commit gitleaks hook | 15min |
| S2 | Grafana/PG/Redis 默认密码 | docker-compose 从 .env 读取，默认值留空 | 15min |
| S3 | API 认证未覆盖 6 端点 | 添加 `Security(verify_api_token)` | 30min |
| S4 | next.config.mjs ignoreBuildErrors | 设为 false，加安全头（CSP/HSTS/X-Frame） | 1h |

#### 功能正确性（4 项）
| # | 问题 | 修复方案 | 工作量 |
|---|------|----------|--------|
| F1 | run_backtest.py getattr TypeError | ✅ **已修复** — 4 参数→3 参数，hyphen→underscore | ✅ Done |
| F2 | 策略熔断无恢复 | 添加 `resume()` 方法 + 日切自动重置 | 1-2h |
| F3 | 多策略共享 Broker 资金竞争 | 文档标注共享模式，或改为独立 Broker per 策略 | 2-4h |
| F4 | 前后端策略类型不一致 | 统一为后端 registry key；price-action→donchian/structure/supertrend/reversal | 1h |

#### 部署（3 项）
| # | 问题 | 修复方案 | 工作量 |
|---|------|----------|--------|
| D1 | 无 Dockerfile | 创建多阶段 Python Dockerfile | 1h |
| D2 | install.cmd 损坏 | 从 git 历史恢复或用 start_dashboard.bat 替代 | 15min |
| D3 | Docker 镜像标签 `latest` | 固定 TimescaleDB/Redis 到具体版本 | 10min |

#### 前端合规（1 项）
| # | 问题 | 修复方案 | 工作量 |
|---|------|----------|--------|
| U1 | strategy-performance.tsx 四项违规 | emoji→Lucide 图标、硬编码色→Token、去重格式化函数、改用 api 模块 | 1h |

#### 文档对齐（1 项）
| # | 问题 | 修复方案 | 工作量 |
|---|------|----------|--------|
| M1 | mock-data.ts 禁止交易对+杠杆 | 限制为 BTC/ETH 现货，移除 leverage 字段 | 30min |

---

### 🟡 HIGH — 上线同步修复（8 项）

| # | 问题 | 来源 |
|---|------|------|
| H1 | `float("inf")` JSON 序列化失败 | 后端 |
| H2 | 文件写入缺原子性保护 | 后端 |
| H3 | requirements.txt websockets 未锁定版本 | 后端/运维 |
| H4 | 无日志轮转（单文件 4.6MB） | 运维/测试 |
| H5 | CI Actions 版本过旧（v3→v4） | 运维 |
| H6 | market_classifier.py 覆盖率仅 17% | 测试 |
| H7 | 前端所有页面 SWR 不暴露 error 状态 | 前端 |
| H8 | 前端 skeleton 组件缺 aria-hidden | 前端 |

---

### 🟢 测试验证结果

| 指标 | 值 | 判定 |
|------|-----|------|
| 单元测试 | 443 passed / 0 failed / 4 skipped | ✅ |
| 覆盖率 | 83% | ✅ ≥80% |
| P0 缺陷 | 0 个 | ✅ |
| 8 策略边界验证 | 全部通过 | ✅ |
| CSV 数据质量 | 7/7 | ✅ |
| 日志异常 | 无生产错误 | ✅ |
| 前视偏差 | 未检测到 | ✅ |

---

## 修复后的上线流程

1. ✅ 完成所有 12 项 P0 修复
2. ✅ 修复 8 项 HIGH 问题
3. 轮换暴露的 API Key
4. 启动 Paper Trading 60 天运行
5. 60 天后：实盘上线
