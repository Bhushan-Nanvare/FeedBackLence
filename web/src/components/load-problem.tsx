import Link from "next/link";

import { ApiError } from "@/lib/api";

/**
 * Shown when a page could not load its data. The wording depends on why: a missing sign-in is a
 * different problem from a workspace you were never invited to, or an API that is not running.
 */
export function LoadProblem({ error, next }: { error: unknown; next?: string }) {
  const status = error instanceof ApiError ? error.status : null;

  if (status === 401) {
    return (
      <Notice>
        This workspace is private.{" "}
        <Link
          href={next ? `/signin?next=${encodeURIComponent(next)}` : "/signin"}
          className="font-medium underline underline-offset-4"
        >
          Sign in
        </Link>{" "}
        to see it.
      </Notice>
    );
  }

  if (status === 403) {
    return (
      <Notice>
        Your account is not a member of this workspace. Ask one of its owners for an invite, or{" "}
        <Link href="/" className="font-medium underline underline-offset-4">
          go to your own workspaces
        </Link>
        .
      </Notice>
    );
  }

  if (status !== null) {
    return <Notice>{error instanceof ApiError ? error.message : "Something went wrong."}</Notice>;
  }

  return (
    <Notice>
      Could not reach the API. Start it with{" "}
      <code className="font-mono">uv run uvicorn app.main:app</code> and reload.
    </Notice>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-xl border border-red-200 p-4 text-sm dark:border-red-900">{children}</p>
  );
}
