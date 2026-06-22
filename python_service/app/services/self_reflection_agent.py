"""
Self-Reflection Agent: 对专家分析进行自我反思，识别逻辑漏洞和偏见
"""
import json
from typing import Dict, Any, Optional
from .llm_gateway import llm_gateway


class SelfReflectionAgent:
    """自我反思代理，在每轮专家分析后进行反思和改进"""
    
    async def reflect(
        self, 
        expert_role: str, 
        analysis: str, 
        context: Dict[str, Any],
        round_num: int = 1,
        total_rounds: int = 10,
        gemini_api_key: Optional[str] = None,
        deepseek_api_key: Optional[str] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        对上一轮分析进行自我反思
        
        Args:
            expert_role: 专家角色名称
            analysis: 原始分析内容
            context: 上下文信息（包含其他专家的历史分析）
            round_num: 当前轮次
            total_rounds: 总轮次
            
        Returns:
            包含改进分析和反思点的字典
        """
        # 构建历史上下文摘要
        history_summary = self._build_history_summary(context)
        
        prompt = f"""你是一位资深的投资研究质量控制专家。请对{expert_role}的分析进行自我反思。

## 当前分析（Round {round_num}/{total_rounds}）

{analysis}

## 历史分析摘要

{history_summary}

## 反思要求

请从以下维度进行反思，输出JSON格式：

```json
{{
    "logic_gaps": ["识别出的逻辑漏洞或不一致"],
    "missing_info": ["缺失的关键信息"],
    "cognitive_biases": ["潜在的认知偏见（如确认偏见、锚定效应等）"],
    "unverified_assumptions": ["需要验证的假设"],
    "data_contradictions": ["与其他专家分析的数据矛盾"],
    "confidence_score": 0.0-1.0,
    "improved_analysis": "改进后的分析摘要（200字以内）"
}}
```

注意：
1. 只识别确实存在的问题，不要强行挑刺
2. confidence_score反映分析的整体可信度
3. improved_analysis应保留原分析的核心观点，修正明显问题"""

        try:
            response = await llm_gateway.generate_content(
                prompt=prompt,
                model=model,
                temperature=0.3,
                max_tokens=1500,
                gemini_api_key=gemini_api_key,
                deepseek_api_key=deepseek_api_key
            )
            
            # 尝试解析JSON响应
            parsed = self._parse_response(response)
            
            return {
                "expert_role": expert_role,
                "round_num": round_num,
                "reflection": parsed,
                "original_analysis": analysis[:500] + "..." if len(analysis) > 500 else analysis
            }
            
        except Exception as e:
            # 反思失败不应阻断主流程
            return {
                "expert_role": expert_role,
                "round_num": round_num,
                "reflection": {
                    "error": str(e),
                    "confidence_score": 0.5,
                    "improved_analysis": analysis[:300]
                },
                "original_analysis": analysis[:300]
            }
    
    def _build_history_summary(self, context: Dict[str, Any]) -> str:
        """构建历史分析摘要"""
        if not context:
            return "（无历史分析）"
        
        summaries = []
        for role, data in context.items():
            if isinstance(data, dict) and "content" in data:
                # 截取前200字作为摘要
                summary = data["content"][:200] + "..." if len(data["content"]) > 200 else data["content"]
                summaries.append(f"- **{role}**: {summary}")
            elif isinstance(data, str):
                summary = data[:200] + "..." if len(data) > 200 else data
                summaries.append(f"- **{role}**: {summary}")
        
        return "\n".join(summaries) if summaries else "（无历史分析）"
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析LLM响应为JSON"""
        import re
        
        # 尝试提取JSON块
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 尝试直接解析整个响应
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # 提取关键字段
        result = {
            "logic_gaps": self._extract_list(response, "逻辑漏洞"),
            "missing_info": self._extract_list(response, "缺失"),
            "cognitive_biases": self._extract_list(response, "偏见"),
            "confidence_score": 0.7,
            "improved_analysis": response[:500]
        }
        return result
    
    def _extract_list(self, text: str, keyword: str) -> list:
        """从文本中提取列表项"""
        items = []
        lines = text.split('\n')
        capture = False
        for line in lines:
            if keyword in line:
                capture = True
                continue
            if capture and line.strip().startswith(('-', '*', '•')):
                items.append(line.strip().lstrip('-*• ').strip())
            elif capture and line.strip() and not line.strip().startswith(('-', '*', '•')):
                if items:  # 已经收集到项目，遇到非列表行则停止
                    break
        return items


# 单例
self_reflection_agent = SelfReflectionAgent()
