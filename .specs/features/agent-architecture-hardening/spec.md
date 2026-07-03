# Agent Architecture Hardening Specification

## Problem Statement

O MVP do assistente financeiro ja entrega LangGraph, especialistas, MCPs, RAG, SSE e memoria basica, mas alguns pontos arquiteturais ainda estao incompletos ou apenas preparados: MCP tools sao carregadas mas nao injetadas nos especialistas, Atendimento usa RAG local em vez de provider MCP, SSE ainda responde por turno, nao ha checkpointer LangGraph, campos avancados do `AgentState` sao pouco populados e `chat_memory`/`working_memory` ainda nao sao centrais no fluxo. Esta feature transforma esses gaps em comportamento real sem mudar os resultados funcionais atuais dos 3 prompts principais.

## Goals

- [ ] Injetar tools via providers tipados com MCP como fonte primaria e fallback in-process.
- [ ] Alinhar Atendimento/RAG ao `chroma-mcp` por provider, preservando recuperacao deterministica antes da LLM.
- [ ] Introduzir contrato SSE tipado com streaming de tokens quando houver LLM streaming real e eventos de progresso/tool para fluxos deterministicos.
- [ ] Adicionar checkpointing SQLite para robustez por `session_id`/thread sem prometer workflows long-running complexos.
- [ ] Popular `retrieved_context`, `pending_action` e `last_tool_results` como trilha de auditoria do turno.
- [ ] Usar `working_memory` para fatos estruturados minimos e manter `chat_memory` preparado para memoria cross-session.
- [ ] Preservar os outputs e cenarios conversacionais atuais como regressao obrigatoria.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Agente Insights completo | P2 desta arquitetura; a feature atual prepara contratos/memoria, mas nao entrega analise mensal nova |
| ReAct/tool-calling livre em todos os especialistas | P1 prioriza determinismo, previsibilidade e regressao do MVP atual |
| Reescrever comportamento dos especialistas | Hardening por baixo; outputs atuais devem permanecer compativeis |
| Atualizacao visual completa do React Chat | Esta feature define/testa contrato SSE; UI completa fica na feature React frontend |
| Streaming simulado para respostas deterministicas | Eventos de progresso/tool bastam; simular tokens criaria comportamento artificial |
| Checkpointing long-running com retomada exata de qualquer node interrompido | P1 cobre robustez por sessao/thread; execucoes complexas ficam futuras |
| Tracing distribuido/metrica completa | P1 exige logs estruturados; observabilidade avancada fica futura |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Fronteira P1 | Hardening arquitetural sem criar novo produto | Fecha os gaps do guia preservando o MVP | y |
| Agente Insights | P2 preparado, nao implementado no P1 | Evita ampliar escopo; memoria/providers ja deixam base pronta | y |
| Compatibilidade | Preservar outputs/cenarios atuais | A feature deve trocar arquitetura por baixo sem regressao funcional | y |
| Frontend | Backend/API apenas, salvo contrato SSE necessario | React frontend ja e feature separada | y |
| Modelo de tools | Deterministico com dependency injection | Mantem testabilidade e evita LLM escolhendo tools financeiras livremente | y |
| Fonte primaria das tools | MCP client primario, fallback in-process | Alinha AD-004 e torna MCP realmente usado em runtime | y |
| Forma de injecao | Providers tipados por dominio | Interfaces explicitas sao mais seguras que listas brutas de `BaseTool` | y |
| Atendimento/RAG | `ChromaToolProvider.query_knowledge(user_id, query)` antes da LLM | Mantem grounding deterministico e remove tool local direta | y |
| Checkpointing | SQLite checkpointer por sessao/thread | Aproveita persistencia local existente | y |
| Memoria estruturada | `working_memory` para poucos fatos seguros | Evita salvar todos os turnos e gerar ruido/sensibilidade | y |
| Campos avancados do estado | Auditoria do turno | `retrieved_context`, `pending_action`, `last_tool_results` passam a ter funcao concreta | y |
| Streaming | Tokens quando houver LLM streaming real; eventos de etapa para fluxos deterministicos | Evita streaming artificial e preserva transparencia | y |
| Contrato SSE | Eventos tipados: `message_delta`, `tool_call`, `tool_result`, `final`, `done`, `error` | Contrato testavel e extensivel | y |
| Traces/sources | Metadata sanitizada | Ajuda UI/debug sem vazar payload sensivel | y |
| Falha MCP runtime | Fallback in-process + log estruturado + evento sanitizado quando relevante | Degrada sem quebrar turno se a tool equivalente funcionar | y |
| Auth boundary | Provider rejeita chamada user-scoped sem `user_id` | Defesa antes do MCP e antes do banco/vetor | y |
| Observabilidade | Logs estruturados por session/user/tool/agent/attempt, sem dados sensiveis | Suficiente para diagnostico do P1 | y |
| Gate final | Testes por gap + smoke dos 3 prompts + docs atualizadas | Fecha regressao funcional e arquitetural | y |

