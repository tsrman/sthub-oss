"""Validate the isolation and exposure rules of rendered Compose models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_SERVICES = frozenset(
    {"traefik", "db", "redis", "keycloak", "backend", "worker", "frontend"}
)
CONTROL_NETWORK = "control-plane"
USER_NETWORK = "streamlit-limited"
DOCKER_SOCKET = "/var/run/docker.sock"
PUBLIC_REGISTRIES = frozenset(
    {
        "docker.io",
        "index.docker.io",
        "quay.io",
        "ghcr.io",
        "gcr.io",
        "mcr.microsoft.com",
        "registry.k8s.io",
    }
)


def _network_names(service: dict[str, Any]) -> set[str]:
    networks = service.get("networks", {})
    if isinstance(networks, dict):
        return set(networks)
    if isinstance(networks, list):
        return {network for network in networks if isinstance(network, str)}
    return set()


def _socket_mounts(service: dict[str, Any]) -> list[bool]:
    mounts: list[bool] = []
    for volume in service.get("volumes", []):
        if isinstance(volume, dict):
            if volume.get("source") == DOCKER_SOCKET or volume.get("target") == DOCKER_SOCKET:
                mounts.append(bool(volume.get("read_only", False)))
        elif isinstance(volume, str):
            parts = volume.split(":")
            if DOCKER_SOCKET in parts[:2]:
                mounts.append(parts[-1] == "ro")
    return mounts


def _has_private_registry(image: object) -> bool:
    if not isinstance(image, str) or not image:
        return False
    first, separator, _ = image.partition("/")
    if not separator:
        return False
    is_registry = "." in first or ":" in first or first == "localhost"
    return is_registry and first not in PUBLIC_REGISTRIES


def _published_ports(service: dict[str, Any]) -> set[str]:
    ports: set[str] = set()
    for port in service.get("ports", []):
        if isinstance(port, dict) and port.get("published") is not None:
            ports.add(str(port["published"]))
        elif isinstance(port, str):
            ports.add(port.rsplit(":", 1)[-1].split("/", 1)[0])
    return ports


def _non_loopback_publications(service: dict[str, Any]) -> set[str]:
    """Return published ports that are reachable from outside the host.

    ``docker compose config`` omits ``host_ip`` when a port is bound to every
    interface, which is what turns a local-only service into a public one.
    """
    exposed: set[str] = set()
    for port in service.get("ports", []):
        if isinstance(port, dict):
            host_ip = port.get("host_ip") or ""
            published = port.get("published")
        elif isinstance(port, str):
            parts = port.split(":")
            host_ip = parts[0] if len(parts) >= 3 else ""
            published = parts[-1].split("/", 1)[0] if len(parts) >= 2 else None
        else:
            continue
        if published is None:
            continue
        if not host_ip.startswith("127.") and host_ip != "::1":
            exposed.add(str(published))
    return exposed


def validate(model: dict, tls: bool) -> list[str]:
    """Return stable violations for the rendered Compose *model*."""
    services = model.get("services", {})
    if not isinstance(services, dict):
        return ["Compose model services must be an object"]

    errors: list[str] = []
    for name in sorted(REQUIRED_SERVICES - set(services)):
        errors.append(f"missing required service: {name}")

    for name, service in services.items():
        if not isinstance(service, dict):
            errors.append(f"{name} service definition must be an object")
            continue
        networks = _network_names(service)
        if name == "traefik":
            if CONTROL_NETWORK not in networks:
                errors.append("traefik must join the control-plane network")
            if USER_NETWORK not in networks:
                errors.append("traefik must join the user-app network")
        else:
            if USER_NETWORK in networks:
                errors.append(f"{name} must not join the user-app network")
            if networks != {CONTROL_NETWORK}:
                errors.append(f"{name} must join only the control-plane network")

        socket_mounts = _socket_mounts(service)
        if name not in {"traefik", "worker"} and socket_mounts:
            errors.append(f"{name} must not mount the Docker socket")
        if name == "worker":
            if not socket_mounts:
                errors.append("worker must mount the Docker socket")
            elif any(socket_mounts):
                errors.append("worker Docker socket mount must be read-write")
        if name == "traefik":
            if not socket_mounts:
                errors.append("traefik must mount the Docker socket")
            elif any(not read_only for read_only in socket_mounts):
                errors.append("traefik Docker socket mount must be read-only")

        if _has_private_registry(service.get("image")):
            errors.append(f"{name} must not use a private registry image reference")

    published_ports = set().union(
        *(_published_ports(service) for service in services.values() if isinstance(service, dict))
    )
    if tls:
        for name, service in services.items():
            if name != "traefik" and isinstance(service, dict) and _published_ports(service):
                errors.append(f"{name} must not publish a host port in the TLS stack")
        if published_ports != {"443"}:
            errors.append("TLS stack must publish only port 443")
    else:
        # The plain-HTTP stack is for local development: Traefik terminates no
        # TLS and the Keycloak admin console is reachable on its published port,
        # so neither may be bound to a routable interface.
        for name, service in sorted(services.items()):
            if not isinstance(service, dict):
                continue
            for port in sorted(_non_loopback_publications(service)):
                errors.append(
                    f"{name} must publish port {port} on loopback only in the HTTP stack"
                )

    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tls", action="store_true", help="validate TLS-only port exposure")
    parser.add_argument("compose_json", type=Path, help="rendered docker compose JSON file")
    args = parser.parse_args()

    with args.compose_json.open(encoding="utf-8") as compose_file:
        errors = validate(json.load(compose_file), tls=args.tls)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
