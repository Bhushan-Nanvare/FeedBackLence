import Link from "next/link";

import { currentUser } from "@/lib/api-server";

import { SignOutButton } from "./sign-out-button";

export async function TopBar() {
  const user = await currentUser();

  return (
    <header className="border-b border-zinc-200 dark:border-zinc-800">
      <nav className="mx-auto flex w-full max-w-3xl items-center justify-between gap-4 px-6 py-3 text-sm">
        <Link href="/" className="font-medium underline-offset-4 hover:underline">
          FeedbackLens
        </Link>
        {user ? (
          <span className="flex items-center gap-4 text-zinc-500">
            <span className="truncate">{user.email}</span>
            <SignOutButton />
          </span>
        ) : (
          <Link href="/signin" className="text-zinc-500 underline-offset-4 hover:underline">
            Sign in
          </Link>
        )}
      </nav>
    </header>
  );
}
