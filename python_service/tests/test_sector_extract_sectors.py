"""Regression tests for _extract_sectors in app/api/sector.py.

Bug history (2026-09-05):
  Old code used `^\\s*\\d+\\.\\s*(?:\\*\\*)?([^:\\*\\n]+)(?:\\*\\*)?[:：]' to parse
  fallback numbered lists. When the LLM emitted an all-UNKNOWN report
  (web_search tools returning empty in current prod network), the
  numbered-list fallback matched the section titles "数据源验证",
  "替代数据源", "历史参考", "风险提示" as sector names. Frontend rendered
  them as clickable "sectors" — user saw "completely no data".

  Fix: add _KNOWN_FAKE_SECTORS blacklist, _SECTION_PREFIXES stopwords
  (fallback-only), per-table column-hint gating, markdown emphasis stripping,
  and UNKNOWN-count early-stop.

Bug history (2026-09-05 v2):
  English-header table path (allow_english=True for Gemini fallback) had no
  English-shape validation — "random words here" / "abc" passed through as
  sector names. Added: must have ≥1 uppercase letter (TitleCase/CamelCase
  required), ≥3 chars (reject "AI"/"IT"), word-count ≤4, must contain at
  least one alphabetic char. Legit names like "Semiconductors" / "Robotics"
  / "Artificial Intelligence" still pass.

Bug history (2026-09-05 v3):
  v2 added `_SECTION_PREFIXES` reuse on the English path as protection against
    "Risk Warning" / "Data Verification" — but `_SECTION_PREFIXES` is 100%
    Chinese, so `startswith` on English names always returns False (dead code).
  Independent reviewer flagged this as residual risk. Fix: new
    `_EN_SECTION_TITLES` frozenset with exact-match English section phrases
    ("Risk Warning", "Executive Summary", "Methodology", ...). Exact-match
    (not startswith) so legit "Risk Parity" / "Risk Management" still pass.

Bug history (2026-09-05 v4):
  v3 still had residual gaps: case-sensitivity ("Risk warning" mixed-case
    passed) and plural variants ("Risk Warnings" / "Data Sources" not covered).
    - Move `_EN_SECTION_TITLES` from inner function to module level
    - Add 4 plural variants: "Risk Warnings" / "Risk Disclosures" /
      "Data Sources" / "Methodologies"
    - Build module-level `_en_section_titles_lower = {t.lower() ...}`
    - Compare with `name.lower() in _en_section_titles_lower` (one-liner
      case-insensitivity, O(1) frozenset lookup, no rebuild per call)
"""
import pytest

from app.api.sector import _extract_sectors


# ---------- 主表解析（3 种格式）----------

def test_main_table_no_rank():
    """LLM 直接写 | 板块 | 涨跌幅 | ...，跳过 rank 列"""
    text = """
| 板块 | 涨跌幅 | 成交额 | 资金净流入 | 热度评级 |
|------|--------|--------|-----------|---------|
| 半导体 | +3.45% | 850亿 | +120亿 | 🔥 |
| 人工智能 | +2.87% | 720亿 | +85亿 | 🔥 |
"""
    assert _extract_sectors(text) == ["半导体", "人工智能"]


def test_main_table_standalone_rank():
    """| 排序 | 板块 | ... —— rank 在独立列"""
    text = """
| 排序 | 板块 | 涨跌幅 |
|------|------|--------|
| 1. | 综合 | +1.2% |
| 2. | 自动化设备 | +0.8% |
"""
    assert _extract_sectors(text) == ["综合", "自动化设备"]


def test_main_table_merged_rank():
    """| ⭐1. 板块 | ... —— rank 与板块名合并"""
    text = """
| 排名 | 板块 | 涨跌幅 |
|------|------|--------|
| ⭐1. 综合 | +1.2% |
| 2. 自动化设备 | +0.8% |
"""
    assert _extract_sectors(text) == ["综合", "自动化设备"]


def test_main_table_ignores_non_sector_tables():
    """'数据维度|状态|说明' 表第一列不是板块，必须跳过"""
    text = """
| 数据维度 | 状态 | 说明 |
|---------|------|------|
| 板块涨跌幅排名 | UNKNOWN | 搜索工具未返回有效数据 |
"""
    assert _extract_sectors(text) == []


def test_main_table_mixed_picks_sector_only():
    """混合表：第一张"数据维度"被跳过，第二张"板块"被抓"""
    text = """
| 数据维度 | 状态 |
|---------|------|
| 涨幅 | OK |
| 板块 | 涨跌幅 |
|------|--------|
| 半导体 | +3% |
| 人工智能 | +2% |
"""
    result = _extract_sectors(text)
    assert "半导体" in result
    assert "人工智能" in result
    assert "涨幅" not in result


def test_main_table_markdown_bold():
    """| **半导体** | ... —— 强调要清掉"""
    text = """
| 板块 | 涨跌幅 |
|------|--------|
| **半导体** | +3% |
| *机器人* | +2% |
| __人工智能__ | +2% |
"""
    result = _extract_sectors(text)
    assert "半导体" in result
    assert "机器人" in result
    assert "人工智能" in result


