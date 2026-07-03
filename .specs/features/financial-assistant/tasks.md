# Assistente Financeiro — Tasks

**Spec**: `.specs/features/financial-assistant/spec.md`
**Design**: `.specs/features/financial-assistant/design.md`
**Status**: Ready for Execute

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec — confirm before Execute. Guidelines found: none — strong defaults applied.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Domain / services | unit | All branches; 1:1 to spec ACs; all listed edge cases | `tests/unit/**/*.py` | `rtk pytest tests/unit -m unit` |
| Auth | integration | Register/login/logout/isolation happy + error paths | `tests/integration/test_auth.py` | `rtk pytest tests/integration/test_auth.py` |
| Agents / routing | integration | 3 cenários conversacionais literais + validator reject | `tests/integration/test_conversation_scenarios.py` | `rtk pytest tests/integration -m integration` |
| MCP servers | integration | Tool invoke + user_id isolation | `tests/integration/test_mcp.py` | `rtk pytest tests/integration/test_mcp.py` |
| Web / dashboard | integration | Dashboard render + HTMX filters + auth guard | `tests/integration/test_dashboard.py` | `rtk pytest tests/integration/test_dashboard.py` |
| Vector / indexer | unit | Write-through + delete sync + user_id filter + ChromaDB fallback | `tests/unit/test_indexer.py`, `tests/integration/test_mcp.py` | `rtk pytest tests/unit/test_indexer.py` |
| LLM-dependent flows | integration (optional) | Real DeepSeek — manual/CI nightly | `tests/integration/test_conversation_scenarios.py` | `rtk pytest -m llm` |

**Gate command (all P1):** `rtk pytest tests/ -m "unit or integration" --tb=short`

**Parallelism:** Tests use per-test SQLite `:memory:` + ChromaDB temp dir namespaced by `test_id` → `[P]` parallel-safe.

---

## Phase 1 — Foundation

### T1: Project scaffold [P] ✅ done (`a3b0e1d`)
- **Requirement**: infra
- **Action**: Criar `pyproject.toml`, estrutura `src/`, `.env.example`, `pytest.ini` com markers
- **Verify**: `pip install -e ".[dev]"` succeeds
- **Commit**: `chore: scaffold project structure`

### T2: Config module ✅ done
- **Requirement**: infra
- **Action**: `config.py` com pydantic-settings (DATABASE_URL, CHROMA_PATH, JWT_SECRET, DEEPSEEK_API_KEY)
- **Verify**: `tests/unit/test_config.py` — loads from env
- **Commit**: `feat: add application settings`

### T3: SQLAlchemy models + Alembic init ✅ done (`6dfd2eb`)
- **Requirement**: AUTH-01, CHAT-01, CHAT-02
- **Action**: Models User, Transaction (`category` nullable — NULL para receitas), BudgetTarget, ChatSession, ChatMessage
- **Verify**: Migration applies; tables exist
- **Commit**: `feat: add database models and migrations`

### T4: Budget category enum + defaults seed ✅ done
- **Requirement**: BUD-01, CONV-01
- **Action**: `BudgetCategory` enum + função `seed_budget_targets(user_id)` — defaults somam 90% (margem intencional)
- **Verify**: `tests/unit/test_budget_defaults.py` — 5 categories with correct ranges; sum of target_pct == 90
- **Commit**: `feat: add budget categories and default targets`

---

## Phase 2 — Auth

### T5: Password hashing utility ✅ done (`db36fd6`)
- **Requirement**: AUTH-01
- **Action**: bcrypt hash/verify in `auth/service.py`
- **Verify**: `tests/unit/test_auth_service.py`
- **Commit**: `feat: add password hashing`

### T6: Register endpoint + template ✅ done (`4905641`)
- **Requirement**: AUTH-01, AUTH-02
- **Action**: `POST /register`, `GET /register`, validation min 8 chars, duplicate email
- **Verify**: `tests/integration/test_auth.py::test_register_success`
- **Commit**: `feat: add user registration`

### T7: Login/logout + JWT cookie ✅ done (`2cc27e9`)
- **Requirement**: AUTH-03, AUTH-04, AUTH-05
- **Action**: `POST /login`, `POST /logout`, httpOnly cookie, redirect dashboard
- **Verify**: `test_login_success`, `test_login_invalid`, `test_protected_route_redirect`
- **Commit**: `feat: add login and session management`

### T8: Auth dependency get_current_user ✅ done
- **Requirement**: AUTH-06
- **Action**: FastAPI dependency injeta `User` em rotas protegidas
- **Verify**: `test_user_isolation_in_repository`
- **Commit**: `feat: add auth dependency for route protection`

