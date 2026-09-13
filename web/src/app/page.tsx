import { connection } from "next/server";

import { getHealth } from "@/lib/api";

export default async function Home() {
  // Status must be checked on every request, not baked in at build time.
  await connection();
  const health = await getHealth();

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
      </header>

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
