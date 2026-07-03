// Teste de integração de página inteira (Fix 1 / UI-AUTH-01, UI-AUTH-02):
// monta AuthProvider + ProtectedRoute + Login/Register REAIS, na mesma
// topologia de rotas de App.tsx (mas com MemoryRouter em vez de
// BrowserRouter, para controlar a rota inicial em teste).
//
// Login.test.tsx/Register.test.tsx (isolados) usam uma rota "/dashboard"
// fake fora do AuthProvider/ProtectedRoute reais — isso mascarou o bug em
// que Login/Register navegavam sem nunca popular o `user` do AuthProvider,
// fazendo ProtectedRoute redirecionar de volta para /login. Este teste
// reproduz a árvore real para provar que o fix (setUser antes de navigate)
// realmente chega à rota protegida.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/hooks/useAuth";
import ProtectedRoute from "@/components/ProtectedRoute";
import Login from "@/pages/Login";
import Register from "@/pages/Register";

function renderApp(initialEntry: "/login" | "/register") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route element={<ProtectedRoute />}>
              <Route path="/dashboard" element={<div>Dashboard Page Marker</div>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Login/Register -> AuthProvider -> ProtectedRoute (integração real)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("login bem-sucedido sincroniza o AuthProvider e chega ao dashboard protegido", async () => {
    const user = userEvent.setup();
    const fetchMock = fetch as ReturnType<typeof vi.fn>;

    // GET /api/auth/me no mount do AuthProvider: usuário ainda não logado.
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Não autenticado" }),
    });

    renderApp("/login");

    // Aguarda o AuthProvider resolver o fetch de mount (loading -> false)
    // antes de interagir com o form, para não disparar o submit durante loading.
    await waitFor(() => {
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    });

    // POST /api/auth/login: sucesso, corpo já traz o user.
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        user: { id: "1", name: "Ana", email: "ana@example.com" },
      }),
    });

    await user.type(screen.getByLabelText(/email/i), "ana@example.com");
    await user.type(screen.getByLabelText(/senha/i), "password123");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    // Deve chegar de fato ao dashboard protegido, sem ficar preso no form
    // de login (o bug fazia ProtectedRoute redirecionar de volta a /login
    // porque `user` continuava null no AuthProvider).
    await waitFor(() => {
      expect(screen.getByText("Dashboard Page Marker")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /entrar/i })).not.toBeInTheDocument();
  });

  it("registro bem-sucedido sincroniza o AuthProvider e chega ao dashboard protegido", async () => {
    const user = userEvent.setup();
    const fetchMock = fetch as ReturnType<typeof vi.fn>;

    // GET /api/auth/me no mount do AuthProvider: usuário ainda não logado.
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Não autenticado" }),
    });

    renderApp("/register");

    await waitFor(() => {
      expect(screen.getByLabelText(/nome/i)).toBeInTheDocument();
    });

    // POST /api/auth/register: sucesso (201), corpo já traz o user.
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: async () => ({
        user: { id: "2", name: "Beatriz", email: "bea@example.com" },
      }),
    });

    await user.type(screen.getByLabelText(/nome/i), "Beatriz");
    await user.type(screen.getByLabelText(/email/i), "bea@example.com");
    await user.type(screen.getByLabelText(/senha/i), "password123");
    await user.click(screen.getByRole("button", { name: /criar conta/i }));

    await waitFor(() => {
      expect(screen.getByText("Dashboard Page Marker")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: /criar conta/i }),
    ).not.toBeInTheDocument();
  });
});
