"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { SidebarShell } from "@/components/sidebar/SidebarShell";
import { useAppShell } from "@/context/AppShellContext";
import { isAuthUnavailableError } from "@/lib/api-errors";
import {
  deleteSession,
  listSessionsPage,
  updateSessionTitle,
  type SessionPageCursor,
  type SessionSummary,
} from "@/lib/session-api";

export default function UtilitySidebar() {
  const { t } = useTranslation();
  const router = useRouter();
  const { activeSessionId, setActiveSessionId } = useAppShell();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingMoreSessions, setLoadingMoreSessions] = useState(false);
  const [historyUnavailable, setHistoryUnavailable] = useState(false);
  const [nextCursor, setNextCursor] = useState<SessionPageCursor | null>(null);
  const hasLoadedSessionsRef = useRef(false);

  const refreshSessions = useCallback(async () => {
    if (!hasLoadedSessionsRef.current) {
      setLoadingSessions(true);
    }
    try {
      const page = await listSessionsPage(50, 0, { force: true });
      setSessions(page.sessions);
      setNextCursor(page.next_cursor);
      setHistoryUnavailable(false);
      hasLoadedSessionsRef.current = true;
    } catch (error) {
      console.error("Failed to load sessions", error);
      setHistoryUnavailable(isAuthUnavailableError(error));
      setSessions([]);
      setNextCursor(null);
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  const loadMoreSessions = useCallback(async () => {
    if (!nextCursor || loadingMoreSessions) return;
    setLoadingMoreSessions(true);
    try {
      const page = await listSessionsPage(50, 0, {
        before_updated_at: nextCursor.before_updated_at,
        before_session_id: nextCursor.before_session_id,
      });
      setSessions((prev) => {
        const seen = new Set(prev.map((session) => session.session_id || session.id));
        return [...prev, ...page.sessions.filter((session) => !seen.has(session.session_id || session.id))];
      });
      setNextCursor(page.next_cursor);
    } catch (error) {
      console.error("Failed to load more sessions", error);
      setHistoryUnavailable(isAuthUnavailableError(error));
    } finally {
      setLoadingMoreSessions(false);
    }
  }, [loadingMoreSessions, nextCursor]);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  const handleNewChat = useCallback(() => {
    setActiveSessionId(null);
    router.push("/");
  }, [router, setActiveSessionId]);

  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      setActiveSessionId(sessionId);
      router.push(`/?session=${encodeURIComponent(sessionId)}`);
    },
    [router, setActiveSessionId],
  );

  const handleRenameSession = useCallback(async (sessionId: string, title: string) => {
    const updated = await updateSessionTitle(sessionId, title);
    setSessions((prev) =>
      prev.map((session) =>
        session.session_id === sessionId
          ? { ...session, title: updated.title, updated_at: updated.updated_at }
          : session,
      ),
    );
  }, []);

  const handleDeleteSession = useCallback(
    async (sessionId: string) => {
      if (!window.confirm(t("Delete this chat history?"))) return;
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((session) => session.session_id !== sessionId));
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
      }
    },
    [activeSessionId, setActiveSessionId],
  );

  return (
    <SidebarShell
      showSessions
      sessions={sessions}
      activeSessionId={activeSessionId}
      loadingSessions={loadingSessions}
      footerSlot={
        <div className="mt-2 space-y-2">
          {historyUnavailable ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2 text-[11px] leading-5 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-300">
              Web 端当前未接入登录态，历史会话不可用。
            </div>
          ) : null}
          {nextCursor ? (
            <button
              type="button"
              onClick={() => void loadMoreSessions()}
              disabled={loadingMoreSessions}
              className="w-full rounded-lg border border-[var(--border)]/70 bg-[var(--background)] px-3 py-2 text-[11px] font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)]/50 hover:text-[var(--foreground)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loadingMoreSessions ? "Loading more..." : "Load more sessions"}
            </button>
          ) : null}
        </div>
      }
      onNewChat={handleNewChat}
      onSelectSession={handleSelectSession}
      onRenameSession={handleRenameSession}
      onDeleteSession={handleDeleteSession}
    />
  );
}