**Open questions:** none — all resolved or logged above.

---

## Implicit-Requirement Dimensions

| Dimension | Resolution |
| --- | --- |
| Input validation & bounds | Providers SHALL reject user-scoped calls without `user_id`; SSE events SHALL validate against typed contracts; working-memory facts SHALL use bounded schemas and sanitized metadata. |
| Failure / partial-failure states | MCP runtime failures SHALL attempt in-process fallback; if fallback also fails, the turn SHALL emit a sanitized `error` event and preserve persisted state integrity. |
| Idempotency / retry / duplicate handling | Existing transaction write-through semantics remain; checkpoint writes SHALL be safe to retry per `session_id`/thread; working-memory writes SHALL use generated IDs and not duplicate on failed retries where detectable. |
| Auth boundaries & rate limits | Every user-scoped provider method SHALL require `user_id`; no new rate limiting in P1 because the app has no rate-limit layer yet. |
| Concurrency / ordering | SSE events SHALL preserve per-turn order; checkpoint and `chat_messages` persistence SHALL not reorder a single session's user/assistant turn. |
| Data lifecycle / expiry | Checkpoints and memory use existing local persistence with no TTL in P1; deletion/retention policy is out of scope. |
| Observability | Structured logs SHALL include session_id, user_id hash or raw user_id only where existing logs already allow it, agent, tool, status and attempt; logs SHALL not include raw financial payload unless already persisted intentionally. |
| External-dependency failure | MCP, ChromaDB and LLM failures SHALL degrade according to existing fallback patterns plus typed SSE error events. |
| State-transition integrity | Graph transitions SHALL preserve `orchestrator -> specialist -> validator -> END|retry`; new streaming/checkpointing SHALL not bypass Validator. |

---

## User Stories

### P1: MCP Tool Providers As Runtime Boundary ⭐ MVP

**User Story**: As a developer maintaining the assistant, I want specialists to use typed MCP-backed providers so that MCPs are the real runtime boundary while preserving deterministic behavior.

**Why P1**: This closes the largest architecture gap: tools are loaded today but specialists mostly import server functions directly.

**Acceptance Criteria**:

1. WHEN `build_graph()` initializes dependencies THEN the system SHALL construct typed finance/chroma tool providers using MCP tools as the primary source.
2. WHEN MCP tool loading fails at startup or runtime THEN the provider SHALL fall back to equivalent in-process tools and log a structured warning.
3. WHEN a user-scoped provider method is called without `user_id` THEN the provider SHALL reject the call before invoking MCP or fallback code.
4. WHEN Transacoes registers a transaction THEN it SHALL call the finance provider rather than importing `mcp_servers.finance.server.create_transaction` directly.
5. WHEN Orcamento requests budget summary THEN it SHALL call the finance provider rather than importing `get_budget_summary` directly.
6. WHEN Validador checks balance or budget summary THEN it SHALL call the finance provider and preserve existing factual validation outcomes.

