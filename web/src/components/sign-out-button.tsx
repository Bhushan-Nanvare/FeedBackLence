"use client";

import { useRouter } from "next/navigation";

import { clearToken } from "@/lib/session";

export function SignOutButton() {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={() => {
        clearToken();
        router.replace("/");
        router.refresh();
      }}
      className="underline-offset-4 hover:underline"
    >
      Sign out
    </button>
  );
}
