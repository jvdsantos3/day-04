import type { Transaction } from "@/types/api";
import Money from "@/components/Money";

// Tabela de transações filtradas (UI-DASH-03). Lista vazia -> estado vazio
// com mensagem clara em vez de uma tabela sem linhas (AC5).
export default function TransactionTable({
  transactions,
}: {
  transactions: Transaction[];
}) {
  if (transactions.length === 0) {
    return <p>Nenhuma transação encontrada para este filtro.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Data</th>
          <th>Descrição</th>
          <th>Categoria</th>
          <th>Tipo</th>
          <th>Valor</th>
        </tr>
      </thead>
      <tbody>
        {transactions.map((t) => (
          <tr key={t.id}>
            <td>{t.date}</td>
            <td>{t.description}</td>
            <td>{t.category ?? "-"}</td>
            <td>{t.type}</td>
            <td className={t.type === "receita" ? "text-income" : "text-expense"}>
              <Money value={t.amount} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
