# Guia de Apresentacao - Assistente Financeiro com LangGraph

**Publico:** curso, demo tecnica, revisao de arquitetura  
**Objetivo:** explicar por que usamos LangGraph, agentes, MCPs, tools, contratos e guardrails, como cada peca aparece no sistema e como ela e construida em codigo.  
**Codigo-base:** `src/financial_assistant/`, `mcp_servers/`, `.specs/features/financial-assistant/`

---

## 1. Visao Executiva

O projeto e um assistente financeiro conversacional em PT-BR. Ele registra receitas e despesas, classifica gastos em 5 categorias de envelope budgeting, responde perguntas sobre planejamento financeiro e valida respostas antes de devolve-las ao usuario.

A arquitetura central nao e um chatbot unico com todas as responsabilidades. O fluxo e:

```text
Usuario
  -> FastAPI /api/chat
  -> LangGraph StateGraph
  -> Orquestrador
  -> um especialista por turno
  -> Validador
  -> AgentResponse via SSE
```

Frase de apresentacao:

> FastAPI recebe a conversa, LangGraph coordena o fluxo, agentes especializados resolvem cada tipo de pergunta, MCPs/tools executam acesso a dados, SQLite prova os numeros e ChromaDB recupera contexto semantico.

### O que ja esta implementado hoje

| Tema | Status | Onde olhar |
| --- | --- | --- |
| Grafo LangGraph completo | Implementado | `src/financial_assistant/agents/graph.py` |
| Orquestrador com structured output | Implementado | `src/financial_assistant/agents/orchestrator.py` |
| Especialistas Atendimento, Transacoes, Orcamento | Implementados | `src/financial_assistant/agents/specialists/` |
| Validador factual | Implementado | `src/financial_assistant/agents/validator.py` |
| MCP client com fallback | Implementado | `src/financial_assistant/mcp/client.py` |
| MCP servers finance/chroma | Implementados | `mcp_servers/finance/server.py`, `mcp_servers/chroma/server.py` |
| Uso das tools pelos especialistas | Deterministico, via funcoes dos MCP servers | Especialistas importam funcoes de `mcp_servers.*.server` |
| Tool-calling livre estilo ReAct | Nao e o padrao atual | Decisao de testabilidade do MVP |
| SSE token-a-token | Nao implementado | SSE por turno em `src/financial_assistant/chat/router.py` |

Ponto importante para falar com precisao: o projeto carrega as tools MCP no startup do grafo com `MultiServerMCPClient`, mas os especialistas atuais nao deixam a LLM escolher tools livremente. Eles chamam funcoes especificas de forma deterministica. Isso torna a demo e os testes mais previsiveis.

---

## 2. Roteiro Sugerido Da Apresentacao

1. Problema: controle financeiro exige disciplina e apps genericos nao explicam alocacao por categorias.
2. Solucao: chat + dashboard + envelope budgeting.
3. LangGraph: por que um grafo em vez de uma chain linear.
4. Agentes: orquestrador, especialistas e validador.
5. Contratos: Pydantic como fronteira entre LLM, grafo, tools e UI.
6. MCPs e tools: acesso padronizado a SQLite e ChromaDB.
7. Guardrails: contrato, isolamento por `user_id`, checagem factual e fallback.
8. Demo: 3 prompts reais da spec.
9. Gaps e proximos passos: streaming token-a-token, uso dinamico das MCP tools pelos especialistas e agente Insights P2.

Prompts de demo:

```text
Quero montar um plano de gastos
```

```text
Gastei 20 reais num pedido de delivery, em qual categoria essa despesa se encaixa?
```

```text
Em quais categorias devo prestar mais atencao ou economizar?
```

---

## 3. LangGraph (Orquestracao)

### Por que usar LangGraph

Um fluxo conversacional financeiro precisa de mais do que "prompt -> resposta". Ele precisa decidir qual especialista responde, manter estado entre nos, validar a saida e repetir o fluxo quando algo nao passa no quality gate.

LangGraph foi escolhido porque oferece:

| Necessidade | Como LangGraph ajuda |
| --- | --- |
| Fluxo explicito | `StateGraph` mostra os nos e edges do processo |
| Estado compartilhado | `AgentState` atravessa orquestrador, especialista e validador |
| Roteamento | `add_conditional_edges` escolhe o especialista por intent |
| Retry controlado | edge do validador volta ao orquestrador quando `final_response=None` |
| Testabilidade | cada node e uma funcao testavel separadamente |

Alternativas descartadas:

| Alternativa | Problema para este sistema |
| --- | --- |
| Chain linear LangChain | Dificulta retry e roteamento por especialistas |
| Agente unico com muitas tools | Mistura CRUD, RAG, budget e validacao no mesmo prompt |
| Microservicos por agente | Overkill para o MVP |

### Aplicacao no sistema

O grafo atual esta em `src/financial_assistant/agents/graph.py`. Ele compila este fluxo:

```text
START
  -> orchestrator
  -> atendimento | transacoes | orcamento
  -> validator
  -> END ou orchestrator novamente
```

O roteamento acontece assim:

| Intent | Especialista |
| --- | --- |
| `explain_budget` | `atendimento` |
| `categorize` | `transacoes` |
| `register_transaction` | `transacoes` |
| `budget_advice` | `orcamento` |

Se a confianca da classificacao for baixa, o roteamento cai para Atendimento para pedir clarificacao. Essa decisao aparece em `specialist_for_intent()`.

### Construcao em codigo

Padrao minimo de LangGraph, conforme a propria documentacao: define-se um `TypedDict` de estado, funcoes node retornam patches parciais, o grafo conecta nodes e compila.

No projeto:

