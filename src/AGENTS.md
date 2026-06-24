# FRONTEND — React SPA

## OVERVIEW

React 19 SPA with Vite 6, Zustand state management, and a multi-agent AI discussion system. Two build targets: dev (Vite dev server at :5173 with `/api` proxy to :3000) and production (Express serves built SPA from `dist/`).

## STRUCTURE

```
src/
├── components/       # UI components (30+ files)
│   ├── analysis/     #   StockHeroCard, AnalysisResult, ScorePanel, ChatSection, etc.
│   ├── dashboard/    #   MarketOverview, MockTradingDashboard, SignalCenter, etc.
│   ├── admin/        #   AdminPanel, SystemMonitor, PipelineManager
│   ├── layout/       #   Header, MobileNav, ResponsiveContainer
│   ├── shared/       #   StockSearchInput, DetailModal, Toast, ConfirmDialog
│   ├── auth/         #   LoginPage, RegisterPage, AuthGuard
│   ├── App.tsx       #   Root component with React.lazy() for all views
│   └── __tests__/    #   Component tests
├── hooks/            # Business logic hooks (9 files)
├── stores/           # Zustand state stores (11 files)
├── services/         # API clients + AI analysis (42 files)
│   ├── discussion/   #   Multi-agent orchestrator, roles, prompts
│   ├── api/          #   API client wrappers
│   └── __tests__/    #   22+ service tests
├── types.ts          # Canonical types (735 LOC — monolithic)
├── types/            # DUPLICATE split types (half-migrated refactor)
├── i18n/             # en/zh-CN locales
├── test/             # Cross-cutting audit/hygiene tests
└── main.tsx          # React entry point
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Add new view/component | `src/components/` + `React.lazy()` in `App.tsx` |
| New state store | `src/stores/useXStore.ts` (Zustand pattern) |
| New analysis hook | `src/hooks/useX.ts` |
| API client method | `src/services/api/xClient.ts` |
| Discussion agent role | `src/services/discussion/prompts/roles/` |
| i18n strings | `src/i18n/locales/{en,zh}.json` |
| Types | `src/types.ts` (canonical) — NOT `src/types/` |
| Component test | `src/components/X/__tests__/X.test.tsx` |
| Service test | `src/services/__tests__/x.test.ts` |
| Express server test | `server/__tests__/x.test.ts` |

## CONVENTIONS

- **All types in `src/types.ts`** — not `src/types/` (that's a stale migration)
- **Stores**: Zustand, one per domain, independent stores never reference each other
- **Components**: `React.lazy()` for any non-trivial component; no barrel `index.ts`
- **Hooks**: Contain all business logic; `App.tsx` only wires hooks to components
- **API calls**: Through `src/services/api/xClient.ts` wrappers, not raw fetch
- **Types**: All API responses follow `{ success, data?, error?, code? }`
- **Analysis levels**: `quick` | `standard` | `deep` — configurable in `analysisLevelConfig.ts`
- **Tests**: Vitest with `globals: true`, `jsdom` env, `@testing-library/react`

## ANTI-PATTERNS

- **No `as any`** — 214+ existing violations; never add new ones
- **No `console.log` in production** — 61+ existing violations; use structured approach
- **No `@ts-ignore` / `@ts-expect-error`** — existing in `ibkrClient.ts` and stockRoutes tests
- **No barrel imports** — components import directly from file paths
- **No ESLint/Prettier** — only `tsc --noEmit` catches errors; format manually
