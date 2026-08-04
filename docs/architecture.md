# Architecture

## Components

```text
Browser -> Traefik -> Frontend SPA
                  -> Control API -> PostgreSQL
                                   -> Redis/arq -> Worker -> Docker
Traefik <- streamlit-limited <- user Streamlit containers
```

The API validates requests and owns the registry. The worker serializes lifecycle jobs by streamlit ID, reads stored files, builds `sthub/{login}-{slug}:{version}`, and runs the image with `--server.baseUrlPath=/st/{login}/{slug}`.

## Networks

| Network | Members | Purpose |
| --- | --- | --- |
| `control-plane` | Traefik, frontend, backend, worker, PostgreSQL, Redis, Keycloak | Control traffic. |
| `streamlit-limited` | Traefik and user apps | Published application traffic only. |

User containers cannot resolve control-plane services.

## Docker socket access

| Component | Access |
| --- | --- |
| Worker | read-write: build/run/stop/remove apps. |
| Traefik | read-only: discover routing labels. |
| API, frontend, user apps | none. |

## User-container invariants

User containers are non-root, capability-dropped, read-only, PID/CPU/memory-limited, have no Docker socket, and only the limited network. Docker runs each app with the `unless-stopped` restart policy and an HTTP healthcheck for that app's `/st/{login}/{slug}/_stcore/health` endpoint. The writable tmpfs mounts are `/tmp` (sized by `CONTAINER_TMPFS_SIZE`) and `/streamlit-runtime` (sized by `CONTAINER_TMPFS_RUNTIME_SIZE`).

## Data ownership and limits

PostgreSQL is the source of truth for users, application metadata, files, build logs, and deployment records. Redis holds transient worker jobs. Docker images and containers are derived artifacts that can be rebuilt from PostgreSQL. Keycloak owns credentials and group membership.

## Single-host limitations

The deployment has one Docker Engine, PostgreSQL volume, Redis service, and worker. It does not provide high availability, multi-host scheduling, or automatic failover. Back up PostgreSQL and test restoration before upgrades.
