# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-04

Initial public release.

### Added

- Self-service hosting for isolated Streamlit applications on a single Docker
  host, published at `/st/{login}/{slug}`.
- Next.js SPA with a Monaco-based editor, file tree, build-log streaming, an
  application registry with filters, deployment history, and starter templates.
- FastAPI control API with Keycloak OIDC authentication, group-based access and
  admin roles, per-user quotas, and a package allowlist.
- Docker worker that serializes lifecycle jobs per application, builds images,
  and runs containers non-root, read-only, capability-dropped, and resource
  limited. Per-application CPU and memory limits are applied to the container.
- Optional AI coding assistant backed by a self-hosted OpenAI-compatible
  gateway; disabled by default and never exposed to the browser.
- Plain-HTTP and TLS Compose stacks, with `scripts/verify_compose.py` enforcing
  network isolation, Docker-socket scope, registry, and port-exposure invariants.

### Known limitations

- `python_version` is accepted and stored but not yet honoured at build time;
  every application is built from `STREAMLIT_BASE_IMAGE`.
- Single Docker host only. No high availability, multi-host scheduling, or
  automatic failover.

[Unreleased]: https://github.com/tsrman/sthub-oss/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tsrman/sthub-oss/releases/tag/v0.1.0
