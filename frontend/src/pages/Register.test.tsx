import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Register from "./Register";

function renderRegister() {
  return render(
    <MemoryRouter initialEntries={["/register"]}>
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="/dashboard" element={<div>Dashboard Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Register", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renderiza form com nome/email/senha", () => {
    renderRegister();
    expect(screen.getByLabelText(/nome/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/senha/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /criar conta/i })).toBeInTheDocument();
  });

  it("senha curta bloqueia envio e mostra erro sem chamar a API", async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByLabelText(/nome/i), "Ana");
    await user.type(screen.getByLabelText(/email/i), "ana@example.com");
    await user.type(screen.getByLabelText(/senha/i), "curta");
    await user.click(screen.getByRole("button", { name: /criar conta/i }));

    expect(
      await screen.findByText("A senha deve ter no mínimo 8 caracteres"),
    ).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("submit válido navega para /dashboard", async () => {
    const user = userEvent.setup();
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: async () => ({ user: { id: "1", name: "Ana", email: "ana@example.com" } }),
    });

    renderRegister();
    await user.type(screen.getByLabelText(/nome/i), "Ana");
    await user.type(screen.getByLabelText(/email/i), "ana@example.com");
    await user.type(screen.getByLabelText(/senha/i), "password123");
    await user.click(screen.getByRole("button", { name: /criar conta/i }));

    await waitFor(() => {
      expect(screen.getByText("Dashboard Page")).toBeInTheDocument();
    });
  });

  it("submit com email duplicado exibe mensagem exata sem navegar", async () => {
    const user = userEvent.setup();
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Email já cadastrado" }),
    });

    renderRegister();
    await user.type(screen.getByLabelText(/nome/i), "Ana");
    await user.type(screen.getByLabelText(/email/i), "ana@example.com");
    await user.type(screen.getByLabelText(/senha/i), "password123");
    await user.click(screen.getByRole("button", { name: /criar conta/i }));

    expect(await screen.findByText("Email já cadastrado")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard Page")).not.toBeInTheDocument();
  });

  it("submit com email duplicado associa erro ao campo de senha via aria-describedby (UI-A11Y-02)", async () => {
    const user = userEvent.setup();
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Email já cadastrado" }),
    });

    renderRegister();
    await user.type(screen.getByLabelText(/nome/i), "Ana");
    await user.type(screen.getByLabelText(/email/i), "ana@example.com");
    await user.type(screen.getByLabelText(/senha/i), "password123");
    await user.click(screen.getByRole("button", { name: /criar conta/i }));

    const errorElement = await screen.findByRole("alert");
    expect(errorElement).toHaveTextContent("Email já cadastrado");
    expect(errorElement.id).toBeTruthy();

    const passwordInput = screen.getByLabelText(/senha/i);
    expect(passwordInput).toHaveAttribute("aria-describedby", errorElement.id);
    expect(passwordInput).toHaveAttribute("aria-invalid", "true");
  });

  it("botão de submit tem classe de foco visível aplicada (UI-A11Y-01)", () => {
    renderRegister();
    const submitButton = screen.getByRole("button", { name: /criar conta/i });
    expect(submitButton).toHaveClass("focus-visible:outline");
    expect(submitButton).toHaveClass("focus-visible:outline-blue-600");
  });
});
