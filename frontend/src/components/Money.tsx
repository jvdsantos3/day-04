// Formata valores monetários vindos da API (string) em BRL (UI-FMT-01).
// A API serializa Decimal como string (ex. "2000.00") para evitar erros de
// arredondamento float — a conversão para number acontece só aqui, na borda
// de apresentação.

const formatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

export default function Money({ value }: { value: string }) {
  return <>{formatter.format(Number(value))}</>;
}
