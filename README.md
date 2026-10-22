# FeedbackLens

FeedbackLens collects user feedback from GitHub issues, CSV files and an embeddable widget, groups it into themes, spots problems that are growing and turns the biggest ones into tickets backed by real quotes.

> **Status:** Phase 5: accounts, workspaces and permissions are in. Widget, cost tracking and deployment are next.

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

## Accounts and workspaces

Feedback belongs to a workspace, and a workspace is private unless it is marked public. The `demo` workspace is public, so anyone can read it and ask it questions without an account; everything else needs one.

**Create an account** at http://localhost:3000/signin — email, your name, and a password of at least 8 characters. Passwords are stored as scrypt hashes, never as text. Creating a workspace makes you its owner.

**Roles** decide what you may do in a workspace:

| Role | May |
| --- | --- |
| `owner`, `admin` | everything, plus product areas and inviting people |
| `member` | import feedback, correct tags, rename themes, draft and file tickets |
| `viewer` | read, search and ask questions |

Owners and admins invite people who have already registered:

```bash
curl -X POST http://localhost:8000/workspaces/demo/members \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"email": "teammate@example.com", "role": "member"}'
```

**Behind the scenes:** signing in returns a signed token that lasts `AUTH_TOKEN_DAYS` (7 by default). The web app keeps it in a cookie and sends it as `Authorization: Bearer …`; pages read the same cookie on the server. To call the API directly, `POST /auth/login` and pass the `access_token` the same way, or click **Authorize** in http://localhost:8000/docs.

Set `AUTH_SECRET_KEY` in `.env` before deploying. Without it the API signs tokens with a key it makes at startup, so every restart signs everyone out.

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

## Importing a CSV

Feedback often lives in a support tool rather than GitHub. Upload an export at http://localhost:3000/workspaces/demo/import, or `POST /workspaces/{slug}/sources/csv`.

- **Column names are matched loosely.** The feedback itself can be `text`, `body`, `description`, `feedback`, `comment` or `message`; a title, date, id, link and author are picked up if present. Case and spacing are ignored, so `Ticket ID` and `Submitted At` work.
- **Rows without text are skipped and listed back**, with the row number, instead of disappearing.
- **Re-uploading the same file is safe.** Rows are matched on their id, or on a fingerprint of their text when there is none, so nothing is duplicated and edits come through as updates.
- **Email addresses and phone numbers are removed before anything is stored**, so they are never saved and never reach an AI model. Dates and version numbers are left alone. GitHub issues are not scrubbed, because they are already public.
- Importing queues tagging and grouping automatically, the same as a GitHub sync.

Limits: 5 MB and 5,000 rows per file.

## Alerts for themes that are growing

A theme that suddenly takes off is the thing a team wants to hear about, so FeedbackLens watches the weekly counts and raises an alert.

- A theme is **rising** when its latest week is at least `ALERT_MIN_RATIO` times its usual rate (3× by default) **and** has at least `ALERT_MIN_ITEMS` reports (8 by default). The second rule is what stops "1 report became 3" from looking like a tripling.
- A quiet theme's usual rate counts as at least one report a week, so a brand-new problem with ten reports is reported as 10× rather than dividing by zero.
- The comparison uses the newest week the workspace has data for, so a check still works when an import finished a few days ago.
- **One alert per theme per week**, enforced by the database, so nobody gets the same warning twice.
- Alerts appear at the top of the themes dashboard. Set `SLACK_WEBHOOK_URL` to have them posted to Slack as well; without it they are recorded and shown, and nothing is sent anywhere.
- Grouping runs queue a check automatically, or use `POST /workspaces/{slug}/alerts/check`.

On 21 days of VS Code feedback this finds "Language model unavailable" (12 reports, 5.3× its usual 2.2 a week) and "Extension host repeatedly crashes" (17 reports, 3.1× its usual 5.5).

## Turning a theme into a ticket

A theme is only useful if it reaches the issue tracker. Open a theme and use the **Ticket** panel, or the endpoints below.

