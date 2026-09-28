# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working with this repo

For any complex task (multi-file changes, new features, schema/migration changes, anything touching the write paths or AI gating described below), present a plan first and wait for explicit approval before implementing. Simple, single-file or clearly-scoped fixes don't need this.

When running multiple agents/subagents for a task, tell the user how many are running and what each one is doing (not just a final combined result). Also show a live flow-diagram widget (visualize tool, HTML/interactive module) with one node per agent and a status badge (queued/running/done) — re-render it as agents start and finish so it reflects current progress, not just the end state.

## What this is

Worthflow: a local-first personal net-worth dashboard. FastAPI backend + SQLite, React/TS frontend, Typer CLI. The user's real financial data lives in `data/private/` (gitignored) and is separate from a fictional `data/demo/` dataset used for development. Treat anything under `data/private/` as sensitive — never inspect, log, or transmit its contents beyond what the user's current request requires, and never "correct" a value there without asking first (this app is the user's live daily-use tool; unexpected values are often the user's own edits, not corruption).

## Commands

### Backend (run from `backend/`)

```bash
.venv/Scripts/pip install -e ".[dev]"       # setup
.venv/Scripts/alembic upgrade head          # apply migrations
.venv/Scripts/uvicorn app.main:app --reload # run API (port 8000)
.venv/Scripts/pytest                        # run all tests
.venv/Scripts/pytest tests/unit/test_trends.py -k test_name  # single test
.venv/Scripts/ruff check app cli tests scripts  # lint (excludes auto-generated alembic/versions)
.venv/Scripts/mypy app cli                  # type check (needs the `dev` extra installed)
```

Tests run against an isolated in-memory SQLite DB and a fake exchange-rate provider (`tests/conftest.py`) — never touch `data/private/finance.db` or the network.

CI (`.github/workflows/ci.yml`) runs these exact commands on push to `main` and on every PR — "passes locally" and "passes in CI" are the same question.

### Frontend (run from `frontend/`)

```bash
npm run dev      # dev server, port 5173, proxies /api to 127.0.0.1:8000
npm run build    # tsc -b && vite build — this is also the CI gate
```

`npm run lint` (eslint) is not currently wired up — eslint isn't installed and there's no config — so it's not part of CI yet.

Use `.claude/launch.json` (via the `run` skill / preview tooling) rather than raw `npm run dev` in a plain shell — Node's PATH doesn't propagate to spawned processes reliably on this machine, hence the `frontend/dev.cmd` wrapper referenced there.

### CLI

`finance <command>` (installed via the backend venv, entry point `cli.main:app`) — `import`, `snapshot add/list`, `accounts list/add/deactivate`, `rates`, `status`, `analyze`.

## Architecture

Two thin front ends (`backend/app/api/` FastAPI routers, `backend/cli/` Typer commands) both delegate to one shared logic layer, `backend/app/services/*`. Neither front end contains business logic — e.g. `POST /api/snapshots` and `finance snapshot add` both ultimately call `snapshots_service`. When changing behavior, change the service function once; both surfaces pick it up.

```
frontend/  (React+TS) ──┐
                         ├──> backend/app/api/    (thin routers)
backend/cli/  (Typer) ──┘             │
                                       v
                         backend/app/services/    (all business logic)
                                       │
                                       v
                         backend/app/database/    (SQLAlchemy models, SQLite)
```

### The canonical write path: `set_monthly_value`

`app/services/snapshots_service.py::set_monthly_value(db, *, account, year, month, value, ...)` is the single path used by the Monthly Values grid, the CLI, and AI-assisted import. It is "additive, correct-in-place": if a snapshot already exists anywhere in that calendar month it corrects that snapshot's value; otherwise it creates a new one dated the month's last day. "Add this month's value" and "fix a typo in an existing value" are the same call — never write snapshots directly when adding this kind of entry point.

### Deterministic calculations vs. AI — hard boundary

`app/services/calculations/` (trends, growth, allocation, portfolio totals) is pure Decimal arithmetic with no AI involvement. `app/services/ai/provider.py::StructuredFinancialData` is the *only* thing ever handed to an AI provider, and it is always the *output* of the calculation engine — an AI provider is never asked to compute a total, a percentage, or any numeric result itself. Keep this boundary when extending either side.

### Privacy-gated AI (two features, one gate)

Both AI-assisted import (`app/services/import_ai/`) and AI analysis (`app/services/ai/service.py`, currently stubbed) require **both** `AI_ANALYSIS_ENABLED=true` and `AI_ALLOW_EXTERNAL_DATA=true` in `.env` before any external call is made; otherwise they raise a clear "not configured" error that the UI surfaces directly. `build_import_interpreter()` in `app/services/import_ai/service.py` is the gate-check entry point. `AnthropicImportInterpreter` (`app/services/ai/anthropic_import_interpreter.py`) calls the Anthropic Messages API directly via `httpx` (no SDK) and defensively parses/sanitizes the JSON response (strips markdown fences, validates enums, skips malformed entries with warnings rather than crashing). The import interpreter is a swappable ABC (`ImportInterpreterProvider`), mirroring the `ExchangeRateProvider` pattern, so another provider can be added without touching the API or frontend.

### Historical exchange rates

`ExchangeRateService` (`app/services/exchange_rates/`) caches every fetched `(base, quote, date)` rate in the `exchange_rates` table so that, e.g., last March's total always uses last March's real rate. On provider failure it falls back to the most recent cached rate and explicitly flags this via `is_stale_fallback` rather than silently substituting a wrong-but-plausible number. Provider is swappable (`ExchangeRateProvider` ABC); `FrankfurterProvider` is the only implementation, hits `api.frankfurter.dev/v1`, and retries transient failures.

### Excel import mapping

`app/services/import_excel/mapping.py` is the single source of truth for which spreadsheet row label maps to which account/currency/type/asset class (`DEFAULT_ACCOUNT_MAPPINGS`), and which labels are the source sheet's own derived rollups to skip on import (`KNOWN_DERIVED_LABELS`). Renaming or adding an account in the source sheet means editing this file, not the parser. The `Crypto`, `Arkusz14`, and `Vattenfall` sheets are explicitly out of scope (not net-worth data). This deterministic "Quick import" path only handles the one exact "Raw data" sheet shape; the newer AI-assisted import path (`import_ai/`) handles arbitrary file layouts via `AnthropicImportInterpreter` and always goes through a preview-then-confirm UI flow before writing anything.

### Frontend structure

`frontend/src/pages/` holds one component per tab (`OverviewPage`, `AccountsPage`, `MonthlyValuesPage`, `ImportPage`), wired up in `App.tsx`. `api/client.ts` wraps `fetch` and includes `extractErrorMessage()` to flatten FastAPI's 422 validation error shape (`detail` can be a string or an array of Pydantic error objects) into a displayable string. `MonthlyValuesPage` uses a staged-changes pattern: edits are held in local `pending` state and only written via `api.setMonthlyValue` (→ `set_monthly_value`) when the user explicitly clicks Save; editing itself is gated behind an explicit "Enable editing" toggle that warns before discarding unsaved changes.

### Migrations

Schema changes go through Alembic (`backend/alembic/`) — modify `app/database/models.py`, then generate/hand-write a migration; don't hand-edit `data/private/finance.db`'s schema.