**Independent Test**: Inject fake providers into specialists/graph and verify each specialist calls the expected provider method while the existing 3 conversation scenarios still pass.

**Requirements**: `AHR-MCP-01`, `AHR-MCP-02`, `AHR-MCP-03`, `AHR-MCP-04`

---

### P1: RAG Through Chroma Provider ⭐ MVP

**User Story**: As a user asking educational budget questions, I want Atendimento answers to keep using grounded knowledge while the implementation goes through the same chroma MCP boundary as other semantic tools.

**Why P1**: Removes the local RAG exception and makes the guide's architecture true in code.

**Acceptance Criteria**:

1. WHEN Atendimento handles `explain_budget` THEN it SHALL retrieve documents through `ChromaToolProvider.query_knowledge(user_id, query, n_results)`.
2. WHEN `query_knowledge` returns docs THEN Atendimento SHALL populate `retrieved_context` in `AgentState` with sanitized source/context metadata.
3. WHEN Atendimento returns `AgentResponse` THEN `metadata.sources` SHALL still include collection/doc identifiers.
4. WHEN Chroma/MCP fails but fallback succeeds THEN Atendimento SHALL answer from fallback results and emit/log sanitized fallback status.
5. WHEN no knowledge docs are available THEN Atendimento SHALL return a helpful PT-BR fallback instead of hallucinating category ranges.

**Independent Test**: Fake `ChromaToolProvider` returns known docs; Atendimento output includes the five categories, `metadata.sources`, and `AgentState.retrieved_context`.

**Requirements**: `AHR-RAG-01`, `AHR-RAG-02`, `AHR-RAG-03`

---

### P1: Typed SSE Streaming Contract ⭐ MVP

**User Story**: As a frontend/API consumer, I want typed SSE events so that the chat can render progress, final answers and safe traces consistently.

**Why P1**: Current SSE sends one full `AgentResponse`; this feature establishes the future-compatible contract without requiring a full UI rewrite.

**Acceptance Criteria**:

1. WHEN a chat turn starts THEN `POST /api/chat` SHALL stream typed SSE events with event names from the allowed set: `message_delta`, `tool_call`, `tool_result`, `final`, `done`, `error`.
2. WHEN a specialist uses LLM streaming THEN the system SHALL emit `message_delta` events in order.
3. WHEN a specialist is deterministic and does not stream tokens THEN the system SHALL emit tool/progress events and a single `final` event.
4. WHEN the turn completes successfully THEN the final event SHALL contain a valid `AgentResponse` payload and the stream SHALL end with `done`.
5. WHEN a recoverable tool fallback occurs THEN the stream SHALL expose only sanitized tool status, not raw sensitive payload.
6. WHEN an unrecoverable error occurs THEN the stream SHALL emit `error` and SHALL not persist an assistant success message.

**Independent Test**: Call `POST /api/chat` with fake graph/stream events and assert SSE event names, order and final payload shape.

**Requirements**: `AHR-SSE-01`, `AHR-SSE-02`, `AHR-SSE-03`, `AHR-SSE-04`

---

### P1: SQLite Checkpointing For Graph Robustness ⭐ MVP

**User Story**: As a developer operating the assistant, I want LangGraph state checkpointed by session/thread so that graph execution has a recoverable technical state boundary beyond plain chat history.

**Why P1**: Current `chat_messages` stores conversation history, but no LangGraph checkpointer is configured.

**Acceptance Criteria**:

1. WHEN a graph is built for production/runtime THEN it SHALL compile with a SQLite-backed checkpointer.
2. WHEN a graph is invoked THEN it SHALL use a stable thread/session identifier derived from `session_id`.
3. WHEN a turn completes THEN existing `chat_messages` persistence SHALL still record user and assistant messages as before.
4. WHEN checkpointing fails before graph execution THEN the system SHALL fail gracefully with a typed `error` event and SHALL not persist a false assistant success.
5. WHEN tests build the graph with an in-memory checkpointer or fake checkpointer THEN behavior SHALL remain deterministic.

