import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from rivon.db import Base, BaseMixin, TenantScopedMixin


class Region(StrEnum):
    EU = "eu"
    NON_EU = "non_eu"


class TenantStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class UserRole(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    AGENT = "agent"


def _string_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    # VARCHAR + CHECK rather than a native Postgres enum: adding a value later
    # is a plain constraint swap instead of ALTER TYPE.
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=16,
        values_callable=lambda members: [m.value for m in members],
    )


class Tenant(BaseMixin, Base):
    """The tenancy root. Its `id` is the `tenant_id` every other table carries,
    so its RLS policy keys on `id` rather than a `tenant_id` column."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(63), unique=True)
    # Set at provisioning. Decides where the tenant's data lives (spec §15.6);
    # changing it is a data migration, not an update.
    region: Mapped[Region] = mapped_column(_string_enum(Region, "region"))
    status: Mapped[TenantStatus] = mapped_column(
        _string_enum(TenantStatus, "status"), server_default=TenantStatus.PENDING.value
    )


class User(BaseMixin, TenantScopedMixin, Base):
    __tablename__ = "users"

    # Globally unique: owners sign in with email alone, before the tenant is
    # known. Stored lowercased so uniqueness is case-insensitive.
    email: Mapped[str] = mapped_column(String(320))
    # Argon2 hash, or UNUSABLE_PASSWORD until the user sets one.
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(_string_enum(UserRole, "role"))

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            UniqueConstraint("email"),
            CheckConstraint("email = lower(email)", name="email_lowercase"),
        )


class RefreshToken(BaseMixin, TenantScopedMixin, Base):
    """One refresh token. Each refresh revokes the token and issues the next in
    the same family; presenting a revoked token revokes the whole family."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID]
    # SHA-256 of the secret part; the token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            UniqueConstraint("tenant_id", "token_hash"),
            Index("ix_refresh_tokens_tenant_id_family_id", "tenant_id", "family_id"),
            Index("ix_refresh_tokens_tenant_id_user_id", "tenant_id", "user_id"),
        )


class PasswordResetToken(BaseMixin, TenantScopedMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(UniqueConstraint("tenant_id", "token_hash"))
