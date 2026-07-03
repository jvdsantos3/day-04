# React Frontend Tasks

**Spec**: `.specs/features/react-frontend/spec.md`
**Design**: `.specs/features/react-frontend/design.md`
**Status**: Ready for Execute

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec — confirm before Execute. Guidelines found: `pytest` via `pyproject.toml` (backend), strong defaults for new frontend layer.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| API auth routes | integration | All endpoints: happy + AUTH-04 generic error + validation 400 | `tests/integration/test_api_auth.py` | `pytest tests/integration/test_api_auth.py -q` |
| API dashboard routes | integration | Summary + transactions; filtros; 401 sem cookie; categoria inválida 400 | `tests/integration/test_api_dashboard.py` | `pytest tests/integration/test_api_dashboard.py -q` |
| React components (auth forms) | unit (Vitest) | Submit válido/inválido; mensagens de erro exibidas | `frontend/src/**/*.test.tsx` | `cd frontend && npm run test` |
| React hooks (useChat SSE) | unit (Vitest) | Parse SSE event; append messages; error state | `frontend/src/hooks/*.test.ts` | `cd frontend && npm run test` |
| E2E smoke (optional P2) | e2e | Login → dashboard render — manual ou Playwright futuro | — | manual |

**Gate (full suite):** `pytest -q` (backend) + `cd frontend && npm run test && npm run build`

**Parallelism assessment:** API integration tests usam DB isolada por fixture existente — `[P]` seguro entre arquivos de teste distintos. Frontend Vitest é `[P]` por padrão. Tasks de implementação backend antes de frontend são sequenciais por fase.

---

## Requirement → Task Map

| Requirement ID | Task(s) |
| -------------- | ------- |
| AUTH-API-01 | T1 |
| AUTH-API-02 | T1 |
| AUTH-API-03 | T2 |
| AUTH-API-04 | T1, T14 |
| API-DASH-01 | T3 |
| API-DASH-02 | T4 |
| CORS-01 | T5 |
| UI-AUTH-01 | T9 |
| UI-AUTH-02 | T10 |
| UI-AUTH-03 | T11 |
| UI-DASH-01 | T12 |
| UI-DASH-02 | T13 |
| UI-DASH-03 | T13 |
| UI-CHAT-01 | T15 |
| UI-CHAT-02 | T15 |
| UI-CHAT-03 | T15 |
| UI-SHELL-01 | T8 |
| UI-SHELL-02 | T8 |
| DEPLOY-01 | T17, T18 |
| UI-A11Y-01 | T19 |
| UI-A11Y-02 | T19 |
| UI-FMT-01 | T12, T13 |

---

## Phase 1: Backend JSON API

### T1 — JSON auth endpoints (AUTH-API-01, AUTH-API-02, AUTH-API-04) — DONE (a524462)

**Scope:** `src/financial_assistant/api/auth_router.py`, `schemas.py`

- `POST /api/auth/register` — JSON body, 201 + cookie, 400 duplicate/short password
- `POST /api/auth/login` — JSON body, 200 + cookie, 401 generic message
- `POST /api/auth/logout` — 200, clear cookie

**Verify:** `pytest tests/integration/test_api_auth.py -q` (criar nesta task)

**Depends on:** none

---

### T2 — GET /api/auth/me (AUTH-API-03) — DONE (18e72c2)

**Scope:** `auth_router.py`

- Retorna `{id, name, email}` para cookie válido
- 401 sem cookie

**Verify:** testes em `test_api_auth.py`

**Depends on:** T1

---

### T3 — GET /api/dashboard/summary (API-DASH-01) — DONE (c99e45c)

**Scope:** `api/dashboard_router.py`

- Query `month` (default: mês atual `YYYY-MM`)
- JSON com income, expense, warning, categories com labels PT-BR

**Verify:** `pytest tests/integration/test_api_dashboard.py -q`

**Depends on:** T1

---

### T4 — GET /api/transactions (API-DASH-02) — DONE (a4024ee)

**Scope:** `dashboard_router.py`

- Query `month`, `category` (opcional)
- 400 categoria inválida

**Verify:** testes em `test_api_dashboard.py`

**Depends on:** T3

---

### T5 — CORS + mount API router (CORS-01) — DONE (5db7d0c)

**Scope:** `main.py`, `api/router.py`

- `CORSMiddleware` para `http://localhost:5173`, `allow_credentials=True`
- Registrar `api_router` prefix `/api`

**Verify:** `pytest -q` (suíte completa ainda passa)

**Depends on:** T1–T4

---

## Phase 2: Frontend Scaffold

### T6 — Vite + React + TypeScript project — DONE (9ade410)

**Scope:** `frontend/` directory

- `npm create vite@latest` (react-ts template)
- ESLint básico, path alias `@/`

**Verify:** `cd frontend && npm run build`

**Depends on:** none `[P]` com Phase 1

---

### T7 — Tailwind CSS + design tokens — DONE (b15bd58)

**Scope:** `frontend/tailwind.config.ts`, `src/index.css`

- Paleta financeira (verde receita, vermelho despesa, neutros)
- Tipografia system-ui

**Verify:** `npm run build`

**Depends on:** T6

---

