// Filtros de mês e categoria da tabela de transações (UI-DASH-02).
// `<input type="month">` já produz o formato "YYYY-MM" exigido pela API.
const FOCUS_RING =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#65f7b0]";

const FIELD_CLASS =
  "mt-1 rounded-2xl border border-white/10 bg-white/[0.08] px-3 py-2 text-sm font-medium text-white shadow-inner shadow-black/20 outline-none transition [color-scheme:dark] hover:border-white/20";

const CATEGORIES: { value: string; label: string }[] = [
  { value: "custos_fixos", label: "Custos Fixos" },
  { value: "conforto", label: "Conforto" },
  { value: "investimentos", label: "Investimentos" },
  { value: "conhecimento_metas", label: "Conhecimento e Metas" },
  { value: "prazeres", label: "Prazeres" },
];

interface TransactionFiltersProps {
  month: string;
  category: string;
  onMonthChange: (month: string) => void;
  onCategoryChange: (category: string) => void;
}

export default function TransactionFilters({
  month,
  category,
  onMonthChange,
  onCategoryChange,
}: TransactionFiltersProps) {
  return (
    <div className="flex flex-wrap gap-3">
      <div>
        <label
          htmlFor="filter-month"
          className="block text-xs font-semibold uppercase tracking-widest text-slate-400"
        >
          Mês
        </label>
        <input
          id="filter-month"
          type="month"
          value={month}
          onChange={(e) => onMonthChange(e.target.value)}
          className={`${FIELD_CLASS} ${FOCUS_RING}`}
        />
      </div>
      <div>
        <label
          htmlFor="filter-category"
          className="block text-xs font-semibold uppercase tracking-widest text-slate-400"
        >
          Categoria
        </label>
        <select
          id="filter-category"
          value={category}
          onChange={(e) => onCategoryChange(e.target.value)}
          className={`${FIELD_CLASS} min-w-52 ${FOCUS_RING}`}
        >
          <option value="">Todas</option>
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
