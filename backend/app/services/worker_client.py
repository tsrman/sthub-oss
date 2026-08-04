from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings

from app.config import Settings, get_settings


class WorkerClient:
    """Client that enqueues jobs for the Build/Run Worker."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings if settings is not None else get_settings()

    def _redis_settings(self) -> RedisSettings:
        return RedisSettings.from_dsn(self.settings.REDIS_URL)

    async def enqueue_build_run(self, streamlit_id: UUID) -> str:
        """Enqueue a build+run job for the given streamlit."""
        return await self._enqueue("build_run", streamlit_id)

    async def enqueue_stop(self, streamlit_id: UUID) -> str:
        """Enqueue a stop job for the given streamlit."""
        return await self._enqueue("stop", streamlit_id)

    async def enqueue_remove(
        self,
        streamlit_id: UUID,
        container_id: str | None,
        image_tag: str | None,
    ) -> str:
        """Enqueue a remove job for the given streamlit."""
        return await self._enqueue(
            "remove",
            streamlit_id,
            container_id,
            image_tag,
        )

    async def _enqueue(self, kind: str, streamlit_id: UUID, *args) -> str:
        pool = await create_pool(self._redis_settings())
        try:
            # No _job_id is passed on purpose: arq silently drops the job when
            # a job/result with the same ID already exists (results are kept
            # for an hour by default), which would lose the task. Tasks for
            # the same streamlit_id are serialized inside the worker instead.
            job = await pool.enqueue_job(
                "streamlit_task",
                kind,
                str(streamlit_id),
                *args,
                _queue_name=self.settings.ARQ_QUEUE_NAME,
            )
            if job is None:
                raise RuntimeError(
                    f"failed to enqueue {kind} task for streamlit {streamlit_id}"
                )
            return job.job_id
        finally:
            await pool.close()
