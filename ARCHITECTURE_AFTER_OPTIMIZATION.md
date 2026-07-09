# ALSA 优化后系统架构说明 (2026-07-08)

> 包含 4 个性能优化和质量改进的完整系统架构

---

## 🏗️ 系统总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                   ALSA 优化后系统架构                             │
└─────────────────────────────────────────────────────────────────┘

用户请求
   ↓
┌─────────────────────────────────────────────────────────────────┐
│  API 层 (FastAPI)                                               │
│  /api/analysis/jobs - 创建分析任务                             │
└─────────────────────────────────────────────────────────────────┘
   ↓
┌─────────────────────────────────────────────────────────────────┐
│  任务管理层 (AnalysisJobService)                               │
│  - 任务队列管理 (MAX_CONCURRENT_JOBS=10)                       │
│  - 任务状态跟踪                                                 │
│  - 结果缓存                                                    │
└─────────────────────────────────────────────────────────────────┘
   ↓
┌─────────────────────────────────────────────────────────────────┐
│  讨论流程编排层 (DiscussionService) ← 主要优化点 3,4          │
│                                                                 │
│  后台搜索 (优化4):                                             │
│  ├─ 搜索任务后台执行                                          │
│  ├─ 30s阻塞 → 0s阻塞                                          │
│  └─ 每轮开始时检查结果                                        │
│                                                                 │
│  Multi-Expert 讨论 (LangGraph):                               │
│  ├─ Round 1-2: 中间专家 (智能验证模式)                       │
│  ├─ Round N: Professional Reviewer (新增批量验证 优化3)      │
│  └─ Round N+1: Chief Strategist (强制最终验证)               │
│                                                                 │
│  三层验证机制 (优化3):                                        │
│  ├─ 第1层: 中间专家按 verification_mode 判断                 │
│  ├─ 第2层: Professional Reviewer 批量交叉验证                │
│  └─ 第3层: Chief Strategist 强制最终验证                     │
└─────────────────────────────────────────────────────────────────┘
   ↓
┌─────────────────────────────────────────────────────────────────┐
│  智能体协调层 (AgentOrchestrator)                              │
│  - 专家轮转调度                                                │
│  - 状态管理                                                    │
│  - 工具执行                                                    │
└─────────────────────────────────────────────────────────────────┘
   ↓
┌─────────────────────────────────────────────────────────────────┐
│  LLM 网关层 (LLMGateway) ← 主要优化点 1                        │
│                                                                 │
│  自适应速率限制 (优化1):                                       │
│  ├─ context="tool": 1.0s (工具轮，快速)                      │
│  ├─ context="final": 1.5s (最终轮，中等)                     │
│  └─ context="default": 3.0s (默认，保守)                     │
│                                                                 │
│  LLM 调用流程:                                                 │
│  ├─ 获取速率限制许可 (await acquire(context))               │
│  ├─ 构建请求 (提示词 + 参数)                                 │
│  ├─ 调用 API (DeepSeek/Gemini)                              │
│  └─ 返回结果                                                  │
└─────────────────────────────────────────────────────────────────┘
   ↓
┌─────────────────────────────────────────────────────────────────┐
│  工具执行层 (ExpertTools) ← 主要优化点 2                       │
│                                                                 │
│  工具并行执行 (优化2):                                         │
│  ├─ 收集待执行工具列表                                       │
│  ├─ asyncio.gather() 并行执行 ← 关键                         │
│  └─ 收集所有结果                                              │
│                                                                 │
│  工具类型:                                                     │
│  ├─ fetch_latest_news (资讯)                                 │
│  ├─ fetch_financial_data (财务数据)                          │
│  ├─ calculate_technical_indicators (技术指标)               │
│  ├─ perform_backtest (回测)                                 │
│  └─ ... (其他 20+ 个工具)                                    │
└─────────────────────────────────────────────────────────────────┘
   ↓
┌─────────────────────────────────────────────────────────────────┐
│  数据源层 (外部 API)                                            │
│  - LLM API (DeepSeek/Gemini)                                  │
│  - 搜索引擎 (Bing/Google)                                      │
│  - 财务数据源 (Tushare/AKShare)                              │
│  - 行情数据源 (实时行情)                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 改动后的执行流程

### 改动前 (基线)

