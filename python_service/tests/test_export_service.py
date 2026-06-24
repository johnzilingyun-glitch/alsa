"""Tests for ExportService — share card HTML generation."""
import pytest
from python_service.app.services.export_service import ExportService, export_service


class TestBuildShareCardHTML:
    """Test share card HTML template generation."""

    def test_basic_card(self):
        svc = ExportService()
        html = svc.build_share_card_html(title="贵州茅台")
        assert "贵州茅台" in html
        assert "<!DOCTYPE html>" in html
        assert "ALSA" in html

    def test_bullish_verdict_color(self):
        svc = ExportService()
        html = svc.build_share_card_html(title="AAPL", verdict="buy")
        assert "看多" in html
        assert "#16a34a" in html  # Green color

    def test_bearish_verdict_color(self):
        svc = ExportService()
        html = svc.build_share_card_html(title="AAPL", verdict="sell")
        assert "看空" in html
        assert "#dc2626" in html  # Red color

    def test_neutral_verdict(self):
        svc = ExportService()
        html = svc.build_share_card_html(title="AAPL", verdict="hold")
        assert "hold" in html or "中性" in html

    def test_with_price_and_change(self):
        svc = ExportService()
        html = svc.build_share_card_html(
            title="贵州茅台",
            price="1850.00",
            change_pct="+2.5%",
        )
        assert "1850.00" in html
        assert "+2.5%" in html

    def test_negative_change_color(self):
        svc = ExportService()
        html = svc.build_share_card_html(
            title="TEST",
            price="100",
            change_pct="-3.2%",
        )
        assert "#dc2626" in html  # Red for negative change

    def test_score_bar_rendered(self):
        svc = ExportService()
        html = svc.build_share_card_html(title="TEST", score=85)
        assert "85" in html
        assert "width:85%" in html

    def test_low_score_red_color(self):
        svc = ExportService()
        html = svc.build_share_card_html(title="TEST", score=20)
        assert "#dc2626" in html  # Red for score < 40

    def test_medium_score_orange_color(self):
        svc = ExportService()
        html = svc.build_share_card_html(title="TEST", score=55)
        assert "#d97706" in html  # Orange for 40 <= score < 70

    def test_highlights_rendered(self):
        svc = ExportService()
        html = svc.build_share_card_html(
            title="TEST",
            highlights=["营收增长15%", "ROE连续三年提升", "护城河强"],
        )
        assert "营收增长15%" in html
        assert "ROE连续三年提升" in html
        assert "<li" in html

    def test_highlights_capped_at_5(self):
        svc = ExportService()
        html = svc.build_share_card_html(
            title="TEST",
            highlights=[f"Point {i}" for i in range(10)],
        )
        # Only first 5 should be rendered
        assert "Point 0" in html
        assert "Point 4" in html
        assert "Point 5" not in html

    def test_sector_report_type(self):
        svc = ExportService()
        html = svc.build_share_card_html(title="消费行业", report_type="sector")
        assert "板块分析" in html

    def test_stock_report_type(self):
        svc = ExportService()
        html = svc.build_share_card_html(title="AAPL", report_type="stock")
        assert "个股深度研报" in html

    def test_no_price_element_when_none(self):
        svc = ExportService()
        html = svc.build_share_card_html(title="TEST")
        # The CSS class 'price-row' exists in the stylesheet, but
        # the actual div element should not be rendered when no price is given
        assert '<div class="price-row">' not in html


class TestSingleton:
    def test_singleton_exists(self):
        assert export_service is not None
        assert isinstance(export_service, ExportService)
