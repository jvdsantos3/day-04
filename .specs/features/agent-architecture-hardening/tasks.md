# Agent Architecture Hardening Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow: per-task cycle, gate, atomic commit, final Verifier and discrimination sensor.

**If the skill cannot be activated, STOP and tell the user -- do not proceed without it.**

This feature has more than 3 phases. Before Execute, offer one worker per phase, sequentially; do not dispatch sub-agents unless the user accepts.

---

**Design**: `.specs/features/agent-architecture-hardening/design.md`  
**Status**: Draft

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec -- confirm before Execute. Guidelines found: `pyproject.toml` declares pytest/pytest-asyncio dev dependencies; no `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`, `.github/workflows`, or root README testing guide found. Strong defaults applied, using existing `tests/unit` and `tests/integration` patterns.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Contracts and small schemas | unit | Validate allowed values, serialization/framing, invalid event/tool payloads and edge cases from spec | `tests/unit/test_*contracts*.py`, `tests/unit/test_streaming_contracts.py` | `.venv/bin/python -m pytest tests/unit -m unit --tb=short` |
| MCP client/provider layer | unit + integration | All provider methods, `user_id` rejection, MCP primary path, fallback path, missing tool/error path, sanitized audit metadata | `tests/unit/test_mcp_providers.py`, `tests/integration/test_mcp.py` | `.venv/bin/python -m pytest tests/unit/test_mcp_providers.py tests/integration/test_mcp.py --tb=short` |
| Specialist business logic | unit | Each specialist branch from ACs, provider injection, state audit patches, no direct MCP server function usage in behavior under test | `tests/unit/test_atendimento.py`, `tests/unit/test_transacoes.py`, `tests/unit/test_orcamento.py`, `tests/unit/test_validator.py` | `.venv/bin/python -m pytest tests/unit/test_atendimento.py tests/unit/test_transacoes.py tests/unit/test_orcamento.py tests/unit/test_validator.py --tb=short` |
| Graph runtime/checkpointing | unit + integration | Build with checkpointer, invoke/stream with `thread_id`, preserve retry/validator topology, persist `chat_messages` only after successful final response | `tests/unit/test_graph.py`, `tests/integration/test_graph_smoke.py` | `.venv/bin/python -m pytest tests/unit/test_graph.py tests/integration/test_graph_smoke.py --tb=short` |
| Chat SSE route | integration | Auth 401, typed event order, final `AgentResponse`, done event, sanitized fallback/error events, no false success persistence on error | `tests/integration/test_chat.py` | `.venv/bin/python -m pytest tests/integration/test_chat.py --tb=short` |
| Conversation regressions | integration | Existing 3 prompts keep spec-defined outcomes while providers/checkpoint/SSE are active | `tests/integration/test_conversation_scenarios.py` | `.venv/bin/python -m pytest tests/integration/test_conversation_scenarios.py -m integration --tb=short` |
| Documentation/spec updates | none | Diff/format check only; docs must match implemented behavior | `.specs/features/agent-architecture-hardening/*.md`, `presentation-guide.md` | `git diff --check -- .specs/features/agent-architecture-hardening presentation-guide.md` |

## Parallelism Assessment

> Generated from codebase -- confirm before Execute.

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --- | --- | --- | --- |
| Unit | Yes | Pure functions, fakes and monkeypatches scoped per test | `tests/unit/test_transacoes.py`, `tests/unit/test_validator.py` use injected fakes/monkeypatch |
| Integration: DB/API | Mostly Yes, but run sequentially by default | Per-test in-memory SQLite or isolated app fixtures; no xdist configured | `tests/integration/test_chat.py`, `tests/integration/test_graph_smoke.py` build isolated SQLite |
| Integration: Chroma/MCP | Mostly Yes, but run sequentially by default | Temp Chroma path + in-memory SQLite per fixture; module monkeypatches would conflict under true parallel xdist | `tests/integration/test_mcp.py` uses `tmp_path`, monkeypatches module globals |
| LLM opt-in | No for normal gate | Hits real DeepSeek API; explicitly deselected from standard integration gate | `tests/integration/test_conversation_scenarios.py` marks real API test with `@pytest.mark.llm` |
| Docs | Yes | Static diff/whitespace check | `git diff --check` |

