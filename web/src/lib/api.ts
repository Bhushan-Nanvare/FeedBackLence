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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    throw new Error(`Request to ${path} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}
