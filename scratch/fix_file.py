import os

file_path = 'python_service/app/services/report_generator_service.py'

with open(file_path, 'rb') as f:
    lines = f.readlines()

print("Original file line count:", len(lines))

# Verify line 1228 and 1329 to be safe
print("Line 1228:", lines[1227].decode('utf-8', errors='replace').strip())
print("Line 1329:", lines[1328].decode('utf-8', errors='replace').strip())

# The replacement code block
replacement = """
        lines = []
        labels = {
            "tagline": "📌 核心论点",
            "investmentThesis": "📋 投资论题",
            "sentiment": "🎯 投资建议",
            "masterVariable": "🔑 核心变量",
            "coreContradiction": "⚡ 核心矛盾",
            "credibilityScore": "📊 可信度评分",
        }
        for key, label in labels.items():
            if key in data:
                lines.append(_format_field(label, data[key]))

        if "expectedPrice" in data and isinstance(data["expectedPrice"], dict):
            ep = data["expectedPrice"]
            lines.append("### 💰 预期价格计算\\n")
            lines.append(f"- **计算公式**: {ep.get('calculation', 'N/A')}")
            lines.append(f"- **预期价格**: ${ep.get('result', 'N/A')}")
            lines.append(f"- **vs当前价格**: {ep.get('vsCurrentPrice', ep.get('currentPrice', 'N/A'))}")
            lines.append(f"- **预期回报**: {ep.get('expectedReturn', 'N/A')}")
            if ep.get('decisionRuleCheck'):
                lines.append(f"- **决策规则校验**: {ep.get('decisionRuleCheck')}")
            lines.append("")

        # Exit Mechanism / Disciplines
        em = data.get("exit_mechanism") or data.get("exitMechanism") or {}
        if em:
            lines.append("### 🚪 退出机制\\n")
            if "takeProfit" in em:
                lines.append("**止盈:**")
                for item in em["takeProfit"]:
                    lines.append(f"- {item}")
            if "stopLoss" in em:
                lines.append("\\n**止损:**")
                for item in em["stopLoss"]:
                    lines.append(f"- {item}")
            if "thesisFalsification" in em or "thesisInvalidation" in em:
                lines.append("\\n**论题证伪条件:**")
                for item in em.get("thesisFalsification", em.get("thesisInvalidation", [])):
                    lines.append(f"- {item}")
            lines.append("")

        if "criticalRisks" in data and isinstance(data["criticalRisks"], list):
            lines.append("### ⚠️ 关键风险\\n")
            for risk in data["criticalRisks"]:
                lines.append(f"- {risk}")
            lines.append("")

        if "falsificationRedlines" in data and isinstance(data["falsificationRedlines"], list):
            lines.append("### 🚨 证伪红线\\n")
            lines.append("| 条件 | 窗口 | 行动 |\\n|------|------|------|")
            for item in data["falsificationRedlines"]:
                if isinstance(item, dict):
                    lines.append(f"| {item.get('condition','')} | {item.get('window','')} | {item.get('action','')} |")
                elif isinstance(item, str):
                    lines.append(f"- {item}")
            lines.append("")

        if "keyRevisionsToPriorAnalyses" in data and isinstance(data["keyRevisionsToPriorAnalyses"], dict):
            lines.append("### 📝 关键修正\\n")
            for rk, rv in data["keyRevisionsToPriorAnalyses"].items():
                lines.append(f"- **{_humanize(rk)}**: {rv}")
            lines.append("")

        # Formatting anything else
        handled = set(labels.keys()) | {"expectedPrice", "tradingPlan", "kellyPosition", "timeHorizon", "buildPlan", "exitMechanism", "criticalRisks", "falsificationRedlines", "keyRevisionsToPriorAnalyses"}
        for key, val in data.items():
            if key not in handled:
                label = _humanize(key)
                if isinstance(val, str):
                    lines.append(f"### {label}\\n\\n{val}\\n")
                elif isinstance(val, dict):
                    lines.append(f"### {label}\\n")
                    for dk, dv in val.items():
                        lines.append(f"- **{_humanize(dk)}**: {dv}")
                    lines.append("")
                elif isinstance(val, list):
                    lines.append(f"### {label}\\n")
                    for item in val:
                        if isinstance(item, dict):
                            lines.append(f"- {' | '.join(str(v) for v in item.values())}")
                        else:
                            lines.append(f"- {item}")
                    lines.append("")

        raw_md = "\\n".join(lines) if lines else ""
        return self._escape_technical_underscores(raw_md)
"""

# Indent the replacement block line endings to bytes
replacement_bytes = [line.encode('utf-8') + b'\n' for line in replacement.split('\n')]

# Perform the replacement: replace lines 1229 to 1328 (0-indexed: 1228 to 1328)
# We want to replace lines[1228:1328]
new_lines = lines[:1228] + replacement_bytes + lines[1328:]

with open(file_path, 'wb') as f:
    f.writelines(new_lines)

print("Replacement complete. New file line count:", len(new_lines))
