# Configuration

Copy `.env.example` to `.env`. Example credentials are local-only.

## Database

| Setting | Purpose |
| --- | --- |
| `DATABASE_URL` | Registry database URL. |

## Keycloak

| Setting | Purpose |
| --- | --- |
| `KEYCLOAK_URL`, `KEYCLOAK_PUBLIC_URL` | Backend and browser Keycloak URLs. |
| `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT`, `KEYCLOAK_CLIENT_SECRET` | OIDC realm, client, optional server-side secret. |
| `KEYCLOAK_ALLOWED_GROUPS`, `KEYCLOAK_ADMIN_GROUP` | Comma-separated allowed groups and admin group. |
| `KEYCLOAK_VERIFY_SSL` | Verify Keycloak TLS. |
| `KEYCLOAK_ADMIN`, `KEYCLOAK_ADMIN_PASSWORD` | Local Keycloak bootstrap credentials. |

## Networking and queue

| Setting | Purpose |
| --- | --- |
| `REDIS_URL`, `ARQ_QUEUE_NAME` | Worker queue. |
| `WORKER_MAX_JOBS`, `WORKER_JOB_TIMEOUT` | Worker concurrency and seconds timeout. |
| `PUBLIC_HOST` | Optional absolute URL prefix. |
| `DOCKER_HOST` | Worker-only Docker endpoint. |
| `CONTROL_NETWORK`, `DOCKER_NETWORK` | Control and user-app network names. |
| `STREAMLIT_BASE_IMAGE` | App build base image. |
| `TRAEFIK_ENTRYPOINT` | Traefik entrypoint for deployed apps: `web` (HTTP stack) or `websecure` (TLS stack). |

## Container limits

| Setting | Purpose |
| --- | --- |
| `CONTAINER_MEMORY`, `CONTAINER_MEMORY_RESERVATION` | App memory limit/reservation. |
| `CONTAINER_CPU_QUOTA`, `CONTAINER_CPU_PERIOD` | CPU quota and period. |
| `CONTAINER_PIDS_LIMIT` | Process limit. |
| `CONTAINER_TMPFS_SIZE` | Size of the writable `/tmp` tmpfs mount (default: `64m`). |
| `CONTAINER_TMPFS_RUNTIME_SIZE` | Size of the writable `/streamlit-runtime` tmpfs mount (default: `32m`). |

User containers use Docker's `unless-stopped` restart policy. Docker healthchecks probe each app's Streamlit endpoint at `/st/{login}/{slug}/_stcore/health` every 10 seconds, with a 3-second timeout, 5 retries, and a 20-second start period.

## Quotas

| Setting | Purpose |
| --- | --- |
| `MAX_RUNNING_APPS_PER_USER`, `MAX_FILES_PER_STREAMLIT` | Per-user app and per-app file quotas. |
| `MAX_FILE_SIZE_BYTES`, `MAX_CODE_SIZE`, `MAX_REQUIREMENTS_SIZE` | File, lint-code, and requirements byte limits. |
| `ALLOWED_PACKAGES` | Comma-separated pip allowlist. |

## CORS/public URL

| Setting | Purpose |
| --- | --- |
| `CORS_ALLOW_ORIGINS` | Comma-separated browser origins; avoid `*` in production. |

## AI

| Setting | Purpose |
| --- | --- |
| `AI_ENABLED` | Disabled by default. |
| `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` | Self-hosted OpenAI-compatible gateway configuration; backend-only. |
| `AI_MAX_TOKENS`, `AI_TIMEOUT` | Completion and timeout limits. |
| `AI_CA_CERT`, `AI_VERIFY_SSL` | Custom CA path and TLS verification. |
| `AI_MAX_CONTEXT_CHARS` | Maximum open-file context characters. |
| `AI_SYSTEM_PROMPT` | System prompt for the assistant; the built-in default is English. Override to change persona, house style, or response language. |

The current open file's code context is sent to the configured AI gateway when the user includes it in an assistant request. Review the gateway's data handling before enabling this feature.
