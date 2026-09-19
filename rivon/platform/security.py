"""Password hashing, opaque tokens and access-token JWTs. No I/O here."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from rivon.platform.models import UserRole

_hasher = PasswordHash((Argon2Hasher(),))

# Stored for accounts that have never set a password. Matches no input.
UNUSABLE_PASSWORD = "!"

# Verified against when there is no real hash to check, so "no such user"
# takes as long as "wrong password" and response time doesn't reveal accounts.
_DUMMY_HASH = _hasher.hash("rivon-timing-equaliser")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> tuple[bool, str | None]:
    """Returns (matches, new_hash). `new_hash` is set when hashing parameters
    have changed and the stored hash should be replaced."""
    if stored_hash == UNUSABLE_PASSWORD:
        burn_password_check(password)
        return False, None
    return _hasher.verify_and_update(password, stored_hash)


def burn_password_check(password: str) -> None:
    _hasher.verify(password, _DUMMY_HASH)


# --- Opaque tokens (refresh, password reset) ----------------------------------
#
# Format: "<tenant_id>.<secret>". The tenant ID lets us open a tenant-scoped
# transaction before looking the token up, so RLS applies to token lookups
# too. Only SHA-256(secret) is stored. Tampering with the tenant part just
# means the hash is looked for in the wrong tenant and not found.


@dataclass(frozen=True)
class OpaqueToken:
    tenant_id: uuid.UUID
    secret: str

    @property
    def value(self) -> str:
        return f"{self.tenant_id}.{self.secret}"

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.secret.encode()).hexdigest()


def new_opaque_token(tenant_id: uuid.UUID) -> OpaqueToken:
    return OpaqueToken(tenant_id=tenant_id, secret=secrets.token_urlsafe(32))


def parse_opaque_token(value: str) -> OpaqueToken | None:
    tenant_part, _, secret = value.partition(".")
    if not secret or len(secret) > 128:
        return None
    try:
        tenant_id = uuid.UUID(tenant_part)
    except ValueError:
        return None
    return OpaqueToken(tenant_id=tenant_id, secret=secret)


# --- Access tokens (JWT) ------------------------------------------------------

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "rivon"
JWT_AUDIENCE = "rivon-api"
ACCESS_TOKEN_TYPE = "access"


@dataclass(frozen=True)
class Principal:
    """Who is calling, as proven by a verified access token."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: UserRole


def create_access_token(
    principal: Principal, secret: str, ttl_seconds: int, now: datetime | None = None
) -> str:
    issued_at = now or datetime.now(UTC)
    claims = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "typ": ACCESS_TOKEN_TYPE,
        "sub": str(principal.user_id),
        "tid": str(principal.tenant_id),
        "role": principal.role.value,
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> Principal:
    """Raises jwt.InvalidTokenError for anything but a valid, unexpired access token."""
    claims = jwt.decode(
        token,
        secret,
        algorithms=[JWT_ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        options={"require": ["exp", "iat", "sub", "tid", "role", "typ"]},
    )
    if claims["typ"] != ACCESS_TOKEN_TYPE:
        raise jwt.InvalidTokenError("not an access token")
    try:
        return Principal(
            user_id=uuid.UUID(claims["sub"]),
            tenant_id=uuid.UUID(claims["tid"]),
            role=UserRole(claims["role"]),
        )
    except ValueError as exc:
        raise jwt.InvalidTokenError("malformed claims") from exc
