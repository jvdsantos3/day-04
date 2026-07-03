import { useCallback, useRef, useState } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import type { AgentResponse, ChatMessage } from "@/types/api";

const SESSION_STORAGE_KEY = "chat_session_id";
const REQUEST_TIMEOUT_MS = 120_000;

function getOrCreateSessionId(): string {
  const existing = sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const created = crypto.randomUUID();
  sessionStorage.setItem(SESSION_STORAGE_KEY, created);
  return created;
}

interface UseChatResult {
  messages: ChatMessage[];
  sendMessage: (text: string) => void;
  isSending: boolean;
}

export function useChat(): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const sessionIdRef = useRef<string>(getOrCreateSessionId());
  const lastUserMessageRef = useRef<string>("");

  const sendMessage = useCallback((text: string) => {
    lastUserMessageRef.current = text;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setIsSending(true);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    fetchEventSource("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ message: text, session_id: sessionIdRef.current }),
      signal: controller.signal,
      openWhenHidden: true,
      async onopen(response) {
        if (!response.ok) {
          throw new Error(`Falha na requisição de chat: ${response.status}`);
        }
      },
      onmessage(ev) {
        if (!ev.event) {
          const payload = JSON.parse(ev.data) as AgentResponse;
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: payload.text,
              sources: payload.metadata?.sources,
            },
          ]);
        } else if (ev.event === "done") {
          setIsSending(false);
        }
      },
      onclose() {
        setIsSending(false);
      },
      onerror(err) {
        clearTimeout(timeoutId);
        const isTimeout = controller.signal.aborted;
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: isTimeout
              ? "Erro: tempo limite excedido ao aguardar resposta."
              : "Erro: não foi possível obter resposta do assistente.",
            isError: true,
          },
        ]);
        setIsSending(false);
        // Lança o erro para impedir o retry automático da lib: a spec quer
        // que o usuário decida tentar de novo (botão "Tentar novamente"),
        // não uma reconexão transparente em segundo plano.
        throw err;
      },
    }).finally(() => {
      clearTimeout(timeoutId);
    });
  }, []);

  return { messages, sendMessage, isSending };
}