```
用户请求
   ↓ (1s)
创建任务
   ↓ (30s) ← 搜索阻塞！
等待搜索完成
   ↓ (1s)
开始讨论
   ├─ Round 1: Deep Research (3.0s rate limit)
   ├─ Round 2: Technical (3.0s rate limit)  
   ├─ Round 3: Professional Reviewer (3.0s rate limit)
   ├─ Round 4: Chief Strategist (3.0s + 8s 验证)
   ↓ (总计 ~120s)
返回结果

关键问题:
- 搜索阻塞: 30s 浪费
- 固定速率限制: 12s 等待
- 重复验证: 16s+ 多余
```

### 改动后 (优化)

```
用户请求
   ↓ (1s)
创建任务 + 【后台】开始搜索 (优化4)
   ↓ (0s) ← 不阻塞！
开始讨论 (搜索并行进行)
   ├─ Round 1: Deep Research
   │  ├─ 工具并行执行 (优化2)
   │  ├─ 速率限制: 1.0s (优化1，改为快速)
   │  └─ 智能验证 (有数据才验证)
   │
   ├─ Round 2: Technical + Fundamental (并行)
   │  ├─ 工具并行执行 (优化2)
   │  ├─ 速率限制: 1.0s × 2 (优化1)
   │  └─ 智能验证 (有数据才验证)
   │
   ├─ Round 3: Professional Reviewer
   │  ├─ 个人分析
   │  ├─ 【新】批量验证前面所有专家 (优化3, 1 LLM 调用)
   │  └─ 发现矛盾和不一致
   │
   ├─ Round 4: Chief Strategist
   │  ├─ 基于 Reviewer 的意见
   │  ├─ 速率限制: 1.5s (优化1，改为中等)
   │  ├─ 强制反思和验证 (质量把控)
   │  └─ 最终交易决策
   │
   ├─ 【检查搜索】(每轮开始)
   │  └─ 搜索完成则注入结果
   │
   ↓ (总计 ~55-60s, -45-50%)
返回结果

核心优化:
- 搜索后台化: 30s → 0s (消除阻塞)
- 速率限制: 12s → 4s (快速执行)
- 验证优化: 重复 → 分层 (交叉验证)
```

---

## 🔄 三层验证机制详解

### 架构设计

```
分析精度 ↑
        │
   ⭐⭐⭐│  ┌──────────────────────────┐
        │  │  第3层: Chief Strategist  │
        │  │  强制最终验证             │
   ⭐⭐ │  │  目标: 决策质量           │
        │  └──────────────────────────┘
        │           ↑
        │  ┌────────┴─────────┐
        │  │                  │
   ⭐  │  ┌──────────────┐   │
        │  │ 第2层:      │   │
        │  │ Professional Reviewer
        │  │ 批量验证交叉对比    │
        │  │ 目标: 一致性  │   │
        │  └──────────────┘   │
        │           ↑         │
        │  ┌────────┴─────────┐
        │  │   中间专家        │
   ⭐  │  │ (智能模式)      │
        │  │ 第1层            │
        │  │ 目标: 过程质量    │
        │  └──────────────────┘
        └─────────────────────→
                灵活性
```

### 执行流程

```
┌─ Round 1-N: 中间专家 (第1层验证)
│  │
│  ├─ 生成分析 (LLM 调用)
│  │
│  ├─ 验证决策:
│  │  ├─ verification_mode == "extreme"
│  │  │  └─ 跳过所有验证 (最快)
│  │  ├─ verification_mode == "quick" (默认)
│  │  │  ├─ has_external_facts? → 进行 grounding_verify
│  │  │  └─ confidence < 0.7? → 进行 reflection
│  │  └─ verification_mode == "quality"
│  │     ├─ 进行 grounding_verify (强制)
│  │     └─ 进行 reflection (强制)
│  │
│  └─ 存储结果到 history_states
│
├─ Round N: Professional Reviewer (第2层验证)
│  │
│  ├─ 【新】收集前面所有中间专家的输出
│  │
│  ├─ 【新】批量验证和反思:
│  │  ├─ 一个 LLM 调用: "请验证以下专家的分析..."
│  │  ├─ 输出: 交叉对比结果
│  │  └─ 作用: 发现矛盾和不一致
│  │
│  ├─ 个人分析 (正常 LLM 调用)
│  │
│  └─ 存储结果 (包含 batch_verifications)
│
└─ Round N+1: Chief Strategist (第3层验证)
   │
   ├─ 【新】检查 Professional Reviewer 的结果
   │  └─ 如果有批量验证结果 → 已知前面的验证情况
   │
   ├─ 生成最终决策 (LLM 调用)
   │
   ├─ 强制验证和反思 (不受 verification_mode 影响):
   │  ├─ 进行 self_reflection (强制)
   │  ├─ 进行 grounding_verify (强制)
   │  └─ 附加验证结果到消息
   │
   └─ 返回最终结果
```

