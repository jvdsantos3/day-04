import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
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
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 focus-visible:outline-[#65f7b0]";
  const FIELD_CLASS =
    "mt-2 w-full rounded-2xl border border-white/10 bg-white/[0.08] px-4 py-3 text-white outline-none transition placeholder:text-slate-500 hover:border-white/20";

  return (
    <div className="grid min-h-[calc(100vh-10rem)] place-items-center">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-4xl border border-white/10 bg-white/[0.07] shadow-2xl shadow-black/30 backdrop-blur-xl lg:grid-cols-[1.05fr_0.95fr]">
        <form onSubmit={handleSubmit} className="p-6 sm:p-8 lg:p-10">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-emerald-200/80">
            Primeira entrada
          </p>
          <h2 className="mt-3 text-3xl font-black tracking-tight text-white">
            Criar conta
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            Configure seu acesso e comece a registrar movimentações pelo chat.
          </p>

          {/* Erros do registro (senha curta e email duplicado, 400) são
              genéricos ao form, então associamos ao campo de senha por ser o
              último preenchido antes do submit (UI-A11Y-02), consistente com
              Login.tsx. */}
          {error && (
            <p
              role="alert"
              id="password-error"
              className="mt-5 rounded-2xl border border-rose-300/30 bg-rose-400/10 p-3 text-sm text-rose-100"
            >
              {error}
            </p>
          )}

          <div className="mt-6 space-y-5">
            <div>
              <label htmlFor="name" className="text-sm font-bold text-slate-200">
                Nome
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
                className={`${FIELD_CLASS} ${FOCUS_RING}`}
              />
            </div>
            <div>
              <label htmlFor="email" className="text-sm font-bold text-slate-200">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                className={`${FIELD_CLASS} ${FOCUS_RING}`}
              />
            </div>
            <div>
              <label htmlFor="password" className="text-sm font-bold text-slate-200">
                Senha
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                aria-invalid={error ? "true" : undefined}
                aria-describedby={error ? "password-error" : undefined}
                className={`${FIELD_CLASS} ${FOCUS_RING}`}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className={`mt-7 w-full rounded-2xl bg-emerald-300 px-5 py-3 text-sm font-black text-slate-950 shadow-lg shadow-emerald-400/20 transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`}
          >
            {loading ? "Criando conta..." : "Criar conta"}
          </button>

          <p className="mt-6 text-center text-sm text-slate-400">
            Já tem conta?{" "}
            <Link to="/login" className={`font-bold text-emerald-200 hover:text-emerald-100 ${FOCUS_RING}`}>
              Entrar
            </Link>
          </p>
        </form>

        <section className="relative hidden overflow-hidden bg-slate-950/60 p-8 lg:block">
          <div className="absolute -right-20 top-12 h-64 w-64 rounded-full bg-emerald-300/15 blur-3xl" />
          <div className="absolute bottom-0 left-0 h-56 w-56 rounded-full bg-cyan-300/10 blur-3xl" />
          <div className="relative flex h-full flex-col justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.32em] text-cyan-200">
                Orçamento guiado
              </p>
              <h2 className="mt-5 text-5xl font-black tracking-tighter text-white">
                Um assistente que registra, classifica e explica.
              </h2>
              <p className="mt-5 text-sm leading-6 text-slate-300">
                Ideal para mostrar LangGraph, agentes especialistas, contratos
                e guardrails com uma interface que sustenta a narrativa.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-3xl border border-white/10 bg-white/6 p-4">
                <p className="text-2xl font-black text-emerald-200">5</p>
                <p className="mt-1 text-xs text-slate-400">categorias</p>
              </div>
              <div className="rounded-3xl border border-white/10 bg-white/6 p-4">
                <p className="text-2xl font-black text-cyan-200">AI</p>
                <p className="mt-1 text-xs text-slate-400">chat guiado</p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
