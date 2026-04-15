"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { SidebarShell } from "@/components/sidebar/SidebarShell";
import { useUnifiedChat } from "@/context/UnifiedChatContext";
import { isAuthUnavailableError } from "@/lib/api-errors";
import {
  deleteSession,
  listSessions,
  updateSessionTitle,
  type SessionSummary,
} from "@/lib/session-api";

export default function WorkspaceSidebar() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();
  const { newSession, loadSession, selectedSessionId, sessionStatuses, sidebarRefreshToken } =
    useUnifiedChat();
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
  }, [refreshSessions, sidebarRefreshToken]);

  const orderedSessions = sessions
    .map((session, index) => {
      const runtime = sessionStatuses[session.session_id];
      return {
        index,
        session: runtime
          ? {
              ...session,
              status: runtime.status,
              active_turn_id: runtime.activeTurnId || session.active_turn_id,
            }
          : session,
      };
    })
    .sort((a, b) => {
      const aPriority = a.session.status === "running" ? 0 : 1;
      const bPriority = b.session.status === "running" ? 0 : 1;
      if (aPriority !== bPriority) return aPriority - bPriority;
      return a.index - b.index;
    })
    .map(({ session }) => session);

  const handleNewChat = () => {
    newSession();
    if (pathname !== "/") router.push("/");
  };

  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      await loadSession(sessionId);
      if (pathname !== "/") router.push("/");
    },
    [loadSession, pathname, router],
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
      if (selectedSessionId === sessionId) {
        newSession();
        if (pathname !== "/") router.push("/");
      }
    },
    [newSession, pathname, router, selectedSessionId],
  );

  return (
    <SidebarShell
      showSessions
      sessions={orderedSessions}
      activeSessionId={selectedSessionId}
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
