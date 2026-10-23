import Link from "next/link";

import { LoadProblem } from "@/components/load-problem";
import type { EvalReport, FieldScore } from "@/lib/api";
import { getEvalReport } from "@/lib/api-server";

export default async function EvalsPage(props: PageProps<"/workspaces/[slug]/evals">) {
  const { slug } = await props.params;

  let report: EvalReport | null = null;
  let problem: unknown = null;
  try {
    report = await getEvalReport(slug);
  } catch (error) {
    problem = error;
  }

  if (report === null) {
    return (
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-12">
        <Link href="/" className="text-sm text-zinc-500 underline-offset-4 hover:underline">
          ← FeedbackLens
        </Link>
        <LoadProblem error={problem} next={`/workspaces/${slug}/evals`} />
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-1">
        <Link href="/" className="text-sm text-zinc-500 underline-offset-4 hover:underline">
          ← FeedbackLens
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">Tagging accuracy</h1>
        <p className="text-sm text-zinc-500">
          How well do AI-generated tags match the human-checked labels in workspace{" "}
          <strong>{slug}</strong>.
        </p>
      </header>

      {/* ---- Summary cards ---- */}
      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <SummaryCard label="Checked labels" value={report.labelled_items} />
        <SummaryCard label="By people" value={report.checked_by_people} />
        <SummaryCard label="Scored items" value={report.scored_items} />
        <SummaryCard label="Skipped (corrected)" value={report.skipped_corrected} />
      </section>

      {report.model && (
        <p className="text-xs text-zinc-500">
          Model: <strong>{report.model}</strong> · Prompt version:{" "}
          <strong>{report.prompt_version ?? "n/a"}</strong>
        </p>
      )}

      {/* ---- One section per field (type, area) ---- */}
      {Object.entries(report.fields).map(([name, field]) => (
        <FieldSection key={name} name={name} field={field} />
      ))}

      {report.scored_items === 0 && (
        <div className="rounded-xl border border-zinc-200 p-6 text-center text-sm text-zinc-500 dark:border-zinc-800">
          <p className="mb-2 text-lg font-medium text-zinc-700 dark:text-zinc-300">
            No items scored yet
          </p>
          {report.labelled_items === 0 ? (
            <p>
              There is nothing to score against. Run{" "}
              <Command>python -m app.evals build --workspace {slug}</Command> to draft checked
              labels from the source labels, then review them in the inbox.
            </p>
          ) : (
            <p>
              There are {report.labelled_items.toLocaleString()} checked labels, but no AI tags to
              compare them with yet. Set <Command>GEMINI_API_KEY</Command>, then run the worker or{" "}
              <Command>POST /workspaces/{slug}/tagging/run</Command>.
            </p>
          )}
        </div>
      )}
    </main>
  );
}

/* ---- Reusable components ---- */

function Command({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs dark:bg-zinc-800">
      {children}
    </code>
  );
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <span className="text-2xl font-bold tabular-nums">{value.toLocaleString()}</span>
      <span className="text-xs text-zinc-500">{label}</span>
    </div>
  );
}

function FieldSection({ name, field }: { name: string; field: FieldScore }) {
  if (field.compared === 0) {
    return (
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold capitalize">{name}</h2>
        <p className="text-sm text-zinc-500">Nothing to compare yet.</p>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-baseline gap-4">
        <h2 className="text-lg font-semibold capitalize">{name}</h2>
        <span className="text-sm text-zinc-600 dark:text-zinc-400">
          {(field.accuracy * 100).toFixed(1)}% correct ({field.correct}/{field.compared}) · macro
          F1 {field.macro_f1.toFixed(2)}
        </span>
      </div>

      {/* Per-class table */}
      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-200 bg-zinc-50 text-xs uppercase text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
            <tr>
              <th className="px-4 py-2">Label</th>
              <th className="px-4 py-2 text-right">Expected</th>
              <th className="px-4 py-2 text-right">Predicted</th>
              <th className="px-4 py-2 text-right">Correct</th>
              <th className="px-4 py-2 text-right">Precision</th>
              <th className="px-4 py-2 text-right">Recall</th>
              <th className="px-4 py-2 text-right">F1</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(field.per_class)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([label, cs]) => (
                <tr
                  key={label}
                  className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                >
                  <td className="px-4 py-2 font-medium">{label}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{cs.expected}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{cs.predicted}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{cs.correct}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{cs.precision.toFixed(2)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{cs.recall.toFixed(2)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{cs.f1.toFixed(2)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Mistakes */}
      {field.mistakes.length > 0 && (
        <div className="text-sm text-zinc-600 dark:text-zinc-400">
          <span className="font-medium">Most common mistakes: </span>
          {field.mistakes.map((m, i) => (
            <span key={i}>
              {i > 0 && ", "}
              {m[0]} → {m[1]} ×{m[2]}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
