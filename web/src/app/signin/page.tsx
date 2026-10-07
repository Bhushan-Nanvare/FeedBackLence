import Link from "next/link";
import { redirect } from "next/navigation";

import { currentUser } from "@/lib/api-server";

import { SignInForm } from "./sign-in-form";

export default async function SignInPage(props: PageProps<"/signin">) {
  const searchParams = await props.searchParams;
  const requested = Array.isArray(searchParams.next) ? searchParams.next[0] : searchParams.next;
  // Only our own pages, so the link cannot be used to bounce someone to another site.
  const next = requested?.startsWith("/") ? requested : "/";

  if (await currentUser()) {
    redirect(next);
  }

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-8 px-6 py-24">
      <header className="flex flex-col gap-2">
        <Link href="/" className="text-sm text-zinc-500 underline-offset-4 hover:underline">
          ← FeedbackLens
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">Sign in</h1>
        <p className="text-sm text-zinc-500">
          Your own workspaces are private. The{" "}
          <Link
            href="/workspaces/demo/themes"
            className="underline underline-offset-4"
          >
            demo workspace
          </Link>{" "}
          is readable without an account.
        </p>
      </header>

      <SignInForm next={next} />
    </main>
  );
}
