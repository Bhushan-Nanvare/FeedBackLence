import Link from "next/link";

import { ImportForm } from "./import-form";

export default async function ImportPage(props: PageProps<"/workspaces/[slug]/import">) {
  const { slug } = await props.params;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-12">
      <header className="flex flex-col gap-1">
        <Link href="/" className="text-sm text-zinc-500 underline-offset-4 hover:underline">
          ← FeedbackLens
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">Import a CSV</h1>
        <p className="text-sm text-zinc-500">
          Bring feedback from a support tool or spreadsheet into workspace {slug}.
        </p>
      </header>

      <ImportForm slug={slug} />

      <section className="flex flex-col gap-2 rounded-xl border border-zinc-200 p-4 text-sm dark:border-zinc-800">
        <h2 className="font-medium">What the file needs</h2>
        <ul className="flex list-disc flex-col gap-1 pl-5 text-zinc-600 dark:text-zinc-400">
          <li>
            One column with the feedback itself, named{" "}
            <code className="font-mono">text</code>, <code className="font-mono">body</code>,{" "}
            <code className="font-mono">description</code>,{" "}
            <code className="font-mono">feedback</code>, <code className="font-mono">comment</code>{" "}
            or <code className="font-mono">message</code>.
          </li>
          <li>
            Optional: a title (<code className="font-mono">title</code> or{" "}
            <code className="font-mono">subject</code>), a date (
            <code className="font-mono">created_at</code> or{" "}
            <code className="font-mono">date</code>), an id, a link and an author. Column names
            ignore case and spacing.
          </li>
          <li>Rows without text are skipped and listed back to you.</li>
          <li>
            Re-uploading the same file updates what changed instead of creating duplicates.
          </li>
          <li>
            <strong>Email addresses and phone numbers are removed</strong> before anything is
            stored, so they never reach an AI model.
          </li>
        </ul>
      </section>
    </main>
  );
}
