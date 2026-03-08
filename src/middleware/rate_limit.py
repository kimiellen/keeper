import time
from typing import final

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 300
LOCKOUT_SECONDS = 900

RATE_LIMITED_PATHS = frozenset({"/api/auth/unlock"})


@final
class _SlidingWindow:
    __slots__ = ("_attempts", "_locked_until")

    def __init__(self) -> None:
        self._attempts: list[float] = []
        self._locked_until: float = 0.0

    def is_allowed(self) -> bool:
        now = time.monotonic()

        if now < self._locked_until:
            return False

        self._attempts = [t for t in self._attempts if now - t < WINDOW_SECONDS]
        if len(self._attempts) >= MAX_ATTEMPTS:
            self._locked_until = now + LOCKOUT_SECONDS
            self._attempts.clear()
            return False

        return True

    def record(self) -> None:
        self._attempts.append(time.monotonic())

    def reset(self) -> None:
        self._attempts.clear()
        self._locked_until = 0.0

    @property
    def locked_remaining(self) -> float:
        return max(0.0, self._locked_until - time.monotonic())


@final
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._window: _SlidingWindow = _SlidingWindow()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path not in RATE_LIMITED_PATHS:
            return await call_next(request)

        if request.method != "POST":
            return await call_next(request)

        if not self._window.is_allowed():
            remaining = self._window.locked_remaining
            return Response(
                content=f'{{"type":"https://keeper.local/errors/rate-limited","title":"请求过于频繁","status":429,"detail":"请在 {int(remaining)} 秒后重试"}}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(int(remaining))},
            )

        response = await call_next(request)

        if response.status_code == 403:
            self._window.record()
        elif response.status_code == 200:
            self._window.reset()

        return response