## Gate Check Commands

> Generated from codebase -- confirm before Execute.

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | After unit-only tasks | `.venv/bin/python -m pytest tests/unit -m unit --tb=short` |
| Targeted Integration | After task touching route/graph/MCP integration | `.venv/bin/python -m pytest <task-specific test files> --tb=short` |
| Full | After phase completion or graph/API changes | `.venv/bin/python -m pytest tests/ -m "unit or integration" --tb=short` |
| Docs | After docs-only task | `git diff --check -- .specs/features/agent-architecture-hardening presentation-guide.md` |

---

## Execution Plan

### Phase 1: Foundations

Create contracts, checkpoint support and MCP tool-bundle support.

```text
T1 ─┐
T3 ─┴──→ T4

T2 ─────→ T10
```

### Phase 2: Providers And Runtime Dependencies

Build typed providers and dependency container.

```text
T4 ──→ T5
```

### Phase 3: Specialist Refactors

After providers/runtime exist, refactor specialists independently.

```text
T5 ──┬──→ T6 [P]
     ├──→ T7 [P]
     ├──→ T8 [P]
     └──→ T9 [P]
```

### Phase 4: Graph, Checkpointing And SSE

Wire dependencies into graph runtime and expose typed SSE.

```text
T2 ─────────────┐
T6, T7, T8, T9 ─┼──→ T10 ──→ T11 ──→ T12
T5 ─────────────┘
T1 ───────────────────────────┘
```

### Phase 5: Regression And Documentation

Prove behavior is preserved and update the guide.

```text
T12 ──→ T13 ──→ T14
```

---

## Task Breakdown

### T1: Add Streaming Event Contracts

**What**: Define typed stream event contracts and SSE formatting helpers.  
**Where**: `src/financial_assistant/contracts/streaming.py`, `tests/unit/test_streaming_contracts.py`  
**Depends on**: None  
**Reuses**: `src/financial_assistant/contracts/agent_response.py`, current `_sse_event` behavior in `src/financial_assistant/chat/router.py`  
**Requirement**: `AHR-SSE-01`, `AHR-SSE-04`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [x] `StreamEvent` accepts only `message_delta`, `tool_call`, `tool_result`, `final`, `done`, `error`.
- [x] `final` event can carry a serialized `AgentResponse`.
- [x] SSE formatter supports named events and multi-line data safely.
- [x] Invalid event names fail validation.
- [x] Quick gate passes.

**Tests**: unit  
**Gate**: quick

---

### T2: Add SQLite Checkpointing Support

**What**: Add checkpoint dependency/config/factory with testable `thread_id` config.  
**Where**: `pyproject.toml`, `src/financial_assistant/config.py`, `src/financial_assistant/agents/checkpointing.py`, `tests/unit/test_checkpointing.py`  
**Depends on**: None  
**Reuses**: `financial_assistant.config.Settings`, LangGraph `MemorySaver` test pattern from installed package  
**Requirement**: `AHR-CHK-01`, `AHR-CHK-02`

**Tools**:

- MCP: `plugin-context7-context7` for LangGraph checkpoint docs if API uncertainty appears
- Skill: `tlc-spec-driven`

**Done when**:

- [x] `langgraph-checkpoint-sqlite` is added to dependencies and installed for the active environment.
- [x] `Settings` exposes a default checkpoint DB path, separate from `finance.db`.
- [x] `graph_config(session_id)` returns `{"configurable": {"thread_id": session_id}}`.
- [x] Checkpointer factory supports injected/in-memory saver for tests.
- [x] Quick gate passes.

**Tests**: unit  
**Gate**: quick

---

### T3: Extend MCP Client With ToolBundle

