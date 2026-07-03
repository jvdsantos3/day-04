// Wrapper genérico de fetch para a API do backend.
// Sempre envia cookies (access_token) e usa /api como base path.
// Lógica específica de auth/dashboard/chat fica nas próximas fases.

export function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  return fetch(`/api${path}`, {
    ...options,
    credentials: "include",
  });
}
