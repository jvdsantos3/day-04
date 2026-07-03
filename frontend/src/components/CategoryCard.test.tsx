import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import CategoryCard from "./CategoryCard";
import type { CategoryBudget } from "@/types/api";

function makeCategory(overrides: Partial<CategoryBudget> = {}): CategoryBudget {
  return {
    category: "custos_fixos",
    label: "Custos Fixos",
    spent: "2000.00",
    pct: 50,
    min_pct: 0,
    max_pct: 100,
    status: "ok",
    ...overrides,
  };
}

describe("CategoryCard", () => {
  it("renderiza label e valor formatado em BRL (UI-FMT-01)", () => {
    render(<CategoryCard category={makeCategory()} />);

    expect(screen.getByText("Custos Fixos")).toBeInTheDocument();
    // Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'}) usa
    // NBSP entre "R$" e o valor — regex tolera espaço normal ou NBSP.
    expect(screen.getByText(/R\$\s*2\.000,00/)).toBeInTheDocument();
  });

  it("status alerta exibe destaque visual ausente quando status ok (AC2)", () => {
    const { rerender } = render(
      <CategoryCard category={makeCategory({ status: "ok" })} />,
    );
    expect(screen.queryByText(/alerta/i)).not.toBeInTheDocument();

    rerender(<CategoryCard category={makeCategory({ status: "alerta" })} />);
    expect(screen.getByText(/alerta/i)).toBeInTheDocument();
  });
});
