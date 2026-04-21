/**
 * Unified WebSocket Client
 *
 * Connects to the single `/api/v1/ws` endpoint and provides
 * a typed streaming interface for the new ChatOrchestrator protocol.
 */

import { apiUrl, wsUrl } from "./api";
import { requiresWebAuth } from "./web-access";

// ---- StreamEvent types (mirror Python StreamEventType) ----

export type StreamEventType =
  | "stage_start"
  | "stage_end"
  | "thinking"
  | "observation"
  | "content"
  | "tool_call"
  | "tool_result"
  | "progress"
  | "sources"
  | "result"
  | "error"
  | "session"
  | "done";

export interface StreamEvent {
  type: StreamEventType;
  source: string;
  stage: string;
  content: string;
  metadata: Record<string, unknown>;
  session_id?: string;
  turn_id?: string;
  seq?: number;
  timestamp: number;
}

// ---- Client message ----

export interface StartTurnMessage {
  type: "message" | "start_turn";
  content: string;
  tools?: string[];
  capability?: string | null;
  knowledge_bases?: string[];
  session_id?: string | null;
  attachments?: {
    type: string;
    url?: string;
    base64?: string;
    filename?: string;
    mime_type?: string;
  }[];
  language?: string;
  config?: Record<string, unknown>;
  notebook_references?: {
    notebook_id: string;
    record_ids: string[];
  }[];
  history_references?: string[];
}

export interface SubscribeTurnMessage {
  type: "subscribe_turn";
  turn_id: string;
  after_seq?: number;
}

export interface SubscribeSessionMessage {
  type: "subscribe_session";
  session_id: string;
  after_seq?: number;
}

export interface ResumeTurnMessage {
  type: "resume_from";
  turn_id: string;
  seq?: number;
}

export interface UnsubscribeMessage {
  type: "unsubscribe";
  turn_id?: string;
  session_id?: string;
}

export interface CancelTurnMessage {
  type: "cancel_turn";
  turn_id: string;
}

export type ChatMessage =
  | StartTurnMessage
  | SubscribeTurnMessage
  | SubscribeSessionMessage
  | ResumeTurnMessage
  | UnsubscribeMessage
  | CancelTurnMessage;

// ---- Connection manager ----

export type EventHandler = (event: StreamEvent) => void;

interface TurnContractPayload {
  version?: number;
  transport?: {
    primary_websocket?: string;
  };
  schemas?: Record<string, unknown>;
  trace_fields?: string[];
}

interface TurnContractCheckResult {
  ok: boolean;
  error?: string;
}

const RECONNECT_BASE_DELAY_MS = 250;
const RECONNECT_MAX_DELAY_MS = 5_000;
const RECONNECT_MAX_ATTEMPTS = 6;

const STRICT_CONTRACT_CHECK = process.env.NEXT_PUBLIC_STRICT_CONTRACT_CHECK === "true";
let turnContractCheckPromise: Promise<TurnContractCheckResult> | null = null;

function buildLocalContractError(message: string): StreamEvent {
  return {
    type: "error",
    source: "contract_guard",
    stage: "contract_check",
    content: message,
    metadata: {
      contract_check: true,
      turn_terminal: true,
      status: "failed",
    },
    timestamp: Date.now(),
  };
}

