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
- **Phase / Task**: Phase 3 (Domain Services): T9 (`344a5f1`) done → T10 (BudgetService, `f7b1878`) done → T11 (contracts) pendente. Phase 4: T12 (`0661b22`), T13 (`8572145`) e T14 (indexer, `8b1c324`) done → T15 pendente.
- **Completed**: Specify, Design, Tasks, T1–T10, T12–T14
- **In-progress**: none
- **Next step**: T11 (Pydantic contracts) e/ou T15 (knowledge base + category examples seed — depende de T13/T14). VEC-01/VEC-04 ficam **Partial** até o write-through ser efetivamente disparado no CRUD real (T16 `finance-mcp.create_transaction`/`delete_transaction` devem chamar `indexer.index_transaction`/`delete_transaction_embedding`).
- **Blockers**: none — o erro de coleção do T9 (`list[...]` sombreado pelo método `list`) foi resolvido com `from __future__ import annotations` no repositório; suíte unit inteira passa (76 testes).
- **Uncommitted files**: none
- **T3 note**: `BudgetCategory`/`TransactionType` enums vivem em `domain/models.py`; T4 reutiliza `BudgetCategory` (não recriar). `Transaction.category` é nullable no DB; invariante tipo↔categoria fica no contrato Pydantic `TransactionCreate` (T11), conforme design. Alembic: `script_location` em `alembic.ini`; `env.py` lê `database_url` de `get_settings()` e importa `domain.models` para autogenerate. Rodar migrations com `.venv/bin/alembic upgrade head` (precisa `data/` existir — gitignored).
- **Spec-precision gap (T2)**: `JWT_EXPIRE_MINUTES=1440` e `DEEPSEEK_BASE_URL=https://api.deepseek.com` sem valor definido na spec — defaults escolhidos na implementação
- **T5 note (SPEC_DEVIATION)**: design named `passlib[bcrypt]`, mas passlib 1.7.4 não inicializa o backend com bcrypt 5.0.0 instalado. `auth/service.py` usa a lib `bcrypt` direto (`hash_password`/`verify_password`); `pyproject.toml` troca `passlib[bcrypt]` → `bcrypt`. T6/T7 devem reusar essas funções — não reintroduzir passlib. Gap de precisão: spec silenciosa sobre senhas >72 bytes → sem tratamento (bcrypt levanta ValueError).
- **Spec-precision gap (T4)**: Prazeres é `≥ 5%` (sem teto na spec) mas `BudgetTarget.max_pct` é float não-nulável → teto modelado como `100.0` em `domain/budget_defaults.py`. BudgetService (T10) deve tratar Prazeres como sem-alerta-por-excesso.
- **T6 note**: App factory `create_app()` em `main.py` (inclui `auth.router`); T7/T27/T29 devem registrar seus routers ali. DB dependency `get_db()` em `db/session.py` (testes fazem `app.dependency_overrides[get_db]` com SQLite `:memory:` + StaticPool — ver `tests/integration/test_auth.py` fixture `client`). `python-multipart` adicionado ao `pyproject` (parsing de `Form`). Register redireciona 303 → `/dashboard` **sem** setar cookie de sessão — auto-login/JWT é escopo do T7. Templates em `web/templates/`; `register.html` é standalone (base layout vem no T26 — pode refatorar para `extends base.html` depois). Gaps de precisão: status de erro de validação (senha curta / email duplicado) não definido na spec → escolhido `400` com re-render do form.
- **T7 note**: JWT helpers em `auth/service.py`: `create_access_token(subject)` / `decode_access_token(token) -> str|None` (HS256, `sub`=user.id, `exp` de `jwt_expire_minutes`). Cookie de sessão `access_token` (const `SESSION_COOKIE_NAME` em `auth/dependencies.py`), `httponly=True, samesite="lax"`, `max_age=jwt_expire_minutes*60`. `get_current_user` (dependency) lê o cookie, decodifica, carrega `User` por UUID e retorna; se ausente/inválido/expirado → `HTTPException(302, Location=/login?next=<path>)`. **Boundary shift**: AUTH-05 (redirect) foi implementado no T7 (não no T8) porque o teste `test_protected_route_redirect` estava no verify do T7. Stub protegido `GET /dashboard` em `web/router.py` (retorna `<h1>Olá, {name}</h1>`) — **T27 substitui** pelo dashboard real (tabela + barras). `web_router` já incluído em `main.create_app`. Login inválido devolve msg única `"Email ou senha inválidos"` (400) p/ senha errada E email inexistente (AUTH-04 — não vazar existência). Gaps de precisão: status não definidos na spec → 303 (login/logout success, POST→GET), 302 (guard redirect), 400 (falhas de form/login).
- **T8 note**: `auth/dependencies.py` agora tem **dois** dependencies compartilhando `_resolve_user(request, db) -> User|None`: `get_current_user` (rotas web → 302 redirect `/login?next=`) e **`get_current_user_api`** (rotas API → `HTTPException(401)`). T29 (`POST /api/chat`) deve usar `get_current_user_api`. Design listava só `get_current_user(token)` — o split web/API é elaboração exigida pela ação 3 do T8 (401 p/ API), não é SPEC_DEVIATION. **Ordering AUTH-06**: `test_user_isolation_in_repository` foi coberto no nível do dependency (não do `TransactionRepository`, que é T9 e ainda não existe): fixture `api_client` em `tests/integration/test_auth.py` monta uma rota-probe `GET /api/_probe/my-transactions` guardada por `get_current_user_api` que filtra `Transaction.user_id == user.id` — prova que a sessão autenticada só enxerga os próprios dados. T9 deve replicar esse isolamento dentro do `TransactionRepository` (todas as queries filtram `user_id`).
- **T12 note**: `vector/client.py` expõe `COLLECTIONS` (5 nomes), `get_chroma_client(path=None)` (PersistentClient, default = `settings.chroma_path`), `get_or_create_collections(client) -> dict[name, Collection]` (idempotente) e `require_user_id(metadata) -> dict` (guard AD-002: levanta `ValueError` se `user_id` ausente/vazio/None; retorna cópia). Módulo é **embedding-agnostic** de propósito — T13 (modelo) e T14 (indexer) geram os embeddings; o client só cria o store + coleções. T14/T17 devem reusar `require_user_id` antes de todo `add/upsert`. Testes usam `tmp_path` (não tocam `./data/chroma`) e passam embeddings explícitos p/ não baixar o modelo default do ChromaDB. Gate rodado com `.venv/bin/python -m pytest` (rtk/pytest global usa env sem o pacote instalado → "No tests collected").
- **T13 note**: `vector/embeddings.py` expõe `get_embeddings() -> HuggingFaceEmbeddings` (singleton via `lru_cache`) e as constantes `EMBEDDING_MODEL_NAME` (`intfloat/multilingual-e5-small`) e `EMBEDDING_DIMENSION` (`384`). `device="cpu"`, `normalize_embeddings=True` (cosine-ready para ChromaDB). Dependência nova `sentence-transformers` adicionada ao `pyproject.toml` (requerida pelo backend do `langchain-huggingface`; download do modelo do HF Hub confirmado funcional no ambiente — ~10s no teste). T14 deve consumir `get_embeddings()` para gerar os vetores antes do `upsert` nas coleções do T12.
- **T14 note**: `vector/indexer.py` expõe `index_transaction(user_id, transaction) -> None` e `delete_transaction_embedding(user_id, transaction_id) -> None`, ambos sem parâmetro de coleção — resolvem o client/coleção internamente via `vector.client.get_chroma_client()` + `get_or_create_collections()` (mesmo padrão de teste do T12: monkeypatch em `vector.client.get_settings` para redirecionar a um `tmp_path`). Metadata gravada: `user_id`, `transaction_id`, `category` (valor do enum ou **ausente** — chromadb 1.5.9 descarta chaves de metadata com valor `None` na escrita, então receitas simplesmente não têm a chave `category`), `amount` (float), `date` (ISO). `delete_transaction_embedding` usa `where={"user_id": ...}` combinado a `ids=[...]` — um `user_id` incorreto não apaga o vetor de outro usuário (AD-002). Qualquer falha na tentativa de indexar (embedding **ou** o próprio upsert no ChromaDB) é capturada, logada (`logger.exception`) e enfileirada em `get_pending_reindex()` (fila em memória, sem persistência — `clear_pending_reindex()` para um futuro worker consumir); a chamada nunca propaga exceção, pois o SQLite já foi gravado pelo caller antes de `index_transaction` rodar. **Pendência real**: T14 só implementa as funções — nenhum caller ainda as invoca; isso deve acontecer em T16 (`finance-mcp.create_transaction`/`update_transaction`/`delete_transaction`), por isso VEC-01/VEC-04 continuam **Partial** na tabela de rastreabilidade.
- **T10 note**: `domain/services/budget_service.py` expõe `BudgetService(session).get_summary(user_id, month="YYYY-MM")` retornando dataclasses `BudgetSummary` (`month`, `total_income: Decimal`, `has_income: bool`, `warning: str|None`, `categories: list[CategoryBudget]`) e `CategoryBudget` (`category`, `spent`, `pct: float`, `min_pct/max_pct/target_pct`, `status: "ok"|"alerta"`, `remaining_pct` = `max_pct-pct`, `over_amount: Decimal`). Regras: `%` sobre receita total do mês; `alerta` **só** quando `pct > max_pct` (BUD-02, `over_amount = spent - max%·receita`); abaixo do mínimo **não** alerta; Prazeres (`max_pct=100`) nunca alerta por excesso; receita 0 → `has_income=False` + `warning="sem receita base"` (const `NO_INCOME_WARNING`), sem percentuais. Reusa `TransactionRepository.list` (T9) p/ escopo user_id + mês. **T11** deve criar o contrato Pydantic `BudgetSummary` (design) — hoje é dataclass; **T21/finance-mcp** e **T22/agente Orçamento** consomem `get_summary` (ferramenta `get_budget_summary`); **T23/dashboard** usa os cards de `categories`. BUD-01/02/03 e CONV-03 ficam **Partial** até o agente (T22) e dashboard (T23).
- **Verify note (T10+)**: `rtk pytest`/`pytest` global NÃO coletam (pacote não instalado no env global) — rodar testes com `.venv/bin/python -m pytest tests/unit/test_budget_service.py -m unit` (suíte unit inteira: 68 testes verdes).
- **Branch**: `master` (git repo inicializado em T1)
- **Env note**: sistema sem `python3-venv`/`ensurepip`; venv em `.venv/` com pip via `get-pip.py`. Usar `.venv/bin/python` para todos os comandos.
