from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

COOKIE_NAME = "keeper_session"

AUTH_EXEMPT_PATHS = frozenset(
    {
        "/api/auth/initialize",
        "/api/auth/unlock",
        "/api/auth/status",
        "/api/health",
        "/",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        if request.url.path in AUTH_EXEMPT_PATHS:
            return await call_next(request)

        session_manager = request.app.state.session_manager
        token = request.cookies.get(COOKIE_NAME)

        if not token or not session_manager.validate(token):
            return Response(
                content='{"locked":true}',
                status_code=401,
                media_type="application/json",
            )

        return await call_next(request)