**Independent Test**: Run graph with a test checkpointer, assert checkpoint calls/config include the session thread id, and assert `chat_messages` persistence remains unchanged.

**Requirements**: `AHR-CHK-01`, `AHR-CHK-02`, `AHR-CHK-03`

---

### P1: AgentState Audit Fields And Memory Use ⭐ MVP

**User Story**: As a developer debugging or extending agents, I want `AgentState` fields to be populated consistently so that each turn explains what context, actions and tool results were used.

**Why P1**: `retrieved_context`, `pending_action` and `last_tool_results` exist today but are underused.

**Acceptance Criteria**:

1. WHEN Atendimento retrieves RAG context THEN it SHALL populate `retrieved_context` with sanitized document/source metadata.
2. WHEN Transacoes offers a registration without persisting THEN it SHALL populate `pending_action` with the proposed action and safe details.
3. WHEN Transacoes persists a transaction THEN it SHALL populate `last_tool_results` with sanitized create result.
4. WHEN Orcamento reads budget summary THEN it SHALL populate `last_tool_results` with sanitized summary metadata sufficient for Validator/audit.
5. WHEN Validator rejects a response THEN it SHALL append a structured note to `agent_notes` without raw sensitive payload beyond existing response text.
6. WHEN a safe durable fact is extracted for memory THEN the system SHALL write it through `working_memory` using the chroma provider.

**Independent Test**: Invoke each specialist with fake providers and assert state patches include the expected audit fields without leaking unbounded raw payloads.

**Requirements**: `AHR-STATE-01`, `AHR-STATE-02`, `AHR-STATE-03`, `AHR-MEM-01`

---

### P1: Regression Preservation For Existing Conversations ⭐ MVP

**User Story**: As a demo presenter, I want the existing conversation scenarios to keep working so that architecture hardening does not break the product story.

**Why P1**: This is a hardening feature, not a behavior rewrite.

**Acceptance Criteria**:

1. WHEN the user asks "Quero montar um plano de gastos" THEN the system SHALL still explain the five categories with ranges/examples and source metadata.
2. WHEN the user asks "Gastei 20 reais num pedido de delivery, em qual categoria essa despesa se encaixa?" THEN the system SHALL still suggest Prazeres and `action="offer_register"` without persisting automatically.
3. WHEN the user asks "Em quais categorias devo prestar mais atencao ou economizar?" THEN the system SHALL still use budget summary data and list prioritized categories.
4. WHEN a response contains financial values or percentages outside `explain_budget` THEN Validator SHALL still check them against provider-backed balance/summary.
5. WHEN all P1 changes are complete THEN `presentation-guide.md` SHALL be updated so the "gaps honestos" section reflects the new state.

**Independent Test**: Run the existing mocked integration conversation scenarios plus targeted checks that providers/checkpoint/SSE are active.

**Requirements**: `AHR-REG-01`, `AHR-REG-02`, `AHR-REG-03`, `AHR-DOC-01`

---

### P2: Insights Preparation

**User Story**: As a future product developer, I want the architecture to prepare for an Insights agent so that trends and export features can be added without reworking providers/memory again.

**Why P2**: Useful, but not needed to close the current hardening gaps.

**Acceptance Criteria**:

1. WHEN providers are designed THEN they SHALL not prevent future read-only monthly comparison tools.
2. WHEN memory schemas are introduced THEN they SHALL allow future facts such as user goals/preferences without coupling them to Insights.
3. WHEN docs mention Insights THEN they SHALL label it as P2, not delivered in P1.

**Independent Test**: Design/tasks review confirms providers expose extension points without implementing Insights behavior.

