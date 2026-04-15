"use client";

import { ShieldAlert } from "lucide-react";

interface RestrictedSurfaceProps {
  title: string;
  message: string;
}

export default function RestrictedSurface({ title, message }: RestrictedSurfaceProps) {
  return (
    <div className="flex h-full min-h-[320px] items-center justify-center px-6 py-10">
      <div className="w-full max-w-xl rounded-2xl border border-amber-200 bg-amber-50/80 p-6 text-center shadow-sm dark:border-amber-900/60 dark:bg-amber-950/20">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
          <ShieldAlert className="h-6 w-6" />
        </div>
        <h1 className="text-lg font-semibold text-[var(--foreground)]">{title}</h1>
        <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">{message}</p>
      </div>
    </div>
  );
}
