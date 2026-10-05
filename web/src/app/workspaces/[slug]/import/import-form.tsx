"use client";

import Link from "next/link";
import { useRef, useState, useTransition } from "react";

import { ApiError, importCsv, type CsvImportResult } from "@/lib/api";

export function ImportForm({ slug }: { slug: string }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<CsvImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, startTransition] = useTransition();

  function upload() {
    if (!file) {
      return;
    }
    setError(null);
    setResult(null);
    startTransition(async () => {
      try {
        setResult(await importCsv(slug, file));
        setFile(null);
        if (input.current) {
          input.current.value = "";
        }
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : "Could not reach the API.");
      }
    });
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={input}
          type="file"
          accept=".csv,text/csv"
          aria-label="CSV file"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="flex-1 text-sm file:mr-3 file:rounded-md file:border file:border-zinc-300 file:bg-transparent file:px-3 file:py-1.5 file:text-sm dark:file:border-zinc-700"
        />
        <button
          type="button"
          disabled={!file || uploading}
          onClick={upload}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {uploading ? "Reading…" : "Import"}
        </button>
      </div>

      {error && (
        <p className="rounded-xl border border-red-200 p-4 text-sm dark:border-red-900">{error}</p>
      )}

      {result && (
        <div className="flex flex-col gap-2 rounded-xl border border-zinc-200 p-4 text-sm dark:border-zinc-800">
          <p>
            <strong>{result.created} new</strong>, {result.updated} updated,{" "}
            {result.unchanged} unchanged, {result.skipped} skipped from{" "}
            {result.source.name}.
          </p>
          {result.problems.length > 0 && (
            <ul className="flex list-disc flex-col gap-1 pl-5 text-zinc-600 dark:text-zinc-400">
              {result.problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          )}
          {result.created + result.updated > 0 && (
            <p className="text-zinc-600 dark:text-zinc-400">
              Run the worker to tag and group the new feedback, then open the{" "}
              <Link
                href={`/workspaces/${slug}/inbox`}
                className="underline-offset-4 hover:underline"
              >
                inbox
              </Link>
              .
            </p>
          )}
        </div>
      )}
    </section>
  );
}
