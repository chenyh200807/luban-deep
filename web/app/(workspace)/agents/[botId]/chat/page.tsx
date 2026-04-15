"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Bot, Loader2, Send } from "lucide-react";
import RestrictedSurface from "@/components/common/RestrictedSurface";
import { apiUrl } from "@/lib/api";
import AssistantResponse from "@/components/common/AssistantResponse";
import { getSession, type SessionMessage } from "@/lib/session-api";
import { UnifiedWSClient, type StreamEvent } from "@/lib/unified-ws";
import { allowsLegacyWebSurfaces, requiresWebAuth } from "@/lib/web-access";

interface BotInfo {
  bot_id: string;
  name: string;
  running: boolean;
}

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  thinking?: string[];
}

export default function BotChatPage() {
  if (!requiresWebAuth() || !allowsLegacyWebSurfaces()) {
    return (
      <RestrictedSurface
        title="TutorBot chat unavailable"
        message="当前 Web 端未接入登录态，或 legacy TutorBot 聊天页面未显式开启，因此已默认关闭。请使用已鉴权入口访问。"
      />
    );
  }
  const { botId } = useParams<{ botId: string }>();
  const router = useRouter();
  const { t } = useTranslation();
  const botIdString = String(botId || "");

  const [bot, setBot] = useState<BotInfo | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [thinking, setThinking] = useState<string[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const thinkingRef = useRef<string[]>([]);
  const streamingContentRef = useRef("");
  const sendLockRef = useRef(false);
  const sessionIdRef = useRef<string | null>(null);
  const activeTurnRef = useRef<string | null>(null);
  const lastSeqRef = useRef(0);
  const clientRef = useRef<UnifiedWSClient | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const storageKey = `tutorbot-session:${botIdString}`;

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    });
  }, []);

  const persistSessionId = useCallback((sessionId: string | null) => {
    if (typeof window === "undefined") return;
    if (sessionId) {
      window.localStorage.setItem(storageKey, sessionId);
      return;
    }
    window.localStorage.removeItem(storageKey);
  }, [storageKey]);

  const finalizeStreamingMessage = useCallback(() => {
    const finalContent = streamingContentRef.current.trim();
    const thinkingSnapshot = thinkingRef.current.length ? [...thinkingRef.current] : undefined;
    if (finalContent) {
      setMessages((msgs) => [
        ...msgs,
        { role: "assistant", content: finalContent, thinking: thinkingSnapshot },
      ]);
    }
    streamingContentRef.current = "";
    setStreamingContent("");
    thinkingRef.current = [];
    setThinking([]);
    setStreaming(false);
    activeTurnRef.current = null;
    lastSeqRef.current = 0;
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  const resumeActiveTurn = useCallback(() => {
    const client = clientRef.current;
    if (!client?.connected || !activeTurnRef.current) {
      return;
    }
    client.send({
      type: "resume_from",
      turn_id: activeTurnRef.current,
      seq: lastSeqRef.current,
    });
  }, []);

  const hydrateMessages = useCallback((sessionMessages: SessionMessage[]) => {
    const restored: ChatMsg[] = sessionMessages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ role: m.role as "user" | "assistant", content: m.content }));
    if (restored.length) {
      setMessages(restored);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    fetch(apiUrl(`/api/v1/tutorbot/${botIdString}`))
      .then((r) => (r.ok ? r.json() : null))
      .then((payload) => {
        if (!cancelled) setBot(payload);
      })
      .catch(() => setBot(null));

    const loadHistory = async () => {
      if (typeof window !== "undefined") {
        const savedSessionId = window.localStorage.getItem(storageKey);
        if (savedSessionId) {
          try {
            const session = await getSession(savedSessionId);
            if (!cancelled) {
              sessionIdRef.current = session.session_id || session.id;
              hydrateMessages(session.messages ?? []);
              const activeTurn = Array.isArray(session.active_turns) ? session.active_turns[0] : undefined;
              if (activeTurn?.turn_id || activeTurn?.id) {
                activeTurnRef.current = activeTurn.turn_id || activeTurn.id;
                lastSeqRef.current = activeTurn?.last_seq || 0;
                resumeActiveTurn();
              }
            }
            return;
          } catch {
            persistSessionId(null);
          }
        }
      }
    };

    void loadHistory();

    return () => {
      cancelled = true;
    };
  }, [botIdString, hydrateMessages, persistSessionId, resumeActiveTurn, storageKey]);

  const handleEvent = useCallback((event: StreamEvent) => {
    if (typeof event.seq === "number") {
      lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
    }
    if (event.session_id) {
      sessionIdRef.current = event.session_id;
      persistSessionId(event.session_id);
    }
    if (event.turn_id) {
      activeTurnRef.current = event.turn_id;
    }

    if (event.type === "progress") {
      thinkingRef.current = [...thinkingRef.current, event.content];
      setThinking(thinkingRef.current);
      scrollToBottom();
      return;
    }

    if (event.type === "content") {
      streamingContentRef.current = `${streamingContentRef.current}${event.content}`;
      setStreamingContent(streamingContentRef.current);
      scrollToBottom();
      return;
    }

    if (event.type === "result" && !streamingContentRef.current) {
      const response = typeof event.metadata?.response === "string" ? event.metadata.response : "";
      if (response) {
        streamingContentRef.current = response;
        setStreamingContent(response);
        scrollToBottom();
      }
      return;
    }

    if (event.type === "done") {
      finalizeStreamingMessage();
      return;
    }

    if (event.type === "error") {
      setMessages((msgs) => [...msgs, { role: "assistant", content: `Error: ${event.content}` }]);
      streamingContentRef.current = "";
      setStreamingContent("");
      thinkingRef.current = [];
      setThinking([]);
      setStreaming(false);
      activeTurnRef.current = null;
      lastSeqRef.current = 0;
      return;
    }
  }, [finalizeStreamingMessage, persistSessionId, scrollToBottom]);

  useEffect(() => {
    const client = new UnifiedWSClient(
      handleEvent,
      () => {
        setStreaming(false);
      },
      () => {
        resumeActiveTurn();
      },
    );
    clientRef.current = client;
    client.connect();

    return () => {
      client.disconnect();
      clientRef.current = null;
    };
  }, [handleEvent, resumeActiveTurn]);

  useEffect(() => {
    if (!streaming) {
      sendLockRef.current = false;
    }
  }, [streaming]);

  const send = useCallback(() => {
    const text = input.trim();
    if (
      !text ||
      streaming ||
      sendLockRef.current ||
      !clientRef.current?.connected
    ) {
      return;
    }

    sendLockRef.current = true;
    setMessages((msgs) => [...msgs, { role: "user", content: text }]);
    setInput("");
    setStreaming(true);
    setThinking([]);
    setStreamingContent("");
    streamingContentRef.current = "";
    clientRef.current.send({
      type: "start_turn",
      content: text,
      capability: "tutorbot",
      session_id: sessionIdRef.current,
      config: {
        bot_id: botIdString,
        interaction_profile: "tutorbot",
        source: "workspace_agents",
      },
    });
    scrollToBottom();
  }, [botIdString, input, streaming, scrollToBottom]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    },
    [send],
  );

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-[var(--border)] px-5 py-3">
        <button
          onClick={() => router.push("/agents")}
          className="rounded-lg p-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <Bot className="h-4 w-4 text-[var(--muted-foreground)]" />
        <span className="text-[14px] font-medium text-[var(--foreground)]">
          {bot?.name ?? botId}
        </span>
        {bot?.running && (
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
        )}
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-6 [scrollbar-gutter:stable]">
        <div className="mx-auto max-w-[720px] space-y-5">
          {messages.length === 0 && !streaming && (
            <div className="flex flex-col items-center justify-center pt-24 text-center">
              <div className="mb-3 rounded-xl bg-[var(--muted)] p-3 text-[var(--muted-foreground)]">
                <Bot size={22} />
              </div>
              <p className="text-[14px] font-medium text-[var(--foreground)]">
                {t("Chat with {{name}}", { name: bot?.name ?? botId })}
              </p>
              <p className="mt-1 text-[13px] text-[var(--muted-foreground)]">
                {t("Send a message to start the conversation.")}
              </p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={msg.role === "user" ? "flex justify-end" : ""}>
              {msg.role === "user" ? (
                <div className="max-w-[80%] rounded-2xl rounded-br-md bg-[var(--primary)] px-4 py-2.5 text-[14px] text-[var(--primary-foreground)]">
                  {msg.content}
                </div>
              ) : (
                <div className="max-w-full">
                  {msg.thinking && msg.thinking.length > 0 && (
                    <details className="mb-2">
                      <summary className="cursor-pointer text-[12px] text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                        {t("Thinking ({{count}} steps)", { count: msg.thinking.length })}
                      </summary>
                      <div className="mt-1 space-y-1 border-l-2 border-[var(--border)] pl-3">
                        {msg.thinking.map((th, j) => (
                          <p key={j} className="text-[12px] text-[var(--muted-foreground)]">{th}</p>
                        ))}
                      </div>
                    </details>
                  )}
                  <AssistantResponse content={msg.content} />
                </div>
              )}
            </div>
          ))}

          {/* Streaming indicator */}
          {streaming && (
            <div className="space-y-2">
              {thinking.length > 0 && (
                <div className="space-y-1 border-l-2 border-[var(--border)] pl-3">
                  {thinking.map((th, i) => (
                    <p key={i} className="text-[12px] text-[var(--muted-foreground)]">{th}</p>
                  ))}
                </div>
              )}
              {streamingContent && (
                <div className="max-w-full">
                  <AssistantResponse content={streamingContent} />
                </div>
              )}
              <div className="flex items-center gap-2 text-[13px] text-[var(--muted-foreground)]">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>{thinking.length > 0 ? t("Working...") : t("Thinking...")}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-[var(--border)] px-5 py-3">
        <div className="mx-auto flex max-w-[720px] items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t("Type a message...")}
            rows={1}
            disabled={streaming}
            className="flex-1 resize-none rounded-xl border border-[var(--border)] bg-transparent px-4 py-2.5 text-[14px] text-[var(--foreground)] outline-none transition-colors focus:border-[var(--ring)] disabled:opacity-50 placeholder:text-[var(--muted-foreground)]/40"
          />
          <button
            onClick={send}
            disabled={streaming || !input.trim()}
            className="flex h-[42px] w-[42px] items-center justify-center rounded-xl bg-[var(--primary)] text-[var(--primary-foreground)] transition-opacity hover:opacity-90 disabled:opacity-30"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
