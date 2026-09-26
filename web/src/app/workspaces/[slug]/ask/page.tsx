import Link from "next/link";

import { AskForm } from "./ask-form";

export default async function AskPage(props: PageProps<"/workspaces/[slug]/ask">) {
  const { slug } = await props.params;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-12">
      <header className="flex flex-col gap-1">
        <Link href="/" className="text-sm text-zinc-500 underline-offset-4 hover:underline">
          ← FeedbackLens
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">Ask your feedback</h1>
        <p className="text-sm text-zinc-500">
          Answers come only from reports in this workspace, and every claim points at the reports
          behind it. Workspace: {slug} ·{" "}
          <Link href={`/workspaces/${slug}/themes`} className="underline-offset-4 hover:underline">
            see the themes
          </Link>
        </p>
      </header>

      <AskForm slug={slug} />
    </main>
  );
}
