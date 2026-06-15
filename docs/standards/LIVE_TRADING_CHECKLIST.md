# 实盘交易门禁清单

**文档版本：** v1.0  
**创建日期：** 2026-06-13  
**状态：** ✅ 已批准

---

## 目的

本文档定义启用实盘交易（Phase 6）的前置条件和安全要求。

**核心原则：** 实盘前必须经过充分验证，保护资金安全优先。

---

## 前置条件（全部必须满足）

### 1. Paper Trading 验收

- [ ] **连续运行 60 天**，无系统故障
- [ ] 每日摘要报告完整（60份）
- [ ] 所有信号和订单可追溯
- [ ] 风控触发记录完整
- [ ] 模拟盘与回测偏差可解释
- [ ] 系统暂停和恢复机制测试通过

### 2. 风控测试

- [ ] 日亏损限制（3%）触发测试 ✅
- [ ] 连续亏损熔断（5笔）触发测试 ✅
- [ ] 数据异常熔断测试 ✅
- [ ] API 失败熔断测试 ✅
- [ ] 人工恢复流程测试 ✅
- [ ] 紧急停止机制测试 ✅

### 3. 系统稳定性

- [ ] **连续 3 周无系统故障**
- [ ] 无数据缺口或异常
- [ ] 无订单执行错误
- [ ] 日志完整可查
- [ ] 监控仪表盘正常

### 4. 代码质量

- [ ] 所有代码通过 review
- [ ] 单元测试覆盖率 >80%
- [ ] 集成测试通过
- [ ] 无高危安全漏洞
- [ ] 代码规范检查通过

### 5. 文档完整

- [ ] DATA_QUALITY_STANDARD.md ✅
- [ ] BACKTEST_VALIDATION.md ✅
- [ ] STRATEGY_ASSUMPTIONS.md ✅
- [ ] AI_USAGE_BOUNDARIES.md ✅
- [ ] LIVE_TRADING_CHECKLIST.md ✅（本文件）
- [ ] 操作手册（如何启动/停止）
- [ ] 故障排查手册

---

## API Key 安全要求

### 权限限制

- [ ] **只读查询权限** ✅
- [ ] **现货交易权限** ✅
- [ ] **禁止提币权限** ❌
- [ ] **禁止合约权限** ❌
- [ ] **禁止杠杆权限** ❌
- [ ] **禁止子账户操作** ❌

### API Key 配置

```python
API_KEY_CONFIG = {
    'permissions': [
        'spot_trade',  # 现货交易
        'account_read',  # 账户查询
    ],
    'ip_whitelist': ['YOUR_IP_ADDRESS'],  # IP 白名单
    'withdrawal_enabled': False,  # 禁止提币
    'leverage_enabled': False,  # 禁止杠杆
}
```

### 验证步骤

```python
# 实盘启动前验证
def verify_api_key_permissions():
    permissions = exchange.fetch_permissions()
    
    assert 'spot_trade' in permissions
    assert 'withdrawal' not in permissions
    assert 'margin_trade' not in permissions
    assert 'futures_trade' not in permissions
    
    print("✅ API Key 权限验证通过")
```

---

## 风控参数要求

### 必须设置的风控参数

```python
RISK_CONTROLS = {
    # 亏损限制
    'daily_loss_limit': 0.03,      # 日亏损 3% 熔断
    'max_drawdown_limit': 0.10,    # 最大回撤 10% 熔断
    
    # 仓位限制
    'max_position_per_trade': 0.20,  # 单笔 20%
    'max_total_position': 0.60,      # 总仓位 60%
    
    # 交易频率限制
    'max_trades_per_day': 10,
    'min_trade_interval': 300,  # 5分钟
    
    # 连续亏损熔断
    'max_consecutive_losses': 5,
    
    # 价格偏差限制
    'max_slippage': 0.005,  # 0.5%
    
    # 数据异常容忍
    'max_data_gap_minutes': 60,  # 1小时
}
```

### 实盘初期更严格

