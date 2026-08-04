# End-to-end tests

Start the root stack, then run:

```bash
docker build -t streamlit-base:latest ./streamlit-base
docker compose up --build -d
cd e2e
npm ci
npx playwright install chromium
npm test
```

By default the suite uses `STHUB_BASE_URL=http://localhost:3001` and
`STHUB_KEYCLOAK_URL=http://localhost:8080`. Override both when the local ports
are occupied, for example:

```bash
STHUB_BASE_URL=http://localhost:33001 \
STHUB_KEYCLOAK_URL=http://localhost:38080 \
npm test
```

The fixture accounts are **local-only**: `testuser` / `testpass` for regular-user tests and `adminuser` / `adminpass` for administrator tests. Do not reuse them outside the local fixture.

## Test files

| File | Purpose |
| --- | --- |
| `auth.spec.ts`, `auth-negative.spec.ts` | Successful and rejected Keycloak login. |
| `registry.spec.ts`, `admin.spec.ts`, `history-filters.spec.ts` | Registry search, owner filtering, and history filters. |
| `create-validation.spec.ts`, `app-lifecycle.spec.ts`, `build-error.spec.ts` | Create validation, run/stop/delete, and build failures. |
| `editor-templates.spec.ts`, `editor-files.spec.ts`, `settings.spec.ts` | Templates, files, and settings. |
| `logs.spec.ts` | Build-log SSE controls. |
| `ai-assistant.spec.ts` | Optional assistant SSE test. |

## Optional AI test

The AI test requires a reachable self-hosted OpenAI-compatible gateway. Set `AI_ENABLED=true`, `AI_BASE_URL`, `AI_API_KEY`, and `AI_MODEL` in the root `.env`, then restart the backend. Do not add a third-party hosted-model dependency to the test setup.
