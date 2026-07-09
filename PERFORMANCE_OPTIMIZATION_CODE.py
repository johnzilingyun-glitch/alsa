"""
ALSA 性能优化代码示例 - 快速实施版本
可直接应用到项目代码中
"""

# =============================================================================
# 优化 1: 自适应速率限制 (推荐立即实施)
# 文件: python_service/app/services/llm_gateway.py
# 改动大小: 中等 (30-40行)
# 预期效果: 减少 30% 耗时
# =============================================================================

"""
BEFORE (原有代码):
    
    class RateLimiter:
        def __init__(self, min_interval: float = 3.0, max_concurrent: int = 2):
            self._min_interval = min_interval
            self._default_min_interval = min_interval
            ...
        
        async def acquire(self):
            await self._semaphore.acquire()
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_request_time
                if elapsed < self._min_interval:
                    wait_time = self._min_interval - elapsed
                    await asyncio.sleep(wait_time)
                self._last_request_time = time.monotonic()

AFTER (优化后):
"""

class RateLimiterOptimized:
    """改进的速率限制器 - 支持自适应间隔"""
    
    def __init__(
        self, 
        min_interval: float = 3.0, 
        max_concurrent: int = 2,
        tool_interval: float = 1.0,     # 新增: 工具轮的速率
        final_interval: float = 1.5,    # 新增: 最终轮的速率
    ):
        self._min_interval = min_interval
        self._default_min_interval = min_interval
        self._tool_interval = tool_interval       # 工具轮: 1.0s
        self._final_interval = final_interval     # 最终轮: 1.5s
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self, context: str = "default"):
        """
        根据上下文选择速率限制
        
        Args:
            context: 'tool' (工具轮) | 'final' (最终轮) | 'default' (其他)
        """
        await self._semaphore.acquire()
        async with self._lock:
            # 根据上下文选择最小间隔
            if context == "tool":
                min_interval = self._tool_interval         # 1.0s
            elif context == "final":
                min_interval = self._final_interval        # 1.5s
            else:
                min_interval = self._min_interval          # 3.0s (保守)
            
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < min_interval:
                wait_time = min_interval - elapsed
                logger.debug(f"[RateLimiter] Sleeping {wait_time:.2f}s (context={context})")
                await asyncio.sleep(wait_time)
            self._last_request_time = time.monotonic()

    def release(self, success: bool = True):
        """Release the semaphore after request completes."""
        if success:
            self._min_interval = self._default_min_interval
        self._semaphore.release()

    async def __aenter__(self, context: str = "default"):
        await self.acquire(context)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release(success=(exc_type is None))


# 在 LLMGateway.generate_content() 中的使用示例:
"""
# 改动 llm_gateway.py generate_content 方法

async def generate_content(
    self, 
    prompt: str, 
    model: str = None, 
    temperature: float = 0.3, 
    on_chunk: Optional[callable] = None, 
    gemini_api_key: Optional[str] = None, 
    deepseek_api_key: Optional[str] = None, 
    cache_key: Optional[str] = None, 
    prompt_version_id: Optional[str] = None, 
    response_schema: Optional[Any] = None,
    is_tool_round: bool = False,      # 新增参数
    is_final_round: bool = False,     # 新增参数
) -> str:
    
    # 确定调用上下文
    context = "final" if is_final_round else ("tool" if is_tool_round else "default")
    
    # 在 LLM 调用前使用新的速率限制
    async with self._rate_limiter.acquire(context):
        # 原有 LLM 调用代码...
        result = await llm_gateway_call(...)
    
    return result
"""


# =============================================================================
# 优化 2: 工具并行执行 (推荐一周内实施)
# 文件: python_service/app/services/expert_tools.py
# 改动大小: 中等 (50-70行)
# 预期效果: 减少 15-20% 耗时
# =============================================================================

"""
BEFORE (原有代码):

    # 工具调用在 agent_orchestrator.py 中串联执行
    for tool_call in tool_calls:
        result = await execute_single_tool(tool_call)
        # 下一个工具等待当前工具完成

AFTER (优化后):
"""

class ToolExecutorOptimized:
    """改进的工具执行器 - 支持并行执行"""
    
    @staticmethod
    async def execute_tools_batch(tool_calls: list) -> dict:
        """
        并行执行工具调用
        
        假设: 工具调用之间无依赖关系 (或依赖关系已在前端处理)
        """
        if not tool_calls:
            return {}
        
        results = {}
        tasks = []
        
        # 第一步: 启动所有工具调用任务
        for tool_call in tool_calls:
            tool_name = tool_call.get("function", {}).get("name", "unknown")
            task = asyncio.create_task(
                ToolExecutorOptimized._execute_single_tool_safe(tool_call)
            )
            tasks.append((tool_name, task))
        
        # 第二步: 并发等待所有任务完成
        for tool_name, task in tasks:
            try:
                result = await task
                results[tool_name] = result
                logger.info(f"[ToolExecutor] {tool_name} completed successfully")
            except Exception as e:
                logger.error(f"[ToolExecutor] {tool_name} failed: {e}")
                results[tool_name] = {"error": str(e), "status": "failed"}
        
        return results
    
    @staticmethod
    async def _execute_single_tool_safe(tool_call: dict) -> dict:
        """
        安全地执行单个工具
        """
        try:
            # 调用原有的工具执行逻辑
            from .expert_tools import execute_single_tool
            return await execute_single_tool(tool_call)
        except asyncio.TimeoutError:
            return {"error": "Tool execution timeout", "status": "timeout"}
        except Exception as e:
            return {"error": str(e), "status": "failed"}


