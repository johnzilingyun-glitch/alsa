def test_svg():
    items = [{"label": "Bull", "value": 210}, {"label": "Base", "value": 170}, {"label": "Bear", "value": 144}]
    bar_h = 24
    gap = 12
    left_margin = 130
    right_margin = 80
    chart_w = 400
    n = len(items)
    svg_h = n * (bar_h + gap) + gap + 40
    svg_w = left_margin + chart_w + right_margin
    vals = [210, 170, 144]
    max_val = 210

    text_color = "#1e293b"
    label_color = "#475569"
    
    parts = [
        f'<svg viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%; display:block; background:#ffffff; border-radius:12px; border:1px solid #e2e8f0; padding: 10px; margin: 15px 0;">',
        '<defs>',
        '  <linearGradient id="barGradient" x1="0%" y1="0%" x2="100%" y2="0%">',
        '    <stop offset="0%" stop-color="#818CF8" />',
        '    <stop offset="100%" stop-color="#4F46E5" />',
        '  </linearGradient>',
        '  <filter id="shadow" x="-5%" y="-10%" width="120%" height="130%">',
        '    <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#4F46E5" flood-opacity="0.15"/>',
        '  </filter>',
        '  <style>',
        '    @keyframes scaleX { from { stroke-dashoffset: 1000; } to { stroke-dashoffset: 0; } }',
        '    .bar-line { stroke-dasharray: 1000; stroke-dashoffset: 0; animation: scaleX 1.2s ease-out forwards; }',
        '  </style>',
        '</defs>'
    ]

    y_offset = gap + 10
    
    for i, item in enumerate(items):
        val = item["value"]
        label = item["label"]
        y = y_offset + i * (bar_h + gap)

        bar_w = max(val / max_val * chart_w, 4)

        parts.append(
            f'<rect x="{left_margin}" y="{y:.0f}" width="{chart_w}" height="{bar_h}" rx="6" fill="#f1f5f9" />'
        )
        parts.append(
            f'<line class="bar-line" x1="{left_margin + 3}" y1="{y + bar_h/2:.0f}" x2="{left_margin + bar_w - 3:.0f}" y2="{y + bar_h/2:.0f}" stroke="url(#barGradient)" stroke-width="{bar_h}" stroke-linecap="round" filter="url(#shadow)"/>'
        )
    parts.append("</svg>")
    print("\n".join(parts))

test_svg()
