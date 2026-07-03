// Filtros de mês e categoria da tabela de transações (UI-DASH-02).
// `<input type="month">` já produz o formato "YYYY-MM" exigido pela API.
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
    <div className="flex gap-4">
      <div>
        <label htmlFor="filter-month" className="block text-sm">
          Mês
        </label>
        <input
          id="filter-month"
          type="month"
          value={month}
          onChange={(e) => onMonthChange(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="filter-category" className="block text-sm">
          Categoria
        </label>
        <select
          id="filter-category"
          value={category}
          onChange={(e) => onCategoryChange(e.target.value)}
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
