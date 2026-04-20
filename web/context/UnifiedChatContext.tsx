"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";
import {
  readStoredActiveSessionId,
  readStoredLanguage,
  writeStoredActiveSessionId,
} from "@/context/AppShellContext";
import { trackWebSurfaceEvent, trackWebSurfaceEventOnce } from "@/lib/surface-telemetry";
import type { StreamEvent, ChatMessage } from "@/lib/unified-ws";
import { primeUnifiedTurnContractCheck, UnifiedWSClient } from "@/lib/unified-ws";
import { getSession, type SessionMessage } from "@/lib/session-api";
import { normalizeMarkdownForDisplay } from "@/lib/markdown-display";
import { shouldAppendEventContent } from "@/lib/stream";

type SessionRuntimeStatus =
  | "idle"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "rejected";

export type ChatMode = "fast" | "deep";

interface OutgoingAttachment {
  type: string;
  url?: string;
  base64?: string;
  filename?: string;
  mime_type?: string;
}

interface NotebookReferencePayload {
  notebook_id: string;
  record_ids: string[];
}

type HistoryReferencePayload = string[];

export interface SendMessageOptions {
  displayUserMessage?: boolean;
  persistUserMessage?: boolean;
  requestSnapshotOverride?: MessageRequestSnapshot;
}

export interface ChatState {
  sessionId: string | null;
  enabledTools: string[];
  activeCapability: string | null;
  chatMode: ChatMode;
  knowledgeBases: string[];
  messages: MessageItem[];
  isStreaming: boolean;
  currentStage: string;
  language: string;
}

interface SessionStatusSnapshot {
  sessionId: string;
  status: SessionRuntimeStatus;
  activeTurnId: string | null;
  updatedAt: number;
}

export interface MessageAttachment {
  type: string;
  filename?: string;
  base64?: string;
  url?: string;
  mime_type?: string;
}

export interface MessageRequestSnapshot {
  content: string;
  capability?: string | null;
  enabledTools: string[];
  knowledgeBases: string[];
  language: string;
  attachments?: MessageAttachment[];
  config?: Record<string, unknown>;
  notebookReferences?: NotebookReferencePayload[];
  historyReferences?: HistoryReferencePayload;
}

export interface MessageItem {
  role: "user" | "assistant" | "system";
  content: string;
  capability?: string;
  events?: StreamEvent[];
  attachments?: MessageAttachment[];
  requestSnapshot?: MessageRequestSnapshot;
}

interface SessionEntry extends ChatState {
  key: string;
  status: SessionRuntimeStatus;
  activeTurnId: string | null;
  lastSeq: number;
  updatedAt: number;
}

interface ProviderState {
  selectedKey: string | null;
  sessions: Record<string, SessionEntry>;
  sidebarRefreshToken: number;
}

function getDefaultChatMode(): ChatMode {
  return process.env.NEXT_PUBLIC_CHAT_DEFAULT_MODE === "deep" ? "deep" : "fast";
}

type Action =
  | { type: "SET_TOOLS"; tools: string[] }
  | { type: "SET_CAPABILITY"; cap: string | null }
  | { type: "SET_CHAT_MODE"; mode: ChatMode }
  | { type: "SET_KB"; kbs: string[] }
  | { type: "SET_LANGUAGE"; lang: string }
  | {
      type: "ADD_USER_MSG";
      key: string;
      content: string;
      capability?: string | null;
      attachments?: MessageAttachment[];
      requestSnapshot?: MessageRequestSnapshot;
    }
  | { type: "STREAM_START"; key: string }
  | { type: "STREAM_EVENT"; key: string; event: StreamEvent }
  | { type: "STREAM_END"; key: string; status?: SessionRuntimeStatus; turnId?: string | null }
  | { type: "BIND_SERVER_SESSION"; key: string; sessionId: string; turnId?: string | null }
  | {
      type: "LOAD_SESSION";
      key: string;
      sessionId: string;
      messages: MessageItem[];
      activeTurnId?: string | null;
      lastSeq?: number;
      status?: SessionRuntimeStatus;
      tools?: string[];
      capability?: string | null;
      chatMode?: ChatMode;
      knowledgeBases?: string[];
      language?: string;
    }
  | { type: "NEW_SESSION"; key: string };

