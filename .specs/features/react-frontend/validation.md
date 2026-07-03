# React Frontend Validation

**Date**: 2026-07-03
**Spec**: `.specs/features/react-frontend/spec.md`
**Diff range**: `228ccb9..HEAD` (commit `5117642` excluído do escopo — pré-existente, não relacionado a esta feature; `.specs/features/financial-assistant/presentation-guide.md` e `presentation-guide.md` na raiz também excluídos — ruído externo pré-existente)
**Verifier**: independent sub-agent (author ≠ verifier)

---

## Task Completion

| Task | Status  | Notes |
| ---- | ------- | ----- |
| T1   | ✅ Done | JSON auth endpoints — evidência confirmada |
| T2   | ✅ Done | GET /api/auth/me — evidência confirmada |
| T3   | ✅ Done | GET /api/dashboard/summary — evidência confirmada, mas ver GAP mês inválido |
| T4   | ✅ Done | GET /api/transactions — evidência confirmada, mesmo GAP mês inválido |
| T5   | ✅ Done | CORS + mount /api — confirmado, testado |
| T6   | ✅ Done | Scaffold Vite+React+TS |
| T7   | ✅ Done | Tailwind + tokens |
| T8   | ✅ Done | App shell + router |
| T9   | ✅ Done | Login page — implementada, mas ver GAP crítico de sincronização pós-login |
| T10  | ✅ Done | Register page — mesmo GAP crítico |
| T11  | ✅ Done | useAuth + ProtectedRoute implementados; `ProtectedRoute` sem teste dedicado |
| T12  | ✅ Done | Dashboard summary cards |
| T13  | ✅ Done | Filtros + tabela — filtros sem teste dedicado |
| T15  | ✅ Done | Chat SSE — comportamento implementado, cobertura de teste parcial (ver detalhes) |
| T17  | ✅ Done | Static mount + fallback SPA — implementado com abordagem de middleware (não catch-all route), testado |
| T18  | ✅ Done | Remoção Jinja2 confirmada por deleção de arquivos + diff stat |
| T19  | ✅ Done | A11y + BRL — implementado e testado |

**Nota de arquitetura (não é gap)**: T17 não foi implementado como uma rota catch-all `/{full_path:path}` com checagem `full_path.startswith("/api/")` como a premissa desta auditoria sugeria. Em vez disso, `main.py` usa um **middleware HTTP** que roda `call_next` primeiro e só cai no fallback SPA quando a resposta real é 404, checando `request.url.path.startswith("/api/")` antes de servir o `index.html` (`src/financial_assistant/main.py:78-93`). O próprio docstring do módulo (linhas 6-14) justifica a escolha: uma rota catch-all seria capturada antes de rotas adicionadas depois via `app.include_router`/testes, enquanto o middleware é garantidamente "por último" por construção. Avaliação: solução válida e mais robusta que a premissa; não é um desvio de spec (DEPLOY-01 não prescreve a técnica, só o comportamento observável).

---

## Spec-Anchored Acceptance Criteria

