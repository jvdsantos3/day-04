import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { DashboardSummary } from "@/types/api";
import Money from "@/components/Money";
import CategoryCard from "@/components/CategoryCard";

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

export default function Dashboard() {
  const [month] = useState(currentMonth());

  const { data, isLoading } = useQuery({
    queryKey: ["summary", month],
    queryFn: () => fetchSummary(month),
  });

  if (isLoading) {
    return <div>Carregando...</div>;
  }

  if (!data) {
    return null;
  }

  return (
    <div className="space-y-6">
      {data.warning && (
        <div className="rounded border border-expense bg-red-50 p-4 text-sm">
          {data.warning} Registre sua receita pelo chat para acompanhar o orçamento.
        </div>
      )}

      <div className="flex gap-6">
        <div>
          <div className="text-sm text-neutral-text">Receita total</div>
          <div className="text-income text-xl font-semibold">
            <Money value={data.total_income} />
          </div>
        </div>
        <div>
          <div className="text-sm text-neutral-text">Despesas totais</div>
          <div className="text-expense text-xl font-semibold">
            <Money value={data.total_expense} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data.categories.map((category) => (
          <CategoryCard key={category.category} category={category} />
        ))}
      </div>
    </div>
  );
}
