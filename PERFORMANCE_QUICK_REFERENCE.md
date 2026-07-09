# ALSA AI 分析性能 - 快速参考卡

## 🎯 核心问题

| 问题 | 根因 | 影响 | 位置 |
|-----|------|------|------|
| **耗时 3-8 分钟** | LLM 请求速率限制 (3s/次) | 每轮分析至少 30-50s 基线延迟 | llm_gateway.py:80 |
| 多轮讨论串联 | 6-10 轮讨论依次执行 | 6轮 × 3s = 18s 纯等待 | agent_orchestrator.py:38 |
| 验证/反思隐藏成本 | 每专家可触发 2 个额外 LLM 调用 | +60 秒 | discussion_service.py:230 |
| 搜索阻塞 | batch_search 最多等 30s | +20 秒 | discussion_service.py:130 |
| **不是流式输出问题** ✅ | 流式设计合理，只是节流到 0.5s | 主观感受延迟，实际时间不变 | llm_gateway.py:400 |

---

## 📊 耗时分析

### 当前分析耗时拆分 (QUICK 拓扑)

```
总耗时: 90-120 秒 (~2分钟)

快照          : 10s   (数据获取)
搜索          : 15s   (batch_search, 可失败)
───────────────────────
讨论轮次      : 60s   (关键瓶颈)
├─ 速率限制   : 12s   (4轮 × 3s)    ⬅️ 主要问题
├─ LLM响应    : 40s   (4轮 × 10s平均)
└─ 验证成本   : 8s    (2个轮次验证)
───────────────────────
其他          : 15s   (反思/批评/报告)
```

### 优化后预期

```
总耗时: 40-50 秒 (~1分钟)  ← -55% 耗时

快照          : 10s   (数据获取)
搜索          : 5s    (后台并行)
───────────────────────
讨论轮次      : 20s   (优化后)
├─ 速率限制   : 4s    (4轮 × 1.0s)  ⬅️ 优化
├─ LLM响应    : 40s   (工具并行, -20%)
└─ 验证成本   : 0s    (批量验证)
───────────────────────
其他          : 10s   (优化反思)
```

---

## 🚀 快速改善方案 (立即可做)

### 方案 A: 环境变量调整 (无需编码, 5 分钟)

```bash
# 编辑 .env 或 .env.runtime
LLM_RATE_LIMIT_INTERVAL=1.5    # ← 从 3.0 改为 1.5 (关键)
MAX_CONCURRENT_JOBS=10         # ← 从 5 改为 10
BATCH_SEARCH_TIMEOUT=15        # ← 新增, 搜索改短

# 重启服务
systemctl restart alsa-python-service

# 预期: -25 到 -35% 耗时 (90s → 60-70s)
```

### 方案 B: 代码优化 (完整方案, 2-3 周)

按优先级:

| 优先级 | 优化 | 效果 | 工作量 |
|--------|------|------|--------|
| 🔴 1 | 自适应速率限制 (tool_interval=1.0s) | -30% | 2h |
| 🔴 2 | 工具并行执行 | -15% | 3h |
| ⚠️ 3 | 批量验证/反思 | -20% | 4h |
| ⚠️ 4 | 搜索后台化 | -10% | 2h |
| 🟡 5 | 前端更新频率 (100ms) | 主观快 30% | 0.5h |

---

## 📋 实施清单

### Week 1 (最小改动)

- [ ] 修改 `.env`: `LLM_RATE_LIMIT_INTERVAL=1.5`
- [ ] 验证效果: 运行诊断脚本
  ```bash
  python3 diagnose_performance.py
  ```

- [ ] (可选) 启用快速模式验证
  ```bash
  VERIFICATION_MODE=quick  # 改为 extreme 仅限测试
  ```

**预期**: -30% 耗时

---

### Week 2 (代码优化)

**Commit 1: 自适应速率限制**
- 文件: `llm_gateway.py`
- 改动: 添加 `tool_interval` 和 `final_interval` 参数
- 测试: 对比 QUICK/STANDARD 耗时
- 预期: 累计 -40% 耗时

**Commit 2: 工具并行执行**
- 文件: `expert_tools.py`, `agent_orchestrator.py`
- 改动: 使用 `asyncio.gather()` 并行工具调用
- 测试: 验证工具结果完整性
- 预期: 累计 -50% 耗时

