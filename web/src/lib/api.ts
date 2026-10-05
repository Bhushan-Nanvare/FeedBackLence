const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Health = {
  status: "ok" | "degraded";
  database: "ok" | "unreachable";
  pgvector: string | null;
};

export type ItemTag = {
  type: string;
  area: string;
  sentiment: string;
  urgency: string;
  confidence: number;
  summary: string;
  reviewed_by_human: boolean;
};

export type FeedbackItem = {
  id: number;
  external_id: string;
  url: string;
  title: string;
  state: string;
  state_reason: string | null;
  labels: string[];
  comments_count: number;
  reactions_count: number;
  author_is_maintainer: boolean;
  external_created_at: string;
  tag: ItemTag | null;
};

export type ItemPage = {
  total: number;
  items: FeedbackItem[];
};

export type ProductArea = {
  id: number;
  slug: string;
  name: string;
  description: string;
};

export type TagCorrection = Partial<Pick<ItemTag, "type" | "area" | "sentiment" | "urgency">>;

export type ThemeWeek = {
  week_start: string;
  item_count: number;
};

export type Theme = {
  id: number;
  name: string;
  summary: string;
  status: string;
  item_count: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
  renamed_by_human: boolean;
  weeks: ThemeWeek[];
  last_week_count: number;
  growth: number | null;
};

export type ThemeList = {
  total: number;
  themes: Theme[];
};

export type ThemeDetail = Theme & {
  items: FeedbackItem[];
};

export type Alert = {
  id: number;
  theme_id: number;
  theme_name: string;
  week_start: string;
  item_count: number;
  baseline: number;
  ratio: number;
  status: string;
  channel: string;
  created_at: string;
};

export type CsvImportResult = {
  source: { id: number; name: string; kind: string };
  created: number;
  updated: number;
  unchanged: number;
  skipped: number;
  problems: string[];
};

export type DuplicateCandidate = {
  number: number;
  title: string;
  url: string;
  similarity: number;
};

export type Ticket = {
  id: number;
  theme_id: number;
  repo: string;
  title: string;
  body: string;
  status: string;
  duplicate_candidates: DuplicateCandidate[];
  external_url: string | null;
  external_id: string | null;
  error: string | null;
  filed_at: string | null;
  created_at: string;
};

export type CitedItem = {
  number: number;
  item: FeedbackItem;
};

export type Answer = {
  question_id: number | null;
  question: string;
  answer: string;
  enough_evidence: boolean;
  considered_count: number;
  sources: CitedItem[];
  dropped_citations: number[];
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** Returns the API health report, or null when the API itself is unreachable. */
export async function getHealth(): Promise<Health | null> {
  try {
    const response = await fetch(`${API_URL}/health`, { cache: "no-store" });
    // A 503 still carries a JSON body saying which dependency is down.
    return (await response.json()) as Health;
  } catch {
    return null;
  }
}

export async function getItems(slug: string, filters: URLSearchParams): Promise<ItemPage> {
  return request<ItemPage>(`/workspaces/${slug}/items?${filters.toString()}`);
}

export async function getProductAreas(slug: string): Promise<ProductArea[]> {
  return request<ProductArea[]>(`/workspaces/${slug}/product-areas`);
}

export async function correctItemTag(
  slug: string,
  itemId: number,
  changes: TagCorrection,
): Promise<ItemTag> {
  return request<ItemTag>(`/workspaces/${slug}/items/${itemId}/tag`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
}

export async function getThemes(slug: string, params: URLSearchParams): Promise<ThemeList> {
  return request<ThemeList>(`/workspaces/${slug}/themes?${params.toString()}`);
}

export async function getTheme(slug: string, themeId: number): Promise<ThemeDetail> {
  return request<ThemeDetail>(`/workspaces/${slug}/themes/${themeId}`);
}

export async function updateTheme(
  slug: string,
  themeId: number,
  changes: { name?: string; status?: string },
): Promise<Theme> {
  return request<Theme>(`/workspaces/${slug}/themes/${themeId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
}

export async function importCsv(slug: string, file: File): Promise<CsvImportResult> {
  const form = new FormData();
  form.append("file", file);
  // No Content-Type header: the browser adds the one multipart needs.
  return request<CsvImportResult>(`/workspaces/${slug}/sources/csv`, {
    method: "POST",
    body: form,
  });
}

export async function draftTicket(
  slug: string,
  themeId: number,
  repo: string | null,
): Promise<Ticket> {
  return request<Ticket>(`/workspaces/${slug}/themes/${themeId}/ticket`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(repo ? { repo } : {}),
  });
}

export async function updateTicket(
  slug: string,
  ticketId: number,
  changes: { title?: string; body?: string; status?: string },
): Promise<Ticket> {
  return request<Ticket>(`/workspaces/${slug}/tickets/${ticketId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
}

export async function fileTicket(slug: string, ticketId: number): Promise<Ticket> {
  return request<Ticket>(`/workspaces/${slug}/tickets/${ticketId}/file`, { method: "POST" });
}

export async function getAlerts(slug: string, limit = 5): Promise<Alert[]> {
  return request<Alert[]>(`/workspaces/${slug}/alerts?limit=${limit}`);
}

export async function askQuestion(slug: string, question: string): Promise<Answer> {
  return request<Answer>(`/workspaces/${slug}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export async function rateAnswer(
  slug: string,
  questionId: number,
  helpful: boolean,
): Promise<void> {
  await request(`/workspaces/${slug}/questions/${questionId}/rating`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ helpful }),
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    throw new ApiError(await explain(response), response.status);
  }
  return (await response.json()) as T;
}

/** Use the API's own explanation when it sends one, so the page can show what is wrong. */
async function explain(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // Fall through to the status text.
  }
  return `Request failed with ${response.status}`;
}