function createSessionEntry(
  key: string,
  sessionId: string | null = null,
  chatMode: ChatMode = getDefaultChatMode(),
): SessionEntry {
  return {
    key,
    sessionId,
    enabledTools: [],
    activeCapability: null,
    chatMode,
    knowledgeBases: [],
    messages: [],
    isStreaming: false,
    currentStage: "",
    language: typeof window === "undefined" ? "en" : readStoredLanguage(),
    status: "idle",
    activeTurnId: null,
    lastSeq: 0,
    updatedAt: Date.now(),
  };
}

function ensureSelectedSession(state: ProviderState): SessionEntry {
  if (state.selectedKey && state.sessions[state.selectedKey]) {
    return state.sessions[state.selectedKey];
  }
  return createSessionEntry("draft");
}

function updateSelectedSession(
  state: ProviderState,
  updater: (session: SessionEntry) => SessionEntry,
): ProviderState {
  const current = ensureSelectedSession(state);
  const key = state.selectedKey || current.key;
  const nextSession = updater(current);
  return {
    ...state,
    selectedKey: key,
    sessions: {
      ...state.sessions,
      [key]: nextSession,
    },
  };
}

function reducer(state: ProviderState, action: Action): ProviderState {
  switch (action.type) {
    case "SET_TOOLS":
      return updateSelectedSession(state, (session) => ({
        ...session,
        enabledTools: action.tools,
      }));
    case "SET_CAPABILITY":
      return updateSelectedSession(state, (session) => ({
        ...session,
        activeCapability: action.cap,
      }));
    case "SET_CHAT_MODE":
      return updateSelectedSession(state, (session) => ({
        ...session,
        chatMode: action.mode,
      }));
    case "SET_KB":
      return updateSelectedSession(state, (session) => ({
        ...session,
        knowledgeBases: action.kbs,
      }));
    case "SET_LANGUAGE":
      return updateSelectedSession(state, (session) => ({
        ...session,
        language: action.lang,
      }));
    case "ADD_USER_MSG": {
      const session = state.sessions[action.key] ?? createSessionEntry(action.key);
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages: [
              ...session.messages,
              {
                role: "user",
                content: action.content,
                capability: action.capability || "",
                ...(action.attachments?.length ? { attachments: action.attachments } : {}),
                ...(action.requestSnapshot ? { requestSnapshot: action.requestSnapshot } : {}),
              },
            ],
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "STREAM_START":
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...(state.sessions[action.key] ?? createSessionEntry(action.key)),
            isStreaming: true,
            status: "running",
            messages: [
              ...(state.sessions[action.key]?.messages ?? []),
              {
                role: "assistant",
                content: "",
                events: [],
                capability: (state.sessions[action.key] ?? createSessionEntry(action.key)).activeCapability || "",
              },
            ],
            updatedAt: Date.now(),
          },
        },
      };
    case "STREAM_EVENT": {
      const session = state.sessions[action.key] ?? createSessionEntry(action.key);
      const msgs = [...session.messages];
      let last = msgs[msgs.length - 1];
      if (last?.role !== "assistant") {
        msgs.push({ role: "assistant", content: "", events: [], capability: session.activeCapability || "" });
        last = msgs[msgs.length - 1];
      }
      const events = [...(last?.events || []), action.event];
      let content = last?.content || "";
      if (shouldAppendEventContent(action.event)) content += action.event.content;
      const capability = last?.capability || session.activeCapability || "";
      msgs[msgs.length - 1] = { ...(last || { role: "assistant", content: "" }), content, events, capability };
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages: msgs,
            currentStage:
              action.event.type === "stage_start"
                ? action.event.stage
                : action.event.type === "stage_end"
                  ? ""
                  : session.currentStage,
            activeTurnId: action.event.turn_id || session.activeTurnId,
            lastSeq: Math.max(session.lastSeq, action.event.seq || 0),
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "STREAM_END":
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...(state.sessions[action.key] ?? createSessionEntry(action.key)),
            isStreaming: false,
            currentStage: "",
            status: action.status ?? "completed",
            activeTurnId:
              action.status === "running"
                ? action.turnId || state.sessions[action.key]?.activeTurnId || null
                : null,
            updatedAt: Date.now(),
          },
        },
        sidebarRefreshToken: state.sidebarRefreshToken + 1,
      };
    case "BIND_SERVER_SESSION": {
      const current = state.sessions[action.key] ?? createSessionEntry(action.key);
      const targetKey = action.sessionId;
      const existing = state.sessions[targetKey];
      const merged: SessionEntry = {
        ...(existing ?? current),
        ...current,
        key: targetKey,
        sessionId: action.sessionId,
        activeTurnId: action.turnId || current.activeTurnId,
        status: current.isStreaming ? "running" : current.status,
        updatedAt: Date.now(),
      };
      const nextSessions = { ...state.sessions };
      delete nextSessions[action.key];
      nextSessions[targetKey] = merged;
      return {
        ...state,
        selectedKey: state.selectedKey === action.key ? targetKey : state.selectedKey,
        sessions: nextSessions,
        sidebarRefreshToken: state.sidebarRefreshToken + 1,
      };
    }
    case "LOAD_SESSION": {
      const existing = state.sessions[action.key] ?? createSessionEntry(action.key, action.sessionId);
      return {
        ...state,
        selectedKey: action.key,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...existing,
            key: action.key,
            sessionId: action.sessionId,
            enabledTools: action.tools ?? existing.enabledTools,
            activeCapability:
              action.capability !== undefined ? action.capability : existing.activeCapability,
            chatMode: action.chatMode ?? existing.chatMode,
            knowledgeBases: action.knowledgeBases ?? existing.knowledgeBases,
            messages: action.messages,
            isStreaming: (action.status || "idle") === "running",
            currentStage: "",
            activeTurnId: action.activeTurnId || null,
            lastSeq: action.lastSeq ?? existing.lastSeq,
            status: action.status || "idle",
            language: action.language ?? existing.language,
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "NEW_SESSION": {
      const MAX_CACHED_SESSIONS = 20;
      const seedChatMode = state.selectedKey
        ? state.sessions[state.selectedKey]?.chatMode ?? getDefaultChatMode()
        : getDefaultChatMode();
      let nextSessions = {
        ...state.sessions,
        [action.key]: createSessionEntry(action.key, null, seedChatMode),
      };
      const keys = Object.keys(nextSessions);
      if (keys.length > MAX_CACHED_SESSIONS) {
        const evictable = keys
          .filter((k) => k !== action.key && nextSessions[k].status !== "running")
          .sort((a, b) => nextSessions[a].updatedAt - nextSessions[b].updatedAt);
        const toRemove = evictable.slice(0, keys.length - MAX_CACHED_SESSIONS);
        for (const k of toRemove) delete nextSessions[k];
      }
      return { ...state, selectedKey: action.key, sessions: nextSessions };
    }
    default:
      return state;
  }
}

