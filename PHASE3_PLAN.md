# ALSA Phase 3 实施计划：Agent能力升级

> **基于**: AUDIT_OPTIMIZATION_REPORT.md Phase 3
> **当前状态**: 4/8任务已完成，4项待实现
> **目标**: 提升AI分析质量和效率

---

## Phase 3 任务拆分

### 3.1 Self-Reflection Agent [P2, 5天]

**目标**: 每轮专家分析后，增加自我反思环节，提升分析质量

**方案**:
```python
# 在discussion_service.py中增加反思节点
class SelfReflectionAgent:
    async def reflect(self, expert_role: str, analysis: str, context: Dict) -> str:
        """对上一轮分析进行自我反思，识别逻辑漏洞和偏见"""
        prompt = f"""你是{expert_role}的自我反思助手。请审查以下分析：
        
{analysis}

识别：
1. 逻辑矛盾或不一致
2. 缺失的关键信息
3. 潜在的认知偏见
4. 需要验证的假设

输出改进后的分析。"""
        return await llm_gateway.generate_content(prompt)
```

**验证**: 每轮专家分析后自动调用反思，输出包含改进点

---

### 3.2 Critic Agent [P2, 5天]

**目标**: 独立校验层，交叉验证各专家观点，识别分歧

**方案**:
```python
class CriticAgent:
    async def critique(self, analyses: List[Dict], symbol: str) -> Dict:
        """独立审查所有专家分析，识别分歧和风险"""
        prompt = f"""你是独立的审查员。以下是对{symbol}的多专家分析：

{json.dumps(analyses, ensure_ascii=False)}

请：
1. 识别专家之间的重大分歧（>20%观点差异）
2. 检查数据一致性（不同专家引用的数据是否矛盾）
3. 评估整体风险偏见（是过度乐观还是悲观？）
4. 给出综合评分（0-100）和置信度"""
        return await llm_gateway.generate_content(prompt)
```

**验证**: 每次讨论结束后输出Critic报告，包含分歧点和综合评分

---

### 3.3 Monte Carlo回测验证 [P2, 5天]

**目标**: 通过蒙特卡洛模拟评估策略稳健性

**方案**:
```python
async def monte_carlo_backtest(
    strategy_func,
    price_data: pd.DataFrame,
    n_simulations: int = 1000,
    confidence_level: float = 0.95
) -> Dict:
    """
    蒙特卡洛回测：随机扰动入场/出场时点，评估策略稳健性
    """
    results = []
    for _ in range(n_simulations):
        # 随机扰动：±5%价格滑点 + ±1天时间偏移
        perturbed_data = add_random_noise(price_data)
        result = strategy_func(perturbed_data)
        results.append(result)
    
    # 计算VaR和置信区间
    returns = [r['total_return'] for r in results]
    var = np.percentile(returns, (1 - confidence_level) * 100)
    
    return {
        "var_95": var,
        "sharpe_mean": np.mean([r['sharpe'] for r in results]),
        "sharpe_std": np.std([r['sharpe'] for r in results]),
        "probability_of_profit": sum(1 for r in returns if r > 0) / n_simulations
    }
```

**验证**: 输出VaR、Sharpe分布、盈利概率

---

### 3.4 Prompt模板版本控制集成 [P2, 3天]

**目标**: 管理Prompt模板版本，支持A/B测试

**方案**:
```python
class PromptVersionManager:
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self._init_table()
    
    def _init_table(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                template TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metrics JSON,  -- 存储性能指标
                active BOOLEAN DEFAULT 0,
                UNIQUE(name, version)
            )
        """)
    
    def get_active_prompt(self, name: str) -> str:
        """获取当前激活的prompt版本"""
        row = self.db.execute(
            "SELECT template FROM prompt_versions WHERE name=? AND active=1",
            (name,)
        ).fetchone()
        return row[0] if row else self._load_default(name)
    
    def ab_test(self, name: str, version_a: str, version_b: str, split: float = 0.5):
        """设置A/B测试，随机分配流量"""
        pass
```

**验证**: 支持多版本管理，可回滚到历史版本

---

## 实施顺序

```
Week 1:
├── Task 3.1: Self-Reflection Agent (5天)
└── Task 3.2: Critic Agent (5天)

Week 2:
├── Task 3.3: Monte Carlo回测 (5天)
└── Task 3.4: Prompt版本控制 (3天)
```

---

## 验收标准

| 指标 | 目标 |
|------|------|
| Self-Reflection | 每轮分析后自动反思，输出包含改进点 |
| Critic Agent | 每次讨论输出综合评分和分歧点 |
| Monte Carlo | 输出VaR、Sharpe分布、盈利概率 |
| Prompt版本 | 支持多版本管理和A/B测试 |

---

*文档生成时间: 2026-06-18*
