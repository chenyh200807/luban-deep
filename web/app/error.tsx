"use client";

import { useEffect } from "react";
import { useTranslation } from "react-i18next";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useTranslation();

  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--background)] px-6 py-12 text-[var(--foreground)]">
      <div className="w-full max-w-md rounded-3xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.08)]">
        <p className="text-sm font-medium text-[var(--muted-foreground)]">{t("Page load failed")}</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{t("Something went wrong")}</h1>
        <p className="mt-3 text-sm leading-6 text-[var(--muted-foreground)]">
          {t("This request did not complete successfully. Retry or refresh the page to continue.")}
        </p>
        <div className="mt-6 flex gap-3">
          <button
            type="button"
            onClick={reset}
            className="rounded-xl bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--primary-foreground)] transition-opacity hover:opacity-90"
          >
            {t("Retry")}
          </button>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-xl border border-[var(--border)] px-4 py-2 text-sm font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--muted)]"
          >
            {t("Refresh")}
          </button>
        </div>
      </div>
    </div>
  );
}
