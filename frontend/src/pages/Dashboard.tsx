import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { DashboardSummary, Transaction } from "@/types/api";
import Money from "@/components/Money";
import CategoryCard from "@/components/CategoryCard";
import TransactionFilters from "@/components/TransactionFilters";
import TransactionTable from "@/components/TransactionTable";

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

async function fetchSummary(month: string): Promise<DashboardSummary> {
  const response = await apiFetch(`/dashboard/summary?month=${month}`);
  if (!response.ok) {
    throw new Error("Falha ao carregar resumo do dashboard");
  }
  return response.json();
}

class InvalidMonthError extends Error {}

async function fetchTransactions(month: string, category: string): Promise<Transaction[]> {
  const params = new URLSearchParams();
  if (month) params.set("month", month);
  if (category) params.set("category", category);

  const response = await apiFetch(`/transactions?${params.toString()}`);
  if (response.status === 400) {
    // Edge case do spec: mês em formato inválido -> API 400 -> SPA reseta
    // para o mês atual (ver Edge Cases em spec.md).
    throw new InvalidMonthError("Filtro de mês inválido");
  }
  if (!response.ok) {
    throw new Error("Falha ao carregar transações");
  }
  const data = (await response.json()) as { transactions: Transaction[] };
  return data.transactions;
}

export default function Dashboard() {
  const initialMonth = currentMonth();
  const [month, setMonth] = useState(initialMonth);
  const [category, setCategory] = useState("");

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["summary", month],
    queryFn: () => fetchSummary(month),
  });

  const {
    data: transactions,
    isLoading: transactionsLoading,
    error: transactionsError,
  } = useQuery({
    queryKey: ["transactions", month, category],
    queryFn: () => fetchTransactions(month, category),
    retry: false,
  });

  // Edge case do spec: mês em formato inválido -> API 400 -> reseta para o
  // mês atual (onError foi removido do useQuery na v5; useEffect é o padrão
  // recomendado para reagir a erros de query).
  useEffect(() => {
    if (transactionsError instanceof InvalidMonthError) {
      setMonth(initialMonth);
    }
  }, [transactionsError, initialMonth]);

  if (summaryLoading) {
    return <div>Carregando...</div>;
  }

  if (!summary) {
    return null;
  }

  return (
    <div className="space-y-6">
      {summary.warning && (
        <div className="rounded border border-expense bg-red-50 p-4 text-sm">
          {summary.warning} Registre sua receita pelo chat para acompanhar o orçamento.
        </div>
      )}

      <div className="flex gap-6">
        <div>
          <div className="text-sm text-neutral-text">Receita total</div>
          <div className="text-income text-xl font-semibold">
            <Money value={summary.total_income} />
          </div>
        </div>
        <div>
          <div className="text-sm text-neutral-text">Despesas totais</div>
          <div className="text-expense text-xl font-semibold">
            <Money value={summary.total_expense} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {summary.categories.map((c) => (
          <CategoryCard key={c.category} category={c} />
        ))}
      </div>

      <TransactionFilters
        month={month}
        category={category}
        onMonthChange={setMonth}
        onCategoryChange={setCategory}
      />

      {transactionsLoading ? (
        <div>Carregando transações...</div>
      ) : (
        <TransactionTable transactions={transactions ?? []} />
      )}
    </div>
  );
}
