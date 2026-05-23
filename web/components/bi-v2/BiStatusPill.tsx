import type { ReactNode } from "react";
import { BI_STATUS_PILL_TONE, type BiStatusTone } from "./tokens";

export type BiStatusPillProps = {
  tone: BiStatusTone;
  label: ReactNode;
  ariaLabel?: string;
  size?: "sm" | "md";
};

const SIZE_CLASS = {
  sm: "rounded px-1.5 py-0.5 text-[10px]",
  md: "rounded px-2 py-0.5 text-xs",
} as const;

export function BiStatusPill({ tone, label, ariaLabel, size = "sm" }: BiStatusPillProps) {
  return (
    <span
      className={`${SIZE_CLASS[size]} font-medium ${BI_STATUS_PILL_TONE[tone]}`}
      aria-label={ariaLabel}
      role={ariaLabel ? "status" : undefined}
    >
      {label}
    </span>
  );
}