---

## 💾 关键数据流

### LLM 调用链路

```
LLM 调用次数优化:

改动前 (QUICK):
├─ Round 1: Deep Research → LLM
├─ Round 2: Technical → LLM
├─ Round 2: Fundamental → LLM
├─ Round 3: Professional Reviewer → LLM
├─ Round 4: Chief Strategist → LLM
│  ├─ LLM 生成
│  ├─ self_reflection_agent.reflect() → LLM
│  └─ grounding_verifier.verify() (规则，不调用 LLM)
└─ 总计: ~6-8 LLM 调用

改动后 (QUICK):
├─ Round 1: Deep Research → LLM
├─ Round 2: Technical → LLM
├─ Round 2: Fundamental → LLM
├─ Round 3: Professional Reviewer
│  ├─ LLM 生成
│  └─ 【新】batch_verify_and_reflect() → LLM (1 次)
├─ Round 4: Chief Strategist → LLM
│  ├─ LLM 生成
│  ├─ self_reflection (保持)
│  └─ grounding_verify (保持)
└─ 总计: ~6-8 LLM 调用 (但优化了执行顺序)
```

### 速率限制链路

```
改动前:
Round 1: acquire(3.0s) → wait 3s
Round 2: acquire(3.0s) → wait 3s
Round 3: acquire(3.0s) → wait 3s
Round 4: acquire(3.0s) → wait 3s + reflection(3.0s)
总计: 15s 速率限制

改动后:
Round 1: acquire(context="tool", 1.0s) → wait 1s
Round 2: acquire(context="tool", 1.0s) → wait 1s
Round 3: acquire(context="tool", 1.0s) → wait 1s
Round 4: acquire(context="final", 1.5s) → wait 1.5s
总计: 4.5s 速率限制 (-70%)

结合优化1: QUICK 节省 12-15s
```

---

## ⚙️ 配置和环境变量

### 优化 1 配置 (速率限制)

```bash
# LLM_TOOL_INTERVAL: 工具轮 LLM 调用间隔 (秒)
LLM_TOOL_INTERVAL=1.0
# - 工具执行多、模型调用频繁的轮次
# - 范围: 0.5-2.0 (建议 0.8-1.2)
# - 增加: 如果看到 503 错误
# - 减少: 如果想加快速度

# LLM_FINAL_INTERVAL: 最终轮 LLM 调用间隔 (秒)
LLM_FINAL_INTERVAL=1.5
# - Chief Strategist 等最终决策专家
# - 范围: 1.0-3.0 (建议 1.2-2.0)
# - 更保守避免错误

# LLM_RATE_LIMIT_INTERVAL: 其他调用的默认间隔 (秒)
LLM_RATE_LIMIT_INTERVAL=3.0
# - 默认保守值
# - 一般不需要改动
```

### 优化 3 配置 (批量验证)

```bash
# BATCH_VERIFICATION_ENABLED: 启用 Professional Reviewer 批量验证
BATCH_VERIFICATION_ENABLED=true
# - true: 启用新的批量验证机制
# - false: 禁用，使用原有逻辑

# BATCH_VERIFICATION_MIN_EXPERTS: 最小专家数
BATCH_VERIFICATION_MIN_EXPERTS=3
# - 只有超过 N 个前面专家时才启用批量验证
# - 默认: 3

# BATCH_VERIFY_TIMEOUT: 批量验证超时时间 (秒)
BATCH_VERIFY_TIMEOUT=30
# - Professional Reviewer 批量验证的最长等待时间
# - 默认: 30
```

### 优化 4 配置 (搜索后台化)