### P1: Autenticação via SPA

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| -------------------------- | --------------------- | ------------------------ | ------ |
| AC1 — Register válido → conta + cookie httpOnly + redirect `/dashboard` | Conta criada, `Set-Cookie` httpOnly, navegação real para `/dashboard` | Backend: `src/financial_assistant/api/auth_router.py:46-47` + `tests/integration/test_api_auth.py:76-81` (`assert "httponly" in set_cookie`) — ✅. Frontend: `frontend/src/pages/Register.tsx:42` `navigate("/dashboard")`, mas **reproduzido empiricamente** (teste ad-hoc nesta auditoria, descartado após uso) que o fluxo real com `AuthProvider`+`ProtectedRoute` reais **não chega ao dashboard** — ver detalhe abaixo | ❌ **GAP crítico** |
| AC2 — Email duplicado → "Email já cadastrado" sem criar conta | Mensagem exata, 0 conta nova | `tests/integration/test_api_auth.py:104-109` `assert second.json() == {"detail": "Email já cadastrado"}` + `assert len(users) == 1`; `frontend/src/pages/Register.test.tsx:69-85` `findByText("Email já cadastrado")` | ✅ PASS |
| AC3 — Login válido → cookie httpOnly + redirect `/dashboard` | Idêntico ao AC1 para login | Backend: `tests/integration/test_api_auth.py:138-149` — ✅. Frontend: mesmo defeito do AC1 (`Login.tsx:33` `navigate("/dashboard")` sem sincronizar `AuthProvider`) | ❌ **GAP crítico** (mesma causa raiz do AC1) |
| AC4 — Credenciais inválidas → "Email ou senha inválidos" genérica | Mesma mensagem para email inexistente e senha errada | `tests/integration/test_api_auth.py:164` e `:180` — ambos `assert resp.json() == {"detail": "Email ou senha inválidos"}` (dois cenários distintos, mesma assertion, prova não-diferenciação) | ✅ PASS |
| AC5 — "Sair" limpa cookie e redireciona `/login` | Cookie limpo + navegação `/login` | Backend: `src/financial_assistant/api/auth_router.py:107-112` + `tests/integration/test_api_auth.py:187-196` (`assert resp.json() == {"ok": True}`, cookie ausente) — ✅. Handler: `frontend/src/layouts/AppLayout.tsx:11-14` (`await logout(); navigate("/login")`) existe e é coerente, mas **nenhum teste** (`AppLayout.test.tsx` não existe) exercita o clique + navegação real | ⚠️ PASS parcial — backend e hook testados; navegação do clique real não coberta (evidence-or-zero: sem file:line de teste, conta como não coberto para a parte de navegação) |
| AC6 — Visitante em `/dashboard` ou `/chat` → `/login` | Redirect para `/login` | `frontend/src/components/ProtectedRoute.tsx:11-13` implementa corretamente; **nenhum `ProtectedRoute.test.tsx` existe** — busca confirmada em todo `frontend/src/**/*.test.tsx` | ❌ **GAP** (evidence-or-zero: comportamento correto por leitura de código, mas sem `file:line` de teste que o exercite) |

**Achado crítico (AC1/AC3), com evidência empírica**: `Login.tsx` e `Register.tsx` chamam `navigate("/dashboard")` diretamente após um POST bem-sucedido, mas nunca atualizam o `AuthProvider` (`frontend/src/hooks/useAuth.tsx:22-70`), que só popula `user` uma única vez, no mount, via `GET /api/auth/me` (linhas 26-58) — não há `refetch()`, `setUser()`, nem `invalidateQueries` disparado a partir de `Login.tsx`/`Register.tsx`. Como `ProtectedRoute` (`ProtectedRoute.tsx:11-13`) decide o redirect com base nesse mesmo contexto React (não recarrega a página), a navegação client-side para `/dashboard` colide com um `user` ainda `null` do fetch de mount anterior ao login, e `ProtectedRoute` reenvia o usuário de volta para `/login`.

Reproduzido nesta auditoria com um teste ad-hoc (montando `AuthProvider` + `ProtectedRoute` + `Login` reais, sem rota fake) em estado descartável — o teste falhou por timeout esperando a tela do dashboard, confirmando que o app trava no formulário de login mesmo após a API responder 200 com sucesso. O arquivo de reprodução foi removido da árvore real após a checagem (não commitado). Os testes existentes de `Login.test.tsx`/`Register.test.tsx` não pegam isso porque usam uma rota `/dashboard` fake fora de `AuthProvider`/`ProtectedRoute` reais (`Register.test.tsx:12`, `<div>Dashboard Page</div>` isolado).

**Impacto**: no MVP real (browser, sem reload completo), um usuário que loga ou se registra pela primeira vez na sessão SPA fica preso na tela de login/registro — quebra o Success Criteria do spec ("Usuário completa fluxo register → dashboard → chat → logout em < 3 minutos") e o Independent Test da própria story P1 Auth.

**Edge case do spec** ("cookie expirou → 401 → SPA redireciona `/login` com 'Sessão expirada'"): busca por `"Sessão expirada"` em `frontend/src` e `src/` — zero ocorrências fora do próprio texto do spec.md. Não implementado. `lib/api.ts` é um wrapper simples sem interceptor de 401 pós-mount.

| Edge case | file:line | Result |
| --------- | --------- | ------ |
| Cookie expirado → 401 → redirect `/login` com "Sessão expirada" | Nenhuma ocorrência em código de produção | ❌ GAP |

---

