# pyright: reportUnknownVariableType=false, reportUnusedFunction=false

from typing import cast

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.api.session import SessionManager
from src.db.engine import create_engine, create_session_factory
from src.db.models import Base
from src.main import app

INIT_PAYLOAD = {
    "email": "test@example.com",
    "password": "MySecurePassword123",
}

ENCRYPTED_PASSWORD = "v1.AES_GCM.dGVzdG5vbmNl.Y2lwaGVydGV4dA.dGFn"


@pytest_asyncio.fixture(autouse=True)
async def _reset_db():
    engine: AsyncEngine = create_engine(":memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.session_manager = SessionManager()
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def authed_client(client: AsyncClient):
    resp = await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
    assert resp.status_code == 201

    resp = await client.post(
        "/api/auth/unlock",
        json={"password": INIT_PAYLOAD["password"]},
    )
    assert resp.status_code == 200

    yield client


@pytest_asyncio.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    return cast(async_sessionmaker[AsyncSession], app.state.session_factory)
