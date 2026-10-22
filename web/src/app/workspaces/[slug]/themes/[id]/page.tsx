import Link from "next/link";

import { LoadProblem } from "@/components/load-problem";
import type { ThemeDetail } from "@/lib/api";
import { getTheme } from "@/lib/api-server";

import { DraftTicketButton, RenameForm, StatusToggle } from "./actions";

export default async function ThemeDetailPage(
  props: PageProps<"/workspaces/[slug]/themes/[id]">,
) {
  const { slug, id } = await props.params;
  const themeId = Number(id);

  let theme: ThemeDetail | null = null;
  let problem: unknown = null;

  try {
    theme = await getTheme(slug, themeId);
  } catch (error) {
    problem = error;
  }

  if (theme === null) {
    return (
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-12">
        <Link href={`/workspaces/${slug}/themes`} className="text-sm text-zinc-500 hover:underline">
          ← Back to themes
        </Link>
        <LoadProblem error={problem} next={`/workspaces/${slug}/themes/${themeId}`} />
      </main>
    );
  }

  const totalWeeks = theme.weeks.length;
  const maxCount = Math.max(...theme.weeks.map((w) => w.item_count), 1);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-12">
      {/* ── Breadcrumb ── */}
      <Link
        href={`/workspaces/${slug}/themes`}
        className="text-sm text-zinc-500 underline-offset-4 hover:underline"
      >
        ← Themes
      </Link>

      {/* ── Header ── */}
      <header className="flex flex-col gap-3">
        <RenameForm slug={slug} themeId={theme.id} initialName={theme.name} />

        {theme.summary && (
          <p className="text-zinc-600 dark:text-zinc-400">{theme.summary}</p>
        )}

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-zinc-500">
          <span>
            <strong className="text-zinc-800 dark:text-zinc-200">{theme.item_count}</strong>{" "}
            {theme.item_count === 1 ? "report" : "reports"} total
          </span>
          <span>
            <strong className="text-zinc-800 dark:text-zinc-200">{theme.last_week_count}</strong>{" "}
            in the latest week
          </span>
          {theme.growth !== null && (
            <GrowthBadge growth={theme.growth} />
          )}
          {theme.first_seen_at && (
            <span>First seen {new Date(theme.first_seen_at).toLocaleDateString()}</span>
          )}
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2 pt-1">
          <StatusToggle slug={slug} themeId={theme.id} initialStatus={theme.status} />
          <DraftTicketButton slug={slug} themeId={theme.id} />
        </div>
      </header>

      {/* ── Weekly sparkline ── */}
      {totalWeeks > 0 && (
        <section aria-labelledby="trend-heading">
          <h2
            id="trend-heading"
            className="mb-3 text-sm font-medium uppercase tracking-wide text-zinc-500"
          >
            Weekly trend
          </h2>
          <div
            className="flex h-20 items-end gap-1"
            role="img"
            aria-label={`Weekly report counts for ${theme.name}`}
          >
            {theme.weeks.map((week) => {
              const height = maxCount > 0 ? Math.round((week.item_count / maxCount) * 100) : 0;
              return (
                <div
                  key={week.week_start}
                  title={`${week.week_start}: ${week.item_count}`}
                  className="flex-1 rounded-sm bg-zinc-800 dark:bg-zinc-200"
                  style={{ height: `${height}%`, minHeight: week.item_count > 0 ? "2px" : "0" }}
                />
              );
            })}
          </div>
          <div className="mt-1 flex justify-between text-xs text-zinc-400">
            {totalWeeks > 1 && (
              <>
                <span>{theme.weeks[0].week_start}</span>
                <span>{theme.weeks[totalWeeks - 1].week_start}</span>
              </>
            )}
          </div>
        </section>
      )}

      {/* ── Feedback items ── */}
      <section aria-labelledby="items-heading">
        <h2
          id="items-heading"
          className="mb-3 text-sm font-medium uppercase tracking-wide text-zinc-500"
        >
          Top feedback items
        </h2>

        {theme.items.length === 0 ? (
          <p className="rounded-xl border border-zinc-200 p-6 text-sm text-zinc-500 dark:border-zinc-800">
            No items assigned to this theme yet.
          </p>
        ) : (
          <div className="flex flex-col divide-y divide-zinc-100 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
            {theme.items.map((item) => (
              <article key={item.id} className="flex flex-col gap-1 px-4 py-3">
                <div className="flex items-start justify-between gap-4">
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    {item.title}
                  </a>
                  {item.reactions_count > 0 && (
                    <span className="shrink-0 text-xs text-zinc-500">
                      👍 {item.reactions_count}
                    </span>
                  )}
                </div>
                {item.tag && (
                  <div className="flex flex-wrap gap-1">
                    <Tag label={item.tag.type} />
                    {item.tag.area && item.tag.area !== "__other__" && (
                      <Tag label={item.tag.area} />
                    )}
                    <Tag label={item.tag.sentiment} />
                    {item.tag.urgency && item.tag.urgency !== "low" && (
                      <Tag label={item.tag.urgency} variant="urgent" />
                    )}
                  </div>
                )}
                <p className="text-xs text-zinc-500">
                  {new Date(item.external_created_at).toLocaleDateString()}
                  {item.tag?.summary && ` · ${item.tag.summary}`}
                </p>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function GrowthBadge({ growth }: { growth: number }) {
  const rising = growth >= 1.5;
  const falling = growth <= 0.5;
  const style = rising
    ? "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200"
    : falling
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
      : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>
      {growth.toFixed(1)}× usual
    </span>
  );
}

function Tag({
  label,
  variant = "default",
}: {
  label: string;
  variant?: "default" | "urgent";
}) {
  const style =
    variant === "urgent"
      ? "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300"
      : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400";
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs ${style}`}>{label}</span>
  );
}
