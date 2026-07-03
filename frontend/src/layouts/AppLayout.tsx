import { Outlet, useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";

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
            <Link to="/dashboard">Dashboard</Link>
            <Link to="/chat">Chat</Link>
            <button type="button" onClick={handleLogout}>
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
