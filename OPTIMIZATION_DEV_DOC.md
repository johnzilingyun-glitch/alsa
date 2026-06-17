# ALSA 优化开发文档

> **基于评审报告生成** | 2026-06-15  
> **文档目的**: 将评审发现转化为可执行的开发任务  
> **总计**: 37项优化任务，分5个Phase执行

---

## Phase 1: 紧急修复（1-2周）

### 目标：消除Critical安全漏洞，确保系统可安全运行

#### Task 1.1: 删除硬编码密钥
**优先级**: P0 | **工作量**: 0.5天 | **负责**: 安全

**修改文件**:
- `python_service/app/services/signal_monitor_service.py:238`
- `src/services/feishuService.ts:203`

**具体操作**:
```python
# signal_monitor_service.py
# 删除前:
webhook_secret = os.getenv("HERMES_WEBHOOK_SECRET", "jR9oR2-DrTyHKLnwXB2mIPFK8mLlozbOL1IcsiLsbs0")
# 删除后:
webhook_secret = os.getenv("HERMES_WEBHOOK_SECRET")
if not webhook_secret:
    print("WARNING: HERMES_WEBHOOK_SECRET not set, webhook signing disabled")
```

```typescript
// feishuService.ts
// 删除第203行的硬编码密钥
// HMAC签名逻辑移至server/feishuRoutes.ts
```

**验证**: grep确认无硬编码密钥

---

#### Task 1.2: 修复LLM Gateway未定义变量
**优先级**: P0 | **工作量**: 0.5天 | **负责**: AI架构

**修改文件**: `python_service/app/services/llm_gateway.py:186`

**具体操作**:
```python
# 删除第186行:
# result_text = result[0] if return_usage and isinstance(result, tuple) else result
# 这行代码引用未定义的result和return_usage，是重构残留
```

**验证**: 运行 `generate_content` 方法不报NameError

---

#### Task 1.3: 修复文件下载正则
**优先级**: P0 | **工作量**: 0.5天 | **负责**: Node.js

**修改文件**: `server/routes/analysisRoutes.ts:24`

**具体操作**:
```typescript
// 修改前:
if (!file || !/^[\w.-]+\\.(html|pdf)$/i.test(file)) {
// 修改后:
if (!file || !/^[\w.-]+\.(html|pdf)$/i.test(file)) {
```

**验证**: 下载HTML/PDF报告正常工作

---

#### Task 1.4: 修复SQL注入
**优先级**: P0 | **工作量**: 1天 | **负责**: 安全

**修改文件**: `python_service/app/api/sector.py:348,407,770`

**具体操作**:
```python
# 添加辅助函数:
def _escape_like(s: str) -> str:
    """转义SQL LIKE特殊字符"""
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

# 替换所有用户输入的like调用:
# 修改前:
AnalysisJob.symbol.like(f"%{req.sector_name}%")
# 修改后:
AnalysisJob.symbol.like(f"%{_escape_like(req.sector_name)}%")
```

**验证**: 构造含`%`和`_`的sector_name测试

---

#### Task 1.5: 修复全局Store暴露
**优先级**: P0 | **工作量**: 0.5天 | **负责**: 前端

**修改文件**: `src/App.tsx:25-27`

**具体操作**:
```typescript
// 修改前:
if (typeof window !== 'undefined') {
  (window as any).useAnalysisStore = useAnalysisStore;
}
// 修改后:
if (import.meta.env.DEV && typeof window !== 'undefined') {
  (window as any).useAnalysisStore = useAnalysisStore;
}
```

**验证**: 生产构建中window无useAnalysisStore

---

#### Task 1.6: 修复API Token时序攻击
**优先级**: P0 | **工作量**: 0.5天 | **负责**: 安全

**修改文件**: `server/securityConfig.ts:44`

**具体操作**:
```typescript
import crypto from 'crypto';

// 修改前:
return token === expected;
// 修改后:
if (!token || !expected) return false;
const a = Buffer.from(token);
const b = Buffer.from(expected);
if (a.length !== b.length) return false;
return crypto.timingSafeEqual(a, b);
```

**验证**: 使用不同长度token测试，确认不会泄露信息

---

#### Task 1.7: 修复is_final_round未定义
**优先级**: P0 | **工作量**: 0.5天 | **负责**: AI架构

**修改文件**: `python_service/app/services/discussion_service.py:311`

**具体操作**:
```python
# 在_call_expert方法开头添加:
is_final_round = role in ("Chief Strategist", "Sector Chief Strategist")
```

**验证**: 使用非DeepSeek模型运行分析不报错

---

## Phase 2: 高优先级修复（2-4周）

### 目标：修复金融准确性、风控缺陷、性能瓶颈

