# React Frontend Specification

## Problem Statement

O assistente financeiro entrega todas as telas via Jinja2 + HTMX servidas pelo FastAPI (AD-001). A interface funciona, mas a experiência visual é básica: layout genérico, pouca hierarquia visual, interações limitadas e sensação de protótipo. Para demonstração e uso real, o produto precisa de um frontend moderno que preserve a mesma funcionalidade (auth, dashboard, chat) com UX profissional.

## Goals

- [ ] Substituir as páginas HTML (`/login`, `/register`, `/dashboard`, `/chat`) por uma SPA React com paridade funcional com o MVP atual
- [ ] Manter autenticação JWT em cookie httpOnly (AD-002) — sem expor token ao JavaScript
- [ ] Expor APIs JSON no FastAPI para consumo pela SPA (auth, dashboard, transações); reutilizar `POST /api/chat` (SSE) existente
- [ ] Deploy unificado: build estático do React servido pelo mesmo processo FastAPI em produção

## Out of Scope

| Feature | Reason |
| ------- | ------ |
| Streaming token-a-token no chat | Especialistas usam `.invoke()` bloqueante; SSE por turno já existe |
| PWA / app mobile nativo | Escopo web desktop-first |
| Internacionalização (i18n) | App permanece PT-BR |
| Tema escuro / múltiplos temas | P2 futuro |
| Remoção dos agentes LangGraph ou MCPs | Backend inalterado na lógica de domínio |
| Novas funcionalidades de negócio (insights, filesystem-mcp) | Feature só troca a camada de apresentação |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Stack frontend | React 19 + Vite + TypeScript | Ecossistema maduro, DX rápida, alinhado ao pedido do usuário | y (pedido explícito) |
| Estilização | Tailwind CSS v4 | Produtividade + UI consistente sem CSS manual extenso | y (agent discretion) |
| Roteamento | React Router v7 | Padrão de mercado para SPA multi-página | y (agent discretion) |
| Fetch de dados | TanStack Query | Cache, loading/error states, refetch em filtros do dashboard | y (agent discretion) |
| Deploy dev | Vite proxy → `:8000` | Cookie SameSite=Lax funciona em same-origin via proxy | y |
| Deploy prod | FastAPI `StaticFiles` + fallback SPA | Um único processo/porta; sem CORS em prod | y |
| Rotas Jinja legadas | Removidas após paridade React | Evita duplicação e confusão de manutenção | y |
| AD-001 (Jinja2+HTMX) | Superseded por AD-005 | Decisão arquitetural explícita na migração | y |

**Open questions:** none — all resolved or logged above.

---

## Implicit-Requirement Dimensions (Large feature sweep)

| Dimension | Resolution |
| --------- | ---------- |
| Input validation & bounds | Formulários validam email, senha ≥8 chars no client; backend mantém validação existente |
| Failure / partial-failure states | Loading skeletons, mensagens de erro inline, toast em falha de rede; SSE timeout 120s |
| Idempotency / retry / duplicate handling | TanStack Query `retry: 1` em GET; POST auth sem retry automático |
| Auth boundaries & rate limits | Mesmas dependências `get_current_user` / `get_current_user_api`; 401 → redirect `/login` |
| Concurrency / ordering | Mensagens de chat append-only por `session_id`; dashboard refetch ao mudar filtro |
| Data lifecycle / expiry | JWT expiry inalterado; logout limpa cookie |
| Observability | Erros de API logados no console em dev; sem telemetria nova |
| External-dependency failure | Backend offline → tela de erro com retry |
| State-transition integrity | Rotas protegidas redirecionam se não autenticado; guest não acessa `/dashboard` |

---

## User Stories

### P1: Autenticação via SPA ⭐ MVP

**User Story**: Como usuário, quero me registrar e fazer login em telas React para acessar o assistente com uma interface moderna.

**Why P1**: Sem auth funcional, nenhuma outra tela é acessível.

**Acceptance Criteria**:

