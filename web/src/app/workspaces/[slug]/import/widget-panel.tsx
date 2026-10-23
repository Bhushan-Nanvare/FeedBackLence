"use client";

import { useState } from "react";

import { ApiError, setWidgetEnabled, type WidgetEmbed } from "@/lib/api";

export function WidgetPanel({ slug, embed }: { slug: string; embed: WidgetEmbed }) {
  const [enabled, setEnabled] = useState(embed.enabled);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      const updated = await setWidgetEnabled(slug, !enabled);
      setEnabled(updated.enabled);
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Could not reach the API.");
    }
    setBusy(false);
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(embed.snippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy — select the snippet and copy it by hand.");
    }
  }

  return (
    <section className="flex flex-col gap-3 rounded-xl border border-zinc-200 p-4 text-sm dark:border-zinc-800">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-medium">Embeddable feedback widget</h2>
        <span className="flex items-center gap-3">
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              enabled
                ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
                : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
            }`}
          >
            {enabled ? "on" : "off"}
          </span>
          <button
            type="button"
            onClick={toggle}
            disabled={busy}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-50 dark:border-zinc-700"
          >
            {busy ? "Saving…" : enabled ? "Turn off" : "Turn on"}
          </button>
        </span>
      </div>

      <p className="text-zinc-600 dark:text-zinc-400">
        Paste this snippet into your website&apos;s HTML to show a floating
        &quot;Feedback&quot; button. Visitors can submit without signing in — emails and phone
        numbers are scrubbed automatically.
      </p>

      {!enabled && (
        <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          The widget is off, so submissions are refused. Turn it on when the snippet is live on
          your site. Feedback already collected is kept either way.
        </p>
      )}

      <pre className="overflow-x-auto rounded-lg border border-zinc-200 bg-zinc-50 p-3 font-mono text-xs dark:border-zinc-700 dark:bg-zinc-900">
        {embed.snippet}
      </pre>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={copy}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700"
        >
          {copied ? "Copied" : "Copy snippet"}
        </button>
        <span className="text-xs text-zinc-500">Workspace: {embed.workspace_slug}</span>
      </div>

      {error && <p className="text-red-600 dark:text-red-400">{error}</p>}
    </section>
  );
}
