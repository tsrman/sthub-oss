# API contract

The API base is `/api/v1`. Authenticated endpoints use `Authorization: Bearer <access_token>`; `GET /health`, `GET /api/v1/config`, and `POST /api/v1/auth/token` are public. Errors have `{"error":{"code":"validation_error","message":"...","details":{}}}`.

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/health` | `{"status":"ok"}`. |
| GET | `/config` | Public Keycloak `url`, `realm`, `client`. |
| POST | `/auth/token` | Authorization-code or refresh-token exchange; returns `access_token`, `refresh_token`, `expires_in`. |
| GET | `/me` | `login`, `display_name`, `email`, `group`, `is_admin`; example email: `user@example.com`. |
| GET/POST | `/streamlits` | List (optional `status`, `q`, admin `owner`) or create. |
| GET | `/streamlits/check-slug?slug=&exclude_id=` | `slug`, `normalized`, `available`, `url`. |
| GET/PATCH/DELETE | `/streamlits/{app_id}` | Read, update, delete. |
| POST | `/streamlits/{app_id}/run`, `/stop`, `/restart`, `/duplicate` | Lifecycle or copied app; lifecycle returns 202, duplicate 201. |
| GET | `/streamlits/{app_id}/logs?follow=true` | Build logs as SSE; accepts bearer token or `?token=`. |
| GET | `/streamlits/{app_id}/deployments` | App deployment history. |
| POST | `/streamlits/{app_id}/lint`, `/lint` | Syntax-check `{code}`; response `{ok,problems}`. |
| GET | `/streamlits/{app_id}/files` | File summaries. |
| GET/PUT/PATCH/DELETE | `/streamlits/{app_id}/files/{path}` | Read (`base64=true` for binary), create, update, delete. Bodies: `{content,content_type}`. |
| GET | `/deployments` | Current user’s cross-app deployment history. |
| GET | `/allowed-packages` | `{packages:[...]}`. |
| GET/POST | `/ai/status`, `/ai/chat` | Secret-free status and chat SSE. |

Streamlit create fields are `name`, `slug`, optional `description`, `python_version`, `cpu_limit`, `memory_limit_mb`; patch makes them optional. Detail fields include identifiers, status, resources, URLs, version, owner, timestamps, `container_id`, and `image_tag`. File reads include `id`, `path`, `content_type`, `is_entrypoint`, `content`, `updated_at`.

## Validation and lifecycle states

- `slug` is normalized to lowercase `[a-z0-9-]`, is 1–40 characters, and cannot start or end with `-`; `login` uses the same segment syntax and is at most 40 characters.
- `cpu_limit` is 0.1–4.0 cores (default 1.0) and `memory_limit_mb` is 64–4096 (default 512). Both are applied to the app's container; each falls back to the global `CONTAINER_CPU_QUOTA` / `CONTAINER_MEMORY` setting when unset.
- `python_version` is one of `3.10`, `3.11`, or `3.12` (default `3.11`). It is accepted, validated, and stored, but **not yet honoured at build time**: every app is built from `STREAMLIT_BASE_IMAGE` and therefore runs that image's Python. Selecting a version does not change the runtime today.
- Application states are `stopped`, `building`, `running`, and `error`. Runtime settings cannot change while building; run/restart move an app to `building` while the worker acts.