- **The draft writes itself** from the theme: how many reports, when they started, how fast it is growing, and five real reports quoted with links back to them.
- **Possible duplicates are checked first.** Recent issues in the target repository are compared with the draft's title, by meaning when an embedding model is available and by shared words otherwise. Anything close is shown before you file.
- **Nothing is filed automatically.** The draft is editable, and filing happens only when you press the button. The same step is a separate API call.
- **It refuses to post into a repository you only read from.** Filing into `microsoft/vscode` when that is a source would spam someone else's project, so it is blocked with an explanation. Set `TICKET_REPO` to a repository you own, and give `GITHUB_TOKEN` write access to it.
- A failed duplicate lookup never loses the draft; a wrong repository name surfaces when you file.

Endpoints: `POST /workspaces/{slug}/themes/{id}/ticket`, `GET /workspaces/{slug}/tickets`, `PATCH /workspaces/{slug}/tickets/{id}`, `POST /workspaces/{slug}/tickets/{id}/file`.

### Re-cleaning older reports

Cleaning rules improve over time, and already-imported reports keep the text they arrived with. To bring them up to date:

```bash
cd backend
uv run python -m app.maintenance reclean --workspace demo --dry-run
uv run python -m app.maintenance reclean --workspace demo
uv run python -m app.worker --once   # re-tags and re-embeds whatever changed
```

## Ask your feedback

Ask a question in plain English at http://localhost:3000/workspaces/demo/ask and get an answer built only from real reports, with a numbered link to each one.

- **Two searches run together.** One matches words (good for exact terms and error codes), one matches meaning (good when users describe the same problem in different words). Their rankings are merged with reciprocal rank fusion, which needs no way to compare the two kinds of score. Asking "chat is too slow to respond" on VS Code feedback finds nothing by words and five relevant reports by meaning.
- **The model only sees real reports.** It receives a numbered list and must point at the ones it used.
- **Citations are checked afterwards.** A number that doesn't match a report it was shown is removed from the answer, and an answer left with no citation is reported as unsupported rather than believed.
- **Nothing to answer from?** It says so instead of inventing something, and no model call is made at all.
- Every question, answer and cited report is saved, along with a thumbs up or down, which is the signal for improving the prompt later.

Word search alone works without any AI key, so `GET /workspaces/{slug}/search?q=...` is useful immediately. Answering needs `GEMINI_API_KEY`; without it the page says exactly that.

Endpoints: `GET /workspaces/{slug}/search`, `POST /workspaces/{slug}/ask`, `POST /workspaces/{slug}/questions/{id}/rating`.

## AI cost tracking

Every model call (tagging, embedding, answering) is logged to the `ai_calls` table with its token usage and latency. The usage dashboard at http://localhost:3000/workspaces/demo/usage shows:

- **Lifetime totals** — calls, items processed, tokens consumed, estimated USD cost.
- **Per-feature breakdown** — how many tokens tagging, embedding and answering each consume, with average latency.
- **Daily chart** — tokens per day for the last 30 days, so spikes are visible at a glance.

The cost estimate uses published Gemini Flash-Lite pricing and is meant as an indicator, not an invoice. No new data collection is needed; the tracking was built into the AI modules from the start.

Endpoint: `GET /workspaces/{slug}/ai/usage?days=30`.

## Embeddable feedback widget

Let visitors submit feedback directly from your website. Paste a single `<script>` tag and a floating "Feedback" button appears in the bottom-right corner.

**How it works:**

