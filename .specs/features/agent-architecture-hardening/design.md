# Agent Architecture Hardening Design

**Spec**: `.specs/features/agent-architecture-hardening/spec.md`  
**Status**: Draft

---

## Architecture Overview

Abordagem escolhida: **providers tipados + runtime incremental**, preservando os especialistas deterministicos atuais. A LLM continua classificando intent e gerando texto no Atendimento, mas o acesso a dados passa por interfaces explicitas (`FinanceToolProvider`, `ChromaToolProvider`) que usam MCP como fonte primaria e fallback in-process quando necessario.

O grafo continua com a topologia atual:

```text
orchestrator -> specialist -> validator -> END|retry
```

As mudancas entram como camadas de runtime ao redor desse fluxo:

```mermaid
flowchart TB
    API[POST /api/chat] --> SSE[SSE Event Stream]
    API --> RT[AgentRuntime]

    subgraph runtime [Agent Runtime]
        DEPS[AgentDependencies]
        FIN[FinanceToolProvider]
        CHR[ChromaToolProvider]
        CP[SQLite Checkpointer]
        EV[Stream Event Adapter]
    end

    subgraph graph [LangGraph StateGraph]
        ORCH[Orquestrador]
        ATD[Atendimento]
        TRN[Transacoes]
        ORC[Orcamento]
        VAL[Validador]
    end

    subgraph tools [MCP / Fallback]
        MCP[MCP tools via MultiServerMCPClient]
        Fallback[In-process StructuredTools]
    end

    RT --> DEPS
    DEPS --> FIN
    DEPS --> CHR
    DEPS --> CP
    DEPS --> EV
    RT --> graph
    graph --> ORCH --> ATD & TRN & ORC
    ATD & TRN & ORC --> VAL
    FIN --> MCP
    CHR --> MCP
    MCP -.failure.-> Fallback
    EV --> SSE
```

### Approach Exploration

| Approach | Summary | Pros | Cons | Verdict |
| --- | --- | --- | --- | --- |
| Providers tipados + incremental runtime | Typed providers wrap MCP/fallback tools; specialists remain deterministic; SSE/checkpointing added around current graph | Preserves behavior, testable, closes stated gaps, minimal product risk | Requires careful dependency injection and event plumbing | Chosen |
| Event bus/runner first | Build a central event bus before touching specialists | Clean streaming abstraction | Larger upfront architecture, delays MCP provider gap | Rejected for P1 |
| Agentic/ReAct tools now | Give specialists dynamic tools and let LLM decide calls | More agent-like, closer to future extensibility | Breaks deterministic finance behavior, larger regression risk, contradicts context decision | Rejected |

### Research Notes

- Installed `langgraph` version is `1.2.7`.
- Context7 docs for LangGraph checkpointing show `thread_id` is required in `configurable`, e.g. `{"configurable": {"thread_id": "1"}}`.
- Context7 docs show `SqliteSaver` lives under `langgraph.checkpoint.sqlite`, but this environment currently lacks that module while `langgraph.checkpoint.memory` exists. Design therefore adds a dependency on `langgraph-checkpoint-sqlite`.
- Context7 docs and local import check confirm custom streaming can use `get_stream_writer`; in this environment the import path is `langgraph.config.get_stream_writer`.
- `langchain-mcp-adapters` docs confirm `MultiServerMCPClient.get_tools()` returns LangChain `BaseTool` objects that can be used with LangGraph/LangChain agents.

---

## Code Reuse Analysis

### Existing Components to Leverage

| Component | Location | How to Use |
| --- | --- | --- |
| LangGraph graph | `src/financial_assistant/agents/graph.py` | Keep topology; add dependency injection, checkpointer config and streaming entrypoint |
| AgentState | `src/financial_assistant/agents/state.py` | Keep fields; make `retrieved_context`, `pending_action`, `last_tool_results` actively populated |
| Orchestrator | `src/financial_assistant/agents/orchestrator.py` | Reuse intent classification and routing |
| Atendimento | `src/financial_assistant/agents/specialists/atendimento.py` | Replace local RAG call with `ChromaToolProvider`; add streaming/event hooks |
| Transacoes | `src/financial_assistant/agents/specialists/transacoes.py` | Replace direct MCP server function imports with `FinanceToolProvider`/`ChromaToolProvider` |
| Orcamento | `src/financial_assistant/agents/specialists/orcamento.py` | Replace direct `get_budget_summary` import with `FinanceToolProvider` |
| Validator | `src/financial_assistant/agents/validator.py` | Replace direct finance function imports with `FinanceToolProvider`; keep factual checks |
| MCP client | `src/financial_assistant/mcp/client.py` | Extend from `list[BaseTool]` to a tool bundle/map with fallback awareness |
| MCP server functions | `mcp_servers/finance/server.py`, `mcp_servers/chroma/server.py` | Keep as fallback source and MCP server implementation; specialists stop importing them directly |
| SSE router | `src/financial_assistant/chat/router.py` | Replace one-event stream with typed SSE event generator |
| Existing tests | `tests/unit/*`, `tests/integration/*` | Reuse fixtures and monkeypatch style; add provider/SSE/checkpoint coverage |

