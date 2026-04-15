"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { SidebarShell } from "@/components/sidebar/SidebarShell";
import { useAppShell } from "@/context/AppShellContext";
import { isAuthUnavailableError } from "@/lib/api-errors";
import {
  deleteSession,
  listSessions,
  updateSessionTitle,
  type SessionSummary,
} from "@/lib/session-api";

export default function UtilitySidebar() {
  const { t } = useTranslation();
  const router = useRouter();
  const { activeSessionId, setActiveSessionId } = useAppShell();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [historyUnavailable, setHistoryUnavailable] = useState(false);
  const hasLoadedSessionsRef = useRef(false);

  const refreshSessions = useCallback(async () => {
    if (!hasLoadedSessionsRef.current) {
      setLoadingSessions(true);
    }
    try {
      setSessions(await listSessions(50, 0, { force: true }));
      setHistoryUnavailable(false);
      hasLoadedSessionsRef.current = true;
    } catch (error) {
      console.error("Failed to load sessions", error);
      setHistoryUnavailable(isAuthUnavailableError(error));
      setSessions([]);
    } finally {
      setLoadingSessions(false);
    }
  }, []);

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
        historyUnavailable ? (
          <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2 text-[11px] leading-5 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-300">
            Web 端当前未接入登录态，历史会话不可用。
          </div>
        ) : undefined
      }
      onNewChat={handleNewChat}
      onSelectSession={handleSelectSession}
      onRenameSession={handleRenameSession}
      onDeleteSession={handleDeleteSession}
    />
  );
}
