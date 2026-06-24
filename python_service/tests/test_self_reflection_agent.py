"""Tests for SelfReflectionAgent — analysis self-reflection and response parsing."""
import pytest
from python_service.app.services.self_reflection_agent import SelfReflectionAgent


class TestBuildHistorySummary:
    """Test history summary construction."""

    def test_empty_context(self):
        agent = SelfReflectionAgent()
        assert agent._build_history_summary({}) == "（无历史分析）"
        assert agent._build_history_summary(None) == "（无历史分析）"

    def test_dict_context_with_content(self):
        agent = SelfReflectionAgent()
        context = {
            "技术分析师": {"content": "MACD金叉，RSI在60附近，趋势偏多"},
            "基本面分析师": {"content": "PE 25倍，ROE 18%，基本面优秀"},
        }
        summary = agent._build_history_summary(context)
        assert "技术分析师" in summary
        assert "基本面分析师" in summary
        assert "MACD" in summary

    def test_string_context(self):
        agent = SelfReflectionAgent()
        context = {
            "分析师A": "简短分析内容",
        }
        summary = agent._build_history_summary(context)
        assert "分析师A" in summary
        assert "简短分析内容" in summary

    def test_long_content_truncated(self):
        agent = SelfReflectionAgent()
        long_content = "x" * 500
        context = {"分析师": {"content": long_content}}
        summary = agent._build_history_summary(context)
        assert "..." in summary
        assert len(summary) < 500


class TestParseResponse:
    """Test LLM response parsing."""

    def test_parse_json_code_block(self):
        agent = SelfReflectionAgent()
        response = """这是一些分析文字。

```json
{
    "logic_gaps": ["数据缺失"],
    "missing_info": ["财报未发布"],
    "cognitive_biases": ["确认偏见"],
    "confidence_score": 0.8,
    "improved_analysis": "改进后的分析"
}
```

额外的文字"""
        parsed = agent._parse_response(response)
        assert parsed["confidence_score"] == 0.8
        assert "数据缺失" in parsed["logic_gaps"]
        assert parsed["improved_analysis"] == "改进后的分析"

    def test_parse_raw_json(self):
        agent = SelfReflectionAgent()
        import json
        response = json.dumps({
            "logic_gaps": [],
            "missing_info": [],
            "cognitive_biases": [],
            "confidence_score": 0.9,
            "improved_analysis": "分析总结"
        })
        parsed = agent._parse_response(response)
        assert parsed["confidence_score"] == 0.9

    def test_parse_fallback_plain_text(self):
        agent = SelfReflectionAgent()
        response = "这是一段纯文本分析，没有JSON格式。\n- 偏见: 确认偏见\n- 缺失: 关键数据"
        parsed = agent._parse_response(response)
        assert "confidence_score" in parsed
        assert "improved_analysis" in parsed
        assert len(parsed["improved_analysis"]) > 0


class TestExtractList:
    """Test list extraction from text."""

    def test_extract_items(self):
        agent = SelfReflectionAgent()
        text = """分析结果：
逻辑漏洞：
- 数据矛盾
- 推理跳跃
其他内容"""
        items = agent._extract_list(text, "逻辑漏洞")
        assert len(items) == 2
        assert "数据矛盾" in items
        assert "推理跳跃" in items

    def test_extract_with_bullets(self):
        agent = SelfReflectionAgent()
        text = """缺失信息：
• 最新财报数据
• 行业对比数据
结论"""
        items = agent._extract_list(text, "缺失")
        assert len(items) == 2

    def test_no_matching_keyword(self):
        agent = SelfReflectionAgent()
        text = "没有相关内容"
        items = agent._extract_list(text, "偏见")
        assert items == []

    def test_extract_with_asterisk(self):
        agent = SelfReflectionAgent()
        text = """偏见检测：
* 锚定效应
* 过度自信"""
        items = agent._extract_list(text, "偏见")
        assert len(items) == 2
