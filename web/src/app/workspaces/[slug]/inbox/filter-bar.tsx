"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import type { ProductArea } from "@/lib/api";

const TYPES = ["bug", "feature_request", "question", "praise", "other"];
const SENTIMENTS = ["negative", "neutral", "positive"];
const URGENCIES = ["high", "medium", "low"];
const STATES = ["open", "closed"];
const SORTS = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "most_reactions", label: "Most reactions" },
];

const selectClass =
  "rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 text-sm dark:border-zinc-700";

export function FilterBar({ areas }: { areas: ProductArea[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("q") ?? "");

  function apply(changes: Record<string, string>) {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value === "") {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    }
    params.delete("page"); // a new filter starts at the first page
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="flex flex-col gap-3">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          apply({ q: search.trim() });
        }}
        className="flex gap-2"
      >
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search titles and text"
          aria-label="Search feedback"
          className="flex-1 rounded-md border border-zinc-300 bg-transparent px-3 py-1.5 text-sm dark:border-zinc-700"
        />
        <button
          type="submit"
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
        >
          Search
        </button>
      </form>

      <div className="flex flex-wrap items-center gap-2">
        <Select name="type" label="Type" options={TYPES} searchParams={searchParams} apply={apply} />
        <Select
          name="area"
          label="Area"
          options={areas.map((area) => area.slug)}
          searchParams={searchParams}
          apply={apply}
        />
        <Select
          name="urgency"
          label="Urgency"
          options={URGENCIES}
          searchParams={searchParams}
          apply={apply}
        />
        <Select
          name="sentiment"
          label="Sentiment"
          options={SENTIMENTS}
          searchParams={searchParams}
          apply={apply}
        />
        <Select
          name="state"
          label="State"
          options={STATES}
          searchParams={searchParams}
          apply={apply}
        />

        <select
          aria-label="Sort"
          value={searchParams.get("sort") ?? "newest"}
          onChange={(event) => apply({ sort: event.target.value })}
          className={selectClass}
        >
          {SORTS.map((sort) => (
            <option key={sort.value} value={sort.value}>
              {sort.label}
            </option>
          ))}
        </select>

        <Toggle name="untagged" label="Untagged only" searchParams={searchParams} apply={apply} />
        <Toggle
          name="include_maintainer"
          label="Include maintainers"
          searchParams={searchParams}
          apply={apply}
        />
      </div>
    </div>
  );
}

type ControlProps = {
  name: string;
  label: string;
  searchParams: URLSearchParams;
  apply: (changes: Record<string, string>) => void;
};

function Select({ name, label, options, searchParams, apply }: ControlProps & { options: string[] }) {
  return (
    <select
      aria-label={label}
      value={searchParams.get(name) ?? ""}
      onChange={(event) => apply({ [name]: event.target.value })}
      className={selectClass}
    >
      <option value="">{label}: any</option>
      {options.map((option) => (
        <option key={option} value={option}>
          {option.replace(/_/g, " ")}
        </option>
      ))}
    </select>
  );
}

function Toggle({ name, label, searchParams, apply }: ControlProps) {
  const checked = searchParams.get(name) === "true";
  return (
    <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => apply({ [name]: event.target.checked ? "true" : "" })}
        className="size-4"
      />
      {label}
    </label>
  );
}
