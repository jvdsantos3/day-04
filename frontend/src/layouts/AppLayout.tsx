import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";

const FOCUS_RING =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#65f7b0]";

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="relative min-h-screen overflow-hidden text-slate-100">
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(148,163,184,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.05)_1px,transparent_1px)] bg-size-[48px_48px]" />
      <div className="pointer-events-none absolute left-1/2 top-0 h-80 w-80 -translate-x-1/2 rounded-full bg-cyan-400/10 blur-3xl" />

      <header className="sticky top-0 z-20 border-b border-white/10 bg-[#07111f]/80 px-4 py-4 backdrop-blur-xl sm:px-6">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-2xl border border-emerald-300/30 bg-emerald-300/10 shadow-[0_0_30px_rgba(101,247,176,0.18)]">
              <span className="text-lg font-black text-emerald-200">F</span>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.32em] text-emerald-200/80">
                Finance AI
              </p>
              <h1 className="text-lg font-semibold tracking-tight text-white">
                Assistente Financeiro
              </h1>
            </div>
          </div>

          {user && (
            <nav className="flex flex-wrap items-center gap-2 rounded-full border border-white/10 bg-white/6 p-1.5 shadow-2xl shadow-black/20">
              <span className="hidden px-3 text-sm font-medium text-slate-300 sm:inline">
                {user.name}
              </span>
              <NavLink
                to="/dashboard"
                className={({ isActive }) =>
                  `rounded-full px-4 py-2 text-sm font-semibold transition ${FOCUS_RING} ${
                    isActive
                      ? "bg-emerald-300 text-slate-950 shadow-lg shadow-emerald-400/20"
                      : "text-slate-300 hover:bg-white/10 hover:text-white"
                  }`
                }
              >
                Dashboard
              </NavLink>
              <NavLink
                to="/chat"
                className={({ isActive }) =>
                  `rounded-full px-4 py-2 text-sm font-semibold transition ${FOCUS_RING} ${
                    isActive
                      ? "bg-emerald-300 text-slate-950 shadow-lg shadow-emerald-400/20"
                      : "text-slate-300 hover:bg-white/10 hover:text-white"
                  }`
                }
              >
                Chat
              </NavLink>
              <button
                type="button"
                onClick={handleLogout}
                className={`rounded-full px-4 py-2 text-sm font-semibold text-slate-300 transition hover:bg-rose-400/10 hover:text-rose-200 ${FOCUS_RING}`}
              >
                Sair
              </button>
            </nav>
          )}
        </div>
      </header>
      <main className="relative z-10 mx-auto min-h-[calc(100vh-81px)] max-w-7xl px-4 py-8 sm:px-6 lg:py-10">
        <Outlet />
      </main>
    </div>
  );
}
