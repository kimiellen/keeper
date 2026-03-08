"""
In-memory session manager for single-user auth.

Security notes:
- Token generated via secrets.token_urlsafe(32) — 256-bit entropy
- Sessions expire after SESSION_TTL_SECONDS (default 3600s / 1 hour)
- Only one active session at a time (single-user design)
- Expired sessions are cleaned on every validation call
"""

import hmac
import secrets
import time
from dataclasses import dataclass

SESSION_TTL_SECONDS = 3600
TOKEN_BYTES = 32


@dataclass(slots=True)
class Session:
    token: str
    created_at: float
    expires_at: float


class SessionManager:
    def __init__(self, ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._session: Session | None = None

    def create(self) -> Session:
        now = time.time()
        session = Session(
            token=secrets.token_urlsafe(TOKEN_BYTES),
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._session = session
        return session

    def validate(self, token: str) -> Session | None:
        if self._session is None:
            return None
        # Security: constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(self._session.token, token):
            return None
        if time.time() > self._session.expires_at:
            self._session = None
            return None
        return self._session

    def revoke(self) -> None:
        self._session = None

    @property
    def active_session(self) -> Session | None:
        if self._session is None:
            return None
        if time.time() > self._session.expires_at:
            self._session = None
            return None
        return self._session
