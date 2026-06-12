import re
import os

with open("src/types.ts", "r", encoding="utf-8") as f:
    content = f.read()

blocks = re.split(r'\n(?=export (?:interface|type|enum|const|function) )', content)

market_keywords = ['Market', 'StockInfo', 'DataQuality', 'NewsItem', 'IndexInfo', 'CommodityAnalysis', 'MarketOverview', 'StockFundamentals', 'FundamentalTableItem', 'IndustryAnchor', 'HistoricalData', 'ValuationAnalysis', 'CapitalFlow', 'InstitutionalFlow']
analysis_keywords = ['TechnicalIndicators', 'RiskMetrics', 'SectorAnalysis', 'Recommendation', 'AnalysisLevel', 'ExpertRole', 'DiscussionMessage', 'AgentMessage', 'VerificationMetrics', 'TradingPlan', 'TradingPlanVersion', 'ActionStance', 'Scenario', 'ScenarioItem', 'ScenarioAnalysis', 'CoreVariable', 'BusinessModel', 'QuantifiedRisk', 'ExpectedValueOutcome', 'SensitivityMatrixRow', 'Catalyst', 'SensitivityFactor', 'ExpectationGap', 'AnalystWeight', 'CalculationResult', 'SegmentValuation', 'DataVerification', 'StockAnalysis', 'PromptVersion', 'SearchAlert', 'AgentReflection', 'PredictionRecord']
trading_keywords = ['MockAccount', 'MockPosition', 'MockTrade', 'TradeIntent', 'PendingOrder', 'TradeAction', 'TradeSignal', 'AlertStatus']

files = {
    'market.ts': [],
    'analysis.ts': [],
    'trading.ts': [],
    'common.ts': []
}

type_to_file = {}

# Parse blocks
parsed_blocks = []
for block in blocks:
    if not block.strip():
        continue
    match = re.search(r'export (?:interface|type|enum|const|function) (\w+)', block)
    name = None
    if match:
        name = match.group(1)
        if name in market_keywords:
            file_name = 'market.ts'
        elif name in analysis_keywords:
            file_name = 'analysis.ts'
        elif name in trading_keywords:
            file_name = 'trading.ts'
        else:
            file_name = 'common.ts'
    else:
        file_name = 'common.ts'
    
    parsed_blocks.append({'name': name, 'content': block, 'file': file_name})
    if name:
        type_to_file[name] = file_name

os.makedirs('src/types', exist_ok=True)

# Find imports needed for each file
for f_name, blocks_list in files.items():
    pass

# To avoid complicated AST parsing, we just import ALL other types from other files using explicit names.
file_contents = {k: "" for k in files.keys()}

for b in parsed_blocks:
    files[b['file']].append(b['content'])

# Build import headers
# We can just extract all words from a file, and if a word matches a type defined in another file, we add it to the import list.
for f_name in files.keys():
    content_str = "\n".join(files[f_name])
    words = set(re.findall(r'\b[A-Za-z_]\w*\b', content_str))
    
    imports = {}
    for word in words:
        if word in type_to_file and type_to_file[word] != f_name:
            source_file = type_to_file[word].replace('.ts', '')
            if source_file not in imports:
                imports[source_file] = set()
            imports[source_file].add(word)
    
    import_statements = []
    for source, type_names in imports.items():
        import_statements.append(f"import type {{ {', '.join(type_names)} }} from './{source}';")
    
    final_content = "\n".join(import_statements) + "\n\n" + content_str
    with open(f"src/types/{f_name}", "w", encoding="utf-8") as f:
        f.write(final_content)

# Update index.ts
with open("src/types/index.ts", "w", encoding="utf-8") as f:
    f.write("export * from './common';\nexport * from './market';\nexport * from './analysis';\nexport * from './trading';\n")

print("Splitting complete with smart imports.")
