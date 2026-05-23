export const BI_DENSITY = {
  rowSm: "px-2 py-1 text-xs",
  rowMd: "px-3 py-2 text-xs",
  cellLabel: "text-[11px] uppercase tracking-wide text-slate-500",
} as const;

export const BI_STATUS_PILL_TONE = {
  emerald: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  sky: "bg-sky-50 text-sky-700 ring-1 ring-sky-200",
  amber: "bg-amber-50 text-amber-800 ring-1 ring-amber-200",
  rose: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
  red: "bg-red-50 text-red-700 ring-1 ring-red-200",
  orange: "bg-orange-50 text-orange-700 ring-1 ring-orange-200",
  slate: "bg-slate-100 text-slate-700 ring-1 ring-slate-200",
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
  page: "min-h-screen bg-slate-50 text-slate-900",
  panel: "rounded-md border border-slate-200 bg-white",
  panelPad: "rounded-md border border-slate-200 bg-white p-4",
  section: "space-y-4",
} as const;
