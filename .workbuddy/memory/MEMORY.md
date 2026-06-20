# 项目记忆

## 系统架构
- 后端：Python 3.13，FastAPI 暴露 REST API
- 前端：Next.js 16 + React 19 + Tailwind 4 + SWR 数据获取
- 策略引擎：事件驱动 bar-by-bar 回测，RiskAwareStrategy 基类
- 缓存：Redis（可用时）+ 内存回退

## 策略注册表 (8个)
grid | rsi | ma | buyhold | donchian | structure | supertrend | reversal

## 关键设计决策
- 所有策略继承 RiskAwareStrategy（熔断：连亏3次/日亏2%/回撤15%）
- 前端 SWR 配置：30s 刷新、3次重试、5s 间隔
- API 层无数据库依赖，数据来自 PaperTrading 引擎内存快照