# 在 agent_orchestrator.py 中的使用示例:
"""
# 改动 agent_orchestrator.py

# 原有代码:
# for tool_call in tool_calls_data:
#     result = await execute_single_tool(tool_call)
#     # ...

# 优化后代码:
if tool_calls_data:
    results = await ToolExecutorOptimized.execute_tools_batch(tool_calls_data)
    # 处理所有工具结果...
"""


# =============================================================================
# 优化 3: 搜索后台化 (推荐一周内实施)
# 文件: python_service/app/services/discussion_service.py
# 改动大小: 小 (20-30行)
# 预期效果: 减少 10-15% 耗时
# =============================================================================

"""
BEFORE (原有代码):

    async def run_discussion(self, symbol, name, snapshot, ...):
        # 阻塞式等待搜索完成
        search_results = await asyncio.wait_for(
            search_toolkit.batch_search(symbol, name, snapshot),
            timeout=30.0  # 可能阻塞 30 秒
        )
        
        # 然后开始讨论
        for r_info in topology:
            ...

AFTER (优化后):
"""

class DiscussionServiceOptimized:
    async def run_discussion_optimized(
        self, 
        symbol: str, 
        name: str, 
        snapshot: dict, 
        level: str = "standard", 
        **kwargs
    ):
        """改进的讨论流程 - 搜索后台化"""
        
        # 第一步: 立即启动搜索任务 (不阻塞)
        search_task = asyncio.create_task(
            self._async_search_wrapper(symbol, name, snapshot)
        )
        
        topology = self.build_topology(level, **kwargs)
        search_results = {}  # 初始为空
        
        # 第二步: 讨论进行中异步获取搜索结果
        for round_idx, r_info in enumerate(topology):
            # 在每一轮开始前，检查搜索是否已完成
            if search_task.done() and not search_results:
                try:
                    search_results = search_task.result()
                    logger.info(f"[DiscussionService] Search results available at round {round_idx}")
                except Exception as e:
                    logger.warning(f"[DiscussionService] Search failed (non-fatal): {e}")
                    search_results = {}
            
            # 继续讨论，使用可能的搜索结果
            experts = r_info["experts"]
            
            # 并行调用专家 (如果该轮是并行的)
            if r_info.get("parallel", False):
                results = await asyncio.gather(*[
                    self._call_expert(
                        role=expert,
                        search_results=search_results,  # 使用最新搜索结果
                        **kwargs
                    )
                    for expert in experts
                ])
            else:
                # 串联调用
                results = []
                for expert in experts:
                    result = await self._call_expert(
                        role=expert,
                        search_results=search_results,
                        **kwargs
                    )
                    results.append(result)
            
            # 处理结果...
        
        return results
    
    async def _async_search_wrapper(self, symbol, name, snapshot):
        """搜索包装 - 超时后返回空结果"""
        try:
            # 最多等待 20 秒 (比原来的 30 秒短)
            result = await asyncio.wait_for(
                self._batch_search(symbol, name, snapshot),
                timeout=20.0
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"[DiscussionService] Search timed out for {symbol}")
            return {}  # 返回空，讨论继续
        except Exception as e:
            logger.error(f"[DiscussionService] Search error: {e}")
            return {}


# =============================================================================
# 优化 4: 前端流式更新频率 (立即可做)
# 文件: python_service/app/services/llm_gateway.py
# 改动大小: 小 (5-10行)
# 预期效果: 主观快 30% (UX 改善)
# =============================================================================

"""
BEFORE (原有代码):

    def _safe_on_chunk(*args, **kwargs):
        now = time.monotonic()
        if (now - _last_call_time[0] > 0.5) or len(args) != 1:
            # 0.5 秒才发一次
            ...

AFTER (优化后):
"""

