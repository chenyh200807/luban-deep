import { apiUrl } from "@/lib/api";
import { ApiError } from "@/lib/api-errors";
import { buildNotebookEntrySearchParams } from "@/lib/pagination-contract";

export interface NotebookEntry {
  id: number;
  session_id: string;
  session_title: string;
  question_id: string;
  question: string;
  question_type: string;
  options: Record<string, string>;
  correct_answer: string;
  explanation: string;
  difficulty: string;
  user_answer: string;
  is_correct: boolean;
  bookmarked: boolean;
  followup_session_id: string;
  created_at: number;
  updated_at: number;
  categories?: NotebookCategory[];
}

export interface NotebookEntryListCursor {
  before_created_at: number;
  before_entry_id: number;
}

export interface NotebookCategory {
  id: number;
  name: string;
  created_at: number;
  entry_count: number;
}

export interface NotebookEntryListResponse {
  items: NotebookEntry[];
  total: number;
  next_cursor?: NotebookEntryListCursor | null;
}

async function expectJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { detail?: unknown; message?: unknown };
      detail = String(payload.detail ?? payload.message ?? "").trim();
    } catch {
      detail = "";
    }
    throw new ApiError(response.status, detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

// ── Entries ──────────────────────────────────────────────────────

export async function listNotebookEntries(filter: {
  category_id?: number;
  bookmarked?: boolean;
  is_correct?: boolean;
  limit?: number;
  offset?: number;
  before_created_at?: number;
  before_entry_id?: number;
} = {}): Promise<NotebookEntryListResponse> {
  const params = buildNotebookEntrySearchParams(filter);
  const query = params.toString();
  const response = await fetch(
    apiUrl(`/api/v1/question-notebook/entries${query ? `?${query}` : ""}`),
    { cache: "no-store" },
  );
  const data = await expectJson<NotebookEntryListResponse>(response);
  return {
    items: data.items ?? [],
    total: data.total ?? 0,
    next_cursor: data.next_cursor ?? null,
  };
}

export async function getNotebookEntry(entryId: number): Promise<NotebookEntry> {
  const response = await fetch(apiUrl(`/api/v1/question-notebook/entries/${entryId}`), {
    cache: "no-store",
  });
  return expectJson<NotebookEntry>(response);
}

export async function lookupNotebookEntry(
  sessionId: string,
  questionId: string,
): Promise<NotebookEntry | null> {
  const params = new URLSearchParams({ session_id: sessionId, question_id: questionId });
  const response = await fetch(
    apiUrl(`/api/v1/question-notebook/entries/lookup/by-question?${params}`),
  );
  if (response.status === 404) return null;
  return expectJson<NotebookEntry>(response);
}

export async function updateNotebookEntry(
  entryId: number,
  updates: { bookmarked?: boolean; followup_session_id?: string },
): Promise<void> {
  const response = await fetch(apiUrl(`/api/v1/question-notebook/entries/${entryId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  await expectJson<{ updated: boolean }>(response);
}

export async function upsertNotebookEntry(data: {
  session_id: string;
  question_id: string;
  question: string;
  question_type?: string;
  options?: Record<string, string>;
  correct_answer?: string;
  explanation?: string;
  difficulty?: string;
  user_answer?: string;
  is_correct?: boolean;
}): Promise<NotebookEntry> {
  const response = await fetch(apiUrl("/api/v1/question-notebook/entries/upsert"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...data,
      options: data.options || {},
      explanation: data.explanation || "",
      difficulty: data.difficulty || "",
    }),
  });
  return expectJson<NotebookEntry>(response);
}

export async function deleteNotebookEntry(entryId: number): Promise<void> {
  const response = await fetch(apiUrl(`/api/v1/question-notebook/entries/${entryId}`), {
    method: "DELETE",
  });
  await expectJson<{ deleted: boolean }>(response);
}

// ── Entry ↔ Category ────────────────────────────────────────────

export async function addEntryToCategory(entryId: number, categoryId: number): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/v1/question-notebook/entries/${entryId}/categories`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category_id: categoryId }),
    },
  );
  await expectJson<{ added: boolean }>(response);
}

export async function removeEntryFromCategory(
  entryId: number,
  categoryId: number,
): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/v1/question-notebook/entries/${entryId}/categories/${categoryId}`),
    { method: "DELETE" },
  );
  await expectJson<{ removed: boolean }>(response);
}

// ── Categories ──────────────────────────────────────────────────

export async function listCategories(): Promise<NotebookCategory[]> {
  const response = await fetch(apiUrl("/api/v1/question-notebook/categories"), {
    cache: "no-store",
  });
  return expectJson<NotebookCategory[]>(response);
}

export async function createCategory(name: string): Promise<NotebookCategory> {
  const response = await fetch(apiUrl("/api/v1/question-notebook/categories"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return expectJson<NotebookCategory>(response);
}

export async function renameCategory(categoryId: number, name: string): Promise<void> {
  const response = await fetch(apiUrl(`/api/v1/question-notebook/categories/${categoryId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await expectJson<{ updated: boolean }>(response);
}

export async function deleteCategory(categoryId: number): Promise<void> {
  const response = await fetch(apiUrl(`/api/v1/question-notebook/categories/${categoryId}`), {
    method: "DELETE",
  });
  await expectJson<{ deleted: boolean }>(response);
}
