import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import TransactionTable from "./TransactionTable";
import type { Transaction } from "@/types/api";

const sample: Transaction = {
  id: "1",
  date: "2026-07-01",
  description: "Mercado",
  amount: "150.00",
  type: "despesa",
  category: "custos_fixos",
};

describe("TransactionTable", () => {
  it("renderiza uma linha por transação com descrição e valor formatado", () => {
    render(<TransactionTable transactions={[sample]} />);

    expect(screen.getByText("Mercado")).toBeInTheDocument();
    expect(screen.getByText(/R\$\s*150,00/)).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(2); // header + 1 linha de dados
  });

  it("lista vazia exibe estado vazio sem linhas de dados (AC5)", () => {
    render(<TransactionTable transactions={[]} />);

    expect(
      screen.getByText("Nenhuma transação encontrada para este filtro."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByRole("row")).not.toBeInTheDocument();
  });
});
