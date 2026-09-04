"""
Critic Agent: 独立校验层，交叉验证各专家观点，识别分歧和风险
"""
import json
from typing import Dict, Any, List, Optional
from .llm_gateway import llm_gateway


class CriticAgent:
    """独立审查员，交叉验证专家分析，识别分歧"""
    
    async def critique(
        self,
        analyses: List[Dict[str, Any]],
        symbol: str,
        name: str = "",
        context: Optional[Dict[str, Any]] = None,
        gemini_api_key: Optional[str] = None,
        deepseek_api_key: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        独立审查所有专家分析
        
        Args:
            analyses: 各专家的分析结果列表
            symbol: 股票代码
            name: 股票名称
            context: 额外上下文（如市场数据）
            
        Returns:
            审查报告，包含分歧点、风险偏见、综合评分
        """
        # 构建分析摘要
        analyses_summary = self._build_analyses_summary(analyses)
        
        # 构建市场数据摘要
        market_summary = self._build_market_summary(context) if context else "（无市场数据）"
        
        prompt = f"""你是一位独立的高级投资审查员（Critic Agent）。你的职责是交叉验证多位专家的分析，识别分歧和潜在风险。

## 分析对象
- 股票代码: {symbol}
- 股票名称: {name}

## 市场数据摘要
{market_summary}

## 各专家分析
{analyses_summary}

## 审查要求

请从以下维度进行独立审查，输出JSON格式：

```json
{{
    "consensus_points": ["专家们达成共识的观点"],
    "major_disagreements": [
        {{
            "topic": "分歧主题",
            "positions": {{"expert_a": "观点A", "expert_b": "观点B"}},
            "severity": "high/medium/low",
            "potential_impact": "分歧对投资决策的影响"
        }}
    ],
    "data_conflicts": ["不同专家引用的数据矛盾"],
    "bias_assessment": {{
        "overall_bias": "bullish/bearish/neutral",
        "bias_magnitude": "strong/moderate/mild",
        "evidence": "判断依据"
    }},
    "risk_flags": ["需要特别关注的风险点"],
    "missing_perspectives": ["缺失的重要分析视角"],
    "overall_score": 0-100,
    "confidence_level": "high/medium/low",
    "recommendation": "综合投资建议（1-2句话）"
}}
```

审查原则：
1. 保持独立客观，不偏向任何一方
2. 重点关注分歧>20%的议题
3. 识别系统性偏见（如集体过度乐观/悲观）
4. 评估分析的完整性（是否有重要视角被忽略）"""

        try:
            # max_tokens 已移除：LLMGateway.generate_content 的签名不支持该参数
            # （旧代码传入了它，每次调用都抛 TypeError
            # "got an unexpected keyword argument 'max_tokens'"，被外层 except
            # 吞掉后 critique 永远走降级分支）；输出长度由网关统一的
            # _apply_max_tokens 策略控制。
            response = await llm_gateway.generate_content(
                prompt=prompt,
                model=model,
                temperature=0.2,  # 低温度确保客观性
                gemini_api_key=gemini_api_key,
                deepseek_api_key=deepseek_api_key,
                openrouter_api_key=openrouter_api_key
            )
            
            parsed = self._parse_response(response)
            
            return {
                "symbol": symbol,
                "name": name,
                "critique": parsed,
                "expert_count": len(analyses),
                "timestamp": self._get_timestamp()
            }
            
        except Exception as e:
            return {
                "symbol": symbol,
                "name": name,
                "critique": {
                    "error": str(e),
                    "overall_score": 50,
                    "confidence_level": "low",
                    "recommendation": "审查失败，建议人工复核"
                },
                "expert_count": len(analyses),
                "timestamp": self._get_timestamp()
            }
    
    def _build_analyses_summary(self, analyses: List[Dict[str, Any]]) -> str:
        """构建各专家分析摘要"""
        summaries = []
        for i, analysis in enumerate(analyses, 1):
            role = analysis.get("role", f"Expert {i}")
            content = analysis.get("content", "")
            # 截取前800字 (increased from 300 to preserve more context for critic review)
            summary = content[:800] + "..." if len(content) > 800 else content
            summaries.append(f"### {role}\n{summary}")
        
        return "\n\n".join(summaries) if summaries else "（无分析数据）"
    
    def _build_market_summary(self, context: Dict[str, Any]) -> str:
        """构建市场数据摘要"""
        fields = []
        key_fields = ["price", "pe", "pb", "market_cap", "change_pct", "volume"]
        for key in key_fields:
            if key in context:
                fields.append(f"- {key}: {context[key]}")
        return "\n".join(fields) if fields else "（无关键市场数据）"
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析LLM响应"""
        import re
        
        # 尝试提取JSON块
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 尝试直接解析
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # 降级处理
        return {
            "overall_score": 50,
            "confidence_level": "low",
            "recommendation": response[:500],
            "consensus_points": [],
            "major_disagreements": [],
            "risk_flags": []
        }
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()


# 单例
critic_agent = CriticAgent()
