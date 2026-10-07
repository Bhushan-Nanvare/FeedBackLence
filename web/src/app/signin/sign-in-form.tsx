"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, register, signIn } from "@/lib/api";
import { storeToken } from "@/lib/session";

const INPUT =
  "rounded-md border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700";

export function SignInForm({ next }: { next: string }) {
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = creating
        ? await register(email, name, password)
        : await signIn(email, password);
      storeToken(result.access_token);
      // The pages read the cookie on the server, so the new one has to be picked up.
      router.replace(next);
      router.refresh();
    } catch (problem) {
      setError(
        problem instanceof ApiError ? problem.message : "Could not reach the API. Is it running?",
      );
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm">
        Email
        <input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className={INPUT}
        />
      </label>

      {creating && (
        <label className="flex flex-col gap-1 text-sm">
          Your name
          <input
            required
            autoComplete="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className={INPUT}
          />
        </label>
      )}

      <label className="flex flex-col gap-1 text-sm">
        Password
        <input
          type="password"
          required
          minLength={creating ? 8 : undefined}
          autoComplete={creating ? "new-password" : "current-password"}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={INPUT}
        />
        {creating && <span className="text-xs text-zinc-500">At least 8 characters.</span>}
      </label>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={busy}
        className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
      >
        {busy ? "Working…" : creating ? "Create account" : "Sign in"}
      </button>

      <button
        type="button"
        onClick={() => {
          setCreating(!creating);
          setError(null);
        }}
        className="self-start text-sm text-zinc-500 underline-offset-4 hover:underline"
      >
        {creating ? "I already have an account" : "Create an account instead"}
      </button>
    </form>
  );
}
