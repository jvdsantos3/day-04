# Agent Architecture Hardening Context

**Gathered:** 2026-07-03  
**Spec:** `.specs/features/agent-architecture-hardening/spec.md`  
**Status:** Ready for design after user review

---

## Feature Boundary

Esta feature fecha os gaps arquiteturais identificados no `presentation-guide.md` sem reescrever o produto: MCP/tools passam a ser a fronteira real de runtime via providers tipados, Atendimento usa RAG por chroma provider, SSE ganha contrato tipado, LangGraph recebe checkpointing SQLite, campos avancados do `AgentState` viram trilha de auditoria, e memoria estruturada minima passa a usar `working_memory`. O comportamento visivel dos 3 prompts principais deve ser preservado.

---

## Implementation Decisions

### Fronteira MVP

- P1 e hardening arquitetural: MCP injection, RAG via MCP/provider, streaming/SSE tipado, checkpointing e memoria usada.
- Agente Insights fica em P2: a feature deve preparar extensibilidade, mas nao implementar analise nova.
- Outputs e cenarios atuais devem ser preservados como regressao obrigatoria.
- Frontend React nao e foco; P1 muda backend/API e contrato SSE, com UI completa ficando para a feature React frontend.

### MCP E Tools

- Especialistas devem continuar deterministicos no P1: o codigo decide quando chamar cada tool.
- MCP client e a fonte primaria das tools; fallback in-process entra apenas quando MCP falha.
- Injeção deve acontecer por providers tipados por dominio, nao por lista bruta global de `BaseTool`.
- Atendimento deve trocar a tool local por `ChromaToolProvider.query_knowledge(user_id, query)`, mantendo recuperacao antes da chamada LLM.

### Memoria E Checkpointing

- Checkpointing P1 deve resolver robustez tecnica por `session_id`/thread, nao prometer workflows long-running complexos.
- Backend preferido para checkpointing: SQLite, alinhado ao banco local existente.
- `working_memory` entra com fatos estruturados minimos e seguros, nao com todos os turnos.
- `retrieved_context`, `pending_action` e `last_tool_results` devem ser preenchidos como contrato de auditoria do turno.

### Streaming E SSE

- Streaming token-a-token deve acontecer quando o especialista realmente usa LLM streaming.
- Especialistas deterministicos devem emitir eventos de progresso/tool e `final`, sem tokenizacao artificial.
- Contrato SSE deve ter eventos tipados: `message_delta`, `tool_call`, `tool_result`, `final`, `done`, `error`.
- Traces expostos devem ser sanitizados: nomes de tools, status e sources; sem payload financeiro sensivel completo.
- Backend/API deve ser testado; UI pode continuar consumindo o evento final por compatibilidade.

### Falhas, Seguranca E Observabilidade

- Falha MCP em runtime deve tentar fallback in-process, gerar log estruturado e expor status sanitizado quando relevante.
- Toda tool user-scoped deve exigir `user_id`; provider rejeita antes de chamar MCP/fallback quando ausente.
- Observabilidade P1: logs estruturados por session_id/user_id/tool/agent/attempt, sem dados sensiveis.
- Gate final: testes unit/integration por gap, smoke/regressao dos 3 prompts atuais e documentacao atualizada.

---

## Agent's Discretion

- Escolher nomes exatos dos providers/interfaces, desde que fiquem tipados por dominio e nao exponham lista global mutavel aos especialistas.
- Definir schemas internos dos eventos SSE, desde que os nomes e payload final `AgentResponse` sejam preservados.
- Definir schema minimo de fatos para `working_memory`, desde que seja pequeno, seguro e testavel.
- Escolher estrategia de sanitizacao/truncamento dos campos de auditoria no `AgentState`.

---

## Declined / Undiscussed Gray Areas -> Assumptions

- Rate limiting novo nao entra em P1; o projeto ainda nao tem camada de rate limit e o escopo atual e arquitetura interna.
- TTL/retencao de checkpoints e memoria nao entra em P1; usa persistencia local existente sem politica nova.
- UI completa de streaming/traces nao entra em P1; contrato backend deve permitir a UI futura.
- ReAct/tool-calling livre nao entra em P1; determinismo financeiro e regressao do MVP tem prioridade.

---

## Specific References

- Gaps de origem: secao "Gaps honestos do estado atual" em `presentation-guide.md`.
- Decisoes existentes: `.specs/STATE.md` AD-002 (user_id), AD-003 (embeddings locais), AD-004 (MCP subprocess + fallback), AD-005 (React frontend separado).
- Feature base ja entregue: `.specs/features/financial-assistant/`.
- Feature frontend em andamento: `.specs/features/react-frontend/`.

---

## Deferred Ideas

- Agente Insights completo com comparativo mes a mes, tendencias e export.
- UI React renderizando deltas, sources e tool traces em tempo real.
- Tool-calling agentic/ReAct para especialistas onde fizer sentido.
- Checkpointing long-running com retomada exata de node interrompido.
- Observabilidade avancada com metricas e tracing distribuido.
