// Tipos espelhando exatamente os contratos JSON do backend (Fase 1).
// Ver .specs/features/react-frontend/design.md e spec.md para os contratos de origem.

export interface User {
  id: string;
  name: string;
  email: string;
}

export interface CategoryBudget {
  category: string;
  label: string;
  spent: string;
  pct: number;
  min_pct: number;
  max_pct: number;
  status: "ok" | "alerta";
}

export interface DashboardSummary {
  month: string;
  total_income: string;
  total_expense: string;
  warning: string | null;
  categories: CategoryBudget[];
}

export interface Transaction {
  id: string;
  date: string; // ISO "YYYY-MM-DD"
  description: string;
  amount: string;
  type: "despesa" | "receita";
  category: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: { collection: string; doc_id: string }[];
  pending?: boolean;
}