### P1: Dashboard financeiro

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | --------------------- | ------------------------ | ------ |
| AC1 — receita/despesa total + 5 cards com progress bar e % | income, expense, 5 categorias com pct | `tests/integration/test_api_dashboard.py:118-131` `assert body["total_income"] == "5000.00"`, `assert len(body["categories"]) == 5`; render: `frontend/src/components/CategoryCard.tsx:25-31` (barra + `pct.toFixed(0)`) | ✅ PASS (backend forte; frontend sem teste de página completa `Dashboard.test.tsx`, mas subcomponentes testados) |
| AC2 — status `alerta` destaca visualmente o card | Cor/ícone de alerta distinto de `ok` | `frontend/src/components/CategoryCard.test.tsx:29-37` — `queryByText(/alerta/i)` ausente quando `ok`, presente quando `alerta`; origem do status: `src/financial_assistant/domain/services/budget_service.py:155` `status="alerta" if is_alert else "ok"`, testado em `test_api_dashboard.py:131` | ✅ PASS |
| AC3 — sem receita → aviso orientando registrar pelo chat | Aviso visível + orientação | Backend: `test_api_dashboard.py:151-157` só verifica `warning` é string não vazia (não o texto literal). Frontend: `frontend/src/pages/Dashboard.tsx:82-86` renderiza `{summary.warning}` + texto fixo "Registre sua receita pelo chat" — **sem teste de frontend** que verifique essa renderização | ⚠️ SPEC-PRECISION GAP — comportamento existe, mas nenhum teste (back ou front) verifica o texto exato/a presença da orientação ao chat |
| AC4 — filtro de mês/categoria atualiza tabela sem reload | Refetch client-side via TanStack Query | `frontend/src/pages/Dashboard.tsx:57-61` `useQuery({queryKey:["transactions", month, category], ...})` — comportamento plausível por leitura de código; **nenhum teste de frontend** (`Dashboard.test.tsx` inexistente) exercita a troca de filtro na página React | ❌ GAP (evidence-or-zero — sem file:line de teste) |
| AC5 — tabela vazia → estado vazio com mensagem clara | Mensagem clara, sem tabela | `frontend/src/components/TransactionTable.test.tsx:24-32` `getByText("Nenhuma transação encontrada para este filtro.")` + `queryByRole("table")` ausente | ✅ PASS |

**GAP crítico adicional, comprovado por execução real nesta auditoria** (não estava nos 6+5+5+4+3 critérios textuais, mas é o edge case explícito do spec):

> "WHEN filtro de mês tem formato inválido THEN API retorna 400 e SPA SHALL resetar para mês atual"

Reproduzido com `TestClient` + fixture de DB de teste idêntica à usada em `test_api_dashboard.py` (registrar usuário, então `GET /api/dashboard/summary?month=not-a-month`): a chamada propaga um `ValueError: invalid literal for int() with base 10: 'not'` não tratado, originado em `src/financial_assistant/domain/repositories/transaction_repository.py:36` (`_month_bounds`, `year, mon = (int(part) for part in month.split("-"))`), sem `try/except` ao redor em `src/financial_assistant/api/dashboard_router.py` (o único `except ValueError` do arquivo, linhas 54-56, cobre apenas `_parse_category`, não o parâmetro `month`). Isso resulta em **500 Internal Server Error**, não os 400 exigidos pelo spec. `Dashboard.tsx:30-41` só trata `response.status === 400` para resetar o mês — como a API nunca retorna 400 nesse cenário, o reset automático do frontend nunca é acionado.

| Edge case | file:line + evidência | Result |
| --------- | ---------------------- | ------ |
| Mês inválido → 400 + reset frontend | `src/financial_assistant/domain/repositories/transaction_repository.py:36` (raiz do 500); `src/financial_assistant/api/dashboard_router.py:54-56` (except só cobre categoria); reproduzido com TestClient nesta auditoria (script descartado, não commitado) | ❌ **GAP crítico** |

---

