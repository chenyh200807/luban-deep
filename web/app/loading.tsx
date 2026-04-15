"use client";

import { useTranslation } from "react-i18next";

export default function RootLoading() {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--background)] px-6 py-12 text-[var(--foreground)]">
      <div className="flex flex-col items-center gap-3 rounded-3xl border border-[var(--border)] bg-[var(--card)] px-6 py-8 shadow-[0_20px_60px_rgba(0,0,0,0.06)]">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--muted)] border-t-[var(--primary)]" />
        <div className="space-y-1 text-center">
          <p className="text-sm font-medium">{t("Loading app")}</p>
          <p className="text-xs text-[var(--muted-foreground)]">{t("Please wait while the page is being prepared.")}</p>
        </div>
      </div>
    </div>
  );
}
