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
