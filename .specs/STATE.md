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
- **Phase / Task**: Phase 1 — T3 (SQLAlchemy models + Alembic init) concluída (`6dfd2eb`); próxima T4 (BudgetCategory enum já criado em models.py + seed defaults)
- **Completed**: Specify, Design, Tasks, T1, T2, T3
- **In-progress**: none
- **Next step**: Executar T4 — `seed_budget_targets(user_id)` com defaults somando 90% + teste `tests/unit/test_budget_defaults.py`
- **Blockers**: none
- **Uncommitted files**: none
- **T3 note**: `BudgetCategory`/`TransactionType` enums vivem em `domain/models.py`; T4 reutiliza `BudgetCategory` (não recriar). `Transaction.category` é nullable no DB; invariante tipo↔categoria fica no contrato Pydantic `TransactionCreate` (T11), conforme design. Alembic: `script_location` em `alembic.ini`; `env.py` lê `database_url` de `get_settings()` e importa `domain.models` para autogenerate. Rodar migrations com `.venv/bin/alembic upgrade head` (precisa `data/` existir — gitignored).
- **Spec-precision gap (T2)**: `JWT_EXPIRE_MINUTES=1440` e `DEEPSEEK_BASE_URL=https://api.deepseek.com` sem valor definido na spec — defaults escolhidos na implementação
- **Branch**: `master` (git repo inicializado em T1)
- **Env note**: sistema sem `python3-venv`/`ensurepip`; venv em `.venv/` com pip via `get-pip.py`. Usar `.venv/bin/python` para todos os comandos.
