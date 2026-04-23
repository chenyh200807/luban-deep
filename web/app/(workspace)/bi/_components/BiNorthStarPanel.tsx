/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiNorthStarPayload } from "@/lib/bi-api";
import { Target } from "lucide-react";
import { formatNumber, SectionHeader } from "./BiShared";

type BiNorthStarPanelProps = {
  payload?: BiNorthStarPayload;
};

export function BiNorthStarPanel({ payload }: BiNorthStarPanelProps) {
  if (!payload) {
    return null;
  }

  return (
    <section className="surface-card overflow-hidden p-6">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <SectionHeader title="北极星" extra={`可信等级 ${payload.trustLevel || "--"}`} />
          <h3 className="mt-4 text-3xl font-semibold tracking-tight text-[var(--foreground)]">{payload.label}</h3>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-[var(--muted-foreground)]">{payload.calculation || payload.definition}</p>
        </div>
        <div className="rounded-[2rem] bg-[var(--foreground)] px-7 py-6 text-white shadow-[0_20px_55px_rgba(45,33,25,0.22)]">
          <div className="flex items-center gap-2 text-sm text-white/70">
            <Target size={16} />
            <span>{payload.windowDays} 天窗口</span>
          </div>
          <p className="mt-3 text-5xl font-semibold tracking-tight">{formatNumber(payload.value)}</p>
          <p className="mt-2 text-sm text-white/70">只统计真实手机号会员</p>
        </div>
      </div>

      {payload.inputs.length ? (
        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {payload.inputs.slice(0, 3).map((input) => (
            <div key={input.metric_id} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
              <p className="text-xs text-[var(--muted-foreground)]">{input.label}</p>
              <p className="mt-1 text-xl font-semibold text-[var(--foreground)]">
                {input.value === null || input.value === undefined ? "待接入" : formatNumber(input.value)}
              </p>
              <p className="mt-1 text-xs text-[var(--muted-foreground)]">{input.authority}</p>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
