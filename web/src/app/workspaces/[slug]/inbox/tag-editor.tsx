"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { correctItemTag, type ItemTag, type ProductArea } from "@/lib/api";

const TYPES = ["bug", "feature_request", "question", "praise", "other"];

export function TagEditor({
  slug,
  itemId,
  tag,
  areas,
}: {
  slug: string;
  itemId: number;
  tag: ItemTag | null;
  areas: ProductArea[];
}) {
  const router = useRouter();
  const [saving, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function correct(changes: { type?: string; area?: string }) {
    setError(null);
    startTransition(async () => {
      try {
        await correctItemTag(slug, itemId, changes);
        router.refresh();
      } catch {
        setError("Could not save");
      }
    });
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="text-zinc-500">Correct:</span>
      <select
        aria-label="Correct type"
        value={tag?.type ?? ""}
        disabled={saving}
        onChange={(event) => correct({ type: event.target.value })}
        className="rounded border border-zinc-300 bg-transparent px-1.5 py-1 dark:border-zinc-700"
      >
        <option value="" disabled>
          type
        </option>
        {TYPES.map((type) => (
          <option key={type} value={type}>
            {type.replace(/_/g, " ")}
          </option>
        ))}
      </select>
      <select
        aria-label="Correct area"
        value={tag?.area ?? ""}
        disabled={saving}
        onChange={(event) => correct({ area: event.target.value })}
        className="rounded border border-zinc-300 bg-transparent px-1.5 py-1 dark:border-zinc-700"
      >
        <option value="" disabled>
          area
        </option>
        {areas.map((area) => (
          <option key={area.slug} value={area.slug}>
            {area.slug}
          </option>
        ))}
        <option value="other">other</option>
      </select>
      {saving && <span className="text-zinc-500">saving…</span>}
      {error && <span className="text-red-600 dark:text-red-400">{error}</span>}
    </div>
  );
}