### P1: Chat conversacional

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | --------------------- | ------------------------ | ------ |
| AC1 — msg do usuário imediata + "digitando..." | Aparece na tela + indicador visível | Estado: `frontend/src/hooks/useChat.test.ts:47-58` (`messages` contém a msg do usuário, `isSending=true`). Indicador visual: `frontend/src/pages/Chat.tsx:70-74` existe no código, mas **nenhum teste renderiza `Chat.tsx`** (não existe `Chat.test.tsx`) para verificar a presença do texto "digitando..." no DOM | ⚠️ GAP parcial — estado do hook testado; renderização visual não testada |
| AC2 — SSE `data:` renderiza texto + `metadata.sources` como citações | Texto + citações se presentes | `useChat.test.ts:60-85` cobre o texto com `metadata: {}` (vazio) — **nenhum teste usa `metadata.sources` preenchido**; renderização das citações em `Chat.tsx:57-65` sem teste | ❌ GAP — a parte "se presente" do critério (sources) não tem evidência alguma |
| AC3 — `event: done` reabilita campo de entrada | Campo reabilitado (efeito no DOM) | `useChat.test.ts:87-103` testa apenas `isSending=false` (variável de estado); nenhum teste renderiza `Chat.tsx` e verifica `input`/`disabled` real | ⚠️ SPEC-PRECISION GAP — asserção testa a causa (estado), não o efeito observável exigido pela letra do critério |
| AC4 — falha (401/500/timeout) exibe erro + permite retry | Erro na conversa + retry disponível | `useChat.test.ts:105-140` testa erro genérico (`new Error("network fail")`) e que `onerror` relança para impedir retry automático da lib — **não diferencia 401/500/timeout**, nem testa o clique manual em "Tentar novamente" (`Chat.tsx:36-42`) | ❌ GAP — comportamento genérico testado; diferenciação por causa e fluxo de retry manual, não |
| AC5 — abrir `/chat` gera ou reutiliza `session_id` em `sessionStorage` | Gera novo OU reutiliza existente | `useChat.test.ts:142-146` testa apenas geração (mock de `crypto.randomUUID`) — **reutilização de um `session_id` pré-existente não tem teste** | ⚠️ GAP parcial — metade do critério ("ou reutilizar") sem evidência |

| Edge case | file:line | Result |
| --------- | --------- | ------ |
| Mensagem vazia bloqueia envio | `frontend/src/pages/Chat.tsx:11,88` (`canSend`/`disabled={!canSend}`) implementado; zero teste (`Chat.test.tsx` inexistente) | ❌ GAP de cobertura (comportamento correto no código) |
| SSE >120s cancela e exibe timeout | `useChat.ts:6,36,74-77` (`REQUEST_TIMEOUT_MS = 120_000`, `AbortController`, mensagem diferenciada) implementado; zero teste com fake timers | ❌ GAP de cobertura (comportamento correto no código) |

**Nota**: o backend `/api/chat` é pré-existente (não criado por esta feature) e mantém cobertura própria em `tests/integration/test_chat.py` (401 e fluxo SSE feliz) — fora do escopo de auditoria desta feature além de confirmar que segue funcionando.

---

### P1: Shell e navegação

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | --------------------- | ------------------------ | ------ |
| AC1 — header com nome, links Dashboard/Chat, Sair | Header autenticado completo | `frontend/src/layouts/AppLayout.tsx:20-33` — implementado; **sem `AppLayout.test.tsx`** | ⚠️ GAP de cobertura (código correto, sem teste) |
| AC2 — layout responsivo mobile ≥375px | Legível em telas pequenas | Classes Tailwind responsivas confirmadas (`Dashboard.tsx:103` `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`, `AppLayout.tsx:18` `flex-wrap`); nenhum teste de viewport | ⚠️ SPEC-PRECISION GAP — "legível" não é operacionalizável sem teste visual/viewport; classes existem mas não são verificadas automaticamente |
| AC3 — `/` sem auth → `/login` | Redirect | `frontend/src/App.tsx:12-20` `RootRedirect` — `Navigate to={user ? "/dashboard" : "/login"}`; sem `App.test.tsx` | ⚠️ GAP de cobertura (lógica correta e coerente com `ProtectedRoute`) |
| AC4 — `/` autenticado → `/dashboard` | Redirect | Mesma linha `App.tsx:19` | ⚠️ GAP de cobertura (mesma ressalva) |

| Requisito técnico | Evidência | Result |
| ------------------ | --------- | ------ |
| DEPLOY-01 (StaticFiles + fallback) | `src/financial_assistant/main.py:73-93`; testado em `tests/integration/test_static_spa.py` (3 testes, executados nesta auditoria — passam) | ✅ PASS |
| DEPLOY-01 edge case (build ausente → 503, não 404 silencioso) | `main.py:90-93`; `tests/integration/test_static_spa.py:55-62` `test_missing_build_returns_503_with_clear_message` — executado, passa | ✅ PASS |
| Fallback nunca mascara `/api/*` | `main.py:84-88` `if request.url.path.startswith("/api/"): return response` | ⚠️ Ver **Sensor de discriminação, mutação 3** — teste existente (`test_unmatched_api_route_returns_404_not_the_spa`) **sobrevive** à remoção dessa checagem, porque o cenário testado (`/api/rota-que-nao-existe`) já produz 404 nativo do roteador FastAPI antes do middleware entrar em jogo, tornando a asserção atual não-discriminante para essa linha específica |
| CORS-01 | `main.py:59-65`; `tests/integration/test_api_cors.py:26-47` — executado, passa | ✅ PASS |

