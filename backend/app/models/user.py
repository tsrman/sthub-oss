from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.streamlit import StreamlitApp
    from app.models.streamlit_file import Deployment


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        sa.Index("ix_users_keycloak_sub", "keycloak_sub", unique=False),
        sa.UniqueConstraint("keycloak_sub", name="users_keycloak_sub_key"),
        sa.UniqueConstraint("login", name="uq_users_login"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    keycloak_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    login: Mapped[str] = mapped_column(String(40), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    streamlits: Mapped[list["StreamlitApp"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="actor", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.login}>"
