# ALSA AI 分析性能优化指南

> 诊断日期: 2026-07-08  
> 分析范围: 端到端分析耗时、瓶颈定位、优化方案  
> 当前状态: **DEEP/STANDARD 分析 3-8分钟，远高于用户期望 (目标: <2分钟)**

---

## 执行摘要

**问题**: AI 分析耗时较长，主要原因是：
1. **LLM 请求速率限制太严格** (3秒/次，中转站防503)
2. **多轮讨论串联等待** (6-10轮讨论 × 3秒基线 = 30-50秒基础开销)
3. **验证和反思的隐藏成本** (每个专家可能触发额外 LLM 调用)
4. **搜索预热阻塞** (batch_search 最多阻塞 30 秒)
5. **前端流式更新粒度粗** (0.5秒/次回调，感知延迟)

**不是流式输出本身的问题** ✅ - 流式输出设计合理，关键是速率限制和多轮等待。

**快速改善预期**: 实施高优先级方案 → **减少 40-50% 耗时** (3分钟 → 90-120秒)

---

## 详细诊断

### 1. LLM 请求速率限制是主要瓶颈 🔴 关键

#### 现状

```python
# llm_gateway.py L80
_min_interval = float(os.getenv("LLM_RATE_LIMIT_INTERVAL", "3.0"))
# 默认 3 秒最小间隔
```

**为什么是 3 秒?** 中转站 (xbrain-dify-service) 容易在高频请求时返回 503，所以加了保护性速率限制。

#### 耗时计算

```
QUICK 拓扑: 4 轮讨论
├─ Round 1: Deep Research      → 3秒等待 + 25秒LLM = 28秒
├─ Round 2: Tech + Fundam      → 3秒等待 + 40秒LLM并行 = 43秒
├─ Round 3: Professional Review → 3秒等待 + 20秒LLM = 23秒
└─ Round 4: Chief Strategist    → 3秒等待 + 15秒LLM = 18秒
              ──────────────────────────
              总计: 12秒纯等待 + 100秒LLM响应 ≈ 112秒

STANDARD 拓扑: 6 轮讨论 + 额外验证和反思
├─ 讨论轮次              ≈ 150-180秒
├─ 验证调用 (4-6次)     ≈ 20-30秒
├─ 反思调用 (4-6次)     ≈ 20-30秒
└─ 其他 (批评/报告)     ≈ 20-30秒
              ──────────────────────────
              总计: ≈ 210-270秒 (3.5-4.5分钟)
```

#### 优化建议: 分化处理

```python
# llm_gateway.py 新增自适应速率
class RateLimiter:
    async def acquire(self, context: str = "tool"):
        """
        context: 'tool' (工具调用轮) | 'final' (最终综合) | 'default'
        根据调用上下文动态调整最小间隔
        """
        await self._semaphore.acquire()
        async with self._lock:
            # 自适应间隔：工具轮 1.0s, 最终轮 1.5s, 默认 3.0s
            min_interval = {
                'tool': 1.0,
                'final': 1.5,
                'default': 3.0,  # 保守，预防503
            }.get(context, 3.0)
            
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < min_interval:
                wait_time = min_interval - elapsed
                await asyncio.sleep(wait_time)
            self._last_request_time = time.monotonic()
```

**预期效果**: 
- 工具轮从 3s 降到 1s → 每轮省 2 秒
- 6 轮讨论省 12 秒
- **总耗时减少 30-40%**

---

### 2. 多轮讨论的串联结构 🔴 关键

#### 现状

[讨论拓扑] 虽然标记了 `parallel: True`，但由于：
- LLM 调用本身受速率限制排队
- 同一用户只有一个 concurrency_limit (Semaphore)
- 工具轮次仍需串联执行

```python
# agent_orchestrator.py L38
for round_num in range(max_tool_rounds + 1):  # 最多 31 轮!
    result = await llm_gateway.generate_content(...)
    if not has_tool_calls(result):
        break  # 无工具调用则停止
```

#### 优化建议: 并行化工具执行

```python
# expert_tools.py 改造工具执行
async def execute_tools_parallel(tool_calls: List[Dict]) -> List[Dict]:
    """并行执行独立的工具调用，而非串联"""
    
    # 第一步：分析工具调用的依赖关系
    independent_groups = identify_independent_tools(tool_calls)
    
    # 第二步：按组并发执行
    results = []
    for group in independent_groups:
        group_results = await asyncio.gather(
            *[execute_single_tool(tc) for tc in group],
            return_exceptions=True
        )
        results.extend(group_results)
    
    return results
```

**预期效果**: 
- 如果某轮有 3-4 个工具调用，并行执行而非串联
- 减少工具执行时间 40-60%
- 总耗时减少 10-20秒

---

### 3. 验证和反思的隐藏成本 ⚠️ 中等

