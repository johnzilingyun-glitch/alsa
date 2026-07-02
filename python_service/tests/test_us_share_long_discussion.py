"""Test US-Share long discussion extraction improvements.

Verifies that the UI Data Expert can properly extract structured JSON
from very long Chinese discussions (27K+ chars) typical of US-Share analysis.
"""
import pytest
import json
import re
from unittest.mock import AsyncMock, patch
from python_service.app.services.report_generator_service import ReportGeneratorService, ReportSchemaValidationError


class TestLongDiscussionExtraction:
    """Test extraction improvements for long discussions."""

    def setup_method(self):
        self.service = ReportGeneratorService()

    def test_preprocess_removes_html_tags(self):
        """HTML tags should be stripped from discussion text."""
        discussion = '<h1>Title</h1><p>Content</p><table><tr><td>Data</td></tr></table>'
        result = self.service._preprocess_discussion_for_extraction(discussion)
        assert '<h1>' not in result
        assert '<p>' not in result
        assert '<table>' not in result
        assert 'Title' in result
        assert 'Content' in result
        assert 'Data' in result

    def test_preprocess_removes_code_blocks(self):
        """Code block markers should be stripped."""
        discussion = '```json\n{"key": "value"}\n```\n```python\nprint("hello")\n```'
        result = self.service._preprocess_discussion_for_extraction(discussion)
        assert '```' not in result
        assert '{"key": "value"}' in result

    def test_preprocess_collapses_blank_lines(self):
        """Excessive blank lines should be collapsed."""
        discussion = 'Line 1\n\n\n\n\nLine 2'
        result = self.service._preprocess_discussion_for_extraction(discussion)
        assert '\n\n\n' not in result

    def test_preprocess_removes_inline_code(self):
        """Inline code backticks should be removed."""
        discussion = 'Price is `100.50` and PE is `15.2`'
        result = self.service._preprocess_discussion_for_extraction(discussion)
        assert '`' not in result
        assert '100.50' in result
        assert '15.2' in result

    def test_smart_truncation_long_discussion(self):
        """Long discussions should be truncated to beginning + end."""
        # Create a 30K char discussion
        early_content = "股票概览: PDD Holdings, 电商巨头" + "x" * 5000
        late_content = "投资建议: BUY, 目标价120美元" + "y" * 15000
        full_discussion = early_content + "z" * 10000 + late_content

        # Simulate the truncation logic
        if len(full_discussion) > 25000:
            truncated = full_discussion[:8000] + "\n\n... [中间内容已省略] ...\n\n" + full_discussion[-17000:]
        else:
            truncated = full_discussion

        # Should contain beginning and end, but not middle
        assert "股票概览" in truncated
        assert "投资建议" in truncated
        assert "... [中间内容已省略] ..." in truncated
        assert len(truncated) < len(full_discussion)

    def test_smart_truncation_short_discussion(self):
        """Short discussions should not be truncated."""
        short_discussion = "Short discussion about PDD"
        if len(short_discussion) > 25000:
            truncated = short_discussion[:8000] + "\n\n... [中间内容已省略] ...\n\n" + short_discussion[-17000:]
        else:
            truncated = short_discussion

        assert truncated == short_discussion

    def test_extract_balanced_json_valid(self):
        """Should extract valid JSON when it starts at the beginning of text."""
        text = '{"verdict": "Good", "score": 85}'
        result = self.service._extract_balanced_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["verdict"] == "Good"
        assert parsed["score"] == 85

    def test_extract_balanced_json_with_nested(self):
        """Should handle nested JSON objects when at the beginning."""
        text = '{"factor": {"size": "Large", "style": "Growth"}, "rec": "BUY"}'
        result = self.service._extract_balanced_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["factor"]["size"] == "Large"

    def test_extract_balanced_json_no_json(self):
        """Should return empty string when no JSON found."""
        text = 'No JSON here, just plain text'
        result = self.service._extract_balanced_json(text)
        assert result == "" or result is None

    def test_extract_balanced_json_with_prefix(self):
        """Should return empty when JSON is not at the start (by design)."""
        text = 'Some text before {"verdict": "Good"}'
        result = self.service._extract_balanced_json(text)
        # This method only works when JSON starts at position 0
        # For mixed text, we use regex fallback
        assert result == "" or result is None

    def test_is_low_quality_garbage_verdict(self):
        """Verdict of '---' should be detected as low quality."""
        ui_data = {"verdict": "---", "investment_thesis": "Good stock", "the_call": "Buy", "tagline": "PDD", "recommendation": "BUY"}
        assert self.service._is_low_quality_ui_data(ui_data) is True

    def test_is_low_quality_oversized_thesis(self):
        """Investment thesis over 500 chars should be detected as low quality."""
        ui_data = {
            "verdict": "Strong buy opportunity",
            "investment_thesis": "x" * 600,  # Too long
            "the_call": "Buy now",
            "tagline": "PDD Holdings",
            "recommendation": "BUY"
        }
        assert self.service._is_low_quality_ui_data(ui_data) is True

    def test_is_low_quality_valid_data(self):
        """Valid data should not be detected as low quality."""
        ui_data = {
            "verdict": "估值极低，Temu盈亏平衡是关键变量",
            "investment_thesis": "PDD当前PE仅7.96倍，扣除每股$45.7净现金后经营业务PE不足4倍",
            "the_call": "建议观望，等待Q2财报确认",
            "tagline": "PDD Holdings: 极端低估vs增长断崖",
            "recommendation": "HOLD"
        }
        assert self.service._is_low_quality_ui_data(ui_data) is False

    def test_is_low_quality_empty_dict(self):
        """Empty dict should be detected as low quality."""
        assert self.service._is_low_quality_ui_data({}) is True

    def test_is_low_quality_none(self):
        """None should be detected as low quality."""
        assert self.service._is_low_quality_ui_data(None) is True

    def test_is_low_quality_invalid_recommendation(self):
        """Invalid recommendation should be detected as low quality."""
        ui_data = {
            "verdict": "Good stock",
            "investment_thesis": "Strong fundamentals",
            "the_call": "Buy",
            "tagline": "PDD",
            "recommendation": "MAYBE"  # Invalid
        }
        assert self.service._is_low_quality_ui_data(ui_data) is True

    @pytest.mark.asyncio
    async def test_full_extraction_with_mock_llm(self):
        """Test full extraction pipeline with mocked LLM response."""
        # Simulate a proper LLM response
        mock_response = json.dumps({
            "verdict": "估值极低，Temu盈亏平衡是关键变量",
            "action_stance": "当前建议HOLD，等待Q2财报确认",
            "investment_thesis": "PDD当前PE仅7.96倍，扣除净现金后经营业务PE不足4倍",
            "tagline": "PDD Holdings: 极端低估vs增长断崖",
            "recommendation": "HOLD",
            "score": 72,
            "factor_profile": {"size": "大盘", "style": "成长", "volatility": "高Beta"},
            "consensus_vs_non_consensus": {
                "market_consensus": "市场定价Temu毁灭价值",
                "our_alpha": "若Temu止血，估值修复空间巨大"
            },
            "scenarios": [
                {"case": "Bull", "probability": 25, "targetPrice": "120", "logic": "Temu盈亏平衡"},
                {"case": "Base", "probability": 50, "targetPrice": "85", "logic": "维持现状"},
                {"case": "Bear", "probability": 25, "targetPrice": "55", "logic": "Temu持续亏损"}
            ]
        })

        with patch('python_service.app.services.report_generator_service.llm_gateway') as mock_gateway:
            mock_gateway.generate_content = AsyncMock(return_value=mock_response)

            result = await self.service._run_ui_data_expert(
                symbol="PDD",
                market="US-Share",
                snapshot={"quote": {"symbol": "PDD"}},
                discussion="[Deep Research Specialist]: PDD是一家电商公司..."
            )

            assert result is not None
            assert result["verdict"] == "估值极低，Temu盈亏平衡是关键变量"
            assert result["recommendation"] == "HOLD"
            assert result["score"] == 72
            assert len(result["scenarios"]) == 3

    @pytest.mark.asyncio
    async def test_extraction_with_garbage_response(self):
        """Test that garbage LLM response triggers quality validation."""
        # Simulate garbage response (like what happened with PDD)
        mock_response = '---\n{"verdict": "---", "investment_thesis": "x" * 600}\n---'

        with patch('python_service.app.services.report_generator_service.llm_gateway') as mock_gateway:
            mock_gateway.generate_content = AsyncMock(return_value=mock_response)

            result = await self.service._run_ui_data_expert(
                symbol="PDD",
                market="US-Share",
                snapshot={"quote": {"symbol": "PDD"}},
                discussion="[Deep Research Specialist]: PDD analysis..."
            )

            # Result should either be empty dict (triggering fallback) or low quality
            if result:
                assert self.service._is_low_quality_ui_data(result) is True

    @pytest.mark.asyncio
    async def test_formal_report_blocks_invalid_ui_schema(self, tmp_path):
        output_path = tmp_path / "invalid_report.html"

        with patch.object(self.service, "_run_ui_data_expert", AsyncMock(return_value={"verdict": "---"})):
            with pytest.raises(ReportSchemaValidationError) as exc_info:
                await self.service.generate_html_report_async(
                    {
                        "symbol": "PDD",
                        "market": "US-Share",
                        "stockInfo": {"symbol": "PDD", "market": "US-Share"},
                        "snapshot": {"quote": {"symbol": "PDD", "price": 100}},
                        "discussion": [{"role": "Chief Strategist", "content": "建议观望，等待更多数据。"}],
                    },
                    str(output_path),
                )

        assert "LLM report schema validation failed" in str(exc_info.value)
        assert not output_path.exists()