---

### P2: Polish visual e acessibilidade

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | --------------------- | ------------------------ | ------ |
| AC1 — outline visível em foco via teclado | Foco visível WCAG 2.1 AA | `FOCUS_RING` replicado em `AppLayout.tsx:4-5`, `Login.tsx:41-42`, `Register.tsx:50-51`, `Chat.tsx:4-5`, `TransactionFilters.tsx:4`; testado em `Login.test.tsx:91-96`, `Register.test.tsx:110-115` — **mutação 1 do sensor confirmou discriminação** (ver abaixo) | ✅ PASS (com nota: string duplicada em 5 arquivos, sem util central — risco de drift, não é bug) |
| AC2 — erro associado ao campo via `aria-describedby` | Associação campo↔erro | `Login.tsx:71-72`, `Register.tsx:90-91`; testado em `Login.test.tsx:69-89`, `Register.test.tsx:87-108` | ✅ PASS (nota: erro sempre associado ao campo senha mesmo quando a causa é o email — decisão documentada em comentário no código, cumpre a letra do critério) |
| AC3 — valores monetários em BRL | `R$ 1.234,56` | `frontend/src/components/Money.tsx:6-9,12` `Intl.NumberFormat("pt-BR", {style:"currency", currency:"BRL"})`; testado em `CategoryCard.test.tsx:20-27`, `TransactionTable.test.tsx:20` | ✅ PASS |

**Status geral**: ❌ Gaps reais presentes (2 críticos de comportamento + múltiplos gaps de cobertura de teste) + ⚠️ spec-precision gaps flagados.

---

## Discrimination Sensor

| # | File:line | Descrição | Resultado |
| - | --------- | --------- | --------- |
| 1 | `frontend/src/components/CategoryCard.tsx:7` | `category.status === "alerta"` → `!==` (inverte a condição de destaque visual de alerta) | ✅ **Killed** — `CategoryCard.test.tsx` (`status alerta exibe destaque visual ausente quando status ok`) falhou corretamente, detectando o `<span>Alerta</span>` inesperado |
| 2 | `frontend/src/hooks/useAuth.tsx:32` | `if (!response.ok)` → `if (response.ok)` (inverte o guard de 401 no `GET /api/auth/me`, faria usuário 401 ser tratado como autenticado) | ✅ **Killed** — 3 testes de `useAuth.test.tsx` falharam (popula user em 200 esperado ficou null; user null em 401 esperado ficou populado com corpo de erro; logout não voltou a null) |
| 3 | `src/financial_assistant/main.py:84-88` | Removida a checagem `if request.url.path.startswith("/api/"): return response` no middleware `spa_fallback` (guard que impede o fallback SPA de mascarar 404s de API) | ❌ **Survived** — `tests/integration/test_static_spa.py::test_unmatched_api_route_returns_404_not_the_spa` continua passando, porque `/api/rota-que-nao-existe` já é 404 nativo do roteador do FastAPI (nenhuma rota interna colide com o path), então o `call_next` já retorna 404 puro sem texto de SPA independentemente da checagem removida. O teste não força o cenário em que a checagem realmente importaria — nenhum endpoint real do backend expõe um caminho onde um handler interno gera 404 (todos os 404 de rota são nativos do roteador) — |

**Sensor depth**: lightweight (3 mutações, código novo desta feature)
**Resultado**: 2/3 killed — 1 sobrevivente (mutação 3)

**Análise da mutação 3 sobrevivente**: não é exatamente um "teste fraco" no sentido de assert vago — é uma linha de código defensiva que, dado o design atual (todas as rotas de API são registradas explicitamente via `app.include_router(api_router, prefix="/api")`, sem handlers que retornem 404 programaticamente dentro de `/api/*`), atualmente não tem nenhum caminho de execução observável que a torne necessária. Ela protegeria contra uma regressão futura (ex.: um endpoint que hoje retorna 404 de dentro do handler, ou uma futura rota de API cujo sub-recurso não exista). O teste teria que ser reforçado adicionando (ou o próprio backend precisaria expor) um cenário de 404 *originado dentro* de um handler `/api/*` para discriminar essa linha. Classificado como spec-precision/test-strength gap de baixo risco — a checagem em si está correta e é boa prática defensiva, mas carece de um teste que a torne falseável.

