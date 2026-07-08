// Filtros de mês, tipo e categoria da tabela de transações (UI-DASH-02).
// `<input type="month">` já produz o formato "YYYY-MM" exigido pela API.
const FOCUS_RING =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#65f7b0]";

const FIELD_CLASS =
  "mt-1 rounded-2xl border border-white/10 bg-white/[0.08] px-3 py-2 text-sm font-medium text-white shadow-inner shadow-black/20 outline-none transition [color-scheme:dark] hover:border-white/20";

const SELECT_CLASS =
  "mt-1 w-full min-w-44 appearance-none rounded-2xl border border-white/10 bg-slate-950/90 px-3 py-2 pr-10 text-sm font-medium text-white shadow-inner shadow-black/20 outline-none transition [color-scheme:dark] hover:border-white/20 cursor-pointer";

const OPTION_CLASS = "bg-slate-900 text-slate-100";

const CATEGORIES: { value: string; label: string }[] = [
  { value: "custos_fixos", label: "Custos Fixos" },
  { value: "conforto", label: "Conforto" },
  { value: "investimentos", label: "Investimentos" },
  { value: "conhecimento_metas", label: "Conhecimento e Metas" },
  { value: "prazeres", label: "Prazeres" },
];

const TYPES: { value: string; label: string }[] = [
  { value: "receita", label: "Receita" },
  { value: "despesa", label: "Despesa" },
];

function FilterSelect({
  id,
  label,
  value,
  onChange,
  options,
  allLabel,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  allLabel: string;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="block text-xs font-semibold uppercase tracking-widest text-slate-400"
      >
        {label}
      </label>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`${SELECT_CLASS} ${FOCUS_RING}`}
        >
          <option value="" className={OPTION_CLASS}>
            {allLabel}
          </option>
          {options.map((option) => (
            <option key={option.value} value={option.value} className={OPTION_CLASS}>
              {option.label}
            </option>
          ))}
        </select>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-slate-400"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
            <path
              fillRule="evenodd"
              d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.25a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.08z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      </div>
    </div>
  );
}

interface TransactionFiltersProps {
  month: string;
  category: string;
  type: string;
  onMonthChange: (month: string) => void;
  onCategoryChange: (category: string) => void;
  onTypeChange: (type: string) => void;
}

export default function TransactionFilters({
  month,
  category,
  type,
  onMonthChange,
  onCategoryChange,
  onTypeChange,
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
      <FilterSelect
        id="filter-type"
        label="Tipo"
        value={type}
        onChange={onTypeChange}
        options={TYPES}
        allLabel="Todos"
      />
      <FilterSelect
        id="filter-category"
        label="Categoria"
        value={category}
        onChange={onCategoryChange}
        options={CATEGORIES}
        allLabel="Todas"
      />
    </div>
  );
}