---

## Phase 3 — Domain Services

### T9: TransactionRepository ✅ done (`344a5f1`)
- **Requirement**: CHAT-01, TBL-01, VEC-05
- **Action**: CRUD filtrado por user_id + month + category; `search_by_description(user_id, query)` via SQL LIKE para fallback semântico
- **Verify**: `tests/unit/test_transaction_repository.py`
- **Commit**: `feat: add transaction repository`

### T10: BudgetService ✅ done (`f7b1878`)
- **Requirement**: BUD-01, BUD-02, BUD-03, CONV-03
- **Action**: `get_summary(user_id, month)` → % por categoria, status ok/alerta, margem
- **Verify**: `tests/unit/test_budget_service.py` — fixture desbalanceada
- **Commit**: `feat: add budget summary service`

### T11: Pydantic contracts ✅ done (`49e9925`, fix `1b06036`)
- **Requirement**: VAL-01, VAL-02, CHAT-02
- **Action**: `TransactionCreate` (category obrigatório para despesa, proibido para receita), `BudgetSummary`, `AgentResponse`, `IntentClassification`
- **Verify**: `tests/unit/test_contracts.py`
- **Commit**: `feat: add pydantic contracts`

---

## Phase 4 — Vector Store

### T12: ChromaDB client setup ✅ done
- **Requirement**: VEC-01
- **Action**: Persistent client, 5 collections: `transactions`, `chat_memory`, `knowledge_base`, `category_examples`, `working_memory`
- **Verify**: `tests/unit/test_chroma_client.py`
- **Commit**: `feat: add chromadb client`

### T13: Embedding model loader ✅ done (`8572145`)
- **Requirement**: VEC-01
- **Action**: HuggingFaceEmbeddings multilingual-e5-small singleton
- **Verify**: embedding dimension == 384
- **Commit**: `feat: add local embedding model`

### T14: Indexer write-through ✅ done (`8b1c324`)
- **Requirement**: VEC-01, VEC-04
- **Action**: index/delete transaction embeddings with user_id
- **Verify**: `tests/unit/test_indexer.py`
- **Commit**: `feat: add write-through vector indexer`

### T15: Knowledge base + category examples seed ✅ done
- **Requirement**: CONV-01, VEC-03
- **Action**: Indexar docs das 5 categorias + faixas + exemplos em `knowledge_base`; seed inicial de descrições rotuladas em `category_examples`
- **Verify**: `query_knowledge("custos fixos")` returns relevant doc; `find_similar_transactions("mercado")` returns category match
- **Commit**: `feat: seed budget knowledge base`

---

## Phase 5 — MCP Servers

### T16: finance-mcp server ✅ done
- **Requirement**: MCP-01, MCP-02, MCP-04
- **Action**: MCP server exposing transaction + budget tools with user_id param
- **Verify**: `tests/integration/test_mcp.py::test_finance_create_transaction`
- **Commit**: `feat: add finance-mcp server`

### T17: chroma-mcp server ✅ done
- **Requirement**: MCP-01, VEC-02, VEC-03, VEC-05
- **Action**: MCP server for `search_transactions`, `find_similar_transactions`, `query_knowledge`, `get_chat_context`, `save_working_memory`; fallback to `TransactionRepository.search_by_description` when ChromaDB down
- **Verify**: `tests/integration/test_mcp.py::test_chroma_search_isolation`, `test_chroma_fallback_sqlite_like`
- **Commit**: `feat: add chroma-mcp server`

### T18: MCP client adapter + fallback ✅ done
- **Requirement**: MCP-03
- **Action**: MultiServerMCPClient wrapper with in-process fallback
- **Verify**: `test_mcp_fallback_on_failure`
- **Commit**: `feat: add mcp client with fallback`

---

## Phase 6 — Agents

### T19: AgentState + graph skeleton ✅ done
- **Requirement**: ORCH-01
- **Action**: StateGraph with nodes: orchestrator, validator; edges defined
- **Verify**: graph compiles without error
- **Commit**: `feat: add langgraph skeleton`

### T20: Orchestrator intent classification
- **Requirement**: ORCH-01, ORCH-02, CONV-01/02/03
- **Action**: Structured output routing; pattern map for 3 real scenarios
- **Verify**: `tests/unit/test_orchestrator_routing.py` — mock LLM returns intents
- **Commit**: `feat: add orchestrator intent routing`

### T21: Specialist — Atendimento ✅ done
- **Requirement**: CONV-01
- **Action**: System prompt + query_knowledge tool; explains 5 categories
- **Verify**: mock test — response contains all category names
- **Commit**: `feat: add atendimento specialist`

