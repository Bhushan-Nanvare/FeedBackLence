import Link from "next/link";

import { getThemes, type Theme } from "@/lib/api";

import { SortLinks } from "./sort-links";
import { WeeklyBars } from "./weekly-bars";

const SORTS = ["size", "growth", "recent"] as const;
type Sort = (typeof SORTS)[number];

export default async function ThemesPage(props: PageProps<"/workspaces/[slug]/themes">) {
  const { slug } = await props.params;
  const searchParams = await props.searchParams;
  const requested = Array.isArray(searchParams.sort) ? searchParams.sort[0] : searchParams.sort;
  const sort: Sort = SORTS.includes(requested as Sort) ? (requested as Sort) : "size";

  let themes: Theme[] | null = null;
  try {
    const result = await getThemes(slug, new URLSearchParams({ sort, limit: "50" }));
    themes = result.themes;
  } catch {
    themes = null;
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-12">
      <header className="flex flex-col gap-1">
        <Link href="/" className="text-sm text-zinc-500 underline-offset-4 hover:underline">
          ← FeedbackLens
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">Themes</h1>
        <p className="text-sm text-zinc-500">
          Feedback grouped by what it is about. Workspace: {slug} ·{" "}
          <Link href={`/workspaces/${slug}/inbox`} className="underline-offset-4 hover:underline">
            open the inbox
          </Link>
        </p>
      </header>

      {themes === null ? (
        <p className="rounded-xl border border-red-200 p-4 text-sm dark:border-red-900">
          Could not reach the API. Start it with{" "}
          <code className="font-mono">uv run uvicorn app.main:app</code> and reload.
        </p>
      ) : themes.length === 0 ? (
        <p className="rounded-xl border border-zinc-200 p-6 text-sm text-zinc-500 dark:border-zinc-800">
          No themes yet. Import feedback, then run the worker: grouping starts once items have
          been processed.
        </p>
      ) : (
        <>
          <SortLinks slug={slug} sort={sort} />
          <div className="flex flex-col gap-3">
            {themes.map((theme) => (
              <ThemeCard key={theme.id} slug={slug} theme={theme} />
            ))}
          </div>
        </>
      )}
    </main>
  );
}

function ThemeCard({ slug, theme }: { slug: string; theme: Theme }) {
  return (
    <article className="flex items-center justify-between gap-4 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex min-w-0 flex-col gap-1">
        <Link
          href={`/workspaces/${slug}/themes/${theme.id}`}
          className="truncate font-medium underline-offset-4 hover:underline"
        >
          {theme.name}
        </Link>
        <p className="text-xs text-zinc-500">
          {theme.item_count} {theme.item_count === 1 ? "report" : "reports"} ·{" "}
          {theme.last_week_count} in the latest week
          {theme.status === "ignored" && " · hidden"}
        </p>
      </div>
      <div className="flex items-center gap-3">
        <GrowthBadge growth={theme.growth} />
        <WeeklyBars weeks={theme.weeks} title={`${theme.name}: reports per week`} />
      </div>
    </article>
  );
}

function GrowthBadge({ growth }: { growth: number | null }) {
  if (growth === null) {
    return null;
  }
  const rising = growth >= 1.5;
  const falling = growth <= 0.5;
  const style = rising
    ? "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200"
    : falling
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
      : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";

  return (
    <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>
      {growth.toFixed(1)}× usual
    </span>
  );
}