### Integration Points

| System | Integration Method |
| --- | --- |
| MCP | `MultiServerMCPClient.get_tools()` produces primary tools; `StructuredTool.from_function` remains fallback |
| LangGraph checkpointing | Compile graph with SQLite checkpointer; invoke/stream with `configurable.thread_id=session_id` |
| LangGraph custom streaming | Nodes/providers emit sanitized custom events through `get_stream_writer()` when a stream context exists |
| FastAPI SSE | `POST /api/chat` maps runtime events to SSE frames |
| SQLite chat history | `_persist_turn()` remains the durable conversation history after successful final response |
| ChromaDB memory | `ChromaToolProvider.save_working_memory()` writes bounded durable facts |

---

## Components

### AgentDependencies

- **Purpose**: Single dependency object passed to graph/node construction so specialists receive providers and runtime services explicitly.
- **Location**: `src/financial_assistant/agents/runtime.py`
- **Interfaces**:
  - `build_agent_dependencies() -> AgentDependencies` - loads MCP-backed providers and runtime adapters.
  - `AgentDependencies(finance, chroma, event_emitter)` - dataclass used by graph node closures.
- **Dependencies**: `mcp.providers`, streaming event emitter.
- **Reuses**: Existing `get_mcp_tools()` behavior and provider fallback.

```python
@dataclass(frozen=True)
class AgentDependencies:
    finance: FinanceToolProvider
    chroma: ChromaToolProvider
    events: StreamEventEmitter | None = None
```

### Tool Bundle Loader

- **Purpose**: Load primary MCP tools and always retain fallback in-process tools so providers can recover from runtime failures.
- **Location**: `src/financial_assistant/mcp/client.py`
- **Interfaces**:
  - `async get_mcp_tool_bundle(client=None) -> ToolBundle`
  - `tool_map(tools: list[BaseTool]) -> dict[str, BaseTool]`
- **Dependencies**: `MultiServerMCPClient`, existing `in_process_tools()`.
- **Reuses**: `MCP_CONNECTIONS`, `_FINANCE_TOOL_FUNCS`, `_CHROMA_TOOL_FUNCS`.

```python
@dataclass(frozen=True)
class ToolBundle:
    primary: dict[str, BaseTool]
    fallback: dict[str, BaseTool]
    source: Literal["mcp", "fallback"]
```

If MCP initialization fails, `primary` and `fallback` may both point to fallback tools, with `source="fallback"`. If MCP initialization succeeds, `primary` contains MCP tools and `fallback` contains in-process equivalents.

### FinanceToolProvider

- **Purpose**: Typed runtime boundary for financial tools.
- **Location**: `src/financial_assistant/mcp/providers.py`
- **Interfaces**:
  - `create_transaction(user_id, date, description, type, amount, category=None) -> ToolResult[dict]`
  - `list_transactions(user_id, month=None, category=None, type=None) -> ToolResult[list[dict]]`
  - `get_budget_summary(user_id, month) -> ToolResult[dict]`
  - `get_balance(user_id, month=None) -> ToolResult[dict]`
  - `update_transaction(...) -> ToolResult[dict]`
  - `delete_transaction(user_id, transaction_id) -> ToolResult[dict]`
- **Dependencies**: `ToolBundle`, structured logger, optional stream emitter.
- **Reuses**: finance MCP tool names and fallback functions.

Provider rules:

- Reject missing/empty `user_id` before invoking any tool.
- Emit sanitized `tool_call` and `tool_result` events.
- Try primary tool first.
- On primary failure, log warning and try fallback equivalent.
- If fallback also fails, return/raise a typed provider error for the graph/router to emit `error`.

### ChromaToolProvider

- **Purpose**: Typed runtime boundary for semantic tools and memory.
- **Location**: `src/financial_assistant/mcp/providers.py`
- **Interfaces**:
  - `search_transactions(user_id, query, n_results=5) -> ToolResult[list[dict]]`
  - `find_similar_transactions(user_id, description, n_results=3) -> ToolResult[list[dict]]`
  - `query_knowledge(user_id, query, n_results=6) -> ToolResult[list[dict]]`
  - `get_chat_context(user_id, query, n_results=5) -> ToolResult[list[dict]]`
  - `save_working_memory(user_id, fact, metadata=None) -> ToolResult[dict]`