### T22: Specialist — Transações ✅ done (`2644173`)
- **Requirement**: CHAT-01/02/03, CONV-02
- **Action**: CRUD tools; categorize without auto-register on question
- **Verify**: `test_categorize_delivery_is_prazeres`
- **Commit**: `feat: add transacoes specialist`

### T23: Specialist — Orçamento ✅ done (`53146fe`)
- **Requirement**: BUD-03, CONV-03, CONV-04
- **Action**: get_budget_summary tool; prioritized advice; orientar registro de receita quando base = zero
- **Verify**: `test_budget_advice_over_budget_categories`
- **Commit**: `feat: add orcamento specialist`

### T24: Validator node ✅ done
- **Requirement**: VAL-01, VAL-02, VAL-03, CONV-05
- **Action**: Pydantic check + factual balance verification + retry loop
- **Verify**: `tests/unit/test_validator.py` — rejects wrong balance
- **Commit**: `feat: add response validator`

### T25: Wire full graph ✅ done
- **Requirement**: ORCH-01
- **Action**: Connect all specialists; max 2 validation retries
- **Verify**: `tests/integration/test_graph_smoke.py`
- **Commit**: `feat: wire complete agent graph`

---

## Phase 7 — Web UI

### T26: Base templates + static CSS
- **Requirement**: WEB-01
- **Action**: Layout base Jinja2, minimal CSS for dashboard cards
- **Verify**: template renders in test client
- **Commit**: `feat: add base web templates`

### T27: Dashboard page
- **Requirement**: WEB-01, WEB-02, WEB-03
- **Action**: `/dashboard` with transaction table + 5 category bars
- **Verify**: `tests/integration/test_dashboard.py::test_dashboard_shows_percentages`
- **Commit**: `feat: add dashboard page`

### T28: Dashboard HTMX filters
- **Requirement**: WEB-04, TBL-03
- **Action**: `/dashboard/transactions` partial with month/category filters
- **Verify**: `test_dashboard_filter_by_category`
- **Commit**: `feat: add dashboard htmx filters`

### T29: Chat page + SSE endpoint
- **Requirement**: WEB-05, CHAT-01
- **Action**: `/chat` UI + `POST /api/chat` SSE streaming from graph
- **Verify**: `test_chat_endpoint_requires_auth`
- **Commit**: `feat: add chat page with sse streaming`

---

## Phase 8 — Integration Tests (Cenários Reais)

### T30: Conversation scenario — plano de gastos
- **Requirement**: CONV-01
- **Action**: `test_plano_de_gastos_explains_five_categories` — mock LLM or `@pytest.mark.llm`
- **Verify**: response mentions all 5 categories + percentage ranges
- **Commit**: `test: add plano de gastos conversation scenario`

### T31: Conversation scenario — delivery categorization
- **Requirement**: CONV-02
- **Action**: `test_delivery_categorization_prazeres` — asserts category + offer_register
- **Verify**: gate passes
- **Commit**: `test: add delivery categorization scenario`

### T32: Conversation scenario — budget advice
- **Requirement**: CONV-03
- **Action**: `test_economizar_categories_advice` — seeded unbalanced data
- **Verify**: response mentions over-budget categories
- **Commit**: `test: add budget advice conversation scenario`

---

## Dependency Graph

```
T1 → T2 → T3 → T4
         ↓
    T5 → T6 → T7 → T8
         ↓
    T9 → T10 → T11
         ↓
T12 → T13 → T14 → T15
         ↓
T16 → T17 → T18
         ↓
T19 → T20 → T21/T22/T23 → T24 → T25
         ↓
T26 → T27 → T28 → T29
         ↓
T30 → T31 → T32
```

**Parallelizable after T8:** T9-T11 ∥ T12-T15 ∥ T16-T17

---

## Requirement → Task Map

| Requirement | Task(s) |
| ----------- | ------- |
| CHAT-01/02/03 | T3, T9, T22, T29 |
| TBL-01/02/03 | T9, T27, T28 |
| BUD-01/02/03 | T4, T10, T23 |
| ORCH-01/02 | T19, T20, T25 |
| VAL-01/02/03 | T11, T24 |
| VEC-01–05 | T12–T15, T14, T17, T9 |
| MCP-01–04 | T16–T18 |
| AUTH-01–06 | T5–T8 |
| WEB-01–05 | T26–T29 |
| CONV-01–05 | T15, T20–T24, T30–T32 |

---

## Execute Notes

- One atomic commit per task
- Gate must pass before task is done
- LLM tests (T30-T32) use mocked LLM by default; `-m llm` for real DeepSeek
- Verifier runs automatically after T32