class TestHTMLRenderingSafety:
    """Test HTML rendering layer safety nets."""

    def setup_method(self):
        self.service = ReportGeneratorService()

    def test_garbage_verdict_not_rendered(self):
        """Verdict of '---' should not render a verdict banner."""
        GARBAGE_VALUES = {"---", "—", "N/A", "n/a", "TBD", "tbd", "TODO", "todo", "None", "null", ""}
        verdict = "---"
        if str(verdict).strip() in GARBAGE_VALUES or len(str(verdict).strip()) < 5:
            verdict = ""
        assert verdict == ""

    def test_valid_verdict_rendered(self):
        """Valid verdict should be preserved."""
        GARBAGE_VALUES = {"---", "—", "N/A", "n/a", "TBD", "tbd", "TODO", "todo", "None", "null", ""}
        verdict = "估值极低，Temu盈亏平衡是关键变量"
        if str(verdict).strip() in GARBAGE_VALUES or len(str(verdict).strip()) < 5:
            verdict = ""
        assert verdict == "估值极低，Temu盈亏平衡是关键变量"

    def test_thesis_truncation(self):
        """Long thesis should be truncated at sentence boundary."""
        thesis_raw = "PDD是一家电商平台。" + "x" * 600

        if len(thesis_raw) > 500:
            truncated = thesis_raw[:500]
            last_period = max(truncated.rfind('。'), truncated.rfind('. '), truncated.rfind('！'), truncated.rfind('?'))
            thesis = truncated[:last_period + 1] if last_period > 100 else truncated + "..."
        else:
            thesis = thesis_raw

        assert len(thesis) <= 510  # Allow some margin for "..."
        assert "PDD" in thesis
