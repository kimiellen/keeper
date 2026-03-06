import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.session import SessionManager
from src.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def _reset_db():
    from src.db.engine import create_engine, create_session_factory
    from src.db.models import Base

    engine = create_engine(":memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.session_manager = SessionManager()
    yield
    await engine.dispose()


INIT_PAYLOAD = {
    "email": "test@example.com",
    "masterPasswordHash": "argon2id$v=19$m=65536,t=3,p=1$dGVzdA$testhash",
    "encryptedUserKey": "v1.AES_GCM.nonce.ciphertext.tag",
    "kdfParams": {
        "algorithm": "Argon2id",
        "memory": 65536,
        "iterations": 3,
        "parallelism": 1,
        "salt": "dGVzdA",
    },
}


async def auth(client: AsyncClient) -> dict[str, str]:
    await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
    resp = await client.post(
        "/api/auth/unlock",
        json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
    )
    return dict(resp.cookies)


async def create_bookmark(client, cookies, name="Test", tag_ids=None, accounts=None):
    payload = {
        "name": name,
        "urls": [{"url": "https://example.com"}],
    }
    if tag_ids is not None:
        payload["tagIds"] = tag_ids
    if accounts is not None:
        payload["accounts"] = accounts
    resp = await client.post("/api/bookmarks", json=payload, cookies=cookies)
    return resp


class TestStats:
    @pytest.mark.asyncio
    async def test_stats_empty(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.get("/api/stats", cookies=cookies)
        assert resp.status_code == 200
        data = resp.json()

        assert data["totalBookmarks"] == 0
        assert data["totalTags"] == 0
        assert data["totalRelations"] == 0
        assert data["totalAccounts"] == 0
        assert data["mostUsedTags"] == []
        assert data["recentlyUsed"] == []

    @pytest.mark.asyncio
    async def test_stats_with_data(self, client: AsyncClient):
        cookies = await auth(client)

        tag1_resp = await client.post(
            "/api/tags",
            json={"name": "Work", "color": "#112233", "icon": "briefcase"},
            cookies=cookies,
        )
        assert tag1_resp.status_code == 201
        tag1 = tag1_resp.json()

        tag2_resp = await client.post(
            "/api/tags",
            json={"name": "Life", "color": "#223344", "icon": "home"},
            cookies=cookies,
        )
        assert tag2_resp.status_code == 201
        tag2 = tag2_resp.json()

        relation1_resp = await client.post(
            "/api/relations",
            json={"name": "Phone", "type": "phone"},
            cookies=cookies,
        )
        assert relation1_resp.status_code == 201
        relation1 = relation1_resp.json()

        relation2_resp = await client.post(
            "/api/relations",
            json={"name": "Email", "type": "email"},
            cookies=cookies,
        )
        assert relation2_resp.status_code == 201
        relation2 = relation2_resp.json()

        bm1_resp = await create_bookmark(
            client,
            cookies,
            name="Bookmark One",
            tag_ids=[tag1["id"]],
            accounts=[
                {
                    "username": "user1",
                    "password": "v1.AES_GCM.nonce.ct.tag",
                    "relatedIds": [relation1["id"]],
                }
            ],
        )
        assert bm1_resp.status_code == 201
        bm1_id = bm1_resp.json()["id"]

        bm2_resp = await create_bookmark(
            client,
            cookies,
            name="Bookmark Two",
            tag_ids=[tag1["id"], tag2["id"]],
            accounts=[
                {
                    "username": "user2",
                    "password": "v1.AES_GCM.nonce.ct.tag",
                    "relatedIds": [relation2["id"]],
                },
                {
                    "username": "user3",
                    "password": "v1.AES_GCM.nonce.ct.tag",
                    "relatedIds": [],
                },
            ],
        )
        assert bm2_resp.status_code == 201
        bm2_id = bm2_resp.json()["id"]

        bm3_resp = await create_bookmark(client, cookies, name="Bookmark Three")
        assert bm3_resp.status_code == 201
        bm3_id = bm3_resp.json()["id"]

        use_resp = await client.post(
            f"/api/bookmarks/{bm2_id}/use", json={}, cookies=cookies
        )
        assert use_resp.status_code == 200

        stats_resp = await client.get("/api/stats", cookies=cookies)
        assert stats_resp.status_code == 200
        data = stats_resp.json()

        assert data["totalBookmarks"] == 3
        assert data["totalTags"] == 2
        assert data["totalRelations"] == 2
        assert data["totalAccounts"] == 3

        assert len(data["mostUsedTags"]) >= 2
        assert data["mostUsedTags"][0]["id"] == tag1["id"]
        assert data["mostUsedTags"][0]["name"] == "Work"
        assert data["mostUsedTags"][0]["count"] == 2
        assert data["mostUsedTags"][1]["id"] == tag2["id"]
        assert data["mostUsedTags"][1]["name"] == "Life"
        assert data["mostUsedTags"][1]["count"] == 1

        assert len(data["recentlyUsed"]) == 3
        assert data["recentlyUsed"][0]["id"] == bm2_id
        recent_ids = [item["id"] for item in data["recentlyUsed"]]
        assert bm1_id in recent_ids
        assert bm3_id in recent_ids
