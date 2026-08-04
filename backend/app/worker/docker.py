from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import docker
from docker.errors import APIError, BuildError, ContainerError, ImageNotFound, NotFound

from app.config import Settings

logger = logging.getLogger(__name__)

_MEMORY_UNITS = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}


def _memory_bytes(value: str) -> int:
    """Parse a Docker memory string such as ``512m`` or ``1g`` into bytes."""
    text = value.strip().lower()
    if not text:
        return 0
    unit = _MEMORY_UNITS.get(text[-1])
    if unit is None:
        return int(text)
    return int(text[:-1]) * unit


class DockerManager:
    """Build and run Streamlit apps in isolated Docker containers."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: docker.DockerClient | None = None

    def _client_sync(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.DockerClient(base_url=self.settings.DOCKER_HOST)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await asyncio.to_thread(self._client.close)
            self._client = None

    def _image_tag(self, login: str, slug: str, version: int) -> str:
        return f"sthub/{login}-{slug}:{version}"

    def _container_name(self, streamlit_id: UUID) -> str:
        return f"sthub-{streamlit_id}"

    def _memory_limits(
        self, memory_limit_mb: int | None
    ) -> tuple[str | int, str | int]:
        """Resolve the container's memory limit and reservation.

        Docker rejects a reservation above the limit, so a per-app limit below the
        global reservation pulls the reservation down with it.
        """
        if not memory_limit_mb:
            return (
                self.settings.CONTAINER_MEMORY,
                self.settings.CONTAINER_MEMORY_RESERVATION,
            )
        limit = memory_limit_mb * 1024 * 1024
        reservation = min(
            _memory_bytes(self.settings.CONTAINER_MEMORY_RESERVATION), limit
        )
        return limit, reservation

    def _cpu_quota(self, cpu_limit: float | None) -> int:
        """Convert a per-app core count into a CFS quota, or fall back to the global one."""
        if not cpu_limit:
            return self.settings.CONTAINER_CPU_QUOTA
        return max(1, int(cpu_limit * self.settings.CONTAINER_CPU_PERIOD))

    def _labels(self, login: str, slug: str, streamlit_id: UUID) -> dict[str, str]:
        url_path = f"/st/{login}/{slug}"
        rule = f"PathPrefix(`{url_path}`)"
        return {
            "traefik.enable": "true",
            f"traefik.http.routers.st-{streamlit_id}.rule": rule,
            f"traefik.http.routers.st-{streamlit_id}.entrypoints": (
                self.settings.TRAEFIK_ENTRYPOINT
            ),
            f"traefik.http.services.st-{streamlit_id}.loadbalancer.server.port": "8501",
            "sthub.user": login,
            "sthub.app": slug,
            "sthub.streamlit_id": str(streamlit_id),
        }

    def _write_context(
        self,
        tmpdir: Path,
        files: dict[str, str | bytes],
        requirements: str,
        base_url_path: str,
    ) -> None:
        dockerfile = (
            f"FROM {self.settings.STREAMLIT_BASE_IMAGE}\n"
            "WORKDIR /app\n"
            "COPY requirements.txt .\n"
            # The base image sets USER streamlit; installing packages needs
            # root, and the base image is PEP 668 managed (hence
            # --break-system-packages).
            "USER root\n"
            "RUN pip install --no-cache-dir --break-system-packages"
            " -r requirements.txt\n"
            "COPY . /app\n"
            "EXPOSE 8501\n"
            "USER streamlit\n"
            f'CMD ["streamlit", "run", "app.py", '
            f'"--server.port=8501", '
            f'"--server.address=0.0.0.0", '
            f'"--server.baseUrlPath={base_url_path}"]\n'
        )
        (tmpdir / "Dockerfile").write_text(dockerfile, encoding="utf-8")
        (tmpdir / "requirements.txt").write_text(requirements, encoding="utf-8")
        for path, content in files.items():
            target = tmpdir / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                target.write_text(content, encoding="utf-8")
            else:
                target.write_bytes(content)

    @staticmethod
    def _is_stale_cache_export_error(error: BuildError) -> bool:
        message = str(error).casefold()
        return "failed to export image" in message and "no such image" in message

    async def build_image(
        self,
        streamlit_id: UUID,
        login: str,
        slug: str,
        version: int,
        files: dict[str, str | bytes],
        requirements: str,
    ) -> dict[str, Any]:
        """Build a Docker image and return metadata about the build."""
        tag = self._image_tag(login, slug, version)
        base_url_path = f"/st/{login}/{slug}"

        with tempfile.TemporaryDirectory(prefix=f"sthub-build-{streamlit_id}-") as td:
            tmpdir = Path(td)
            await asyncio.to_thread(
                self._write_context, tmpdir, files, requirements, base_url_path
            )

            logs: list[str] = []

            def collect(build_log: Any) -> None:
                for line in build_log:
                    if isinstance(line, dict):
                        log_text = line.get("stream") or json.dumps(line)
                    else:
                        log_text = str(line)
                    if log_text.strip():
                        logs.append(log_text.strip())

            build_args = {
                "path": str(tmpdir),
                "tag": tag,
                "rm": True,
                "forcerm": True,
                "network_mode": self.settings.DOCKER_NETWORK,
            }
            try:
                image, build_log = await asyncio.to_thread(
                    self._client_sync().images.build, **build_args
                )
                collect(build_log)
            except BuildError as exc:
                collect(exc.build_log)
                if self._is_stale_cache_export_error(exc):
                    try:
                        image, build_log = await asyncio.to_thread(
                            self._client_sync().images.build,
                            **(build_args | {"nocache": True}),
                        )
                        collect(build_log)
                    except BuildError as retry_error:
                        collect(retry_error.build_log)
                        return {
                            "success": False,
                            "image_tag": tag,
                            "image_id": None,
                            "logs": logs,
                            "error": str(retry_error),
                        }
                else:
                    return {
                        "success": False,
                        "image_tag": tag,
                        "image_id": None,
                        "logs": logs,
                        "error": str(exc),
                    }

            return {
                "success": True,
                "image_tag": tag,
                "image_id": image.id,
                "logs": logs,
                "error": None,
            }

    async def run_container(
        self,
        streamlit_id: UUID,
        login: str,
        slug: str,
        version: int,
        cpu_limit: float | None = None,
        memory_limit_mb: int | None = None,
    ) -> dict[str, Any]:
        """Run a container from the built image and return its id.

        ``cpu_limit`` (in cores) and ``memory_limit_mb`` are the app's own limits;
        each falls back to the corresponding global ``CONTAINER_*`` setting.
        """
        tag = self._image_tag(login, slug, version)
        name = self._container_name(streamlit_id)
        labels = self._labels(login, slug, streamlit_id)
        mem_limit, mem_reservation = self._memory_limits(memory_limit_mb)
        cpu_quota = self._cpu_quota(cpu_limit)
        healthcheck = {
            "test": [
                "CMD",
                "python",
                "-c",
                "import urllib.request; urllib.request.urlopen("
                f"'http://127.0.0.1:8501/st/{login}/{slug}/_stcore/health', "
                "timeout=3)",
            ],
            "interval": 10_000_000_000,
            "timeout": 3_000_000_000,
            "retries": 5,
            "start_period": 20_000_000_000,
        }

        # Remove any stale container with the same name (e.g. left behind by a
        # crashed run) so a retry does not fail with a 409 name conflict.
        try:
            existing = await asyncio.to_thread(self._client_sync().containers.get, name)
        except NotFound:
            existing = None
        if existing is not None:
            try:
                await asyncio.to_thread(existing.remove, force=True)
            except Exception as exc:
                logger.warning("Could not remove stale container %s: %s", name, exc)

        try:
            container = await asyncio.to_thread(
                self._client_sync().containers.run,
                tag,
                name=name,
                detach=True,
                labels=labels,
                network=self.settings.DOCKER_NETWORK,
                mem_limit=mem_limit,
                mem_reservation=mem_reservation,
                cpu_quota=cpu_quota,
                cpu_period=self.settings.CONTAINER_CPU_PERIOD,
                pids_limit=self.settings.CONTAINER_PIDS_LIMIT,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                tmpfs={
                    "/tmp": f"rw,noexec,nosuid,size={self.settings.CONTAINER_TMPFS_SIZE}",
                    "/streamlit-runtime": (
                        "rw,noexec,nosuid,"
                        f"size={self.settings.CONTAINER_TMPFS_RUNTIME_SIZE}"
                    ),
                },
                read_only=True,
                restart_policy={"Name": "unless-stopped"},
                healthcheck=healthcheck,
                environment={
                    "STREAMLIT_SERVER_ENABLE_STATIC_SERVING": "true",
                },
            )
        except (ContainerError, ImageNotFound, APIError) as exc:
            return {
                "success": False,
                "container_id": None,
                "error": str(exc),
            }

        return {
            "success": True,
            "container_id": container.id,
            "error": None,
        }

    async def stop_container(self, container_id: str) -> dict[str, Any]:
        """Stop and remove a container."""
        try:
            container = await asyncio.to_thread(
                self._client_sync().containers.get, container_id
            )
            await asyncio.to_thread(container.stop, timeout=10)
            await asyncio.to_thread(container.remove, force=True)
        except NotFound:
            logger.warning("Container %s not found during stop", container_id)
        except Exception as exc:  # pragma: no cover
            return {"success": False, "error": str(exc)}

        return {"success": True, "error": None}

    async def remove_container(self, container_id: str | None) -> dict[str, Any]:
        """Remove a container if it exists."""
        if not container_id:
            return {"success": True, "error": None}
        return await self.stop_container(container_id)

    async def remove_image(self, image_tag: str | None) -> dict[str, Any]:
        """Remove a built image if it exists."""
        if not image_tag:
            return {"success": True, "error": None}
        try:
            await asyncio.to_thread(
                self._client_sync().images.remove, image_tag, force=True
            )
        except NotFound:
            logger.warning("Image %s not found during remove", image_tag)
        except Exception as exc:  # pragma: no cover
            return {"success": False, "error": str(exc)}

        return {"success": True, "error": None}

    async def stream_logs(self, container_id: str, tail: int = 100) -> list[str]:
        """Return the last ``tail`` lines of container logs."""
        try:
            container = await asyncio.to_thread(
                self._client_sync().containers.get, container_id
            )
            raw = await asyncio.to_thread(
                container.logs,
                tail=tail,
                timestamps=False,
                stdout=True,
                stderr=True,
            )
        except NotFound:
            return []

        text = raw.decode("utf-8", errors="replace")
        return [line for line in text.splitlines() if line]
