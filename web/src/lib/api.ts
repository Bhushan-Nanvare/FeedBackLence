const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Health = {
  status: "ok" | "degraded";
  database: "ok" | "unreachable";
  pgvector: string | null;
};

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
