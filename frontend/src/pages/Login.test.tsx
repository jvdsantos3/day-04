import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Login from "./Login";
import { AuthProvider } from "@/hooks/useAuth";

// Login agora depende de useAuth() (Fix UI-AUTH-01: setUser antes de
// navigate), então precisa de um AuthProvider real na árvore. O GET
// /api/auth/me do mount do AuthProvider é mockado com 401 (visitante) em
// todos os testes deste arquivo, consumindo a 1ª chamada de fetch.
function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<div>Dashboard Page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("Login", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    // Consome o GET /api/auth/me do mount do AuthProvider (visitante, 401)
    // antes de cada teste configurar seu próprio mock para o POST de login.
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Não autenticado" }),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renderiza form com campos email/senha e botão submit", () => {
    renderLogin();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/senha/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /entrar/i })).toBeInTheDocument();
  });

  it("submit com credenciais válidas navega para /dashboard", async () => {
    const user = userEvent.setup();
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ user: { id: "1", name: "Ana", email: "ana@example.com" } }),
    });

    renderLogin();
    await user.type(screen.getByLabelText(/email/i), "ana@example.com");
    await user.type(screen.getByLabelText(/senha/i), "password123");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    await waitFor(() => {
      expect(screen.getByText("Dashboard Page")).toBeInTheDocument();
    });
  });

  it("submit com 401 exibe mensagem de erro sem navegar", async () => {
    const user = userEvent.setup();
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Email ou senha inválidos" }),
    });

    renderLogin();
    await user.type(screen.getByLabelText(/email/i), "ana@example.com");
    await user.type(screen.getByLabelText(/senha/i), "wrongpass");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByText("Email ou senha inválidos")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard Page")).not.toBeInTheDocument();
  });

  it("submit com 401 associa erro ao campo de senha via aria-describedby (UI-A11Y-02)", async () => {
    const user = userEvent.setup();
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Email ou senha inválidos" }),
    });

    renderLogin();
    await user.type(screen.getByLabelText(/email/i), "ana@example.com");
    await user.type(screen.getByLabelText(/senha/i), "wrongpass");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    const errorElement = await screen.findByRole("alert");
    expect(errorElement).toHaveTextContent("Email ou senha inválidos");
    expect(errorElement.id).toBeTruthy();

    const passwordInput = screen.getByLabelText(/senha/i);
    expect(passwordInput).toHaveAttribute("aria-describedby", errorElement.id);
    expect(passwordInput).toHaveAttribute("aria-invalid", "true");
  });

  it("botão de submit tem classe de foco visível aplicada (UI-A11Y-01)", () => {
    renderLogin();
    const submitButton = screen.getByRole("button", { name: /entrar/i });
    expect(submitButton).toHaveClass("focus-visible:outline");
    expect(submitButton).toHaveClass("focus-visible:outline-blue-600");
  });

  it("botão fica desabilitado durante o loading", async () => {
    const user = userEvent.setup();
    let resolveFetch: (value: unknown) => void = () => {};
    (fetch as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );

    renderLogin();
    await user.type(screen.getByLabelText(/email/i), "ana@example.com");
    await user.type(screen.getByLabelText(/senha/i), "password123");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(screen.getByRole("button")).toBeDisabled();

    resolveFetch({
      ok: true,
      status: 200,
      json: async () => ({ user: { id: "1", name: "Ana", email: "ana@example.com" } }),
    });
  });
});
