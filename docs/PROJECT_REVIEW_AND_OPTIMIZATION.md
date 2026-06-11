# ALSA 项目评审与优化方案

> **评审日期**：2026-06-11
> **评审范围**：AI专家系统架构 + 金融分析架构
> **目标**：识别核心问题，制定可执行优化路线图

---

## 一、项目核心价值

ALSA = AI-powered Living Stock Analyst，核心创新点：

- **多专家协作**：10+AI角色模拟专业投研团队，通过辩论博弈生成决策
- **全链路覆盖**：数据采集→量化计算→多轮讨论→报告生成→交易日志
- **跨市场支持**：A股/美股/港股，多数据源（AkShare + Yahoo Finance）

---

## 二、架构优势总结

| 维度 | 亮点 | 证据 |
|------|------|------|
| **AI协作** | 辩论拓扑设计精妙 | 多空两轮对决 + Professional Reviewer纠偏 |
| **Prompt工程** | 角色定义严谨 | 25+模板，含输出纪律、自检清单、数据协议 |
| **数据架构** | 时序存储高效 | Parquet + DuckDB + Polars，查询性能5-10x Pandas |
| **LLM网关** | 多模型回退 | Gemini→DeepSeek→Default，RateLimiter防限流 |
| **风控设计** | 仓位管理意识 | 分步建仓计划 + 逻辑证伪止损 |

---

## 三、核心问题识别

### 🔴 P0 - 阻塞性问题（影响系统可用性/可信度）

| # | 问题 | 影响 | 当前状态 |
|---|------|------|---------|
| 1 | **无回测验证系统** | 无法证明AI分析准确性，用户信任度低 | 完全缺失 |
| 2 | **DEEP拓扑缩减严重** | 深度分析仅6轮，缺少多空辩论+风控量化 | 从10轮缩减到6轮 |

### 🟡 P1 - 重要问题（影响功能完整性）

| # | 问题 | 影响 | 当前状态 |
|---|------|------|---------|
| 3 | **无组合管理** | 单只股票分析优秀，但无法构建投资组合 | 缺失 |
| 4 | **LLM输出无结构化验证** | 关键字段（价格/仓位）可能格式错误 | 无JSON Schema校验 |
| 5 | **无实时行情推送** | WebSocket仅用于分析进度，缺少盘中行情 | 仅推送分析状态 |
| 6 | **选股策略静态** | 用户无法自定义筛选条件 | 硬编码5种策略 |

### 🟢 P2 - 优化项（提升体验/可维护性）

| # | 问题 | 影响 | 当前状态 |
|---|------|------|---------|
| 7 | **Prompt版本管理弱** | 无法A/B测试不同Prompt效果 | 有表无对比工具 |
| 8 | **宏观数据滞后** | 依赖搜索获取宏观数据 | 无预置日历 |
| 9 | **数据质量控制弱** | 异常值可能污染分析结果 | quality字段未自动校验 |
| 10 | **类型定义集中** | types.ts 735行，维护困难 | 单文件 |

---

## 四、优化方案详情

### 方案1：回测验证系统（P0）

**目标**：追踪AI预测 vs 实际涨跌，量化分析准确率

**架构设计**：
```
分析完成 → 存储预测(方向/目标价/时间维度)
    ↓
定期任务 → 拉取实际行情 → 计算偏差
    ↓
Dashboard → 准确率统计 + 净值曲线
```

**数据模型**：
```python
class PredictionRecord(SQLModel, table=True):
    prediction_id: str
    analysis_id: str  # 关联AnalysisRun
    symbol: str
    market: str
    predicted_direction: str  # up/down/neutral
    predicted_target_price: float
    predicted_timeframe: str  # 1w/1m/3m
    confidence: float
    created_at: datetime

class PredictionOutcome(SQLModel, table=True):
    outcome_id: str
    prediction_id: str
    actual_price_at_expiry: float
    actual_return_pct: float
    direction_correct: bool
    price_error_pct: float
    evaluated_at: datetime
```

**核心指标**：
- 方向准确率（Direction Accuracy）
- 目标价偏差（Price Error %）
- 按时间维度分层统计（1周/1月/3月）
- 按市场分层统计（A股/美股/港股）

**工作量估算**：3-5天

---

### 方案2：恢复完整DEEP拓扑（P0）

**目标**：恢复10轮完整讨论，提升分析深度

**当前拓扑（6轮）**：
```python
DEEP_TOPOLOGY = [
    {"round": 1, "experts": ["Deep Research Specialist"]},
    {"round": 2, "experts": ["Technical Analyst", "Fundamental Analyst"], "parallel": True},
    {"round": 3, "experts": ["Sentiment Analyst"]},
    {"round": 4, "experts": ["Serenity Alpha Analyst"]},
    {"round": 5, "experts": ["Professional Reviewer"]},
    {"round": 6, "experts": ["Chief Strategist"]},
]
```

**建议恢复（10轮）**：
```python
DEEP_TOPOLOGY = [
    {"round": 1, "experts": ["Deep Research Specialist"]},           # 数据地基
    {"round": 2, "experts": ["Technical Analyst", "Fundamental Analyst"], "parallel": True},  # 硬分析
    {"round": 3, "experts": ["Sentiment Analyst"]},                  # 情绪面
    {"round": 4, "experts": ["Bull Researcher", "Bear Researcher"], "parallel": True},  # 多空辩论①
    {"round": 5, "experts": ["Professional Reviewer"]},              # 逻辑纠偏
    {"round": 6, "experts": ["Aggressive Risk Analyst", "Conservative Risk Analyst", "Neutral Risk Analyst"], "parallel": True},  # 风控三视角
    {"round": 7, "experts": ["Contrarian Strategist"]},              # 逆向思维
    {"round": 8, "experts": ["Bull Researcher", "Bear Researcher"], "parallel": True},  # 多空辩论②
    {"round": 9, "experts": ["Risk Manager"]},                       # 风险量化
    {"round": 10, "experts": ["Chief Strategist"]},                  # 最终决策
]
```

