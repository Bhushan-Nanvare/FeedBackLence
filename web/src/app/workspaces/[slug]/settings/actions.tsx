"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import * as api from "@/lib/api";

// ---------------------------------------------------------------------------
// Invite member form
// ---------------------------------------------------------------------------

export function InviteForm({ slug }: { slug: string }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "member" | "viewer">("member");
  const [result, setResult] = useState<api.Member | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    startTransition(async () => {
      try {
        const member = await api.addMember(slug, email.trim(), role);
        setResult(member);
        setEmail("");
        setError(null);
        // So the new person appears in the list above without a reload.
        router.refresh();
      } catch (err) {
        setError(err instanceof api.ApiError ? err.message : "Invite failed");
        setResult(null);
      }
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="teammate@example.com"
          required
          className="min-w-0 flex-1 rounded-md border border-zinc-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-900"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as typeof role)}
          className="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900"
        >
          <option value="admin">Admin</option>
          <option value="member">Member</option>
          <option value="viewer">Viewer</option>
        </select>
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-zinc-900 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {pending ? "Inviting…" : "Invite"}
        </button>
      </div>
      {result && (
        <p className="text-sm text-emerald-600 dark:text-emerald-400">
          ✓ {result.name} ({result.email}) added as {result.role}
        </p>
      )}
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
    </form>
  );
}

// ---------------------------------------------------------------------------
// Remove member button
// ---------------------------------------------------------------------------

export function RemoveMemberButton({
  slug,
  email,
  name,
}: {
  slug: string;
  email: string;
  name: string;
}) {
  const router = useRouter();
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  if (done) {
    return <span className="text-xs text-zinc-400">Removed</span>;
  }

  function remove() {
    if (!confirm(`Remove ${name} from this workspace?`)) return;
    startTransition(async () => {
      try {
        await api.removeMember(slug, email);
        setDone(true);
        setError(null);
        router.refresh();
      } catch (err) {
        setError(err instanceof api.ApiError ? err.message : "Remove failed");
      }
    });
  }

  return (
    <span className="flex items-center gap-2">
      <button
        onClick={remove}
        disabled={pending}
        className="text-xs text-red-600 hover:underline disabled:opacity-50 dark:text-red-400"
      >
        {pending ? "…" : "Remove"}
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Product areas editor
// ---------------------------------------------------------------------------

type AreaRow = { slug: string; name: string; description: string };

export function ProductAreasEditor({
  workspaceSlug,
  initial,
}: {
  workspaceSlug: string;
  initial: api.ProductArea[];
}) {
  const [areas, setAreas] = useState<AreaRow[]>(
    initial.map((a) => ({ slug: a.slug, name: a.name, description: a.description })),
  );
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function addRow() {
    setAreas((prev) => [...prev, { slug: "", name: "", description: "" }]);
    setSaved(false);
  }

  function removeRow(i: number) {
    setAreas((prev) => prev.filter((_, idx) => idx !== i));
    setSaved(false);
  }

  function updateRow(i: number, field: keyof AreaRow, value: string) {
    setAreas((prev) => prev.map((row, idx) => (idx === i ? { ...row, [field]: value } : row)));
    setSaved(false);
  }

  function save() {
    startTransition(async () => {
      try {
        const updated = await api.replaceProductAreas(workspaceSlug, areas);
        setAreas(updated.map((a) => ({ slug: a.slug, name: a.name, description: a.description })));
        setSaved(true);
        setError(null);
      } catch (err) {
        setError(err instanceof api.ApiError ? err.message : "Save failed");
      }
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col divide-y divide-zinc-100 rounded-lg border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
        {areas.length === 0 && (
          <p className="px-4 py-3 text-sm text-zinc-500">No product areas yet. Add one below.</p>
        )}
        {areas.map((area, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 px-3 py-2">
            <input
              placeholder="slug"
              value={area.slug}
              onChange={(e) => updateRow(i, "slug", e.target.value)}
              className="w-28 rounded border border-zinc-300 px-2 py-1 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-900"
            />
            <input
              placeholder="Display name"
              value={area.name}
              onChange={(e) => updateRow(i, "name", e.target.value)}
              className="min-w-0 flex-1 rounded border border-zinc-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-900"
            />
            <input
              placeholder="Description (optional)"
              value={area.description}
              onChange={(e) => updateRow(i, "description", e.target.value)}
              className="min-w-0 flex-1 rounded border border-zinc-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-900"
            />
            <button
              onClick={() => removeRow(i)}
              className="text-xs text-red-600 hover:underline dark:text-red-400"
            >
              Remove
            </button>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={addRow}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          + Add area
        </button>
        <button
          onClick={save}
          disabled={pending}
          className="rounded-md bg-zinc-900 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {pending ? "Saving…" : "Save areas"}
        </button>
        {saved && <span className="text-sm text-emerald-600 dark:text-emerald-400">✓ Saved</span>}
        {error && <span className="text-sm text-red-600 dark:text-red-400">{error}</span>}
      </div>
    </div>
  );
}
