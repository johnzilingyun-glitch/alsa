import re

filepath = 'D:/zily/alsa/alsa/python_service/app/services/report_generator_service.py'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

if 'def esc(t):' not in text:
    text = text.replace('def md(t): return markdown2.markdown(t) if t else ""', 'def md(t): return markdown2.markdown(t) if t else ""\n        import html\n        def esc(t): return html.escape(str(t)) if t else ""')

# Regex substitutions to add esc()
text = re.sub(r'ks_condition = kill_switch\.get\("condition"\) or "([^"]+)"', r'ks_condition = esc(kill_switch.get("condition") or "\1")', text)

text = text.replace('{s.get("case", "N/A")}', '{esc(s.get("case", "N/A"))}')
text = text.replace('{s.get("logic", "")}', '{esc(s.get("logic", ""))}')
text = text.replace("{s.get('logic', '')}", "{esc(s.get('logic', ''))}")

text = text.replace('{wind_control.get("lockup_date") or "无近三个月大额解禁信息"}', '{esc(wind_control.get("lockup_date") or "无近三个月大额解禁信息")}')
text = text.replace('{wind_control.get("lockup_impact") or "解禁冲击评估为低/无"}', '{esc(wind_control.get("lockup_impact") or "解禁冲击评估为低/无")}')
text = text.replace('{wind_control.get("reduction_plan") or "无未完成减持公告"}', '{esc(wind_control.get("reduction_plan") or "无未完成减持公告")}')
text = text.replace('{wind_control.get("crowding_level") or "机构仓位拥挤度适中"}', '{esc(wind_control.get("crowding_level") or "机构仓位拥挤度适中")}')

text = text.replace('{wind_control.get("lockup_date") or "无近三个月大额禁售解禁信息"}', '{esc(wind_control.get("lockup_date") or "无近三个月大额禁售解禁信息")}')
text = text.replace('{wind_control.get("lockup_impact") or "解禁及减持冲击低/无"}', '{esc(wind_control.get("lockup_impact") or "解禁及减持冲击低/无")}')
text = text.replace('{wind_control.get("crowding_level") or "南向资金持股变动稳健"}', '{esc(wind_control.get("crowding_level") or "南向资金持股变动稳健")}')
text = text.replace('{wind_control.get("reduction_plan") or "大股东及质押风险为安全/无"}', '{esc(wind_control.get("reduction_plan") or "大股东及质押风险为安全/无")}')

text = text.replace('{wind_control.get("lockup_date") or "无大额内部人买卖交易记录"}', '{esc(wind_control.get("lockup_date") or "无大额内部人买卖交易记录")}')
text = text.replace('{wind_control.get("lockup_impact") or "无正在执行的10b5-1大额减持计划"}', '{esc(wind_control.get("lockup_impact") or "无正在执行的10b5-1大额减持计划")}')
text = text.replace('{wind_control.get("reduction_plan") or "空头头寸占比 (Short Interest) 处于安全低位"}', '{esc(wind_control.get("reduction_plan") or "空头头寸占比 (Short Interest) 处于安全低位")}')
text = text.replace('{wind_control.get("crowding_level") or "13F 机构持仓未见踩踏或大幅抛售"}', '{esc(wind_control.get("crowding_level") or "13F 机构持仓未见踩踏或大幅抛售")}')

text = text.replace('{discipline.get("left_side_condition") or locale["label_no_left"]}', '{esc(discipline.get("left_side_condition") or locale["label_no_left"])}')
text = text.replace('{discipline.get("right_side_trigger") or locale["label_no_right"]}', '{esc(discipline.get("right_side_trigger") or locale["label_no_right"])}')
text = text.replace('{discipline.get("max_drawdown_limit") or locale["label_default_drawdown"]}', '{esc(discipline.get("max_drawdown_limit") or locale["label_default_drawdown"])}')
text = text.replace('{discipline.get("thesis_invalidation_trigger") or locale["label_no_invalidation"]}', '{esc(discipline.get("thesis_invalidation_trigger") or locale["label_no_invalidation"])}')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text)

print("Patch applied to generator successfully!")

# Now patch the existing HTML report directly
html_path = 'D:/zily/alsa/alsa/reports/601899_report_20260603_105357.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# The specific bug in 601899 is the KS condition having <80,000 and <140 and <MA200.
# We will just manually escape it in the generated report.
html = html.replace('<80,000元', '&lt;80,000元').replace('<140亿', '&lt;140亿').replace('<28%', '&lt;28%').replace('<MA200', '&lt;MA200')

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print("Patch applied to 601899 html successfully!")
