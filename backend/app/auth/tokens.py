"""Sign-in tokens, so the API can tell who is calling without keeping sessions in memory."""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt

from app.config import Settings

ALGORITHM = "HS256"

logger = logging.getLogger(__name__)


def create_access_token(user_id: int, *, secret: str, valid_for: timedelta) -> str:
    issued_at = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": int(issued_at.timestamp()),
            "exp": int((issued_at + valid_for).timestamp()),
        },
        secret,
        algorithm=ALGORITHM,
    )


def read_access_token(token: str, *, secret: str) -> int | None:
    """The user id inside a valid token, or None when it is expired, forged or malformed."""
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None


def signing_secret(settings: Settings) -> str:
    return settings.auth_secret_key or _development_secret()


@lru_cache(maxsize=1)
def _development_secret() -> str:
    logger.warning(
        "AUTH_SECRET_KEY is not set, so a temporary one is used: everyone is signed out "
        "when the API restarts. Set it in .env before deploying."
    )
    return secrets.token_urlsafe(32)
