import Link from "next/link";
import { connection } from "next/server";

import { LoadProblem } from "@/components/load-problem";
import type { UsageSummary } from "@/lib/api";
import { getUsage } from "@/lib/api-server";

// ---------------------------------------------------------------------------
// /workspaces/[slug]/usage — AI cost tracking dashboard.
//
// This page reads from GET /workspaces/{slug}/ai/usage, which aggregates
// the ai_calls table that is already populated by the tagging, embedding
// and answering modules.  No new data is written; this is purely a read page.
// ---------------------------------------------------------------------------

export default async function UsagePage(props: PageProps<"/workspaces/[slug]/usage">) {
  const { slug } = await props.params;

  // Must be checked on every request — we are reading live data, not
  // something that can be baked in at build time.
  await connection();

  let usage: UsageSummary | null = null;
  let problem: unknown = null;
  try {
    usage = await getUsage(slug);
  } catch (error) {
    problem = error;
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-12">
      {/* -- Page header, same layout as themes/ask/inbox pages -- */}
      <header className="flex flex-col gap-1">
        <Link href="/" className="text-sm text-zinc-500 underline-offset-4 hover:underline">
          ← FeedbackLens
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">AI usage</h1>
        <p className="text-sm text-zinc-500">
          Token counts, call volume and estimated cost for this workspace. Workspace: {slug} ·{" "}
          <Link href={`/workspaces/${slug}/themes`} className="underline-offset-4 hover:underline">
            see the themes
          </Link>
        </p>
      </header>

      {/* -- Error state -- */}
      {usage === null ? (
        <LoadProblem error={problem} next={`/workspaces/${slug}/usage`} />
      ) : usage.total_calls === 0 ? (
        /* -- Empty state: no AI calls have been made yet -- */
        <p className="rounded-xl border border-zinc-200 p-6 text-sm text-zinc-500 dark:border-zinc-800">
          No AI calls recorded yet. Import feedback and run tagging to start tracking usage.
        </p>
      ) : (
        <>
          {/* -- Lifetime summary cards -- */}
          <SummaryCards usage={usage} />

          {/* -- Per-feature breakdown table -- */}
          {usage.by_feature.length > 0 && <FeatureTable features={usage.by_feature} />}

          {/* -- Daily usage bars for the last 30 days -- */}
          {usage.daily.length > 0 && <DailyChart daily={usage.daily} />}
        </>
      )}
    </main>
  );
}

// ---------------------------------------------------------------------------
// Summary cards — four key numbers at a glance.
// ---------------------------------------------------------------------------

function SummaryCards({ usage }: { usage: UsageSummary }) {
  const cards = [
    {
      label: "Total calls",
      value: usage.total_calls.toLocaleString(),
      detail: `${usage.succeeded_calls.toLocaleString()} succeeded`,
    },
    {
      label: "Items processed",
      value: usage.total_items.toLocaleString(),
      detail: "feedback items sent to AI",
    },
    {
      label: "Total tokens",
      value: formatTokens(usage.total_tokens),
      detail: `${formatTokens(usage.input_tokens)} in · ${formatTokens(usage.output_tokens)} out`,
    },
    {
      label: "Estimated cost",
      // Show the dollar sign and at least 4 decimal places so small numbers
      // don't just show "$0.00" and look broken.
      value: `$${usage.estimated_cost_usd.toFixed(4)}`,
      detail: "rough estimate, Gemini Flash-Lite pricing",
    },
  ];

  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="flex flex-col gap-1 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800"
        >
          <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            {card.label}
          </span>
          <span className="text-xl font-semibold tracking-tight">{card.value}</span>
          <span className="text-xs text-zinc-500">{card.detail}</span>
        </div>
      ))}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Per-feature breakdown table.
// ---------------------------------------------------------------------------

function FeatureTable({ features }: { features: UsageSummary["by_feature"] }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">By feature</h2>
      <div className="overflow-x-auto rounded-xl border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
              <th className="px-4 py-2">Feature</th>
              <th className="px-4 py-2 text-right">Calls</th>
              <th className="px-4 py-2 text-right">Items</th>
              <th className="px-4 py-2 text-right">Input tokens</th>
              <th className="px-4 py-2 text-right">Output tokens</th>
              <th className="px-4 py-2 text-right">Avg latency</th>
            </tr>
          </thead>
          <tbody>
            {features.map((f) => (
              <tr
                key={f.feature}
                className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50"
              >
                {/* Feature name — capitalise the first letter for readability */}
                <td className="px-4 py-2 font-medium">
                  {f.feature.charAt(0).toUpperCase() + f.feature.slice(1)}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {f.total_calls.toLocaleString()}
                  {/* Show failed count only when there are failures */}
                  {f.total_calls !== f.succeeded_calls && (
                    <span className="ml-1 text-xs text-red-500">
                      ({f.total_calls - f.succeeded_calls} failed)
                    </span>
                  )}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {f.total_items.toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {formatTokens(f.input_tokens)}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {formatTokens(f.output_tokens)}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {f.avg_latency_ms > 0 ? `${Math.round(f.avg_latency_ms)} ms` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Daily usage — a simple horizontal bar chart built with plain HTML.
//
// Each row is one calendar day.  The bar width is proportional to the
// day's total tokens relative to the busiest day.  Days with zero calls
// are omitted by the backend, so the list may have gaps.
// ---------------------------------------------------------------------------

function DailyChart({ daily }: { daily: UsageSummary["daily"] }) {
  // The busiest day sets the 100% width for the bars.
  const maxTokens = Math.max(...daily.map((d) => d.input_tokens + d.output_tokens), 1);

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
        Daily usage (last 30 days)
      </h2>
      <div className="flex flex-col gap-1 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
        {daily.map((d) => {
          const dayTokens = d.input_tokens + d.output_tokens;
          // Width as a percentage of the busiest day, with a minimum of 2%
          // so that even a tiny day is still visible as a sliver.
          const pct = Math.max((dayTokens / maxTokens) * 100, dayTokens > 0 ? 2 : 0);
          return (
            <div key={d.date} className="flex items-center gap-3">
              {/* Date label — fixed width so the bars line up */}
              <span className="w-24 shrink-0 text-xs font-mono text-zinc-500">{d.date}</span>
              {/* The bar itself */}
              <div className="relative h-5 flex-1">
                <div
                  className="absolute inset-y-0 left-0 rounded bg-zinc-800 dark:bg-zinc-300"
                  style={{ width: `${pct}%` }}
                />
              </div>
              {/* Token count to the right of the bar */}
              <span className="w-20 shrink-0 text-right text-xs font-mono text-zinc-500">
                {formatTokens(dayTokens)}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a token count for display.  Large numbers get shortened to "12.3k"
 * or "1.2M" so the cards and table stay compact.
 */
function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString();
}
