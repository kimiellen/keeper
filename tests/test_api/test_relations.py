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
    _ = await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
    resp = await client.post(
        "/api/auth/unlock",
        json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
    )
    return dict(resp.cookies)


async def create_relation(
    client: AsyncClient,
    cookies: dict[str, str],
    name: str,
    relation_type: str = "phone",
):
    payload = {"name": name, "type": relation_type}
    return await client.post("/api/relations", json=payload, cookies=cookies)


class TestListRelations:
    @pytest.mark.asyncio
    async def test_list_relations_empty(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.get("/api/relations", cookies=cookies)

        assert resp.status_code == 200
        assert resp.json() == {"data": [], "total": 0}

    @pytest.mark.asyncio
    async def test_list_relations_with_data(self, client: AsyncClient):
        cookies = await auth(client)
        _ = await create_relation(client, cookies, "Phone")
        _ = await create_relation(client, cookies, "Email", "email")

        resp = await client.get("/api/relations", cookies=cookies)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        names = [item["name"] for item in data["data"]]
        assert names == ["Email", "Phone"]


class TestGetRelation:
    @pytest.mark.asyncio
    async def test_get_relation_success(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await create_relation(client, cookies, "Mobile", "phone")
        relation_id = create_resp.json()["id"]

        resp = await client.get(f"/api/relations/{relation_id}", cookies=cookies)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == relation_id
        assert data["name"] == "Mobile"
        assert data["type"] == "phone"

    @pytest.mark.asyncio
    async def test_get_relation_not_found(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.get("/api/relations/9999", cookies=cookies)

        assert resp.status_code == 404


class TestCreateRelation:
    @pytest.mark.asyncio
    async def test_create_relation_success(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await create_relation(client, cookies, "Identity", "idcard")

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] > 0
        assert data["name"] == "Identity"
        assert data["type"] == "idcard"
        assert "createdAt" in data
        assert "updatedAt" in data

    @pytest.mark.asyncio
    async def test_create_relation_all_types(self, client: AsyncClient):
        cookies = await auth(client)
        relation_types = ["phone", "email", "idcard", "other"]

        for index, relation_type in enumerate(relation_types, start=1):
            resp = await create_relation(
                client, cookies, f"Relation{index}", relation_type
            )
            assert resp.status_code == 201
            assert resp.json()["type"] == relation_type

    @pytest.mark.asyncio
    async def test_create_relation_duplicate_name(self, client: AsyncClient):
        cookies = await auth(client)
        _ = await create_relation(client, cookies, "Duplicate")
        resp = await create_relation(client, cookies, "Duplicate", "email")

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_relation_invalid_type(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/relations",
            json={"name": "BadType", "type": "twitter"},
            cookies=cookies,
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_relation_empty_name(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/relations",
            json={"name": "", "type": "phone"},
            cookies=cookies,
        )

        assert resp.status_code == 422


class TestUpdateRelation:
    @pytest.mark.asyncio
    async def test_update_relation_success(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await create_relation(client, cookies, "Old", "phone")
        relation_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/relations/{relation_id}",
            json={"name": "New", "type": "email"},
            cookies=cookies,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == relation_id
        assert data["name"] == "New"
        assert data["type"] == "email"

    @pytest.mark.asyncio
    async def test_update_relation_not_found(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.put(
            "/api/relations/9999",
            json={"name": "Missing", "type": "phone"},
            cookies=cookies,
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_relation_duplicate_name(self, client: AsyncClient):
        cookies = await auth(client)
        _ = await create_relation(client, cookies, "First", "phone")
        second = await create_relation(client, cookies, "Second", "email")
        second_id = second.json()["id"]

        resp = await client.put(
            f"/api/relations/{second_id}",
            json={"name": "First", "type": "other"},
            cookies=cookies,
        )

        assert resp.status_code == 409


class TestDeleteRelation:
    @pytest.mark.asyncio
    async def test_delete_relation_success(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await create_relation(client, cookies, "Temporary", "phone")
        relation_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/relations/{relation_id}", cookies=cookies)

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_relation_not_found(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.delete("/api/relations/9999", cookies=cookies)

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_relation_in_use_no_cascade(self, client: AsyncClient):
        cookies = await auth(client)
        relation_resp = await create_relation(client, cookies, "Emergency", "phone")
        relation_id = relation_resp.json()["id"]

        bookmark_payload = {
            "name": "Test Bookmark",
            "urls": [{"url": "https://example.com"}],
            "tagIds": [],
            "accounts": [
                {
                    "username": "user",
                    "password": "v1.AES_GCM.nonce.ct.tag",
                    "relatedIds": [relation_id],
                }
            ],
        }
        bookmark_resp = await client.post(
            "/api/bookmarks", json=bookmark_payload, cookies=cookies
        )
        assert bookmark_resp.status_code == 201

        resp = await client.delete(f"/api/relations/{relation_id}", cookies=cookies)

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_relation_cascade(self, client: AsyncClient):
        cookies = await auth(client)
        relation_resp = await create_relation(client, cookies, "Parent", "other")
        relation_id = relation_resp.json()["id"]

        bookmark_payload = {
            "name": "Test Bookmark",
            "urls": [{"url": "https://example.com"}],
            "tagIds": [],
            "accounts": [
                {
                    "username": "user",
                    "password": "v1.AES_GCM.nonce.ct.tag",
                    "relatedIds": [relation_id],
                }
            ],
        }
        bookmark_resp = await client.post(
            "/api/bookmarks", json=bookmark_payload, cookies=cookies
        )
        assert bookmark_resp.status_code == 201
        bookmark_id = bookmark_resp.json()["id"]

        resp = await client.delete(
            f"/api/relations/{relation_id}?cascade=true", cookies=cookies
        )

        assert resp.status_code == 204

        bookmark_get = await client.get(
            f"/api/bookmarks/{bookmark_id}", cookies=cookies
        )
        assert bookmark_get.status_code == 200
        accounts = bookmark_get.json()["accounts"]
        assert len(accounts) == 1
        assert accounts[0]["relatedIds"] == []