const initialState: ProviderState = {
  selectedKey: null,
  sessions: {},
  sidebarRefreshToken: 0,
};

interface ChatContextValue {
  state: ChatState;
  setTools: (tools: string[]) => void;
  setCapability: (cap: string | null) => void;
  setChatMode: (mode: ChatMode) => void;
  setKBs: (kbs: string[]) => void;
  setLanguage: (lang: string) => void;
  sendMessage: (
    content: string,
    attachments?: OutgoingAttachment[],
    config?: Record<string, unknown>,
    notebookReferences?: NotebookReferencePayload[],
    historyReferences?: HistoryReferencePayload,
    options?: SendMessageOptions,
  ) => void;
  cancelStreamingTurn: () => void;
  newSession: () => void;
  loadSession: (sessionId: string) => Promise<void>;
  selectedSessionId: string | null;
  sessionStatuses: Record<string, SessionStatusSnapshot>;
  sidebarRefreshToken: number;
}

const ChatCtx = createContext<ChatContextValue | null>(null);

export function UnifiedChatProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const restoredRef = useRef(false);
  const stateRef = useRef(initialState);
  const runnersRef = useRef<
    Map<
      string,
      {
        key: string;
        client: UnifiedWSClient;
      }
    >
  >(new Map());
  const resumeTargetsRef = useRef<Map<string, { turnId: string; seq: number }>>(new Map());
  const pendingResumeTelemetryRef = useRef<Map<string, string>>(new Map());
  const draftCounterRef = useRef(0);
  const retryTimersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(
    () => () => {
      runnersRef.current.forEach(({ client }) => client.disconnect());
      runnersRef.current.clear();
      retryTimersRef.current.forEach((id) => clearTimeout(id));
      retryTimersRef.current.clear();
    },
    [],
  );

  useEffect(() => {
    void primeUnifiedTurnContractCheck();
  }, []);

  const makeDraftKey = useCallback(() => {
    draftCounterRef.current += 1;
    return `draft_${Date.now()}_${draftCounterRef.current}`;
  }, []);

  const hydrateMessages = useCallback((messages: SessionMessage[]): MessageItem[] => {
    return messages.map((message) => ({
      role: message.role,
      content:
        message.role === "assistant"
          ? normalizeMarkdownForDisplay(message.content)
          : message.content,
      capability: message.capability || "",
      events: Array.isArray(message.events) ? message.events : [],
      attachments: Array.isArray(message.attachments)
        ? message.attachments.map((item) => ({
            type: item.type,
            filename: item.filename,
            base64: item.base64,
            url: item.url,
            mime_type: item.mime_type,
          }))
        : [],
    }));
  }, []);

  const moveRunner = useCallback((oldKey: string, newKey: string) => {
    if (oldKey === newKey) return;
    const runner = runnersRef.current.get(oldKey);
    if (!runner) return;
    runnersRef.current.delete(oldKey);
    runner.key = newKey;
    runnersRef.current.set(newKey, runner);
    const target = resumeTargetsRef.current.get(oldKey);
    if (target) {
      resumeTargetsRef.current.delete(oldKey);
      resumeTargetsRef.current.set(newKey, target);
    }
    const pendingResumeTurnId = pendingResumeTelemetryRef.current.get(oldKey);
    if (pendingResumeTurnId) {
      pendingResumeTelemetryRef.current.delete(oldKey);
      pendingResumeTelemetryRef.current.set(newKey, pendingResumeTurnId);
    }
  }, []);

  const resumeActiveTurn = useCallback((key: string) => {
    const target =
      resumeTargetsRef.current.get(key) ||
      (() => {
        const session = stateRef.current.sessions[key];
        if (!session?.isStreaming || !session.activeTurnId) return null;
        return { turnId: session.activeTurnId, seq: session.lastSeq };
      })();
    if (!target) return;
    const runner = runnersRef.current.get(key);
    if (!runner?.client.connected) return;
    const session = stateRef.current.sessions[key];
    pendingResumeTelemetryRef.current.set(key, target.turnId);
    void trackWebSurfaceEvent({
      eventName: "resume_attempted",
      sessionId: session?.sessionId,
      turnId: target.turnId,
      metadata: { seq: target.seq },
    });
    runner.client.send({
      type: "resume_from",
      turn_id: target.turnId,
      seq: target.seq,
    });
  }, []);

  const handleRunnerEvent = useCallback(
    (runnerKey: string, event: StreamEvent) => {
      const runner = runnersRef.current.get(runnerKey);
      const effectiveKey = runner?.key || runnerKey;
      const turnIdFromEvent =
        (event.metadata as { turn_id?: string } | undefined)?.turn_id || event.turn_id || "";
      if (turnIdFromEvent) {
        const existingTarget = resumeTargetsRef.current.get(effectiveKey);
        resumeTargetsRef.current.set(effectiveKey, {
          turnId: turnIdFromEvent,
          seq: typeof event.seq === "number" ? event.seq : existingTarget?.seq ?? 0,
        });
      }
      const pendingResumeTurnId = pendingResumeTelemetryRef.current.get(effectiveKey);
      if (
        pendingResumeTurnId &&
        turnIdFromEvent &&
        pendingResumeTurnId === turnIdFromEvent &&
        event.type !== "error"
      ) {
        pendingResumeTelemetryRef.current.delete(effectiveKey);
        trackWebSurfaceEventOnce(`web:resume-succeeded:${turnIdFromEvent}`, {
          eventName: "resume_succeeded",
          sessionId:
            (event.metadata as { session_id?: string } | undefined)?.session_id ||
            event.session_id ||
            stateRef.current.sessions[effectiveKey]?.sessionId,
          turnId: turnIdFromEvent,
          metadata: { event_type: event.type },
        });
      }
      if (event.type === "session") {
        const sessionId =
          (event.metadata as { session_id?: string } | undefined)?.session_id ||
          event.session_id ||
          "";
        const turnId =
          (event.metadata as { turn_id?: string } | undefined)?.turn_id || event.turn_id || null;
        if (sessionId) {
          dispatch({
            type: "BIND_SERVER_SESSION",
            key: effectiveKey,
            sessionId,
            turnId,
          });
          moveRunner(effectiveKey, sessionId);
        }
        void trackWebSurfaceEvent({
          eventName: "session_event_received",
          sessionId: sessionId || stateRef.current.sessions[effectiveKey]?.sessionId,
          turnId,
        });
        return;
      }
      if (event.type === "done") {
        resumeTargetsRef.current.delete(effectiveKey);
        pendingResumeTelemetryRef.current.delete(effectiveKey);
        const status = String((event.metadata as { status?: string } | undefined)?.status || "completed");
        dispatch({
          type: "STREAM_END",
          key: effectiveKey,
          status: (status as SessionRuntimeStatus) || "completed",
          turnId: event.turn_id || null,
        });
        const runner = runnersRef.current.get(effectiveKey);
        runner?.client.disconnect();
        runnersRef.current.delete(effectiveKey);
        return;
      }
      dispatch({ type: "STREAM_EVENT", key: effectiveKey, event });
      if (
        event.type === "error" &&
        Boolean((event.metadata as { turn_terminal?: boolean } | undefined)?.turn_terminal)
      ) {
        resumeTargetsRef.current.delete(effectiveKey);
        pendingResumeTelemetryRef.current.delete(effectiveKey);
        trackWebSurfaceEventOnce(`web:surface-render-failed:${turnIdFromEvent || effectiveKey}`, {
          eventName: "surface_render_failed",
          sessionId:
            (event.metadata as { session_id?: string } | undefined)?.session_id ||
            event.session_id ||
            stateRef.current.sessions[effectiveKey]?.sessionId,
          turnId: turnIdFromEvent || null,
          metadata: {
            status: (event.metadata as { status?: string } | undefined)?.status || "failed",
            source: event.source,
          },
        });
        const status = String((event.metadata as { status?: string } | undefined)?.status || "failed");
        dispatch({
          type: "STREAM_END",
          key: effectiveKey,
          status: status as SessionRuntimeStatus,
          turnId: event.turn_id || null,
        });
      }
    },
    [moveRunner],
  );

  const ensureRunner = useCallback(
    (key: string) => {
      const existing = runnersRef.current.get(key);
      if (existing) {
        if (!existing.client.connected) existing.client.connect();
        return existing;
      }
      const record = {
        key,
        client: new UnifiedWSClient(
          (event) => handleRunnerEvent(record.key, event),
          () => {
            resumeTargetsRef.current.delete(record.key);
            const session = stateRef.current.sessions[record.key];
            if (session?.isStreaming) {
              trackWebSurfaceEventOnce(
                `web:surface-render-failed:runner-close:${session.activeTurnId || record.key}`,
                {
                  eventName: "surface_render_failed",
                  sessionId: session.sessionId,
                  turnId: session.activeTurnId,
                  metadata: { source: "runner_close" },
                },
              );
              dispatch({ type: "STREAM_END", key: record.key, status: "failed" });
            }
            runnersRef.current.delete(record.key);
          },
          () => {
            const session = stateRef.current.sessions[record.key];
            const resumeTarget = resumeTargetsRef.current.get(record.key);
            void trackWebSurfaceEvent({
              eventName: "ws_connected",
              sessionId: session?.sessionId,
              turnId: resumeTarget?.turnId || session?.activeTurnId || null,
            });
            resumeActiveTurn(record.key);
          },
        ),
      };
      runnersRef.current.set(key, record);
      record.client.connect();
      return record;
    },
    [handleRunnerEvent, resumeActiveTurn],
  );

  const sendThroughRunner = useCallback(
    function dispatchToRunner(key: string, msg: ChatMessage, attempt = 0) {
      if (attempt > 0) {
        const session = stateRef.current.sessions[key];
        if (session && !session.isStreaming && session.status !== "running") {
          return;
        }
      }
      const runner = ensureRunner(key);
      if (runner.client.terminated) {
        return;
      }
      if (!runner.client.connected) {
        if (attempt >= 8) {
          console.error("WebSocket failed to connect after retries");
          resumeTargetsRef.current.delete(key);
          runnersRef.current.delete(key);
          dispatch({ type: "STREAM_END", key, status: "failed" });
          return;
        }
        const delay = Math.min(4_000, 200 * 2 ** Math.max(0, attempt));
        const jitter = Math.floor(delay * 0.2 * Math.random());
        const timerId = setTimeout(() => {
          retryTimersRef.current.delete(timerId);
          dispatchToRunner(key, msg, attempt + 1);
        }, delay + jitter);
        retryTimersRef.current.add(timerId);
        return;
      }
      runner.client.send(msg);
    },
    [ensureRunner],
  );

  const loadSession = useCallback(
    async (sessionId: string) => {
      const session = await getSession(sessionId);
      const activeTurn = Array.isArray(session.active_turns) ? session.active_turns[0] : undefined;
      const key = session.session_id || session.id;
      dispatch({
        type: "LOAD_SESSION",
        key,
        sessionId: key,
        messages: hydrateMessages(session.messages ?? []),
        activeTurnId: activeTurn?.turn_id || activeTurn?.id || null,
        lastSeq: activeTurn?.last_seq || 0,
        status: (session.status as SessionRuntimeStatus | undefined) || (activeTurn ? "running" : "idle"),
        tools: Array.isArray(session.preferences?.tools) ? session.preferences.tools : [],
        capability: session.preferences?.capability || null,
        chatMode: session.preferences?.chat_mode === "deep" ? "deep" : "fast",
        knowledgeBases: Array.isArray(session.preferences?.knowledge_bases)
          ? session.preferences.knowledge_bases
          : [],
        language: session.preferences?.language || "en",
      });
      if (activeTurn?.turn_id || activeTurn?.id) {
        resumeTargetsRef.current.set(key, {
          turnId: activeTurn.turn_id || activeTurn.id,
          seq: activeTurn?.last_seq || 0,
        });
        const runner = ensureRunner(key);
        if (runner.client.connected) {
          resumeActiveTurn(key);
        }
      }
    },
    [ensureRunner, hydrateMessages, resumeActiveTurn],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const current = state.selectedKey ? state.sessions[state.selectedKey] : null;
    writeStoredActiveSessionId(current?.sessionId ?? null);
  }, [state.selectedKey, state.sessions]);

  useEffect(() => {
    if (restoredRef.current || typeof window === "undefined") return;
    restoredRef.current = true;
    const savedSessionId = readStoredActiveSessionId();
    if (savedSessionId) {
      void loadSession(savedSessionId).catch(() => {
        writeStoredActiveSessionId(null);
        dispatch({ type: "NEW_SESSION", key: makeDraftKey() });
      });
      return;
    }
    dispatch({ type: "NEW_SESSION", key: makeDraftKey() });
  }, [loadSession, makeDraftKey]);

  const sendMessage = useCallback(
    (
      content: string,
      attachments?: OutgoingAttachment[],
      config?: Record<string, unknown>,
      notebookReferences?: NotebookReferencePayload[],
      historyReferences?: HistoryReferencePayload,
      options?: SendMessageOptions,
    ) => {
      const msgAttachments = attachments?.map((a) => ({
        type: a.type,
        filename: a.filename,
        base64: a.base64,
        url: a.url,
        mime_type: a.mime_type,
      }));
      const currentState = stateRef.current;
      let key = currentState.selectedKey;
      if (!key) {
        key = makeDraftKey();
        dispatch({ type: "NEW_SESSION", key });
      }
      const session = currentState.sessions[key] ?? createSessionEntry(key);
      const replaySnapshot = options?.requestSnapshotOverride;
      const effectiveCapability = replaySnapshot?.capability ?? session.activeCapability;
      const effectiveChatMode =
        effectiveCapability === null
          ? (
              replaySnapshot?.config?.chat_mode === "deep"
                ? "deep"
                : replaySnapshot?.config?.chat_mode === "fast"
                  ? "fast"
                  : session.chatMode
            )
          : session.chatMode;
      const effectiveTools = replaySnapshot?.enabledTools ?? session.enabledTools;
      const effectiveKnowledgeBases = replaySnapshot?.knowledgeBases ?? session.knowledgeBases;
      const effectiveLanguage = replaySnapshot?.language ?? session.language;
      const requestConfig: Record<string, unknown> = {
        ...(config || {}),
        ...(effectiveCapability === null ? { chat_mode: effectiveChatMode } : {}),
      };
      const researchSources = Array.isArray(config?.sources)
        ? config.sources.filter((value): value is string => typeof value === "string")
        : [];
      const shouldSendKnowledgeBases =
        effectiveTools.includes("rag") ||
        (effectiveCapability === "deep_research" && researchSources.includes("kb"));
      const requestSnapshot: MessageRequestSnapshot = replaySnapshot ?? {
        content,
        capability: effectiveCapability,
        enabledTools: [...effectiveTools],
        knowledgeBases: shouldSendKnowledgeBases ? [...effectiveKnowledgeBases] : [],
        language: effectiveLanguage,
        ...(msgAttachments?.length ? { attachments: msgAttachments } : {}),
        ...(Object.keys(requestConfig).length > 0 ? { config: requestConfig } : {}),
        ...(notebookReferences?.length ? { notebookReferences } : {}),
        ...(historyReferences?.length ? { historyReferences: [...historyReferences] } : {}),
      };
      if (options?.displayUserMessage !== false) {
        dispatch({
          type: "ADD_USER_MSG",
          key,
          content,
          capability: effectiveCapability,
          attachments: msgAttachments,
          requestSnapshot,
        });
      }
      dispatch({ type: "STREAM_START", key });
      void trackWebSurfaceEvent({
        eventName: "start_turn_sent",
        sessionId: session.sessionId,
        metadata: {
          capability: effectiveCapability || "chat",
          has_attachments: Boolean(msgAttachments?.length),
        },
      });
      const effectiveConfig =
        options?.persistUserMessage === false
          ? { ...requestConfig, _persist_user_message: false }
          : requestConfig;
      sendThroughRunner(key, {
        type: "start_turn",
        content,
        tools: effectiveTools,
        capability: effectiveCapability,
        knowledge_bases: shouldSendKnowledgeBases ? effectiveKnowledgeBases : [],
        session_id: session.sessionId,
        attachments,
        language: effectiveLanguage,
        ...(notebookReferences?.length
          ? { notebook_references: notebookReferences }
          : {}),
        ...(historyReferences?.length
          ? { history_references: historyReferences }
          : {}),
        ...(effectiveConfig && Object.keys(effectiveConfig).length > 0
          ? { config: effectiveConfig }
          : {}),
      });
    },
    [makeDraftKey, sendThroughRunner],
  );

  const cancelStreamingTurn = useCallback(() => {
    const currentState = stateRef.current;
    const key = currentState.selectedKey;
    if (!key) return;
    const session = currentState.sessions[key];
    const turnId = session?.activeTurnId;
    if (!session || !turnId) return;
    resumeTargetsRef.current.delete(key);
    pendingResumeTelemetryRef.current.delete(key);
    void trackWebSurfaceEvent({
      eventName: "user_cancelled",
      sessionId: session.sessionId,
      turnId,
    });
    const runner = runnersRef.current.get(key);
    if (runner?.client.connected) {
      runner.client.send({ type: "cancel_turn", turn_id: turnId });
      runner.client.disconnect();
      runnersRef.current.delete(key);
    }
    dispatch({ type: "STREAM_END", key, status: "cancelled" });
  }, []);

  const derivedState = useMemo<ChatState>(() => {
    const current = ensureSelectedSession(state);
    return {
      sessionId: current.sessionId,
      enabledTools: current.enabledTools,
      activeCapability: current.activeCapability,
      chatMode: current.chatMode,
      knowledgeBases: current.knowledgeBases,
      messages: current.messages,
      isStreaming: current.isStreaming,
      currentStage: current.currentStage,
      language: current.language,
    };
  }, [state]);

  const sessionStatuses = useMemo<Record<string, SessionStatusSnapshot>>(() => {
    const entries: Record<string, SessionStatusSnapshot> = {};
    for (const session of Object.values(state.sessions)) {
      if (!session.sessionId || session.status !== "running") continue;
      entries[session.sessionId] = {
        sessionId: session.sessionId,
        status: session.status,
        activeTurnId: session.activeTurnId,
        updatedAt: session.updatedAt,
      };
    }
    return entries;
  }, [state.sessions]);

  const setTools = useCallback((tools: string[]) => {
    dispatch({ type: "SET_TOOLS", tools });
  }, []);

  const setCapability = useCallback((cap: string | null) => {
    dispatch({ type: "SET_CAPABILITY", cap });
  }, []);

  const setChatMode = useCallback((mode: ChatMode) => {
    dispatch({ type: "SET_CHAT_MODE", mode });
  }, []);

  const setKBs = useCallback((kbs: string[]) => {
    dispatch({ type: "SET_KB", kbs });
  }, []);

  const setLanguage = useCallback((lang: string) => {
    dispatch({ type: "SET_LANGUAGE", lang });
  }, []);

  const newSession = useCallback(() => {
    dispatch({ type: "NEW_SESSION", key: makeDraftKey() });
  }, [makeDraftKey]);

  const value: ChatContextValue = {
    state: derivedState,
    setTools,
    setCapability,
    setChatMode,
    setKBs,
    setLanguage,
    sendMessage,
    cancelStreamingTurn,
    newSession,
    loadSession,
    selectedSessionId: derivedState.sessionId,
    sessionStatuses,
    sidebarRefreshToken: state.sidebarRefreshToken,
  };

  return <ChatCtx.Provider value={value}>{children}</ChatCtx.Provider>;
}

export function useUnifiedChat() {
  const ctx = useContext(ChatCtx);
  if (!ctx) throw new Error("useUnifiedChat must be inside UnifiedChatProvider");
  return ctx;
}
