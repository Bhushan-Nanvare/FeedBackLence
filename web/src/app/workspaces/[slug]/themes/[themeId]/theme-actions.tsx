"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { updateTheme, type Theme } from "@/lib/api";

export function ThemeActions({ slug, theme }: { slug: string; theme: Theme }) {
  const router = useRouter();
  const [name, setName] = useState(theme.name);
  const [saving, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function save(changes: { name?: string; status?: string }) {
    setError(null);
    startTransition(async () => {
      try {
        await updateTheme(slug, theme.id, changes);
        router.refresh();
      } catch {
        setError("Could not save");
      }
    });
  }

  const hidden = theme.status === "ignored";

  return (
    <div className="flex flex-col gap-2">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim()) {
            save({ name: name.trim() });
          }
        }}
        className="flex flex-wrap gap-2"
      >
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label="Theme name"
          className="min-w-64 flex-1 rounded-md border border-zinc-300 bg-transparent px-3 py-1.5 text-sm dark:border-zinc-700"
        />
        <button
          type="submit"
          disabled={saving || name.trim() === theme.name}
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
        >
          Rename
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={() => save({ status: hidden ? "open" : "ignored" })}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-40 dark:border-zinc-700"
        >
          {hidden ? "Show again" : "Hide theme"}
        </button>
      </form>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {theme.renamed_by_human && (
        <p className="text-xs text-zinc-500">
          Named by a person, so grouping runs will keep this name.
        </p>
      )}
    </div>
  );
}
