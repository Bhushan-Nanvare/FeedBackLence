"use client";

import { useState } from "react";

import { ApiError, askQuestion, rateAnswer, type Answer, type CitedItem } from "@/lib/api";

const EXAMPLES = [
  "What do users complain about in the terminal?",
  "Why are people unhappy with chat?",
  "What breaks after updating?",
];

export function AskForm({ slug }: { slug: string }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (trimmed.length < 3 || asking) {
      return;
    }
    setQuestion(trimmed);
    setAsking(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await askQuestion(slug, trimmed));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not reach the API.");
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
        className="flex flex-col gap-3"
      >
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void ask(question);
            }
          }}
          rows={2}
          placeholder="Ask about your feedback…"
          aria-label="Your question"
          className="w-full rounded-md border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700"
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            disabled={asking || question.trim().length < 3}
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {asking ? "Reading the feedback…" : "Ask"}
          </button>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => void ask(example)}
              disabled={asking}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-600 disabled:opacity-40 dark:border-zinc-700 dark:text-zinc-400"
            >
              {example}
            </button>
          ))}
        </div>
      </form>

      {error && (
        <p className="rounded-xl border border-red-200 p-4 text-sm dark:border-red-900">{error}</p>
      )}
      {answer && <AnswerView slug={slug} answer={answer} />}
    </div>
  );
}

function AnswerView({ slug, answer }: { slug: string; answer: Answer }) {
  return (
    <section className="flex flex-col gap-4">
      <div className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
        <p className="whitespace-pre-wrap leading-relaxed">
          <WithCitations text={answer.answer} sources={answer.sources} />
        </p>
        <p className="mt-3 text-xs text-zinc-500">
          {answer.enough_evidence
            ? `Based on ${answer.sources.length} of ${answer.considered_count} reports read`
            : "Not enough feedback to answer this"}
          {answer.dropped_citations.length > 0 &&
            " · removed a reference that pointed at nothing"}
        </p>
      </div>

      {answer.sources.length > 0 && (
        <div className="flex flex-col gap-2">
          <h2 className="text-sm font-medium uppercase tracking-wide text-zinc-500">Sources</h2>
          {answer.sources.map((source) => (
            <SourceCard key={source.number} source={source} />
          ))}
        </div>
      )}

      {answer.question_id !== null && <Rating slug={slug} questionId={answer.question_id} />}
    </section>
  );
}

/** Turns "[2]" in the answer into a link to that source. */
function WithCitations({ text, sources }: { text: string; sources: CitedItem[] }) {
  const known = new Set(sources.map((source) => source.number));
  return (
    <>
      {text.split(/(\[\d+\])/).map((part, index) => {
        const match = /^\[(\d+)\]$/.exec(part);
        if (match && known.has(Number(match[1]))) {
          return (
            <a
              key={index}
              href={`#source-${match[1]}`}
              className="mx-0.5 rounded bg-zinc-200 px-1 text-xs font-medium text-zinc-700 no-underline dark:bg-zinc-700 dark:text-zinc-200"
            >
              {match[1]}
            </a>
          );
        }
        return <span key={index}>{part}</span>;
      })}
    </>
  );
}

function SourceCard({ source }: { source: CitedItem }) {
  const { item } = source;
  return (
    <article
      id={`source-${source.number}`}
      className="flex gap-3 rounded-xl border border-zinc-200 p-3 text-sm dark:border-zinc-800"
    >
      <span className="mt-0.5 h-fit rounded bg-zinc-200 px-1.5 text-xs font-medium dark:bg-zinc-700">
        {source.number}
      </span>
      <div className="flex min-w-0 flex-col gap-1">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium underline-offset-4 hover:underline"
        >
          {item.title}
        </a>
        {item.tag?.summary && (
          <p className="text-zinc-600 dark:text-zinc-400">{item.tag.summary}</p>
        )}
        <p className="text-xs text-zinc-500">
          #{item.external_id} · {new Date(item.external_created_at).toLocaleDateString()} ·{" "}
          {item.state}
        </p>
      </div>
    </article>
  );
}

function Rating({ slug, questionId }: { slug: string; questionId: number }) {
  const [sent, setSent] = useState<boolean | null>(null);

  async function send(helpful: boolean) {
    try {
      await rateAnswer(slug, questionId, helpful);
      setSent(helpful);
    } catch {
      // A rating is not worth interrupting the reader for.
    }
  }

  if (sent !== null) {
    return <p className="text-xs text-zinc-500">Thanks: recorded as {sent ? "helpful" : "not helpful"}.</p>;
  }

  return (
    <div className="flex items-center gap-2 text-xs text-zinc-500">
      Was this helpful?
      <button
        type="button"
        onClick={() => void send(true)}
        className="rounded-md border border-zinc-300 px-2 py-1 dark:border-zinc-700"
      >
        Yes
      </button>
      <button
        type="button"
        onClick={() => void send(false)}
        className="rounded-md border border-zinc-300 px-2 py-1 dark:border-zinc-700"
      >
        No
      </button>
    </div>
  );
}
