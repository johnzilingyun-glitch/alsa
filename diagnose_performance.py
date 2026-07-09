#!/usr/bin/env python3
"""
ALSA 性能诊断脚本
- 检测 LLM 请求间隔
- 分析讨论拓扑
- 估算分析耗时
"""

import os
import sys
import json
from pathlib import Path

# 尝试导入项目模块
sys.path.insert(0, str(Path(__file__).parent / "python_service"))

def diagnose_rate_limit():
    """检测当前速率限制配置"""
    print("\n" + "="*70)
    print("【诊断 1】LLM 请求速率限制")
    print("="*70)
    
    # 检查环境变量
    env_interval = os.getenv("LLM_RATE_LIMIT_INTERVAL", "3.0")
    env_timeout = os.getenv("LLM_STREAM_TIMEOUT_SECONDS", "300")
    env_max_jobs = os.getenv("MAX_CONCURRENT_JOBS", "5")
    
    print(f"\n当前配置:")
    print(f"  LLM_RATE_LIMIT_INTERVAL     : {env_interval} 秒 (间隔)")
    print(f"  LLM_STREAM_TIMEOUT_SECONDS  : {env_timeout} 秒 (单次调用超时)")
    print(f"  MAX_CONCURRENT_JOBS         : {env_max_jobs} 个 (并发job)")
    
    interval_s = float(env_interval)
    
    # 计算分析耗时
    print(f"\n耗时估算:")
    
    topologies = {
        "QUICK": {"rounds": 4, "avg_llm_per_round": 20},
        "STANDARD": {"rounds": 6, "avg_llm_per_round": 25},
        "DEEP": {"rounds": 10, "avg_llm_per_round": 30},
    }
    
    for level, config in topologies.items():
        rounds = config["rounds"]
        avg_llm = config["avg_llm_per_round"]
        
        # 保守估计: 每轮 (间隔 + LLM响应)
        rate_limit_cost = rounds * interval_s
        llm_cost = rounds * avg_llm
        verification_cost = rounds * 10  # 假设 50% 的轮次需要验证
        total = rate_limit_cost + llm_cost + verification_cost
        
        print(f"\n  {level}:")
        print(f"    - 速率限制成本  : {rate_limit_cost:.0f}s (={rounds} 轮 × {interval_s}s)")
        print(f"    - LLM 响应成本  : {llm_cost:.0f}s (={rounds} 轮 × {avg_llm}s)")
        print(f"    - 验证开销      : {verification_cost:.0f}s")
        print(f"    - 预计总时间    : {total:.0f}s (~{total//60}分{total%60:.0f}秒)")
    
    # 诊断建议
    print(f"\n⚠️  诊断结果:")
    if interval_s >= 3.0:
        print(f"  ❌ 速率限制过高 ({interval_s}s)")
        print(f"     建议: 降至 1.0-1.5s (需要监控503错误)")
    elif interval_s >= 1.5:
        print(f"  ⚠️  速率限制适中 ({interval_s}s)")
        print(f"     建议: 可尝试降至 1.0s")
    else:
        print(f"  ✅ 速率限制合理 ({interval_s}s)")
    
    return interval_s


def diagnose_topology():
    """分析讨论拓扑结构"""
    print("\n" + "="*70)
    print("【诊断 2】讨论拓扑和并行度")
    print("="*70)
    
    try:
        from app.services.discussion_service import (
            QUICK_TOPOLOGY,
            STANDARD_TOPOLOGY,
            DEEP_TOPOLOGY
        )
        
        topologies = {
            "QUICK": QUICK_TOPOLOGY,
            "STANDARD": STANDARD_TOPOLOGY,
            "DEEP": DEEP_TOPOLOGY,
        }
        
        for name, topo in topologies.items():
            print(f"\n  {name} 拓扑:")
            total_experts = 0
            parallel_rounds = 0
            
            for round_info in topo:
                round_num = round_info["round"]
                experts = round_info["experts"]
                is_parallel = round_info.get("parallel", False)
                
                total_experts += len(experts)
                if is_parallel:
                    parallel_rounds += 1
                
                parallel_mark = "║" if is_parallel else "║ (串联)"
                print(f"    {round_num:2}. {', '.join(experts[:2])}{'...' if len(experts) > 2 else '':<20} {parallel_mark}")
            
            print(f"    ─────────────────────────────────")
            print(f"    总专家数: {total_experts}, 并行轮数: {parallel_rounds}/{len(topo)}")
    
    except ImportError as e:
        print(f"  ⚠️  无法导入拓扑: {e}")


