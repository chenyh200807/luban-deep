export function buildSessionPageSearchParams(
  limit: number,
  offset = 0,
  options?: { before_updated_at?: number; before_session_id?: string },
): URLSearchParams {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (options?.before_updated_at !== undefined) {
    params.set("before_updated_at", String(options.before_updated_at));
  }
  if (options?.before_session_id) {
    params.set("before_session_id", options.before_session_id);
  }
  return params;
}

export function buildNotebookEntrySearchParams(filter: {
  category_id?: number;
  bookmarked?: boolean;
  is_correct?: boolean;
  limit?: number;
  offset?: number;
  before_created_at?: number;
  before_entry_id?: number;
} = {}): URLSearchParams {
  const params = new URLSearchParams();
  if (filter.category_id !== undefined) params.set("category_id", String(filter.category_id));
  if (filter.bookmarked !== undefined) params.set("bookmarked", String(filter.bookmarked));
  if (filter.is_correct !== undefined) params.set("is_correct", String(filter.is_correct));
  if (filter.limit !== undefined) params.set("limit", String(filter.limit));
  if (filter.offset !== undefined) params.set("offset", String(filter.offset));
  if (filter.before_created_at !== undefined) {
    params.set("before_created_at", String(filter.before_created_at));
  }
  if (filter.before_entry_id !== undefined) {
    params.set("before_entry_id", String(filter.before_entry_id));
  }
  return params;
}
