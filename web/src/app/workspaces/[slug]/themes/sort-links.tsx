import Link from "next/link";

const OPTIONS = [
  { value: "size", label: "Most reports" },
  { value: "growth", label: "Growing fastest" },
  { value: "recent", label: "Most recent" },
];

export function SortLinks({ slug, sort }: { slug: string; sort: string }) {
  return (
    <nav className="flex flex-wrap gap-2 text-sm">
      {OPTIONS.map((option) => (
        <Link
          key={option.value}
          href={`/workspaces/${slug}/themes?sort=${option.value}`}
          className={`rounded-md px-3 py-1.5 ${
            option.value === sort
              ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
              : "border border-zinc-300 dark:border-zinc-700"
          }`}
        >
          {option.label}
        </Link>
      ))}
    </nav>
  );
}
