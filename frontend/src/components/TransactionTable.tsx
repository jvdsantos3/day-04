import type { Transaction } from "@/types/api";
import Money from "@/components/Money";

const FOCUS_RING =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#65f7b0]";

// Tabela de transações filtradas (UI-DASH-03). Lista vazia -> estado vazio
// com mensagem clara em vez de uma tabela sem linhas (AC5).
export default function TransactionTable({
  transactions,
  onDelete,
  deletingId = null,
}: {
  transactions: Transaction[];
  onDelete?: (transaction: Transaction) => void;
  deletingId?: string | null;
}) {
  if (transactions.length === 0) {
    return (
      <div className="rounded-3xl border border-dashed border-white/15 bg-white/4 p-8 text-center">
        <p className="text-lg font-bold text-white">
          Nenhuma transação encontrada para este filtro.
        </p>
        <p className="mt-2 text-sm text-slate-400">
          Ajuste os filtros ou registre uma movimentação pelo chat.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-3xl border border-white/10">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse">
          <thead className="bg-white/6">
            <tr className="text-left text-xs font-black uppercase tracking-[0.18em] text-slate-400">
              <th className="px-5 py-4">Data</th>
              <th className="px-5 py-4">Descrição</th>
              <th className="px-5 py-4">Categoria</th>
              <th className="px-5 py-4">Tipo</th>
              <th className="px-5 py-4 text-right">Valor</th>
              {onDelete && <th className="px-5 py-4 text-right">Ações</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {transactions.map((t) => (
              <tr key={t.id} className="bg-white/3 transition hover:bg-white/[0.07]">
                <td className="whitespace-nowrap px-5 py-4 text-sm font-medium text-slate-300">
                  {t.date}
                </td>
                <td className="px-5 py-4 text-sm font-semibold text-white">{t.description}</td>
                <td className="px-5 py-4 text-sm text-slate-300">
                  <span className="rounded-full border border-white/10 bg-white/6 px-3 py-1">
                    {t.category ?? "Sem categoria"}
                  </span>
                </td>
                <td className="px-5 py-4 text-sm">
                  <span
                    className={
                      t.type === "receita"
                        ? "rounded-full bg-emerald-300/15 px-3 py-1 font-bold text-emerald-100"
                        : "rounded-full bg-rose-300/15 px-3 py-1 font-bold text-rose-100"
                    }
                  >
                    {t.type}
                  </span>
                </td>
                <td
                  className={
                    t.type === "receita"
                      ? "px-5 py-4 text-right text-sm font-black text-income"
                      : "px-5 py-4 text-right text-sm font-black text-expense"
                  }
                >
                  <Money value={t.amount} />
                </td>
                {onDelete && (
                  <td className="px-5 py-4 text-right">
                    <button
                      type="button"
                      onClick={() => onDelete(t)}
                      disabled={deletingId === t.id}
                      aria-label={`Excluir transação ${t.description}`}
                      className={`rounded-xl border border-rose-300/30 bg-rose-400/10 px-3 py-1.5 text-xs font-bold text-rose-100 transition hover:bg-rose-400/20 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`}
                    >
                      {deletingId === t.id ? "Excluindo..." : "Excluir"}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
