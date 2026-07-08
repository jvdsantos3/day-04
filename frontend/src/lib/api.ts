// Wrapper genérico de fetch para a API do backend.
// Sempre envia cookies (access_token) e usa /api como base path.

export function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  return fetch(`/api${path}`, {
    ...options,
    credentials: "include",
  });
}

export async function readApiError(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string | { msg?: string }[] };
    if (typeof data.detail === "string" && data.detail.trim()) {
      return data.detail;
    }
  } catch {
    // Respostas sem corpo JSON (ex.: 204) caem no fallback.
  }
  return fallback;
}
