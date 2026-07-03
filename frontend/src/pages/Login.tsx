import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import type { User } from "@/types/api";

export default function Login() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const response = await apiFetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        if (response.status === 401) {
          const data = await response.json();
          setError(data.detail ?? "Email ou senha inválidos");
        } else {
          setError("Ocorreu um erro. Tente novamente.");
        }
        return;
      }

      // Popula o AuthProvider com o usuário já retornado no corpo do login
      // ANTES de navegar — ProtectedRoute lê esse mesmo contexto, e sem isso
      // o redirect ocorre com o `user=null` do fetch de mount (UI-AUTH-01).
      const body = (await response.json()) as { user: User };
      setUser(body.user);
      navigate("/dashboard");
    } catch {
      setError("Ocorreu um erro. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  const FOCUS_RING =
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600";

  return (
    <form onSubmit={handleSubmit}>
      <h2>Login</h2>
      {/* Erro do login (401) é genérico ao form (não aponta um campo
          específico), então associamos ao campo de senha por ser o último
          preenchido antes do submit (UI-A11Y-02). */}
      {error && (
        <p role="alert" id="password-error">
          {error}
        </p>
      )}
      <label htmlFor="email">Email</label>
      <input
        id="email"
        type="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        required
        className={FOCUS_RING}
      />
      <label htmlFor="password">Senha</label>
      <input
        id="password"
        type="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
        aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? "password-error" : undefined}
        className={FOCUS_RING}
      />
      <button type="submit" disabled={loading} className={FOCUS_RING}>
        {loading ? "Entrando..." : "Entrar"}
      </button>
    </form>
  );
}