#### Task 2.1: 启用API认证默认
**工作量**: 2天 | **文件**: `python_service/app/security.py`, `server/securityConfig.ts`

**实现方案**:
1. 启动时生成随机API_TOKEN（如未配置）
2. 将token写入`.env.runtime`
3. 打印到控制台供用户使用
4. 所有API端点强制要求token

---

#### Task 2.2: 实现LLM多提供商回退
**工作量**: 3天 | **文件**: `python_service/app/services/llm_gateway.py`

**实现方案**:
```python
async def generate_with_fallback(self, prompt, model, ...):
    providers = [
        ("gemini", self._generate_gemini),
        ("deepseek", self._generate_deepseek),
        ("default", self._generate_default),
    ]
    for name, func in providers:
        try:
            return await func(prompt, model, ...)
        except (RateLimitError, ServiceUnavailableError):
            continue
    raise Exception("All providers failed")
```

---

#### Task 2.3: 修复RSI算法
**工作量**: 1天 | **文件**: `python_service/app/quant/polars_indicators.py`

**修改方案**:
```python
# 修改前 (SMA):
rs = avg_gain / avg_loss

# 修改后 (Wilder's EMA):
alpha = 1.0 / period
avg_gain = gain.ewm_mean(alpha=alpha, adjust=False)
avg_loss = loss.ewm_mean(alpha=alpha, adjust=False)
rs = avg_gain / avg_loss
```

---

#### Task 2.4: 修复A股成长选股
**工作量**: 2天 | **文件**: `python_service/app/services/screening_service.py`

**修改方案**:
```python
elif screen_type == "growth":
    # 修改前: 仅PE过滤
    df = df[(df["pe"] > 0) & (df["pe"] < 50)]
    
    # 修改后: 多维度成长筛选
    df = df[
        (df["pe"] > 0) & (df["pe"] < 50) &
        (df.get("revenue_growth", 0) > 15) &
        (df.get("earnings_growth", 0) > 20)
    ]
```

---

#### Task 2.5: 杀伤开关持久化
**工作量**: 3天 | **文件**: `python_service/app/risk/kill_switch.py`

**实现方案**:
```python
class KillSwitch:
    def __init__(self, db_path="kill_switch_state.json"):
        self.state = self._load_state()
    
    def _load_state(self):
        if os.path.exists(self.db_path):
            with open(self.db_path) as f:
                return json.load(f)
        return {"state": "ACTIVE", "events": []}
    
    def _save_state(self):
        with open(self.db_path, 'w') as f:
            json.dump(self.state, f)
```

---

#### Task 2.6: 修复加权平均成本
**工作量**: 1天 | **文件**: `python_service/app/services/mock_trading_service.py:177`

**修改方案**:
```python
# 修改前 (混合含佣/不含佣):
new_cost = ((current_shares * average_cost) + total_required) / new_shares

# 修改后 (纯价格平均):
new_cost = ((current_shares * average_cost) + (shares * execution_price)) / new_shares
# commission单独记录，不影响成本基准
```

---

#### Task 2.7: 信号监控异步化
**工作量**: 2天 | **文件**: `python_service/app/services/signal_monitor_service.py`

**修改方案**:
```python
# 批量获取替代逐个获取:
async def _check_us_batch(self, alerts):
    symbols = [a.symbol for a in alerts]
    # 使用yf.download批量获取
    data = await asyncio.to_thread(yf.download, symbols, ...)
```

---

#### Task 2.8: 统一Paper Trading系统
**工作量**: 5天 | **文件**: `python_service/app/services/mock_trading_service.py`

**实现方案**:
1. 删除`PaperTrading_System/`目录
2. 统一手续费模型到`mock_trading_service.py`
3. 实现正确的A股手续费:
   - 买入: 佣金0.025%（最低5元）
   - 卖出: 佣金0.025% + 印花税0.05%
   - 过户费: 0.001%（沪市）

---

## Phase 3: DevOps基础设施（1个月）

### 目标：建立可维护、可监控的生产环境

#### Task 3.1: Docker化部署
**工作量**: 3天

**创建文件**:
- `Dockerfile` (Python后端)
- `Dockerfile.frontend` (Node.js网关+React)
- `docker-compose.yml`
- `.dockerignore`

---

#### Task 3.2: CI/CD流水线
**工作量**: 3天

**创建文件**: `.github/workflows/ci.yml`

```yaml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm run lint
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm test
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm audit --audit-level=high
```

---

#### Task 3.3: Python日志系统
**工作量**: 3天

**修改文件**: 所有核心服务的`print()`调用

**方案**:
```python
import logging
logger = logging.getLogger(__name__)

# 替换所有print:
# print(f"Error: {e}") 
# 改为:
logger.error("Error occurred", exc_info=True)
```