async function fetchTurnContractCheck(): Promise<TurnContractCheckResult> {
  if (!requiresWebAuth()) {
    return { ok: true };
  }
  try {
    const response = await fetch(apiUrl("/api/v1/system/turn-contract"), {
      method: "GET",
      cache: "no-store",
    });
    if (!response.ok) {
      return {
        ok: false,
        error: `turn contract endpoint returned HTTP ${response.status}`,
      };
    }
    const payload = (await response.json()) as TurnContractPayload;
    const errors: string[] = [];
    if (payload.transport?.primary_websocket !== "/api/v1/ws") {
      errors.push(
        `primary_websocket mismatch: expected /api/v1/ws, got ${payload.transport?.primary_websocket || "(empty)"}`,
      );
    }
    if (!payload.schemas || !("start_turn_message" in payload.schemas)) {
      errors.push("missing start_turn_message schema");
    }
    if (!payload.schemas || !("turn_start_response" in payload.schemas)) {
      errors.push("missing turn_start_response schema");
    }
    const traceFields = new Set(payload.trace_fields || []);
    for (const fieldName of ["session_id", "turn_id", "capability", "bot_id"]) {
      if (!traceFields.has(fieldName)) {
        errors.push(`missing trace field ${fieldName}`);
      }
    }
    if (errors.length > 0) {
      return {
        ok: false,
        error: `turn contract mismatch: ${errors.join("; ")}`,
      };
    }
    return { ok: true };
  } catch (error) {
    return {
      ok: false,
      error: `turn contract probe failed: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

export function primeUnifiedTurnContractCheck(): Promise<TurnContractCheckResult> {
  if (!turnContractCheckPromise) {
    turnContractCheckPromise = fetchTurnContractCheck();
  }
  return turnContractCheckPromise;
}

export class UnifiedWSClient {
  private ws: WebSocket | null = null;
  private onEvent: EventHandler;
  private onClose?: () => void;
  private onOpen?: () => void;
  private connectInFlight = false;
  private connectAttempt = 0;
  private reconnectAttempt = 0;
  private reconnectEnabled = true;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private permanentlyClosed = false;

  constructor(onEvent: EventHandler, onClose?: () => void, onOpen?: () => void) {
    this.onEvent = onEvent;
    this.onClose = onClose;
    this.onOpen = onOpen;
  }

  connect(): void {
    if (this.permanentlyClosed) return;
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return;
    if (this.connectInFlight) return;
    this.reconnectEnabled = true;
    this.clearReconnectTimer();
    this.connectInFlight = true;
    this.connectAttempt += 1;
    void this.connectWithContractCheck(this.connectAttempt);
  }

  private async connectWithContractCheck(connectAttempt: number): Promise<void> {
    const contractCheck = await primeUnifiedTurnContractCheck();
    if (connectAttempt !== this.connectAttempt) {
      this.connectInFlight = false;
      return;
    }
    if (!contractCheck.ok && contractCheck.error) {
      const message = `[contract-check] ${contractCheck.error}`;
      if (STRICT_CONTRACT_CHECK) {
        this.onEvent(buildLocalContractError(message));
        this.connectInFlight = false;
        return;
      }
      console.warn(message);
    }

    const url = wsUrl("/api/v1/ws");
    try {
      this.ws = new WebSocket(url);
    } catch (error) {
      this.connectInFlight = false;
      this.onEvent(
        buildLocalContractError(
          `WebSocket bootstrap failed: ${error instanceof Error ? error.message : String(error)}`,
        ),
      );
      return;
    }

    this.ws.onmessage = (ev) => {
      try {
        const event: StreamEvent = JSON.parse(ev.data);
        this.onEvent(event);
      } catch {
        console.warn("Unparseable WS message:", ev.data);
      }
    };

    this.ws.onopen = () => {
      this.connectInFlight = false;
      this.reconnectAttempt = 0;
      this.clearReconnectTimer();
      this.onOpen?.();
    };

    this.ws.onclose = () => {
      this.ws = null;
      this.connectInFlight = false;
      if (this.reconnectEnabled) {
        this.scheduleReconnect();
        return;
      }
      this.onClose?.();
    };

    this.ws.onerror = (err) => {
      console.error("WS error:", err);
    };
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) return;
    if (this.reconnectAttempt >= RECONNECT_MAX_ATTEMPTS) {
      this.reconnectEnabled = false;
      this.permanentlyClosed = true;
      this.onClose?.();
      return;
    }
    const attempt = this.reconnectAttempt + 1;
    const delay = Math.min(
      RECONNECT_MAX_DELAY_MS,
      RECONNECT_BASE_DELAY_MS * 2 ** Math.max(0, attempt - 1),
    );
    const jitter = Math.floor(delay * 0.2 * Math.random());
    this.reconnectAttempt = attempt;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.reconnectEnabled) return;
      this.connectInFlight = false;
      this.connect();
    }, delay + jitter);
  }

  send(msg: ChatMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error("WebSocket not connected");
      return;
    }
    this.ws.send(JSON.stringify(msg));
  }

  disconnect(): void {
    this.connectAttempt += 1;
    this.reconnectEnabled = false;
    this.permanentlyClosed = true;
    this.clearReconnectTimer();
    this.ws?.close();
    this.ws = null;
    this.connectInFlight = false;
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  get terminated(): boolean {
    return this.permanentlyClosed;
  }
}
