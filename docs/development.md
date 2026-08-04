# Development

Frontend tooling requires Node.js **>=20.19.0**. The CI `20` setup and the
Docker `node:20-alpine` base use the maintained mutable Node 20 release line,
which satisfies this floor.

## Backend

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -q
ruff check .
ruff format --check .
```

`tests/test_files_api.py` and `tests/test_streamlits_api.py` are integration tests
that need PostgreSQL on `127.0.0.1:5438` with the `streamlit`/`streamlit` role.
Start one before running the full suite:

```bash
docker run -d --name sthub-testdb -e POSTGRES_USER=streamlit \
  -e POSTGRES_PASSWORD=streamlit -e POSTGRES_DB=streamlit_registry \
  -p 127.0.0.1:5438:5432 postgres:16-alpine
```

`alembic check` resolves `DATABASE_URL`, whose default hostname `db` only exists
inside the Compose network, so run it against the running stack rather than from
a host virtualenv:

```bash
docker compose run --rm backend alembic check
```

## Frontend

```bash
cd frontend
npm ci
npm test
npm run build
```

## Compose and E2E

```bash
docker compose config --format json > /tmp/sthub-compose.json
python3 scripts/verify_compose.py /tmp/sthub-compose.json
docker compose -f compose.tls.yaml config --format json > /tmp/sthub-compose-tls.json
python3 scripts/verify_compose.py --tls /tmp/sthub-compose-tls.json
docker build -t streamlit-base:latest ./streamlit-base
docker compose up --build -d
cd e2e && npm ci && npx playwright install chromium && npm test
```

## Release hygiene

```bash
python3 -m unittest scripts.tests.test_check_release scripts.tests.test_verify_compose -v
python3 scripts/check_release.py .
git diff --check
```
