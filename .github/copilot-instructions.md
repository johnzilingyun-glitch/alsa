# Copilot Instructions

## Commands

```bash
npm run dev          # Start Express API + Vite SPA on port 3000
npm run dev:py       # Start Python FastAPI service on port 8000 (required for A-Share data)
npm run build        # Vite production build
npm run lint         # TypeScript type-check (tsc --noEmit)
npm test             # Run all tests (vitest run)
npm run test:watch   # Vitest in watch mode

# Run a single test file:
npx vitest run src/test/aiService.test.ts
```

## Architecture

This is a **three-tier stock analysis app** for A-Share, HK-Share, and US-Share markets:

1. **React SPA** (`src/`) — UI, Zustand state, hooks, components
2. **Express API gateway** (`server.ts` + `server/`) — runs on port 3000, proxies AI calls and serves the Vite SPA in dev via middleware
3. **Python FastAPI service** (`python_service/`) — runs on port 8000, uses AkShare for A-Share data (spot quotes, sector flows, northbound capital, technicals). Node calls it at `http://127.0.0.1:8000`.

### AI Analysis Pipeline

- **Primary LLM**: Gemini via `@google/genai` SDK (`src/services/geminiService.ts`). Model fallback chain: `gemini-3.1-pro-preview` → `gemini-3.1-flash-lite-preview` → `gemini-1.5-pro`.
- **Cross-provider fallback** (`src/services/llmProvider.ts`): When all Gemini models are quota-exhausted, falls back to OpenAI (`gpt-4o-mini`) or Anthropic in sequence.
- **`aiService.ts` is a facade**: It re-exports from `analysisService`, `marketService`, `discussionService`, and `adminService`. Add new functionality to the underlying services, not to `aiService.ts`.

### Multi-Agent Discussion System

`src/services/discussion/` orchestrates a structured debate between expert agents:

- **Three topologies** defined in `orchestrator.ts`: `quick` (3 rounds), `standard` (7 rounds), `deep` (10 rounds)
- Round order matters — e.g., `Bull Researcher` and `Bear Researcher` run in parallel (round 4), then `Contrarian Strategist` synthesizes their output
- Agent roles are typed as `AgentRole` in `src/types.ts`

### Analysis Levels

`quick` | `standard` | `deep` — controlled via `src/services/analysisLevelConfig.ts`. Each level specifies which output fields are populated, whether discussion/backtest runs, token estimates, and latency.

### State Management

Zustand stores in `src/stores/`. Each store is scoped to a domain:
- `useAnalysisStore` — current stock analysis result, symbol, market
- `useDiscussionStore` — multi-agent discussion state
- `useUIStore` — modal visibility, error messages, admin panel
- `useConfigStore` — Gemini API key, language, service mode
- `useMarketStore`, `useScenarioStore`, `useDecisionStore`, `useWatchlistStore`

Hooks in `src/hooks/` contain all business logic and call into `src/services/`. `App.tsx` only wires hooks to components.

### Data Persistence

Analysis history is stored as JSON files in `data/history/` on the server (30-day retention, cleaned on startup). Logs go to `data/optimization_log.json`.

## Key Conventions

- **All types live in `src/types.ts`** — the canonical single-file type source. Add new types here.
- **All API responses from Python follow `{ success: boolean, data?: any, error?: string, code?: string }`** — Node checks `success` before using `data`.
- **Market values are always** `"A-Share" | "HK-Share" | "US-Share"` (the `Market` type) — never plain strings.
- **Large components are lazy-loaded** in `App.tsx` with `React.lazy`. Follow this pattern for any new heavy component.
- **i18n**: UI strings go into `src/i18n/locales/en.json` and `zh.json`. The app defaults to Chinese (`zh-CN`) and supports English.
- **A-Share symbol validation**: 6-digit strings. STAR Market (`68xxxx`) and ChiNext (`30xxxx`) have a ±20% price limit; all others ±10%.
- **`StockInfo.lastUpdated` must include `"CST"`** — this is validated in `validateStockInfo()`.

## Environment Variables

```
GEMINI_API_KEY          # Required — Gemini AI API key
FEISHU_WEBHOOK_URL      # Optional — Feishu bot webhook for report delivery
VITE_OPENAI_API_KEY     # Optional — fallback LLM (also read as OPENAI_API_KEY)
VITE_ANTHROPIC_API_KEY  # Optional — fallback LLM (also read as ANTHROPIC_API_KEY)
APP_URL                 # Injected by AI Studio at runtime
```

Copy `.env.example` to `.env` and set `GEMINI_API_KEY`.

## Workflow Rules

- **每次完成用户任务后**，必须通过 `#tool:askQuestion` 询问用户是否还有其他需求需要完成。

## Coding Guidelines (Karpathy Rules)

遵循以下编码行为准则，减少常见 LLM 编码错误：

### 1. 先思考再编码

- 明确陈述你的假设。如果不确定，就问。
- 如果存在多种解读，展示它们——不要默默选一个。
- 如果有更简单的方案，说出来。必要时提出反对意见。
- 如果有不清楚的地方，停下来。说明困惑点，然后提问。

### 2. 简洁优先

最少的代码解决问题，不做投机性开发：

- 不添加未被要求的功能。
- 不为一次性代码创建抽象。
- 不添加未被要求的"灵活性"或"可配置性"。
- 不为不可能发生的场景添加错误处理。
- 如果写了 200 行能用 50 行解决，重写。

问自己："高级工程师会说这太复杂了吗？" 如果是，简化。

### 3. 精准修改

只动必须动的。只清理自己的代码：

- 不"改进"相邻的代码、注释或格式。
- 不重构没有问题的东西。
- 匹配现有风格，即使你会用不同方式写。
- 如果注意到无关的死代码，提及它——不要删除。
- 移除因你的修改而变得无用的 imports/变量/函数。
- 不移除已有的死代码，除非被要求。

测试标准：每一行改动都应直接追溯到用户的请求。

### 4. 目标驱动执行

定义成功标准，循环验证直到满足：

- "添加验证" → "为无效输入写测试，然后让它们通过"
- "修复 bug" → "写一个重现 bug 的测试，然后让它通过"
- "重构 X" → "确保重构前后测试都通过"

多步骤任务请陈述简要计划：
```
1. [步骤] → 验证: [检查方式]
2. [步骤] → 验证: [检查方式]
3. [步骤] → 验证: [检查方式]
```
