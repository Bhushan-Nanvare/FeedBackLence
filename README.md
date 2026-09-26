# FeedbackLens

FeedbackLens collects user feedback from GitHub issues, CSV files and an embeddable widget, groups it into themes, spots problems that are growing and turns the biggest ones into tickets backed by real quotes.

> **Status:** Phase 0: project setup.

## Tech stack

| Layer | Choice |
| --- | --- |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy, Alembic |
| Database and vectors | PostgreSQL + pgvector |
| Background jobs | Worker process backed by a Postgres job queue |
| AI | Gemini (tagging, embeddings, theme naming, answers) |
| CI | GitHub Actions |

## Project layout

```
backend/     FastAPI app, database models, migrations, tests
web/         Next.js frontend
docker-compose.yml   Local Postgres + pgvector
```

## Run locally

Requirements: Docker Desktop, Python 3.11+ with [uv](https://docs.astral.sh/uv/), Node.js 24.

**1. Start the database** (Postgres + pgvector on `localhost:5434`)

```bash
docker compose up -d
```

**2. Start the API** at http://localhost:8000 (interactive docs at `/docs`)

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

**3. Start the worker**, which runs imports and other background jobs

```bash
cd backend
uv run python -m app.worker
```

**4. Start the web app** at http://localhost:3000

```bash
cd web
npm install
npm run dev
```

The home page shows whether the API, database and pgvector are reachable.

Settings have working local defaults. To override them, copy `.env.example` to `.env` (backend) and `web/.env.example` to `web/.env.local` (frontend).

## Import GitHub issues

With the API and worker running, open http://localhost:8000/docs and:

1. `POST /workspaces/demo/sources/github` with `{"repo": "microsoft/vscode", "backfill_days": 30}`
2. `POST /workspaces/demo/sources/{source_id}/sync` to queue the import
3. `GET /workspaces/demo/jobs/{job_id}` to watch it finish

The first sync imports issues created in the last `backfill_days` (up to `max_items`). Later syncs only fetch issues updated since the previous run. Pull requests and bot posts are skipped, and template text, logs and screenshots are removed from each issue before any AI step reads it.

Without a token GitHub allows 60 API requests per hour. Set `GITHUB_TOKEN` in `.env` to raise that to 5,000.

## AI tagging

After each sync the worker labels new and changed issues with a **type** (bug, feature request, question, praise, other), **product area**, **sentiment**, **urgency** and a **one-line summary**. It uses Gemini with a strict JSON schema, so the model can only answer with known labels.

1. Add `GEMINI_API_KEY` to `.env` (a free key from [Google AI Studio](https://aistudio.google.com/apikey)).
2. Optionally adjust the product areas with `PUT /workspaces/demo/product-areas`. The demo workspace starts with areas for VS Code.
3. Tagging is queued automatically after a sync, or manually with `POST /workspaces/demo/tagging/run`.
4. Check progress with `GET /workspaces/demo/tagging/status`.

How it keeps cost and mistakes down:

- Issues written by maintainers are internal tasks, so they are skipped.
- Items go to the model in batches (15 by default), and requests are spaced to stay under `GEMINI_REQUESTS_PER_MINUTE`. When Gemini says to slow down, the job waits for the time it asks for.
- Unchanged items are never tagged twice, and tags a person has reviewed are never overwritten.
- Feedback text is treated as untrusted data in the prompt, and every result is validated before it is saved.
- Every model call is recorded in `ai_calls` with its token usage and latency.

## Feedback inbox

Open http://localhost:3000/workspaces/demo/inbox (or follow the link from the home page).

- Filter by type, product area, urgency, sentiment or state, show only untagged items, search titles and text, and sort by newest, oldest or most reactions.
- Maintainers' own issues are hidden unless you ask for them.
- Each card links to the original issue and shows its labels and one-line summary.
- The **Correct** dropdowns fix a wrong label. Corrected items are marked, are never re-labelled by AI, and become the checked set used later to measure tagging accuracy.

Endpoints: `GET /workspaces/{slug}/items` (filters, paging), `GET /workspaces/{slug}/items/{id}`, `PATCH /workspaces/{slug}/items/{id}/tag`.

## Themes: grouping similar feedback

Once items are imported, the worker turns each one into a vector and groups similar ones into **themes**, so "the terminal crashes when I split it" reported 40 different ways becomes one row.

```bash
cd backend
uv sync --extra local-embeddings   # once: installs the local embedding model runner
uv run python -m app.worker        # embeds new items, then groups them
```

- **Vectors** capture what a report is about. By default a small model runs on your machine (`EMBEDDING_PROVIDER=local`): no key, no quota, no cost. Set `EMBEDDING_PROVIDER=gemini` to use the API instead; both produce the same size, so you can switch without touching the database.
- **Grouping** uses HDBSCAN, which leaves one-off reports out instead of forcing everything into a group. A theme needs at least `CLUSTER_MIN_SIZE` reports (5 by default).
- **Themes keep their identity across runs.** Each run matches its groups to the previous ones by the reports they share, so a theme's id, and the name you gave it, survive as new feedback arrives.
- **Names** start as the title of the theme's most typical report. Rename a theme in the dashboard and later runs keep your name.
- Leftover reports that sit very close to a theme's centre are attached to it.
- Weekly counts per theme are stored, which drives the trend chart now and alerts in a later phase.

Dashboard: http://localhost:3000/workspaces/demo/themes. Endpoints: `GET /workspaces/{slug}/themes` (sort by size, growth or recency), `GET .../themes/{id}`, `PATCH .../themes/{id}` (rename or hide), `POST .../themes/recluster`.

## Ask your feedback

Ask a question in plain English at http://localhost:3000/workspaces/demo/ask and get an answer built only from real reports, with a numbered link to each one.

- **Two searches run together.** One matches words (good for exact terms and error codes), one matches meaning (good when users describe the same problem in different words). Their rankings are merged with reciprocal rank fusion, which needs no way to compare the two kinds of score. Asking "chat is too slow to respond" on VS Code feedback finds nothing by words and five relevant reports by meaning.
- **The model only sees real reports.** It receives a numbered list and must point at the ones it used.
- **Citations are checked afterwards.** A number that doesn't match a report it was shown is removed from the answer, and an answer left with no citation is reported as unsupported rather than believed.
- **Nothing to answer from?** It says so instead of inventing something, and no model call is made at all.
- Every question, answer and cited report is saved, along with a thumbs up or down, which is the signal for improving the prompt later.

Word search alone works without any AI key, so `GET /workspaces/{slug}/search?q=...` is useful immediately. Answering needs `GEMINI_API_KEY`; without it the page says exactly that.

Endpoints: `GET /workspaces/{slug}/search`, `POST /workspaces/{slug}/ask`, `POST /workspaces/{slug}/questions/{id}/rating`.

## Measuring tagging accuracy

AI labels are only worth trusting if we know how often they are right, so FeedbackLens keeps a **checked set** of correct answers and scores the AI against it.

```bash
cd backend
uv run python -m app.evals build --workspace demo --limit 1500
uv run python -m app.evals score --workspace demo
```

- **Drafts come free from the repository's own labels.** An issue labelled `bug` and `terminal` becomes "type: bug, area: terminal". On 21 days of VS Code issues this drafts roughly 190 answers.
- Labels that only describe how an issue was handled, such as `invalid` or `*duplicate`, are ignored, because they don't say what kind of feedback it is.
- **Corrections you make in the inbox replace the drafts** and are never overwritten by a later draft run.
- **Items you corrected are left out of the score**, since a corrected tag matches the answer by definition and would flatter the model.
- The report shows accuracy, precision, recall and F1 for each label, macro F1, and the most common mistakes.
- `--json` saves the report, `--save-baseline` stores it as the reference, and `--baseline evals/baseline.json --max-drop 3` fails when a score falls more than 3 points. That is how this will run in CI in Phase 5; today it runs locally, because scoring needs a database with real tags.

## Checks

Backend:

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Frontend:

```bash
cd web
npm run lint
npm run build
```

Tests use a separate `feedbacklens_test` database, created and migrated automatically, so your local data is never touched.

The same checks run in GitHub Actions on every push and pull request.

## Roadmap

- [x] Phase 0: project setup
- [ ] Phase 1: GitHub import, AI tagging, feedback inbox
- [ ] Phase 2: theme grouping and dashboard
- [ ] Phase 3: ask questions with cited answers
- [ ] Phase 4: trend alerts, theme to ticket, CSV import
- [ ] Phase 5: workspaces and login, widget, cost tracking, evaluation in CI, deployment