```python
# Phase 6 初期（前30天）
STRICT_RISK_CONTROLS = {
    'daily_loss_limit': 0.02,       # 2%（更严格）
    'max_total_position': 0.40,     # 40%（更保守）
    'max_trades_per_day': 5,        # 更少交易
}
```

---

## 初始资金要求

### 金额限制

- [ ] 初始资金 ≤ **$500**
- [ ] 是用户可承受的损失
- [ ] 不影响生活

### 资金增长规则

**禁止早期快速增加：**
```
Month 1-3: $500（验证阶段）
Month 4-6: $1000（如果前3月成功）
Month 7+: 根据表现逐步增加
```

**增加前提：**
- 连续 3 个月盈利
- 回撤始终 <10%
- 无严重风控事故
- 用户明确同意

---

## 实盘开关

### 手动开关（强制）

```python
# .env 文件
LIVE_TRADING_ENABLED=false  # 默认关闭

# 启用实盘需要明确修改
LIVE_TRADING_ENABLED=true
```

### 双重确认

```python
def start_live_trading():
    """启动实盘"""
    
    # 1. 环境变量检查
    if os.getenv('LIVE_TRADING_ENABLED') != 'true':
        raise Exception("实盘未启用")
    
    # 2. 命令行确认
    confirm = input("确认启动实盘交易？(YES/no): ")
    if confirm != "YES":
        raise Exception("用户取消")
    
    # 3. 门禁检查
    checklist_passed = verify_live_trading_checklist()
    if not checklist_passed:
        raise Exception("门禁检查未通过")
    
    # 4. 最后警告
    print("⚠️  即将启动实盘交易")
    print("⚠️  使用真实资金，存在亏损风险")
    final_confirm = input("最后确认 (YES/no): ")
    if final_confirm != "YES":
        raise Exception("用户取消")
    
    # 5. 启动
    print("✅ 实盘交易已启动")
    log_live_trading_start()
```

---

## 人工确认流程

### 每次参数变更

**必须人工确认：**
- 网格数量
- 价格区间
- 单网格仓位
- 风控参数

**流程：**
```python
def update_strategy_parameters(new_params: dict):
    """更新策略参数"""
    
    # 1. 显示变更
    show_parameter_diff(current_params, new_params)
    
    # 2. 风险评估
    risk = assess_parameter_risk(new_params)
    print(f"风险评级：{risk}")
    
    # 3. 人工确认
    confirm = input("确认变更？(YES/no): ")
    if confirm != "YES":
        return False
    
    # 4. 记录审计日志
    log_parameter_change(current_params, new_params, approved_by="user")
    
    # 5. 应用变更
    apply_parameters(new_params)
    
    return True
```

---

## 紧急停止流程

### 立即停止

**触发条件：**
1. 用户手动触发
2. 日亏损达到 5%
3. 系统检测到严重异常
4. 数据持续异常 >1小时

**停止步骤：**
```python
def emergency_stop(reason: str):
    """紧急停止"""
    
    # 1. 标记系统状态
    system_status = "EMERGENCY_STOPPED"
    
    # 2. 取消所有挂单
    cancel_all_orders()
    
    # 3. 记录原因
    log_emergency_stop(reason, timestamp=now())
    
    # 4. 发送告警
    send_alert(f"🚨 紧急停止：{reason}")
    
    # 5. 生成报告
    generate_emergency_report()
    
    # 6. 等待人工处理
    print("系统已紧急停止，等待人工恢复")
```

### 恢复流程

**不能自动恢复，必须：**
```python
def recover_from_emergency():
    """从紧急停止恢复"""
    
    # 1. 人工检查
    print("请检查以下内容：")
    checklist = [
        "系统日志是否有异常",
        "订单状态是否正常",
        "账户余额是否正确",
        "风控参数是否合理",
        "停止原因是否已解决"
    ]
    
    for item in checklist:
        confirm = input(f"✓ {item}？(y/n): ")
        if confirm != 'y':
            print("检查未通过，无法恢复")
            return False
    
    # 2. 确认恢复
    confirm = input("确认恢复交易？(YES/no): ")
    if confirm != "YES":
        return False
    
    # 3. 重置状态
    system_status = "RUNNING"
    log_system_recovery()
    
    print("✅ 系统已恢复")
    return True
```

