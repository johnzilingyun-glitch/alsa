# ALSA Phase 2 实施计划：金融准确性、风控缺陷、性能瓶颈

> **基于**: AUDIT_OPTIMIZATION_REPORT.md + 代码审计 (2026-06-18)
> **当前状态**: Phase 1 全部完成（8/8），Phase 2 剩余 12 项需修复
> **目标**: 修复金融计算准确性、消除性能瓶颈、补齐安全防护

---

## 当前状态审计

### Phase 1 已完成（12项）

| # | 问题 | 状态 |
|---|------|------|
| C5 | LLM输出校验层 | ✅ `output_validator.py` |
| C6 | 回测trade_list提取 | ✅ `run_qlib_bridge.py:168-192` |
| C7 | Kill Switch SQLite | ✅ `kill_switch.py` HMAC签名 |
| H2 | Admin Token自动生成 | ✅ `admin.py:12-28` |
| H3 | print→logging | ✅ 核心模块 |
| H4 | Metrics SQLite持久化 | ✅ `metrics.py` flush |
| H5/H6 | RSI/ATR Wilder平滑 | ✅ `technicals.py:53,105` |
| H10 | 信号监控批量化 | ✅ `signal_monitor_service.py` batch yf |
| H11 | yfinance异步化 | ✅ `asyncio.to_thread()` |
| H12/H13 | 退避修复 | ✅ 成功重置+max_delay=120s |
| H14 | Agent Memory | ✅ `brain_manager.py` Mem0+Qdrant |
| H22 | CORS白名单 | ✅ `get_allowed_origins()` |

### Phase 2 待修复（12项）

| # | 问题 | 严重性 | 状态 | 文件 |
|---|------|--------|------|------|
| H7 | PE百分位使用静态EPS | High | ❌ 未修复 | `market_data_service.py:666-672,991-997` |
| H8 | A股成长选股列不存在 | High | ❌ 未修复 | `screening_service.py:324-330` |
| H9 | 加权平均成本错误 | High | ❌ 未修复 | `mock_trading_service.py:196` |
| H15 | Structured Output部分实现 | Medium | ⚠️ 部分 | `llm_gateway.py` 无schema enforcement |
| H18 | LLM专家调用串行 | High | ❌ 未修复 | `discussion_service.py` parallel标志未使用 |
| H19 | SQLite无WAL/连接池 | High | ❌ 未修复 | `db/sqlite.py` DELETE模式 |
| H20 | 无Prompt Injection防护 | High | ❌ 未修复 | `api/analysis.py` symbol无校验 |
| H23 | Socket房间无验证 | Medium | ❌ 未修复 | `server.ts:188-191` |
| H24 | 硬编码测试URL | High | ❌ 未修复 | `llm_gateway.py:68` |
| H25 | Prompt强制中文 | Low | ❌ 未修复 | `runtime.py:19` |
| H16 | 选股无回测验证 | Medium | ❌ 未修复 | `screening_service.py` 无backtest |
| H17 | 回测Alpha/Beta硬编码 | Medium | ❌ 未修复 | `run_qlib_bridge.py:229-240` |
| — | Paper Trading双系统 | High | ❌ 未修复 | `mock_trading_service.py` vs `paper_trading_system/` |

---

## Phase 2 任务拆分

### 2.1 金融计算准确性（5项，~10天）

#### Task 2.1.1: PE百分位使用历史EPS [H7]
**优先级**: P1 | **工作量**: 2天 | **文件**: `market_data_service.py`

**问题**: 当前用单一静态 `trailingEPS` 计算2年历史PE百分位，只反映价格变化不反映EPS变化。

