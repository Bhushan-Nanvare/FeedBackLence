import Link from "next/link";

import { LoadProblem } from "@/components/load-problem";
import type { ItemPage, ProductArea } from "@/lib/api";
import { getItems, getProductAreas } from "@/lib/api-server";

import { FilterBar } from "./filter-bar";
import { ItemCard } from "./item-card";

const PAGE_SIZE = 25;
const FILTER_KEYS = [
  "q",
  "type",
  "area",
  "sentiment",
  "urgency",
  "state",
  "untagged",
  "include_maintainer",
  "sort",
];

type SearchParams = Record<string, string | string[] | undefined>;

export default async function InboxPage(props: PageProps<"/workspaces/[slug]/inbox">) {
  const { slug } = await props.params;
  const searchParams = await props.searchParams;
  const page = Math.max(1, Number(single(searchParams.page) ?? "1") || 1);

  const filters = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = single(searchParams[key]);
    if (value) {
      filters.set(key, value);
    }
  }
  filters.set("limit", String(PAGE_SIZE));
  filters.set("offset", String((page - 1) * PAGE_SIZE));

  let result: { items: ItemPage; areas: ProductArea[] } | null = null;
  let problem: unknown = null;
  try {
    const [items, areas] = await Promise.all([getItems(slug, filters), getProductAreas(slug)]);
    result = { items, areas };
  } catch (error) {
    problem = error;
  }

  if (result === null) {
    return (
      <Shell slug={slug}>
        <LoadProblem error={problem} next={`/workspaces/${slug}/inbox`} />
      </Shell>
    );
  }

  const { items, areas } = result;
  const lastPage = Math.max(1, Math.ceil(items.total / PAGE_SIZE));

  return (
    <Shell slug={slug}>
      <FilterBar areas={areas} />

      <p className="text-sm text-zinc-500">
        {items.total} {items.total === 1 ? "item" : "items"}
        {items.total > 0 && ` · page ${page} of ${lastPage}`}
      </p>

      {items.items.length === 0 ? (
        <p className="rounded-xl border border-zinc-200 p-6 text-sm text-zinc-500 dark:border-zinc-800">
          No feedback matches these filters. Import issues first, or clear the filters.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {items.items.map((item) => (
            <ItemCard key={item.id} slug={slug} item={item} areas={areas} />
          ))}
        </div>
      )}

      {items.total > PAGE_SIZE && (
        <nav className="flex items-center justify-between text-sm">
          <PageLink slug={slug} searchParams={searchParams} page={page - 1} disabled={page <= 1}>
            ← Previous
          </PageLink>
          <PageLink
            slug={slug}
            searchParams={searchParams}
            page={page + 1}
            disabled={page >= lastPage}
          >
            Next →
          </PageLink>
        </nav>
      )}
    </Shell>
  );
}

function Shell({ slug, children }: { slug: string; children: React.ReactNode }) {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-12">
      <header className="flex flex-col gap-1">
        <Link href="/" className="text-sm text-zinc-500 underline-offset-4 hover:underline">
          ← FeedbackLens
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">Inbox</h1>
        <p className="text-sm text-zinc-500">
          Workspace: {slug} ·{" "}
          <Link href={`/workspaces/${slug}/import`} className="underline-offset-4 hover:underline">
            import a CSV
          </Link>
        </p>
      </header>
      {children}
    </main>
  );
}

function PageLink({
  slug,
  searchParams,
  page,
  disabled,
  children,
}: {
  slug: string;
  searchParams: SearchParams;
  page: number;
  disabled: boolean;
  children: React.ReactNode;
}) {
  if (disabled) {
    return <span className="text-zinc-400">{children}</span>;
  }

  const params = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = single(searchParams[key]);
    if (value) {
      params.set(key, value);
    }
  }
  params.set("page", String(page));

  return (
    <Link
      href={`/workspaces/${slug}/inbox?${params.toString()}`}
      className="underline-offset-4 hover:underline"
    >
      {children}
    </Link>
  );
}

function single(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}
