import os
import pytest
from jinja2 import Environment, FileSystemLoader

@pytest.fixture
def jinja_env():
    prompts_dir = os.path.join(os.path.dirname(__file__), "..", "app", "prompts")
    return Environment(loader=FileSystemLoader(prompts_dir))

@pytest.fixture
def base_context():
    return {
        "role": "Fundamental Analyst",
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "template": "Analyze the fundamentals.",
        "is_zh": False,
        "is_final_round": False,
        "is_sector_intermediate": False,
        "is_markdown_intermediate": True,
        "macro_data": None,
        "commodity_data": None,
        "macro_indicators": None,
        "macro_regime_text": "",
        "peer_data": None,
        "sentiment_data": None,
        "brain_ctx": {},
        "history": {},
        "market": "us",
        "has_search_tools": True,
        "use_native_tools": False,
        "enrichment_text": "",
        "tool_descriptions": "Tool: web_search",
        "current_date": "2026-06-15",
        
        # Formatted facts
        "long_name": "Apple Inc.",
        "full_code": "AAPL",
        "exchange_display": "NASDAQ",
        "industry": "Consumer Electronics",
        "sector": "Technology",
        "listing_date": "1980-12-12",
        "biz_summary": "Designs smartphones.",
        "cross_listing": None,
        "sector_stocks": [],
        "get_val": lambda *args, **kwargs: "N/A",
        "listing_currency": "USD",
        "fin_currency": "USD",
        "currency_warning": False,
        "currency_note": "",
        "indicators_json": "",
        "quarterly_history": [],
        "fmt_num": lambda x: str(x),
        "valuation_guidance": "",
    }

def test_base_prompt_render_english(jinja_env, base_context):
    template = jinja_env.get_template("base_prompt.jinja")
    rendered = template.render(**base_context)
    
    assert "Role: Fundamental Analyst" in rendered
    assert "Analyze the fundamentals." in rendered
    assert "You are an institutional-grade AI analyst" in rendered
    assert "Professional Markdown Output" in rendered
    assert "Respond in English" in rendered
    assert "Apple Inc." in rendered

def test_base_prompt_render_chinese(jinja_env, base_context):
    base_context["is_zh"] = True
    template = jinja_env.get_template("base_prompt.jinja")
    rendered = template.render(**base_context)
    
    assert "⚠️ LANGUAGE MANDATE:" in rendered
    assert "专业Markdown输出" in rendered
    assert "Respond in Simplified Chinese" in rendered

def test_macro_data_rendering(jinja_env, base_context):
    base_context["macro_data"] = {
        "USD/CNY": 7.2,
        "Source": "CFETS",
        "Date": "2026-06-15"
    }
    template = jinja_env.get_template("base_prompt.jinja")
    rendered = template.render(**base_context)
    
    assert "实时汇率 USD/CNY: 7.2" in rendered

def test_final_round_output_rules(jinja_env, base_context):
    base_context["role"] = "Chief Strategist"
    base_context["is_final_round"] = True
    base_context["is_markdown_intermediate"] = False
    
    template = jinja_env.get_template("base_prompt.jinja")
    rendered = template.render(**base_context)
    
    assert "Structured Data Footer (CRITICAL)" in rendered or "结构化数据尾注 (CRITICAL)" in rendered