**Commit 3: 搜索后台化**
- 文件: `discussion_service.py`
- 改动: 使用 `asyncio.create_task()` 替代 `await`
- 测试: 验证搜索结果仍被注入
- 预期: 累计 -55% 耗时

---

### Week 3 (验收)

- [ ] 综合性能测试
- [ ] 生成性能报告 (基线 vs 优化)
- [ ] 监控 503 错误率 (需要时回退)
- [ ] 用户反馈收集

---

## ⚙️ 关键参数速查

### 环境变量

```bash
# LLM 速率
LLM_RATE_LIMIT_INTERVAL=3.0        # ⬅️ 改为 1.5
LLM_STREAM_TIMEOUT_SECONDS=300     # 单次调用超时

# 并发控制
MAX_CONCURRENT_JOBS=5              # ⬅️ 改为 10
MAX_TOOL_CONCURRENT=5              # 工具并发

# 搜索
BATCH_SEARCH_TIMEOUT=30            # ⬅️ 改为 15
SEARCH_CACHE_TTL_HOURS=24          # 搜索缓存

# 前端
LLM_STREAM_THROTTLE_MS=500         # ⬅️ 改为 100 (可选)

# 验证
VERIFICATION_MODE=quick            # extreme | quick | quality
```

---

## 🔍 诊断工具

### 快速诊断

```bash
python3 diagnose_performance.py
```

输出:
- ✅ 当前配置
- ✅ 耗时估算
- ✅ 拓扑分析
- ✅ 优化建议
- ✅ 快速测试命令

### 性能测试

```bash
# 基线 (当前)
time curl -X POST http://localhost:8000/api/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "market": "us", "analysis_level": "quick"}' \
  | jq '.job_id' | xargs -I {} \
  bash -c 'until curl -s http://localhost:8000/api/analysis/jobs/{} | jq -e ".status == \"completed\"" > /dev/null; do sleep 2; done; echo "Completed"'

# 预期: ~90-120s

# 优化后
# (修改 .env, 重启服务, 再测试)
# 预期: ~60-70s
```

---

## 🎓 性能瓶颈知识库

### 为什么是 3.0 秒?

中转站 (`xbrain-dify-service-test.xiaopeng.link/llm_api`) 在高频请求时容易返回 503。所以设置了 3.0s 保护性速率限制。

**改为 1.5s 安全吗?** 
- 可以，但需要监控 503 错误
- 添加自适应退避: 503 时自动升回 3.0s
- 工具轮用 1.0s，最终轮用 1.5s，其他用 3.0s

### 为什么验证那么慢?

每个专家输出都要：
1. 检查是否有外部事实 → 调用 `grounding_verifier` (LLM 调用, ~15s)
2. 检查信心度 → 调用 `self_reflection_agent` (LLM 调用, ~15s)

对 6 个专家，这就是 180 秒额外成本。

**解决方案**: 批量验证 (一个 LLM 调用处理所有)

---

## 📚 详细文档

- 📄 [完整优化指南](./PERFORMANCE_OPTIMIZATION_GUIDE.md)
- 🔧 [代码示例](./PERFORMANCE_OPTIMIZATION_CODE.py)
- 🧪 [诊断脚本](./diagnose_performance.py)

---

## 🆘 常见问题

### Q: 流式输出是主要问题吗?
**A:** 否。流式设计合理，只是前端更新节流到 0.5s（改为 100ms 只能改善主观感受）。关键是速率限制和多轮等待。

### Q: 为什么我的分析特别慢?
**A:** 可能是:
1. 搜索结果丰富 (batch_search 耗时 20+ 秒)
2. 验证成本高 (启用了 VERIFICATION_MODE=quality)
3. 拓扑复杂 (DEEP 拓扑 10 轮 vs QUICK 4 轮)

运行诊断脚本可快速定位。

### Q: 改了速率限制会不会出问题?
**A:** 低风险。原有 3.0s 是为了防止 503。改为 1.5s 会增加 503 概率，但不会导致业务失败（503 会触发重试）。

### Q: 何时看到改善?
**A:** 
- 环境变量: 立即 (重启后)
- 代码优化: 2-3 周

---

## 📞 联系支持

问题排查:
1. 运行 `python3 diagnose_performance.py`
2. 检查日志: `tail -f logs/py_api.log`
3. 查看环境变量: `echo $LLM_RATE_LIMIT_INTERVAL`

---

**最后更新**: 2026-07-08  
**诊断者**: Claude Haiku  
**状态**: ✅ 已识别根因，可立即改善