---

## 禁止事项

### ❌ 绝对禁止

1. **跳过门禁检查**
2. **禁用风控**
3. **删除止损**
4. **超过仓位限制**
5. **交易小币种**（非 BTC/ETH）
6. **使用合约/杠杆**
7. **AI 自动调参**
8. **自动增加资金**

---

## 监控要求

### 实时监控

**必须实时监控：**
- 账户余额
- 持仓状态
- 未实现盈亏
- 订单状态
- 风控状态
- 系统健康

**监控工具：**
- Grafana 仪表盘
- Telegram/Email 告警

### 每日检查

- [ ] 查看昨日交易
- [ ] 检查风控日志
- [ ] 确认系统正常
- [ ] 审查异常信号

### 每周审计

- [ ] 生成周报
- [ ] AI 分析报告
- [ ] 参数是否需要调整（人工决策）
- [ ] 风控是否合理

---

## Phase 6 验收标准（用户修正版）⭐

**运行 90 天后验收：**

### 必须满足（核心）

1. **连续 3 个月无严重风控事故**
   - 未触发日亏损 5% 熔断
   - 未触发连续亏损 5 笔熔断
   - 风控日志完整

2. **回撤在预设范围内**
   - 最大回撤 <10%
   - 单日回撤 <3%
   - 回撤原因可解释

3. **结果可复盘**
   - 所有交易决策有记录
   - 所有风控触发有记录
   - 所有 NO_TRADE 和 PAUSE 有原因
   - 可生成完整复盘报告

4. **系统稳定**
   - 无数据异常
   - 无订单错误
   - 无系统故障

### 不要求

- ❌ 不要求"连续 3 个月不亏损"
- ❌ 不要求固定收益率
- ❌ 不要求与回测偏差 <固定值

**原因：**
市场不可预测，强行"不亏损"可能导致：
- 为了过关而不交易
- 过度拟合避免亏损
- 掩盖真实问题

**正确目标：**
系统稳定、风控有效、回撤可控、决策可追溯。

---

## 用户风险确认

### 必须签署（书面或电子）

**风险确认书：**

```
我已充分理解并同意：

1. 加密货币交易存在高风险，可能损失全部本金
2. 本系统为个人学习和研究项目，不保证盈利
3. 回测收益不代表实盘收益
4. 我只使用可承受损失的资金（≤$500）
5. 我理解并接受所有风险
6. 我不会因亏损追究系统开发者责任
7. 我会遵守所有安全规则和限制

签名：___________
日期：___________
```

---

## 实盘启动检查清单

**启动当天，逐项检查：**

### 环境检查
- [ ] .env 配置正确
- [ ] API Key 权限验证通过
- [ ] 数据库连接正常
- [ ] Redis 连接正常
- [ ] Grafana 仪表盘可访问

### 风控检查
- [ ] 风控参数已设置
- [ ] 熔断机制测试通过
- [ ] 紧急停止机制可用
- [ ] 告警通知正常

### 策略检查
- [ ] 策略参数已确认
- [ ] NO_TRADE 条件已设置
- [ ] PAUSE 条件已设置

### 资金检查
- [ ] 初始资金 ≤ $500
- [ ] 账户余额正确
- [ ] 无其他未平仓单

### 最终确认
- [ ] 用户风险确认书已签署
- [ ] 所有门禁条件满足
- [ ] 双重确认通过
- [ ] 准备启动实盘

---

**文档状态：** ✅ 已批准  
**Phase：** Phase 5-6  
**优先级：** 最高  
**更新日期：** 2026-06-13

**警告：实盘交易使用真实资金，务必严格遵守本清单！**
