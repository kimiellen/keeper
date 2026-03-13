import hmac
import secrets
import time
from dataclasses import dataclass, field

SESSION_TTL_SECONDS = 3600
TOKEN_BYTES = 32


@dataclass(slots=True)
class Session:
    token: str
    created_at: float
    expires_at: float
    encryption_key: bytes = field(default_factory=bytes)


class SessionManager:
    def __init__(self, ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._session: Session | None = None

    def create(self, encryption_key: bytes) -> Session:
        now = time.time()
        session = Session(
            token=secrets.token_urlsafe(TOKEN_BYTES),
            created_at=now,
            expires_at=now + self._ttl,
            encryption_key=encryption_key,
        )
        self._session = session
        return session

    def validate(self, token: str) -> Session | None:
        if self._session is None:
            return None
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

    @property
    def encryption_key(self) -> bytes | None:
        session = self.active_session
        if session is None:
            return None
        return session.encryption_key
