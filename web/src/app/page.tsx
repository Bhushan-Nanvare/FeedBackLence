import Link from "next/link";
import { connection } from "next/server";

import { getHealth, type AuthUser } from "@/lib/api";
import { currentUser } from "@/lib/api-server";

import { NewWorkspace } from "./new-workspace";

export default async function Home() {
  // Status must be checked on every request, not baked in at build time.
  await connection();
  const [health, user] = await Promise.all([getHealth(), currentUser()]);

  const checks = [
    {
      label: "API",
      ok: health !== null,
      detail: health ? "reachable" : "not reachable",
    },
    {
      label: "Database",
      ok: health?.database === "ok",
      detail: health?.database ?? "unknown",
    },
    {
      label: "pgvector",
      ok: Boolean(health?.pgvector),
      detail:
        health?.database !== "ok"
          ? "unknown"
          : health.pgvector
            ? `v${health.pgvector}`
            : "not installed",
    },
  ];

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-10 px-6 py-24">
      <header className="flex flex-col gap-3">
        <h1 className="text-4xl font-semibold tracking-tight">FeedbackLens</h1>
        <p className="text-lg text-zinc-600 dark:text-zinc-400">
          Collects user feedback from everywhere, groups it into themes, spots problems that are
          growing and turns the biggest ones into tickets backed by real quotes.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/workspaces/demo/themes"
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
          >
            See the demo themes
          </Link>
          <Link
            href="/workspaces/demo/ask"
            className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium dark:border-zinc-700"
          >
            Ask a question
          </Link>
          {user === null && (
            <Link
              href="/signin"
              className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium dark:border-zinc-700"
            >
              Sign in
            </Link>
          )}
        </div>
      </header>

      {user !== null && <YourWorkspaces user={user} />}

      <section
        aria-labelledby="status-heading"
        className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800"
      >
        <h2
          id="status-heading"
          className="text-sm font-medium uppercase tracking-wide text-zinc-500"
        >
          System status
        </h2>
        <ul className="mt-4 flex flex-col gap-3">
          {checks.map((check) => (
            <li key={check.label} className="flex items-center justify-between">
              <span className="flex items-center gap-3">
                <span
                  aria-hidden
                  className={`size-2.5 rounded-full ${check.ok ? "bg-emerald-500" : "bg-red-500"}`}
                />
                {check.label}
              </span>
              <span className="font-mono text-sm text-zinc-500">{check.detail}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}

function YourWorkspaces({ user }: { user: AuthUser }) {
  return (
    <section
      aria-labelledby="workspaces-heading"
      className="flex flex-col gap-4 rounded-xl border border-zinc-200 p-6 dark:border-zinc-800"
    >
      <h2
        id="workspaces-heading"
        className="text-sm font-medium uppercase tracking-wide text-zinc-500"
      >
        Your workspaces
      </h2>
      {user.workspaces.length === 0 ? (
        <p className="text-sm text-zinc-500">
          You are not in a workspace yet. Make one, or ask someone to invite you to theirs.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {user.workspaces.map((workspace) => (
            <li key={workspace.slug} className="flex items-center justify-between gap-4">
              <Link
                href={`/workspaces/${workspace.slug}/themes`}
                className="truncate font-medium underline-offset-4 hover:underline"
              >
                {workspace.name}
              </Link>
              <span className="flex items-center gap-3 text-sm text-zinc-500">
                <span className="font-mono text-xs">{workspace.role}</span>
                <Link
                  href={`/workspaces/${workspace.slug}/inbox`}
                  className="underline-offset-4 hover:underline"
                >
                  inbox
                </Link>
                <Link
                  href={`/workspaces/${workspace.slug}/import`}
                  className="underline-offset-4 hover:underline"
                >
                  import
                </Link>
                <Link
                  href={`/workspaces/${workspace.slug}/usage`}
                  className="underline-offset-4 hover:underline"
                >
                  usage
                </Link>
                <Link
                  href={`/workspaces/${workspace.slug}/evals`}
                  className="underline-offset-4 hover:underline"
                >
                  evals
                </Link>
              </span>
            </li>
          ))}
        </ul>
      )}
      <NewWorkspace />
    </section>
  );
}