- **Dependencies**: `ToolBundle`, structured logger, optional stream emitter.
- **Reuses**: chroma MCP tool names and fallback functions.

Provider-specific notes:

- `query_knowledge` still requires `user_id` at provider boundary even though the underlying KB is global.
- `save_working_memory` only receives bounded/sanitized facts from specialist logic.
- Large Chroma results are reduced before entering `AgentState`.

### ToolResult And Provider Errors

- **Purpose**: Preserve tool status/source without leaking raw payload into SSE/audit logs.
- **Location**: `src/financial_assistant/mcp/providers.py`
- **Interfaces**:
  - `ToolResult[T](data: T, tool_name: str, source: "mcp"|"fallback", fallback_used: bool)`
  - `ProviderToolError(tool_name, message, recoverable=False)`
- **Dependencies**: Pydantic or dataclass only.
- **Reuses**: Existing return dict/list payloads.

Specialists use `.data` for business logic and use `.audit_metadata()` for `last_tool_results`.

### Stream Event Contracts

- **Purpose**: Typed internal event model that maps directly to SSE frames.
- **Location**: `src/financial_assistant/contracts/streaming.py`
- **Interfaces**:
  - `StreamEvent(event: StreamEventType, data: dict, sequence: int | None = None)`
  - `SseEventFrame.from_stream_event(event) -> str`
  - `format_sse_event(event_name: str, payload: dict | str) -> str`
- **Dependencies**: `pydantic`.
- **Reuses**: `AgentResponse` for `final` payload.

Allowed event names:

```python
StreamEventType = Literal[
    "message_delta",
    "tool_call",
    "tool_result",
    "final",
    "done",
    "error",
]
```

`final` data contains an `AgentResponse` JSON payload. `tool_call`/`tool_result` payloads contain only sanitized fields:

```python
{
    "agent": "transacoes",
    "tool": "create_transaction",
    "source": "mcp",
    "fallback_used": False,
    "status": "ok",
}
```

### Stream Event Emitter

- **Purpose**: Allow nodes/providers to emit events both during graph streaming and in unit tests.
- **Location**: `src/financial_assistant/agents/streaming.py`
- **Interfaces**:
  - `emit_stream_event(event: StreamEvent) -> None`
  - `InMemoryStreamEmitter` for tests.
  - `LangGraphStreamEmitter` using `langgraph.config.get_stream_writer()`.
- **Dependencies**: `langgraph.config.get_stream_writer`.
- **Reuses**: LangGraph custom stream support.

When no stream writer exists, `emit_stream_event` must be no-op or delegate to an injected test emitter. This preserves `graph.run()` compatibility.

### Graph Runtime And Checkpointing

- **Purpose**: Build compiled graphs with dependencies and checkpointing, and expose invoke/stream entrypoints.
- **Location**: `src/financial_assistant/agents/graph.py`, `src/financial_assistant/agents/checkpointing.py`
- **Interfaces**:
  - `build_graph(deps: AgentDependencies | None = None, checkpointer=None) -> CompiledStateGraph`
  - `run(user_id, session_id, message, *, graph=None, deps=None) -> AgentResponse`
  - `stream_turn(user_id, session_id, message, *, graph=None, deps=None) -> Iterator[StreamEvent]`
  - `graph_config(session_id: str) -> dict`
- **Dependencies**: `langgraph-checkpoint-sqlite`, `AgentDependencies`.
- **Reuses**: Existing `_persist_turn()`, routing functions and nodes.

Checkpoint design:

- Add dependency `langgraph-checkpoint-sqlite`.
- Add setting such as `checkpoint_db_path`, default `data/langgraph_checkpoints.sqlite`.
- Use a process-lifetime SQLite checkpointer for runtime.
- Compile with `graph.compile(checkpointer=checkpointer)`.
- Invoke/stream with `{"configurable": {"thread_id": session_id}}`.
- Tests can inject `MemorySaver` or fake checkpointer.

The checkpoint DB should be separate from `data/finance.db` to avoid coupling Alembic/domain schema with LangGraph-managed checkpoint tables.

### Specialist Node Refactors

- **Purpose**: Keep specialist behavior but route every external data operation through providers and populate audit state fields.
- **Location**: `src/financial_assistant/agents/specialists/*.py`
- **Interfaces**:
  - `atendimento_node(state, *, chroma, events=None) -> dict`
  - `transacoes_node(state, *, finance, chroma, events=None) -> dict`
  - `orcamento_node(state, *, finance, events=None) -> dict`
  - helper functions keep fake dependencies for unit tests.
