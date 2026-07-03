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
          ? "group relative overflow-hidden rounded-3xl border border-rose-300/30 bg-rose-400/10 p-4 shadow-lg shadow-rose-950/20"
          : "group relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.07] p-4 shadow-lg shadow-black/10"
      }
    >
      <div className="absolute -right-8 -top-8 h-24 w-24 rounded-full bg-white/5 blur-2xl transition group-hover:bg-emerald-300/10" />
      <div className="relative flex items-start justify-between gap-3">
        <span className="text-sm font-bold leading-tight text-white">{category.label}</span>
        <span
          className={
            isAlerta
              ? "rounded-full bg-rose-300/15 px-2 py-1 text-[0.65rem] font-black uppercase tracking-widest text-rose-100"
              : "rounded-full bg-emerald-300/15 px-2 py-1 text-[0.65rem] font-black uppercase tracking-widest text-emerald-100"
          }
        >
          {isAlerta ? "Alerta" : "Ok"}
        </span>
      </div>
      <div className="relative mt-5 text-2xl font-black tracking-tight text-white">
        <Money value={category.spent} />
      </div>
      <div className="relative mt-4 h-2.5 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className={
            isAlerta
              ? "h-full rounded-full bg-linear-to-r from-rose-300 to-orange-300"
              : "h-full rounded-full bg-linear-to-r from-emerald-300 to-cyan-300"
          }
          style={{ width: `${barWidth}%` }}
        />
      </div>
      <div className="relative mt-3 flex items-center justify-between text-xs font-medium text-slate-400">
        <span>{category.pct.toFixed(0)}% usado</span>
        <span>
          meta {category.min_pct.toFixed(0)}-{category.max_pct.toFixed(0)}%
        </span>
      </div>
    </div>
  );
}
