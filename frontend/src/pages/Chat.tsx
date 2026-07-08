import { useState, type FormEvent } from "react";
import { useChat } from "@/hooks/useChat";

const FOCUS_RING =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#65f7b0]";

const QUICK_PROMPTS = [
  "Quanto gastei este mês?",
  "Registre uma despesa de R$ 42 com almoço hoje",
  "Como está meu orçamento de conforto?",
];

export default function Chat() {
  const { messages, sendMessage, isSending } = useChat();
  const [input, setInput] = useState("");

  const canSend = input.trim().length > 0 && !isSending;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSend) return;
    sendMessage(input.trim());
    setInput("");
  }

  function handleRetry(content: string) {
    if (isSending) return;
    sendMessage(content);
  }

  return (
    <div className="grid min-h-[calc(100vh-10rem)] gap-6 lg:grid-cols-[0.85fr_1.15fr]">
      <aside className="rounded-4xl border border-white/10 bg-white/[0.07] p-6 shadow-2xl shadow-black/25 backdrop-blur-xl">
        <div className="inline-flex rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-cyan-100">
          Agente financeiro
        </div>
        <h2 className="mt-5 text-4xl font-black tracking-[-0.04em] text-white">
          Converse com seus dados.
        </h2>
        <p className="mt-4 text-sm leading-6 text-slate-300">
          Pergunte sobre gastos, registre transações e deixe o assistente
          explicar decisões com base no seu histórico financeiro.
        </p>

        <div className="mt-8 space-y-3">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
            Sugestões
          </p>
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => sendMessage(prompt)}
              disabled={isSending}
              className={`w-full rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3 text-left text-sm font-semibold text-slate-200 transition hover:border-emerald-300/30 hover:bg-emerald-300/10 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`}
            >
              {prompt}
            </button>
          ))}
        </div>
      </aside>

      <section className="flex min-h-144 flex-col overflow-hidden rounded-4xl border border-white/10 bg-slate-950/55 shadow-2xl shadow-black/30 backdrop-blur-xl">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
          <div>
            <p className="text-sm font-bold text-white">Chat financeiro</p>
            <p className="text-xs text-slate-400">Respostas com base nos seus dados financeiros</p>
          </div>
          <span className="rounded-full bg-emerald-300/15 px-3 py-1 text-xs font-black uppercase tracking-widest text-emerald-100">
            online
          </span>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {messages.length === 0 && (
            <div className="grid h-full min-h-80 place-items-center rounded-3xl border border-dashed border-white/10 bg-white/3 p-8 text-center">
              <div>
                <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-emerald-300/15 text-2xl">
                  F
                </div>
                <p className="mt-4 text-xl font-black text-white">
                  Comece com uma pergunta ou registro.
                </p>
                <p className="mt-2 max-w-md text-sm leading-6 text-slate-400">
                  Exemplo: "registre R$ 120 de mercado hoje" ou "onde estou
                  gastando mais este mês?".
                </p>
              </div>
            </div>
          )}

          {messages.map((message, index) => {
            if (message.isError) {
              return (
                <div
                  key={index}
                  className="mr-auto max-w-[82%] rounded-3xl border border-rose-300/30 bg-rose-400/10 p-4 text-sm text-rose-50"
                >
                  <p>{message.content}</p>
                  <button
                    type="button"
                    onClick={() => handleRetry(lastUserContentBefore(messages, index))}
                    className={`mt-3 rounded-full bg-rose-300 px-4 py-2 text-sm font-bold text-slate-950 ${FOCUS_RING}`}
                  >
                    Tentar novamente
                  </button>
                </div>
              );
            }

            return (
              <div
                key={index}
                className={
                  message.role === "user"
                    ? "ml-auto max-w-[82%] rounded-3xl rounded-br-md bg-linear-to-br from-emerald-300 to-cyan-300 p-4 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-950/30"
                    : "mr-auto max-w-[82%] rounded-3xl rounded-bl-md border border-white/10 bg-white/[0.07] p-4 text-sm leading-6 text-slate-100"
                }
              >
                <p>{message.content}</p>
                {message.sources && message.sources.length > 0 && (
                  <ul className="mt-2 space-y-1 text-xs opacity-80">
                    {message.sources.map((source, sourceIndex) => (
                      <li key={sourceIndex}>
                        fonte: {source.collection}/{source.doc_id}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}

          {isSending && (
            <div className="mr-auto max-w-[82%] rounded-3xl rounded-bl-md border border-white/10 bg-white/[0.07] p-4 text-sm text-slate-300">
              analisando seus dados...
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="border-t border-white/10 p-4">
          <div className="flex gap-3 rounded-3xl border border-white/10 bg-white/6 p-2">
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              disabled={isSending}
              placeholder="Digite uma pergunta ou registre uma transação..."
              className={`min-w-0 flex-1 rounded-2xl border-0 bg-transparent px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 disabled:opacity-60 ${FOCUS_RING}`}
            />
            <button
              type="submit"
              disabled={!canSend}
              className={`rounded-2xl bg-emerald-300 px-5 py-3 text-sm font-black text-slate-950 shadow-lg shadow-emerald-400/20 transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`}
            >
              Enviar
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

// Localiza o conteúdo da última mensagem do usuário antes de uma mensagem de
// erro, para permitir reenviá-la no botão "Tentar novamente".
function lastUserContentBefore(
  messages: { role: "user" | "assistant"; content: string }[],
  index: number,
): string {
  for (let i = index - 1; i >= 0; i--) {
    if (messages[i].role === "user") {
      return messages[i].content;
    }
  }
  return "";
}
