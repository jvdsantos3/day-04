import { useState, type FormEvent } from "react";
import { useChat } from "@/hooks/useChat";

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
    <div className="flex h-full flex-col space-y-4">
      <div className="flex-1 space-y-3 overflow-y-auto">
        {messages.map((message, index) => {
          if (message.isError) {
            return (
              <div
                key={index}
                className="rounded border border-expense bg-red-50 p-3 text-sm"
              >
                <p>{message.content}</p>
                <button
                  type="button"
                  onClick={() => handleRetry(lastUserContentBefore(messages, index))}
                  className="mt-2 rounded bg-expense px-3 py-1 text-sm text-white"
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
                  ? "ml-auto max-w-[75%] rounded bg-blue-600 p-3 text-sm text-white"
                  : "mr-auto max-w-[75%] rounded bg-neutral-100 p-3 text-sm"
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
          <div className="mr-auto max-w-[75%] rounded bg-neutral-100 p-3 text-sm text-neutral-text">
            digitando...
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          disabled={isSending}
          placeholder="Digite sua mensagem..."
          className="flex-1 rounded border border-neutral-300 p-2 text-sm"
        />
        <button
          type="submit"
          disabled={!canSend}
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          Enviar
        </button>
      </form>
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