---

#### Task 3.4: 健康检查端点
**工作量**: 1天

**修改文件**: `python_service/main.py`

```python
@app.get("/api/health/ready")
async def readiness_check():
    checks = {
        "database": check_db_connection(),
        "llm_provider": check_llm_availability(),
        "data_source": check_data_source(),
    }
    all_ok = all(checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
```

---

## Phase 4: 数据源升级（1-2个月）

### 目标：提升数据质量和分析准确性

#### Task 4.1: 集成Tushare Pro
**工作量**: 5天

**实现方案**:
```python
class TushareDataProvider:
    def __init__(self, token):
        self.client = tushare.pro_api(token)
    
    def get_financials(self, symbol):
        # 财务报表
        income = self.client.income(ts_code=symbol)
        balance = self.client.balancesheet(ts_code=symbol)
        cashflow = self.client.cashflow(ts_code=symbol)
        return merge(income, balance, cashflow)
```

---

#### Task 4.2: 添加风险指标计算
**工作量**: 5天

**创建文件**: `python_service/app/quant/risk_metrics.py`

```python
class RiskMetrics:
    @staticmethod
    def compute_var(returns, confidence=0.95):
        """参数法VaR"""
        from scipy import stats
        mu = returns.mean()
        sigma = returns.std()
        return stats.norm.ppf(1 - confidence, mu, sigma)
    
    @staticmethod
    def compute_sharpe(returns, rf=0.03):
        """年化Sharpe比率"""
        excess = returns - rf / 252
        return excess.mean() / excess.std() * np.sqrt(252)
    
    @staticmethod
    def compute_max_drawdown(equity_curve):
        """最大回撤"""
        peak = equity_curve.expanding(min_periods=1).max()
        drawdown = (equity_curve - peak) / peak
        return drawdown.min()
```

---

#### Task 4.3: 报告添加图表
**工作量**: 5天

**实现方案**:
- 使用`plotly`生成K线图+技术指标
- 使用`matplotlib`生成收益分布图
- 将图表base64编码嵌入HTML

---

## Phase 5: 产品化（季度）

### 目标：提升用户体验和产品竞争力

#### Task 5.1: 移动端适配
**工作量**: 15天

**方案**: 
- 响应式设计优化
- 触摸友好的交互
- PWA支持

---

#### Task 5.2: 多用户系统
**工作量**: 10天

**方案**:
- JWT认证
- RBAC权限
- 共享Watchlist
- 团队协作

---

#### Task 5.3: API产品化
**工作量**: 10天

**方案**:
- OpenAPI文档
- API Key管理
- 速率限制
- SDK（Python/JS）

---

## 开发规范

### 代码规范
1. **Python**: 遵循PEP 8，使用black格式化
2. **TypeScript**: 遵循ESLint配置，使用Prettier
3. **Git**: Conventional Commits格式
4. **测试**: 每个PR必须有测试覆盖

### 分支策略
```
main (生产)
├── develop (开发)
│   ├── feature/task-1.1 (功能分支)
│   ├── feature/task-1.2
│   └── ...
├── release/v1.1 (发布分支)
└── hotfix/xxx (紧急修复)
```

### 代码审查
- 每个PR需要至少1人审查
- 安全相关修改需要2人审查
- 自动化CI检查必须通过

### 文档要求
- 每个API端点必须有文档
- 每个配置项必须有说明
- 重大修改必须更新CHANGELOG

---

## 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| LLM API变更 | 中 | 高 | 抽象Provider层，快速适配 |
| 数据源失效 | 高 | 中 | 多数据源冗余 |
| 安全漏洞被利用 | 中 | 高 | 立即修复Critical问题 |
| 性能瓶颈 | 中 | 中 | 监控+压测 |
| 用户流失 | 低 | 高 | 持续迭代+用户反馈 |

---

## 成功指标

### Phase 1 完成标准
- [ ] 0个Critical安全漏洞
- [ ] 所有High安全问题修复
- [ ] 系统可安全运行

### Phase 2 完成标准
- [ ] RSI/MACD等指标与TradingView一致
- [ ] A股选股策略准确率>80%
- [ ] 模拟交易手续费与真实市场差异<10%

### Phase 3 完成标准
- [ ] Docker一键部署
- [ ] CI/CD自动化
- [ ] 核心服务100%日志覆盖

### Phase 4 完成标准
- [ ] A股数据准确率>95%
- [ ] 风险指标计算正确
- [ ] 报告包含可视化图表

### Phase 5 完成标准
- [ ] 移动端可用
- [ ] 多用户支持
- [ ] API文档完整

---

*文档生成时间: 2026-06-15*  
*基于: REVIEW_REPORT.md 128项发现*