**方案**:
```python
# 当前 (错误):
trailing_eps = info.get("trailingEps")
hist_pe = hist['Close'] / trailing_eps  # 所有日期用同一个EPS

# 修复: 使用滚动TTM EPS
# 1. 从yfinance获取 quarterly_financials
# 2. 按季度滚动计算TTM EPS (最近4个季度净利润之和)
# 3. 对每个历史日期，用该日期之前的最近4个季度计算TTM EPS
# 4. hist_pe = hist['Close'] / rolling_ttm_eps
```

**验证**: 周期股（如券商、航运）的PE百分位应随EPS周期变化。

#### Task 2.1.2: A股成长选股修复 [H8]
**优先级**: P1 | **工作量**: 2天 | **文件**: `screening_service.py`

**问题**: `revenue_growth` 和 `earnings_growth` 列在DataFrame中不存在，`df.get()` 始终返回默认值0，成长筛选永远返回空。

**方案**:
```python
# 方案A (推荐): 使用AkShare的财务指标接口
import akshare as ak
# 获取个股财务指标: ak.stock_financial_analysis_indicator()
# 或使用 stock_zh_a_spot_em 已有字段中的 "市盈率-动态" 做间接判断

# 方案B: 用PE+PB+ROE组合替代growth筛选
# 调整 SCREEN_PRESETS["growth"] 的筛选条件为:
# - PE > 0 & PE < 30 (估值合理)
# - PB > 0 & PB < 5 (资产质量)
# - ROE > 15% (盈利能力，需从yfinance获取)
# - 市值 > 50亿 (流动性)
```

**验证**: 运行 `run_screen("growth", "A-Share")` 返回至少10只股票。

#### Task 2.1.3: 加权平均成本修复 [H9]
**优先级**: P1 | **工作量**: 1天 | **文件**: `mock_trading_service.py`

**问题**: 成本基准不含手续费，且使用pre-slippage价格。

**方案**:
```python
# 当前 (错误):
new_cost = ((current_shares * average_cost) + (shares * execution_price)) / new_shares

# 修复: 成本基准 = (总投入价格 + 手续费) / 总股数
new_cost = ((current_shares * average_cost) + (shares * actual_price) + cost) / new_shares
```

**验证**: 模拟买入100股@10元，手续费0.25元，average_cost应为10.0025。

#### Task 2.1.4: 回测Alpha/Beta计算 [H17]
**优先级**: P1 | **工作量**: 2天 | **文件**: `run_qlib_bridge.py`

**问题**: 16个指标中9个是硬编码stub。

**方案**:
```python
# 从metrics_df中提取实际计算:
# Alpha = 策略年化收益 - 无风险利率 - Beta * (基准年化收益 - 无风险利率)
# Beta = Cov(策略收益, 基准收益) / Var(基准收益)
# Sortino = (策略收益 - 无风险利率) / 下行标准差 * sqrt(252)
# Calmar = 年化收益 / 最大回撤
# Profit Factor = 总盈利 / 总亏损
```

**验证**: 输出指标不再有 `alpha=0.0, beta=1.0` 等stub。

#### Task 2.1.5: 选股策略回测验证 [H16]
**优先级**: P2 | **工作量**: 3天 | **文件**: `screening_service.py` (新增方法)

**方案**:
```python
def backtest_screen(screen_type: str, market: str, lookback_months: int = 12):
    """回测选股策略: 每月调仓，统计历史收益"""
    # 1. 每月末运行screen获取top N
    # 2. 等权买入，持有到下月末
    # 3. 计算累计收益、Sharpe、MaxDD
    # 4. 与benchmark对比
```

**验证**: 输出回测报告含年化收益、Sharpe、胜率。

---

### 2.2 性能与并发（3项，~5天）

#### Task 2.2.1: SQLite WAL模式 + 连接池 [H19]
**优先级**: P1 | **工作量**: 1天 | **文件**: `db/sqlite.py`

**方案**:
```python
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

engine = create_engine(
    f"sqlite:///{DATABASE_URL}",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
```

**验证**: 并发写入不报 `database is locked`。

