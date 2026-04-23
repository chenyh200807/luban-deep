/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiAiQualityPayload, BiTeachingEffectPayload, BiUnitEconomicsPayload } from "@/lib/bi-api";
import { BookOpenCheck, Bot, Wallet } from "lucide-react";
import { formatNumber, SectionHeader } from "./BiShared";

type BiAiQualityPanelProps = {
  aiQuality?: BiAiQualityPayload;
  teachingEffect?: BiTeachingEffectPayload;
  unitEconomics?: BiUnitEconomicsPayload;
};

function formatUsd(value: number) {
  return `$${formatNumber(Math.round(value * 10000) / 10000)}`;
}

export function BiAiQualityPanel({ aiQuality, teachingEffect, unitEconomics }: BiAiQualityPanelProps) {
  if (!aiQuality && !teachingEffect && !unitEconomics) {
    return null;
  }

  return (
    <section className="grid gap-5 lg:grid-cols-2">
      {aiQuality ? (
        <div className="surface-card p-5">
          <div className="flex items-start justify-between gap-3">
            <SectionHeader title="AI 质量" extra={`可信 ${aiQuality.trustLevel || "--"}`} />
            <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">
              <Bot size={16} />
            </div>
          </div>
          <p className="mt-4 text-3xl font-semibold text-[var(--foreground)]">
            {formatNumber(aiQuality.engineeringSuccessRate)}%
          </p>
          <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">{aiQuality.note}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
              <p className="text-xs text-[var(--muted-foreground)]">失败回合</p>
              <p className="mt-1 text-lg font-semibold">{formatNumber(aiQuality.failedTurns)}</p>
            </div>
            <div className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
              <p className="text-xs text-[var(--muted-foreground)]">教学质量</p>
              <p className="mt-1 text-lg font-semibold">{aiQuality.teachingSuccessStatus || "待抽检"}</p>
            </div>
          </div>
          {aiQuality.samples.length ? (
            <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--secondary)]/60 p-4">
              <p className="text-sm font-semibold text-[var(--foreground)]">质量样本</p>
              <div className="mt-3 grid gap-2">
                {aiQuality.samples.slice(0, 4).map((sample, index) => (
                  <div
                    key={sample.turn_id || `${sample.session_id}-${index}`}
                    className="rounded-xl bg-[var(--background)] px-3 py-2 text-sm"
                  >
                    <p className="font-medium text-[var(--foreground)]">
                      {sample.status || "quality_sample"} · {sample.session_id || "--"}
                    </p>
                    <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                      turn {sample.turn_id || "--"}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="surface-card p-5">
        <div className="flex items-start justify-between gap-3">
          <SectionHeader title="教学与单位经济" extra={unitEconomics?.revenueStatus === "pending" ? "收入待接入" : ""} />
          <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">
            <Wallet size={16} />
          </div>
        </div>
        <p className="mt-4 text-sm leading-6 text-[var(--muted-foreground)]">
          {teachingEffect?.summary || unitEconomics?.summary || "等待教学效果和单位经济数据。"}
        </p>
        {teachingEffect?.chapterProgress.length ? (
          <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--secondary)]/60 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-[var(--foreground)]">
              <BookOpenCheck size={15} />
              章节进展
            </div>
            <div className="mt-3 grid gap-2">
              {teachingEffect.chapterProgress.slice(0, 4).map((chapter) => (
                <div key={chapter.chapterId || chapter.name} className="rounded-xl bg-[var(--background)] px-3 py-2">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="font-medium text-[var(--foreground)]">{chapter.name}</span>
                    <span className="text-[var(--muted-foreground)]">{formatNumber(chapter.mastery)}%</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--border)]">
                    <div
                      className="h-full rounded-full bg-[var(--primary)]"
                      style={{ width: `${Math.max(0, Math.min(100, chapter.mastery))}%` }}
                    />
                  </div>
                  <p className="mt-2 text-xs text-[var(--muted-foreground)]">
                    {chapter.evidence || `${formatNumber(chapter.memberCount)} 名真实会员样本`}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ) : null}
        {unitEconomics ? (
          <div className="mt-4 rounded-2xl bg-[var(--secondary)] px-4 py-3">
            <p className="text-xs text-[var(--muted-foreground)]">单有效学习成本</p>
            <p className="mt-1 text-2xl font-semibold text-[var(--foreground)]">
              {formatUsd(unitEconomics.costPerEffectiveLearningUsd)}
            </p>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">窗口成本 {formatUsd(unitEconomics.windowTotalCostUsd)}</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
