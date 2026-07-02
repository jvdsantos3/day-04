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
- **Phase / Task**: Phase 2 (Auth) — T7 (login/logout + JWT cookie) done; próxima T8 (auth dependency + isolation)
- **Completed**: Specify, Design, Tasks, T1, T2, T3, T4, T5, T6, T7
- **In-progress**: none
- **Next step**: Executar T8 — `get_current_user` **já existe** em `auth/dependencies.py` (criado no T7 p/ AUTH-05). T8 deve focar AUTH-06: isolamento por `user_id` no repositório e cobrir `test_user_isolation_in_repository`. Nota de ordering: esse teste depende do `TransactionRepository` (T9); confirmar se T8 roda antes de T9 ou se o teste de isolamento usa apenas queries diretas por `user_id`. Não recriar `get_current_user`.
- **Blockers**: none
- **Uncommitted files**: none
- **T3 note**: `BudgetCategory`/`TransactionType` enums vivem em `domain/models.py`; T4 reutiliza `BudgetCategory` (não recriar). `Transaction.category` é nullable no DB; invariante tipo↔categoria fica no contrato Pydantic `TransactionCreate` (T11), conforme design. Alembic: `script_location` em `alembic.ini`; `env.py` lê `database_url` de `get_settings()` e importa `domain.models` para autogenerate. Rodar migrations com `.venv/bin/alembic upgrade head` (precisa `data/` existir — gitignored).
- **Spec-precision gap (T2)**: `JWT_EXPIRE_MINUTES=1440` e `DEEPSEEK_BASE_URL=https://api.deepseek.com` sem valor definido na spec — defaults escolhidos na implementação
- **T5 note (SPEC_DEVIATION)**: design named `passlib[bcrypt]`, mas passlib 1.7.4 não inicializa o backend com bcrypt 5.0.0 instalado. `auth/service.py` usa a lib `bcrypt` direto (`hash_password`/`verify_password`); `pyproject.toml` troca `passlib[bcrypt]` → `bcrypt`. T6/T7 devem reusar essas funções — não reintroduzir passlib. Gap de precisão: spec silenciosa sobre senhas >72 bytes → sem tratamento (bcrypt levanta ValueError).
- **Spec-precision gap (T4)**: Prazeres é `≥ 5%` (sem teto na spec) mas `BudgetTarget.max_pct` é float não-nulável → teto modelado como `100.0` em `domain/budget_defaults.py`. BudgetService (T10) deve tratar Prazeres como sem-alerta-por-excesso.
- **T6 note**: App factory `create_app()` em `main.py` (inclui `auth.router`); T7/T27/T29 devem registrar seus routers ali. DB dependency `get_db()` em `db/session.py` (testes fazem `app.dependency_overrides[get_db]` com SQLite `:memory:` + StaticPool — ver `tests/integration/test_auth.py` fixture `client`). `python-multipart` adicionado ao `pyproject` (parsing de `Form`). Register redireciona 303 → `/dashboard` **sem** setar cookie de sessão — auto-login/JWT é escopo do T7. Templates em `web/templates/`; `register.html` é standalone (base layout vem no T26 — pode refatorar para `extends base.html` depois). Gaps de precisão: status de erro de validação (senha curta / email duplicado) não definido na spec → escolhido `400` com re-render do form.
- **T7 note**: JWT helpers em `auth/service.py`: `create_access_token(subject)` / `decode_access_token(token) -> str|None` (HS256, `sub`=user.id, `exp` de `jwt_expire_minutes`). Cookie de sessão `access_token` (const `SESSION_COOKIE_NAME` em `auth/dependencies.py`), `httponly=True, samesite="lax"`, `max_age=jwt_expire_minutes*60`. `get_current_user` (dependency) lê o cookie, decodifica, carrega `User` por UUID e retorna; se ausente/inválido/expirado → `HTTPException(302, Location=/login?next=<path>)`. **Boundary shift**: AUTH-05 (redirect) foi implementado no T7 (não no T8) porque o teste `test_protected_route_redirect` estava no verify do T7. Stub protegido `GET /dashboard` em `web/router.py` (retorna `<h1>Olá, {name}</h1>`) — **T27 substitui** pelo dashboard real (tabela + barras). `web_router` já incluído em `main.create_app`. Login inválido devolve msg única `"Email ou senha inválidos"` (400) p/ senha errada E email inexistente (AUTH-04 — não vazar existência). Gaps de precisão: status não definidos na spec → 303 (login/logout success, POST→GET), 302 (guard redirect), 400 (falhas de form/login).
- **Branch**: `master` (git repo inicializado em T1)
- **Env note**: sistema sem `python3-venv`/`ensurepip`; venv em `.venv/` com pip via `get-pip.py`. Usar `.venv/bin/python` para todos os comandos.
