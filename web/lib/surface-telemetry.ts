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
  | "surface_render_failed"
  | ProductBehaviorEventName;

type ProductBehaviorEventName =
  | "module_viewed"
  | "section_viewed"
  | "section_expanded"
  | "learning_action_started"
  | "learning_action_completed"
  | "module_returned"
  | "module_exited"
  | "event_error";

interface SurfaceEventPayload {
  eventName: SurfaceEventName;
  sessionId?: string | null;
  turnId?: string | null;
  metadata?: Record<string, unknown>;
}

type ProductBehaviorPayload = {
  eventName: ProductBehaviorEventName;
  visitId?: string;
  module: string;
  action: string;
  sessionId?: string | null;
  turnId?: string | null;
  section?: string;
  objectType?: string;
  objectId?: string;
  entrySource?: string;
  referrerModule?: string;
  durationMs?: number;
  visibleMs?: number;
  result?: string;
  errorCode?: string;
  releaseId?: string;
  appVersion?: string;
  platform?: string;
  deviceModel?: string;
  networkType?: string;
};

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

export function getOrCreateWebBehaviorVisitId(): string {
  const key = "deeptutor_behavior_visit_id";
  const now = Date.now();
  const maxAgeMs = 30 * 60 * 1000;
  try {
    const storage = globalThis.window?.localStorage;
    if (!storage) return `web-visit-${buildEventId()}`;
    const raw = storage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw) as { id?: string; touchedAt?: number };
      if (parsed.id && parsed.touchedAt && now - parsed.touchedAt < maxAgeMs) {
        storage.setItem(key, JSON.stringify({ id: parsed.id, touchedAt: now }));
        return parsed.id;
      }
    }
    const id = `web-visit-${buildEventId()}`;
    storage.setItem(key, JSON.stringify({ id, touchedAt: now }));
    return id;
  } catch (_) {
    return `web-visit-${buildEventId()}`;
  }
}

export async function trackWebProductBehaviorEvent(payload: ProductBehaviorPayload): Promise<void> {
  const visitId = payload.visitId || getOrCreateWebBehaviorVisitId();
  await trackWebSurfaceEvent({
    eventName: payload.eventName,
    sessionId: payload.sessionId,
    turnId: payload.turnId,
    metadata: {
      visit_id: visitId,
      module: payload.module,
      section: payload.section || "",
      action: payload.action,
      object_type: payload.objectType || "",
      object_id: payload.objectId || "",
      entry_source: payload.entrySource || "",
      referrer_module: payload.referrerModule || "",
      duration_ms: payload.durationMs || 0,
      visible_ms: payload.visibleMs || 0,
      result: payload.result || "",
      error_code: payload.errorCode || "",
      release_id: payload.releaseId || "",
      app_version: payload.appVersion || "",
      platform: payload.platform || "web",
      device_model: payload.deviceModel || "",
      network_type: payload.networkType || "",
    },
  });
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