def diagnose_verification():
    """检测验证和反思的成本"""
    print("\n" + "="*70)
    print("【诊断 3】验证和反思成本")
    print("="*70)
    
    env_mode = os.getenv("VERIFICATION_MODE", "quick")
    
    print(f"\n当前配置: VERIFICATION_MODE = {env_mode}")
    
    modes = {
        "extreme": {
            "desc": "极速模式 (跳过所有验证)",
            "per_expert": 0,
            "remarks": "质量最低，速度最快"
        },
        "quick": {
            "desc": "快速模式 (智能选择)",
            "per_expert": 0.5,
            "remarks": "只对有事实的内容验证"
        },
        "quality": {
            "desc": "质量模式 (强制所有检查)",
            "per_expert": 2.0,
            "remarks": "每个专家触发验证+反思"
        },
    }
    
    for mode, info in modes.items():
        marker = "✅ 当前" if mode == env_mode else "  "
        print(f"\n{marker} {info['desc']}")
        print(f"   - 每专家额外调用: {info['per_expert']} 次")
        print(f"   - 说明: {info['remarks']}")
        
        # 耗时估计
        if info['per_expert'] > 0:
            extra_time = 6 * info['per_expert'] * 12  # 6个专家 × per_expert × 12秒/LLM调用
            print(f"   - 预计额外耗时 (STANDARD): +{extra_time:.0f}秒")


def diagnose_tools():
    """检测工具执行情况"""
    print("\n" + "="*70)
    print("【诊断 4】工具执行效率")
    print("="*70)
    
    try:
        from app.services.expert_tools import tool_executor
        
        # 检查缓存
        cache_info = tool_executor._cache if hasattr(tool_executor, '_cache') else None
        
        print(f"\n工具执行器:")
        if cache_info:
            print(f"  - 缓存状态: {len(cache_info)} 条记录")
        else:
            print(f"  - 缓存: 无")
        
        # 建议
        print(f"\n⚠️  诊断建议:")
        print(f"  - 当前工具调用可能为 串联执行")
        print(f"  - 建议: 实施工具并行化 (可减少 15-20% 耗时)")
        
    except Exception as e:
        print(f"  ⚠️  无法检测工具: {e}")