1. Go to the import page for your workspace (e.g. http://localhost:3000/workspaces/demo/import).
2. Copy the embed snippet shown under "Embeddable feedback widget".
3. Paste it into your site's HTML, just before `</body>`.

The widget is self-contained (no dependencies, no build step) and uses Shadow DOM so it cannot clash with your site's styles. Submissions go through the same PII scrubbing pipeline as CSV imports — emails and phone numbers are removed before anything is stored. Tagging and embedding jobs are queued automatically.

Endpoints: `POST /workspaces/{slug}/widget/submit` (public, no auth), `GET /workspaces/{slug}/widget/embed`.

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
- `--json` saves the report, `--save-baseline` stores it as the reference, and `--baseline evals/baselines/demo.json --max-drop 3` fails when a score falls more than 3 points.

### CI integration

The GitHub Actions CI workflow runs the eval scorer after tests pass:

```yaml
- name: Eval regression check
  run: |
    uv run python -m app.evals score \
      --workspace demo \
      --baseline ../../evals/baselines/demo.json \
      --max-drop 3.0
```

If any accuracy or macro F1 score drops more than 3 points compared to the saved baseline, the CI step fails and blocks the PR.

To update the baseline after intentional prompt changes:

```bash
cd backend
uv run python -m app.evals score --workspace demo --save-baseline ../evals/baselines/demo.json
```

### Dashboard

View the eval report in the browser at `/workspaces/{slug}/evals`, or fetch it via `GET /workspaces/{slug}/evals`.

## Deployment

The project ships production-ready Docker images for the backend (FastAPI + uvicorn) and frontend (Next.js standalone).

### Build images

```bash
# Build both images
make build

# Or individually
docker build -t feedbacklens-api backend/
docker build -t feedbacklens-web web/
```

### Start the full stack

Copy `.env.example` to `.env` and set the required variables:

```bash
cp .env.example .env
# Edit .env:
#   POSTGRES_PASSWORD=...  (required — change from default!)
#   AUTH_SECRET_KEY=...    (generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
#   GEMINI_API_KEY=...
```

Then start all four services (database, API, worker, web):

```bash
make up
# or:
docker compose -f docker-compose.production.yml up -d
```

The API is available at http://localhost:8000 and the web app at http://localhost:3000.

### Useful Makefile commands

| Command | What it does |
| --- | --- |
| `make up` | Start the production stack |
| `make down` | Stop and remove all containers |
| `make logs` | Tail all container logs |
| `make logs-api` | Tail API logs only |
| `make migrate` | Run Alembic migrations via the running api container |
| `make shell-api` | Open a shell inside the API container |
| `make shell-db` | Open a psql shell inside the database container |
| `make build` | Build both Docker images |
| `make test` | Run backend tests |
| `make lint` | Run ruff + eslint |
| `make evals` | Score AI tags against the demo baseline |
| `make baseline` | Save current scores as the new baseline |

### How the API container starts

The entrypoint script (`backend/docker-entrypoint.sh`) runs `alembic upgrade head` before starting uvicorn, so migrations are applied automatically on every deploy. To run the background worker instead:

```bash
docker compose -f docker-compose.production.yml run --rm worker
```

### Environment variables

All configuration is via environment variables. See `.env.example` for the full list. The minimum set for production:

| Variable | Required | Notes |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | ✅ | Change from the default |
| `AUTH_SECRET_KEY` | ✅ | Random 32-byte hex, generated once |
| `GEMINI_API_KEY` | ✅ | For tagging, embeddings and answers |
| `PUBLIC_WEB_URL` | optional | Public base URL, e.g. `https://feedbacklens.example.com` |
| `GITHUB_TOKEN` | optional | Raises GitHub API rate limit to 5,000/hour |
| `SLACK_WEBHOOK_URL` | optional | Sends trend alerts to Slack |
| `TICKET_REPO` | optional | GitHub repository to file tickets into |

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
- [x] Phase 1: GitHub import, AI tagging, feedback inbox
- [x] Phase 2: theme grouping and dashboard
- [x] Phase 3: ask questions with cited answers
- [x] Phase 4: trend alerts, theme to ticket, CSV import
- Phase 5:
  - [x] accounts, workspaces and roles
  - [x] embeddable feedback widget
  - [x] AI cost tracking
  - [x] evaluation suite in CI
  - [x] deployment and public demo
- [x] Phase 6: theme detail page and workspace settings

## Theme detail

Visit `/workspaces/{slug}/themes/{id}` to see a single theme in depth:

- Full weekly sparkline and growth badge
- Top 20 feedback items with AI tags (type, area, sentiment, urgency)
- Inline rename (saved immediately to the API)
- Ignore / restore toggle
- Draft-ticket button (drafts a GitHub issue with quotes from the items)

## Workspace settings

Visit `/workspaces/{slug}/settings` to manage a workspace:

- Members list with role badges; owners and admins can remove members
- Invite form — adds anyone who already has an account
- Product areas editor — add, edit and remove areas used for AI classification
- Quick links to all workspace pages

The settings page is read-only for viewers and members; only owners and admins see the edit controls.
