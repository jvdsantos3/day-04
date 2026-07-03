import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
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
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 focus-visible:outline-[#65f7b0]";
  const FIELD_CLASS =
    "mt-2 w-full rounded-2xl border border-white/10 bg-white/[0.08] px-4 py-3 text-white outline-none transition placeholder:text-slate-500 hover:border-white/20";

  return (
    <div className="grid min-h-[calc(100vh-10rem)] place-items-center">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-4xl border border-white/10 bg-white/[0.07] shadow-2xl shadow-black/30 backdrop-blur-xl lg:grid-cols-[0.95fr_1.05fr]">
        <section className="relative hidden overflow-hidden bg-slate-950/60 p-8 lg:block">
          <div className="absolute -left-16 top-10 h-56 w-56 rounded-full bg-emerald-300/15 blur-3xl" />
          <div className="absolute bottom-0 right-0 h-64 w-64 rounded-full bg-cyan-300/10 blur-3xl" />
          <div className="relative flex h-full flex-col justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.32em] text-emerald-200">
                Finance AI
              </p>
              <h2 className="mt-5 text-5xl font-black tracking-tighter text-white">
                Controle seu dinheiro com um agente ao lado.
              </h2>
              <p className="mt-5 text-sm leading-6 text-slate-300">
                Dashboard, orçamento e chat financeiro prontos para uma demo
                clara e convincente.
              </p>
            </div>
            <div className="rounded-3xl border border-emerald-300/20 bg-emerald-300/10 p-5">
              <p className="text-sm font-bold text-emerald-100">Demo preparada</p>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                Entre para mostrar registros, categorias e respostas do assistente.
              </p>
            </div>
          </div>
        </section>

        <form onSubmit={handleSubmit} className="p-6 sm:p-8 lg:p-10">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-200/80">
            Acesso
          </p>
          <h2 className="mt-3 text-3xl font-black tracking-tight text-white">
            Entrar no cockpit
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            Use sua conta para abrir o dashboard financeiro.
          </p>

          {/* Erro do login (401) é genérico ao form (não aponta um campo
              específico), então associamos ao campo de senha por ser o último
              preenchido antes do submit (UI-A11Y-02). */}
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
            {loading ? "Entrando..." : "Entrar"}
          </button>

          <p className="mt-6 text-center text-sm text-slate-400">
            Ainda não tem conta?{" "}
            <Link
              to="/register"
              className={`font-bold text-emerald-200 hover:text-emerald-100 ${FOCUS_RING}`}
            >
              Criar conta
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