**Requirements**: `AHR-INS-01`

---

## Edge Cases

- WHEN MCP client returns a tool list missing a required tool THEN provider initialization SHALL fail over to in-process equivalent or fail startup with a clear error if no equivalent exists.
- WHEN both MCP and fallback fail for a required financial write THEN the transaction SHALL not be partially reported as registered.
- WHEN an SSE client disconnects mid-turn THEN the server SHALL avoid persisting a successful assistant message unless the graph turn completed.
- WHEN checkpoint storage is unavailable THEN the chat endpoint SHALL emit a typed error and preserve existing persisted data.
- WHEN `working_memory` write fails after the main response is valid THEN the response MAY still succeed, but the failure SHALL be logged and surfaced only as sanitized metadata if exposed.
- WHEN provider logs include identifiers THEN they SHALL avoid raw secrets and avoid dumping full tool payloads.
- WHEN `AgentState` audit fields contain large provider results THEN they SHALL be truncated/sanitized to bounded metadata.
- WHEN frontend clients only understand the old final-response shape THEN the `final` SSE event SHALL preserve the `AgentResponse` JSON payload.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| AHR-MCP-01 | P1: MCP Tool Providers | Design | Pending |
| AHR-MCP-02 | P1: MCP Tool Providers | Design | Pending |
| AHR-MCP-03 | P1: MCP Tool Providers | Design | Pending |
| AHR-MCP-04 | P1: MCP Tool Providers | Design | Pending |
| AHR-RAG-01 | P1: RAG Through Chroma Provider | Design | Pending |
| AHR-RAG-02 | P1: RAG Through Chroma Provider | Design | Pending |
| AHR-RAG-03 | P1: RAG Through Chroma Provider | Design | Pending |
| AHR-SSE-01 | P1: Typed SSE Streaming | Design | Pending |
| AHR-SSE-02 | P1: Typed SSE Streaming | Design | Pending |
| AHR-SSE-03 | P1: Typed SSE Streaming | Design | Pending |
| AHR-SSE-04 | P1: Typed SSE Streaming | Design | Pending |
| AHR-CHK-01 | P1: SQLite Checkpointing | Design | Pending |
| AHR-CHK-02 | P1: SQLite Checkpointing | Design | Pending |
| AHR-CHK-03 | P1: SQLite Checkpointing | Design | Pending |
| AHR-STATE-01 | P1: AgentState Audit Fields | Design | Pending |
| AHR-STATE-02 | P1: AgentState Audit Fields | Design | Pending |
| AHR-STATE-03 | P1: AgentState Audit Fields | Design | Pending |
| AHR-MEM-01 | P1: AgentState Audit Fields | Design | Pending |
| AHR-REG-01 | P1: Regression Preservation | Design | Pending |
| AHR-REG-02 | P1: Regression Preservation | Design | Pending |
| AHR-REG-03 | P1: Regression Preservation | Design | Pending |
| AHR-DOC-01 | P1: Regression Preservation | Design | Pending |
| AHR-INS-01 | P2: Insights Preparation | - | Pending |

**Coverage:** 23 total, 0 mapped to tasks, 23 unmapped.

---

## Success Criteria

- [ ] The guide's current architecture gaps are either implemented or explicitly moved to P2/out of scope.
- [ ] Existing 3 conversation scenarios keep their observable outcomes.
- [ ] Specialists no longer import MCP server functions directly for runtime behavior covered by providers.
- [ ] `POST /api/chat` emits typed SSE events and preserves final `AgentResponse`.
- [ ] Graph runtime uses SQLite-backed checkpointing by session/thread.
- [ ] `AgentState` audit fields are populated in tests for Atendimento, Transacoes, Orcamento and Validator rejection.
- [ ] Provider fallback behavior is tested for startup/runtime failure.
- [ ] `presentation-guide.md` is updated after implementation to reflect the new state.