### T8 — App shell + React Router (UI-SHELL-01, UI-SHELL-02) — DONE (c9aea0b)

**Scope:** `App.tsx`, `layouts/AppLayout.tsx`, `lib/api.ts`

- Rotas: `/`, `/login`, `/register`, `/dashboard`, `/chat`
- `api.ts` com `credentials: 'include'`
- Redirect `/` → `/dashboard` ou `/login`

**Verify:** `npm run build`

**Depends on:** T7

---

## Phase 3: Auth UI

### T9 — Login page (UI-AUTH-01) — DONE (5751965)

**Scope:** `pages/Login.tsx`

- Form email/password, loading state, error inline

**Verify:** Vitest `Login.test.tsx`

**Depends on:** T8, T5

---

### T10 — Register page (UI-AUTH-02) — DONE (eb6e163)

**Scope:** `pages/Register.tsx`

- Form name/email/password, validação client ≥8 chars

**Verify:** Vitest `Register.test.tsx`

**Depends on:** T8, T5

---

### T11 — Auth guard + useAuth hook (UI-AUTH-03)

**Scope:** `hooks/useAuth.ts`, `components/ProtectedRoute.tsx`

- `GET /api/auth/me` on mount
- 401 → redirect `/login`
- Logout chama `POST /api/auth/logout`

**Verify:** Vitest `useAuth.test.ts`

**Depends on:** T9, T10

---

## Phase 4: Dashboard UI

### T12 — Dashboard summary cards (UI-DASH-01, UI-FMT-01)

**Scope:** `pages/Dashboard.tsx`, `components/CategoryCard.tsx`, `components/Money.tsx`

- TanStack Query `useQuery(['summary', month])`
- Cards com progress bar, alerta visual
- Warning banner quando sem receita

**Verify:** Vitest `CategoryCard.test.tsx`

**Depends on:** T11, T3

---

### T13 — Transaction filters + table (UI-DASH-02, UI-DASH-03)

**Scope:** `components/TransactionFilters.tsx`, `TransactionTable.tsx`

- Filtros mês + categoria refetch sem full reload
- Empty state

**Verify:** Vitest `TransactionTable.test.tsx`

**Depends on:** T12, T4

---

## Phase 5: Chat UI

### T15 — Chat page with SSE (UI-CHAT-01, UI-CHAT-02, UI-CHAT-03)

**Scope:** `pages/Chat.tsx`, `hooks/useChat.ts`

- `session_id` em `sessionStorage`
- SSE via fetch stream ou `@microsoft/fetch-event-source`
- Typing indicator, sources metadata, timeout 120s

**Verify:** Vitest `useChat.test.ts` (mock stream)

**Depends on:** T11

---

## Phase 6: Integration & Cleanup

### T17 — FastAPI static mount + SPA fallback (DEPLOY-01)

**Scope:** `main.py`

- `StaticFiles` em `frontend/dist`
- Fallback `index.html` para rotas não-API

**Verify:** `npm run build && uvicorn ...` → `http://localhost:8000/dashboard` carrega SPA

**Depends on:** T13, T15

---

### T18 — Remove Jinja2 HTML routes

**Scope:** Remover templates e rotas HTML de `auth/router.py`, `web/router.py`, `chat/router.py` GET `/chat`

- Manter apenas lógica movida para `/api/*`
- Deletar `web/templates/` (exceto se referenciado em testes — atualizar testes)

**Verify:** `pytest -q` + smoke manual login/dashboard/chat

**Depends on:** T17

---

## Phase 7: Polish (P2)

### T19 — Acessibilidade + formatação BRL (UI-A11Y-01, UI-A11Y-02, UI-FMT-01)

**Scope:** componentes existentes

- `aria-describedby` em erros
- Focus rings visíveis
- `Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })`

**Verify:** Vitest + inspeção manual Tab navigation

**Depends on:** T18

---

## Parallelization Guide

```
Phase 1 (T1→T5): sequencial — API base
Phase 2 (T6→T8): [P] com Phase 1 após T1
Phase 3 (T9,T10 [P] → T11)
Phase 4 (T12 → T13)
Phase 5 (T15 [P] com Phase 4 após T11)
Phase 6 (T17 → T18)
Phase 7 (T19) — opcional P2
```

**MVP cutoff:** T1–T18 (P1 completo)
**Total tasks:** 19 (T14 número reservado para AUTH-API-04 coberto em T1/T14 — renumerar: skip T14 gap, use T1 for AUTH-API-04)

---

## Execute Prompts (resumo por wave)

| Wave | Tasks | Prompt seed |
| ---- | ----- | ----------- |
| W1 | T1, T2 | "Implement JSON auth API per design.md contracts" |
| W2 | T3, T4, T5 | "Dashboard JSON API + CORS + router mount" |
| W3 | T6, T7, T8 | "Scaffold Vite React TS + Tailwind + Router shell" |
| W4 | T9, T10, T11 | "Auth pages + guard hook" |
| W5 | T12, T13 | "Dashboard page with cards and transaction table" |
| W6 | T15 | "Chat page SSE client" |
| W7 | T17, T18 | "Static mount + remove Jinja routes" |
| W8 | T19 | "A11y polish P2" |
