export interface CitationDisplayRef {
  marker: string;
  title: string;
  locator: string;
  publicQuote: string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/** Read the server-owned public citation projection; never infer refs from prose. */
export function extractCitationReferences(metadata: unknown): CitationDisplayRef[] {
  const root = asRecord(metadata);
  const bundle = asRecord(root?.citation_bundle);
  if (!bundle || !Array.isArray(bundle.refs)) return [];

  return bundle.refs.flatMap((value) => {
    const ref = asRecord(value);
    if (!ref || ref.visibility === "private") return [];
    const marker = String(ref.marker ?? "").trim();
    const title = String(ref.title ?? "").trim();
    const locator = String(ref.locator ?? "").trim();
    const publicQuote = String(ref.public_quote ?? "").trim();
    if (!title && !locator && !publicQuote) return [];
    return [{ marker, title, locator, publicQuote }];
  });
}
