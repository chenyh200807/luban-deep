import { apiUrl } from "./api";

type SurfaceEventName =
  | "ws_connected"
  | "start_turn_sent"
  | "session_event_received"
  | "first_visible_content_rendered"
  | "done_rendered"
  | "user_cancelled"
  | "resume_attempted"
  | "resume_succeeded"
  | "surface_render_failed";

interface SurfaceEventPayload {
  eventName: SurfaceEventName;
  sessionId?: string | null;
  turnId?: string | null;
  metadata?: Record<string, unknown>;
}

const SURFACE_NAME = "web";
const sentEventKeys = new Set<string>();

function buildEventId(): string {
  const randomPart =
    typeof globalThis !== "undefined" && globalThis.crypto?.randomUUID
      ? globalThis.crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `web-${randomPart}`;
}

export async function trackWebSurfaceEvent(payload: SurfaceEventPayload): Promise<void> {
  const collectedAtMs = Date.now();
  try {
    await fetch(apiUrl("/api/v1/observability/surface-events"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      keepalive: true,
      body: JSON.stringify({
        event_id: buildEventId(),
        surface: SURFACE_NAME,
        event_name: payload.eventName,
        session_id: payload.sessionId || undefined,
        turn_id: payload.turnId || undefined,
        collected_at_ms: collectedAtMs,
        sent_at_ms: Date.now(),
        metadata: payload.metadata || {},
      }),
    });
  } catch (_) {
    // Telemetry is best-effort and must never block the main chat flow.
  }
}

export function trackWebSurfaceEventOnce(
  uniqueKey: string,
  payload: SurfaceEventPayload,
): void {
  const dedupeKey = String(uniqueKey || "").trim();
  if (!dedupeKey) {
    void trackWebSurfaceEvent(payload);
    return;
  }
  if (sentEventKeys.has(dedupeKey)) return;
  sentEventKeys.add(dedupeKey);
  void trackWebSurfaceEvent(payload);
}