#### Task 2.2.2: LLM专家并行调用 [H18]
**优先级**: P1 | **工作量**: 3天 | **文件**: `discussion_service.py`

**问题**: `topology` 中的 `parallel: True` 标志从未被读取，专家调用实际上是串行的。

**方案**:
```python
# 当前: LangGraph graph build 不区分 parallel/serial
# 修复: 对 parallel round 的专家，用 asyncio.gather 并行调用

async def _run_parallel_experts(self, experts: List[str], round_num: int):
    """并行调用同一轮的多个专家"""
    tasks = [self._call_expert(expert, round_num) for expert in experts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {expert: result for expert, result in zip(experts, results)}
```

**验证**: 10轮DEEP模式耗时从5-10分钟降至2-4分钟。

#### Task 2.2.3: 移除硬编码测试URL [H24]
**优先级**: P1 | **工作量**: 0.5天 | **文件**: `llm_gateway.py`

**方案**:
```python
# 当前 (危险):
self.default_base_url = os.getenv("DEFAULT_LLM_BASE_URL", "http://xbrain-dify-service-test.xiaopeng.link/llm_api")

# 修复: 无默认值，缺失时报错
self.default_base_url = os.getenv("DEFAULT_LLM_BASE_URL")
if not self.default_base_url:
    raise ValueError("DEFAULT_LLM_BASE_URL environment variable is required")
```

**验证**: 未设置环境变量时启动报错而非静默连接测试服务器。

---

### 2.3 安全加固（2项，~4天）

#### Task 2.3.1: Prompt Injection防护 [H20]
**优先级**: P1 | **工作量**: 2天 | **文件**: `api/analysis.py`, `api/sector.py`

**方案**:
```python
import re

# symbol格式校验 (A股/港股/美股)
_SYMBOL_PATTERN = re.compile(r'^[A-Za-z0-9._-]{1,20}$')

class AnalysisJobCreate(BaseModel):
    symbol: str
    market: str

    @validator('symbol')
    def validate_symbol(cls, v):
        if not _SYMBOL_PATTERN.match(v):
            raise ValueError(f'Invalid symbol format: {v}')
        return v.upper()

# config白名单校验
ALLOWED_CONFIG_KEYS = {"geminiApiKey", "deepseekApiKey", "analysisLevel"}
```

**验证**: 发送 `symbol="ignore previous instructions"` 返回422错误。

#### Task 2.3.2: Socket房间验证 [H23]
**优先级**: P2 | **工作量**: 2天 | **文件**: `server.ts`

**方案**:
```typescript
io.use((socket, next) => {
    const token = socket.handshake.auth?.token;
    if (!token || !verifyToken(token)) {
        return next(new Error('Authentication required'));
    }
    next();
});

io.on('connection', (socket) => {
    socket.on('joinRoom', (room) => {
        // 验证room格式: 只允许 job_id 格式 (UUID)
        if (!/^[0-9a-f-]{36}$/i.test(room)) {
            return socket.emit('error', 'Invalid room format');
        }
        socket.join(room);
    });
});
```

**验证**: 无token的socket连接被拒绝。

---

### 2.4 产品化补全（2项，~3天）

#### Task 2.4.1: Structured Output Schema Enforcement [H15]
**优先级**: P2 | **工作量**: 2天 | **文件**: `llm_gateway.py`

**问题**: 仅靠 `<structured_data>` XML标签和正则提取，无API级schema验证。

**方案**:
```python
# DeepSeek支持 response_format={"type": "json_object"}
# Gemini支持 response_schema (JSON Schema)

async def generate_content(self, prompt, schema=None, ...):
    if schema and provider == "deepseek":
        kwargs["response_format"] = {"type": "json_object"}
        # 在prompt末尾追加: "You MUST respond with valid JSON matching this schema: ..."
    elif schema and provider == "gemini":
        config["response_schema"] = schema
        config["response_mime_type"] = "application/json"
```

