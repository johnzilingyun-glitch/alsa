# PROJECT KNOWLEDGE BASE — ALSA

**Generated:** 2026-06-24
**Commit:** 7747d63
**Branch:** main

## OVERVIEW

AI-powered quantitative trading & research platform. Three-tier architecture: React SPA (client) → Express API gateway → FastAPI backend. Cross-market support (A-Share, HK-Share, US-Share) with LLM-driven analysis, multi-agent discussion system, paper trading engine, and real-time dashboards.

## STRUCTURE

```
.
├── src/                    # React 19 SPA (components, stores, hooks, services)
├── server/                 # Express 4 API gateway
├── python_service/         # FastAPI + Celery backend (325 files)
│   ├── app/api/            #   26 API route modules
│   ├── app/services/       #   50+ service modules
│   ├── app/db/             #   SQLite (SQLModel) + Redis
│   ├── app/backtest/       #   Event-driven backtest engine
│   ├── app/decision/       #   Trading decision court
│   ├── app/quant/          #   Polars indicators, risk metrics, valuation
│   ├── app/lake/           #   DuckDB + Parquet data lake
│   ├── app/vector/         #   LanceDB vector store (embeddings)
│   ├── app/risk/           #   Kill switch + pre-trade risk
│   ├── app/prompting/      #   Prompt version registry + runtime
│   ├── app/observability/  #   Metrics + audit logging
│   ├── tests/              #   62 pytest files
│   ├── paper_trading_system/ # Qlib-based simulation engine (Python 3.9)
│   └── scratch/            #   ~50 ad-hoc debug scripts (NOT production code)
├── sdk/                    # Published SDK packages (js/ + python/)
├── skills/                 # AI agent skill definitions (22 dirs)
├── config/                 # MCP tool config (mcporter.json)
├── scripts/                # IBKR gateway launcher, repo hygiene audit
├── data/                   # Analysis history JSON, brain state, SQLite DBs
├── reports/                # Generated HTML/TXT sector reports
├── server.ts               # Express entry point (at root, outside server/)
├── Dockerfile              # Python backend container
├── Dockerfile.frontend     # Node frontend + gateway container
└── docker-compose.yml      # 6 services: backend, frontend, celery_worker, redis, postgres
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Frontend UI code | `src/components/` | 30+ components, lazy-loaded in App.tsx |
| Zustand state stores | `src/stores/` | 11 domain-scoped stores |
| Business logic hooks | `src/hooks/` | useStockAnalysis, useDiscussion, useChat, etc. |
| AI analysis pipeline (client) | `src/services/` | aiService, geminiService, llmProvider |
| Multi-agent discussion | `src/services/discussion/` | Orchestrator, 7+ roles, 3 topologies |
| Types (canonical) | `src/types.ts` | 735 lines — ALSO duplicated in src/types/ dir |
| Express gateway routes | `server/` + `server/routes/` | analysisRoutes, ibkrRoutes, llmRoutes |
| LLM gateway | `server/llmGateway.ts` | Also proxied to python_service |
| FastAPI routes | `python_service/app/api/` | 26 route files, aggregated in router.py |
| Backend services | `python_service/app/services/` | 50+ files (market, analysis, trading, etc.) |
| LLM proxy (Python) | `python_service/app/services/llm_gateway.py` | 658 lines — oversized |
| Database models | `python_service/app/db/models.py` | 14+ SQLModel tables |
| Data providers | `python_service/app/services/data_providers/` | AkShare, yfinance, iwencai router |
| Python tests | `python_service/tests/` | 62 pytest files |
| Vitest tests | `src/**/__tests__/` + `server/__tests__/` | ~77 test files |
| CLI tool | `python_service/cli.py` | `alsacli` — Click-based, not documented in root |
| SDK | `sdk/js/alsa-sdk/` + `sdk/python/alsa_sdk/` | Separate packages, zero test coverage |
| Celery worker | `python_service/app/worker.py` | 2 tasks: run_analysis, run_sector_analysis |
| Config/CI | `.github/workflows/ci.yml` | 4 parallel jobs (lint, test, security, python-test) |

## CODE MAP

Key symbols and their locations:

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `App` | component | `src/App.tsx:50` | Root React component, lazy-loads all views |
| `server.ts` | entry | `server.ts` | Express gateway, mounts routes + proxy + WebSocket |
| `main.py` | entry | `python_service/main.py` | FastAPI app, async loops, init_db |
| `worker.py` | entry | `python_service/app/worker.py` | Celery app: `alsa_worker` |
| `cli.py` | entry | `python_service/cli.py` | Click CLI tool (`alsacli`) |
| `router.py` | route | `python_service/app/api/router.py` | Aggregates 26 route modules |
| `llmGateway.ts` | service | `server/llmGateway.ts` | Server-side LLM proxy |
| `llm_gateway.py` | service | `python_service/app/services/llm_gateway.py` | Python LLM gateway (658 LOC) |
| `aiService.ts` | facade | `src/services/aiService.ts` | Client-side AI service facade |
| `discussion_service.py` | service | `python_service/app/services/discussion_service.py` | Multi-agent discussion (810 LOC) |
| `brain_manager.py` | service | `python_service/app/services/brain_manager.py` | Brain/genome management (371 LOC) |
| `stockRoutes.ts` | routes | `server/stockRoutes.ts` | Stock data routes (1261 LOC — oversized) |
| `analysisJobService.py` | service | `python_service/app/services/analysis_job_service.py` | Analysis job lifecycle (566 LOC) |
| `data_providers/` | package | `python_service/app/services/data_providers/` | Market data sources (AkShare, yfinance) |

## CONVENTIONS (Project-Specific)

- **API response shape**: `{ success: boolean, data?: any, error?: string, code?: string }` — Node checks `success` before using `data`
- **Market type**: Always `"A-Share" | "HK-Share" | "US-Share"` (never plain strings)
- **A-Share validation**: 6-digit codes; STAR (`68xxxx`) and ChiNext (`30xxxx`) have ±20% limit, others ±10%
- **StockInfo.lastUpdated**: Must include `"CST"` — validated in `validateStockInfo()`
- **All types in `src/types.ts`** (canonical) — except `src/types/` dir is a half-finished migration
- **Zustand stores**: Domain-scoped, never shared between domains (one store = one concern)
- **Components**: Lazy-loaded via `React.lazy()` in `App.tsx` for any non-trivial component
- **i18n**: Default `zh-CN`; English in `src/i18n/locales/en.json`; UI strings only
- **Analysis levels**: `quick` | `standard` | `deep` — configure fields populated, token estimates, latency
- **Python tests**: Run from project root with `PYTHONPATH` set; conftest handles `API_TOKEN` poisoning from `load_dotenv`
- **Test placement**: TypeScript in `__tests__/` next to source; Python in `python_service/tests/`
- **No formatter**: Only `tsc --noEmit` — no ESLint, Prettier, Biome, ruff, or black

## ANTI-PATTERNS (THIS PROJECT)

- **Dual type system**: `src/types.ts` AND `src/types/` co-exist — one is stale; do NOT add to both
- **Oversized modules**: Do not add to files >250 LOC without splitting first (see `stockRoutes.ts` 1261 LOC, `llm_gateway.py` 658 LOC, `discussion_service.py` 810 LOC)
- **Bare `except:` in Python**: 17+ occurrences — always log the exception; never silence
- **`print()` over logging**: 200+ occurrences in Python, 60+ `console.log` in Node — use proper logging for any new code
- **`as any`**: 214+ locations — avoid in new code; use proper types
- **Scratch debris**: `python_service/scratch/` is for ad-hoc scripts — never commit debug scripts to root or src/
- **Express + FastAPI route overlap**: Some routes handled by BOTH Express and proxied to FastAPI — verify which layer owns the route before adding
- **Docker vs Dockerless**: Two deployment paths (docker-compose and start-alsa.sh) — can drift independently

## UNIQUE STYLES

- **Package name is `"react-example"`** — known bug, NOT the project name
- **Chinese/English bilingual** throughout codebase, docs, and prompts
- **AI agent workspace**: `.claude/`, `.omo/`, `.mimocode/`, `.codegraph/`, `skills/`, `dev.md` — all AI/agent development artifacts
- **Async background loops** in main.py: precompute (5min), signal monitor (60s), API key cleanup (5min), prediction accuracy (3600s)
- **Data lake**: Hive-style Parquet partitioning at `python_service/data/lake/ohlc/market={market}/year={year}/symbol={symbol}/`
- **Two Python venvs**: `python_service/.venv/` (3.11) + `.venv_qlib/` (3.9 for Qlib Cython compat)

## COMMANDS

```bash
npm run dev:no-ibkr    # Express + Vite (no Interactive Brokers)
npm run dev:py         # FastAPI dev server (port 8001)
npm run build          # vite build → dist/
npm run lint           # tsc --noEmit (ONLY quality gate)
npm test               # vitest run
npm run test:all       # vitest + pytest python_service/tests/
npm run audit:repo     # Repo hygiene check (forbids data/ .db .log .env in git)
npm run dev            # Full stack w/ IBKR gateway

# Python tests standalone:
PYTHONPATH=/abs/path/to/python_service python_service/.venv/bin/pytest python_service/tests/
```

## NOTES

- **No ESLint/Prettier/Biome**: Only `tsc --noEmit` for TypeScript quality; Python has no linter config (orphaned `.ruff_cache/` but no `ruff.toml`)
- **CI is minimal**: Single workflow, 4 jobs, no deploy/release pipeline — only runs on push/PR to main/develop
- **Docker Compose includes Postgres+Redis** but dev mode uses SQLite + Redis through Celery
- **`.env.runtime` files** hold API keys; `python_service/.env.runtime` has 30+ stale `ADMIN_TOKEN` values
- **`load_dotenv` at import time** in `llm_gateway.py` and `brain_manager.py` — can overwrite env vars set by test fixtures
