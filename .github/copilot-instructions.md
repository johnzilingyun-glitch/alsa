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
