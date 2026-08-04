# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

STHub hosts user-authored Streamlit applications on a single Docker host. An authenticated
user creates an app, edits its files in the browser, and the platform builds and runs it as
an isolated container published at `/st/{login}/{slug}`.

## Commands

### Backend (`backend/`)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -q
ruff check . && ruff format --check .
```

`pytest.ini` sets `--cov-fail-under=80`, so **a single-module run fails the coverage gate
even when every test passes**. Pass `--no-cov` when running a subset:

```bash
pytest tests/test_validation.py -q --no-cov
pytest tests/test_worker_docker.py::test_run_container_applies_per_app_limits --no-cov
```

`tests/test_files_api.py` and `tests/test_streamlits_api.py` create databases at *collection*
time and need PostgreSQL on `127.0.0.1:5438`; without it the whole suite errors out before
running. Start one:

```bash
docker run -d --name sthub-testdb -e POSTGRES_USER=streamlit \
  -e POSTGRES_PASSWORD=streamlit -e POSTGRES_DB=streamlit_registry \
  -p 127.0.0.1:5438:5432 postgres:16-alpine
```

`alembic check` resolves `DATABASE_URL`, whose default host `db` exists only inside the
Compose network, so run it against the stack: `docker compose run --rm backend alembic check`.

### Frontend (`frontend/`)

```bash
npm ci && npm run lint && npm test && npm run build
npx vitest run src/lib/time.test.ts    # single file
```

### Stack and E2E

```bash
docker build -t streamlit-base:latest ./streamlit-base
docker compose up --build -d
cd e2e && npm ci && npx playwright install chromium && npm test
npx playwright test app-lifecycle.spec.ts        # single spec
```

E2E needs a freshly built `streamlit-base:latest`; a stale local tag silently tests old
dependencies. Ports `3001` and `8080` must be free, or override
`STHUB_BASE_URL` / `STHUB_KEYCLOAK_URL`. `ai-assistant.spec.ts` skips unless `AI_ENABLED=true`.

### Release gate

```bash
python3 -m unittest scripts.tests.test_check_release scripts.tests.test_verify_compose -v
python3 scripts/check_release.py .
docker compose config --format json > /tmp/c.json && python3 scripts/verify_compose.py /tmp/c.json
docker compose -f compose.tls.yaml config --format json > /tmp/t.json && python3 scripts/verify_compose.py --tls /tmp/t.json
pip-audit -r backend/requirements.txt && pip-audit -r streamlit-base/requirements.txt
```

Run `check_release.py` against an exported tree (`git archive HEAD | tar -x -C …`) when using
`--all-files`; on a working copy it reports every venv and cache directory.

## Architecture

### The API never touches Docker

`backend/app/api/` validates requests and owns the registry; it enqueues work through
`services/worker_client.py` onto an arq/Redis queue. Only `backend/app/worker/` imports the
Docker SDK (`worker/docker.py`, `worker/reconciler.py`). Keep it that way — Compose grants the
socket read-write to the worker, read-only to Traefik, and to nobody else, and
`scripts/verify_compose.py` asserts it.

Every job is enqueued as a single arq function, `streamlit_task(kind, streamlit_id, …)` in
`worker/settings.py`, which dispatches to `worker/tasks.py`. Jobs for the same `streamlit_id`
are serialized by a per-id `asyncio.Lock` held in the worker context; different ids run
concurrently. No `_job_id` is passed on purpose — arq silently drops a job whose id matches a
retained result, which would lose the task.

### PostgreSQL is the source of truth

Users, app metadata, files, build logs, and deployment records live in PostgreSQL. Redis holds
only transient jobs. Images and containers are derived artifacts. A cron job
(`worker/reconciler.py`, every :00 and :30) reconciles the two: a `running` app whose container
vanished becomes `stopped`, and an app stuck in `building` past `WORKER_JOB_TIMEOUT` becomes
`error`.

### Two networks

`control-plane` carries Traefik, frontend, backend, worker, PostgreSQL, Redis, and Keycloak.
`streamlit-limited` carries Traefik and user containers only, so user apps cannot resolve
control-plane services. User containers are additionally non-root, capability-dropped,
read-only, and PID/CPU/memory-limited, with tmpfs at `/tmp` and `/streamlit-runtime`.

### Routing

The worker writes Traefik labels and runs each app with
`--server.baseUrlPath=/st/{login}/{slug}`; Traefik discovers the container through the socket.
A newly started container is not routable immediately — E2E helpers retry on the app's own
content rather than on an HTTP status, because the frontend serves a 404 in the gap.

### Redeploy triggers

`_RUNTIME_FIELDS` in `api/streamlits.py` (`slug`, `python_version`, `cpu_limit`,
`memory_limit_mb`) is the set whose mutation requires a rebuild; changing any of them while
the app is `building` is a 409. Per-app `cpu_limit` / `memory_limit_mb` fall back to the
global `CONTAINER_*` settings, and a per-app limit below the global reservation pulls the
reservation down with it (Docker rejects a reservation above the limit).

`python_version` is validated, stored, and returned by the API but **not implemented** — the
worker always builds `FROM ${STREAMLIT_BASE_IMAGE}`. Do not describe it as working.

### Frontend

Next.js App Router SPA. `lib/api.ts` holds the axios instance whose request interceptor
refreshes the Keycloak token before each call and whose response interceptor bounces to
`/login` on 401. `lib/auth.ts` owns the `keycloak-js` singleton; state lives in
`stores/` (zustand). Server components are not used for data — everything is client-side
against `/api/v1`.

## Conventions that will bite

- **English only.** `check_release.py` rejects Cyrillic in any tracked file outside vendored
  Monaco. UI strings, API messages, comments, and test fixtures are all English.
- **No internal hostnames.** The gate matches the *shapes* of corporate infrastructure —
  internal TLDs, multi-label private DNS zones, PKI paths, private registry hosts in `FROM`
  lines — rather than a list of real domains, because listing them would publish the very
  thing the check exists to keep out. `PRIVATE_MARKER_PATTERNS` in `check_release.py` is the
  authority; that file exempts itself, nothing else does, so do not quote the patterns
  elsewhere. Use invented hosts like `registry.example-company.net` in fixtures.
- **`.env.example` must document every `Settings` field** in `backend/app/config.py`; a
  commented-out `# KEY=` counts. The gate diffs them.
- **Versions must agree** across `backend/app/main.py`, `frontend/package.json`,
  `e2e/package.json`, and the newest `## [x.y.z]` in `CHANGELOG.md`.
- **`docs/plans/` and `docs/superpowers/` are rejected.** Agent implementation plans do not
  ship. Design rationale goes in `docs/designs/` and gets linked from the README.
- **`streamlit-base/requirements.txt` is the only place base packages are declared.** Every
  direct dependency needs an exact `==` pin, the Dockerfile installs the file rather than
  listing packages, and `_SAFE_BASE_MINIMUMS` in `check_release.py` sets security floors.
  Keep `ALLOWED_PACKAGES` (`config.py`, `.env.example`) in sync with it.
- **`scripts/` is standard-library only** — no third-party imports, including `packaging`.
- **`ruff` is a runtime dependency**, not a dev one: `services/lint_service.py` shells out to
  it to lint user code. Do not "clean it up" out of `requirements.txt`.
- `backend/pyproject.toml` deliberately pins only `line-length` and `target-version`; widening
  `lint.select` surfaces ~159 pre-existing findings and is a separate change.
- `frontend/eslint.config.mjs` downgrades two React Compiler rules to `warn` for the same
  reason — they flag pre-existing `useEffect` patterns that need a behavioural refactor.