**关键补充**：
- Round 4/8：多空两轮辩论，防止确认偏差
- Round 6：三位风险分析师并行，覆盖激进/保守/中性视角
- Round 7：逆向策略师挑战主流共识
- Round 9：Risk Manager做VaR/仓位/止损量化

**工作量估算**：1天（主要调整discussion_service.py）

---

### 方案3：组合管理模块（P1）

**目标**：支持多股票持仓、风险预算、再平衡

**核心功能**：
1. **持仓管理**：添加/删除持仓，记录成本价
2. **风险预算**：单只股票上限、行业集中度上限
3. **再平衡提醒**：偏离目标权重时触发
4. **组合分析**：相关性矩阵、波动率归因

**数据模型**：
```python
class Portfolio(SQLModel, table=True):
    portfolio_id: str
    user_id: str
    name: str
    created_at: datetime

class PortfolioPosition(SQLModel, table=True):
    position_id: str
    portfolio_id: str
    symbol: str
    market: str
    shares: int
    cost_price: float
    target_weight: float  # 目标权重%
    current_weight: float  # 当前权重%
    last_rebalance: datetime
```

**工作量估算**：5-7天

---

### 方案4：LLM输出结构化验证（P1）

**目标**：关键字段强制JSON Schema校验

**实现方式**：
```python
from pydantic import BaseModel, validator

class ChiefStrategistOutput(BaseModel):
    expected_price: float
    direction: str  # buy/hold/sell
    confidence: float
    position_plan: List[PositionLayer]
    
    @validator('direction')
    def validate_direction(cls, v):
        if v not in ['buy', 'hold', 'sell']:
            raise ValueError('direction must be buy/hold/sell')
        return v
    
    @validator('confidence')
    def validate_confidence(cls, v):
        if not 0 <= v <= 1:
            raise ValueError('confidence must be between 0 and 1')
        return v
```

**集成位置**：`discussion_service.py` 每轮输出后调用 `Model.parse_raw(output)`

**工作量估算**：2-3天

---

### 方案5：实时行情推送（P1）

**目标**：WebSocket支持盘中价格推送

**架构**：
```
前端订阅 → WebSocket → 后端行情服务 → AkShare/Yahoo实时API → 推送
```

**关键接口**：
```typescript
// 前端订阅
socket.emit('subscribe_realtime', { symbols: ['600519', 'AAPL'] });

// 后端推送
socket.emit('price_update', { symbol: '600519', price: 1850.00, change: 2.3 });
```

**工作量估算**：3-4天

---

## 五、技术债务清理

| 文件 | 问题 | 修复建议 |
|------|------|---------|
| `polars_indicators.py:32-33` | `ema_12`/`ema_26`变量未使用 | 删除冗余变量 |
| `llm_gateway.py:98` | `load_dotenv(override=False)`可能被覆盖 | 统一加载策略 |
| `types.ts` | 735行过于集中 | 按模块拆分为 `types/stock.ts`, `types/analysis.ts` 等 |

---

## 六、实施路线图

### Phase 1（1-2周）：可信度建设
- [ ] 实现回测验证系统（方案1）
- [ ] 恢复完整DEEP拓扑（方案2）
- [ ] 清理技术债务

### Phase 2（2-3周）：功能完善
- [ ] LLM输出结构化验证（方案4）
- [ ] 实时行情推送（方案5）
- [ ] 组合管理模块（方案3）

### Phase 3（3-4周）：体验优化
- [ ] Prompt版本对比工具
- [ ] 自定义选股策略
- [ ] 宏观日历集成

---

## 七、成功指标

| 指标 | 当前 | 目标（3个月后） |
|------|------|----------------|
| 方向准确率 | 未知 | >60% |
| 分析完成时间 | ~5分钟 | <3分钟（10轮） |
| 用户留存率 | 未知 | >40%（周活） |
| 组合管理覆盖率 | 0% | >50%用户使用 |

---

## 八、风险与缓解

| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 回测系统冷启动（无历史数据） | 高 | 先用模拟数据验证，逐步积累真实预测 |
| 10轮讨论耗时过长 | 中 | 支持"快速/标准/深度"三级，用户可选 |
| LLM输出格式不稳定 | 中 | 结构化验证 + 降级策略（格式错误时重试） |
| 实时行情API限流 | 低 | RateLimiter + 本地缓存 |

---

## 附录：文件修改清单

| 优先级 | 文件 | 修改内容 |
|--------|------|---------|
| P0 | `python_service/app/services/discussion_service.py` | 恢复DEEP_TOPOLOGY为10轮 |
| P0 | `python_service/app/db/models.py` | 新增PredictionRecord/PredictionOutcome模型 |
| P0 | `python_service/app/services/` | 新增backtest_service.py |
| P1 | `python_service/app/services/discussion_service.py` | 增加输出结构化验证 |
| P1 | `python_service/app/services/` | 新增portfolio_service.py |
| P1 | `server.ts` | WebSocket实时行情推送 |
| P2 | `src/types.ts` | 拆分为模块化类型定义 |
