import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import type { User } from "@/types/api";

const MIN_PASSWORD_LENGTH = 8;

export default function Register() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError("A senha deve ter no mínimo 8 caracteres");
      return;
    }

    setLoading(true);
    try {
      const response = await apiFetch("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password }),
      });

      if (!response.ok) {
        if (response.status === 400) {
          const data = await response.json();
          setError(data.detail ?? "Não foi possível criar a conta");
        } else {
          setError("Ocorreu um erro. Tente novamente.");
        }
        return;
      }

      // Popula o AuthProvider com o usuário já retornado no corpo do
      // register ANTES de navegar — ver mesma correção/motivo em Login.tsx
      // (UI-AUTH-02).
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
      <h2>Registro</h2>
      {/* Erros do registro (senha curta e email duplicado, 400) são
          genéricos ao form, então associamos ao campo de senha por ser o
          último preenchido antes do submit (UI-A11Y-02), consistente com
          Login.tsx. */}
      {error && (
        <p role="alert" id="password-error">
          {error}
        </p>
      )}
      <label htmlFor="name">Nome</label>
      <input
        id="name"
        type="text"
        value={name}
        onChange={(event) => setName(event.target.value)}
        required
        className={FOCUS_RING}
      />
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
        {loading ? "Criando conta..." : "Criar conta"}
      </button>
    </form>
  );
}
