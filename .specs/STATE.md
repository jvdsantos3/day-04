# STATE

## Decisions

### AD-001
- **Decision**: Stack web FastAPI + Jinja2 + HTMX para MVP
- **Reason**: Stack Python unificada; auth + dashboard + SSE sem SPA complexa
- **Trade-off**: UX menos rica que React; suficiente para MVP
- **Scope**: Todas as features web do financial-assistant
- **Date**: 2026-07-02
- **Status**: active

### AD-002
- **Decision**: Autenticação JWT em cookie httpOnly + bcrypt; dados isolados por user_id
- **Reason**: Auth simples solicitada (nome, email, senha); stateless; multi-usuário
- **Trade-off**: Sem refresh token rotation no MVP
- **Scope**: SQLite, ChromaDB, MCPs, agentes — todo acesso filtra user_id
- **Date**: 2026-07-02
- **Status**: active

### AD-003
- **Decision**: Embeddings locais via intfloat/multilingual-e5-small (384 dims)
- **Reason**: DeepSeek sem API de embeddings; zero custo; PT-BR
- **Trade-off**: Download inicial do modelo; CPU-only no dev
- **Scope**: ChromaDB collections, chroma-mcp, indexer
- **Date**: 2026-07-02
- **Status**: active

### AD-004
- **Decision**: MCPs finance-mcp e chroma-mcp como sub-processos com fallback in-process
- **Reason**: Extensibilidade e isolamento de domínio solicitados
- **Trade-off**: Latência no cold start
- **Scope**: LangGraph agents, tool loading
- **Date**: 2026-07-02
- **Status**: active

## Handoff

- **Feature**: financial-assistant / `.specs/features/financial-assistant/`
- **Phase / Task**: Design + Tasks completos — aguardando aprovação para Execute T1
- **Completed**: Specify, Design, Tasks
- **In-progress**: none
- **Next step**: Usuário aprovar design/tasks → iniciar T1 (scaffold)
- **Blockers**: none
- **Uncommitted files**: `.specs/**`
- **Branch**: _(none yet)_
