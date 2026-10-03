"use client";

import { useState, useTransition } from "react";

import { ApiError, draftTicket, fileTicket, updateTicket, type Ticket } from "@/lib/api";

export function TicketPanel({ slug, themeId }: { slug: string; themeId: number }) {
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [repo, setRepo] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  function run(action: () => Promise<Ticket>, after?: (ticket: Ticket) => void) {
    setError(null);
    startTransition(async () => {
      try {
        const result = await action();
        setTicket(result);
        after?.(result);
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : "Could not reach the API.");
      }
    });
  }

  if (ticket === null) {
    return (
      <section className="flex flex-col gap-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
        <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">Ticket</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Draft an issue for this theme, with the report count and real quotes. Nothing is filed
          until you approve it.
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            value={repo}
            onChange={(event) => setRepo(event.target.value)}
            placeholder="your-name/your-repo"
            aria-label="Repository to file into"
            className="min-w-56 flex-1 rounded-md border border-zinc-300 bg-transparent px-3 py-1.5 text-sm dark:border-zinc-700"
          />
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(
                () => draftTicket(slug, themeId, repo.trim() || null),
                (created) => {
                  setTitle(created.title);
                  setBody(created.body);
                },
              )
            }
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {busy ? "Writing…" : "Draft a ticket"}
          </button>
        </div>
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      </section>
    );
  }

  const filed = ticket.status === "filed";

  return (
    <section className="flex flex-col gap-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
          Ticket for {ticket.repo}
        </h2>
        <span className="text-xs text-zinc-500">{ticket.status}</span>
      </div>

      {ticket.duplicate_candidates.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-900 dark:bg-amber-950/30">
          <p className="font-medium">This may already be reported:</p>
          <ul className="mt-1 flex flex-col gap-1">
            {ticket.duplicate_candidates.map((candidate) => (
              <li key={candidate.number}>
                <a
                  href={candidate.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline-offset-4 hover:underline"
                >
                  #{candidate.number} {candidate.title}
                </a>{" "}
                <span className="text-zinc-500">
                  ({Math.round(candidate.similarity * 100)}% alike)
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {filed ? (
        <p className="text-sm">
          Filed as{" "}
          <a
            href={ticket.external_url ?? "#"}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium underline-offset-4 hover:underline"
          >
            issue #{ticket.external_id}
          </a>
          .
        </p>
      ) : (
        <>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            aria-label="Ticket title"
            className="rounded-md border border-zinc-300 bg-transparent px-3 py-1.5 text-sm dark:border-zinc-700"
          />
          <textarea
            value={body}
            onChange={(event) => setBody(event.target.value)}
            rows={12}
            aria-label="Ticket body"
            className="rounded-md border border-zinc-300 bg-transparent px-3 py-2 font-mono text-xs dark:border-zinc-700"
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => updateTicket(slug, ticket.id, { title, body }))}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-40 dark:border-zinc-700"
            >
              Save draft
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  await updateTicket(slug, ticket.id, { title, body });
                  return fileTicket(slug, ticket.id);
                })
              }
              className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
            >
              Approve and file on GitHub
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => updateTicket(slug, ticket.id, { status: "dismissed" }))}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-40 dark:border-zinc-700"
            >
              Dismiss
            </button>
          </div>
        </>
      )}

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
    </section>
  );
}
