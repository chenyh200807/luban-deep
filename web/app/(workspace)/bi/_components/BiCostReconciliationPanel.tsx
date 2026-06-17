/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiCostReconciliationProvider } from "@/lib/bi-cost-reconciliation";
import { InfoLine, SectionHeader, formatNumber, toneClasses } from "./BiShared";

type BiCostReconciliationPanelProps = {
  providers: BiCostReconciliationProvider[];
};

export function BiCostReconciliationPanel({ providers }: BiCostReconciliationPanelProps) {
  return (
    <section className="surface-card p-5">
      <SectionHeader
        title="官方账单对账"
        extra={providers.length ? `${providers.length} 个 provider` : "等待官方对账"}
      />
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        {providers.length ? (
          providers.map((provider) => (
            <ProviderCostReconciliationCard key={provider.providerName} provider={provider} />
          ))
        ) : (
          <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)] xl:col-span-3">
            当前没有官方账单对账数据。这里需要后端返回 provider=all 的 reconciliation.providers，空态不代表成本已经对齐。
          </p>
        )}
      </div>
    </section>
  );
}

function ProviderCostReconciliationCard({ provider }: { provider: BiCostReconciliationProvider }) {
  const officialTone = getCostStatusTone(provider.officialStatus, provider.reconciliationStatus);
  const warningText = provider.warnings.length ? provider.warnings.join(" / ") : "暂无对账告警";

  return (
    <article className="rounded-2xl border border-[var(--border)]/70 bg-white/88 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-[var(--foreground)]">{provider.label}</p>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">{provider.providerName}</p>
        </div>
        <span className={`muted-chip ${toneClasses(officialTone)}`}>{provider.officialStatus}</span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <InfoLine label="内账金额" value={formatProviderAmount(provider.internalAmount, provider.currency)} />
        <InfoLine label="官方金额" value={formatProviderAmount(provider.officialAmount, provider.currency)} />
        <InfoLine label="官方净额" value={formatProviderAmount(provider.netOfficialAmount, provider.currency)} />
        <InfoLine label="金额差异" value={formatProviderAmount(provider.amountDelta, provider.currency)} />
        <InfoLine label="Token 差异" value={provider.tokenDelta === null ? "暂无" : formatNumber(provider.tokenDelta)} />
        <InfoLine label="对账状态" value={provider.reconciliationStatus || "unknown"} />
      </div>

      <div className="mt-4 rounded-2xl bg-[var(--secondary)] px-3 py-3">
        <p className="text-xs text-[var(--muted-foreground)]">连接器状态</p>
        <p className="mt-1 text-sm leading-6 text-[var(--secondary-foreground)]">
          内账 {provider.internalStatus || "unknown"} · 官方 {provider.officialStatus || "unknown"}
        </p>
        <p className="mt-2 text-xs leading-5 text-[var(--muted-foreground)]">{warningText}</p>
      </div>
    </article>
  );
}

function formatProviderAmount(value: number | null, currency: string) {
  if (value === null || Number.isNaN(value)) return "暂无";
  const normalizedCurrency = currency || "CNY";
  const maximumFractionDigits = Math.abs(value) >= 1 ? 2 : 6;
  return `${normalizedCurrency} ${new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits,
  }).format(value)}`;
}

function getCostStatusTone(officialStatus: string, reconciliationStatus: string) {
  const joined = `${officialStatus} ${reconciliationStatus}`.toLowerCase();
  if (joined.includes("error") || joined.includes("untrusted")) return "critical";
  if (
    joined.includes("unconfigured") ||
    joined.includes("warning") ||
    joined.includes("waiting") ||
    joined.includes("mismatch")
  ) {
    return "warning";
  }
  return "info";
}
