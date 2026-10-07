"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, createWorkspace } from "@/lib/api";

export function NewWorkspace() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="self-start text-sm text-zinc-500 underline-offset-4 hover:underline"
      >
        + New workspace
      </button>
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await createWorkspace(slug, name);
      // Straight to importing, because an empty workspace has nothing to show.
      router.push(`/workspaces/${created.slug}/import`);
      router.refresh();
    } catch (problem) {
      setError(
        problem instanceof ApiError ? problem.message : "Could not reach the API. Is it running?",
      );
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 text-sm">
      <div className="flex flex-wrap gap-2">
        <input
          required
          pattern="[a-z0-9][a-z0-9-]{1,63}"
          placeholder="short-name"
          aria-label="Workspace address"
          value={slug}
          onChange={(event) => setSlug(event.target.value)}
          className="w-40 rounded-md border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700"
        />
        <input
          required
          placeholder="Workspace name"
          aria-label="Workspace name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="flex-1 rounded-md border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-zinc-900 px-4 py-2 font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {busy ? "Creating…" : "Create"}
        </button>
      </div>
      <p className="text-xs text-zinc-500">
        The short name becomes the address: /workspaces/{slug || "short-name"}/themes
      </p>
      {error && <p className="text-red-600 dark:text-red-400">{error}</p>}
    </form>
  );
}
