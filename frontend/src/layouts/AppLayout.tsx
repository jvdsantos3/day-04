import { Outlet, useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";

const FOCUS_RING =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600";

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div>
      <header className="flex flex-wrap items-center justify-between gap-2 p-4">
        <h1 className="text-lg font-semibold">Assistente Financeiro</h1>
        {user && (
          <nav className="flex flex-wrap items-center gap-4">
            <span>{user.name}</span>
            <Link to="/dashboard" className={FOCUS_RING}>
              Dashboard
            </Link>
            <Link to="/chat" className={FOCUS_RING}>
              Chat
            </Link>
            <button type="button" onClick={handleLogout} className={FOCUS_RING}>
              Sair
            </button>
          </nav>
        )}
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
