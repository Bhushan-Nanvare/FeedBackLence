import type { FeedbackItem, ProductArea } from "@/lib/api";

import { TagEditor } from "./tag-editor";

const TYPE_STYLES: Record<string, string> = {
  bug: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  feature_request: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  question: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  praise: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  other: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

const URGENCY_STYLES: Record<string, string> = {
  high: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  low: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

export function ItemCard({
  slug,
  item,
  areas,
}: {
  slug: string;
  item: FeedbackItem;
  areas: ProductArea[];
}) {
  const created = new Date(item.external_created_at).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <article className="flex flex-col gap-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex flex-col gap-1">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium underline-offset-4 hover:underline"
        >
          {item.title}
        </a>
        {item.tag ? (
          <p className="text-sm text-zinc-600 dark:text-zinc-400">{item.tag.summary}</p>
        ) : (
          <p className="text-sm italic text-zinc-500">Not tagged yet</p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        {item.tag && (
          <>
            <Chip className={TYPE_STYLES[item.tag.type] ?? TYPE_STYLES.other}>
              {item.tag.type.replace(/_/g, " ")}
            </Chip>
            <Chip className="bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
              {item.tag.area}
            </Chip>
            <Chip className={URGENCY_STYLES[item.tag.urgency] ?? URGENCY_STYLES.low}>
              {item.tag.urgency} urgency
            </Chip>
            <Chip className="bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
              {item.tag.sentiment}
            </Chip>
            {item.tag.reviewed_by_human && (
              <Chip className="bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-200">
                corrected by a person
              </Chip>
            )}
          </>
        )}
        {item.author_is_maintainer && (
          <Chip className="bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
            maintainer
          </Chip>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-zinc-500">
        <span>
          #{item.external_id} · {created} · {item.state}
          {item.state_reason ? ` (${item.state_reason})` : ""} · {item.reactions_count} reactions ·{" "}
          {item.comments_count} comments
        </span>
        <TagEditor slug={slug} itemId={item.id} tag={item.tag} areas={areas} />
      </div>
    </article>
  );
}

function Chip({ children, className }: { children: React.ReactNode; className: string }) {
  return <span className={`rounded-full px-2 py-0.5 font-medium ${className}`}>{children}</span>;
}