---

## Interactive UAT Results

Não realizado — fora do escopo desta rodada (validação automatizada com evidence-or-zero + sensor de mutação, conforme solicitado). Os GAPs críticos encontrados (login/registro não sincronizam o AuthProvider; mês inválido gera 500) são comportamentais e já confirmados por execução real, dispensando UAT manual para sua detecção.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| No features beyond what was asked | ✅ |
| No abstractions for single-use code | ✅ |
| No unnecessary "flexibility" added | ✅ |
| Only touched files required for task | ✅ |
| Didn't "improve" unrelated code | ✅ |
| Matches existing patterns/style | ✅ |
| Would senior engineer approve? | ⚠️ Não sem antes corrigir o GAP crítico de sincronização pós-login/registro — é um bug funcional que quebra o fluxo principal do MVP |
| Tests map to acceptance criteria and are non-shallow (spot-check: Auth story) | ⚠️ Parcial — testes de Login/Register usam rota fake fora do `AuthProvider` real, o que mascarou o GAP crítico; testes de `useAuth`/`CategoryCard` são não-shallow e discriminantes (confirmado pelo sensor) |
| Spec-anchored outcome check (asserted values match spec-defined outcome) | ⚠️ Maioria PASS; found gaps: aviso "sem receita" só checa "string não vazia" no backend (não o texto), reabilitação do chat input testada via estado interno não via efeito DOM |
| Per-layer Coverage Expectation met (domain 1:1 ACs; routes happy+edge+error) | ❌ Edge case do spec (mês inválido → 400) não tem NENHUM teste, backend ou frontend — nem happy nem error path cobre esse cenário, e a implementação real falha (500) |
| Every test in scope maps to a spec AC/edge case/Done-when (no unclaimed tests) | ✅ |
| Documented project quality/testing guidelines followed | `pyproject.toml` (pytest markers `unit`/`integration`) — seguido; frontend usa Vitest + Testing Library como strong default, sem guideline formal documentada além do próprio tasks.md |

❌ Dois itens "No"/parcial acima → feature NÃO pronta para marcar como concluída sem fix.

---

## Edge Cases

- [x] Mensagem vazia bloqueia envio no chat: implementado, sem teste (GAP de cobertura, não de comportamento)
- [x] SSE >120s cancela e mostra timeout: implementado, sem teste (GAP de cobertura)
- [ ] Cookie JWT expirado → 401 → "Sessão expirada": **NÃO implementado** (GAP real)
- [ ] Mês inválido → API 400 + reset frontend: **NÃO implementado corretamente — API retorna 500** (GAP crítico real, comprovado por execução)
- [x] Backend 500 → mensagem genérica + retry: coberto no chat (`useChat.ts` erro genérico), não testado para status específicos
- [x] Build React ausente → 503 com mensagem clara: implementado e testado (`test_static_spa.py`)

---

## Gate Check

- **Gate command**: `.venv/bin/python -m pytest -q -m "unit or integration"` (backend) + `cd frontend && npm run test -- --run && npm run build` (frontend)
- **Resultado backend**: 200 passed, 1 deselected, 0 failed
- **Resultado frontend (Vitest)**: 25 passed (6 arquivos), 0 failed
- **Resultado frontend (build)**: `tsc -b && vite build` — sucesso, sem erros
- **Test count before feature**: 200 (baseline informada e confirmada por leitura de commits/diff)
- **Test count after feature**: 200 (Fase 1 adicionou 21 testes de API JSON; T18 removeu ~27 testes HTML-only líquidos migrando ~4 equivalentes para `/api/*` — waterline coincidente confirmada por diff stat: `test_dashboard.py` -304 linhas e `test_templates.py` -72 linhas deletados; `test_api_auth.py` +232, `test_api_cors.py` +47, `test_api_dashboard.py` +337, `test_static_spa.py` +62 adicionados)
- **Delta**: 0 líquido — não é regressão, é o resultado esperado e documentado na spec/commit `88bcbd2` ("Net: 224 -> 200 passing")
- **Skipped tests**: 1 deselecionado (`test_delivery_categorization_prazeres_real_deepseek`, teste real contra LLM externo, fora do marker `unit or integration` — pré-existente, não relacionado a esta feature)
- **Failures**: nenhuma no gate automatizado. Os GAPs críticos encontrados (sincronização pós-login, mês inválido → 500) **não são detectados pela suíte de testes existente** — foram encontrados por reprodução manual/ad-hoc nesta auditoria, fora do gate padrão.

