# BACKEND — FastAPI + Celery

## OVERVIEW

FastAPI backend (port 8001) with SQLite/PostgreSQL, Celery async task queue, DuckDB + Parquet data lake, LanceDB vector store, and 50+ service modules. The largest module in the project at 325 files.

## STRUCTURE

```
python_service/
├── app/
│   ├── api/               # 26 route files (aggregated by router.py)
│   ├── services/          # 50+ services (analysis, market, trading, LLM, etc.)
│   │   ├── data_providers/ #   AkShare, yfinance, iwencai data sources
│   │   └── tools/         #   AI tool registry (iwencai, search)
│   ├── db/                # SQLModel ORM, SQLite (dev) / Postgres (Docker)
│   │   └── repositories/  # 7 data access layers
│   ├── backtest/          # Event-driven backtest engine
│   ├── decision/          # Trading decision court + field validation
│   ├── quant/             # Polars indicators, risk metrics, valuation
│   ├── risk/              # Kill switch + pre-trade risk gate
│   ├── lake/              # DuckDB engine on partitioned Parquet
│   ├── vector/            # LanceDB vector embeddings store
│   ├── prompting/         # Prompt version registry + runtime
│   ├── observability/     # Metrics + audit logging
│   ├── evaluation/        # Model evaluation
│   ├── reconciliation/    # Trade reconciliation engine
│   ├── worker.py          # Celery app: alsa_worker
│   ├── security.py        # Auth + rate limiting
│   └── logging.py         # Structured logging setup
├── tests/                 # 62 pytest files (the OFFICIAL test suite)
├── paper_trading_system/  # Qlib-based simulation (Python 3.9)
├── scratch/               # ~50 ad-hoc debug scripts (NOT production)
├── cli.py                 # Click CLI tool: alsacli
├── main.py                # FastAPI entry
└── pyproject.toml         # Dependencies
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
| New API endpoint | `app/api/x.py` + register in `router.py` |
| New business logic | `app/services/x_service.py` |
| Data source adapter | `app/services/data_providers/` |
| Database access | `app/db/repositories/` |
| New DB table | `app/db/models.py` (SQLModel) |
| Backtest logic | `app/backtest/` |
| Prompt versioning | `app/prompting/` |
| Celery task | `app/worker.py` |
| CLI command | `cli.py` (Click) |
| Python tests | `tests/test_x.py` (61 files) |

## CONVENTIONS

- **API response shape**: `{ success: boolean, data?: any, error?: string, code?: string }`
- **SQLModel ORM**: All database models in `app/db/models.py`
- **Route registration**: Add new routes to `app/api/x.py`, then register in `app/api/router.py`
- **Service pattern**: Business logic in `app/services/`, route handlers are thin wrappers
- **Celery tasks**: Defined in `app/worker.py`; uses Redis broker
- **Async loops**: Background loops in `main.py` (precompute 5min, signal 60s, cleanup 5min)
- **Testing**: pytest with `conftest.py` handling DB setup, `api_token` poisoning, and table cleanup
- **`load_dotenv` side effect**: `llm_gateway.py` and `brain_manager.py` call `load_dotenv('.env.runtime')` at import time — this can overwrite env vars

## ANTI-PATTERNS

- **No bare `except:`** — 17+ existing violations; always log the exception
- **No `print()` over logging** — 200+ existing violations; use `structlog`/standard logging
- **No files >250 LOC** — existing violations: `discussion_service.py` (810), `llm_gateway.py` (658), `analysis_job_service.py` (566), `report_generator_service.py` (3185)
- **No `as any` equivalent** — use Pydantic models, not raw dicts
- **Scratch scripts** are in `scratch/` — never commit debug/test scripts elsewhere
- **Dual-entry confusion**: `main.py` (FastAPI) and `cli.py` (CLI) share the same service classes but are separate entry points — test both
