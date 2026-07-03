import type { CategoryBudget } from "@/types/api";
import Money from "@/components/Money";

// Card de uma categoria de orçamento (UI-DASH-01). Destaque visual quando
// status === "alerta" (AC2), distinto de status === "ok".
export default function CategoryCard({ category }: { category: CategoryBudget }) {
  const isAlerta = category.status === "alerta";
  const barWidth = Math.min(category.pct, 100);

  return (
    <div
      className={
        isAlerta
          ? "rounded border border-expense bg-red-50 p-4"
          : "rounded border border-neutral-border p-4"
      }
    >
      <div className="flex items-center justify-between">
        <span className="font-medium">{category.label}</span>
        {isAlerta && <span className="text-expense text-sm font-semibold">Alerta</span>}
      </div>
      <div className="mt-2">
        <Money value={category.spent} />
      </div>
      <div className="mt-2 h-2 w-full rounded bg-neutral-border">
        <div
          className={isAlerta ? "h-2 rounded bg-expense" : "h-2 rounded bg-income"}
          style={{ width: `${barWidth}%` }}
        />
      </div>
      <div className="mt-1 text-sm">{category.pct.toFixed(0)}%</div>
    </div>
  );
}
