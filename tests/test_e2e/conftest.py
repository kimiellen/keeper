import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from typing import Any

from src.api.session import SessionManager
from src.db.engine import create_engine, create_session_factory
from src.db.models import Base
from src.main import app

INIT_PAYLOAD = {
    "email": "test@example.com",
    "password": "MySecurePassword123",
}

ENCRYPTED_PASSWORD = "v1.AES_GCM.dGVzdG5vbmNl.Y2lwaGVydGV4dA.dGFn"
ENCRYPTED_PASSWORD_2 = "v1.AES_GCM.bm9uY2Uy.Y2lwaGVydGV4dDI.dGFnMg"


@pytest_asyncio.fixture(autouse=True)
async def _reset_db():
    """每个测试用例之前重置数据库和会话状态。"""
    engine = create_engine(":memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.session_manager = SessionManager()
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def client():
    """裸 HTTP 客户端，未认证。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def authed_client(client: AsyncClient):
    """已初始化并解锁的客户端，携带有效 session cookie。"""
    resp = await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
    assert resp.status_code == 201

    resp = await client.post(
        "/api/auth/unlock",
        json={"password": INIT_PAYLOAD["password"]},
    )
    assert resp.status_code == 200

    yield client


async def seed_tag(
    client: AsyncClient, name: str, color: str = "#FF5733", icon: str = "star"
) -> dict[str, Any]:
    """创建一个标签并返回响应 JSON。"""
    resp = await client.post(
        "/api/tags", json={"name": name, "color": color, "icon": icon}
    )
    assert resp.status_code == 201, f"seed_tag failed: {resp.text}"
    return resp.json()


async def seed_relation(
    client: AsyncClient, name: str, type_: str = "email"
) -> dict[str, Any]:
    """创建一个关联并返回响应 JSON。"""
    resp = await client.post("/api/relations", json={"name": name, "type": type_})
    assert resp.status_code == 201, f"seed_relation failed: {resp.text}"
    return resp.json()


async def seed_bookmark(
    client: AsyncClient,
    name: str,
    urls: list[dict[str, Any]] | None = None,
    tag_ids: list[int] | None = None,
    accounts: list[dict[str, Any]] | None = None,
    notes: str = "",
    pinyin_initials: str | None = None,
) -> dict[str, Any]:
    """创建一个书签并返回响应 JSON。"""
    body: dict[str, Any] = {"name": name, "notes": notes}
    if urls is not None:
        body["urls"] = urls
    if tag_ids is not None:
        body["tagIds"] = tag_ids
    if accounts is not None:
        body["accounts"] = accounts
    if pinyin_initials is not None:
        body["pinyinInitials"] = pinyin_initials
    resp = await client.post("/api/bookmarks", json=body)
    assert resp.status_code == 201, f"seed_bookmark failed: {resp.text}"
    return resp.json()