**What**: Preserve fallback tools while exposing primary MCP tool map for providers.  
**Where**: `src/financial_assistant/mcp/client.py`, `tests/integration/test_mcp.py`  
**Depends on**: None  
**Reuses**: `get_mcp_tools()`, `in_process_tools()`, existing MCP fallback integration tests  
**Requirement**: `AHR-MCP-01`, `AHR-MCP-02`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [x] `ToolBundle` or equivalent exposes `primary`, `fallback`, and `source`.
- [x] Successful MCP loading keeps in-process fallback tools available.
- [x] MCP load failure returns fallback as primary and fallback with `source="fallback"`.
- [x] Missing/duplicate tool names are handled deterministically.
- [x] Targeted integration gate for `tests/integration/test_mcp.py` passes.

**Tests**: integration  
**Gate**: targeted integration

---

### T4: Create Typed MCP Providers

**What**: Implement `FinanceToolProvider`, `ChromaToolProvider`, `ToolResult`, and provider errors.  
**Where**: `src/financial_assistant/mcp/providers.py`, `tests/unit/test_mcp_providers.py`  
**Depends on**: T1, T3  
**Reuses**: MCP tool names from `mcp_servers/finance/server.py`, `mcp_servers/chroma/server.py`, stream event contracts from T1  
**Requirement**: `AHR-MCP-01`, `AHR-MCP-02`, `AHR-MCP-03`, `AHR-MEM-01`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Every provider method rejects missing/empty `user_id` for user-scoped tools.
- [ ] Provider calls primary tool first and fallback tool on primary failure.
- [ ] Provider emits/logs sanitized `tool_call` and `tool_result` metadata.
- [ ] `ToolResult.audit_metadata()` returns bounded safe metadata.
- [ ] Both primary-success and fallback-success paths are covered.
- [ ] Quick gate passes.

**Tests**: unit  
**Gate**: quick

---

### T5: Add Agent Runtime Dependency Container

**What**: Build `AgentDependencies` and runtime dependency factory for graph nodes.  
**Where**: `src/financial_assistant/agents/runtime.py`, `tests/unit/test_runtime.py`  
**Depends on**: T4  
**Reuses**: Providers from T4, existing graph dependency style with injectable functions  
**Requirement**: `AHR-MCP-01`, `AHR-INS-01`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] `AgentDependencies` exposes finance/chroma providers and optional event emitter.
- [ ] Factory builds providers from the tool bundle.
- [ ] Tests can inject fake dependencies without loading MCP/Chroma/DeepSeek.
- [ ] Design remains extendable for future Insights read-only tools.
- [ ] Quick gate passes.

**Tests**: unit  
**Gate**: quick

---

### T6: Refactor Atendimento To Chroma Provider [P]

**What**: Route Atendimento RAG through `ChromaToolProvider` and populate retrieved-context audit state.  
**Where**: `src/financial_assistant/agents/specialists/atendimento.py`, `tests/unit/test_atendimento.py`  
**Depends on**: T5  
**Reuses**: Existing prompt, `AgentResponse.metadata.sources`, fake LLM pattern  
**Requirement**: `AHR-RAG-01`, `AHR-RAG-02`, `AHR-RAG-03`, `AHR-STATE-01`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Atendimento no longer calls `knowledge_seed.query_knowledge` directly in runtime behavior.
- [ ] Atendimento receives/uses `chroma.query_knowledge(user_id, query, n_results)`.
- [ ] Node patch includes `retrieved_context`.
- [ ] `metadata.sources` is preserved.
- [ ] Empty knowledge results return safe PT-BR fallback.
- [ ] Specialist unit tests pass.

**Tests**: unit  
**Gate**: quick

---

### T7: Refactor Transacoes To Providers [P]

**What**: Route categorization and transaction writes through providers and populate pending/tool audit fields.  
**Where**: `src/financial_assistant/agents/specialists/transacoes.py`, `tests/unit/test_transacoes.py`  
**Depends on**: T5  
**Reuses**: Existing regex parser, category rationale, `AgentResponse.action` behavior  
**Requirement**: `AHR-MCP-04`, `AHR-STATE-02`, `AHR-REG-02`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Runtime behavior no longer imports/calls `mcp_servers.*.server` functions directly.
- [ ] Categorize flow uses `chroma.find_similar_transactions`.
- [ ] Register flow uses `finance.create_transaction`.
- [ ] `categorize` flow sets `pending_action` and does not persist.
- [ ] Register flow sets sanitized `last_tool_results`.
- [ ] Delivery/cinema/salary regression unit tests pass.