- **Dependencies**: providers, streaming emitter.
- **Reuses**: existing parse/categorize/format logic.

Expected state patches:

| Specialist | State fields |
| --- | --- |
| Atendimento | `final_response`, `retrieved_context`, optional `last_tool_results` for RAG status |
| Transacoes categorize | `final_response`, `pending_action`, `last_tool_results` for similarity lookup |
| Transacoes register | `final_response`, `last_tool_results` for create result |
| Orcamento | `final_response`, `last_tool_results` for summary metadata |
| Validator rejection | `validation_attempts`, `final_response=None`, structured `agent_notes` |

### Chat Router Streaming

- **Purpose**: Convert graph runtime events into SSE frames.
- **Location**: `src/financial_assistant/chat/router.py`
- **Interfaces**:
  - `post_chat(body, user) -> StreamingResponse`
  - `_stream_turn_events(user_id, session_id, message) -> Iterator[str]`
- **Dependencies**: `agent_graph.stream_turn`, `contracts.streaming`.
- **Reuses**: Existing `ChatRequest`, `get_current_user_api`.

Compatibility:

- Old clients can keep reading the `final` event's `AgentResponse`.
- Tests update from "first data chunk is AgentResponse" to "there is a `final` event with AgentResponse and a final `done` event".

---

## Data Models

### AgentState Audit Payloads

These are stored inside existing `AgentState` fields as bounded dict/list data.

```python
RetrievedContextItem = {
    "collection": "knowledge_base",
    "doc_id": "kb-overview",
    "source": "mcp" | "fallback",
}

PendingAction = {
    "type": "offer_register",
    "description": "pedido de delivery",
    "suggested_category": "prazeres",
}

LastToolResults = {
    "tool": "get_budget_summary",
    "source": "mcp",
    "fallback_used": False,
    "status": "ok",
    "summary": {"month": "2026-07", "has_income": True},
}
```

Design rule: audit payloads may include IDs, categories, statuses, months and booleans, but should not dump full unbounded tool payloads.

### StreamEvent

```python
class StreamEvent(BaseModel):
    event: Literal["message_delta", "tool_call", "tool_result", "final", "done", "error"]
    data: dict
    sequence: int | None = None
```

### ToolResult

```python
@dataclass(frozen=True)
class ToolResult(Generic[T]):
    data: T
    tool_name: str
    source: Literal["mcp", "fallback"]
    fallback_used: bool = False

    def audit_metadata(self) -> dict: ...
```

### Working Memory Fact

P1 uses a minimal safe shape. The system should only save when a specialist has a clear, bounded fact.

```python
WorkingMemoryFact = {
    "kind": "goal" | "preference" | "note",
    "fact": str,
    "metadata": dict,
}
```

Examples:

- `{"kind": "goal", "fact": "usuario mencionou meta de viagem", "metadata": {"topic": "viagem"}}`
- `{"kind": "preference", "fact": "usuario prefere explicacoes simples", "metadata": {"source": "chat"}}`

Do not save raw full chat turns as working memory in P1.

---

## Error Handling Strategy

| Error Scenario | Handling | User Impact |
| --- | --- | --- |
| MCP init fails | Tool bundle source becomes fallback; structured warning logged | Transparent if fallback works |
| MCP runtime call fails, fallback works | Provider emits/logs fallback status and returns fallback data | Turn continues; optional sanitized tool_result marks fallback |
| MCP and fallback both fail | Provider raises `ProviderToolError`; stream emits `error`; no false assistant success persisted | User sees retry-friendly error |
| Missing `user_id` | Provider raises validation error before tool call | Internal error path; no data access |
| Chroma knowledge empty | Atendimento returns helpful PT-BR fallback, no invented ranges | User gets safe explanation to seed/try later |
| Checkpointer unavailable before graph run | Chat emits typed `error`; `_persist_turn` is not called | No false assistant message |
| SSE client disconnect | Generator stops; success persistence only happens if graph completed | User may retry |
| Validator rejects | Existing retry loop preserved; structured `agent_notes` added | User sees approved response or fallback |
| Working memory write fails | Main response can still succeed; failure logged/sanitized | User is not blocked by memory side-effect |

---

## Risks & Concerns