1. WHEN o usuário acessa `/register` e submete nome, email e senha válidos (≥8 chars) THEN o sistema SHALL criar a conta, definir cookie JWT httpOnly e redirecionar para `/dashboard`
2. WHEN o usuário submete email já cadastrado THEN o sistema SHALL exibir mensagem "Email já cadastrado" sem criar conta
3. WHEN o usuário acessa `/login` e submete credenciais válidas THEN o sistema SHALL definir cookie JWT httpOnly e redirecionar para `/dashboard`
4. WHEN o usuário submete credenciais inválidas THEN o sistema SHALL exibir "Email ou senha inválidos" (mensagem genérica, AUTH-04)
5. WHEN o usuário autenticado clica em "Sair" THEN o sistema SHALL limpar o cookie e redirecionar para `/login`
6. WHEN um visitante não autenticado acessa `/dashboard` ou `/chat` THEN o sistema SHALL redirecionar para `/login`

**Independent Test**: Registrar usuário novo, fazer logout, login novamente — cookie persiste sessão entre reload.

**Requirements**: `AUTH-API-01`, `AUTH-API-02`, `AUTH-API-03`, `AUTH-API-04`, `UI-AUTH-01`, `UI-AUTH-02`, `UI-AUTH-03`

---

### P1: Dashboard financeiro ⭐ MVP

**User Story**: Como usuário autenticado, quero ver meu resumo mensal e transações em um dashboard visual para entender minha situação financeira rapidamente.

**Why P1**: Core value proposition do produto além do chat.

**Acceptance Criteria**:

1. WHEN o usuário autenticado acessa `/dashboard` THEN o sistema SHALL exibir receita total, despesas totais e cards das 5 categorias de orçamento com barra de progresso e percentual gasto
2. WHEN uma categoria está em status `alerta` THEN o sistema SHALL destacar visualmente o card (cor/ícone de alerta)
3. WHEN não há receita registrada no mês THEN o sistema SHALL exibir aviso orientando a registrar receita pelo chat
4. WHEN o usuário altera filtro de mês ou categoria THEN o sistema SHALL atualizar a tabela de transações sem recarregar a página inteira
5. WHEN a tabela está vazia para o filtro THEN o sistema SHALL exibir estado vazio com mensagem clara

**Independent Test**: Usuário com dados seed vê cards e tabela; filtrar por categoria reduz linhas exibidas.

**Requirements**: `API-DASH-01`, `API-DASH-02`, `UI-DASH-01`, `UI-DASH-02`, `UI-DASH-03`

---

### P1: Chat conversacional ⭐ MVP

**User Story**: Como usuário autenticado, quero conversar com o assistente em uma interface de chat moderna para registrar transações e tirar dúvidas.

**Why P1**: Canal principal de interação com os agentes LangGraph.

**Acceptance Criteria**:

1. WHEN o usuário envia uma mensagem no chat THEN o sistema SHALL exibir a mensagem do usuário imediatamente e indicador de "digitando..." até a resposta
2. WHEN a resposta SSE chega (`data: {AgentResponse JSON}`) THEN o sistema SHALL renderizar a mensagem do assistente com texto e, se presente, `metadata.sources` como citações
3. WHEN o evento SSE `event: done` chega THEN o sistema SHALL reabilitar o campo de entrada
4. WHEN a requisição falha (401, 500, timeout) THEN o sistema SHALL exibir erro na conversa e permitir nova tentativa
5. WHEN o usuário abre `/chat` THEN o sistema SHALL gerar ou reutilizar `session_id` (UUID) persistido em `sessionStorage`

**Independent Test**: Enviar "oi" e receber resposta do atendimento; enviar transação e ver confirmação.

**Requirements**: `UI-CHAT-01`, `UI-CHAT-02`, `UI-CHAT-03` (reutiliza `CHAT-01` backend existente)

---

### P1: Shell e navegação ⭐ MVP

**User Story**: Como usuário autenticado, quero navegar entre dashboard e chat com layout consistente.

**Why P1**: Estrutura mínima de app utilizável.

**Acceptance Criteria**:

1. WHEN autenticado THEN o sistema SHALL exibir header com nome do usuário, links Dashboard/Chat e botão Sair
2. WHEN em qualquer página autenticada THEN o sistema SHALL manter layout responsivo (mobile ≥375px legível)
3. WHEN acessa `/` sem autenticação THEN o sistema SHALL redirecionar para `/login`
4. WHEN acessa `/` autenticado THEN o sistema SHALL redirecionar para `/dashboard`

