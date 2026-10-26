# Tier-1 Agent Engine

Prompt compiler, skill injection, a parallel worker mesh (memory, research, tools, test, audit),
token-optimised delegation with *measured* savings, a hash-chained evidence ledger, cron and signed
webhooks, a CLI, an MCP stdio server, and a control-plane UI.

## Quick start
    pip install -e ".[dev]"
    pytest
    TIER1_PROVIDER=mock tier1 serve        # UI at http://127.0.0.1:8000
    tier1 run "Explain caching" --json

## Real models
    export TIER1_PROVIDER=anthropic TIER1_PROVIDER_API_KEY=...   # or openai + TIER1_PROVIDER_BASE_URL
    export TIER1_MODEL_SMALL=... TIER1_MODEL_MEDIUM=... TIER1_MODEL_LARGE=...
Set `TIER1_PRICE_*` to your contract prices; cost and savings figures are only as accurate as these.

## Production
Copy `.env.example` to `.env`, set `TIER1_ENV=production`, a long `TIER1_API_TOKEN` and `TIER1_WEBHOOK_SECRET`
(the server refuses to start without them), then `docker compose up -d --build`. Put TLS in front (reverse proxy).
`/health` for probes, `/metrics` for Prometheus.

## Webhooks
`POST /v1/webhooks/<job>` with headers `X-Tier1-Timestamp` and `X-Tier1-Signature = hex(HMAC_SHA256(secret, "<ts>.<raw body>"))`.
Timestamps older than 5 minutes and replayed signatures are rejected. The body is passed to the job as untrusted data via `{input}`.

## MCP
    {"mcpServers": {"tier1": {"command": "tier1", "args": ["mcp"], "env": {"TIER1_PROVIDER": "anthropic", "TIER1_PROVIDER_API_KEY": "..."}}}}
Tools: tier1_run, tier1_compile, tier1_skills, tier1_usage, tier1_verify_ledger.

## Skills
Drop a Markdown file with `name`, `description`, `triggers: [a, b]`, `priority` frontmatter into `skills/`; it is hot-reloaded.
Skills containing instruction-override phrases are rejected.

## How savings are measured
Each run records real provider token usage per call. The baseline is a counterfactual: one large-tier call that receives the prompt,
all raw fetched/retrieved material and every skill, with the same answer length. `saved_pct = 1 - actual/baseline`. It can be negative for
tiny prompts. It is a model of the alternative, not a billing comparison.

## Execution modes
`mode` on `/v1/run`, `--mode` on the CLI, or a prefix in the prompt (also in cron jobs and Slack): `ralph:` re-runs with the auditor's
findings until the answer verifies (max `TIER1_MAX_RALPH_ITERATIONS`, reports `verified: false` honestly), `team:` / `ultrawork:`
decomposes into up to 4 sub-tasks run in parallel, then synthesises, `plan:` compiles only. Default is `autopilot`.

## Notebooks (NotebookLM / Obsidian / context-mode style)
SQLite FTS5 index with BM25 + stemming. `POST /v1/kb/{nb}/sources`, `GET /v1/kb/{nb}/search?q=`, `POST /v1/kb/{nb}/ask`
(answers use only retrieved chunks; citations are verified against what was retrieved and invented ones are stripped; no hits = no model call).
`POST /v1/kb/{nb}/import-vault {"path": "vault"}` imports an Obsidian vault from the sandbox (wikilinks, tags, backlinks, deletion sync, dot-dirs skipped);
set `TIER1_VAULT_DIR` to keep it synced automatically. Large web/tool output seen during runs is indexed into notebook `session` and stays out of the
prompt; the `kb_search` tool retrieves it on demand.

## Autofill (Notion AI style)
`POST /v1/autofill {"records":[{...}], "fields":{"sentiment":"positive|neutral|negative","hours":"number: effort","summary":"one sentence"}}`
fills columns on the small tier (<=50 records, <=10 columns), validates enums/numbers, retries once, and reports per-row failures.

## Slack and notifications
Set `TIER1_SLACK_SIGNING_SECRET`; point a slash command at `/v1/slack/command` and Events API at `/v1/slack/events` (add `TIER1_SLACK_BOT_TOKEN` for @mention replies).
Requests are signature- and replay-checked; replies only go to `*.slack.com` response URLs. `TIER1_NOTIFY_URL` receives signed job-done/failed events.