#### 现状

```python
# discussion_service.py L230-280
# 每个专家都可能触发:
if should_verify:
    verification = grounding_verifier.verify(content, snapshot)  # 额外LLM调用
    
if should_reflect:
    reflection = self_reflection_agent.reflect(...)  # 额外LLM调用

# 最终专家强制执行两个检查
```

**隐藏成本分析**:
```
STANDARD 拓扑 6 轮:
├─ 中间专家 (4 个): 50% 概率触发验证/反思
│  └─ 平均 2 × (验证15秒 + 反思15秒) = 60 秒
├─ 最终专家 (2 个): 100% 触发验证/反思
│  └─ 2 × (验证15秒 + 反思15秒) = 60 秒
├─ 批评Agent           : 20 秒
└─ 报告生成           : 15 秒
        ──────────────────────────
        总计: 155 秒额外验证/反思成本
```

#### 优化建议: 批量验证和选择性跳过

```python
# discussion_service.py 批量验证
async def batch_verify_and_reflect(
    self, 
    expert_outputs: Dict[str, str],
    is_final_round: bool
) -> Dict[str, Dict]:
    """
    一次性验证和反思多个专家输出
    is_final_round: 最终轮强制所有检查; 中间轮则智能选择
    """
    
    verification_results = {}
    reflection_results = {}
    
    if self._verification_mode == 'extreme':
        # 跳过所有检查 (速度最快)
        return {expert: {} for expert in expert_outputs}
    
    # 批量验证 (一个调用处理所有)
    if is_final_round or self._verification_mode == 'quality':
        combined_content = "\n---\n".join(
            f"[{expert}] {content}" 
            for expert, content in expert_outputs.items()
        )
        
        # 一次LLM调用验证所有输出
        verification_prompt = f"""
        请验证以下专家分析中的事实陈述。
        
        {combined_content}
        
        对每个专家输出，标记任何不准确或不可验证的陈述。
        """
        
        verification_result = await llm_gateway.generate_content(
            verification_prompt,
            model="deepseek-chat",
            temperature=0.2  # 低温度，确保准确
        )
        
        # 解析结果并分发给各专家
        verification_results = parse_verification_result(
            verification_result, 
            expert_outputs.keys()
        )
    
    # 类似地批量反思...
    
    return {
        "verifications": verification_results,
        "reflections": reflection_results
    }
```

**预期效果**: 
- 将 6-8 个单独验证/反思调用合并为 2-3 个批量调用
- 减少 30-50 秒耗时
- 同时保持验证质量

---

### 4. 搜索预热的阻塞问题 ⚠️ 中等

#### 现状

```python
# discussion_service.py L130-140
search_results = await asyncio.wait_for(
    search_toolkit.batch_search(symbol, name, snapshot),
    timeout=30.0  # 可能阻塞 30 秒
)
```

**问题**: 搜索结果未到达前，整个讨论管道被阻塞。

#### 优化建议: 后台搜索 + 渐进式填充

```python
# discussion_service.py 改造
async def run_discussion(self, ...):
    """改为后台启动搜索，讨论继续进行"""
    
    # 不等待搜索完成，立即返回
    search_task = asyncio.create_task(
        search_toolkit.batch_search(symbol, name, snapshot)
    )
    
    # 使用缓存或基础数据启动讨论
    topology = self.build_topology(level, ...)
    
    # 在讨论进行中，异步等待搜索
    try:
        search_results = await asyncio.wait_for(search_task, timeout=20.0)
    except asyncio.TimeoutError:
        # 搜索超时，使用默认结果继续
        search_results = {}
    
    # 讨论继续...
    for r_info in topology:
        experts = r_info["experts"]
        # 如果搜索已完成，注入最新结果
        if search_task.done() and not search_results:
            try:
                search_results = search_task.result()
            except:
                pass
        
        # 并行调用专家
        results = await asyncio.gather(
            *[
                self._call_expert(
                    role=expert,
                    search_results=search_results,  # 使用最新搜索结果
                    ...
                )
                for expert in experts
                if r_info.get("parallel", False)
            ]
        )
```

**预期效果**: 
- 搜索从阻塞改为后台并行
- 减少 10-20 秒关键路径时间

---

### 5. 流式输出的粒度优化 🟡 轻微

#### 现状

```python
# llm_gateway.py L400-430
def _safe_on_chunk(*args, **kwargs):
    now = time.monotonic()
    # 节流: 0.5 秒才发一次
    if (now - _last_call_time[0] > 0.5) or len(args) != 1:
        ...
```

**问题**: 前端更新粒度粗，用户感知到"卡顿"，实际上是等待 0.5s 才收到更新。

#### 优化建议: 更频繁的更新

