import { readTokenInBrowser } from "./session";

/** Where the browser sends API requests. Next.js bakes this in when building. */
const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * The address to use for this request.
 *
 * Pages are rendered on the server, which in a container cannot reach the API at
 * its public address — "localhost" there is the web container itself. API_INTERNAL_URL
 * (for example http://api:8000) is the way across the container network. Unset, as it
 * is in local development, both sides use the public address.
 */
function apiUrl(): string {
  if (typeof window === "undefined") {
    return process.env.API_INTERNAL_URL || PUBLIC_API_URL;
  }
  return PUBLIC_API_URL;
}

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

export type WorkspaceMembership = {
  slug: string;
  name: string;
  role: string;
};

export type AuthUser = {
  id: number;
  email: string;
  name: string;
  workspaces: WorkspaceMembership[];
};

export type SignInResult = {
  access_token: string;
  token_type: string;
  user_id: number;
  email: string;
  name: string;
};

export type Workspace = {
  slug: string;
  name: string;
  is_public: boolean;
  role: string;
};

export type Member = {
  email: string;
  name: string;
  role: string;
};

// ---------------------------------------------------------------------------
// AI cost tracking — mirrors backend schemas FeatureUsage, DailyUsage and
// UsageSummary.  All fields come straight from the GET /ai/usage endpoint.
// ---------------------------------------------------------------------------

/** Token and call totals for one AI feature (e.g. "tagging", "embedding", "ask"). */
export type FeatureUsage = {
  feature: string;
  total_calls: number;
  succeeded_calls: number;
  total_items: number;
  input_tokens: number;
  output_tokens: number;
  avg_latency_ms: number;
};

/** Token and call totals for one calendar day, across all features. */
export type DailyUsage = {
  date: string;
  total_calls: number;
  succeeded_calls: number;
  input_tokens: number;
  output_tokens: number;
};

/** The full response from GET /workspaces/{slug}/ai/usage. */
export type UsageSummary = {
  total_calls: number;
  succeeded_calls: number;
  total_items: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  by_feature: FeatureUsage[];
  daily: DailyUsage[];
};

/** The embed snippet and config returned by GET /widget/embed. */
export type WidgetEmbed = {
  script_url: string;
  workspace_slug: string;
  api_url: string;
  snippet: string;
  enabled: boolean;
};

/** Precision, recall and F1 for one label value (e.g. "bug"). */
export type ClassScore = {
  expected: number;
  predicted: number;
  correct: number;
  precision: number;
  recall: number;
  f1: number;
};

/** Accuracy and per-class scores for one tagging field (e.g. "type" or "area"). */
export type FieldScore = {
  compared: number;
  correct: number;
  accuracy: number;
  macro_f1: number;
  per_class: Record<string, ClassScore>;
  mistakes: (string | number)[][];
};

/** The full evaluation report from GET /workspaces/{slug}/evals. */
export type EvalReport = {
  workspace: string;
  model: string | null;
  prompt_version: string | null;
  labelled_items: number;
  checked_by_people: number;
  scored_items: number;
  skipped_corrected: number;
  fields: Record<string, FieldScore>;
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
    const response = await fetch(`${apiUrl()}/health`, { cache: "no-store" });
    // A 503 still carries a JSON body saying which dependency is down.
    return (await response.json()) as Health;
  } catch {
    return null;
  }
}

export async function register(
  email: string,
  name: string,
  password: string,
): Promise<SignInResult> {
  return request<SignInResult>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, name, password }),
  });
}

export async function signIn(email: string, password: string): Promise<SignInResult> {
  return request<SignInResult>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function getMe(token?: string | null): Promise<AuthUser> {
  return request<AuthUser>("/auth/me", undefined, token);
}

export async function createWorkspace(slug: string, name: string): Promise<Workspace> {
  return request<Workspace>("/workspaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slug, name }),
  });
}

export async function getMembers(slug: string, token?: string | null): Promise<Member[]> {
  return request<Member[]>(`/workspaces/${slug}/members`, undefined, token);
}

export async function addMember(slug: string, email: string, role: string): Promise<Member> {
  return request<Member>(`/workspaces/${slug}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, role }),
  });
}

export async function getItems(
  slug: string,
  filters: URLSearchParams,
  token?: string | null,
): Promise<ItemPage> {
  return request<ItemPage>(`/workspaces/${slug}/items?${filters.toString()}`, undefined, token);
}

export async function getProductAreas(
  slug: string,
  token?: string | null,
): Promise<ProductArea[]> {
  return request<ProductArea[]>(`/workspaces/${slug}/product-areas`, undefined, token);
}

/** Replace the workspace's product areas with a new list (PUT /product-areas). */
export async function replaceProductAreas(
  slug: string,
  areas: { slug: string; name: string; description: string }[],
): Promise<ProductArea[]> {
  return request<ProductArea[]>(`/workspaces/${slug}/product-areas`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(areas),
  });
}

/** Remove someone from a workspace (DELETE /members/{email}). */
export async function removeMember(slug: string, email: string): Promise<void> {
  await request(`/workspaces/${slug}/members/${encodeURIComponent(email)}`, {
    method: "DELETE",
  });
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

export async function getThemes(
  slug: string,
  params: URLSearchParams,
  token?: string | null,
): Promise<ThemeList> {
  return request<ThemeList>(`/workspaces/${slug}/themes?${params.toString()}`, undefined, token);
}

export async function getTheme(
  slug: string,
  themeId: number,
  token?: string | null,
): Promise<ThemeDetail> {
  return request<ThemeDetail>(`/workspaces/${slug}/themes/${themeId}`, undefined, token);
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

export async function getAlerts(
  slug: string,
  limit = 5,
  token?: string | null,
): Promise<Alert[]> {
  return request<Alert[]>(`/workspaces/${slug}/alerts?limit=${limit}`, undefined, token);
}

export async function askQuestion(slug: string, question: string): Promise<Answer> {
  return request<Answer>(`/workspaces/${slug}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

/** Fetch aggregated AI usage (tokens, calls, cost) for a workspace. */
export async function getUsage(
  slug: string,
  days = 30,
  token?: string | null,
): Promise<UsageSummary> {
  return request<UsageSummary>(`/workspaces/${slug}/ai/usage?days=${days}`, undefined, token);
}

/** Fetch the widget embed snippet for a workspace. */
export async function getWidgetEmbed(
  slug: string,
  token?: string | null,
): Promise<WidgetEmbed> {
  return request<WidgetEmbed>(`/workspaces/${slug}/widget/embed`, undefined, token);
}

/** Turn public widget submissions on or off. Owners and admins only. */
export async function setWidgetEnabled(slug: string, enabled: boolean): Promise<WidgetEmbed> {
  return request<WidgetEmbed>(`/workspaces/${slug}/widget/enable`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

/** Fetch the evaluation report (accuracy vs checked labels) for a workspace. */
export async function getEvalReport(
  slug: string,
  token?: string | null,
): Promise<EvalReport> {
  return request<EvalReport>(`/workspaces/${slug}/evals`, undefined, token);
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

/**
 * On the server the caller passes the token it read from the cookie; in the browser we read the
 * cookie here, so forms do not have to think about it.
 */
async function request<T>(path: string, init?: RequestInit, token?: string | null): Promise<T> {
  const headers = new Headers(init?.headers);
  const bearer = token ?? readTokenInBrowser();
  if (bearer) {
    headers.set("Authorization", `Bearer ${bearer}`);
  }
  const response = await fetch(`${apiUrl()}${path}`, { cache: "no-store", ...init, headers });
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
