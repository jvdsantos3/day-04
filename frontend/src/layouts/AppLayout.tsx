import { Outlet } from "react-router-dom";

// Layout mínimo do shell. Header/nav funcional (dados de usuário, logout)
// depende do hook useAuth, que só existe a partir da Fase 3 (T11).
export default function AppLayout() {
  return (
    <div>
      <header>
        <h1>Assistente Financeiro</h1>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