## Studio outputs, background tasks, chat
`POST /v1/kb/{nb}/studio {"kind": "briefing|faq|study_guide|timeline", "focus": "..."}` generates cited study material from a notebook (same citation check as `ask`).
`POST /v1/tasks` starts any run in the background (202 + `task_id`); `GET /v1/tasks/{id}` polls, `GET /v1/tasks/{id}/events` streams ledger progress as SSE,
`DELETE /v1/tasks/{id}` cancels and closes the run records. Task handles live in memory (a restart loses handles; finished runs remain in `/v1/runs`);
on startup, runs left `running` are marked `interrupted`. `POST /v1/chat/{session}` keeps recent turns plus a deterministic rolling summary as untrusted context;
Slack @mentions in the same thread share one session. Mode prefixes work inside chat.

## Spend caps, document ingest, vault write-back, benchmarking
`max_cost_usd` (API, tasks, chat, MCP, `tier1 run --max-cost`) is a per-request soft cap shared by every call a run makes, including parallel `team` sub-tasks;
it is checked before each model call, so one in-flight call can overshoot. `ralph` stops early and says so (`stopped_early`); results carry a `budget` block.
`POST /v1/kb/{nb}/ingest {"url": ...}` or `{"path": ...}` indexes HTML (nav/footer/script stripped, headings kept), text/Markdown/JSON/CSV and PDFs with a text layer
(`pip install 'tier1-agent[pdf]'`; scanned PDFs need OCR, which is not included). URLs use the same SSRF and redirect checks as `http_get`.
`POST /v1/kb/{nb}/ask` with `save_to_vault: "<dir>"` writes the cited answer as an Obsidian note under `<dir>/Tier1/` with `[[wikilinks]]` to its sources. It never overwrites,
and is refused unless `TIER1_SANDBOX_WRITABLE=1` and the sandbox is mounted read-write (compose mounts it read-only by default).
`tier1 bench tasks.json --modes autopilot,ralph,team` (or `POST /v1/bench`) runs your own prompts through each mode with the cache cleared and reports cost, calls, audit score and
cost per verified answer. With the mock provider the numbers are synthetic; use a real provider, and remember the audit score comes from the pipeline's own auditor.

## Known limits
Not implemented: git-worktree isolated coding agents (Orca-style), semantic/embedding search (retrieval is BM25), OCR and Office-format parsing, Notion write-back, live two-way Obsidian sync (notes are written once; edits are picked up by the vault auto-sync). Slack/notification paths are tested against mock transports, not a live workspace.
Research needs URLs in the prompt (no search backend is bundled). Memory ranking is lexical, not embeddings. SQLite is single-node.
DNS-rebinding between the SSRF check and the fetch is not fully closed; use an egress proxy or `TIER1_HTTP_ALLOWLIST` in production.
# Render production persistence

`render.yaml` defines the production web service and a Render Managed PostgreSQL
database. Applying that Blueprint creates a billable database resource. The
service receives its internal connection string as `TIER1_DATABASE_URL`; no
database credentials belong in Git.

Free Render staging remains SQLite-backed and ephemeral. Use the Blueprint only
when durable production persistence is intended, then set the provider and
other production secrets in the Render Dashboard.

## Local PostgreSQL with Docker

Start a durable local database with:

```powershell
docker compose -f docker-compose.local.yml up -d
```

Then set `TIER1_DATABASE_URL` to
`postgresql://tier1:tier1-local-only@127.0.0.1:5432/tier1` before starting the
app. Stop the database with `docker compose -f docker-compose.local.yml down`;
the named volume preserves local data until it is explicitly removed.
# Phase 2 runtime evidence

Run `python -m tier1.runtime_evidence.proof` (or `phase2-proof` after installing the project). In this checkout it intentionally returns `NOT_OBSERVED` because the real notebook app and runner-owned browser journey are not present. The lower-level package tests exercise local signed process/HTTP records, but those fixtures are not Phase 2 completion evidence and do not prove Hermes enforcement, Tier-1 status, or production behavior.
