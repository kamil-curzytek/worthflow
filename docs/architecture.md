# Architecture

## Layering

```
frontend/  (React + TS)  ──┐
                            ├──>  backend/app/api/      (FastAPI routers — thin)
backend/cli/  (Typer)    ──┘             │
                                          v
                              backend/app/services/     (business logic — the only
                                          │               place either front end
                                          v               should reach into)
                              backend/app/database/      (SQLAlchemy models, SQLite)
```

The API and CLI never contain business logic themselves — both call into
`app/services/*` and just handle their own I/O concerns (HTTP request/response
vs. terminal I/O). This is what "CLI and dashboard use the same underlying logic"
means concretely: `app/services/snapshots_service.py::add_or_update_monthly_snapshot`
is called by both `POST /api/snapshots` and `finance snapshot add`.

## Why this stack

- **SQLite**: single-file, zero-ops, matches "local-first" directly. The database
  layer (`app/database/session.py`) only knows a SQLAlchemy URL — swapping in
  Postgres later is a connection-string and dependency change, not a rewrite.
- **FastAPI**: async-capable, typed, auto-docs at `/docs` — useful once the
  dashboard needs more than CRUD (e.g. streaming AI analysis later).
- **React + TypeScript + Recharts**: mature, widely documented, and Recharts'
  declarative API keeps chart code readable as more views get added.
- **Typer**: thin wrapper over Click with good typing support; keeps CLI commands
  as small functions that call the same services the API calls.
- **Frankfurter** for exchange rates: free, no API key, ECB-backed, and critically
  supports historical-date lookups (`/v1/2021-06-01?from=PLN&to=EUR`) — required for
  "what rate applied to last year's snapshot" to be answerable at all.

## Data model

```
users            id, email, display_name

accounts         id, user_id, name, type, asset_class, currency, institution,
                  is_active, created_at, updated_at
                  UNIQUE(user_id, name)

snapshots        id, account_id, snapshot_date, value, currency, source, note,
                  import_batch_id, created_at, updated_at
                  UNIQUE(account_id, snapshot_date)

exchange_rates   id, base_currency, quote_currency, rate, rate_date, source,
                  fetched_at
                  UNIQUE(base_currency, quote_currency, rate_date, source)

import_batches   id, source_filename, status, row_count, imported_at, notes
```

Key decisions:

- **One currency per account**, stored in `accounts.currency`, not per-snapshot.
  This matches how the source data is actually tracked (each account always held
  the same currency) and avoids a currency column that's redundant 100% of the
  time. `snapshots.currency` still denormalizes it onto each row so a snapshot is
  self-describing even if an account's currency were ever changed later.
- **No `Asset`/`Holding` entity yet.** The spec allows for one, but nothing in the
  source data needs share-level tracking (eTrade RSU/ESPP values in "Raw data" are
  already dollar amounts, not share counts — the ESPP sheet's separate qty/price
  tracking is importable later without a schema change, by adding a table that
  references `accounts`, not by changing `snapshots`).
- **`asset_class` lives on `Account`**, not a separate join table. The source
  sheet's CASH/TRADING/CRYPTO/TESLA rollups are a fixed, small, rarely-changing
  set — a full many-to-many category model would be premature.
- **No AI/recommendation/goal tables yet.** `app/services/ai/provider.py` defines
  the interface Phase 7+ will use, but nothing is persisted until there's an actual
  feature that needs it (see "Phases" below).
- **Snapshots are additive, not overwritten**, enforced by
  `UNIQUE(account_id, snapshot_date)` plus `create_snapshot` refusing to overwrite
  by default. Correcting a value for an *existing* date is a distinct, explicit
  operation (`allow_overwrite=True` / `add_or_update_monthly_snapshot`), so
  "add this month" and "fix a typo" can't be confused with each other.

## Excel → database mapping

The source file (`Moneytalks.xlsx`) has a "Raw data" sheet shaped as:

- Row 3: year, sparse (only set at the first column of each year's block)
- Row 4: month name for every populated column
- Rows 5–17: one row per account, one value per (account, month) cell, in the
  account's *native* currency
- Rows 19–31 and 36–42: the sheet's own SUM / category rollups / percentages,
  computed with a single static "today's rate" applied to *all* history (see
  the `Conversion` sheet — one hardcoded rate per currency, no history)

`app/services/import_excel/`:

- `mapping.py` — the only place that says which row label means which account,
  currency, type, and asset class (`DEFAULT_ACCOUNT_MAPPINGS`), plus which labels
  are the sheet's own derived rollups to skip (`KNOWN_DERIVED_LABELS`). Renaming,
  adding, or retiring an account in the source sheet means editing this file, not
  the parser.
- `parser.py` — reads the year/month header cells directly (forward-filling the
  year across columns) rather than assuming a fixed column range, so a reordered
  or gap-containing header (the source file is missing an October 2023 column, for
  real) still parses correctly. An unrecognized account label produces a warning,
  not a crash or a silent drop.
- `importer.py` — `preview_import` (read-only) then `commit_import` (writes,
  wrapped in one `ImportBatch`). Rollup rows (SUM, CASH, TRADING %, ...) are never
  imported — they're recomputed by `app/services/calculations/` using correct
  per-date historical FX rates instead of the sheet's one static rate.

Explicitly **out of scope** for import (confirmed with the data owner): the
`Crypto`, `Arkusz14`, and `Vattenfall` sheets — the latter two aren't net-worth
data at all (a utility-bill tracker and a rent-split calculator that happen to
live in the same workbook). `ESPP`, `Trading212`, and `Passive Income` hold
richer sub-ledger detail behind three of the accounts (contribution history,
dividends, share counts) — deferred past the MVP, not lost; they can be imported
later as tables that reference `accounts` without changing `snapshots`.

## Deterministic calculations vs. AI

`app/services/calculations/` is pure arithmetic — `trends.py` has zero I/O and can
be unit-tested with plain Decimal inputs; `portfolio.py` does the DB queries and FX
conversion but still no AI. `app/services/ai/provider.py::StructuredFinancialData`
is the only thing ever handed to an AI provider — it's the *output* of the
calculation engine, never raw snapshots, and an AI provider is never asked to
compute a total or a percentage itself.

## Phases implemented so far

1. Foundation — schema, migrations, config, `.gitignore`, demo dataset ✅
2. Excel ingestion — mapping, parser, preview/commit ✅
3. Dashboard — overview, accounts, monthly history, trend/allocation charts,
   currency selector ✅
4. Currency — Frankfurter provider, DB-cached historical rates, graceful
   degradation on API failure ✅
5. CLI — `import`, `snapshot`, `accounts`, `rates`, `status`, `analyze`, sharing
   `app/services/*` with the API ✅
6. Analysis engine — trend/growth/allocation math, unit-tested ✅
7. AI — split into two features sharing one privacy gate:
   - **AI-assisted import** ✅ — `AnthropicImportInterpreter` reads an arbitrary
     spreadsheet/CSV and proposes an account/snapshot mapping via the Import tab's
     preview-then-confirm flow (`app/services/import_ai/`, `app/services/ai/
     anthropic_import_interpreter.py`)
   - **AI analysis** — interface defined (`app/services/ai/provider.py`,
     `AIAnalysisService`), **no real provider wired up yet**, deliberately deferred
     until there's a concrete use case to design the prompt/output contract against
8. Advisor extensions (goals, scenarios, recommendations) — **not started**;
   `app/services/ai/provider.py`'s `StructuredAnalysis` shape leaves room for
   `recommendations`/`questions` fields so this doesn't require a breaking change
