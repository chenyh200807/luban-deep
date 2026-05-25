export const BI_DENSITY = {
  rowSm: "px-2 py-1 text-xs",
  rowMd: "px-3 py-2 text-xs",
  cellLabel: "text-[11px] uppercase tracking-wide text-slate-500",
} as const;

export const BI_STATUS_PILL_TONE = {
  emerald: "bg-emerald-300/10 text-emerald-100 ring-1 ring-emerald-300/25",
  sky: "bg-cyan-300/10 text-cyan-100 ring-1 ring-cyan-300/25",
  amber: "bg-amber-300/10 text-amber-100 ring-1 ring-amber-300/25",
  rose: "bg-rose-300/10 text-rose-100 ring-1 ring-rose-300/25",
  red: "bg-red-300/10 text-red-100 ring-1 ring-red-300/25",
  orange: "bg-orange-300/10 text-orange-100 ring-1 ring-orange-300/25",
  slate: "bg-white/10 text-slate-200 ring-1 ring-white/15",
} as const;

export type BiStatusTone = keyof typeof BI_STATUS_PILL_TONE;

export const BI_SEVERITY_TONE: Record<"critical" | "high" | "medium" | "low", BiStatusTone> = {
  critical: "red",
  high: "orange",
  medium: "amber",
  low: "slate",
};

export const BI_TRUST_TONE: Record<"A" | "B" | "C" | "D", BiStatusTone> = {
  A: "emerald",
  B: "sky",
  C: "amber",
  D: "rose",
};

export const BI_CONTAINER = {
  page: "min-h-screen bg-[#101622] text-slate-100",
  panel: "rounded-2xl border border-white/10 bg-white/[0.04]",
  panelPad: "rounded-2xl border border-white/10 bg-white/[0.04] p-4",
  section: "space-y-4",
} as const;
