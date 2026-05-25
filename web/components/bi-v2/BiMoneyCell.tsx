export type BiMoneyCellProps = {
  amount: number;
  currency?: "CNY" | "POINT";
  trust?: "A" | "B" | "C" | "D";
  ariaLabel?: string;
  align?: "left" | "right";
};

const CURRENCY_PREFIX: Record<NonNullable<BiMoneyCellProps["currency"]>, string> = {
  CNY: "¥",
  POINT: "",
};

const CURRENCY_SUFFIX: Record<NonNullable<BiMoneyCellProps["currency"]>, string> = {
  CNY: "",
  POINT: " 点",
};

function formatAmount(amount: number, currency: NonNullable<BiMoneyCellProps["currency"]>) {
  if (currency === "POINT") return Math.round(amount).toLocaleString("zh-CN");
  return amount.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function BiMoneyCell({
  amount,
  currency = "CNY",
  trust,
  ariaLabel,
  align = "right",
}: BiMoneyCellProps) {
  const value = formatAmount(amount, currency);
  return (
    <span
      className={`inline-flex items-baseline gap-1 tabular-nums ${
        align === "right" ? "justify-end" : "justify-start"
      }`}
      aria-label={ariaLabel ?? `${CURRENCY_PREFIX[currency]}${value}${CURRENCY_SUFFIX[currency]}`}
    >
      <span className="text-slate-100">
        {CURRENCY_PREFIX[currency]}
        {value}
        {CURRENCY_SUFFIX[currency]}
      </span>
      {trust && trust !== "A" ? (
        <span
          className="rounded bg-white/10 px-1 text-[10px] font-medium text-slate-300"
          aria-label={`数据可信等级 ${trust}`}
          title={`数据可信等级 ${trust}`}
        >
          {trust}
        </span>
      ) : null}
    </span>
  );
}