```python
# src/financial_assistant/agents/graph.py
def build_graph() -> CompiledStateGraph:
    _load_mcp_tools()

    graph = StateGraph(AgentState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("atendimento", atendimento_node)
    graph.add_node("transacoes", transacoes_node)
    graph.add_node("orcamento", orcamento_node)
    graph.add_node("validator", validator_node)

    graph.add_edge(START, "orchestrator")
    graph.add_conditional_edges(
        "orchestrator",
        _route_to_specialist,
        {name: name for name in ("atendimento", "transacoes", "orcamento")},
    )

    for name in ("atendimento", "transacoes", "orcamento"):
        graph.add_edge(name, "validator")

    graph.add_conditional_edges(
        "validator",
        _route_after_validation,
        {"orchestrator": "orchestrator", END: END},
    )
    return graph.compile()
```

Entrada de um turno:

```python
initial_state: AgentState = {
    "messages": [HumanMessage(message)],
    "user_id": user_id,
    "session_id": session_id,
    "intent": None,
    "intent_confidence": None,
    "retrieved_context": [],
    "pending_action": None,
    "agent_notes": [],
    "last_tool_results": None,
    "validation_attempts": 0,
    "final_response": None,
}

result = compiled.invoke(initial_state)
response = result["final_response"]
```

### Como explicar no slide

> LangGraph e o fluxo de trabalho. Ele nao substitui os agentes; ele organiza quem roda, em qual ordem, com qual estado e com qual criterio de saida.

---

## 4. AgentState (Memoria De Trabalho)

### Por que usar AgentState

Sem um estado compartilhado, cada agente precisaria reconsultar banco, historico e contexto a cada passo. `AgentState` funciona como uma memoria de trabalho intra-turno: o orquestrador escreve a intencao, o especialista escreve a resposta e o validador decide se aprova.

### Aplicacao no sistema

O estado vive em `src/financial_assistant/agents/state.py`.

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str
    intent: str | None
    intent_confidence: float | None
    retrieved_context: list[str]
    pending_action: dict | None
    agent_notes: list[str]
    last_tool_results: dict | None
    validation_attempts: int
    final_response: AgentResponse | None
```

Campos principais:

| Campo | Quem escreve | Quem le | Para que serve |
| --- | --- | --- | --- |
| `messages` | entrada do grafo | todos | mensagem atual e historico da execucao |
| `user_id` | FastAPI/auth | tools e agentes | isolamento multi-usuario |
| `session_id` | chat UI/API | persistencia | agrupar turnos da conversa |
| `intent` | orquestrador | grafo/especialistas | roteamento e comportamento |
| `intent_confidence` | orquestrador | edge de roteamento | fallback para Atendimento em ambiguidade |
| `final_response` | especialista/validador | validador/API | resposta uniforme ao usuario |
| `validation_attempts` | validador | edge de retry | evitar loop infinito |

Alguns campos ja existem para evolucao do fluxo, mas ainda sao pouco usados pelos especialistas atuais: `retrieved_context`, `pending_action` e `last_tool_results`. Eles sao bons pontos para mostrar como o desenho ja preve auditoria e memoria de trabalho mais rica, sem afirmar que isso esta totalmente explorado hoje.

### Construcao em codigo

O detalhe importante e o reducer `add_messages`.

```python
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
```

Por padrao, um update de estado substituiria o campo. Com `add_messages`, novos itens de `messages` sao anexados. Isso e util quando um node quer adicionar uma mensagem sem apagar o historico.

No projeto, a maior parte dos nodes retorna patches pequenos:

```python
def orchestrator_node(state: AgentState) -> dict:
    classification = classify_intent(state["messages"][-1].content)
    return {
        "intent": classification.intent.value,
        "intent_confidence": classification.confidence,
    }
```

---

## 5. Contratos (Pydantic)

### Por que usar contratos

LLM gera texto. Sistema financeiro precisa de estruturas verificaveis. Os contratos Pydantic definem a fronteira entre linguagem natural e codigo: se a saida nao cabe no contrato, ela nao avanca.

Contratos resolvem:

| Risco | Contrato |
| --- | --- |
| Orquestrador devolver texto livre | `IntentClassification` |
| Especialista devolver formato imprevisivel | `AgentResponse` |
| Receita vir com categoria | `TransactionCreate` |
| Despesa sem categoria | `TransactionCreate` |
| Orçamento sair sem shape serializavel | `BudgetSummary` |

### Aplicacao no sistema

Arquivos principais:

| Contrato | Arquivo | Uso |
| --- | --- | --- |
| `Intent` | `src/financial_assistant/contracts/agent_response.py` | valores possiveis de roteamento |
| `IntentClassification` | `src/financial_assistant/contracts/agent_response.py` | saida estruturada do orquestrador |
| `AgentResponse` | `src/financial_assistant/contracts/agent_response.py` | resposta final de qualquer especialista |
| `TransactionCreate` | `src/financial_assistant/contracts/transaction.py` | validacao antes de persistir |
| `BudgetSummary` | `src/financial_assistant/contracts/budget.py` | serializacao de orçamento |

### Construcao em codigo

Contrato do orquestrador:

```python
class Intent(str, Enum):
    EXPLAIN_BUDGET = "explain_budget"
    CATEGORIZE = "categorize"
    BUDGET_ADVICE = "budget_advice"
    REGISTER_TRANSACTION = "register_transaction"