---

## Fix Plans

### Fix 1 (Blocker): Login/Register não sincronizam `AuthProvider` antes de navegar para `/dashboard`

- **Root cause**: `Login.tsx:33` e `Register.tsx:42` chamam `navigate("/dashboard")` diretamente após o POST bem-sucedido, sem atualizar o contexto `AuthProvider` (`useAuth.tsx`), que só busca `/api/auth/me` uma vez no mount. `ProtectedRoute` usa esse mesmo contexto e vê `user=null`, redirecionando de volta para `/login`.
- **Fix task**: Após sucesso em `Login.tsx`/`Register.tsx`, atualizar o estado de `user` no `AuthProvider` antes de navegar — expor um `setUser`/`refetch` em `useAuth.tsx` e chamá-lo com os dados retornados pelo POST (que já incluem `{user: {...}}`), ou disparar um novo fetch de `/api/auth/me` e aguardar antes do `navigate`.
- **Verify**: Adicionar um teste que monte `AuthProvider` + `ProtectedRoute` + `Login`/`Register` reais (não a rota fake atual) e confirme que, após submit bem-sucedido, a rota protegida renderiza sem novo redirect para `/login`.
- **Priority**: Blocker — quebra o fluxo principal do MVP (login/registro → dashboard) na primeira navegação de cada sessão SPA.

### Fix 2 (Blocker): `GET /api/dashboard/summary` e `GET /api/transactions` retornam 500 (não 400) para `month` malformado

- **Root cause**: `src/financial_assistant/domain/repositories/transaction_repository.py:36` (`_month_bounds`) levanta `ValueError` sem tratamento; `src/financial_assistant/api/dashboard_router.py` só captura `ValueError` para `_parse_category` (linhas 54-56), não para `month`.
- **Fix task**: Validar/capturar o `ValueError` de `_month_bounds` (ou validar o formato de `month` antes de chamá-la) em `dashboard_router.py`, retornando 400 com mensagem clara, espelhando o tratamento já existente para categoria inválida.
- **Verify**: `tests/integration/test_api_dashboard.py` — adicionar caso `GET .../summary?month=not-a-month` e `GET .../transactions?month=2026-13`, ambos esperando 400. Frontend: confirmar que `Dashboard.tsx`'s `InvalidMonthError` branch reseta o mês quando a API responde 400 real.
- **Priority**: Blocker — viola edge case explícito do spec, comprovado por execução real nesta auditoria.

### Fix 3 (Major): Cobertura de teste ausente em pontos-chave de navegação e chat

- **Root cause**: `ProtectedRoute.tsx`, `App.tsx` (`RootRedirect`), `AppLayout.tsx`, `Dashboard.tsx`, `TransactionFilters.tsx` e `Chat.tsx` não têm testes de componente dedicados — a suíte de 25 testes cobre hooks e subcomponentes isoladamente, mas não os fluxos de integração de página inteira. Isso permitiu que o Fix 1 passasse despercebido pela suíte automatizada.
- **Fix task**: Adicionar `ProtectedRoute.test.tsx`, `Dashboard.test.tsx` (cobrindo troca de filtro sem reload e o aviso de "sem receita"), `Chat.test.tsx` (indicador "digitando...", botão desabilitado em mensagem vazia, `metadata.sources` renderizado, timeout 120s com fake timers).
- **Priority**: Major — não bloqueia funcionalidade per se, mas é a lacuna estrutural que permitiu os dois Blockers acima passarem no gate verde.

### Fix 4 (Minor): Mutação 3 do sensor sobreviveu — guard `/api/` no fallback SPA sem teste discriminante

- **Root cause**: `test_unmatched_api_route_returns_404_not_the_spa` usa um path (`/api/rota-que-nao-existe`) que já produz 404 nativo do roteador, tornando a checagem explícita em `main.py:84` não-observável pelo teste atual.
- **Fix task**: Não é necessário mudar o código de produção (a checagem é boa prática defensiva e correta). Fortalecer o teste — ou documentar explicitamente por que a linha é defensiva e aceitável sem teste discriminante atual (nenhum endpoint real gera 404 de dentro de um handler `/api/*` hoje).
- **Priority**: Minor — risco baixo, comportamento atual correto, apenas a rede de segurança de teste é fraca para essa linha específica.

---

## Requirement Traceability Update

