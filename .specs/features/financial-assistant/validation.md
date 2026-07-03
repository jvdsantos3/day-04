# financial-assistant Validation

**Date**: 2026-07-02
**Spec**: `.specs/features/financial-assistant/spec.md`
**Diff range**: repo root (`a3b0e1d`..`43d1c56`, T1–T32, entire `src/`+`tests/` tree)
**Verifier**: independent sub-agent (author ≠ verifier)

---

## Task Completion

All 32 tasks (T1–T32) are marked done in `tasks.md` and correspond to real commits in `git log`. No task is blocked or partial in `tasks.md`'s own bookkeeping. `STATE.md`'s Handoff records 3 real bugs found and fixed via live-testing against the real DeepSeek API after T29 (DeepSeek `response_format` incompatibility, CONV-02 misclassification, Validator over-rejecting Atendimento's illustrative figures) — all three now have regression tests (verified below).

| Task range | Status | Notes |
| ---------- | ------ | ----- |
| T1–T32     | ✅ Done | Matches `git log`; gate passes (below) |

---

## Spec-Anchored Acceptance Criteria

Evidence-or-zero: every row cites `file:line` + the actual assertion. Where spec.md is silent on a precise value, marked ⚠️.

| Requirement | Criterion (spec-defined outcome) | `file:line` — assertion | Result |
| --- | --- | --- | --- |
| CHAT-01 | Expense persisted w/ exact fields | `tests/unit/test_transaction_repository.py:65-85` — `stored.amount == Decimal("150.00")`, `stored.category == PLEASURES` | ✅ PASS |
| CHAT-02 | Income persisted with `category=NULL` | `tests/unit/test_transacoes.py:94-110` — `calls[0]["category"] is None` | ✅ PASS |
| CHAT-03 | Ambiguous amount/category → clarification, no persist | `tests/unit/test_transacoes.py:113-132` — `response.action == "none"`, `calls == []` | ✅ PASS |
| TBL-01 | Table cols: data/descrição/tipo/valor/categoria | `tests/unit/test_transaction_repository.py:189-207` — asserts all 5 fields on returned row | ✅ PASS |
| TBL-02 | No transactions → empty state | `tests/integration/test_dashboard.py:121-137` — `"Nenhuma transação registrada" in response.text` | ✅ PASS |
| TBL-03 | Filter by category/period → matching only | `tests/integration/test_dashboard.py:230-274` — category/month/combined filters each assert exact inclusion/exclusion | ✅ PASS |
| BUD-01 | % computed over month's total income, user-scoped | `tests/unit/test_budget_service.py:117-156` — `pct == pytest.approx(50.0)` etc., cross-user isolation test | ✅ PASS (discrimination-confirmed, sensor #1) |
| BUD-02 | Alert w/ category, %, faixa, excess amount | `tests/unit/test_budget_service.py:162-176` — `status=="alerta"`, `min_pct/max_pct/target_pct`, `over_amount == Decimal("1000")` | ✅ PASS |
| BUD-03 AC1/2 | Summary of 5 categories, gasto/%/faixa/status | `tests/unit/test_budget_service.py:202-205` — `[c.category ...] == list(BudgetCategory)` | ✅ PASS |
| BUD-03 AC3 | "Como está meu orçamento?" → unconditional 5-category summary | — no test, no code path found | ❌ **GAP** — see finding #1 |
| ORCH-01 | One specialist per turn, orchestrator→specialist→validator | `tests/integration/test_graph_smoke.py:92-102` — `budget_advice_intent["n"] == 1`; `src/.../agents/graph.py:64-82` builds exactly this edge set | ✅ PASS (discrimination-confirmed, sensor #2) |
| ORCH-02 | Ambiguous intent → route to Atendimento | `tests/unit/test_orchestrator_routing.py:95-100` tests `specialist_for_intent()` directly; `src/.../agents/graph.py:54-56` `_route_to_specialist` calls `specialist_for_intent(Intent(state["intent"]))` **without confidence**, so it's unreachable end-to-end | ❌ **GAP** (confirmed, not just documented) — see finding #2 |
| VAL-01 | Validator enforces `AgentResponse` contract | `tests/unit/test_validator.py:87-104` — `validate(None,...).approved is False`; rejects malformed dict | ✅ PASS |
| VAL-02 | Contract fields validated (category, action, confidence) | `tests/unit/test_contracts.py:173-205` — `ValidationError` on bad `action`/confidence/intent | ✅ PASS |
| VAL-03 | Inconsistent value vs. bank → block + regenerate | `tests/unit/test_validator.py:127-143` (spec's literal Independent Test) — `approved is False`, `"VAL-03" in result.reason` | ✅ PASS (discrimination-confirmed, sensor #3) |
| INS-01 (P2) | Comparar mês atual vs. anterior | No `insights` module/agent anywhere in `src/`/`tests/` (`grep -rl insights` → 0 hits) | ✅ Correctly absent, not silently broken |
| VEC-01 | Transaction creation indexes embedding w/ metadata → SQLite id | `tests/unit/test_indexer.py:58-77` — `metadatas[0] == {"user_id":..., "transaction_id": str(transaction.id), ...}` | ✅ PASS |
| VEC-02 | Search returns hits with score ≥ configurable threshold | `tests/integration/test_mcp.py:346-381` — hits below threshold dropped, only close match returned | ✅ PASS (⚠️ threshold value `0.5` itself is a spec-precision gap, self-disclosed in `STATE.md` T17 note) |
| VEC-03 | Atendimento uses `query_knowledge` **and cites the source** (collection+doc) | `tests/unit/test_knowledge_seed.py:101-109` covers only the raw MCP-layer lookup; `src/.../agents/specialists/atendimento.py:58-72` (`_build_context`, `answer`) never surfaces `doc_id`/collection in the reply text | ❌ **GAP** — see finding #3 |
| VEC-04 | Deleting a transaction removes its embedding | `tests/unit/test_indexer.py:112-123` — `collection.count() == 0` after delete | ✅ PASS |
| VEC-05 | ChromaDB down → degrade to SQLite LIKE, no CRUD loss | `tests/integration/test_mcp.py:384-406` — `chroma_mcp.search_transactions` falls back, `hits[0]["score"] is None` | ✅ PASS |
| MCP-01 | Graph startup connects to finance-mcp/chroma-mcp, loads tools dynamically | No call site: `grep -rn get_mcp_tools src/` shows it's only *defined* in `mcp/client.py`; `main.py`/`agents/graph.py` never call it — specialists statically import `mcp_servers.*.server` functions instead | ❌ **GAP** — see finding #4 |
| MCP-02 | `create_transaction` writes through SQLite + ChromaDB | `tests/integration/test_mcp.py:102-127` — `vector_row["documents"][0] == "compra no mercado"` after `finance_mcp.create_transaction` | ✅ PASS |
| MCP-03 | MCP server init failure → log + in-process fallback | `tests/integration/test_mcp.py:545-554` — function-level PASS, but per MCP-01's finding this fallback path is never reached by the running app (dead in production) | ⚠️ **PARTIAL** (unit-proven, unreachable at runtime) |
| MCP-04 | Validator uses `get_balance` as authoritative source | `src/.../agents/validator.py:49-50` imports `_get_balance` from `mcp_servers.finance.server`; `tests/unit/test_validator.py:127-143` exercises it | ✅ PASS |
| AUTH-01 | Valid register → bcrypt hash, redirect dashboard | `tests/integration/test_auth.py:73-95` — `resp.status_code==303`, `password_hash.startswith(("$2a$",...))`, 5 budget targets seeded | ✅ PASS |
| AUTH-02 | Duplicate email → "Email já cadastrado" | `tests/integration/test_auth.py:97-114` — `assert "Email já cadastrado" in second.text` | ✅ PASS |
| AUTH-03 | Valid login → JWT httpOnly cookie, redirect dashboard | `tests/integration/test_auth.py:168-189` — `"httponly" in set_cookie`, `"samesite=lax" in set_cookie` | ✅ PASS |
| AUTH-04 | Wrong credentials → generic error, no existence leak | `tests/integration/test_auth.py:223-242` — same status/message for wrong-password and unknown-email | ✅ PASS |
| AUTH-05 | Unauthenticated → redirect `/login` | `tests/integration/test_auth.py:245-252` — `resp.headers["location"].startswith("/login")` | ✅ PASS (⚠️ "preservando URL de retorno" edge case: code implements `next=` param at `src/.../auth/dependencies.py:29-33`, but **no test asserts the `next=` query param** — see finding #5) |
| AUTH-06 | Data access filtered by session's `user_id` | `tests/integration/test_auth.py:334-380` — Ana's probe sees only her own transaction | ✅ PASS |
| WEB-01 | `/dashboard` shows transaction table (current month) | `tests/integration/test_dashboard.py:99-118` — asserts `aluguel`, `Despesa`, `R$ 2000.00` present | ✅ PASS |
| WEB-02 | Cards/bars, % per category vs. faixa (5 categories) | `tests/integration/test_dashboard.py:99-118, 140-176` — all 5 names present + `alerta` class on overshoot | ✅ PASS |
| WEB-03 | No transactions this month → empty state | `tests/integration/test_dashboard.py:121-137` | ✅ PASS |
| WEB-04 | Filter updates via HTMX, no full reload | `tests/integration/test_dashboard.py:178-188` — `hx-get="/dashboard/transactions"`, `hx-target="#transactions-table"` | ✅ PASS |
| WEB-05 | `/chat` integrated to same agent graph | `tests/integration/test_chat.py:93-117` — POST `/api/chat` invokes `agent_graph.run`, SSE event carries `AgentResponse` | ✅ PASS |
| CONV-01 | "Plano de gastos" → 5 categories + faixas + examples, no pre-existing tx required | `tests/integration/test_conversation_scenarios.py:92-105` (real graph, exact prompt) — all 5 names + `"30-40%"` in response.text | ✅ PASS |
| CONV-02 | Delivery question → Prazeres + explanation + offer register, no auto-persist | `tests/integration/test_conversation_scenarios.py:116-133` (real graph, exact prompt) — `action == "offer_register"`, `not create_calls` | ✅ PASS (+ 1 opt-in `@pytest.mark.llm` regression test, confirmed collected/deselected correctly) |
| CONV-03 | "Em quais categorias..." → invokes `get_budget_summary`, lists priority categories | `tests/integration/test_conversation_scenarios.py:186-203` (real graph, exact prompt) — `"custos_fixos" in response.text`, `"conforto" not in response.text` | ✅ PASS |
| CONV-04 | No income → orient to register income first | `tests/unit/test_orcamento.py:159-167` — `response.text == NO_INCOME_ADVICE`, `"receita" in response.text.lower()` | ✅ PASS |
| CONV-05 | Validator checks cited percentuais vs. `get_budget_summary` | `tests/unit/test_validator.py:146-161` — `approved is False`, `"CONV-05" in result.reason` | ✅ PASS |

**Status**: ❌ 4 confirmed gaps (BUD-03 AC3, ORCH-02, VEC-03, MCP-01) + 1 partial (MCP-03) + 2 minor untested-edge notes (AUTH-05's `next=`, negative-amount literal case). 33/38 requirement rows fully PASS with precise-outcome evidence.

---

## Discrimination Sensor

All mutations made on the real tree, one at a time, confirmed-killed, then reverted with `git checkout --`; `git status`/`git diff` clean before and after.

| # | File:line | Mutation | Killed? |
| - | --------- | -------- | ------- |
| 1 | `src/financial_assistant/domain/services/budget_service.py:141` | `pct > target.max_pct` → `pct < target.max_pct` (BUD-02 alert flip) | ✅ Killed — 4 failed in `tests/unit/test_budget_service.py` |
| 2 | `src/financial_assistant/agents/graph.py:61` | `state["final_response"] is None` → `is not None` (retry-routing flip, ORCH-01/VAL-03 loop) | ✅ Killed — 2 failed in `tests/integration/test_graph_smoke.py` (one a hard `AttributeError` crash) |
| 3 | `src/financial_assistant/agents/validator.py:177` | `if intent in _SKIPS_FINANCIAL_FIGURE_CHECK_FOR` → `if intent not in ...` (inverted the live-bug-fix deny-list) | ✅ Killed — 6 failed in `tests/unit/test_validator.py`, including the exact regression test for the live DeepSeek bug (`test_validate_skips_financial_check_for_explain_budget_illustrative_figures`) |

**Sensor depth**: lightweight (3 targeted mutations, proportional to feature risk — no payment/auth-critical path requiring the P0 tier).
**Result**: 3/3 killed — ✅ PASS. Working tree confirmed clean (`git status --short` shows only the pre-existing untracked `presentation-guide.md`, unrelated to this diff).

---

## Code Quality

Skimmed `agents/validator.py`, `agents/graph.py`, `web/router.py`, `agents/specialists/transacoes.py`.

| Principle | Status |
| --- | --- |
| No features beyond what was asked | ✅ |
| No abstractions for single-use code | ✅ — injectable `find_similar=None`/`create=None`/`get_summary=None` params are a consistent, minimal testing seam, not speculative flexibility |
| No unnecessary "flexibility" added | ✅ |
| Only touched files required for task | ✅ |
| Didn't "improve" unrelated code | ✅ |
| Matches existing patterns/style | ✅ — consistent `*_node(state, *, dep=None)` shape across all 5 graph nodes |
| Would senior engineer approve? | ✅, with the caveat that `graph.py`'s own docstring (lines 8-20) **already discloses** the ORCH-02 gap in comments — good self-documentation, but the gap should have been either closed or tracked as an open follow-up task, not left as a comment |
| Spec-anchored outcome check | ✅ for 33/38 rows; 4 gaps + 1 partial documented above |
| Per-layer coverage (domain 1:1 ACs; routes happy+edge+error) | ✅ — domain services (`budget_service`, `transaction_repository`) have dense 1:1 AC tests; routes cover auth guard (302/401), validation errors (400), and success paths |
| Every test maps to a spec requirement | ✅ — every test file's docstring cites the requirement IDs it covers; no unclaimed/orphan tests found in the files sampled |
| Documented guidelines followed | "none — strong defaults applied" (per `tasks.md`'s own Test Coverage Matrix header) |

No dead code or unearned abstractions found in the sampled files. `mcp/client.py`'s `get_mcp_tools()`/fallback logic is *not* dead code in the sense of unused-and-should-be-deleted — it's fully unit-tested — but it is unreachable from any production code path (finding #4), which is a wiring gap rather than a quality issue.

---

## Edge Cases (spec.md)

- [x] Valor negativo/zero rejeitado — `tests/unit/test_contracts.py:84-91` tests `amount=Decimal("0")`; the `Field(gt=Decimal("0"))` constraint (`contracts/transaction.py:26`) covers negative values too, but **no test explicitly exercises a negative amount** — minor coverage gap, not a functional one (logically covered by `gt=0`).
- [x] Categoria inexistente → mapeia ou pede confirmação — `tests/integration/test_dashboard.py:290-297` (400 on invalid filter category); `tests/unit/test_validator.py:247-255` (rejects unknown `suggested_category`)
- [x] Receita → `categoria=NULL` — covered extensively (CHAT-02, VEC-01 income test)
- [ ] DeepSeek API failure (timeout/429) → friendly error, no state corruption — **no test found** (`grep` for timeout/429/friendly-error patterns in tests returned nothing)
- [x] Despesa sem receita no mês → % sobre zero + aviso — `tests/unit/test_budget_service.py:233-244` (`NO_INCOME_WARNING`)
- [ ] Soma de targets > 100% → alerta de inconsistência — no test found for a user-configured target sum >100% (targets aren't user-configurable in this MVP per T16 note — `set_budget_targets` is P2 — so this edge case may be moot for the current scope, but spec.md doesn't scope it that way)
- [x] Falha de indexação de embedding → persiste SQLite + enfileira reindexação — `tests/unit/test_indexer.py:139-155`
- [x] Busca semântica 0 resultados → informa e sugere filtros — `tests/unit/test_transaction_repository.py:482-494` covers the 0-result contract at the repo/fallback layer; no test found for the *user-facing message* ("sugerir busca por filtros") from the agent conversation layer
- [x] Senha < 8 caracteres rejeitada — `tests/integration/test_auth.py:116-129`
- [ ] JWT expira → redireciona login preservando URL de retorno — code implements `next=` (`auth/dependencies.py:29-33`) but **no test asserts it**; also no test exercises actual token expiry (only missing/absent-cookie case)
- [x] Usuário A acessa transação de B → 404 (não 403) — `tests/unit/test_transaction_repository.py:134-151, 364-381, 407-421`; `tests/integration/test_mcp.py:236-260`

---

## Gate Check

- **Gate command**: `.venv/bin/python -m pytest tests/ -m "unit or integration" --tb=short`
- **Result**: 192 passed, 0 failed, 0 skipped, 1 deselected (llm)
- **LLM marker check**: `pytest -m llm --collect-only` → exactly 1 test collected (`test_delivery_categorization_prazeres_real_deepseek`), 192 deselected — confirms it is correctly excluded from the default gate. Full collection (no marker filter) = 193, matching 192+1 exactly.
- **Test count**: 193 total (matches `STATE.md`'s self-reported "192 passed; +1 -m llm opt-in")
- **Skipped tests**: none
- **Failures**: none

---

## Requirement Traceability Update

| Requirement | Previous Status (spec.md) | New Status |
| ----------- | -------------------------- | ---------- |
| CHAT-01/02/03 | Done | ✅ Verified |
| TBL-01/02/03 | Done | ✅ Verified |
| BUD-01/02 | Partial | ✅ Verified |
| BUD-03 | Partial | ⚠️ AC1/2 Verified, **AC3 Needs Fix** (no "resumo incondicional" path) |
| ORCH-01 | Done | ✅ Verified |
| ORCH-02 | Partial | ❌ **Needs Fix** (confirmed unreachable at graph level, not just "partial") |
| VAL-01/02/03 | Done | ✅ Verified |
| INS-01 | Pending | ✅ Correctly out of scope (P2, genuinely absent) |
| VEC-01/04/05 | Partial/Done | ✅ Verified |
| VEC-02 | Pending | ✅ Verified (⚠️ threshold value is a spec-precision gap) |
| VEC-03 | Pending | ❌ **Needs Fix** (retrieval works; "citar a fonte" AC unmet) |
| MCP-01 | Pending | ❌ **Needs Fix** (dynamic connection never happens at graph init) |
| MCP-02 | Pending | ✅ Verified |
| MCP-03 | Pending | ⚠️ Verified in isolation, unreachable at runtime (depends on MCP-01 fix) |
| MCP-04 | Pending | ✅ Verified |
| AUTH-01–06 | Done | ✅ Verified |
| WEB-01–05 | Done | ✅ Verified |
| CONV-01–05 | Done | ✅ Verified |

Note: spec.md's own "Requirement Traceability" table (bottom of spec.md) is **stale** — it still lists BUD-01/02/03, VEC-01–05, MCP-01–04, ORCH-02 as "Partial"/"Pending" from mid-implementation, even though later `STATE.md` handoff notes (T16, T23) claim most were later resolved. Independent verification confirms most genuinely were resolved by later tasks, but 4 were not (see gaps above) — so neither the stale spec.md table nor the STATE.md handoff's optimistic narrative should be taken at face value; this validation.md is the authoritative status.

---

## Summary

**Overall**: ⚠️ Issues — core MVP loop (chat registration, budgeting, auth, dashboard, the 3 literal conversational scenarios) is solid and well-tested, with a strong discrimination sensor result. Four requirement-level gaps and one partial were found that were either previously undisclosed (BUD-03 AC3, VEC-03, MCP-01) or under-classified as "partial" when they are actually fully inert at the system level (ORCH-02).

**Spec-anchored check**: 33/38 requirement rows PASS with exact-outcome evidence; 4 GAP, 1 PARTIAL, plus 2 minor untested-edge-case notes (negative amount, JWT `next=` param) and 2 edge cases with no test at all (DeepSeek timeout/429 friendly error, config'd-target-sum->100% warning).

**Sensor**: 3/3 mutations killed — the test suite meaningfully discriminates on the highest-risk new logic (budget alert threshold, retry-routing edge, the exact live-bug-fix deny-list).

**Gate**: 192 passed, 0 failed, 1 correctly deselected (llm).

**What works**: Registration/login/logout + user isolation (AUTH-*), transaction CRUD + categorization (CHAT-*/TBL-*), envelope budgeting math and alerting (BUD-01/02), full LangGraph orchestration for the base flow with bounded retry (ORCH-01, VAL-*), ChromaDB write-through/delete-sync/fallback (VEC-01/02/04/05), dashboard + HTMX filters (WEB-*), and all 3 literal spec conversational scenarios end-to-end through the real graph (CONV-01/02/03).

**Issues found**:
1. **BUD-03 AC3** ("como está meu orçamento?" → unconditional 5-category summary) has no implementation path — `orcamento.budget_advice()` only ever returns *flagged* categories or `NO_ATTENTION_TEXT`, never a full breakdown. Fix: add a dedicated intent/handler for the literal "como está meu orçamento?" phrasing that returns all 5 categories unconditionally.
2. **ORCH-02** (ambiguous intent → Atendimento) is implemented as a pure function (`specialist_for_intent(intent, confidence)`) but the graph's `_route_to_specialist` never passes `confidence`, so this path is unreachable in the running system despite being unit-tested. Fix: thread `confidence` through `orchestrator_node`'s returned state and use it in the routing edge.
3. **VEC-03** ("citar a fonte") — the Atendimento specialist retrieves from `knowledge_base` but never surfaces `doc_id`/collection in its reply text. Fix: append a source citation to `AgentResponse.text` or `metadata` in `atendimento.answer()`.
4. **MCP-01** (dynamic MCP connection at graph startup) is never exercised — `get_mcp_tools()` is fully built and tested but nothing calls it; specialists hard-import `mcp_servers.*.server` functions as static Python calls instead. This also means MCP-03's fallback is currently dead code in production. Fix: either wire `get_mcp_tools()` into `build_graph()`/app startup, or explicitly re-scope MCP-01's AC in spec.md to describe the current "in-process by default" architecture (which the design.md's own fallback story already anticipates) so it isn't silently unmet.
5. **Minor**: no test asserts the `next=` query param on the AUTH-05 redirect, and no test drives an actual expired-JWT clock scenario (only "no cookie" is tested).

**Next steps**: Route findings #1–#4 as fix tasks (bounded to the standard 3 fix→re-verify iterations); #5 is a minor test-coverage addition, not a functional fix.

---

*Note for future sessions: validation-only tasks like this one are a good fit for a faster/cheaper model tier.*
