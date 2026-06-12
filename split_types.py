import re

with open("src/types.ts", "r", encoding="utf-8") as f:
    content = f.read()

# We will split it into blocks: export interface XXX or export type XXX
# and assign them to different files based on keywords.

blocks = re.split(r'\n(?=export (?:interface|type) )', content)

market_keywords = ['Market', 'StockInfo', 'DataQuality', 'NewsItem', 'IndexInfo', 'CommodityAnalysis', 'MarketOverview', 'StockFundamentals', 'FundamentalTableItem', 'HistoricalData', 'ValuationAnalysis', 'CapitalFlow', 'InstitutionalFlow']
analysis_keywords = ['TechnicalIndicators', 'RiskMetrics', 'SectorAnalysis', 'Recommendation', 'AnalysisLevel', 'ExpertRole', 'DiscussionMessage', 'StockAnalysis', 'ScenarioItem', 'ScenarioAnalysis', 'PromptVersion', 'SearchAlert', 'AgentReflection', 'PredictionRecord']
trading_keywords = ['MockAccount', 'MockPosition', 'MockTrade', 'TradeIntent', 'PendingOrder', 'TradeAction', 'TradeSignal', 'AlertStatus']

market_blocks = []
analysis_blocks = []
trading_blocks = []
common_blocks = []

for block in blocks:
    if not block.strip():
        continue
    
    # Extract the name of the type/interface
    match = re.search(r'export (?:interface|type) (\w+)', block)
    if match:
        name = match.group(1)
        if name in market_keywords:
            market_blocks.append(block)
        elif name in analysis_keywords:
            analysis_blocks.append(block)
        elif name in trading_keywords:
            trading_blocks.append(block)
        else:
            common_blocks.append(block)
    else:
        common_blocks.append(block)

# Since some types depend on each other, we will add import statements at the top
common_content = "\n".join(common_blocks)
market_content = "import { DataQuality, TechnicalIndicators, RiskMetrics } from './common';\n" + "import { SectorAnalysis, CommodityAnalysis, Recommendation } from './analysis';\n\n" + "\n".join(market_blocks)
analysis_content = "import { RiskMetrics } from './common';\n" + "\n".join(analysis_blocks)
trading_content = "\n".join(trading_blocks)

with open("src/types/common.ts", "w", encoding="utf-8") as f:
    f.write(common_content)

with open("src/types/market.ts", "w", encoding="utf-8") as f:
    f.write(market_content)

with open("src/types/analysis.ts", "w", encoding="utf-8") as f:
    f.write(analysis_content)

with open("src/types/trading.ts", "w", encoding="utf-8") as f:
    f.write(trading_content)

# Update index.ts (src/types.ts)
with open("src/types.ts", "w", encoding="utf-8") as f:
    f.write("export * from './types/common';\nexport * from './types/market';\nexport * from './types/analysis';\nexport * from './types/trading';\n")

print("Splitting complete.")
