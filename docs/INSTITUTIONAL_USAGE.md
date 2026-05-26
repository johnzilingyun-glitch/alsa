# 机构级模块功能使用说明

> 适用于 ALSA 机构级风控 / 运维 / 回测模块的日常使用与运维操作指南。

---

## 1. 紧急熔断开关 (Kill Switch)

### 1.1 查看当前状态
```bash
curl http://localhost:8001/api/institutional/kill-switch
```
返回示例：
```json
{
  "state": "ACTIVE",
  "triggered_at": null,
  "trigger": null,
  "reason": null
}
```

### 1.2 触发熔断
当系统出现异常（如行情数据中断、模型输出质量骤降）时，立即停止所有新订单提交：
```bash
curl -X POST http://localhost:8001/api/institutional/kill-switch/trigger \
  -H "Content-Type: application/json" \
  -d '{"trigger": "MANUAL_OPERATOR", "reason": "行情源异常，暂停交易"}'
```

**支持的触发器类型 (trigger)**：
| 触发器 | 场景 |
|:---|:---|
| `MANUAL_OPERATOR` | 运维人员手动触发 |
| `DAILY_LOSS_LIMIT` | 日内亏损超限 |
| `POSITION_LIMIT_BREACH` | 持仓比例超限 |
| `DATA_FEED_FAILURE` | 行情/数据源中断 |
| `MODEL_QUALITY_DEGRADATION` | 模型输出质量骤降 |
| `CONNECTIVITY_LOSS` | 网络连接丢失 |
| `REGULATORY_HALT` | 监管暂停 |
| `SYSTEM_ERROR` | 系统内部错误 |

### 1.3 熔断后的行为
- `can_submit_order()` → 返回 `False`（禁止新开仓）
- `can_reduce_risk()` → 返回 `True`（允许减仓/平仓）
- `can_cancel_order()` → 返回 `True`（允许撤单）

### 1.4 重置熔断
需经过审批流程，提供审批 ID：
```bash
curl -X POST http://localhost:8001/api/institutional/kill-switch/reset \
  -H "Content-Type: application/json" \
  -d '{"approval_id": "APPROVAL-2025-0601-001"}'
```

---

## 2. 盘前风控校验 (Pre-Trade Risk Check)

### 2.1 提交风控校验请求
在下单前调用此接口，系统会检查仓位限制、集中度、日内暴露等：
```bash
curl -X POST http://localhost:8001/api/institutional/risk/pre-trade-check \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "600519",
    "side": "BUY",
    "notional": 500000,
    "portfolio_value": 10000000,
    "existing_position_notional": 800000,
    "daily_new_exposure_so_far": 1500000
  }'
```

返回示例：
```json
{
  "approved": true,
  "violations": []
}
```

如果被拒绝：
```json
{
  "approved": false,
  "violations": [
    {"rule": "SINGLE_NAME_WEIGHT_LIMIT", "message": "Single name weight 13.0% exceeds limit 10.0%"}
  ]
}
```

### 2.2 风控规则说明
| 规则 | 默认阈值 | 说明 |
|:---|:---|:---|
| `MAX_SINGLE_ORDER` | ¥10,000,000 | 单笔下单金额上限 |
| `MAX_POSITION` | ¥50,000,000 | 单票持仓总额上限 |
| `SINGLE_NAME_WEIGHT_LIMIT` | 10% | 单票占组合市值比例上限 |
| `DAILY_EXPOSURE_LIMIT` | 25% | 日内新增暴露占组合比例上限 |

---

## 3. 交易字段校验 (Trading Fields Validator)

此模块在每次分析任务完成时**自动运行**，校验 AI 首席策略师给出的交易计划字段。

### 3.1 校验规则
- **价格字段**：必须为具体数值，拒绝模糊表述（"约185元"、"185附近"、"左右"）
- **仓位字段**：必须为数值百分比
- **评分字段**：必须在合理范围内
- **交叉校验**：止损价 < 当前价 < 目标价（做多时）

### 3.2 查看校验结果
在分析任务的 `tradingPlan` 字段中：
```json
{
  "tradingPlan": {
    "entryPrice": "185.00",
    "stopLoss": "170.00",
    "targetPrice": "220.00",
    "_validated": true,
    "_validation_errors": []
  }
}
```

若校验失败：
```json
{
  "_validated": false,
  "_validation_errors": ["entryPrice contains qualifier (约/左右/附近)"]
}
```

---

## 4. 系统可观测性 (Observability)

### 4.1 查看指标摘要
```bash
curl http://localhost:8001/api/institutional/metrics/summary
```
返回示例：
```json
{
  "api_latency_ms": {
    "count": 1234,
    "mean": 45.2,
    "p50": 32.0,
    "p95": 120.0,
    "p99": 450.0
  }
}
```

### 4.2 查看审计日志
```bash
curl "http://localhost:8001/api/institutional/audit/recent?limit=20"
```
返回示例：
```json
[
  {
    "timestamp": "2025-06-01T10:30:00Z",
    "action": "KILL_SWITCH_TRIGGERED",
    "actor": "operator:zhangsan",
    "details": {"trigger": "MANUAL_OPERATOR", "reason": "行情源异常"}
  }
]
```