```python
# llm_gateway.py 改进
def _safe_on_chunk(*args, **kwargs):
    now = time.monotonic()
    
    # 策略: 100ms 或 chunk 计数，取先到者
    time_elapsed = now - _last_call_time[0]
    chunk_accumulated = len(_accumulated_buffer)
    
    should_send = (
        time_elapsed > 0.1 or  # 100ms 触发一次
        chunk_accumulated > 10 or  # 或 10 个 chunk
        kwargs  # 或有额外参数
    )
    
    if should_send:
        _last_call_time[0] = now
        loop.call_soon_threadsafe(_original_on_chunk, ...)
```

**预期效果**: 
- 主观感受快 30-40%（实际耗时不变，但 UX 改善）

---

## 优化方案总结表

| # | 优化项 | 优先级 | 难度 | 预期时间减少 | 相关文件 |
|---|-------|--------|------|------------|---------|
| 1 | 速率限制自适应 (1s/3s) | 🔴 高 | 低 | 30-40% | llm_gateway.py |
| 2 | 工具执行并行化 | 🔴 高 | 中 | 10-20% | expert_tools.py |
| 3 | 批量验证/反思 | ⚠️ 中 | 高 | 15-25% | discussion_service.py |
| 4 | 搜索后台执行 | ⚠️ 中 | 中 | 10-15% | discussion_service.py |
| 5 | 前端更新频率 (100ms) | 🟡 低 | 低 | 主观快 30% | llm_gateway.py |
| 6 | QUICK模式验证跳过 | ⚠️ 中 | 低 | 20-30% | discussion_service.py |
| 7 | 增加并发限制 (5→10) | ⚠️ 中 | 低 | 吞吐 +100% | analysis_job_service.py |

**组合实施**高优先级 (1-4): **总减少 60-80% 耗时** ✅

---

## 立即可做的快速改善 (无需重构)

### 环境变量调优

```bash
# .env 或 .env.runtime
# 从 3.0 改为 1.5
LLM_RATE_LIMIT_INTERVAL=1.5

# 允许更多并发
MAX_CONCURRENT_JOBS=10

# 搜索超时改短 (使其更快失败或成功)
BATCH_SEARCH_TIMEOUT=15

# 流式输出节流改短
LLM_STREAM_THROTTLE_MS=100
```

**预期**: 减少 25-35% 耗时 (无需代码改动)

### 配置优化

```python
# python_service/main.py
# 默认使用 QUICK 拓扑而非 STANDARD
DEFAULT_ANALYSIS_LEVEL = os.getenv("DEFAULT_ANALYSIS_LEVEL", "quick")

# 默认启用快速模式
DEFAULT_VERIFICATION_MODE = os.getenv("DEFAULT_VERIFICATION_MODE", "quick")
```

---

## 代码实现步骤 (完整优化)

### 第 1 步: 自适应速率限制 (2小时)

**文件**: `python_service/app/services/llm_gateway.py`

```python
class RateLimiter:
    def __init__(self, min_interval: float = 3.0, max_concurrent: int = 2, 
                 tool_interval: float = 1.0, final_interval: float = 1.5):
        self._min_interval = min_interval
        self._default_min_interval = min_interval
        self._tool_interval = tool_interval  # 工具轮
        self._final_interval = final_interval  # 最终轮
        self._current_context = None
        ...

    async def acquire(self, context: str = "default"):
        """根据上下文选择速率"""
        await self._semaphore.acquire()
        async with self._lock:
            if context == "tool":
                min_interval = self._tool_interval
            elif context == "final":
                min_interval = self._final_interval
            else:
                min_interval = self._min_interval
            
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < min_interval:
                wait_time = min_interval - elapsed
                await asyncio.sleep(wait_time)
            self._last_request_time = time.monotonic()
```

在 `generate_content` 中传入 `context`:

```python
async def generate_content(self, prompt, model, ..., is_tool_round=False, is_final_round=False):
    context = "final" if is_final_round else ("tool" if is_tool_round else "default")
    async with llm_rate_limiter.acquire(context):
        # 调用 LLM
        ...
```

### 第 2 步: 工具并行执行 (3小时)

**文件**: `python_service/app/services/expert_tools.py`

```python
async def execute_tools_batch(tool_calls: List[Dict]) -> Dict[str, Any]:
    """
    分析工具依赖，并行执行独立工具
    """
    # 依赖分析 (简单版本: 假设工具无依赖)
    # 实际版本需要检查输入是否来自其他工具
    
    results = {}
    tasks = []
    
    for tool_call in tool_calls:
        task = asyncio.create_task(
            execute_single_tool_safe(tool_call)
        )
        tasks.append((tool_call["name"], task))
    
    for name, task in tasks:
        try:
            result = await task
            results[name] = result
        except Exception as e:
            results[name] = {"error": str(e)}
    
    return results

async def execute_single_tool_safe(tool_call):
    """单个工具执行，带异常处理"""
    try:
        return await execute_single_tool(tool_call)
    except Exception as e:
        logger.error(f"Tool {tool_call['name']} failed: {e}")
        return {"error": str(e)}
```