| Concern | Location | Impact | Mitigation |
| --- | --- | --- | --- |
| Specialists directly import MCP server functions | `src/financial_assistant/agents/specialists/transacoes.py`, `orcamento.py`, `validator.py` | MCP is not the real runtime boundary | Introduce providers and make direct imports live only in provider fallback layer |
| Atendimento RAG bypasses chroma-mcp | `src/financial_assistant/agents/specialists/atendimento.py` | Architecture docs and runtime differ | Route through `ChromaToolProvider.query_knowledge` |
| Checkpoint SQLite dependency missing | environment check: `langgraph.checkpoint.sqlite` absent | Runtime design cannot use SQLite saver until dependency added | Add `langgraph-checkpoint-sqlite` dependency and tests |
| Streaming can become fake if implemented by splitting final text | `src/financial_assistant/chat/router.py` | Misleading UX and tests | Only emit `message_delta` from real LLM streaming/custom events; deterministic nodes emit progress/tool/final |
| Provider fallback could hide real outages | `src/financial_assistant/mcp/client.py` / new providers | Hard to diagnose MCP failures | Structured logs and sanitized `tool_result` fallback metadata |
| AgentState audit fields could leak large/sensitive payloads | `src/financial_assistant/agents/state.py` consumers | Sensitive financial data in logs/SSE/tests | Store bounded metadata, not full raw payloads |
| Existing tests monkeypatch private module globals | `tests/integration/test_graph_smoke.py`, `test_conversation_scenarios.py` | Refactor may break tests noisily | Move tests to provider injection; keep regression assertions |
| `SqliteSaver.from_conn_string` lifecycle needs care | new `checkpointing.py` | Closed connection if context manager lifetime is wrong | Wrap in process-lifetime factory and test graph invocation with injected saver |

---

## Tech Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| Provider pattern | Typed domain providers over raw `BaseTool` list | Safer contracts, easier tests, no global mutable registry |
| MCP fallback | Provider-level primary/fallback call path | Startup fallback exists today; runtime fallback closes the partial-failure gap |
| Checkpoint DB | Separate SQLite file, e.g. `data/langgraph_checkpoints.sqlite` | Avoid mixing LangGraph checkpoint tables with Alembic-managed domain DB |
| Checkpoint dependency | Add `langgraph-checkpoint-sqlite` | Installed LangGraph lacks SQLite checkpointer module |
| Streaming source | LangGraph custom events via `get_stream_writer` plus final event | Uses framework-native streaming instead of ad hoc buffering |
| LLM streaming | Real deltas only from models/nodes that stream | Avoid artificial token streaming for deterministic specialists |
| Audit state | Bounded/sanitized dicts in existing state fields | Uses current `AgentState` without adding persisted schema |
| Insights | P2 only | Keeps P1 focused on hardening and regression preservation |

Project-level decisions: no new AD is required. This design conforms to AD-002 (`user_id` isolation), AD-003 (local embeddings), AD-004 (MCP subprocess + fallback) and AD-005 (React frontend as separate presentation feature).

---

## Requirement Mapping

| Requirement | Design Element |
| --- | --- |
| `AHR-MCP-01` | `AgentDependencies`, `ToolBundle`, providers |
| `AHR-MCP-02` | provider-level fallback and structured logs |
| `AHR-MCP-03` | provider `user_id` validation |
| `AHR-MCP-04` | specialist/validator refactors to providers |
| `AHR-RAG-01` | `ChromaToolProvider.query_knowledge` in Atendimento |
| `AHR-RAG-02` | `retrieved_context` audit payload |
| `AHR-RAG-03` | preserved `metadata.sources` |
| `AHR-SSE-01` | `StreamEvent` contract and chat router mapping |
| `AHR-SSE-02` | LLM streaming through custom events |
| `AHR-SSE-03` | deterministic tool/progress/final events |
| `AHR-SSE-04` | sanitized fallback/error SSE payloads |
| `AHR-CHK-01` | SQLite checkpointer factory and graph compile |
| `AHR-CHK-02` | `graph_config(session_id)` with `thread_id` |
| `AHR-CHK-03` | `_persist_turn()` retained after successful final response |
| `AHR-STATE-01` | Atendimento `retrieved_context` |
| `AHR-STATE-02` | Transacoes `pending_action` and `last_tool_results` |
| `AHR-STATE-03` | Orcamento/Validator audit state |
| `AHR-MEM-01` | `ChromaToolProvider.save_working_memory` for bounded facts |
| `AHR-REG-01` | existing conversation scenario regression tests |
| `AHR-REG-02` | delivery categorize/no auto-register regression |
| `AHR-REG-03` | budget advice regression and Validator checks |
| `AHR-DOC-01` | update `presentation-guide.md` after implementation |
| `AHR-INS-01` | providers/memory extension points, no Insights implementation |
