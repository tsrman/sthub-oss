# Deployment

## HTTP quick start

```bash
cp .env.example .env
docker build -t streamlit-base:latest ./streamlit-base
docker compose up --build -d
```

The local HTTP stack is at `http://localhost:3001`. Replace all local-only credentials and set explicit CORS origins for shared use.

## TLS

```bash
./certs/generate-certs.sh
docker build -t streamlit-base:latest ./streamlit-base
docker compose -f compose.tls.yaml up --build -d
```

Trust `certs/local.crt` only for local testing. The TLS Compose stack publishes only port 443. In production mount trusted certificates; never commit certificate private keys.

## External Keycloak

Use a production Keycloak deployment, configure backend and public URLs, realm, redirect URIs, allowed/admin groups, client secret, and TLS verification. Do not use fixture or bootstrap accounts.

## Backup, restore, and migrations

```bash
docker compose exec -T db pg_dump -U streamlit -d streamlit_registry > sthub.sql
docker compose exec -T db psql -U streamlit -d streamlit_registry < sthub.sql
docker compose run --rm backend alembic upgrade head
```

Backups contain code and logs. Back up and test restoration before migrations or upgrades.

## Image upgrades and hardening

Rebuild `streamlit-base:latest` whenever its Dockerfile, Python version, Streamlit version, or system dependencies change. Rebuild backend, worker, and frontend images, then test a representative application before rollout.

## Production hardening checklist

- Use trusted TLS and restrict host ingress to Traefik.
- Replace all fixture and bootstrap credentials; set explicit CORS and public URLs.
- Keep Docker socket access read-write only for the worker and read-only for Traefik.
- Preserve control-plane/user-app network isolation and container resource limits.
- Back up and protect PostgreSQL data, then rehearse restore operations.
- Keep AI disabled unless a reviewed self-hosted compatible gateway and protected credentials are available.