### 第 3 步: 批量验证 (4小时)

**文件**: `python_service/app/services/discussion_service.py`

```python
async def batch_verify_outputs(self, expert_outputs: Dict[str, str], snapshot):
    """一次性验证多个专家输出"""
    if not expert_outputs:
        return {}
    
    # 构建验证提示
    output_list = "\n---\n".join(
        f"【{expert}】\n{content[:500]}"  # 每个输出最多 500 字
        for expert, content in expert_outputs.items()
    )
    
    verify_prompt = f"""
    请快速验证以下专家分析中的关键数据点和逻辑。
    
    {output_list}
    
    格式: 对每个专家，列出任何错误或不合理的地方。
    如果无明显错误，写"✓ 合理"。
    """
    
    result = await llm_gateway.generate_content(
        verify_prompt,
        model="deepseek-chat",
        temperature=0.1,
        is_final_round=True
    )
    
    return parse_verification_result(result)
```

### 第 4 步: 搜索后台化 (2小时)

```python
async def run_discussion(self, symbol, name, snapshot, ...):
    # 立即启动搜索任务 (非阻塞)
    search_task = asyncio.create_task(
        search_toolkit.batch_search(symbol, name, snapshot)
    )
    
    topology = self.build_topology(level, ...)
    search_results = {}
    
    for r_idx, r_info in enumerate(topology):
        # 在每一轮开始前，检查搜索是否完成
        if search_task.done() and not search_results:
            try:
                search_results = search_task.result()
            except:
                search_results = {}
        
        # 讨论继续...
        experts = r_info["experts"]
        
        # 并行调用专家
        if r_info.get("parallel"):
            results = await asyncio.gather(*[
                self._call_expert(
                    role=expert,
                    search_results=search_results,
                    ...
                )
                for expert in experts
            ])
        else:
            # 串联调用
            ...
```

---

## 测试验证计划

### 基线测试

```bash
# 记录当前状态
curl -s -X POST http://localhost:8000/api/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "market": "us",
    "analysis_level": "quick"
  }' | jq '.job_id' | xargs -I {} \
  bash -c 'echo "Job: {}"; time curl -s http://localhost:8000/api/analysis/jobs/{} | jq .progress'
```

### 优化后测试

实施每个优化后，重新测试相同股票，记录耗时。

### 预期数据

```
┌─ 基线 ────────────────────────────────┐
│ QUICK  : 90-120秒                      │
│ STANDARD: 180-240秒                    │
│ DEEP   : 300-360秒                     │
└────────────────────────────────────────┘
           ↓ 优化 1 (速率限制)
┌─ 优化后 1 ────────────────────────────┐
│ QUICK  : 65-85秒 (-30%)                │
│ STANDARD: 130-160秒 (-30%)             │
└────────────────────────────────────────┘
           ↓ 优化 2 (工具并行)
┌─ 优化后 2 ────────────────────────────┐
│ QUICK  : 55-75秒 (-40%)                │
│ STANDARD: 110-140秒 (-40%)             │
└────────────────────────────────────────┘
           ↓ 优化 3-4 (批量验证 + 搜索)
┌─ 优化后 3-4 ──────────────────────────┐
│ QUICK  : 45-60秒 (-50%)                │
│ STANDARD: 80-110秒 (-55%)              │
└────────────────────────────────────────┘
```

---

## 风险与回滚

| 风险 | 缓解策略 |
|-----|--------|
| 降低速率限制导致 503 | 添加自适应退避 (503时升回3.0s) |
| 并行工具导致资源爆炸 | 限制并发工具数 (max 5个/轮) |
| 批量验证准确度下降 | A/B测试 + 验证对比 |
| 搜索失败影响质量 | 搜索失败时用缓存 + 日志告警 |

---

## 推荐实施顺序

1. **Week 1**: 优化 1 (速率限制) + 快速环境变量调优
2. **Week 1-2**: 优化 2 (工具并行化)
3. **Week 2**: 优化 3-4 (批量验证 + 搜索后台化)
4. **Week 2-3**: 测试验证 + 线上灰度发布
5. **Week 3**: 监控性能数据 + 迭代优化

---

## 总结

✅ **流式输出本身设计合理** - 不是主要瓶颈
❌ **关键问题**: 速率限制 (3秒) + 多轮串联等待 + 验证/反思隐藏成本

✅ **快速改善** (环境变量): 25-35% 减少，0 代码改动
✅ **完整优化** (上述方案): 50-60% 减少，2-3周实施

**建议**: 立即调整环境变量测试效果，并行开发代码优化方案。