| Requirement ID | Previous Status | New Status |
| --------------- | ---------------- | ----------- |
| AUTH-API-01 | Done (T1) | ✅ Verified |
| AUTH-API-02 | Done (T1) | ✅ Verified |
| AUTH-API-03 | Done (T2) | ✅ Verified |
| AUTH-API-04 | Done (T1) | ✅ Verified |
| API-DASH-01 | Done (T3) | ⚠️ Verified com ressalva — 500 em vez de 400 para mês inválido (edge case do spec) |
| API-DASH-02 | Done (T4) | ⚠️ Verified com ressalva — mesmo problema de mês inválido |
| UI-AUTH-01 | Done (T9/5751965) | ❌ Needs Fix — Login não sincroniza `AuthProvider`, quebrando o próprio AC1/AC3 de auth |
| UI-AUTH-02 | Done (T10/eb6e163) | ❌ Needs Fix — mesmo defeito em Register |
| UI-AUTH-03 | Done (T11/2271cff) | ⚠️ Verified com ressalva — `useAuth` correto e testado; `ProtectedRoute` sem teste dedicado (evidence-or-zero) |
| UI-DASH-01 | Done (T12) | ✅ Verified |
| UI-DASH-02 | Done (T13) | ⚠️ Verified com ressalva — sem teste de página completa (`Dashboard.test.tsx`) para troca de filtro sem reload |
| UI-DASH-03 | Done (T13) | ✅ Verified |
| UI-CHAT-01 | Done (T15/2964185) | ⚠️ Verified com ressalva — indicador "digitando..." sem teste de renderização |
| UI-CHAT-02 | Done (T15/2964185) | ⚠️ Verified com ressalva — `metadata.sources` sem teste |
| UI-CHAT-03 | Done (T15/2964185) | ⚠️ Verified com ressalva — reabilitação testada via estado, não via efeito DOM |
| UI-SHELL-01 | Done (T8; 2271cff) | ⚠️ Verified com ressalva — código correto, sem teste dedicado |
| UI-SHELL-02 | Done (T8; 2271cff) | ⚠️ Verified com ressalva — responsividade não é verificável automaticamente (spec-precision gap) |
| DEPLOY-01 | Done (T17/4c7a24b, T18/88bcbd2) | ✅ Verified (implementação por middleware, válida; guard `/api/` com teste não-discriminante — minor) |
| CORS-01 | Done (T5) | ✅ Verified |
| UI-A11Y-01 | Done (T19) | ✅ Verified |
| UI-A11Y-02 | Done (T19) | ✅ Verified (nota: erro sempre associado ao campo senha, decisão documentada) |
| UI-FMT-01 | Done (T12, T19) | ✅ Verified |

---

## Summary

**Overall**: ❌ Not Ready (2 gaps Blocker de comportamento real, confirmados por execução)

**Spec-anchored check**: 13/23 critérios PASS exato; 2 GAP crítico (Blocker); ~8 GAP de cobertura de teste (comportamento correto no código, sem teste); 4 spec-precision gaps flagados
**Sensor**: 2/3 mutações killed, 1 survived (minor, defensivo)
**Gate**: 225 testes passados (200 backend + 25 frontend), 0 falhas, build limpo

**O que funciona**: toda a camada de API JSON backend (auth, dashboard, transactions) está correta e bem testada; CORS; fallback SPA com 503 para build ausente; formatação BRL; foco visível; `aria-describedby`; card de alerta de categoria; estado vazio de transações; `useAuth`/`useChat` (hooks) corretamente testados e discriminantes (confirmado pelo sensor).

**Issues found**:
1. **Blocker** — Login/Register não sincronizam o `AuthProvider` antes de navegar, deixando o usuário preso na tela de login/registro na primeira sessão SPA (Fix 1).
2. **Blocker** — `month` malformado gera 500 em vez de 400 no dashboard/transactions, violando edge case explícito do spec (Fix 2).
3. **Major** — Lacuna estrutural de testes de integração de página (ProtectedRoute, Dashboard, Chat, AppLayout, App) que permitiu os dois Blockers passarem no gate verde (Fix 3).
4. **Minor** — Guard `/api/` no fallback SPA sem teste discriminante (Fix 4).

**Next steps**: Rotear Fix 1 e Fix 2 como fix tasks para um implementador (não o Verifier); Fix 3 pode ser combinado com a correção do Fix 1 (o teste que prova o Fix 1 já cobre parte do gap estrutural); Fix 4 é opcional/documentação. Re-verificar após a correção, dentro do limite de 3 rodadas fix→re-verify.
