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
    "password": "MySecurePassword123",
}


async def auth(client: AsyncClient) -> dict[str, str]:
    _ = await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
    resp = await client.post(
        "/api/auth/unlock",
        json={"password": INIT_PAYLOAD["password"]},
    )
    return dict(resp.cookies)


async def create_tag(
    client: AsyncClient,
    cookies: dict[str, str],
    name: str,
    color: str | None = None,
    icon: str | None = None,
):
    payload = {"name": name}
    if color is not None:
        payload["color"] = color
    if icon is not None:
        payload["icon"] = icon
    return await client.post("/api/tags", json=payload, cookies=cookies)


class TestListTags:
    @pytest.mark.asyncio
    async def test_list_tags_empty(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.get("/api/tags", cookies=cookies)

        assert resp.status_code == 200
        data = resp.json()
        assert data == {"data": [], "total": 0}

    @pytest.mark.asyncio
    async def test_list_tags_with_data(self, client: AsyncClient):
        cookies = await auth(client)
        _ = await create_tag(client, cookies, "Alpha")
        _ = await create_tag(client, cookies, "Beta")

        resp = await client.get("/api/tags", cookies=cookies)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        names = [item["name"] for item in data["data"]]
        assert names == ["Alpha", "Beta"]

    @pytest.mark.asyncio
    async def test_list_tags_sorted_by_name(self, client: AsyncClient):
        cookies = await auth(client)
        _ = await create_tag(client, cookies, "Charlie")
        _ = await create_tag(client, cookies, "Alpha")

        resp = await client.get("/api/tags", cookies=cookies)

        assert resp.status_code == 200
        names = [item["name"] for item in resp.json()["data"]]
        assert names == ["Alpha", "Charlie"]

    @pytest.mark.asyncio
    async def test_list_tags_sorted_desc(self, client: AsyncClient):
        cookies = await auth(client)
        _ = await create_tag(client, cookies, "Alpha")
        _ = await create_tag(client, cookies, "Beta")

        resp = await client.get("/api/tags?sort=-name", cookies=cookies)

        assert resp.status_code == 200
        names = [item["name"] for item in resp.json()["data"]]
        assert names == ["Beta", "Alpha"]


class TestGetTag:
    @pytest.mark.asyncio
    async def test_get_tag_success(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await create_tag(client, cookies, "Work")
        tag_id = create_resp.json()["id"]

        resp = await client.get(f"/api/tags/{tag_id}", cookies=cookies)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tag_id
        assert data["name"] == "Work"

    @pytest.mark.asyncio
    async def test_get_tag_not_found(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.get("/api/tags/9999", cookies=cookies)

        assert resp.status_code == 404


class TestCreateTag:
    @pytest.mark.asyncio
    async def test_create_tag_success(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await create_tag(client, cookies, "Finance")

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] > 0
        assert data["name"] == "Finance"
        assert "createdAt" in data
        assert "updatedAt" in data

    @pytest.mark.asyncio
    async def test_create_tag_with_color(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await create_tag(client, cookies, "Urgent", color="#FF0000")

        assert resp.status_code == 201
        assert resp.json()["color"] == "#FF0000"

    @pytest.mark.asyncio
    async def test_create_tag_with_icon(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await create_tag(client, cookies, "Site", icon="globe")

        assert resp.status_code == 201
        assert resp.json()["icon"] == "globe"

    @pytest.mark.asyncio
    async def test_create_tag_defaults(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await create_tag(client, cookies, "Defaulted")

        assert resp.status_code == 201
        data = resp.json()
        assert data["color"] == "#3B82F6"
        assert data["icon"] == ""

    @pytest.mark.asyncio
    async def test_create_tag_duplicate_name(self, client: AsyncClient):
        cookies = await auth(client)
        _ = await create_tag(client, cookies, "Duplicate")
        resp = await create_tag(client, cookies, "Duplicate")

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_tag_name_too_long(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await create_tag(client, cookies, "a" * 51)

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_tag_empty_name(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await create_tag(client, cookies, "")

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_tag_invalid_color(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await create_tag(client, cookies, "BadColor", color="red")

        assert resp.status_code == 422


class TestUpdateTag:
    @pytest.mark.asyncio
    async def test_update_tag_success(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await create_tag(client, cookies, "Old")
        tag_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/tags/{tag_id}",
            json={"name": "New", "color": "#123456", "icon": "star"},
            cookies=cookies,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tag_id
        assert data["name"] == "New"
        assert data["color"] == "#123456"
        assert data["icon"] == "star"

    @pytest.mark.asyncio
    async def test_update_tag_not_found(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.put(
            "/api/tags/9999",
            json={"name": "Missing", "color": "#123456", "icon": "x"},
            cookies=cookies,
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_tag_duplicate_name(self, client: AsyncClient):
        cookies = await auth(client)
        _ = await create_tag(client, cookies, "First")
        second = await create_tag(client, cookies, "Second")
        second_id = second.json()["id"]

        resp = await client.put(
            f"/api/tags/{second_id}",
            json={"name": "First", "color": "#123456", "icon": "x"},
            cookies=cookies,
        )

        assert resp.status_code == 409


class TestDeleteTag:
    @pytest.mark.asyncio
    async def test_delete_tag_success(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await create_tag(client, cookies, "Temp")
        tag_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/tags/{tag_id}", cookies=cookies)

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_tag_not_found(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.delete("/api/tags/9999", cookies=cookies)

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_tag_in_use_no_cascade(self, client: AsyncClient):
        cookies = await auth(client)
        tag_resp = await create_tag(client, cookies, "InUse")
        tag_id = tag_resp.json()["id"]

        bookmark_payload = {
            "name": "Test Bookmark",
            "urls": [{"url": "https://example.com"}],
            "tagIds": [tag_id],
            "accounts": [],
        }
        bookmark_resp = await client.post(
            "/api/bookmarks", json=bookmark_payload, cookies=cookies
        )
        assert bookmark_resp.status_code == 201

        resp = await client.delete(f"/api/tags/{tag_id}", cookies=cookies)

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_tag_cascade(self, client: AsyncClient):
        cookies = await auth(client)
        tag_resp = await create_tag(client, cookies, "CascadeTag")
        tag_id = tag_resp.json()["id"]

        bookmark_payload = {
            "name": "Test Bookmark",
            "urls": [{"url": "https://example.com"}],
            "tagIds": [tag_id],
            "accounts": [],
        }
        bookmark_resp = await client.post(
            "/api/bookmarks", json=bookmark_payload, cookies=cookies
        )
        assert bookmark_resp.status_code == 201
        bookmark_id = bookmark_resp.json()["id"]

        resp = await client.delete(f"/api/tags/{tag_id}?cascade=true", cookies=cookies)

        assert resp.status_code == 204

        bookmark_get = await client.get(
            f"/api/bookmarks/{bookmark_id}", cookies=cookies
        )
        assert bookmark_get.status_code == 200
        assert bookmark_get.json()["tagIds"] == []
