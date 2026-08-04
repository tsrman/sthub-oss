# Contributing

Open an issue before substantial work; use [SECURITY.md](SECURITY.md) instead of public issues for vulnerabilities. Follow [development](docs/development.md), branch from `main`, use focused imperative commits, and use the pull request template. DCO sign-off is not required.

## Setup

Install backend dependencies with `cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt`. Install frontend dependencies with `cd frontend && npm ci`. Use `cp .env.example .env` and the local Compose stack for integration or E2E work.

## Test matrix

| Change area | Verification |
| --- | --- |
| Backend | `pytest tests/ -q`, `ruff check .`, `ruff format --check .` from `backend`. The two API test modules need PostgreSQL on `127.0.0.1:5438` — see [development](docs/development.md). |
| Migrations | `docker compose run --rm backend alembic check` against the running stack. |
| Frontend | `npm run lint`, `npm test`, and `npm run build` from `frontend`. |
| Compose/networking | Render both Compose files and run `scripts/verify_compose.py`. |
| E2E | Build the base image, start Compose, then `npm test` from `e2e`. |
| Python dependencies | Run `pip-audit -r backend/requirements.txt` and `pip-audit -r streamlit-base/requirements.txt`; base-image changes also require a clean `streamlit-base` Docker build. |
| Release files | `python3 scripts/check_release.py .` and `git diff --check`. |
