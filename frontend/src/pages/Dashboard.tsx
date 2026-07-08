import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ConfirmDialog from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";
import { apiFetch, readApiError } from "@/lib/api";
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

async function fetchTransactions(
  month: string,
  category: string,
  type: string,
): Promise<Transaction[]> {
  const params = new URLSearchParams();
  if (month) params.set("month", month);
  if (category) params.set("category", category);
  if (type) params.set("type", type);

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
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const initialMonth = currentMonth();
  const [month, setMonth] = useState(initialMonth);
  const [category, setCategory] = useState("");
  const [type, setType] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Transaction | null>(null);

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["summary", month],
    queryFn: () => fetchSummary(month),
  });

  const {
    data: transactions,
    isLoading: transactionsLoading,
    error: transactionsError,
  } = useQuery({
    queryKey: ["transactions", month, category, type],
    queryFn: () => fetchTransactions(month, category, type),
    retry: false,
  });

  const deleteMutation = useMutation({
    mutationFn: async (transactionId: string) => {
      const response = await apiFetch(`/transactions/${transactionId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(
          await readApiError(response, "Falha ao excluir transação"),
        );
      }
    },
    onSuccess: () => {
      showToast("Transação excluída com sucesso.", "success");
      setPendingDelete(null);
    },
    onError: (error) => {
      showToast(
        error instanceof Error ? error.message : "Falha ao excluir transação",
        "error",
      );
    },
    onSettled: () => {
      setDeletingId(null);
      void queryClient.invalidateQueries({ queryKey: ["transactions"] });
      void queryClient.invalidateQueries({ queryKey: ["summary"] });
    },
  });

  function handleDeleteRequest(transaction: Transaction) {
    setPendingDelete(transaction);
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeletingId(pendingDelete.id);
    await deleteMutation.mutateAsync(pendingDelete.id);
  }

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

  const income = Number(summary.total_income);
  const expense = Number(summary.total_expense);
  const balance = income - expense;
  const expenseRate = income > 0 ? Math.min((expense / income) * 100, 100) : 0;
  const monthLabel = new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${summary.month}-01T00:00:00Z`));

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden rounded-4xl border border-white/10 bg-white/[0.07] p-6 shadow-2xl shadow-black/30 backdrop-blur-xl lg:p-8">
        <div className="absolute right-0 top-0 h-64 w-64 rounded-full bg-emerald-300/10 blur-3xl" />
        <div className="absolute bottom-0 left-1/3 h-48 w-48 rounded-full bg-cyan-300/10 blur-3xl" />

        <div className="relative grid gap-8 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
          <div className="space-y-5">
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-emerald-100">
              Visão de {monthLabel}
            </div>
            <div>
              <h2 className="max-w-3xl text-4xl font-black tracking-[-0.04em] text-white sm:text-5xl lg:text-6xl">
                Seu dinheiro em modo cockpit.
              </h2>
              <p className="mt-4 max-w-2xl text-base leading-7 text-slate-300">
                Acompanhe orçamento, gastos e decisões em uma tela só, com o
                assistente pronto para registrar e explicar movimentações.
              </p>
            </div>
          </div>

          <div className="rounded-3xl border border-emerald-300/20 bg-slate-950/60 p-5 shadow-2xl shadow-emerald-950/20">
            <p className="text-sm font-medium text-slate-400">Saldo projetado</p>
            <div className="mt-2 text-4xl font-black tracking-tight text-emerald-200">
              <Money value={balance.toFixed(2)} />
            </div>
            <div className="mt-5 h-2 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-linear-to-r from-emerald-300 to-cyan-300"
                style={{ width: `${100 - expenseRate}%` }}
              />
            </div>
            <div className="mt-3 flex justify-between text-xs font-medium text-slate-400">
              <span>{expenseRate.toFixed(0)}% usado</span>
              <span>{(100 - expenseRate).toFixed(0)}% livre</span>
            </div>
          </div>
        </div>
      </section>

      {summary.warning && (
        <div className="rounded-2xl border border-rose-300/30 bg-rose-400/10 p-4 text-sm text-rose-100 shadow-lg shadow-rose-950/20">
          {summary.warning} Registre sua receita pelo chat para acompanhar o orçamento.
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-3">
        <div className="rounded-3xl border border-white/10 bg-white/[0.07] p-5 backdrop-blur-xl">
          <div className="text-sm font-medium text-slate-400">Receita total</div>
          <div className="mt-3 text-3xl font-black tracking-tight text-income">
            <Money value={summary.total_income} />
          </div>
          <p className="mt-3 text-sm text-slate-400">Entrada consolidada do mês.</p>
        </div>
        <div className="rounded-3xl border border-white/10 bg-white/[0.07] p-5 backdrop-blur-xl">
          <div className="text-sm font-medium text-slate-400">Despesas totais</div>
          <div className="mt-3 text-3xl font-black tracking-tight text-expense">
            <Money value={summary.total_expense} />
          </div>
          <p className="mt-3 text-sm text-slate-400">Tudo que saiu no período.</p>
        </div>
        <div className="rounded-3xl border border-white/10 bg-white/[0.07] p-5 backdrop-blur-xl">
          <div className="text-sm font-medium text-slate-400">Categorias monitoradas</div>
          <div className="mt-3 text-3xl font-black tracking-tight text-white">
            {summary.categories.length}
          </div>
          <p className="mt-3 text-sm text-slate-400">Com alertas automáticos de orçamento.</p>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-200/80">
              Orçamento vivo
            </p>
            <h3 className="mt-2 text-2xl font-black tracking-tight text-white">
              Categorias e limites
            </h3>
          </div>
          <p className="max-w-xl text-sm text-slate-400">
            Verde indica margem saudável. Rosa acende quando uma categoria
            passa da faixa recomendada.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {summary.categories.map((c) => (
            <CategoryCard key={c.category} category={c} />
          ))}
        </div>
      </section>

      <section className="rounded-4xl border border-white/10 bg-slate-950/45 p-5 shadow-2xl shadow-black/20 backdrop-blur-xl">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-200/80">
              Extrato inteligente
            </p>
            <h3 className="mt-2 text-2xl font-black tracking-tight text-white">
              Transações
            </h3>
          </div>
          <TransactionFilters
            month={month}
            category={category}
            type={type}
            onMonthChange={setMonth}
            onCategoryChange={setCategory}
            onTypeChange={setType}
          />
        </div>

        {transactionsLoading ? (
          <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-sm text-slate-300">
            Carregando transações...
          </div>
        ) : (
          <TransactionTable
            transactions={transactions ?? []}
            onDelete={handleDeleteRequest}
            deletingId={deletingId}
          />
        )}
      </section>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Excluir transação?"
        description={
          pendingDelete
            ? `A transação "${pendingDelete.description}" será removida permanentemente.`
            : ""
        }
        confirmLabel="Excluir"
        loading={deletingId !== null}
        onConfirm={() => void confirmDelete()}
        onCancel={() => {
          if (deletingId === null) {
            setPendingDelete(null);
          }
        }}
      />
    </div>
  );
}
