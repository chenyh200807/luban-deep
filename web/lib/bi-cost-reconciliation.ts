export interface BiCostReconciliationProvider {
  providerName: string
  label: string
  internalStatus: string
  officialStatus: string
  reconciliationStatus: string
  currency: string
  internalAmount: number | null
  officialAmount: number | null
  netOfficialAmount: number | null
  amountDelta: number | null
  tokenDelta: number | null
  totalTokens: number | null
  officialTokens: number | null
  warnings: string[]
}

const PROVIDER_LABELS: Record<string, string> = {
  deepseek: 'DeepSeek 官方',
  dashscope: '阿里云 DashScope/Bailian',
  unknown: 'Unknown/other provider',
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

function toString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return fallback
}

function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

function nullableNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null
  const parsed = toNumber(value, Number.NaN)
  return Number.isFinite(parsed) ? parsed : null
}

function toArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function normalizeCurrencyAmounts(value: unknown): Record<string, number> {
  const record = asRecord(value)
  return Object.fromEntries(
    Object.entries(record)
      .map(([currency, amount]) => [currency.trim().toUpperCase(), toNumber(amount, Number.NaN)] as const)
      .filter(([currency, amount]) => Boolean(currency) && Number.isFinite(amount))
  )
}

function pickCurrency(...amounts: Array<Record<string, number>>): string {
  for (const preferred of ['CNY', 'USD']) {
    if (amounts.some(item => Object.prototype.hasOwnProperty.call(item, preferred))) return preferred
  }
  for (const item of amounts) {
    const first = Object.keys(item)[0]
    if (first) return first
  }
  return 'CNY'
}

function amountForCurrency(amounts: Record<string, number>, currency: string): number | null {
  return Object.prototype.hasOwnProperty.call(amounts, currency) ? amounts[currency] : null
}

function collectWarnings(...values: unknown[]): string[] {
  return Array.from(
    new Set(
      values
        .flatMap(value => toArray(value))
        .map(value => toString(value))
        .filter(Boolean)
    )
  )
}

function normalizeCostReconciliationProvider(
  providerName: string,
  rawProvider: unknown
): BiCostReconciliationProvider {
  const provider = asRecord(rawProvider)
  const internal = asRecord(provider.internal)
  const officialUsage = asRecord(provider.official_usage ?? provider.officialUsage)
  const reconciliation = asRecord(provider.reconciliation)
  const internalAmounts = normalizeCurrencyAmounts(internal.currency_amounts ?? internal.currencyAmounts)
  const officialAmounts = normalizeCurrencyAmounts(
    officialUsage.currency_amounts ?? officialUsage.currencyAmounts ?? officialUsage.list_price_cost
  )
  const netOfficialAmounts = normalizeCurrencyAmounts(
    officialUsage.net_charge_cost ?? officialUsage.netChargeCost
  )
  const amountDeltas = normalizeCurrencyAmounts(
    reconciliation.amount_delta_by_currency ?? reconciliation.amountDeltaByCurrency
  )
  const currency = pickCurrency(internalAmounts, officialAmounts, netOfficialAmounts, amountDeltas)
  return {
    providerName,
    label: PROVIDER_LABELS[providerName] ?? providerName,
    internalStatus: toString(internal.status, 'unknown'),
    officialStatus: toString(officialUsage.status, 'unconfigured'),
    reconciliationStatus: toString(reconciliation.status, 'unknown'),
    currency,
    internalAmount: amountForCurrency(internalAmounts, currency),
    officialAmount: amountForCurrency(officialAmounts, currency),
    netOfficialAmount: amountForCurrency(netOfficialAmounts, currency),
    amountDelta: amountForCurrency(amountDeltas, currency),
    tokenDelta: nullableNumber(reconciliation.token_delta ?? reconciliation.tokenDelta),
    totalTokens: nullableNumber(internal.total_tokens ?? internal.totalTokens),
    officialTokens: nullableNumber(officialUsage.total_tokens ?? officialUsage.totalTokens),
    warnings: collectWarnings(reconciliation.warnings, provider.warnings),
  }
}

export function normalizeBiCostReconciliation(raw: unknown): BiCostReconciliationProvider[] {
  const record = asRecord(raw)
  const providers = asRecord(record.providers)
  return Object.entries(providers)
    .map(([providerName, providerPayload]) =>
      normalizeCostReconciliationProvider(providerName, providerPayload)
    )
    .sort((left, right) => left.providerName.localeCompare(right.providerName))
}
