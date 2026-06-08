import json
import sys
import os
import re
from typing import List, Dict, Any

CATEGORY_KEYS = {
    "upside": ["upside", "opportunities", "bull_thesis", "catalysts", "key_opps", "upside_points", "core_thesis"],
    "downside": ["downside", "risks", "critical_risks", "risks_summary", "key_risks", "downside_points"],
    "moat": ["moat_points", "competitive_advantages", "moat", "competitive_positioning", "moat_summary"],
    "macro": ["macro_points", "macro", "technical_analysis", "macro_supply_demand", "macro_summary"],
    "risks": ["risks_points", "thesis_invalidation_trigger", "stop_loss_rules", "exit_mechanism", "risks", "risks_summary"]
}

def _extract_strings_from_dict(d_val: dict, category: str) -> List[str]:
    strs = []
    for dk, dv in d_val.items():
        # For moat or upside, skip keys indicating disadvantage or risk
        if category in ("moat", "upside"):
            if any(x in dk.lower() for x in ["disadvantage", "risk", "shortcoming", "weakness", "threat", "bear"]):
                continue
        if isinstance(dv, str) and len(dv) > 5:
            strs.append(dv)
        elif isinstance(dv, dict):
            strs.extend(_extract_strings_from_dict(dv, category))
        elif isinstance(dv, list):
            for item in dv:
                if isinstance(item, str) and len(item) > 5:
                    strs.append(item)
    return strs

def extract_items_by_keywords_dual(category: str, keywords: List[str], discussion_msgs: List[Dict[str, Any]], limit: int = 5) -> List[str]:
    # 1. Try JSON extraction first
    items = []
    for m in discussion_msgs:
        content = m.get("content", "").strip()
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            try:
                obj = json.loads(match.group(0))
                target_keys = CATEGORY_KEYS.get(category, [])
                for tk in target_keys:
                    for k in obj.keys():
                        if k.lower() == tk.lower() or tk.lower() in k.lower() or k.lower() in tk.lower():
                            val = obj[k]
                            if isinstance(val, list):
                                for item in val:
                                    if isinstance(item, str) and len(item) > 5:
                                        if item not in items:
                                            items.append(item)
                            elif isinstance(val, dict):
                                for item in _extract_strings_from_dict(val, category):
                                    if item not in items:
                                        items.append(item)
                            elif isinstance(val, str) and len(val) > 10:
                                sentences = re.split(r'[。\n]+', val)
                                for s in sentences:
                                    s_clean = s.strip()
                                    if len(s_clean) > 8:
                                        if s_clean not in items:
                                            items.append(s_clean)
            except Exception as e:
                pass
    
    if len(items) >= 2:
        return items[:limit]

    # 2. Fallback to boundary-aware text scanner on normalized text
    for m in discussion_msgs:
        content = m.get("content", "")
        if not content:
            continue
        content_normalized = content.replace('\\n', '\n')
        lines = content_normalized.split('\n')
        in_section = False
        for line in lines:
            line_stripped = line.strip()
            
            # Check for header or bold label
            is_header = line_stripped.startswith('#')
            is_bold = line_stripped.startswith('**')
            is_bold_label = is_bold and any(kw.lower() in line_stripped.lower() for kw in keywords)
            
            if is_header:
                if any(kw.lower() in line_stripped.lower() for kw in keywords):
                    in_section = True
                else:
                    in_section = False
                continue
            elif is_bold:
                if is_bold_label:
                    in_section = True
                else:
                    in_section = False
                continue
            
            if in_section:
                if '|' in line_stripped or line_stripped.startswith('---') or line_stripped.startswith('==='):
                    continue
                if not line_stripped:
                    continue
                    
                m_bullet = re.match(r'^\s*[-*•▪◆\d.)]+\s*(.+)$', line_stripped)
                if m_bullet:
                    clean = m_bullet.group(1).strip().strip('*').strip()
                    if len(clean) > 8 and not clean.startswith('#') and not clean.startswith('---'):
                        if clean not in items:
                            items.append(clean)
                            if len(items) >= limit:
                                break
                elif line_stripped and not line_stripped.startswith('#') and len(line_stripped) > 15:
                    if line_stripped not in items:
                        items.append(line_stripped)
                        if len(items) >= limit:
                            break
        if len(items) >= limit:
            break
    return items[:limit]

def test():
    with open('/home/ubuntu/work/alsa/scratch/job_0fa38353.json', 'r', encoding='utf-8') as f:
        job_data = json.load(f)
    discussion_msgs = job_data.get("discussion", [])
    
    print("--- Testing extract_items_by_keywords_dual ---")
    upside = extract_items_by_keywords_dual("upside", ["看涨", "利好", "上行", "催化剂", "Catalyst", "Upside", "机遇", "优势", "核心竞争力", "核心论点"], discussion_msgs)
    print("Upside items found:", len(upside))
    for i, item in enumerate(upside):
        print(f"  {i+1}: {repr(item)}")
        
    downside = extract_items_by_keywords_dual("downside", ["看跌", "利空", "下行", "风险", "Risk", "Downside", "压制", "威胁", "一致性偏差", "被忽视", "盲区", "Consensus Bias"], discussion_msgs)
    print("Downside items found:", len(downside))
    for i, item in enumerate(downside):
        print(f"  {i+1}: {repr(item)}")

    moat_points = extract_items_by_keywords_dual("moat", ["护城河", "Moat", "壁垒", "竞争优势"], discussion_msgs)
    print("Moat items found:", len(moat_points))
    for i, item in enumerate(moat_points):
        print(f"  {i+1}: {repr(item)}")

    macro_points = extract_items_by_keywords_dual("macro", ["宏观", "技术面", "资金面", "Technical", "Macro"], discussion_msgs)
    print("Macro items found:", len(macro_points))
    for i, item in enumerate(macro_points):
        print(f"  {i+1}: {repr(item)}")

    risks_points = extract_items_by_keywords_dual("risks", ["证伪", "失效", "止损", "Invalidation", "风险预警"], discussion_msgs)
    print("Risks items found:", len(risks_points))
    for i, item in enumerate(risks_points):
        print(f"  {i+1}: {repr(item)}")

if __name__ == '__main__':
    test()