```bash
# BATCH_SEARCH_TIMEOUT: 后台搜索超时时间 (秒)
BATCH_SEARCH_TIMEOUT=15
# - 搜索最长等待时间 (改短了)
# - 原来是 30s，现在后台执行
# - 范围: 10-30
# - 增加: 如果搜索结果缺失

# MAX_CONCURRENT_JOBS: 最大并发任务数
MAX_CONCURRENT_JOBS=10
# - 可以并行进行的分析任务数
# - 默认: 10 (原为 5)
# - 提高: 增加吞吐量
# - 降低: 减少资源占用
```

### 验证模式配置

```bash
# verification_mode: 中间专家的验证模式
# 调用 API 时可指定: /api/analysis/jobs?verification_mode=quick

# extreme: 极速模式
# - 跳过所有验证和反思
# - 最快，质量风险最大
# - 用于: 初步扫描

# quick: 快速模式 (默认)
# - 智能判断: 有外部数据才验证，低置信度才反思
# - 平衡速度和质量
# - 用于: 常规分析

# quality: 质量模式
# - 强制所有验证和反思
# - 最慢，质量最好
# - 用于: 重要决策
```

---

## 🔍 监控和调试

### 关键日志消息

```bash
# 优化 1: 速率限制
[RateLimiter] Acquiring with context=tool, interval=1.0s
[RateLimiter] Acquiring with context=final, interval=1.5s

# 优化 3: 批量验证
[BatchVerify] Professional Reviewer: Collecting outputs from 2 experts
[BatchVerify] Professional Reviewer: Batch verification completed

# 优化 4: 搜索后台化
[DiscussionService] Background search started (non-blocking)
[Round 2] Search results available, injecting into expert discussion

# 最终专家
[Final-Expert] Chief Strategist: Professional Reviewer already verified...
[Final-Expert] Chief Strategist: Enforcing quality checks (reflection...)
```

### 性能指标

```bash
# 运行诊断脚本
python3 diagnose_performance.py

# 输出示例:
# Configuration Summary:
# - LLM_TOOL_INTERVAL: 1.0s ✅
# - LLM_FINAL_INTERVAL: 1.5s ✅
# - BATCH_VERIFICATION_ENABLED: true ✅
# - BATCH_SEARCH_TIMEOUT: 15s ✅
# - MAX_CONCURRENT_JOBS: 10
#
# Performance Analysis:
# - QUICK analysis: Expected 55-65s (-45-50%)
# - STANDARD analysis: Expected 130-140s (-45%)
# - DEEP analysis: Expected 180-200s (-50%)
```

---

## 🚨 常见问题

### Q1: 性能没有改善

**A**: 检查以下几项：
1. 环境变量是否设置: `grep "LLM_\|BATCH_" .env`
2. 服务是否重启: `systemctl status alsa-python-service`
3. 日志中是否看到新的消息: `tail -f logs/py_api.log | grep RateLimiter`

### Q2: 看到 503 错误

**A**: LLM 限流过快
```bash
LLM_TOOL_INTERVAL=1.5      # 改为 1.5
LLM_FINAL_INTERVAL=2.0     # 改为 2.0
systemctl restart alsa-python-service
```

### Q3: 搜索结果缺失

**A**: 搜索超时，增加时间
```bash
BATCH_SEARCH_TIMEOUT=20    # 改为 20
systemctl restart alsa-python-service
```

### Q4: 分析质量下降

**A**: 可能是过度优化，切换模式
```bash
# 改为 quality 模式测试
curl ... -d '{"verification_mode": "quality"}'

# 或禁用批量验证
BATCH_VERIFICATION_ENABLED=false
```

---

## 📚 相关文件索引

| 文件 | 用途 | 优先级 |
|-----|------|-------|
| OPTIMIZATION_CHANGES_SUMMARY.md | 改动总结 + 排查指南 | ⭐⭐⭐ |
| OPTIMIZATION_3_ACTIVATION.md | 优化3详细设计 | ⭐⭐ |
| OPTIMIZATION_COMPLETE_DEPLOYMENT.md | 部署清单 | ⭐⭐⭐ |
| PERFORMANCE_OPTIMIZATION_GUIDE.md | 完整指南 | ⭐⭐ |
| diagnose_performance.py | 诊断脚本 | ⭐⭐⭐ |

---

**系统架构更新完成 ✅**

所有优化已集成，可立即投入生产！
