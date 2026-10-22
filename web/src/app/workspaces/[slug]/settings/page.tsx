import Link from "next/link";

import { LoadProblem } from "@/components/load-problem";
import type { Member, ProductArea, Workspace } from "@/lib/api";
import { currentUser, getMembers, getProductAreas } from "@/lib/api-server";

import { InviteForm, ProductAreasEditor, RemoveMemberButton } from "./actions";

async function getWorkspace(slug: string, token: string | null): Promise<Workspace | null> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/workspaces`,
      {
        cache: "no-store",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      },
    );
    if (!res.ok) return null;
    const list = (await res.json()) as Workspace[];
    return list.find((w) => w.slug === slug) ?? null;
  } catch {
    return null;
  }
}

export default async function SettingsPage(props: PageProps<"/workspaces/[slug]/settings">) {
  const { slug } = await props.params;

  const user = await currentUser();
  const token = user ? null : null; // currentUser already uses the cookie; getMembers/getProductAreas also use the cookie via api-server helpers

  let members: Member[] = [];
  let areas: ProductArea[] = [];
  let workspace: Workspace | null = null;
  let problem: unknown = null;

  try {
    [members, areas] = await Promise.all([getMembers(slug), getProductAreas(slug)]);
    // We need the workspace's own fields (name, is_public) — get from the user's membership list
    workspace = user?.workspaces.find((w) => w.slug === slug)
      ? ({ slug, name: slug, is_public: false, role: user.workspaces.find((w) => w.slug === slug)!.role } as Workspace)
      : null;
  } catch (error) {
    problem = error;
  }

  const myRole = user?.workspaces.find((w) => w.slug === slug)?.role ?? null;
  const canManage = myRole === "owner" || myRole === "admin";

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-10 px-6 py-12">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-zinc-500">
        <Link href="/" className="hover:underline">
          FeedbackLens
        </Link>
        <span>/</span>
        <Link href={`/workspaces/${slug}/themes`} className="hover:underline">
          {slug}
        </Link>
        <span>/</span>
        <span>Settings</span>
      </nav>

      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Workspace settings</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Workspace: <code className="font-mono">{slug}</code>
          {myRole && (
            <>
              {" "}· Your role:{" "}
              <span className="font-medium text-zinc-700 dark:text-zinc-300">{myRole}</span>
            </>
          )}
        </p>
      </header>

      {problem && <LoadProblem error={problem} next={`/workspaces/${slug}/settings`} />}

      {/* ── Members ── */}
      <Section title="Members">
        {members.length === 0 ? (
          <p className="text-sm text-zinc-500">No members found.</p>
        ) : (
          <div className="flex flex-col divide-y divide-zinc-100 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
            {members.map((member) => (
              <div key={member.email} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="flex min-w-0 flex-col">
                  <span className="truncate font-medium">{member.name}</span>
                  <span className="truncate text-xs text-zinc-500">{member.email}</span>
                </div>
                <div className="flex shrink-0 items-center gap-4">
                  <RoleBadge role={member.role} />
                  {canManage && member.role !== "owner" && (
                    <RemoveMemberButton slug={slug} email={member.email} name={member.name} />
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Invite form — only for owners and admins */}
        {canManage && (
          <div className="mt-4 flex flex-col gap-2">
            <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Invite someone (they must already have an account)
            </p>
            <InviteForm slug={slug} />
          </div>
        )}

        {!canManage && !user && (
          <p className="mt-2 text-sm text-zinc-500">
            <Link href="/signin" className="underline">
              Sign in
            </Link>{" "}
            to manage members.
          </p>
        )}
      </Section>

      {/* ── Product areas ── */}
      <Section title="Product areas">
        <p className="mb-3 text-sm text-zinc-500">
          Product areas let the AI classify feedback by part of the product. Each area needs a
          unique slug (used in the API) and a display name.
        </p>
        {canManage ? (
          <ProductAreasEditor workspaceSlug={slug} initial={areas} />
        ) : (
          <div className="flex flex-col divide-y divide-zinc-100 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
            {areas.length === 0 && (
              <p className="px-4 py-3 text-sm text-zinc-500">No product areas configured.</p>
            )}
            {areas.map((area) => (
              <div key={area.id} className="flex items-center gap-3 px-4 py-3">
                <code className="text-xs text-zinc-500">{area.slug}</code>
                <span className="font-medium">{area.name}</span>
                {area.description && (
                  <span className="text-sm text-zinc-500">— {area.description}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* ── Navigation shortcuts ── */}
      <Section title="Quick links">
        <ul className="flex flex-col gap-2 text-sm">
          {[
            { href: `/workspaces/${slug}/themes`, label: "Themes" },
            { href: `/workspaces/${slug}/inbox`, label: "Feedback inbox" },
            { href: `/workspaces/${slug}/import`, label: "Import" },
            { href: `/workspaces/${slug}/ask`, label: "Ask a question" },
            { href: `/workspaces/${slug}/usage`, label: "AI usage & cost" },
            { href: `/workspaces/${slug}/evals`, label: "Evaluation report" },
          ].map(({ href, label }) => (
            <li key={href}>
              <Link href={href} className="text-zinc-600 underline-offset-4 hover:underline dark:text-zinc-400">
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </Section>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">{title}</h2>
      {children}
    </section>
  );
}

const ROLE_STYLES: Record<string, string> = {
  owner: "bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-200",
  admin: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  member: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  viewer: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
};

function RoleBadge({ role }: { role: string }) {
  const style = ROLE_STYLES[role] ?? ROLE_STYLES.viewer;
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>{role}</span>
  );
}