def create_streaming_callback_optimized(on_chunk_callback):
    """改进的流式回调 - 更高频率的前端更新"""
    
    _last_call_time = [0.0]
    _chunk_buffer = []
    _accumulated_chars = 0
    
    def _safe_on_chunk(*args, **kwargs):
        nonlocal _accumulated_chars
        
        now = time.monotonic()
        
        # 改进: 100ms 或 10 个 chunk，取先到者
        time_elapsed = now - _last_call_time[0]
        
        # 累积字符
        if args and isinstance(args[0], int):
            _accumulated_chars += args[0]
        
        should_send = (
            time_elapsed > 0.1      # 100ms 触发 (原来 0.5s)
            or len(_chunk_buffer) > 10  # 或 10 个 chunk
            or kwargs               # 或有额外参数 (消息)
        )
        
        if should_send and on_chunk_callback:
            _last_call_time[0] = now
            
            if kwargs:
                # 发送带消息的更新
                on_chunk_callback(_accumulated_chars, **kwargs)
            else:
                # 发送字符计数更新
                on_chunk_callback(_accumulated_chars)
            
            _accumulated_chars = 0
            _chunk_buffer = []
        else:
            # 缓冲 chunk
            if args:
                _chunk_buffer.extend(args)
    
    return _safe_on_chunk


# =============================================================================
# 优化 5: 环境变量快速配置 (立即可做, 无需代码改动)
# 文件: .env 或 .env.runtime
# 改动大小: 极小 (3行)
# 预期效果: 减少 25-35% 耗时
# =============================================================================

"""
# .env 原有配置:
LLM_RATE_LIMIT_INTERVAL=3.0
MAX_CONCURRENT_JOBS=5
VERIFICATION_MODE=quick
LLM_STREAM_TIMEOUT_SECONDS=300

# .env 优化后配置:
LLM_RATE_LIMIT_INTERVAL=1.5        # 从 3.0s 改为 1.5s (需监控503)
MAX_CONCURRENT_JOBS=10             # 从 5 改为 10 (增加吞吐)
VERIFICATION_MODE=quick            # 保持 quick (已是较优)
LLM_STREAM_TIMEOUT_SECONDS=300     # 保持不变
BATCH_SEARCH_TIMEOUT=15            # 新增: 搜索超时改短
LLM_STREAM_THROTTLE_MS=100         # 新增: 前端更新频率 (100ms)

# 生效: 重启 Python 服务
# systemctl restart alsa-python-service
"""


# =============================================================================
# 优化 6: 快速模式 - 跳过非必要验证 (针对 QUICK 拓扑)
# 文件: python_service/app/services/discussion_service.py
# 改动大小: 小 (10-15行)
# 预期效果: QUICK 拓扑减少 30%，STANDARD 不明显
# =============================================================================

"""
BEFORE (原有代码):

    # 所有模式都进行相同的验证
    if should_verify:
        verification = grounding_verifier.verify(content, snapshot)

AFTER (优化后):
"""

def should_verify_optimized(
    level: str,
    verification_mode: str,
    has_external_facts: bool,
    is_final_expert: bool
) -> bool:
    """
    智能决定是否需要验证
    
    Args:
        level: 分析级别 ('quick', 'standard', 'deep')
        verification_mode: 验证模式 ('extreme', 'quick', 'quality')
        has_external_facts: 内容是否包含外部事实
        is_final_expert: 是否为最终专家
    """
    
    # 极速模式: 跳过所有验证
    if verification_mode == "extreme":
        return False
    
    # 质量模式: 验证所有 + 最终专家强制验证
    if verification_mode == "quality":
        return True
    
    # 快速模式 (默认):
    # - QUICK 拓扑: 仅最终专家验证
    # - STANDARD/DEEP: 最终专家 + 有事实的内容
    if verification_mode == "quick":
        if level == "quick" and not is_final_expert:
            # QUICK 拓扑的中间专家跳过验证 (节省 30% 耗时)
            return False
        
        if is_final_expert:
            # 最终专家总是验证
            return True
        
        # 中间专家仅对有事实的内容验证
        return has_external_facts
    
    return True


# =============================================================================
# 总结: 推荐实施顺序
# =============================================================================

"""
Week 1:
  1. 修改 .env: LLM_RATE_LIMIT_INTERVAL = 1.5 (立即, 5分钟)
  2. 实施优化 1: 自适应速率限制 (2小时编码 + 1小时测试)
  3. 验证效果: 对比基线 vs 优化后耗时

Week 2:
  4. 实施优化 2: 工具并行执行 (3小时编码 + 1小时测试)
  5. 实施优化 3: 搜索后台化 (1小时编码 + 30分钟测试)

Week 3:
  6. 实施优化 4: 前端更新频率 (30分钟编码)
  7. 实施优化 6: 快速模式 (1小时编码)
  8. 综合测试 + 性能报告

预期效果:
  - 快速改善 (env 变量): -30% 耗时 (90s → 63s)
  - Week 1 后: -40% 耗时 (90s → 54s)
  - Week 2 后: -50% 耗时 (90s → 45s)
  - Week 3 完成: -55-60% 耗时 (90s → 36-40s)

目标: <60 秒 QUICK 分析, <120 秒 STANDARD 分析 ✅
"""
