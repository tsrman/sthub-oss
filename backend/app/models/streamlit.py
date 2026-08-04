from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Float, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.streamlit_file import BuildLog, Deployment, StreamlitFile


class StreamlitApp(Base):
    __tablename__ = "streamlits"
    __table_args__ = (
        sa.Index("ix_streamlits_status", "status", unique=False),
        sa.Index("ix_streamlits_user_id", "user_id", unique=False),
        sa.UniqueConstraint("user_id", "slug", name="uq_streamlits_owner_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="stopped"
    )
    container_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    python_version: Mapped[str] = mapped_column(String(10), nullable=False)
    cpu_limit: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # e.g. 0.5, 1.0, 2.0
    memory_limit_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)  # MB
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)  # legacy
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    owner: Mapped["User"] = relationship(back_populates="streamlits")
    files: Mapped[list["StreamlitFile"]] = relationship(
        back_populates="streamlit", cascade="all, delete-orphan"
    )
    build_logs: Mapped[list["BuildLog"]] = relationship(
        back_populates="streamlit", cascade="all, delete-orphan"
    )
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="streamlit", cascade="all, delete-orphan"
    )

    @property
    def url_path(self) -> str:
        login = self.owner.login if self.owner else "unknown"
        return f"/st/{login}/{self.slug}"

    @property
    def public_url(self) -> str:
        base = get_settings().PUBLIC_HOST.rstrip("/")
        return f"{base}{self.url_path}" if base else self.url_path

    def __repr__(self) -> str:
        return f"<StreamlitApp {self.name} ({self.status})>"
