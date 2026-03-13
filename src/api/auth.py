from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from src.api.schemas import (
    AuthInfoResponse,
    InitializeRequest,
    InitializeResponse,
    StatusResponseLocked,
    StatusResponseUnlocked,
    UnlockRequest,
    UnlockResponse,
)
from src.api.session import SessionManager
from src.crypto.kdf import derive_key, hash_password, verify_password
from src.db.models import Authentication
from src.middleware.auth import COOKIE_NAME

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=max_age,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="strict",
    )


@router.post("/initialize", status_code=201, response_model=InitializeResponse)
async def initialize(
    body: InitializeRequest, request: Request
) -> InitializeResponse | Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        existing = await session.execute(
            select(Authentication).where(Authentication.id == 1)
        )
        if existing.scalar_one_or_none() is not None:
            return Response(
                content='{"type":"https://keeper.local/errors/already-initialized","title":"已初始化","status":409,"detail":"数据库已包含认证信息,无法重复初始化"}',
                status_code=409,
                media_type="application/json",
            )

        now = datetime.now(timezone.utc).isoformat()
        auth_record = Authentication(
            id=1,
            email=body.email,
            password_hash=hash_password(body.password),
            created_at=now,
            last_login=now,
        )
        session.add(auth_record)
        await session.commit()

    return InitializeResponse()


@router.get("/info", response_model=AuthInfoResponse)
async def info(request: Request) -> AuthInfoResponse | Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(
            select(Authentication).where(Authentication.id == 1)
        )
        auth = result.scalar_one_or_none()

    if auth is None:
        return Response(
            content='{"type":"https://keeper.local/errors/not-initialized","title":"未初始化","status":400,"detail":"请先调用 /api/auth/initialize"}',
            status_code=400,
            media_type="application/json",
        )

    return AuthInfoResponse(email=auth.email)


@router.post("/unlock", response_model=UnlockResponse)
async def unlock(
    body: UnlockRequest, request: Request, response: Response
) -> UnlockResponse | Response:
    session_factory = request.app.state.session_factory
    session_manager: SessionManager = request.app.state.session_manager

    async with session_factory() as session:
        result = await session.execute(
            select(Authentication).where(Authentication.id == 1)
        )
        auth = result.scalar_one_or_none()

        if auth is None:
            return Response(
                content='{"type":"https://keeper.local/errors/not-initialized","title":"未初始化","status":400,"detail":"请先调用 /api/auth/initialize"}',
                status_code=400,
                media_type="application/json",
            )

        if not verify_password(body.password, auth.password_hash):
            return Response(
                content='{"type":"https://keeper.local/errors/invalid-master-password","title":"主密码错误","status":403,"detail":"主密码不正确"}',
                status_code=403,
                media_type="application/json",
            )

        now = datetime.now(timezone.utc).isoformat()
        auth.last_login = now
        await session.commit()

    encryption_key = derive_key(body.password)
    active_session = session_manager.create(encryption_key)
    _set_session_cookie(
        response,
        active_session.token,
        int(active_session.expires_at - active_session.created_at),
    )

    return UnlockResponse()


@router.post("/lock", status_code=204)
async def lock(request: Request) -> Response:
    session_manager: SessionManager = request.app.state.session_manager
    session_manager.revoke()
    resp = Response(status_code=204)
    _clear_session_cookie(resp)
    return resp


@router.get("/status", response_model=None)
async def status(
    request: Request,
) -> StatusResponseUnlocked | StatusResponseLocked | Response:
    session_manager: SessionManager = request.app.state.session_manager
    token = request.cookies.get(COOKIE_NAME)

    if not token:
        return Response(
            content='{"locked":true}',
            status_code=401,
            media_type="application/json",
        )

    active = session_manager.validate(token)
    if active is None:
        return Response(
            content='{"locked":true}',
            status_code=401,
            media_type="application/json",
        )

    expires_at = datetime.fromtimestamp(active.expires_at, tz=timezone.utc).isoformat()
    return StatusResponseUnlocked(sessionExpiresAt=expires_at)
