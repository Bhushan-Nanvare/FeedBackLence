"use client";

import { useState, useTransition } from "react";

import * as api from "@/lib/api";

// ---------------------------------------------------------------------------
// Rename form — inline edit that calls PATCH /themes/{id}
// ---------------------------------------------------------------------------

export function RenameForm({
  slug,
  themeId,
  initialName,
}: {
  slug: string;
  themeId: number;
  initialName: string;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(initialName);
  const [saved, setSaved] = useState(initialName);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function submit() {
    if (!name.trim() || name.trim() === saved) {
      setEditing(false);
      setName(saved);
      return;
    }
    startTransition(async () => {
      try {
        const updated = await api.updateTheme(slug, themeId, { name: name.trim() });
        setSaved(updated.name);
        setName(updated.name);
        setEditing(false);
        setError(null);
      } catch (e) {
        setError(e instanceof api.ApiError ? e.message : "Rename failed");
      }
    });
  }

  if (!editing) {
    return (
      <span className="flex items-center gap-2">
        <span className="text-3xl font-semibold tracking-tight">{saved}</span>
        <button
          onClick={() => setEditing(true)}
          className="rounded px-2 py-0.5 text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          aria-label="Rename theme"
        >
          rename
        </button>
      </span>
    );
  }

  return (
    <span className="flex flex-col gap-1">
      <span className="flex items-center gap-2">
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
            if (e.key === "Escape") {
              setEditing(false);
              setName(saved);
            }
          }}
          className="rounded-md border border-zinc-300 px-2 py-1 text-xl font-semibold focus:outline-none focus:ring-2 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-900"
        />
        <button
          onClick={submit}
          disabled={pending}
          className="rounded-md bg-zinc-900 px-3 py-1 text-sm text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {pending ? "Saving…" : "Save"}
        </button>
        <button
          onClick={() => {
            setEditing(false);
            setName(saved);
            setError(null);
          }}
          className="text-sm text-zinc-500 hover:underline"
        >
          Cancel
        </button>
      </span>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Status toggle — ignore / restore (PATCH status)
// ---------------------------------------------------------------------------

export function StatusToggle({
  slug,
  themeId,
  initialStatus,
}: {
  slug: string;
  themeId: number;
  initialStatus: string;
}) {
  const [themeStatus, setThemeStatus] = useState(initialStatus);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const ignored = themeStatus === "ignored";

  function toggle() {
    startTransition(async () => {
      try {
        const updated = await api.updateTheme(slug, themeId, {
          status: ignored ? "open" : "ignored",
        });
        setThemeStatus(updated.status);
        setError(null);
      } catch (e) {
        setError(e instanceof api.ApiError ? e.message : "Update failed");
      }
    });
  }

  return (
    <span className="flex flex-col gap-1">
      <button
        onClick={toggle}
        disabled={pending}
        className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-50 ${
          ignored
            ? "border-emerald-300 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-700 dark:text-emerald-400 dark:hover:bg-emerald-950/30"
            : "border-zinc-300 text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
        }`}
      >
        {pending ? "…" : ignored ? "Restore theme" : "Ignore theme"}
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Draft ticket button — calls POST /themes/{id}/ticket then redirects
// ---------------------------------------------------------------------------

export function DraftTicketButton({
  slug,
  themeId,
}: {
  slug: string;
  themeId: number;
}) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function draft() {
    startTransition(async () => {
      try {
        await api.draftTicket(slug, themeId, null);
        // Redirect to themes page where they can see the ticket link
        window.location.href = `/workspaces/${slug}/themes/${themeId}`;
      } catch (e) {
        setError(e instanceof api.ApiError ? e.message : "Failed to draft ticket");
      }
    });
  }

  return (
    <span className="flex flex-col gap-1">
      <button
        onClick={draft}
        disabled={pending}
        className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
      >
        {pending ? "Drafting…" : "Draft ticket"}
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </span>
  );
}