**Tests**: unit  
**Gate**: quick

---

### T8: Refactor Orcamento To Finance Provider [P]

**What**: Route budget summary reads through provider and populate audit metadata.  
**Where**: `src/financial_assistant/agents/specialists/orcamento.py`, `tests/unit/test_orcamento.py`  
**Depends on**: T5  
**Reuses**: Existing `budget_advice`, `_format_advice`, `_format_full_summary` logic  
**Requirement**: `AHR-MCP-04`, `AHR-STATE-03`, `AHR-REG-03`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Runtime behavior no longer imports/calls finance MCP server function directly.
- [ ] Budget summary reads use `finance.get_budget_summary`.
- [ ] Node patch includes sanitized `last_tool_results`.
- [ ] No-income and prioritized-category behavior remains unchanged.
- [ ] Orcamento unit tests pass.

**Tests**: unit  
**Gate**: quick

---

### T9: Refactor Validator To Finance Provider [P]

**What**: Route factual balance/budget checks through provider and preserve retry semantics.  
**Where**: `src/financial_assistant/agents/validator.py`, `tests/unit/test_validator.py`  
**Depends on**: T5  
**Reuses**: Existing `validate()`, regex extraction, `ValidationResult`, retry logic  
**Requirement**: `AHR-MCP-04`, `AHR-STATE-03`, `AHR-REG-03`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Validator uses provider-backed `get_balance` and `get_budget_summary`.
- [ ] Existing explain-budget skip remains fail-closed for other intents.
- [ ] Rejection appends structured `agent_notes`.
- [ ] Currency/percent mismatch tests still reject.
- [ ] Validator unit tests pass.

**Tests**: unit  
**Gate**: quick

---

### T10: Wire Graph Dependencies And Checkpointing

**What**: Compile graph with injected dependencies and checkpointer, invoke with `thread_id`.  
**Where**: `src/financial_assistant/agents/graph.py`, `tests/unit/test_graph.py`, `tests/integration/test_graph_smoke.py`  
**Depends on**: T2, T5, T6, T7, T8, T9  
**Reuses**: Existing graph topology, `_persist_turn()`, `specialist_for_intent()`  
**Requirement**: `AHR-CHK-01`, `AHR-CHK-02`, `AHR-CHK-03`, `AHR-MCP-01`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] `build_graph()` accepts/injects `AgentDependencies`.
- [ ] Node registrations close over providers instead of using module globals.
- [ ] Graph compiles with checkpointer when provided.
- [ ] `run()` invokes graph with `graph_config(session_id)`.
- [ ] Existing retry and low-confidence routing integration tests pass.
- [ ] Full gate passes for graph-related tests.

**Tests**: unit + integration  
**Gate**: targeted integration

---

### T11: Add Graph Stream Turn Runtime

**What**: Add `stream_turn()` or equivalent graph runtime event generator.  
**Where**: `src/financial_assistant/agents/graph.py`, `src/financial_assistant/agents/streaming.py`, `tests/unit/test_graph.py`  
**Depends on**: T1, T10  
**Reuses**: Stream contracts from T1, graph config/checkpointing from T10  
**Requirement**: `AHR-SSE-02`, `AHR-SSE-03`, `AHR-SSE-04`

**Tools**:

- MCP: `plugin-context7-context7` if LangGraph stream API uncertainty appears
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Graph stream runtime emits typed `StreamEvent` objects.
- [ ] Deterministic specialists produce tool/progress/final events without fake token splitting.
- [ ] Provider fallback events are sanitized.
- [ ] `run()` remains available for non-stream callers.
- [ ] Unit graph streaming tests pass.

**Tests**: unit  
**Gate**: quick

