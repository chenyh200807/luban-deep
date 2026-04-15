"use client";

import { useTranslation } from "react-i18next";

export default function WorkspaceLoading() {
  const { t } = useTranslation();

  return (
    <div className="flex h-full items-center justify-center bg-[var(--background)] px-6 text-[var(--foreground)]">
      <div className="flex flex-col items-center gap-3 rounded-3xl border border-[var(--border)] bg-[var(--card)] px-6 py-8 shadow-[0_16px_48px_rgba(0,0,0,0.06)]">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-[var(--muted)] border-t-[var(--primary)]" />
        <div className="text-center">
          <p className="text-sm font-medium">{t("Loading workspace")}</p>
          <p className="text-xs text-[var(--muted-foreground)]">{t("Chat and sidebar content will be ready shortly.")}</p>
        </div>
      </div>
    </div>
  );
}