def generate_recommendations(interval_s):
    """生成优化建议"""
    print("\n" + "="*70)
    print("【优化建议】按优先级排列")
    print("="*70)
    
    recommendations = [
        {
            "priority": "🔴 高",
            "action": "降低 LLM_RATE_LIMIT_INTERVAL",
            "from": "3.0s",
            "to": "1.5s",
            "impact": "-30% 耗时",
            "risk": "可能增加 503 错误 (需添加自适应退避)",
            "file": ".env / .env.runtime"
        },
        {
            "priority": "🔴 高",
            "action": "启用快速验证模式",
            "from": "quick",
            "to": "extreme (仅测试) 或 quick (保持)",
            "impact": "-20-30% 耗时",
            "risk": "质量可能下降 (只建议QUICK拓扑)",
            "file": "环境变量或 config"
        },
        {
            "priority": "⚠️  中",
            "action": "工具并行执行",
            "from": "串联",
            "to": "并行 (相同轮次)",
            "impact": "-15% 耗时",
            "risk": "需要重构工具执行器",
            "file": "expert_tools.py"
        },
        {
            "priority": "⚠️  中",
            "action": "批量验证/反思",
            "from": "单个调用",
            "to": "一次性处理多个专家",
            "impact": "-20% 耗时",
            "risk": "需要改造验证逻辑",
            "file": "discussion_service.py"
        },
        {
            "priority": "⚠️  中",
            "action": "搜索后台化",
            "from": "阻塞等待",
            "to": "异步任务",
            "impact": "-10-15% 耗时",
            "risk": "较低",
            "file": "discussion_service.py"
        },
        {
            "priority": "🟡 低",
            "action": "前端更新频率",
            "from": "0.5s 节流",
            "to": "100ms 节流",
            "impact": "主观快 30% (实际不变)",
            "risk": "无",
            "file": "llm_gateway.py"
        }
    ]
    
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. 【{rec['priority']}】{rec['action']}")
        print(f"   ├─ 改动: {rec['from']} → {rec['to']}")
        print(f"   ├─ 效果: {rec['impact']}")
        print(f"   ├─ 风险: {rec['risk']}")
        print(f"   └─ 文件: {rec['file']}")


def quick_test_command():
    """生成快速测试命令"""
    print("\n" + "="*70)
    print("【快速测试】执行以下命令验证改善")
    print("="*70)
    
    print(f"""
# 1. 记录基线 (当前配置)
BASELINE_JOB=$(curl -s -X POST http://localhost:8000/api/analysis/jobs \\
  -H "Content-Type: application/json" \\
  -d '{{"symbol": "AAPL", "market": "us", "analysis_level": "quick"}}' | jq -r '.job_id')

echo "Job ID: $BASELINE_JOB"
time curl -s http://localhost:8000/api/analysis/jobs/$BASELINE_JOB | jq '.progress'

# 2. 修改环境变量 (需要重启服务)
# 编辑 .env: LLM_RATE_LIMIT_INTERVAL=1.5

# 3. 重新测试 (记录耗时对比)
OPTIMIZED_JOB=$(curl -s -X POST http://localhost:8000/api/analysis/jobs \\
  -H "Content-Type: application/json" \\
  -d '{{"symbol": "AAPL", "market": "us", "analysis_level": "quick"}}' | jq -r '.job_id')

echo "Optimized Job ID: $OPTIMIZED_JOB"
time curl -s http://localhost:8000/api/analysis/jobs/$OPTIMIZED_JOB | jq '.progress'

# 4. 对比结果
# 预期: 基线 ~90-120s → 优化后 ~60-85s
    """)


def main():
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " ALSA 性能诊断报告 ".center(68) + "║")
    print("║" + " 分析 AI 耗时、流式输出、请求间隔等问题 ".center(68) + "║")
    print("╚" + "="*68 + "╝")
    
    # 执行诊断
    interval_s = diagnose_rate_limit()
    diagnose_topology()
    diagnose_verification()
    diagnose_tools()
    
    # 生成建议
    generate_recommendations(interval_s)
    
    # 快速测试
    quick_test_command()
    
    print("\n" + "="*70)
    print("【诊断完成】")
    print("="*70)
    print(f"""
📄 详细报告: PERFORMANCE_OPTIMIZATION_GUIDE.md
📋 改动建议: 见上文【优化建议】
🚀 快速改善: 调整 LLM_RATE_LIMIT_INTERVAL 至 1.5s (需重启服务)

⏱️  预期效果:
  - 快速改善 (环境变量): -30% 耗时 (~90s → ~60s)
  - 完整优化 (代码重构): -50-60% 耗时 (~90s → ~40-45s)

🔗 相关文件:
  - python_service/app/services/llm_gateway.py
  - python_service/app/services/agent_orchestrator.py
  - python_service/app/services/discussion_service.py
  - python_service/app/services/expert_tools.py
    """)


if __name__ == "__main__":
    main()
