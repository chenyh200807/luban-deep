import type { StreamEvent } from "@/lib/unified-ws";

export function resolveStreamEventVisibility(event: StreamEvent): "public" | "internal" {
  const metadata = (event.metadata ?? {}) as {
    visibility?: unknown;
  };
  const visibility = event.visibility ?? metadata.visibility;
  return visibility === "internal" ? "internal" : "public";
}

export function isUserVisibleStreamEvent(event: StreamEvent): boolean {
  return resolveStreamEventVisibility(event) === "public";
}

export function shouldAppendEventContent(event: StreamEvent): boolean {
  if (!isUserVisibleStreamEvent(event)) return false;
  if (event.type !== "content") return false;
  const metadata = (event.metadata ?? {}) as {
    call_id?: string;
    call_kind?: string;
  };
  if (!metadata.call_id) return true;
  return metadata.call_kind === "llm_final_response";
}