---

### T12: Update Chat SSE Endpoint

**What**: Map `agent_graph.stream_turn()` events to HTTP SSE frames.  
**Where**: `src/financial_assistant/chat/router.py`, `tests/integration/test_chat.py`  
**Depends on**: T11  
**Reuses**: `ChatRequest`, `get_current_user_api`, existing SSE endpoint tests  
**Requirement**: `AHR-SSE-01`, `AHR-SSE-03`, `AHR-SSE-04`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Auth behavior remains 401 for unauthenticated API calls.
- [ ] Successful turn emits typed SSE events in order.
- [ ] `final` event contains valid `AgentResponse` JSON.
- [ ] Stream ends with `done`.
- [ ] Error path emits `error` and does not report false success.
- [ ] Chat integration tests pass.

**Tests**: integration  
**Gate**: targeted integration

---

### T13: Update Conversation Regression Tests

**What**: Update mocked integration scenarios to prove providers/checkpoint/SSE-compatible graph still preserves outputs.  
**Where**: `tests/integration/test_conversation_scenarios.py`, optionally `tests/integration/test_graph_smoke.py`  
**Depends on**: T12  
**Reuses**: Existing 3 literal prompts and fixtures  
**Requirement**: `AHR-REG-01`, `AHR-REG-02`, `AHR-REG-03`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] "Quero montar um plano de gastos" still mentions five categories and sources.
- [ ] Delivery categorization still returns Prazeres and `offer_register` without create call.
- [ ] Budget advice still lists prioritized categories from summary.
- [ ] Validator still rejects inconsistent non-`explain_budget` values.
- [ ] Full gate passes.

**Tests**: integration  
**Gate**: full

---

### T14: Update Presentation Guide And Spec Traceability

**What**: Update docs so the guide and feature specs reflect the implemented hardening state.  
**Where**: `presentation-guide.md`, `.specs/features/agent-architecture-hardening/spec.md`, `.specs/features/agent-architecture-hardening/design.md`, `.specs/features/agent-architecture-hardening/tasks.md`  
**Depends on**: T13  
**Reuses**: Current "Gaps honestos" section and requirement traceability tables  
**Requirement**: `AHR-DOC-01`, `AHR-INS-01`

**Tools**:

- MCP: none
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] `presentation-guide.md` no longer describes completed P1 items as current gaps.
- [ ] Remaining gaps are explicitly P2/out of scope.
- [ ] Spec requirement traceability statuses reflect completed tasks.
- [ ] Tasks status is updated through T14.
- [ ] Docs gate passes.

**Tests**: none  
**Gate**: docs

---

## Parallel Execution Map

Visual representation of task ordering within phases (`[P]` = order-free, no inter-task dependency):

```text
Phase 1:
  T1 ─┐
  T2 ─┼──→ T4
  T3 ─┘

Phase 2:
  T4 ──→ T5

Phase 3:
  T5 complete, then:
    ├── T6 [P] Atendimento
    ├── T7 [P] Transacoes
    ├── T8 [P] Orcamento
    └── T9 [P] Validator

Phase 4:
  T2 + T5 + T6/T7/T8/T9 complete:
    T10 ──→ T11 ──→ T12

Phase 5:
  T12 ──→ T13 ──→ T14
```

**Parallelism constraint:** `[P]` means order-free within the phase. It is not a directive to spawn one sub-agent per task. Because this feature has more than 3 phases, Execute should first offer one worker per phase, sequentially.

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| --- | --- | --- | --- |
| T1 | None | No incoming arrows | OK |
| T2 | None | No incoming arrows | OK |
| T3 | None | No incoming arrows | OK |
| T4 | T1, T3 | T1/T3 feed T4 | OK |
| T5 | T4 | T4 -> T5 | OK |
| T6 | T5 | T5 -> T6 | OK |
| T7 | T5 | T5 -> T7 | OK |
| T8 | T5 | T5 -> T8 | OK |
| T9 | T5 | T5 -> T9 | OK |
| T10 | T2, T5, T6, T7, T8, T9 | T2 + T5 + T6/T7/T8/T9 -> T10 | OK |
| T11 | T1, T10 | T10 -> T11 plus T1 stream contract dependency | OK |
| T12 | T11 | T11 -> T12 | OK |
| T13 | T12 | T12 -> T13 | OK |
| T14 | T13 | T13 -> T14 | OK |

