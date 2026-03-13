from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request, Response

from src.api.schemas import (
    DatabaseCreateRequest,
    DatabaseCreateResponse,
    DatabaseInfo,
    DatabaseListResponse,
    DatabaseOpenRequest,
    DatabaseOpenResponse,
    DatabaseRemoveRequest,
)
from src.api.session import SessionManager
from src.crypto.kdf import hash_password
from src.db.config import DatabaseConfig
from src.db.engine import DatabaseManager
from src.db.models import Authentication
from src.middleware.auth import COOKIE_NAME

router = APIRouter(prefix="/api/db", tags=["database"])


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="strict",
    )


@router.get("/list", response_model=DatabaseListResponse)
async def list_databases(request: Request) -> DatabaseListResponse:
    db_config: DatabaseConfig = request.app.state.db_config
    raw = db_config.get_databases()

    existing = [db for db in raw if Path(db["path"]).exists()]

    if len(existing) < len(raw):
        config = db_config.load()
        config["databases"] = existing
        if config.get("current") and not Path(config["current"]).exists():
            config["current"] = None
        db_config.save(config)

    databases = [DatabaseInfo(path=db["path"], name=db["name"]) for db in existing]
    current = db_config.get_current()

    return DatabaseListResponse(
        databases=databases,
        current=current,
    )


@router.post("/open", response_model=DatabaseOpenResponse)
async def open_database(
    body: DatabaseOpenRequest, request: Request
) -> DatabaseOpenResponse | Response:
    path = str(Path(body.path.strip()).expanduser())

    if not Path(path).exists():
        return Response(
            content='{"type":"https://keeper.local/errors/db-not-found","title":"数据库文件不存在","status":404,"detail":"指定路径的数据库文件不存在"}',
            status_code=404,
            media_type="application/json",
        )

    db_manager: DatabaseManager = request.app.state.db_manager
    db_config: DatabaseConfig = request.app.state.db_config
    session_manager: SessionManager = request.app.state.session_manager

    await db_manager.switch(path)

    request.app.state.engine = db_manager.engine
    request.app.state.session_factory = db_manager.session_factory

    db_config.set_current(path)
    session_manager.revoke()

    resp = DatabaseOpenResponse(name=Path(path).name)
    return resp


@router.post("/create", status_code=201, response_model=DatabaseCreateResponse)
async def create_database(
    body: DatabaseCreateRequest, request: Request
) -> DatabaseCreateResponse | Response:
    path = str(Path(body.path.strip()).expanduser())

    if Path(path).exists():
        return Response(
            content='{"type":"https://keeper.local/errors/db-already-exists","title":"数据库文件已存在","status":409,"detail":"指定路径已有同名文件，请使用"选择数据库"打开或更换路径"}',
            status_code=409,
            media_type="application/json",
        )

    parent = Path(path).parent
    if not parent.exists():
        return Response(
            content='{"type":"https://keeper.local/errors/invalid-path","title":"目录不存在","status":400,"detail":"目标文件的父目录不存在"}',
            status_code=400,
            media_type="application/json",
        )

    db_manager: DatabaseManager = request.app.state.db_manager
    db_config: DatabaseConfig = request.app.state.db_config
    session_manager: SessionManager = request.app.state.session_manager

    await db_manager.switch(path)

    request.app.state.engine = db_manager.engine
    request.app.state.session_factory = db_manager.session_factory

    now = datetime.now(timezone.utc).isoformat()
    assert db_manager.session_factory is not None
    async with db_manager.session_factory() as session:
        auth_record = Authentication(
            id=1,
            email=body.email,
            password_hash=hash_password(body.password),
            created_at=now,
            last_login=now,
        )
        session.add(auth_record)
        await session.commit()

    db_config.set_current(path)
    session_manager.revoke()

    return DatabaseCreateResponse(name=Path(path).name)


@router.post("/remove", status_code=204)
async def remove_database(body: DatabaseRemoveRequest, request: Request) -> Response:
    path = str(Path(body.path.strip()).expanduser())

    db_config: DatabaseConfig = request.app.state.db_config

    known_paths = [db["path"] for db in db_config.get_databases()]
    if path not in known_paths:
        return Response(
            content='{"type":"https://keeper.local/errors/db-not-found","title":"数据库未关联","status":404,"detail":"指定路径的数据库不在已知列表中"}',
            status_code=404,
            media_type="application/json",
        )

    is_current = db_config.get_current() == path
    if is_current:
        return Response(
            content='{"type":"https://keeper.local/errors/db-in-use","title":"数据库正在使用","status":409,"detail":"无法移除当前正在使用的数据库"}',
            status_code=409,
            media_type="application/json",
        )

    db_config.remove_database(path)
    return Response(status_code=204)