**Independent Test**: Navegar Dashboard ↔ Chat sem perder sessão.

**Requirements**: `UI-SHELL-01`, `UI-SHELL-02`, `DEPLOY-01`

---

### P2: Polish visual e acessibilidade

**User Story**: Como usuário, quero uma interface acessível e polida para uso confortável prolongado.

**Why P2**: Melhora UX mas não bloqueia paridade funcional.

**Acceptance Criteria**:

1. WHEN elementos interativos são focados via teclado THEN o sistema SHALL exibir outline visível (WCAG 2.1 AA focus)
2. WHEN formulários têm erro THEN o sistema SHALL associar mensagem ao campo via `aria-describedby`
3. WHEN valores monetários são exibidos THEN o sistema SHALL formatar em BRL (`R$ 1.234,56`)

**Independent Test**: Navegar login só com Tab; leitor de tela anuncia erros de formulário.

**Requirements**: `UI-A11Y-01`, `UI-A11Y-02`, `UI-FMT-01`

---

## Edge Cases

- WHEN cookie JWT expirou THEN API retorna 401 e SPA SHALL redirecionar para `/login` com mensagem "Sessão expirada"
- WHEN backend retorna 500 THEN SPA SHALL exibir mensagem genérica de erro com opção de retry
- WHEN usuário envia mensagem vazia no chat THEN SPA SHALL bloquear envio (botão desabilitado)
- WHEN SSE demora >120s THEN SPA SHALL cancelar e exibir timeout
- WHEN filtro de mês tem formato inválido THEN API retorna 400 e SPA SHALL resetar para mês atual
- WHEN build React não existe em dev sem `npm run dev` THEN FastAPI em prod SHALL retornar 503 com mensagem clara (não 404 silencioso)

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| AUTH-API-01 | P1: Auth | Design | Done (T1) |
| AUTH-API-02 | P1: Auth | Design | Done (T1) |
| AUTH-API-03 | P1: Auth | Design | Done (T2) |
| AUTH-API-04 | P1: Auth | Design | Done (T1) |
| API-DASH-01 | P1: Dashboard | Design | Done (T3) |
| API-DASH-02 | P1: Dashboard | Design | Done (T4) |
| UI-AUTH-01 | P1: Auth | Design | Done (T9/5751965) |
| UI-AUTH-02 | P1: Auth | Design | Done (T10/eb6e163) |
| UI-AUTH-03 | P1: Auth | Design | Done (T11/2271cff) |
| UI-DASH-01 | P1: Dashboard | Design | Done (T12) |
| UI-DASH-02 | P1: Dashboard | Design | Done (T13) |
| UI-DASH-03 | P1: Dashboard | Design | Done (T13) |
| UI-CHAT-01 | P1: Chat | Design | Done (T15/pending-hash) |
| UI-CHAT-02 | P1: Chat | Design | Done (T15/pending-hash) |
| UI-CHAT-03 | P1: Chat | Design | Done (T15/pending-hash) |
| UI-SHELL-01 | P1: Shell | Design | Done (T8; guard/header dinâmico completados em 2271cff) |
| UI-SHELL-02 | P1: Shell | Design | Done (T8; guard/header dinâmico completados em 2271cff) |
| DEPLOY-01 | P1: Shell | Design | Pending |
| CORS-01 | P1: Dev | Design | Done (T5) |
| UI-A11Y-01 | P2: A11y | - | Pending |
| UI-A11Y-02 | P2: A11y | - | Pending |
| UI-FMT-01 | P2: Format | - | Done (T12) |

**Coverage:** 22 total, 0 mapped to tasks, 22 unmapped ⚠️

---

## Success Criteria

- [ ] Usuário completa fluxo register → dashboard → chat → logout em < 3 minutos sem instruções externas
- [ ] Paridade funcional com telas Jinja2/HTMX atuais (auth, dashboard com filtros, chat SSE)
- [ ] `pytest` da suíte backend continua passando após migração (novos testes de API JSON inclusos)
- [ ] `npm run build` gera assets servidos em `http://localhost:8000/` sem porta separada em produção