**验证**: LLM输出始终是合法JSON，无需正则提取。

#### Task 2.4.2: Prompt多语言支持 [H25]
**优先级**: P3 | **工作量**: 0.5天 | **文件**: `runtime.py`

**方案**:
```python
def get_prompt(self, name: str, version: str = "v1", language: str = "zh-CN") -> Dict[str, Any]:
    lang_suffix = "zh" if language.startswith("zh") else "en"
    # ... rest of logic
```

**验证**: `get_prompt("technical_analyst", language="en-US")` 加载 `_en.md` 模板。

---

### 2.5 Paper Trading统一（1项，~5天）

#### Task 2.5.1: 统一Paper Trading系统
**优先级**: P1 | **工作量**: 5天

**问题**: 两套完全独立的系统:
- `mock_trading_service.py`: 实时模拟交易 (SQLModel + SQLite)
- `paper_trading_system/`: 历史回测 (Qlib框架)

**方案**:
```
Phase 2a: 统一手续费模型
- mock_trading_service.py 的手续费改为 A股标准:
  买入: 佣金0.025% (最低5元) + 过户费0.001%
  卖出: 佣金0.025% (最低5元) + 印花税0.05% + 过户费0.001%
- paper_trading_system 的 market_configs.py 对齐

Phase 2b: 共享策略接口
- 定义统一的 StrategyProtocol (Python Protocol)
- mock_trading_service 和 paper_trading_system 都实现该接口

Phase 2c: 回测→模拟交易过渡
- 增加 backtest_to_mock() 方法: 回测结果直接转为模拟交易初始仓位
```

**验证**: 同一策略在回测和模拟交易中的收益率差异<5%（因滑点模型差异）。

---

## 实施顺序

```
Week 1: 金融计算准确性
├── Task 2.1.1: PE百分位历史EPS (2天)
├── Task 2.1.2: A股成长选股 (2天)
└── Task 2.1.3: 加权平均成本 (1天)

Week 2: 性能 + 安全
├── Task 2.2.1: SQLite WAL (1天)
├── Task 2.2.3: 移除测试URL (0.5天)
├── Task 2.3.1: Prompt Injection防护 (2天)
└── Task 2.1.4: 回测Alpha/Beta (2天)

Week 3: 并行化 + 产品化
├── Task 2.2.2: LLM专家并行 (3天)
├── Task 2.4.2: Prompt多语言 (0.5天)
└── Task 2.3.2: Socket房间验证 (2天)

Week 4: Paper Trading统一
├── Task 2.5.1a: 统一手续费 (1天)
├── Task 2.5.1b: 共享策略接口 (2天)
├── Task 2.5.1c: 回测→模拟过渡 (2天)
└── Task 2.1.5: 选股回测验证 (3天)
```

---

## 验收标准

| 指标 | 目标 |
|------|------|
| PE百分位 | 周期股百分位随EPS周期变化 |
| 成长选股 | `run_screen("growth", "A-Share")` 返回≥10只 |
| 成本基准 | 含手续费，与实际交易一致 |
| SQLite并发 | 10并发写入无 `database is locked` |
| LLM并行 | DEEP模式耗时<4分钟 |
| Prompt安全 | 注入字符串被拒绝 |
| 回测指标 | Alpha/Beta/Sortino/Calmar真实计算 |
| Paper Trading | 回测→模拟收益差异<5% |

---

## 风险

| 风险 | 缓解 |
|------|------|
| AkShare成长数据缺失 | 用ROE+营收增速代理 |
| SQLite WAL迁移数据丢失 | 备份后迁移 |
| LLM并行导致API限流 | 保持RateLimiter，增加并发上限配置 |
| Paper Trading统一影响现有功能 | 分阶段迁移，保留旧接口 |

---

*文档生成时间: 2026-06-18*
*基于: 代码审计 + AUDIT_OPTIMIZATION_REPORT.md Phase 2*