---

## Task Granularity Check

| Task | Scope | Status |
| --- | --- | --- |
| T1: Streaming contracts | One contract module + tests | Granular |
| T2: Checkpoint support | One config/factory concern + tests | Granular |
| T3: ToolBundle loader | One MCP client enhancement + tests | Granular |
| T4: Typed providers | One provider module with paired unit tests | Granular |
| T5: Runtime dependencies | One runtime container module + tests | Granular |
| T6: Atendimento refactor | One specialist + tests | Granular |
| T7: Transacoes refactor | One specialist + tests | Granular |
| T8: Orcamento refactor | One specialist + tests | Granular |
| T9: Validator refactor | One validator module + tests | Granular |
| T10: Graph dependency/checkpoint wiring | One graph integration concern + tests | Granular |
| T11: Graph stream runtime | One streaming runtime concern + tests | Granular |
| T12: Chat SSE endpoint | One API endpoint surface + tests | Granular |
| T13: Conversation regressions | Existing integration regression suite update | Granular |
| T14: Docs/traceability | Documentation closure | Granular |

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| T1 | Contracts | unit | unit | OK |
| T2 | Config/checkpoint factory | unit | unit | OK |
| T3 | MCP client integration | integration | integration | OK |
| T4 | Provider business logic | unit | unit | OK |
| T5 | Runtime dependency container | unit | unit | OK |
| T6 | Specialist business logic | unit | unit | OK |
| T7 | Specialist business logic | unit | unit | OK |
| T8 | Specialist business logic | unit | unit | OK |
| T9 | Validator business logic | unit | unit | OK |
| T10 | Graph runtime/checkpointing | unit + integration | unit + integration | OK |
| T11 | Graph streaming runtime | unit | unit | OK |
| T12 | Chat route/API | integration | integration | OK |
| T13 | Conversation regressions | integration | integration | OK |
| T14 | Documentation | none | none | OK |

---

## Requirement -> Task Map

| Requirement ID | Task(s) |
| --- | --- |
| AHR-MCP-01 | T3, T4, T5, T10 |
| AHR-MCP-02 | T3, T4, T12 |
| AHR-MCP-03 | T4 |
| AHR-MCP-04 | T6, T7, T8, T9, T10 |
| AHR-RAG-01 | T6 |
| AHR-RAG-02 | T6 |
| AHR-RAG-03 | T6, T13 |
| AHR-SSE-01 | T1, T12 |
| AHR-SSE-02 | T11 |
| AHR-SSE-03 | T11, T12 |
| AHR-SSE-04 | T1, T4, T11, T12 |
| AHR-CHK-01 | T2, T10 |
| AHR-CHK-02 | T2, T10 |
| AHR-CHK-03 | T10, T12 |
| AHR-STATE-01 | T6 |
| AHR-STATE-02 | T7 |
| AHR-STATE-03 | T8, T9 |
| AHR-MEM-01 | T4, T6 |
| AHR-REG-01 | T6, T13 |
| AHR-REG-02 | T7, T13 |
| AHR-REG-03 | T8, T9, T13 |
| AHR-DOC-01 | T14 |
| AHR-INS-01 | T5, T14 |

---

## Before Execute: MCPs And Skills

Before starting Execute, confirm which tools/skills to use.

**Available MCPs likely relevant**:

- `plugin-context7-context7`: library docs for LangGraph/checkpointing/streaming/MCP adapter when API details are uncertain.

**Skills likely relevant**:

- `tlc-spec-driven`: required for Execute.
- `test-driven-development`: required when implementing behavior changes.
- `systematic-debugging`: use when tests fail or behavior is unexpected.
- `verification-before-completion`: required before completion claims.
