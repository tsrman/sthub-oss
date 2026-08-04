from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import (
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    Boolean,
    LargeBinary,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.streamlit import StreamlitApp
    from app.models.user import User


class StreamlitFile(Base):
    __tablename__ = "streamlit_files"
    __table_args__ = (
        sa.Index("ix_streamlit_files_streamlit_id", "streamlit_id", unique=False),
        sa.UniqueConstraint(
            "streamlit_id", "path", name="streamlit_files_streamlit_id_path_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    streamlit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("streamlits.id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_entrypoint: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    streamlit: Mapped["StreamlitApp"] = relationship(back_populates="files")

    @property
    def content(self) -> str:
        return self.content_text or ""

    def __repr__(self) -> str:
        return f"<StreamlitFile {self.path}>"


class BuildLog(Base):
    __tablename__ = "build_logs"
    __table_args__ = (
        sa.Index("ix_build_logs_streamlit_id", "streamlit_id", unique=False),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    streamlit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("streamlits.id", ondelete="CASCADE"),
        nullable=False,
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    streamlit: Mapped["StreamlitApp"] = relationship(back_populates="build_logs")

    def __repr__(self) -> str:
        return f"<BuildLog {self.stage}:{self.level}>"


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (
        sa.Index("ix_deployments_streamlit_id", "streamlit_id", unique=False),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    streamlit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("streamlits.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    result: Mapped[str] = mapped_column(String(20), nullable=False)

    streamlit: Mapped["StreamlitApp"] = relationship(back_populates="deployments")
    actor: Mapped["User"] = relationship(back_populates="deployments")

    def __repr__(self) -> str:
        return f"<Deployment {self.kind} v{self.version}>"
