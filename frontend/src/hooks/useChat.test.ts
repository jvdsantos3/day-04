import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useChat } from "./useChat";

type FetchEventSourceInit = {
  onmessage?: (ev: { event?: string; data: string }) => void;
  onclose?: () => void;
  onerror?: (err: unknown) => number | null | undefined | void;
  onopen?: (response: Response) => Promise<void>;
};

let capturedInit: FetchEventSourceInit | undefined;

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn((_url: string, init: FetchEventSourceInit) => {
    capturedInit = init;
    return Promise.resolve();
  }),
}));

describe("useChat", () => {
  beforeEach(() => {
    capturedInit = undefined;
    const store: Record<string, string> = {};
    vi.stubGlobal("sessionStorage", {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, value: string) => {
        store[key] = value;
      },
      removeItem: (key: string) => {
        delete store[key];
      },
      clear: () => {
        for (const key of Object.keys(store)) delete store[key];
      },
    });
    vi.stubGlobal("crypto", {
      randomUUID: () => "test-uuid-1234",
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("adiciona a mensagem do usuário imediatamente e marca isSending=true", () => {
    const { result } = renderHook(() => useChat());

    act(() => {
      result.current.sendMessage("oi");
    });

    expect(result.current.messages).toEqual([
      expect.objectContaining({ role: "user", content: "oi" }),
    ]);
    expect(result.current.isSending).toBe(true);
  });

  it("adiciona a mensagem do assistente ao receber onmessage padrão", async () => {
    const { result } = renderHook(() => useChat());

    act(() => {
      result.current.sendMessage("oi");
    });

    await waitFor(() => expect(capturedInit?.onmessage).toBeDefined());

    act(() => {
      capturedInit!.onmessage!({
        data: JSON.stringify({
          text: "Olá!",
          suggested_category: null,
          action: "none",
          metadata: {},
        }),
      });
    });

    await waitFor(() => {
      expect(result.current.messages).toContainEqual(
        expect.objectContaining({ role: "assistant", content: "Olá!" }),
      );
    });
  });

  it("marca isSending=false ao receber evento done", async () => {
    const { result } = renderHook(() => useChat());

    act(() => {
      result.current.sendMessage("oi");
    });

    await waitFor(() => expect(capturedInit?.onmessage).toBeDefined());

    act(() => {
      capturedInit!.onmessage!({ event: "done", data: "end" });
    });

    await waitFor(() => {
      expect(result.current.isSending).toBe(false);
    });
  });

  it("adiciona mensagem de erro e marca isSending=false ao receber onerror", async () => {
    const { result } = renderHook(() => useChat());

    act(() => {
      result.current.sendMessage("oi");
    });

    await waitFor(() => expect(capturedInit?.onerror).toBeDefined());

    act(() => {
      try {
        capturedInit!.onerror!(new Error("network fail"));
      } catch {
        // esperado: onerror lança para impedir retry automático da lib
      }
    });

    await waitFor(() => {
      expect(result.current.isSending).toBe(false);
    });
    expect(result.current.messages).toContainEqual(
      expect.objectContaining({ role: "assistant", isError: true }),
    );
  });

  it("onerror lança para impedir retry automático da biblioteca", async () => {
    const { result } = renderHook(() => useChat());

    act(() => {
      result.current.sendMessage("oi");
    });

    await waitFor(() => expect(capturedInit?.onerror).toBeDefined());

    expect(() => capturedInit!.onerror!(new Error("boom"))).toThrow();
  });

  it("gera e persiste session_id em sessionStorage no primeiro uso", () => {
    renderHook(() => useChat());

    expect(sessionStorage.getItem("chat_session_id")).toBe("test-uuid-1234");
  });
});
