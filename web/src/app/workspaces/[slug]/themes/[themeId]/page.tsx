import Link from "next/link";
import { notFound } from "next/navigation";

import { getTheme, type FeedbackItem, type ThemeDetail } from "@/lib/api";

import { WeeklyBars } from "../weekly-bars";
import { ThemeActions } from "./theme-actions";

export default async function ThemePage(
  props: PageProps<"/workspaces/[slug]/themes/[themeId]">,
) {
  const { slug, themeId } = await props.params;

  let theme: ThemeDetail;
  try {
    theme = await getTheme(slug, Number(themeId));
  } catch {
    notFound();
  }

  const firstSeen = theme.first_seen_at ? formatDate(theme.first_seen_at) : "unknown";
  const lastSeen = theme.last_seen_at ? formatDate(theme.last_seen_at) : "unknown";

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-12">
      <header className="flex flex-col gap-3">
        <Link
          href={`/workspaces/${slug}/themes`}
          className="text-sm text-zinc-500 underline-offset-4 hover:underline"
        >
          ← All themes
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">{theme.name}</h1>
        {theme.summary && <p className="text-zinc-600 dark:text-zinc-400">{theme.summary}</p>}
        <p className="text-sm text-zinc-500">
          {theme.item_count} {theme.item_count === 1 ? "report" : "reports"} · first seen{" "}
          {firstSeen} · latest {lastSeen}
          {theme.growth !== null && ` · ${theme.growth.toFixed(1)}× the usual weekly rate`}
        </p>
        <ThemeActions slug={slug} theme={theme} />
      </header>

      <section className="flex flex-col gap-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
        <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
          Reports per week
        </h2>
        <WeeklyBars weeks={theme.weeks} title={`${theme.name}: reports per week`} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">
          Most typical reports
        </h2>
        {theme.items.map((item) => (
          <ItemRow key={item.id} item={item} />
        ))}
      </section>
    </main>
  );
}

function ItemRow({ item }: { item: FeedbackItem }) {
  return (
    <article className="flex flex-col gap-1 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <a
        href={item.url}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium underline-offset-4 hover:underline"
      >
        {item.title}
      </a>
      {item.tag?.summary && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">{item.tag.summary}</p>
      )}
      <p className="text-xs text-zinc-500">
        #{item.external_id} · {formatDate(item.external_created_at)} · {item.state} ·{" "}
        {item.reactions_count} reactions
      </p>
    </article>
  );
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