def test_main_table_markdown_link():
    """| [半导体](url) | ... —— 链接要拆出 text"""
    text = """
| 板块 | 涨跌幅 |
|------|--------|
| [半导体](http://example.com) | +3% |
"""
    assert _extract_sectors(text) == ["半导体"]


# ---------- 用户截图原 case ----------

def test_user_screenshot_all_unknown_report():
    """用户截图的真实失败报告 —— 应当返回空列表，不应误识别章节标题"""
    text = """
# A股板块轮动扫描报告
## ⚠️ 数据获取状态声明
| 数据维度 | 状态 | 说明 |
|---------|------|------|
| 板块涨跌幅排名 | UNKNOWN | 搜索工具未返回有效数据 |
| 板块 | 涨跌幅 | 成交额 | 资金净流入 | 热度评级 |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
1. **数据源验证**：建议核实 web_search 工具
2. **替代数据源**：尝试 finance_query
3. **历史参考**：knowledge_search 检索
4. **风险提示**：在缺乏数据情况下
"""
    assert _extract_sectors(text) == []


# ---------- Numbered list fallback ----------

def test_fallback_numbered_with_colon():
    """numbered list with 冒号 —— 真板块能抓到"""
    text = """
1. **低空经济**：政策催化叠加订单兑现
2. **固态电池**：量产临近
3. **数据要素**：商业化加速
"""
    result = _extract_sectors(text)
    assert "低空经济" in result
    assert "固态电池" in result
    assert "数据要素" in result


def test_fallback_numbered_known_fake_sections_rejected():
    """numbered list 全是已知假板块 —— 必须全拒"""
    text = """
1. **数据源验证**：核实 web_search
2. **替代数据源**：尝试 finance_query
3. **历史参考**：检索历史
4. **风险提示**：在缺乏数据情况下
"""
    assert _extract_sectors(text) == []


def test_fallback_unknown_heavy_early_stop():
    """UNKNOWN ≥ 5 + numbered list —— 必须早停，避免抓假板块"""
    text = """
板块热度全部 UNKNOWN UNKNOWN UNKNOWN UNKNOWN UNKNOWN UNKNOWN
1. **数据源验证**：核实
2. **替代数据源**：尝试
"""
    assert _extract_sectors(text) == []


def test_signal_table_not_sector():
    """'信号类型|板块|强度' 表 —— 列名首列不是'板块/排序'，必须跳过"""
    text = """
| 信号类型 | 板块 | 强度 |
|---------|------|------|
| UNKNOWN | UNKNOWN | UNKNOWN |
"""
    assert _extract_sectors(text) == []


# ---------- 英文表头路径 (allow_english=True, Gemini 兜底) ----------

def test_english_header_legit_sectors_accepted():
    """英文表头 + 真板块名 (TitleCase / CamelCase) —— 必须通过"""
    text = """
| Rank | Sector | Change |
|---|---|---|
| 1. | Semiconductors | +3% |
| 2. | Robotics | -1% |
| 3. | Artificial Intelligence | +2% |
| 4. | New Energy Vehicles | +1.5% |
"""
    result = _extract_sectors(text)
    assert result == ["Semiconductors", "Robotics", "Artificial Intelligence", "New Energy Vehicles"]


def test_english_header_garbage_phrases_rejected():
    """英文表头 + 说明性短语 (无大写) —— 必须拒"""
    text = """
| Rank | Sector | Change |
|---|---|---|
| 1. | random words here | +3% |
| 2. | abc | -1% |
| 3. | data source verification | +2% |
"""
    result = _extract_sectors(text)
    # "abc" 过短 (2 字符) 被拒
    # "random words here" / "data source verification" 全小写无大写被拒
    assert result == [], f"English garbage should be rejected, got {result}"


def test_english_header_too_short_token_rejected():
    """'AI' / 'IT' / 'VR' 这种过短 token —— 应该拒（避免和章节标签混淆）"""
    text = """
| Rank | Sector | Change |
|---|---|---|
| 1. | AI | +3% |
| 2. | IT | -1% |
| 3. | VR | +2% |
"""
    result = _extract_sectors(text)
    assert result == [], f"Too-short English tokens should be rejected, got {result}"


def test_english_header_mixed_picks_only_valid():
    """英文表头混合：真板块 + 垃圾 —— 只收真板块"""
    text = """
| Rank | Sector | Change |
|---|---|---|
| 1. | Semiconductors | +3% |
| 2. | random words here | -1% |
| 3. | Robotics | +2% |
| 4. | abc | -2% |
"""
    result = _extract_sectors(text)
    assert result == ["Semiconductors", "Robotics"]


