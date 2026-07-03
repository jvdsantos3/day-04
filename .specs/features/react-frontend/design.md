# React Frontend Design

**Spec**: `.specs/features/react-frontend/spec.md`
**Status**: Draft

---

## Architecture Overview

Migração de **server-rendered HTML (Jinja2+HTMX)** para **SPA React** consumindo APIs JSON no mesmo FastAPI. A lógica de domínio, agentes LangGraph, MCPs e persistência permanecem inalteradas.

```
┌─────────────────────────────────────────────────────────────┐
│  Browser                                                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  React SPA (Vite build → /frontend/dist)            │    │
│  │  React Router │ TanStack Query │ Tailwind           │    │
│  └──────────────────────┬──────────────────────────────┘    │
└─────────────────────────┼───────────────────────────────────┘
                          │ credentials: include (cookie JWT)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI (:8000)                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ /api/auth/*  │  │ /api/dashboard│  │ POST /api/chat   │   │
│  │ JSON + cookie│  │ /api/trans... │  │ SSE (existente)  │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
│         └─────────────────┴───────────────────┘              │
│                           │                                   │
│              Domain services, repos, agents (inalterados)     │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ StaticFiles("/") → frontend/dist + SPA index fallback │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Approach Comparison

| Approach | Pros | Cons | Verdict |
| -------- | ---- | ---- | ------- |
| **A: SPA + JSON API no mesmo FastAPI** (recomendado) | Um deploy, cookie same-origin, reutiliza auth | Novos endpoints JSON | ✅ Escolhido |
| B: SPA separada (porta 5173 prod) | Dev isolado | CORS + cookie cross-origin complexo | ❌ |
| C: Next.js SSR | SEO melhor | Overkill para app autenticado; stack mista | ❌ |

**AD-001 superseded:** AD-005 registra React como camada web; FastAPI permanece servidor único.

---

## Risks & Concerns

| Concern | Mitigation |
| ------- | ---------- |
| Auth atual é form POST + redirect HTML | Novos endpoints `/api/auth/*` retornam JSON + `Set-Cookie`; testes de integração |
| Duplicação Jinja + React durante migração | Remover rotas HTML na última task após paridade |
| SSE com `fetch` não suporta stream nativo em todos browsers | Usar `fetch` + `ReadableStream` ou `@microsoft/fetch-event-source` |
| CORS em dev (Vite :5173 → API :8000) | `CORSMiddleware` com `allow_credentials=True`, origins `http://localhost:5173` |
| Cookie `SameSite=Lax` em dev cross-port | Vite proxy `/api` → `:8000` evita cross-origin em dev |

---

## Components

### Backend — `src/financial_assistant/api/`

| Component | Purpose | Interfaces |
| --------- | ------- | ---------- |
| `auth_router.py` | JSON auth (AUTH-API-01..04) | `POST /api/auth/register`, `login`, `logout`; `GET /api/auth/me` |
| `dashboard_router.py` | Dashboard data (API-DASH-01..02) | `GET /api/dashboard/summary?month=`, `GET /api/transactions?month=&category=` |
| `schemas.py` | Pydantic response models | `UserOut`, `DashboardSummaryOut`, `TransactionOut`, `AuthError` |

**Reuses:** `auth.service`, `get_current_user_api`, `BudgetService`, `TransactionRepository`, `CATEGORY_LABELS` logic from `web/router.py`.

### Frontend — `frontend/`

| Component | Path | Purpose |
| --------- | ---- | ------- |
| App shell | `src/App.tsx`, `src/layouts/AppLayout.tsx` | Router, nav, auth guard |
| Auth pages | `src/pages/Login.tsx`, `Register.tsx` | Forms (UI-AUTH-01..03) |
| Dashboard | `src/pages/Dashboard.tsx` | Cards + filters (UI-DASH-01..03) |
| Chat | `src/pages/Chat.tsx` | SSE client (UI-CHAT-01..03) |
| API client | `src/lib/api.ts` | `fetch` wrapper com `credentials: 'include'` |
| Hooks | `src/hooks/useAuth.ts`, `useChat.ts` | Session state, SSE stream |
| Types | `src/types/api.ts` | Mirrors Pydantic schemas |

### Static serving — `main.py`

```python
# Prod: mount StaticFiles from frontend/dist
# SPA fallback: unmatched GET → index.html (exceto /api/*)
```

---

## API Contracts

### `POST /api/auth/register`

```json
// Request
{ "name": "João", "email": "a@b.com", "password": "senha123" }

// 201 Response
{ "user": { "id": "...", "name": "João", "email": "a@b.com" } }
// + Set-Cookie: session=...

// 400 Response
{ "detail": "Email já cadastrado" }
```

### `POST /api/auth/login`

```json
// Request
{ "email": "a@b.com", "password": "senha123" }

// 200 + Set-Cookie
{ "user": { "id": "...", "name": "João", "email": "a@b.com" } }

// 401
{ "detail": "Email ou senha inválidos" }
```

### `POST /api/auth/logout`

```json
// 200 — clears cookie
{ "ok": true }
```

### `GET /api/auth/me`

```json
// 200
{ "id": "...", "name": "João", "email": "a@b.com" }

// 401 — no/invalid cookie
```

### `GET /api/dashboard/summary?month=2026-07`

```json
{
  "month": "2026-07",
  "total_income": "5000.00",
  "total_expense": "3200.00",
  "warning": null,
  "categories": [
    {
      "category": "custos_fixos",
      "label": "Custos Fixos",
      "spent": "2000.00",
      "pct": 40.0,
      "min_pct": 50,
      "max_pct": 60,
      "status": "alerta"
    }
  ]
}
```

### `GET /api/transactions?month=2026-07&category=custos_fixos`

```json
{
  "transactions": [
    {
      "id": "...",
      "date": "2026-07-15",
      "description": "Aluguel",
      "amount": "-1500.00",
      "type": "despesa",
      "category": "custos_fixos"
    }
  ]
}
```

### `POST /api/chat` (existente)

Inalterado — SSE com `AgentResponse` JSON + `event: done`.

---

## Data Models (TypeScript)

```typescript
interface User {
  id: string;
  name: string;
  email: string;
}

interface CategoryBudget {
  category: string;
  label: string;
  spent: string;
  pct: number;
  min_pct: number;
  max_pct: number;
  status: "ok" | "alerta";
}

interface DashboardSummary {
  month: string;
  total_income: string;
  total_expense: string;
  warning: string | null;
  categories: CategoryBudget[];
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: { collection: string; doc_id: string }[];
  pending?: boolean;
}
```

---

## Dev Workflow

```bash
# Terminal 1 — backend
uvicorn financial_assistant.main:app --reload --port 8000

# Terminal 2 — frontend (proxy /api → :8000)
cd frontend && npm run dev
```

`frontend/vite.config.ts`:
```typescript
server: {
  proxy: { '/api': 'http://localhost:8000' }
}
```

---

## File Structure

```
frontend/
├── package.json
├── vite.config.ts
├── tailwind.config.ts
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css
│   ├── lib/api.ts
│   ├── hooks/
│   ├── pages/
│   ├── components/
│   └── types/
└── dist/          # gitignored, build output

src/financial_assistant/
├── api/
│   ├── __init__.py
│   ├── router.py      # aggregates /api/*
│   ├── auth_router.py
│   ├── dashboard_router.py
│   └── schemas.py
└── main.py            # + StaticFiles mount, remove Jinja routers
```

---

## Migration Plan

1. Adicionar API JSON (sem remover HTML ainda) — testes passam
2. Scaffold React + auth pages
3. Dashboard + chat
4. Mount static + remover rotas Jinja (`auth/router.py` HTML, `web/router.py`, `chat/router.py` GET `/chat`)
5. Atualizar README com instruções dev/prod