**审计动作类型**：
`ORDER_SUBMITTED`, `ORDER_CANCELLED`, `KILL_SWITCH_TRIGGERED`, `KILL_SWITCH_RESET`, `RISK_CHECK_PASSED`, `RISK_CHECK_FAILED`, `POSITION_OPENED`, `POSITION_CLOSED`, `CONFIG_CHANGED`, `MODEL_PROMOTED`

---

## 5. 回测引擎 (Backtest Engine)

### 5.1 Python API 使用

```python
from python_service.app.backtest.engine import BacktestEngine
from python_service.app.backtest.costs import CostModel
from python_service.app.backtest.simulator import ExecutionSimulator

# 初始化
cost_model = CostModel()  # A 股默认费率
simulator = ExecutionSimulator()
engine = BacktestEngine(
    initial_cash=1_000_000,
    cost_model=cost_model,
    simulator=simulator,
)

# 逐日回放
for bar in daily_bars:
    engine.on_bar(bar)
    # 提交订单
    engine.submit_order(symbol="600519", side="BUY", price=1850.0, quantity=100)

# 获取绩效
metrics = engine.get_metrics()
print(f"总收益: {metrics.total_return:.2%}")
print(f"最大回撤: {metrics.max_drawdown:.2%}")
print(f"夏普比率: {metrics.sharpe_ratio:.2f}")
```

### 5.2 成本模型参数
| 费用项 | 默认值 | 说明 |
|:---|:---|:---|
| 佣金 | 0.025% (双边) | 可自定义 |
| 印花税 | 0.05% (卖出) | A 股固定费率 |
| 滑点估算 | 基于成交量 | 量越小滑点越大 |

### 5.3 成交模拟器规则
- 涨停板：买入订单被拒绝
- 跌停板：卖出订单被拒绝
- 停牌：所有订单被拒绝

---

## 6. 模型评估框架 (Model Evaluator)

### 6.1 Python API 使用
```python
from python_service.app.evaluation.model_eval import ModelEvaluator, EvalSuite, EvalCase

evaluator = ModelEvaluator()

# 定义测试套件
suite = EvalSuite(
    name="trading_plan_quality",
    cases=[
        EvalCase(input="分析贵州茅台", expected_contains=["止损", "目标价", "仓位"]),
        EvalCase(input="分析不存在的股票XYZ", expected_contains=["无法找到"]),
    ],
    pass_threshold=0.8,
)

# 对比两个模型版本
result = evaluator.compare(
    suite=suite,
    baseline_fn=old_model_generate,
    candidate_fn=new_model_generate,
)
print(f"基线通过率: {result.baseline_pass_rate:.0%}")
print(f"候选通过率: {result.candidate_pass_rate:.0%}")
```

---

## 7. PromptOps 版本治理

### 7.1 Prompt 生命周期
```
DRAFT → ACTIVE → CANARY → ACTIVE (promoted) 或 DEPRECATED
```

### 7.2 Python API 使用
```python
from python_service.app.prompting.version_registry import PromptVersionRegistry

registry = PromptVersionRegistry()

# 注册新版本
v = registry.register(
    prompt_id="chief_strategist_v2",
    template="你是首席策略师...",
    metadata={"author": "zhangsan", "change": "增加止损逻辑强化"}
)

# 激活
registry.activate(v.version_id)

# 灰度 (canary)
registry.promote_to_canary(v.version_id)

# 记录运行指标
registry.record_run(v.version_id, latency_ms=1200, success=True, score=0.85)

# 查看统计
stats = registry.get_version_stats(v.version_id)
print(f"平均分: {stats['mean_score']:.2f}, 成功率: {stats['success_rate']:.0%}")
```

---

## 8. 每日对账 (Reconciliation)

### 8.1 Python API 使用
```python
from python_service.app.reconciliation.engine import ReconciliationEngine

engine = ReconciliationEngine()

# 添加内部记录
engine.add_internal_position("600519", quantity=100, avg_cost=1850.0)
engine.set_internal_cash(850_000.0)

# 添加外部（券商）记录
engine.add_external_position("600519", quantity=100, market_value=185_000.0)
engine.set_external_cash(850_050.0)  # 微小差异

# 执行对账
result = engine.reconcile()
print(f"持仓匹配: {result.positions_matched}")
print(f"现金差异: ¥{result.cash_difference:.2f}")
print(f"通过: {result.passed}")  # 在容差范围内则 True
```

---

## 9. 部署注意事项

1. **无需额外依赖**：所有新模块使用纯 Python + 已有依赖（pydantic, SQLModel），无新增 pip 包。
2. **内存单例**：`KillSwitch`、`MetricsCollector` 等为进程内单例，重启后状态丢失。生产环境建议接入 Redis 做持久化。
3. **测试数据库**：测试使用独立的 `python_service/data/test_app.db`，不影响生产数据。
4. **API 路由注册**：通过 `python_service/app/api/router.py` 统一注册，新增模块只需 `include_router`。
5. **中间件顺序**：metrics 中间件在 CORS 之后注册，确保所有跨域请求都被正确计量。