def test_english_header_long_sentence_rejected():
    """超过 4 词的"长句" —— 应该被拒（不是板块名）"""
    text = """
| Rank | Sector | Change |
|---|---|---|
| 1. | This Is Way Too Many Words To Be A Sector Name | +3% |
| 2. | Cloud Computing | -1% |
"""
    result = _extract_sectors(text)
    # 第 1 行 11 词被拒
    # 第 2 行 "Cloud Computing" 2 词全大写首字母通过
    assert "Cloud Computing" in result
    assert len(result) == 1


@pytest.mark.parametrize("section_title", [
    "Risk Warning", "Data Verification", "Disclaimer",
    "Executive Summary", "Methodology", "Summary",
    "Introduction", "Conclusion",
])
def test_english_section_titles_rejected(section_title):
    """英文 fallback 章节标题完整短语 —— 必须拒（防止 Gemini 失败章节被当板块）

    完整短语 == 精确匹配（不用 startswith）以避免误伤合法板块名
    （如 "Risk Parity" / "Risk Management"）。
    """
    text = f"""
| Rank | Sector | Change |
|---|---|---|
| 1. | {section_title} | +3% |
| 2. | Semiconductors | +2% |
"""
    result = _extract_sectors(text)
    assert section_title not in result, \
        f"English section title '{section_title}' should be rejected, got {result}"
    assert "Semiconductors" in result, \
        f"Legit sector should still pass, got {result}"


def test_english_legit_risk_prefix_not_rejected():
    """含 'Risk' 但不是章节标题的合法板块名 —— 必须通过（验证精确匹配不误伤）"""
    text = """
| Rank | Sector | Change |
|---|---|---|
| 1. | Risk Parity | +3% |
| 2. | Risk Management | +2% |
"""
    result = _extract_sectors(text)
    assert result == ["Risk Parity", "Risk Management"], \
        f"'Risk Parity'/'Risk Management' are legit sectors and must not be rejected, got {result}"


@pytest.mark.parametrize("variant", [
    # Case variants
    "risk warning", "Risk warning", "RISK WARNING",
    "executive summary", "Executive summary", "EXECUTIVE SUMMARY",
    "data verification", "Data Verification",
    # Plural variants
    "Risk Warnings", "Risk Disclosures", "Data Sources",
    "Methodologies",
])
def test_english_section_title_variants_rejected(variant):
    """v4: case-insensitive + 复数变体 —— 必须拒

    第二次 review 指出 v3 残留：
    - 大小写敏感性："Risk warning"（mixed case）会漏过滤
    - 复数变体："Risk Warnings" / "Risk Disclosures" / "Data Sources" / "Methodologies"
    修复：模块级 _en_section_titles_lower = {t.lower() for t in _EN_SECTION_TITLES}，
    比较时 name.lower() in _en_section_titles_lower。
    """
    text = f"""
| Rank | Sector | Change |
|---|---|---|
| 1. | {variant} | +3% |
| 2. | Semiconductors | +2% |
"""
    result = _extract_sectors(text)
    assert variant not in result, \
        f"English section title variant '{variant}' should be rejected, got {result}"
    assert "Semiconductors" in result, \
        f"Legit sector should still pass, got {result}"


def test_english_singular_plural_not_section_passes():
    """v4: 复数变体但不是章节标题（如 'Risks Warnings'）—— 必须不误伤"""
    text = """
| Rank | Sector | Change |
|---|---|---|
| 1. | Risks Warnings | +3% |
| 2. | Datas | +2% |
"""
    result = _extract_sectors(text)
    # "Risks Warnings" / "Datas" 都不在 _en_section_titles_lower 里（只有 "Risk Warnings" / "Data Sources"），
    # 应该通过（不是精确匹配章节标题）
    assert "Risks Warnings" in result, f"'Risks Warnings' should not be over-rejected, got {result}"
    assert "Datas" in result, f"'Datas' should not be over-rejected, got {result}"


# ---------- 边界 ----------

def test_empty_input():
    assert _extract_sectors("") == []


def test_none_input():
    assert _extract_sectors(None) == []  # type: ignore[arg-type]


def test_unknown_only_rejected():
    """纯 UNKNOWN 行 — 不应误识别"""
    text = """
| 板块 | 涨跌幅 |
|------|--------|
| UNKNOWN | UNKNOWN |
"""
    assert _extract_sectors(text) == []


@pytest.mark.parametrize("name,should_contain", [
    ("半导体", True),
    ("人工智能", True),
    ("新能源汽车", True),
    ("医药", True),
    ("证券", True),
    ("综合", True),
    ("自动化设备", True),
    ("专用设备", True),
    ("低空经济", True),
    ("固态电池", True),
    ("数据要素", True),  # 数据 不在 _SECTION_PREFIXES（避免误伤真板块）
])
def test_real_sector_names_round_trip(name, should_contain):
    """真实申万行业 + 常见概念板块名都能被识别（主表 + fallback 都过）"""
    text = f"""
| 板块 | 涨跌幅 |
|------|--------|
| {name} | +3% |
"""
    result = _extract_sectors(text)
    if should_contain:
        assert name in result, f"{name} should be in {result}"
    else:
        assert name not in result