class IntentClassification(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
```

Contrato de resposta dos especialistas:

```python
class AgentResponse(BaseModel):
    text: str
    suggested_category: BudgetCategory | None = None
    action: Literal["none", "offer_register", "registered"] = "none"
    metadata: dict = {}
```

Por que `action` importa:

| `action` | Significado |
| --- | --- |
| `none` | resposta informativa, sem acao de UI |
| `offer_register` | sistema sugeriu categoria, mas nao registrou |
| `registered` | transacao foi persistida |

Essa diferenca atende o cenario:

```text
Gastei 20 reais num pedido de delivery, em qual categoria essa despesa se encaixa?
```

Esse prompt pergunta "qual categoria?", entao o sistema deve explicar e oferecer registro, nao persistir automaticamente.

Contrato de transacao:

```python
class TransactionCreate(BaseModel):
    date: date
    description: str = Field(min_length=1, max_length=255)
    type: TransactionType
    amount: Decimal = Field(gt=Decimal("0"))
    category: BudgetCategory | None = None

    @model_validator(mode="after")
    def _check_category_matches_type(self) -> "TransactionCreate":
        if self.type is TransactionType.EXPENSE and self.category is None:
            raise ValueError("category e obrigatorio para despesas")
        if self.type is TransactionType.INCOME and self.category is not None:
            raise ValueError("category nao e permitido para receitas")
        return self
```

Frase para apresentacao:

> Prompt e uma sugestao para o modelo. Contrato e uma regra para o sistema.

---

## 6. Agentes

### Visao geral

O MVP usa um padrao supervisor simples: um orquestrador escolhe um especialista por turno e um validador aprova ou rejeita a resposta.

```text
Usuario
  -> Orquestrador
  -> Atendimento | Transacoes | Orcamento
  -> Validador
  -> Resposta
```

O projeto nao usa, hoje, uma malha de agentes conversando livremente entre si. Isso e deliberado: o MVP prioriza previsibilidade, testes e demo estavel.

---

### 6.1 Orquestrador

#### Por que existe

Sem orquestrador, todos os especialistas precisariam tentar entender toda mensagem. Isso cria acoplamento, prompts maiores e maior chance de chamar a ferramenta errada.

O orquestrador tem uma unica tarefa: classificar a intencao da mensagem e deixar o grafo rotear.

#### Aplicacao no sistema

Arquivo: `src/financial_assistant/agents/orchestrator.py`

Ele usa DeepSeek via `ChatOpenAI` com `base_url` configurado para a API DeepSeek. A saida e `IntentClassification`.

#### Construcao em codigo

```python
def classify_intent(
    message: str,
    llm: BaseChatModel | None = None,
) -> IntentClassification:
    model = llm if llm is not None else get_orchestrator_llm()
    structured_model = model.with_structured_output(
        IntentClassification,
        method="function_calling",
    )
    return structured_model.invoke([("system", SYSTEM_PROMPT), ("human", message)])
```

O metodo `function_calling` foi escolhido porque a API DeepSeek rejeitou o formato `json_schema` em teste real. Esse detalhe e bom para apresentar porque mostra uma decisao tecnica baseada em evidencia do fornecedor.

Roteamento deterministico:

```python
SPECIALIST_BY_INTENT: dict[Intent, str] = {
    Intent.EXPLAIN_BUDGET: "atendimento",
    Intent.CATEGORIZE: "transacoes",
    Intent.BUDGET_ADVICE: "orcamento",
    Intent.REGISTER_TRANSACTION: "transacoes",
}

def specialist_for_intent(intent: Intent, confidence: float = 1.0) -> str:
    if confidence < AMBIGUITY_CONFIDENCE_THRESHOLD:
        return "atendimento"
    return SPECIALIST_BY_INTENT[intent]
```

Guardrail do orquestrador:

| Guardrail | Como aparece |
| --- | --- |
| Enum de intents | `Intent` limita valores |
| Confianca entre 0 e 1 | `Field(ge=0.0, le=1.0)` |
| Ambiguidade | `confidence < 0.5` roteia para Atendimento |
| LLM nao escolhe node direto | mapa `SPECIALIST_BY_INTENT` e codigo deterministico |

---

### 6.2 Atendimento

#### Por que existe

Atendimento e o front-door educacional. Ele responde perguntas gerais, explica as categorias e usa conhecimento semantico para manter a resposta grounded.

Sem esse agente, perguntas como "quero montar um plano de gastos" cairiam no mesmo fluxo de CRUD financeiro, misturando educacao com persistencia.

#### Aplicacao no sistema

Arquivo: `src/financial_assistant/agents/specialists/atendimento.py`

Responsabilidades:

| Responsabilidade | Implementacao |
| --- | --- |
| Explicar categorias | prompt + knowledge base |
| Usar RAG | `query_knowledge` |
| Citar fontes | `metadata["sources"]` |
| Nao depender de transacoes | responde sem exigir dados do usuario |

Observacao importante: a docstring fala em `chroma-mcp`, mas o codigo atual chama `financial_assistant.vector.knowledge_seed.query_knowledge` via uma tool local LangChain. Ou seja, conceitualmente e RAG/Chroma; operacionalmente, este especialista nao chama `mcp_servers/chroma/server.py` diretamente.

#### Construcao em codigo

Tool local:

```python
@tool
def query_knowledge(query: str, n_results: int = 6) -> list[dict[str, object]]:
    """Busca semantica na base de conhecimento de orcamento."""
    return knowledge_seed.query_knowledge(query, n_results=n_results)
```

Resposta grounded:

```python
def answer(message: str, llm: BaseChatModel | None = None) -> AgentResponse:
    model = llm if llm is not None else get_atendimento_llm()
    docs = query_knowledge.invoke({"query": message})
    context = "\n".join(f"- {doc['document']}" for doc in docs)
    messages = [
        SystemMessage(SYSTEM_PROMPT),
        HumanMessage(f"CONTEXTO:\n{context}\n\nPERGUNTA: {message}"),
    ]
    response = model.invoke(messages)
    return AgentResponse(text=response.content, metadata={"sources": _cite_sources(docs)})
```

Node LangGraph:

```python
def atendimento_node(state: AgentState) -> dict:
    last_message = state["messages"][-1]
    return {"final_response": answer(last_message.content)}
```

Guardrails:

| Guardrail | Como aparece |
| --- | --- |
| Nao inventar faixas | system prompt manda usar apenas `CONTEXTO` |
| Fonte da resposta | `metadata["sources"]` |
| Contrato de saida | retorna `AgentResponse` |
| Checagem de numeros pessoais | validador pula apenas para `explain_budget`, pois valores podem ser exemplos pedagogicos |

---

### 6.3 Transacoes

#### Por que existe

Transacoes concentra CRUD financeiro e categorizacao. Esse agente lida com risco maior porque pode persistir dados. Por isso ele e mais deterministico que agentico: regex para extracao, similaridade para categoria e tool especifica para persistir.

#### Aplicacao no sistema

Arquivo: `src/financial_assistant/agents/specialists/transacoes.py`

Ele cobre dois intents:

| Intent | O que faz | Persiste? |
| --- | --- | --- |
| `categorize` | sugere categoria e explica | Nao |
| `register_transaction` | extrai valor/tipo, categoriza e cria transacao | Sim |

Tools/funcoes usadas:

| Funcao | Origem | Uso |
| --- | --- | --- |
| `find_similar_transactions` | `mcp_servers.chroma.server` | achar categoria por similaridade |
| `create_transaction` | `mcp_servers.finance.server` | persistir no SQLite e indexar no Chroma |

#### Construcao em codigo

Extracao deterministica:

```python
def parse_transaction_message(message: str) -> ParsedTransaction | None:
    type_ = _infer_type(message)
    extracted = _extract_amount(message)
    if type_ is None or extracted is None:
        return None
    amount, span = extracted
    if amount <= 0:
        return None
    return ParsedTransaction(
        type=type_,
        amount=amount,
        description=_clean_description(message, span),
    )
```

Categorizacao:

```python
def categorize(
    description: str,
    user_id: str,
    find_similar: Callable[..., list[dict]] | None = None,
) -> BudgetCategory | None:
    finder = find_similar if find_similar is not None else _find_similar_transactions
    hits = finder(user_id=user_id, description=description)
    for hit in hits:
        category_value = hit.get("metadata", {}).get("category")
        if category_value:
            return BudgetCategory(category_value)
    return None
```

Fluxo "qual categoria?":

```python
def _handle_categorize(message: str, user_id: str, *, find_similar=None) -> AgentResponse:
    category = categorize(message, user_id, find_similar=find_similar)
    if category is None:
        return AgentResponse(text=CLARIFICATION_TEXT, action="none")
    return AgentResponse(
        text=_categorization_explanation(category),
        suggested_category=category,
        action="offer_register",
    )
```

Fluxo "registre":

```python
def _handle_register(message: str, user_id: str, *, find_similar=None, create=None) -> AgentResponse:
    parsed = parse_transaction_message(message)
    if parsed is None:
        return AgentResponse(text=CLARIFICATION_TEXT, action="none")

    category = None
    if parsed.type == TransactionType.EXPENSE:
        category = categorize(parsed.description, user_id, find_similar=find_similar)
        if category is None:
            return AgentResponse(text=CLARIFICATION_TEXT, action="none")

    creator = create if create is not None else _create_transaction
    created = creator(
        user_id=user_id,
        date=date.today().isoformat(),
        description=parsed.description,
        type=parsed.type.value,
        amount=str(parsed.amount),
        category=category.value if category else None,
    )
    return AgentResponse(
        text=_confirmation_text(created),
        suggested_category=category,
        action="registered",
        metadata={"transaction": created},
    )
```

Guardrails:

| Guardrail | Como aparece |
| --- | --- |
| Valor ausente ou invalido | pergunta clarificacao, nao persiste |
| Categoria nao inferida | pergunta clarificacao, nao persiste |
| Receita sem categoria | `TransactionCreate` valida |
| Despesa com categoria obrigatoria | `TransactionCreate` valida |
| Isolamento usuario | toda chamada recebe `user_id` |
| Valor recem-criado | entra em `metadata["transaction"]` para o validador reconhecer |

---

### 6.4 Orcamento

#### Por que existe

Orcamento responde perguntas sobre percentuais, faixas e recomendacoes. Ele nao precisa de LLM para calcular numeros: a fonte correta e o `BudgetService` por meio de `finance-mcp.get_budget_summary`.

Isso reduz alucinacao: o agente apenas formata e prioriza dados calculados pelo dominio.

#### Aplicacao no sistema

Arquivo: `src/financial_assistant/agents/specialists/orcamento.py`

Responsabilidades:

| Caso | Resposta |
| --- | --- |
| Sem receita no mes | orienta registrar receita primeiro |
| "como esta meu orcamento?" | resumo das 5 categorias |
| "onde economizar?" | lista categorias em alerta ou com margem apertada |

#### Construcao em codigo

```python
def budget_advice(
    user_id: str,
    month: str | None = None,
    *,
    get_summary: Callable[..., dict] | None = None,
    message: str = "",
) -> AgentResponse:
    fetch = get_summary if get_summary is not None else _get_budget_summary
    summary = fetch(user_id=user_id, month=month or date.today().strftime("%Y-%m"))
    if not summary["has_income"]:
        return AgentResponse(text=NO_INCOME_ADVICE)
    if _wants_full_summary(message):
        return AgentResponse(text=_format_full_summary(summary["categories"]))
    return AgentResponse(text=_format_advice(summary["categories"]))
```

Priorizacao:

```python
def _needs_attention(category: dict) -> bool:
    return category["status"] == "alerta" or category["remaining_pct"] <= TIGHT_MARGIN_PCT
```

Guardrails:

| Guardrail | Como aparece |
| --- | --- |
| Nao calcular % sem receita | `has_income` retorna orientacao |
| Numeros vem do dominio | `get_budget_summary` |
| Sem LLM para matematica | formatacao deterministica |
| Validador confere percentuais | `validate()` extrai `%` e compara com summary |

---

### 6.5 Validador

#### Por que existe

O validador separa geracao de verificacao. Especialistas podem montar respostas; o validador decide se elas podem sair para o usuario.

Em um sistema financeiro, isso e essencial. Uma resposta bonita com saldo errado e pior que uma falha explicita.

#### Aplicacao no sistema

Arquivo: `src/financial_assistant/agents/validator.py`

Checks:

| Check | Implementacao |
| --- | --- |
| Shape correto | `_coerce_response()` para `AgentResponse` |
| Texto nao vazio | `checked.text.strip()` |
| PT-BR | heuristica `_looks_like_pt_br()` |
| Categoria valida | `BudgetCategory(...)` |
| Valores em R$ | extrai e compara com `get_balance`/`get_budget_summary` |
| Percentuais | extrai e compara com `get_budget_summary` |
| Retry | `final_response=None` enquanto tentativas < 2 |

#### Construcao em codigo

```python
def validate(
    response: object,
    *,
    user_id: str,
    intent: str | None = None,
    month: str | None = None,
    get_balance: Callable[..., dict] | None = None,
    get_budget_summary: Callable[..., dict] | None = None,
) -> ValidationResult:
    checked = _coerce_response(response)
    if checked is None:
        return ValidationResult(False, "AgentResponse invalido ou ausente")
    if not checked.text.strip():
        return ValidationResult(False, "resposta vazia")
    if not _looks_like_pt_br(checked.text):
        return ValidationResult(False, "resposta nao parece estar em PT-BR")

    if intent in _SKIPS_FINANCIAL_FIGURE_CHECK_FOR:
        return ValidationResult(True, None)

    amounts = _extract_currency_values(checked.text)
    percents = _extract_percent_values(checked.text)
    if amounts or percents:
        balance = fetch_balance(user_id=user_id, month=target_month)
        summary = fetch_summary(user_id=user_id, month=target_month)
        ...
```

Node:

```python
def validator_node(state: AgentState, *, get_balance=None, get_budget_summary=None) -> dict:
    attempts = state["validation_attempts"] + 1
    result = validate(
        state["final_response"],
        user_id=state["user_id"],
        intent=state.get("intent"),
        get_balance=get_balance,
        get_budget_summary=get_budget_summary,
    )
    if result.approved:
        return {"validation_attempts": attempts}

    if attempts >= MAX_VALIDATION_ATTEMPTS:
        return {
            "validation_attempts": attempts,
            "final_response": AgentResponse(text=FALLBACK_TEXT),
            "agent_notes": agent_notes,
        }
    return {
        "validation_attempts": attempts,
        "final_response": None,
        "agent_notes": agent_notes,
    }
```

Frase para apresentacao:

> O LLM escreve a prosa; o validador pede o extrato.

---

## 7. MCPs

### Por que usar MCP

MCP, Model Context Protocol, padroniza ferramentas externas acessiveis por agentes. Neste projeto, ele evita que a logica de SQLite/ChromaDB fique espalhada pelos nodes LangGraph.

Beneficios:

| Beneficio | Aplicacao no projeto |
| --- | --- |
| Desacoplamento | agentes nao precisam conhecer SQLAlchemy/Chroma internamente |
| Reuso | Transacoes, Orcamento e Validador usam as mesmas funcoes financeiras |
| Extensibilidade | novos MCPs podem entrar sem reescrever o grafo |
| Contrato | `@mcp.tool()` expoe schema de tool |
| Fallback | se subprocesso falha, sistema usa tools in-process |

### Aplicacao no sistema

MCP servers:

| Server | Arquivo | Papel |
| --- | --- | --- |
| `finance-mcp` | `mcp_servers/finance/server.py` | CRUD financeiro e orcamento sobre SQLite |
| `chroma-mcp` | `mcp_servers/chroma/server.py` | busca semantica, RAG e memoria sobre ChromaDB |

Cliente MCP:

```python
MCP_CONNECTIONS: dict[str, StdioConnection] = {
    "finance": {"transport": "stdio", "command": "python", "args": ["-m", "mcp_servers.finance"]},
    "chroma": {"transport": "stdio", "command": "python", "args": ["-m", "mcp_servers.chroma"]},
}
```

Carregamento:

```python
async def get_mcp_tools(client: MultiServerMCPClient | None = None) -> list[BaseTool]:
    client = client if client is not None else MultiServerMCPClient(MCP_CONNECTIONS)
    try:
        return await client.get_tools()
    except Exception:
        logger.warning("MCP client failed; falling back to in-process tools", exc_info=True)
        return in_process_tools()
```

Fallback:

```python
def in_process_tools() -> list[BaseTool]:
    return [
        StructuredTool.from_function(func)
        for func in (*_FINANCE_TOOL_FUNCS, *_CHROMA_TOOL_FUNCS)
    ]
```

### finance-mcp

Tools:

| Tool | Uso |
| --- | --- |
| `create_transaction` | cria receita/despesa e indexa no Chroma |
| `list_transactions` | lista por usuario, mes, categoria e tipo |
| `get_budget_summary` | retorna percentuais por categoria |
| `get_balance` | retorna totais e saldo |
| `update_transaction` | atualiza e reindexa |
| `delete_transaction` | remove do SQLite e do Chroma |

Exemplo:

```python
@mcp.tool()
def create_transaction(
    user_id: str,
    date: str,
    description: str,
    type: str,
    amount: str,
    category: str | None = None,
) -> dict:
    payload = TransactionCreate(
        date=date_.fromisoformat(date),
        description=description,
        type=TransactionType(type),
        amount=Decimal(amount),
        category=BudgetCategory(category) if category else None,
    )
    uid = uuid.UUID(user_id)
    with SessionLocal() as session:
        transaction = TransactionRepository(session).create(...)
        session.commit()
        result = _serialize_transaction(transaction)
        index_transaction(uid, transaction)
    return result
```

Guardrail aqui: `TransactionCreate` valida antes de persistir; `user_id` e obrigatorio; write-through so indexa depois do commit.

### chroma-mcp

Tools:

| Tool | Uso |
| --- | --- |
| `search_transactions` | busca semantica em transacoes do usuario |
| `find_similar_transactions` | mistura historico do usuario + exemplos globais para categorizar |
| `query_knowledge` | consulta base de conhecimento global |
| `get_chat_context` | recupera memoria semantica de conversas |
| `save_working_memory` | salva fato estruturado em memoria |

Exemplo:

```python
@mcp.tool()
def find_similar_transactions(user_id: str, description: str, n_results: int = 3) -> list[dict]:
    own = _semantic_query("transactions", description, n_results, where={"user_id": user_id})
    examples = _semantic_query("category_examples", description, n_results, where={"user_id": GLOBAL_USER_ID})
    combined = sorted(own + examples, key=lambda hit: hit["score"], reverse=True)
    return combined[:n_results]
```

Fallback de busca:

```python
@mcp.tool()
def search_transactions(user_id: str, query: str, n_results: int = 5) -> list[dict]:
    try:
        hits = _semantic_query("transactions", query, n_results, where={"user_id": user_id})
        threshold = get_settings().chroma_similarity_threshold
        return [hit for hit in hits if hit["score"] >= threshold]
    except Exception:
        rows = TransactionRepository(session).search_by_description(uuid.UUID(user_id), query)
        return [_fallback_hit(row) for row in rows]
```

### Status real do uso de MCP pelos agentes

Este ponto merece um slide proprio:

| Pergunta | Resposta atual |
| --- | --- |
| O grafo conecta aos MCPs? | Sim, `_load_mcp_tools()` chama `get_mcp_tools()` em `build_graph()` |
| As tools MCP sao convertidas para LangChain tools? | Sim, via `MultiServerMCPClient.get_tools()` ou fallback `StructuredTool` |
| Especialistas usam essas `BaseTool` dinamicas? | Ainda nao diretamente |
| Como eles acessam dados hoje? | Importam e chamam funcoes dos MCP servers de forma deterministica |
| Isso e ruim? | Nao para o MVP; melhora previsibilidade e testes |
| Evolucao natural | Injetar subconjuntos de `BaseTool` por especialista quando houver necessidade de tool-calling agentico |

---

## 8. Tools

### Por que separar "tools" de "MCP"

Tool e a operacao que o agente pode executar. MCP e um protocolo/camada para expor tools. Neste projeto existem dois tipos praticos:

| Tipo | Exemplo | Uso |
| --- | --- | --- |
| Tool local LangChain | `query_knowledge` em Atendimento | RAG direto no codigo |
| Tool MCP | `create_transaction`, `get_budget_summary` | acesso a dominio financeiro e vetorial |

### Aplicacao no sistema

Mapa agente -> tools:

| Agente | Tools/funcoes usadas hoje | Observacao |
| --- | --- | --- |
| Orquestrador | LLM structured output | nao chama MCP |
| Atendimento | `query_knowledge` local | RAG sobre knowledge base |
| Transacoes | `find_similar_transactions`, `create_transaction` | funcoes dos MCP servers |
| Orcamento | `get_budget_summary` | funcao do finance-mcp |
| Validador | `get_balance`, `get_budget_summary` | fonte autoritativa |

### Contrato de uma tool segura

Uma tool segura neste projeto deve seguir estas regras:

1. Receber `user_id` quando acessa dados de usuario.
2. Validar payload com contrato Pydantic quando altera dados.
3. Retornar `dict` ou `list[dict]` serializavel.
4. Nao expor dados de outro usuario.
5. Ter fallback ou erro controlado quando depender de servico externo.

Exemplo de assinatura segura:

```python
@mcp.tool()
def get_budget_summary(user_id: str, month: str) -> dict:
    with SessionLocal() as session:
        summary = BudgetService(session).get_summary(uuid.UUID(user_id), month)
    return BudgetSummaryContract.model_validate(summary).model_dump(mode="json")
```

---

## 9. Guardrails

### Por que guardrails sao camadas, nao uma coisa so

Nao existe um unico guardrail que resolva tudo. O sistema combina regras de entrada, contratos de saida, isolamento de dados, validacao factual e fallback operacional.

### Camadas do sistema

| Camada | Protege contra | Exemplo |
| --- | --- | --- |
| Contratos Pydantic | shape invalido e regra de negocio quebrada | `TransactionCreate`, `AgentResponse` |
| Roteamento deterministico | especialista errado ou tool errada | `SPECIALIST_BY_INTENT` |
| Isolamento por `user_id` | vazamento cross-user | tools exigem `user_id` |
| Validador factual | alucinacao numerica | compara R$ e % com SQLite |
| Fallback operacional | indisponibilidade MCP/Chroma | in-process tools, SQL LIKE |
| Clarificacao | persistencia incerta | pergunta antes de gravar |

### Exemplo completo: registro de despesa

Prompt:

```text
Gastei R$ 150 no cinema
```

Fluxo:

```text
1. Orquestrador -> intent register_transaction
2. Grafo -> Transacoes
3. Transacoes -> parse regex: despesa, 150, cinema
4. Transacoes -> find_similar_transactions: categoria prazeres
5. Transacoes -> create_transaction
6. finance-mcp -> TransactionCreate valida despesa com categoria
7. SQLite commit
8. index_transaction escreve embedding
9. Transacoes -> AgentResponse(action="registered", metadata={"transaction": ...})
10. Validador -> reconhece R$ 150 em metadata/banco
11. API -> SSE com AgentResponse
```

### Exemplo completo: resposta rejeitada

Se um especialista responder:

```text
Voce gastou R$ 9999 em conforto.
```

E esse valor nao existir em `get_balance` nem em `get_budget_summary`, o validador retorna:

```python
ValidationResult(False, "valor R$ 9999 nao confere com o banco (VAL-03)")
```

O node devolve `final_response=None`, e a edge condicional manda o fluxo de volta ao orquestrador. Depois de 2 tentativas, retorna fallback amigavel.

---

## 10. RAG E Memoria

### Por que usar RAG

O assistente precisa explicar regras de orçamento e categorias sem inventar faixas. RAG permite recuperar documentos da knowledge base e injetar contexto no prompt.

### Aplicacao no sistema

Colecoes ChromaDB previstas/implementadas:

| Collection | Conteudo | Uso |
| --- | --- | --- |
| `knowledge_base` | regras das categorias | Atendimento |
| `category_examples` | exemplos rotulados | Transacoes |
| `transactions` | descricoes do usuario | busca e categorizacao |
| `chat_memory` | turnos relevantes | memoria semantica |
| `working_memory` | fatos estruturados | coordenacao futura |

### Tipos de "memoria"

| Camada | Tecnologia | Papel |
| --- | --- | --- |
| Intra-turno | `AgentState` | coordenar nodes na execucao atual |
| Historico duravel | SQLite `chat_messages` | salvar conversas por sessao |
| Semantica | ChromaDB | recuperar contexto por similaridade |

### Construcao em codigo

Atendimento usa RAG deterministico:

```python
docs = query_knowledge.invoke({"query": message})
context = "\n".join(f"- {doc['document']}" for doc in docs)
response = model.invoke([
    SystemMessage(SYSTEM_PROMPT),
    HumanMessage(f"CONTEXTO:\n{context}\n\nPERGUNTA: {message}"),
])
```

Transacoes usa similaridade como few-shot dinamico:

```python
hits = finder(user_id=user_id, description=description)
for hit in hits:
    category_value = hit.get("metadata", {}).get("category")
    if category_value:
        return BudgetCategory(category_value)
```

Persistencia da conversa:

```python
def _persist_turn(user_id: str, session_id: str, message: str, response: AgentResponse) -> None:
    with SessionLocal() as session:
        session.add_all([
            ChatMessage(user_id=uuid.UUID(user_id), session_id=session_id, role="user", content=message),
            ChatMessage(user_id=uuid.UUID(user_id), session_id=session_id, role="assistant", content=response.text),
        ])
        session.commit()
```

---

## 11. API, SSE E Frontend

### Por que SSE

O chat precisa de um canal simples para enviar a resposta do agente ao navegador. SSE e suficiente para resposta servidor -> cliente, com menor complexidade que WebSocket.

### Aplicacao no sistema

Endpoint:

```python
@router.post("/api/chat")
def post_chat(body: ChatRequest, user: User = Depends(get_current_user_api)) -> StreamingResponse:
    return StreamingResponse(
        _stream_turn(str(user.id), body.session_id, body.message),
        media_type="text/event-stream",
    )
```

Stream:

```python
def _stream_turn(user_id: str, session_id: str, message: str) -> Iterator[str]:
    response = agent_graph.run(user_id, session_id, message)
    yield _sse_event(response.model_dump_json())
    yield _sse_event("end", event="done")
```

Status atual:

| Tema | Estado |
| --- | --- |
| SSE por turno | Implementado |
| Evento `done` | Implementado |
| Streaming token-a-token | Nao implementado |
| Motivo | especialistas usam `.invoke()` bloqueante |

Como explicar:

> O protocolo SSE ja esta no lugar, mas o conteudo ainda sai por turno completo. Streaming token-a-token exige reescrever especialistas para chamadas streaming.

---

## 12. Walkthrough De Um Turno

Prompt:

```text
Gastei 20 reais num pedido de delivery, em qual categoria essa despesa se encaixa?
```

### Estado inicial

```python
{
    "messages": [HumanMessage("Gastei 20 reais num pedido de delivery...")],
    "user_id": "...",
    "session_id": "...",
    "intent": None,
    "intent_confidence": None,
    "final_response": None,
    "validation_attempts": 0,
}
```

### Orquestrador

Classifica como:

```python
IntentClassification(intent=Intent.CATEGORIZE, confidence=0.9)
```

State patch:

```python
{"intent": "categorize", "intent_confidence": 0.9}
```

### Grafo

`_route_to_specialist()` retorna:

```text
transacoes
```

### Transacoes

Como `intent == "categorize"`, chama `_handle_categorize`, nao `_handle_register`.

Resposta:

```python
AgentResponse(
    text="Essa despesa se encaixa na categoria **prazeres** porque ... Quer que eu registre essa despesa?",
    suggested_category=BudgetCategory.PLEASURES,
    action="offer_register",
)
```

### Validador

Confere:

```text
AgentResponse valido
texto nao vazio
PT-BR
categoria valida
```

Como nao houve registro automatico, nao existe `metadata["transaction"]`.

### API

Envia:

```text
data: {"text":"...","suggested_category":"prazeres","action":"offer_register","metadata":{}}

event: done
data: end
```

---

## 13. Como Navegar O Codigo Ao Vivo

Ordem recomendada para abrir arquivos no IDE:

1. `src/financial_assistant/chat/router.py` - entrada HTTP/SSE.
2. `src/financial_assistant/agents/graph.py` - fluxo LangGraph.
3. `src/financial_assistant/agents/state.py` - estado compartilhado.
4. `src/financial_assistant/agents/orchestrator.py` - classificacao e roteamento.
5. `src/financial_assistant/contracts/agent_response.py` - contratos de intent/resposta.
6. `src/financial_assistant/agents/specialists/transacoes.py` - exemplo mais completo de tool + contrato.
7. `mcp_servers/finance/server.py` - tool que persiste transacao.
8. `src/financial_assistant/agents/validator.py` - guardrail factual.
9. `src/financial_assistant/mcp/client.py` - MCP client e fallback.

Mapa rapido:

```text
src/financial_assistant/
  agents/
    graph.py              # monta StateGraph
    state.py              # AgentState
    orchestrator.py       # classify_intent + specialist_for_intent
    validator.py          # validate + validator_node
    specialists/
      atendimento.py      # RAG + LLM
      transacoes.py       # regex + similaridade + create_transaction
      orcamento.py        # get_budget_summary + formatacao
  contracts/
    agent_response.py     # Intent, IntentClassification, AgentResponse
    transaction.py        # TransactionCreate
    budget.py             # BudgetSummary
  mcp/
    client.py             # MultiServerMCPClient + fallback

mcp_servers/
  finance/server.py       # finance-mcp tools
  chroma/server.py        # chroma-mcp tools
```

---

## 14. Gaps, Decisoes E Roadmap

### Gaps honestos do estado atual

| Tema | Estado atual | Evolucao possivel |
| --- | --- | --- |
| MCP tools carregadas mas nao injetadas nos especialistas | grafo chama `_load_mcp_tools()`, especialistas importam funcoes | passar subconjuntos de tools por dependencia |
| Atendimento usa tool local para RAG | chama `knowledge_seed.query_knowledge` | alinhar com `chroma-mcp.query_knowledge(user_id, query)` |
| SSE por turno | resposta completa por evento | streaming token-a-token com `.astream()` |
| Checkpointing LangGraph | nao ha checkpointer configurado; historico fica em SQLite `chat_messages` | adicionar checkpointer se precisar retomar execucoes do grafo |
| Campos de estado avancados | `retrieved_context`, `pending_action` e `last_tool_results` existem, mas sao pouco populados | especialistas preencherem para auditoria e coordenacao |
| `chat_memory`/`working_memory` existem no MCP | nao sao centrais no fluxo atual | usar para fatos duraveis e memoria cross-session |
| Agente Insights | P2 | tendencias, comparativo mensal, export |

### Por que algumas escolhas sao boas para o MVP

| Escolha | Motivo |
| --- | --- |
| Um especialista por turno | reduz complexidade e loops |
| Regex para extracao de transacao | previsivel e testavel |
| Orcamento sem LLM | numeros financeiros nao dependem de geracao |
| Validador separado | quality gate independente do especialista |
| Fallback in-process para MCP | demo nao quebra se subprocesso falhar |

### Proximo passo arquitetural natural

Se a apresentacao pedir "como ficaria mais agentico?", o caminho e:

1. Manter `StateGraph` como orquestrador.
2. Carregar tools via `get_mcp_tools()`.
3. Filtrar tools por especialista.
4. Injetar ferramentas no node.
5. Usar `create_agent()` ou um executor tool-calling somente onde fizer sentido.
6. Preservar `AgentResponse` e Validador como contrato final.

Exemplo conceitual:

```python
async def build_transacoes_agent():
    tools = await get_mcp_tools()
    allowed = [
        tool for tool in tools
        if tool.name in {"create_transaction", "find_similar_transactions"}
    ]
    return create_agent("openai:gpt-4.1", allowed)
```

Mas isso nao deve remover os contratos. Mesmo com tool-calling livre, a resposta final continua precisando caber em `AgentResponse`.

---

## 15. Perguntas Frequentes Para A Banca

### Por que nao um agente unico?

Porque um agente unico precisaria explicar conceitos, categorizar despesas, persistir transacoes, calcular orçamento e validar saldo no mesmo prompt. Separar especialistas reduz escopo, melhora testes e deixa o fluxo explicito.

### MCP e overkill para um monolito?

No MVP, MCP funciona como fronteira de extensibilidade. O fallback in-process evita custo operacional alto, mas o contrato de tool ja prepara o sistema para novos dominios como CSV, cambio ou relatorios.

### O sistema deixa a LLM mexer direto no banco?

Nao. A LLM nao acessa SQL. Persistencia passa por funcoes/tools com `user_id`, contratos Pydantic e repositorios de dominio.

### Como o sistema evita alucinacao de saldo?

O validador extrai valores e percentuais citados na resposta e compara contra `get_balance` e `get_budget_summary`. Se nao bater, rejeita e tenta regenerar.

### Receita tem categoria?

Nao. Receita usa `category=None`. Categorias de envelope budgeting se aplicam a despesas.

### O que acontece se ChromaDB cair?

CRUD continua no SQLite. `search_transactions` degrada para SQL LIKE. O sistema perde ranking semantico, mas nao perde operacao basica.

### O que acontece se MCP falhar no startup?

`get_mcp_tools()` registra warning e retorna `StructuredTool` in-process com as mesmas funcoes Python.

---

## 16. Checklist Antes Da Demo

- `.env` com `DEEPSEEK_API_KEY`.
- Banco SQLite migrado.
- Knowledge base seedada.
- Usuario de demo criado.
- Receita do mes registrada para cenarios de orçamento.
- Algumas despesas desbalanceadas para gerar alerta.
- ChromaDB populado com exemplos de categoria.
- Saber abrir rapidamente `graph.py`, `orchestrator.py`, `transacoes.py`, `validator.py` e `mcp/client.py`.
- Ter resposta pronta para "MCP e usado dinamicamente hoje?".

---

## 17. Frases Curtas Para Slides

| Tema | Frase |
| --- | --- |
| LangGraph | "O grafo torna o fluxo explicito: decidir, executar, validar." |
| AgentState | "E a memoria de trabalho entre os nos do turno." |
| Orquestrador | "A LLM classifica; o codigo roteia." |
| Contratos | "Prompt orienta; Pydantic obriga." |
| Tools | "Toda acao externa entra por uma funcao com contrato." |
| MCP | "Protocolo para expor ferramentas sem acoplar dominio ao agente." |
| Validador | "O LLM escreve; o banco confirma." |
| RAG | "Conhecimento recuperado antes da resposta, nao inventado durante." |
| Segurança | "`user_id` atravessa tudo: API, grafo, tool e query." |

---

## 18. Referencias

- Spec principal: `.specs/features/financial-assistant/spec.md`
- Design principal: `.specs/features/financial-assistant/design.md`
- React frontend spec: `.specs/features/react-frontend/spec.md`
- Grafo: `src/financial_assistant/agents/graph.py`
- Estado: `src/financial_assistant/agents/state.py`
- Orquestrador: `src/financial_assistant/agents/orchestrator.py`
- Especialistas: `src/financial_assistant/agents/specialists/`
- Validador: `src/financial_assistant/agents/validator.py`
- Contratos: `src/financial_assistant/contracts/`
- MCP client: `src/financial_assistant/mcp/client.py`
- MCP servers: `mcp_servers/finance/server.py`, `mcp_servers/chroma/server.py`
- API chat SSE: `src/financial_assistant/chat/router.py`

