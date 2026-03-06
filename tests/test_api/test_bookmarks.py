import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from xpinyin import Pinyin

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


async def create_tag(
    client: AsyncClient, cookies: dict[str, str], name: str
) -> dict[str, object]:
    resp = await client.post(
        "/api/tags",
        json={"name": name, "color": "#112233", "icon": "tag"},
        cookies=cookies,
    )
    assert resp.status_code == 201
    return resp.json()


async def create_relation(
    client: AsyncClient, cookies: dict[str, str], name: str
) -> dict[str, object]:
    resp = await client.post(
        "/api/relations",
        json={"name": name, "type": "other"},
        cookies=cookies,
    )
    assert resp.status_code == 201
    return resp.json()


class TestListBookmarks:
    @pytest.mark.asyncio
    async def test_list_bookmarks_empty(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.get("/api/bookmarks", cookies=cookies)
        assert resp.status_code == 200
        assert resp.json() == {"data": [], "total": 0, "limit": 50, "offset": 0}

    @pytest.mark.asyncio
    async def test_list_bookmarks_with_data(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="Alpha")
        await create_bookmark(client, cookies, name="Beta")

        resp = await client.get("/api/bookmarks?sort=name", cookies=cookies)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 2
        assert len(data["data"]) == 2
        assert data["data"][0]["name"] == "Alpha"
        assert data["data"][1]["name"] == "Beta"

    @pytest.mark.asyncio
    async def test_list_bookmarks_pagination(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="A")
        await create_bookmark(client, cookies, name="B")
        await create_bookmark(client, cookies, name="C")

        resp = await client.get("/api/bookmarks?sort=name&limit=2", cookies=cookies)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 3
        assert data["limit"] == 2
        assert len(data["data"]) == 2

    @pytest.mark.asyncio
    async def test_list_bookmarks_offset(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="Alpha")
        await create_bookmark(client, cookies, name="Beta")
        await create_bookmark(client, cookies, name="Gamma")

        resp = await client.get(
            "/api/bookmarks?sort=name&offset=1&limit=2", cookies=cookies
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 3
        assert data["offset"] == 1
        assert [item["name"] for item in data["data"]] == ["Beta", "Gamma"]

    @pytest.mark.asyncio
    async def test_list_bookmarks_search(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="GitHub")
        await create_bookmark(client, cookies, name="Notebook")

        match_resp = await client.get("/api/bookmarks?search=git", cookies=cookies)
        assert match_resp.status_code == 200
        match_data = match_resp.json()
        assert match_data["total"] == 1
        assert match_data["data"][0]["name"] == "GitHub"

        miss_resp = await client.get("/api/bookmarks?search=zzz", cookies=cookies)
        assert miss_resp.status_code == 200
        miss_data = miss_resp.json()
        assert miss_data["total"] == 0
        assert miss_data["data"] == []

    @pytest.mark.asyncio
    async def test_list_bookmarks_filter_by_tag(self, client: AsyncClient):
        cookies = await auth(client)
        tag = await create_tag(client, cookies, "Work")
        tag_id = tag["id"]

        await create_bookmark(client, cookies, name="Tagged", tag_ids=[tag_id])
        await create_bookmark(client, cookies, name="Untagged")

        resp = await client.get(f"/api/bookmarks?tagIds={tag_id}", cookies=cookies)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 1
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "Tagged"
        assert data["data"][0]["tagIds"] == [tag_id]

    @pytest.mark.asyncio
    async def test_list_bookmarks_headers(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="One")

        resp = await client.get("/api/bookmarks", cookies=cookies)
        assert resp.status_code == 200
        assert resp.headers.get("X-Total-Count") == "1"


class TestGetBookmark:
    @pytest.mark.asyncio
    async def test_get_bookmark_success(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await client.post(
            "/api/bookmarks",
            json={
                "name": "Google",
                "pinyinInitials": "gg",
                "urls": [{"url": "https://google.com"}],
                "notes": "search engine",
                "accounts": [
                    {
                        "username": "alice",
                        "password": "v1.AES_GCM.nonce.ct.tag",
                        "relatedIds": [],
                    }
                ],
            },
            cookies=cookies,
        )
        assert create_resp.status_code == 201
        bookmark_id = create_resp.json()["id"]

        resp = await client.get(f"/api/bookmarks/{bookmark_id}", cookies=cookies)
        assert resp.status_code == 200
        data = resp.json()

        assert data["id"] == bookmark_id
        assert data["name"] == "Google"
        assert data["pinyinInitials"] == "gg"
        assert data["urls"] == [{"url": "https://google.com", "lastUsed": None}]
        assert data["notes"] == "search engine"
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["id"] == 1
        assert data["accounts"][0]["username"] == "alice"
        assert data["accounts"][0]["password"] == "v1.AES_GCM.nonce.ct.tag"
        assert data["accounts"][0]["relatedIds"] == []

    @pytest.mark.asyncio
    async def test_get_bookmark_not_found(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.get("/api/bookmarks/not-exists", cookies=cookies)
        assert resp.status_code == 404


class TestCreateBookmark:
    @pytest.mark.asyncio
    async def test_create_bookmark_minimal(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/bookmarks", json={"name": "Minimal"}, cookies=cookies
        )
        assert resp.status_code == 201
        data = resp.json()

        assert data["name"] == "Minimal"
        assert data["tagIds"] == []
        assert data["urls"] == []
        assert data["notes"] == ""
        assert data["accounts"] == []

    @pytest.mark.asyncio
    async def test_create_bookmark_full(self, client: AsyncClient):
        cookies = await auth(client)
        tag = await create_tag(client, cookies, "Bank")
        relation = await create_relation(client, cookies, "Mobile")

        resp = await client.post(
            "/api/bookmarks",
            json={
                "name": "ICBC",
                "tagIds": [tag["id"]],
                "urls": [
                    {"url": "https://icbc.com"},
                    {"url": "https://secure.icbc.com"},
                ],
                "notes": "personal account",
                "accounts": [
                    {
                        "username": "bob",
                        "password": "v1.AES_GCM.nonce.ct.tag",
                        "relatedIds": [relation["id"]],
                    }
                ],
            },
            cookies=cookies,
        )
        assert resp.status_code == 201
        data = resp.json()

        assert data["name"] == "ICBC"
        assert data["tagIds"] == [tag["id"]]
        assert len(data["urls"]) == 2
        assert data["notes"] == "personal account"
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["username"] == "bob"
        assert data["accounts"][0]["relatedIds"] == [relation["id"]]

    @pytest.mark.asyncio
    async def test_create_bookmark_auto_pinyin(self, client: AsyncClient):
        cookies = await auth(client)
        name = "中文测试"
        resp = await client.post("/api/bookmarks", json={"name": name}, cookies=cookies)
        assert resp.status_code == 201
        data = resp.json()

        expected = Pinyin().get_initials(name, "").lower()[:50]
        assert data["pinyinInitials"] == expected

    @pytest.mark.asyncio
    async def test_create_bookmark_custom_pinyin(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/bookmarks",
            json={"name": "自定义", "pinyinInitials": "zdy"},
            cookies=cookies,
        )
        assert resp.status_code == 201
        assert resp.json()["pinyinInitials"] == "zdy"

    @pytest.mark.asyncio
    async def test_create_bookmark_location_header(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/bookmarks", json={"name": "Header Test"}, cookies=cookies
        )
        assert resp.status_code == 201
        bookmark_id = resp.json()["id"]
        assert resp.headers.get("Location") == f"/api/bookmarks/{bookmark_id}"

    @pytest.mark.asyncio
    async def test_create_bookmark_invalid_tag(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/bookmarks",
            json={"name": "Bad Tag", "tagIds": [9999]},
            cookies=cookies,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_bookmark_invalid_related_id(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/bookmarks",
            json={
                "name": "Bad Relation",
                "accounts": [
                    {
                        "username": "user",
                        "password": "v1.AES_GCM.nonce.ct.tag",
                        "relatedIds": [9999],
                    }
                ],
            },
            cookies=cookies,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_bookmark_invalid_password_format(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/bookmarks",
            json={
                "name": "Bad Password",
                "accounts": [
                    {
                        "username": "user",
                        "password": "plain-text-password",
                        "relatedIds": [],
                    }
                ],
            },
            cookies=cookies,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_bookmark_empty_name(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post("/api/bookmarks", json={"name": ""}, cookies=cookies)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_bookmark_account_ids_sequential(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/bookmarks",
            json={
                "name": "Multi Account",
                "accounts": [
                    {
                        "username": "u1",
                        "password": "v1.AES_GCM.nonce.ct.tag",
                        "relatedIds": [],
                    },
                    {
                        "username": "u2",
                        "password": "v1.AES_GCM.nonce.ct.tag",
                        "relatedIds": [],
                    },
                    {
                        "username": "u3",
                        "password": "v1.AES_GCM.nonce.ct.tag",
                        "relatedIds": [],
                    },
                ],
            },
            cookies=cookies,
        )
        assert resp.status_code == 201
        ids = [account["id"] for account in resp.json()["accounts"]]
        assert ids == [1, 2, 3]


class TestUpdateBookmark:
    @pytest.mark.asyncio
    async def test_update_bookmark_success(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await create_bookmark(client, cookies, name="Before")
        assert create_resp.status_code == 201
        bookmark_id = create_resp.json()["id"]

        tag = await create_tag(client, cookies, "UpdatedTag")

        resp = await client.put(
            f"/api/bookmarks/{bookmark_id}",
            json={
                "name": "After",
                "tagIds": [tag["id"]],
                "urls": [{"url": "https://after.example.com"}],
                "notes": "updated notes",
                "accounts": [
                    {
                        "username": "newuser",
                        "password": "v1.AES_GCM.nonce.ct.tag",
                        "relatedIds": [],
                    }
                ],
            },
            cookies=cookies,
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["id"] == bookmark_id
        assert data["name"] == "After"
        assert data["tagIds"] == [tag["id"]]
        assert data["urls"] == [{"url": "https://after.example.com", "lastUsed": None}]
        assert data["notes"] == "updated notes"
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["username"] == "newuser"

    @pytest.mark.asyncio
    async def test_update_bookmark_not_found(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.put(
            "/api/bookmarks/not-exists",
            json={"name": "Nope", "urls": [{"url": "https://example.com"}]},
            cookies=cookies,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_bookmark_invalid_tag(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await create_bookmark(client, cookies, name="Before")
        bookmark_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/bookmarks/{bookmark_id}",
            json={
                "name": "After",
                "tagIds": [99999],
                "urls": [{"url": "https://x.com"}],
            },
            cookies=cookies,
        )
        assert resp.status_code == 422


class TestPatchBookmark:
    @pytest.mark.asyncio
    async def test_patch_bookmark_name_only(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await client.post(
            "/api/bookmarks",
            json={
                "name": "Original",
                "urls": [{"url": "https://origin.example.com"}],
                "notes": "keep me",
            },
            cookies=cookies,
        )
        assert create_resp.status_code == 201
        original = create_resp.json()
        bookmark_id = original["id"]

        patch_resp = await client.patch(
            f"/api/bookmarks/{bookmark_id}",
            json={"name": "Renamed"},
            cookies=cookies,
        )
        assert patch_resp.status_code == 200
        patched = patch_resp.json()

        assert patched["name"] == "Renamed"
        assert patched["notes"] == original["notes"]
        assert patched["urls"] == original["urls"]
        assert patched["accounts"] == original["accounts"]

    @pytest.mark.asyncio
    async def test_patch_bookmark_notes(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await create_bookmark(client, cookies, name="Patch Notes")
        bookmark_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/bookmarks/{bookmark_id}",
            json={"notes": "new note"},
            cookies=cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "new note"

    @pytest.mark.asyncio
    async def test_patch_bookmark_not_found(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.patch(
            "/api/bookmarks/not-exists",
            json={"name": "x"},
            cookies=cookies,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_bookmark_tags(self, client: AsyncClient):
        cookies = await auth(client)
        tag = await create_tag(client, cookies, "PatchTag")
        create_resp = await create_bookmark(client, cookies, name="Patch Tags")
        bookmark_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/bookmarks/{bookmark_id}",
            json={"tagIds": [tag["id"]]},
            cookies=cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["tagIds"] == [tag["id"]]


class TestDeleteBookmark:
    @pytest.mark.asyncio
    async def test_delete_bookmark_success(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await create_bookmark(client, cookies, name="ToDelete")
        bookmark_id = create_resp.json()["id"]

        delete_resp = await client.delete(
            f"/api/bookmarks/{bookmark_id}", cookies=cookies
        )
        assert delete_resp.status_code == 204

        get_resp = await client.get(f"/api/bookmarks/{bookmark_id}", cookies=cookies)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_bookmark_not_found(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.delete("/api/bookmarks/not-exists", cookies=cookies)
        assert resp.status_code == 404


class TestUseBookmark:
    @pytest.mark.asyncio
    async def test_use_bookmark_basic(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await create_bookmark(client, cookies, name="Use Basic")
        bookmark_id = create_resp.json()["id"]
        old_last_used = create_resp.json()["lastUsedAt"]

        resp = await client.post(
            f"/api/bookmarks/{bookmark_id}/use", json={}, cookies=cookies
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["message"] == "更新使用时间成功"
        assert data["lastUsedAt"] != old_last_used

        get_resp = await client.get(f"/api/bookmarks/{bookmark_id}", cookies=cookies)
        assert get_resp.status_code == 200
        assert get_resp.json()["lastUsedAt"] == data["lastUsedAt"]

    @pytest.mark.asyncio
    async def test_use_bookmark_with_url(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await client.post(
            "/api/bookmarks",
            json={
                "name": "Use URL",
                "urls": [
                    {"url": "https://a.example.com"},
                    {"url": "https://b.example.com"},
                ],
            },
            cookies=cookies,
        )
        assert create_resp.status_code == 201
        bookmark_id = create_resp.json()["id"]

        use_resp = await client.post(
            f"/api/bookmarks/{bookmark_id}/use",
            json={"url": "https://b.example.com"},
            cookies=cookies,
        )
        assert use_resp.status_code == 200
        used_at = use_resp.json()["lastUsedAt"]

        get_resp = await client.get(f"/api/bookmarks/{bookmark_id}", cookies=cookies)
        assert get_resp.status_code == 200
        urls = get_resp.json()["urls"]
        target = [item for item in urls if item["url"] == "https://b.example.com"][0]
        assert target["lastUsed"] == used_at

    @pytest.mark.asyncio
    async def test_use_bookmark_with_account(self, client: AsyncClient):
        cookies = await auth(client)
        create_resp = await client.post(
            "/api/bookmarks",
            json={
                "name": "Use Account",
                "accounts": [
                    {
                        "username": "alice",
                        "password": "v1.AES_GCM.nonce.ct.tag",
                        "relatedIds": [],
                    }
                ],
            },
            cookies=cookies,
        )
        assert create_resp.status_code == 201
        bookmark_id = create_resp.json()["id"]

        use_resp = await client.post(
            f"/api/bookmarks/{bookmark_id}/use",
            json={"accountId": 1},
            cookies=cookies,
        )
        assert use_resp.status_code == 200
        used_at = use_resp.json()["lastUsedAt"]

        get_resp = await client.get(f"/api/bookmarks/{bookmark_id}", cookies=cookies)
        assert get_resp.status_code == 200
        account = get_resp.json()["accounts"][0]
        assert account["id"] == 1
        assert account["lastUsed"] == used_at

    @pytest.mark.asyncio
    async def test_use_bookmark_not_found(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/bookmarks/not-exists/use",
            json={},
            cookies=cookies,
        )
        assert resp.status_code == 404
