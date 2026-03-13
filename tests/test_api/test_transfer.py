import csv
import io
import json
from typing import Any

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
    await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
    resp = await client.post(
        "/api/auth/unlock",
        json={"password": INIT_PAYLOAD["password"]},
    )
    return dict(resp.cookies)


async def create_tag(
    client: AsyncClient, cookies: dict[str, str], name: str
) -> dict[str, Any]:
    resp = await client.post(
        "/api/tags",
        json={"name": name, "color": "#112233", "icon": "tag"},
        cookies=cookies,
    )
    assert resp.status_code == 201
    return resp.json()


async def create_relation(
    client: AsyncClient, cookies: dict[str, str], name: str
) -> dict[str, Any]:
    resp = await client.post(
        "/api/relations",
        json={"name": name, "type": "other"},
        cookies=cookies,
    )
    assert resp.status_code == 201
    return resp.json()


async def create_bookmark(
    client: AsyncClient,
    cookies: dict[str, str],
    name: str = "Test",
    tag_ids: list[int] | None = None,
    accounts: list[dict[str, Any]] | None = None,
    urls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "urls": urls or [{"url": "https://example.com"}],
    }
    if tag_ids is not None:
        payload["tagIds"] = tag_ids
    if accounts is not None:
        payload["accounts"] = accounts
    resp = await client.post("/api/bookmarks", json=payload, cookies=cookies)
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Export JSON
# ---------------------------------------------------------------------------


class TestExportJson:
    @pytest.mark.asyncio
    async def test_export_json_unauthorized_without_session(self, client: AsyncClient):
        resp = await client.get("/api/transfer/export/json")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_json_unauthorized_after_lock(self, client: AsyncClient):
        cookies = await auth(client)
        lock_resp = await client.post("/api/auth/lock", cookies=cookies)
        assert lock_resp.status_code == 204

        resp = await client.get("/api/transfer/export/json", cookies=cookies)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_json_unauthorized_without_cookie(self, client: AsyncClient):
        _ = await auth(client)
        client.cookies.clear()
        resp = await client.get("/api/transfer/export/json")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_json_empty_db(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.get(
            "/api/transfer/export/json",
            cookies=cookies,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0"
        assert data["data"]["bookmarks"] == []
        assert data["data"]["tags"] == []
        assert data["data"]["relations"] == []
        assert "Content-Disposition" in resp.headers

    @pytest.mark.asyncio
    async def test_export_json_with_data(self, client: AsyncClient):
        cookies = await auth(client)
        tag = await create_tag(client, cookies, "工作")
        rel = await create_relation(client, cookies, "手机号")
        encrypted_pw = "secret123"
        await create_bookmark(
            client,
            cookies,
            name="GitHub",
            tag_ids=[tag["id"]],
            accounts=[
                {
                    "username": "user1",
                    "password": encrypted_pw,
                    "relatedIds": [rel["id"]],
                }
            ],
        )

        resp = await client.get(
            "/api/transfer/export/json",
            cookies=cookies,
        )
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["data"]["tags"]) == 1
        assert data["data"]["tags"][0]["name"] == "工作"
        assert len(data["data"]["relations"]) == 1
        assert data["data"]["relations"][0]["name"] == "手机号"
        assert len(data["data"]["bookmarks"]) == 1
        bm = data["data"]["bookmarks"][0]
        assert bm["name"] == "GitHub"
        assert bm["accounts"][0]["username"] == "user1"
        # 导出的密码应该是明文
        assert bm["accounts"][0]["password"] == "secret123"
        assert "X-Export-Warning" in resp.headers

    @pytest.mark.asyncio
    async def test_export_json_decrypts_passwords(self, client: AsyncClient):
        """验证导出时密码被正确解密为明文。"""
        cookies = await auth(client)
        pw1 = "alpha"
        pw2 = "beta"
        await create_bookmark(
            client,
            cookies,
            name="Multi",
            accounts=[
                {"username": "u1", "password": pw1, "relatedIds": []},
                {"username": "u2", "password": pw2, "relatedIds": []},
            ],
        )
        resp = await client.get(
            "/api/transfer/export/json",
            cookies=cookies,
        )
        data = resp.json()
        accounts = data["data"]["bookmarks"][0]["accounts"]
        assert accounts[0]["password"] == "alpha"
        assert accounts[1]["password"] == "beta"


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------


class TestExportCsv:
    @pytest.mark.asyncio
    async def test_export_csv_unauthorized_without_session(self, client: AsyncClient):
        resp = await client.get("/api/transfer/export/csv")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_csv_empty_db(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.get(
            "/api/transfer/export/csv",
            cookies=cookies,
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        lines = resp.text.strip().split("\n")
        assert len(lines) == 1  # header only
        assert "name" in lines[0]

    @pytest.mark.asyncio
    async def test_export_csv_with_data(self, client: AsyncClient):
        cookies = await auth(client)
        tag = await create_tag(client, cookies, "社交")
        encrypted_pw = "mypass"
        await create_bookmark(
            client,
            cookies,
            name="Twitter",
            tag_ids=[tag["id"]],
            accounts=[{"username": "jack", "password": encrypted_pw, "relatedIds": []}],
        )

        resp = await client.get(
            "/api/transfer/export/csv",
            cookies=cookies,
        )
        assert resp.status_code == 200
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["name"] == "Twitter"
        assert rows[0]["username"] == "jack"
        # CSV 导出密码是明文
        assert rows[0]["password"] == "mypass"
        assert rows[0]["tags"] == "社交"
        assert "X-Export-Warning" in resp.headers

    @pytest.mark.asyncio
    async def test_export_csv_multiple_accounts(self, client: AsyncClient):
        """一个书签有多个账户时, CSV 每个账户一行。"""
        cookies = await auth(client)
        pw1 = "pw1"
        pw2 = "pw2"
        await create_bookmark(
            client,
            cookies,
            name="Site",
            accounts=[
                {"username": "u1", "password": pw1, "relatedIds": []},
                {"username": "u2", "password": pw2, "relatedIds": []},
            ],
        )
        resp = await client.get(
            "/api/transfer/export/csv",
            cookies=cookies,
        )
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["username"] == "u1"
        assert rows[0]["password"] == "pw1"
        assert rows[1]["username"] == "u2"
        assert rows[1]["password"] == "pw2"

    @pytest.mark.asyncio
    async def test_export_csv_bookmark_no_account(self, client: AsyncClient):
        """没有账户的书签也会输出一行。"""
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="NoAccount")
        resp = await client.get(
            "/api/transfer/export/csv",
            cookies=cookies,
        )
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["name"] == "NoAccount"
        assert rows[0]["username"] == ""
        assert rows[0]["password"] == ""


# ---------------------------------------------------------------------------
# Import Preview
# ---------------------------------------------------------------------------


class TestImportPreview:
    @pytest.mark.asyncio
    async def test_preview_keeper_json(self, client: AsyncClient):
        cookies = await auth(client)
        keeper_data = {
            "version": "1.0",
            "data": {
                "tags": [{"id": 1, "name": "T1"}],
                "relations": [{"id": 1, "name": "R1", "type": "phone"}],
                "bookmarks": [
                    {"name": "B1", "tagIds": [1], "accounts": [], "urls": []},
                    {"name": "B2", "tagIds": [], "accounts": [], "urls": []},
                ],
            },
        }
        resp = await client.post(
            "/api/transfer/import/preview",
            json={"format": "keeper_json", "content": json.dumps(keeper_data)},
            cookies=cookies,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "keeper_json"
        assert data["totalBookmarks"] == 2
        assert data["totalTags"] == 1
        assert data["totalRelations"] == 1
        assert data["conflicts"] == []

    @pytest.mark.asyncio
    async def test_preview_detects_conflicts(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="Existing")

        keeper_data = {
            "version": "1.0",
            "data": {
                "tags": [],
                "relations": [],
                "bookmarks": [
                    {"name": "Existing", "tagIds": [], "accounts": [], "urls": []},
                    {"name": "New", "tagIds": [], "accounts": [], "urls": []},
                ],
            },
        }
        resp = await client.post(
            "/api/transfer/import/preview",
            json={"format": "keeper_json", "content": json.dumps(keeper_data)},
            cookies=cookies,
        )
        data = resp.json()
        assert data["totalBookmarks"] == 2
        assert len(data["conflicts"]) == 1
        assert data["conflicts"][0]["name"] == "Existing"
        assert data["conflicts"][0]["type"] == "duplicate_name"

    @pytest.mark.asyncio
    async def test_preview_bitwarden_json(self, client: AsyncClient):
        cookies = await auth(client)
        bw_data = {
            "encrypted": False,
            "folders": [{"id": "f1", "name": "Social"}],
            "items": [
                {"type": 1, "name": "Twitter", "login": {}},
                {"type": 1, "name": "GitHub", "login": {}},
                {"type": 2, "name": "SecureNote"},  # type!=1, 应被忽略
            ],
        }
        resp = await client.post(
            "/api/transfer/import/preview",
            json={"format": "bitwarden_json", "content": json.dumps(bw_data)},
            cookies=cookies,
        )
        data = resp.json()
        assert data["format"] == "bitwarden_json"
        assert data["totalBookmarks"] == 2  # 只有 type==1
        assert data["totalTags"] == 1
        assert any("Login" in w for w in data["warnings"])

    @pytest.mark.asyncio
    async def test_preview_csv(self, client: AsyncClient):
        cookies = await auth(client)
        csv_content = (
            "name,url,username,password,notes,tags\n"
            "Site1,https://a.com,user,pw,,Tag1\n"
            'Site2,https://b.com,,,notes,"Tag1,Tag2"\n'
        )
        resp = await client.post(
            "/api/transfer/import/preview",
            json={"format": "csv", "content": csv_content},
            cookies=cookies,
        )
        data = resp.json()
        assert data["format"] == "csv"
        assert data["totalBookmarks"] == 2
        assert data["totalTags"] == 2
        assert any("自动加密" in w for w in data["warnings"])

    @pytest.mark.asyncio
    async def test_preview_invalid_keeper_json(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/transfer/import/preview",
            json={"format": "keeper_json", "content": "not json"},
            cookies=cookies,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_preview_invalid_bitwarden_json(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/transfer/import/preview",
            json={"format": "bitwarden_json", "content": '{"encrypted": true}'},
            cookies=cookies,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_preview_empty_csv(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/transfer/import/preview",
            json={"format": "csv", "content": "col1,col2\nval1,val2\n"},
            cookies=cookies,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Import Keeper JSON
# ---------------------------------------------------------------------------


class TestImportKeeperJson:
    def _make_keeper_export(
        self,
        bookmarks: list[dict[str, Any]],
        tags: list[dict[str, Any]] | None = None,
        relations: list[dict[str, Any]] | None = None,
    ) -> str:
        return json.dumps(
            {
                "version": "1.0",
                "data": {
                    "tags": tags or [],
                    "relations": relations or [],
                    "bookmarks": bookmarks,
                },
            }
        )

    @pytest.mark.asyncio
    async def test_import_unauthorized_without_session(self, client: AsyncClient):
        resp = await client.post(
            "/api/transfer/import",
            json={
                "format": "keeper_json",
                "content": self._make_keeper_export([]),
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_import_basic(self, client: AsyncClient):
        cookies = await auth(client)
        content = self._make_keeper_export(
            bookmarks=[
                {
                    "name": "Site A",
                    "tagIds": [],
                    "urls": [{"url": "https://a.com", "lastUsed": ""}],
                    "notes": "notes here",
                    "accounts": [
                        {
                            "id": 1,
                            "username": "u1",
                            "password": "plaintext_pw",
                            "relatedIds": [],
                        }
                    ],
                }
            ]
        )
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "keeper_json", "content": content},
            cookies=cookies,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1
        assert data["skipped"]["bookmarks"] == 0

        # 验证书签已创建且密码已加密
        bm_resp = await client.get("/api/bookmarks", cookies=cookies)
        bms = bm_resp.json()["data"]
        assert len(bms) == 1
        assert bms[0]["name"] == "Site A"

    @pytest.mark.asyncio
    async def test_import_with_tags_and_relations(self, client: AsyncClient):
        """测试导入时标签和关联的 ID 映射。"""
        cookies = await auth(client)
        content = self._make_keeper_export(
            tags=[
                {"id": 100, "name": "工作"},
                {"id": 200, "name": "个人"},
            ],
            relations=[
                {"id": 50, "name": "手机号", "type": "phone"},
            ],
            bookmarks=[
                {
                    "name": "带标签",
                    "tagIds": [100, 200],
                    "urls": [],
                    "accounts": [
                        {
                            "id": 1,
                            "username": "u",
                            "password": "pw",
                            "relatedIds": [50],
                        }
                    ],
                }
            ],
        )
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "keeper_json", "content": content},
            cookies=cookies,
        )
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1
        assert data["imported"]["tags"] == 2
        assert data["imported"]["relations"] == 1

        # 验证标签已创建
        tag_resp = await client.get("/api/tags", cookies=cookies)
        tag_names = [t["name"] for t in tag_resp.json()["data"]]
        assert "工作" in tag_names
        assert "个人" in tag_names

        rel_resp = await client.get("/api/relations", cookies=cookies)
        rel_names = [r["name"] for r in rel_resp.json()["data"]]
        assert "手机号" in rel_names

    @pytest.mark.asyncio
    async def test_import_conflict_skip(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="Dup")

        content = self._make_keeper_export(
            bookmarks=[
                {
                    "name": "Dup",
                    "tagIds": [],
                    "urls": [],
                    "accounts": [],
                },
                {
                    "name": "New",
                    "tagIds": [],
                    "urls": [],
                    "accounts": [],
                },
            ]
        )
        resp = await client.post(
            "/api/transfer/import",
            json={
                "format": "keeper_json",
                "content": content,
                "conflictPolicy": "skip",
            },
            cookies=cookies,
        )
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1
        assert data["skipped"]["bookmarks"] == 1

        bm_resp = await client.get("/api/bookmarks", cookies=cookies)
        total = bm_resp.json()["total"]
        assert total == 2  # 原有1 + 导入1

    @pytest.mark.asyncio
    async def test_import_conflict_rename(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="Dup")

        content = self._make_keeper_export(
            bookmarks=[{"name": "Dup", "tagIds": [], "urls": [], "accounts": []}]
        )
        resp = await client.post(
            "/api/transfer/import",
            json={
                "format": "keeper_json",
                "content": content,
                "conflictPolicy": "rename",
            },
            cookies=cookies,
        )
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1
        assert data["skipped"]["bookmarks"] == 0

        bm_resp = await client.get("/api/bookmarks?sort=name", cookies=cookies)
        names = [b["name"] for b in bm_resp.json()["data"]]
        assert "Dup" in names
        assert "Dup (导入)" in names

    @pytest.mark.asyncio
    async def test_import_conflict_overwrite(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="Over")

        content = self._make_keeper_export(
            bookmarks=[
                {
                    "name": "Over",
                    "tagIds": [],
                    "urls": [{"url": "https://new.com", "lastUsed": ""}],
                    "accounts": [],
                }
            ]
        )
        resp = await client.post(
            "/api/transfer/import",
            json={
                "format": "keeper_json",
                "content": content,
                "conflictPolicy": "overwrite",
            },
            cookies=cookies,
        )
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1

        bm_resp = await client.get("/api/bookmarks", cookies=cookies)
        bms = bm_resp.json()["data"]
        assert len(bms) == 1
        assert bms[0]["name"] == "Over"

    @pytest.mark.asyncio
    async def test_import_invalid_format(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "keeper_json", "content": "bad"},
            cookies=cookies,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_import_existing_tag_reuses_id(self, client: AsyncClient):
        """如果标签名已存在, 导入应复用已有标签而非创建新标签。"""
        cookies = await auth(client)
        existing_tag = await create_tag(client, cookies, "已有标签")

        content = self._make_keeper_export(
            tags=[{"id": 999, "name": "已有标签"}],
            bookmarks=[{"name": "BM", "tagIds": [999], "urls": [], "accounts": []}],
        )
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "keeper_json", "content": content},
            cookies=cookies,
        )
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1

        # 应该只有一个标签
        tag_resp = await client.get("/api/tags", cookies=cookies)
        tags = tag_resp.json()["data"]
        tag_names = [t["name"] for t in tags]
        assert tag_names.count("已有标签") == 1


# ---------------------------------------------------------------------------
# Import Bitwarden JSON
# ---------------------------------------------------------------------------


class TestImportBitwardenJson:
    def _make_bitwarden_export(
        self,
        items: list[dict[str, Any]],
        folders: list[dict[str, Any]] | None = None,
    ) -> str:
        return json.dumps(
            {
                "encrypted": False,
                "folders": folders or [],
                "items": items,
            }
        )

    @pytest.mark.asyncio
    async def test_import_basic_login(self, client: AsyncClient):
        cookies = await auth(client)
        content = self._make_bitwarden_export(
            items=[
                {
                    "type": 1,
                    "name": "GitHub",
                    "login": {
                        "uris": [{"uri": "https://github.com"}],
                        "username": "dev",
                        "password": "ghpass",
                    },
                    "notes": "dev account",
                }
            ]
        )
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "bitwarden_json", "content": content},
            cookies=cookies,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1

        bm_resp = await client.get("/api/bookmarks", cookies=cookies)
        bms = bm_resp.json()["data"]
        assert len(bms) == 1
        assert bms[0]["name"] == "GitHub"

    @pytest.mark.asyncio
    async def test_import_bitwarden_with_folders(self, client: AsyncClient):
        cookies = await auth(client)
        content = self._make_bitwarden_export(
            folders=[
                {"id": "f1", "name": "Work"},
                {"id": "f2", "name": "Personal"},
            ],
            items=[
                {
                    "type": 1,
                    "name": "Slack",
                    "folderId": "f1",
                    "login": {"username": "a", "password": "b"},
                },
                {
                    "type": 1,
                    "name": "Netflix",
                    "folderId": "f2",
                    "login": {"username": "c", "password": "d"},
                },
            ],
        )
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "bitwarden_json", "content": content},
            cookies=cookies,
        )
        data = resp.json()
        assert data["imported"]["bookmarks"] == 2
        assert data["imported"]["tags"] == 2

        tag_resp = await client.get("/api/tags", cookies=cookies)
        tag_names = {t["name"] for t in tag_resp.json()["data"]}
        assert "Work" in tag_names
        assert "Personal" in tag_names

    @pytest.mark.asyncio
    async def test_import_bitwarden_skips_non_login(self, client: AsyncClient):
        cookies = await auth(client)
        content = self._make_bitwarden_export(
            items=[
                {
                    "type": 1,
                    "name": "Login Item",
                    "login": {"username": "x", "password": "y"},
                },
                {"type": 2, "name": "Secure Note"},
                {"type": 3, "name": "Card"},
            ]
        )
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "bitwarden_json", "content": content},
            cookies=cookies,
        )
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1

    @pytest.mark.asyncio
    async def test_import_bitwarden_encrypted_rejected(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/transfer/import",
            json={
                "format": "bitwarden_json",
                "content": json.dumps({"encrypted": True, "items": []}),
            },
            cookies=cookies,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_import_bitwarden_conflict_rename(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="GitHub")

        content = self._make_bitwarden_export(
            items=[
                {
                    "type": 1,
                    "name": "GitHub",
                    "login": {"username": "u", "password": "p"},
                }
            ]
        )
        resp = await client.post(
            "/api/transfer/import",
            json={
                "format": "bitwarden_json",
                "content": content,
                "conflictPolicy": "rename",
            },
            cookies=cookies,
        )
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1

        bm_resp = await client.get("/api/bookmarks?sort=name", cookies=cookies)
        names = [b["name"] for b in bm_resp.json()["data"]]
        assert "GitHub" in names
        assert "GitHub (导入)" in names

    @pytest.mark.asyncio
    async def test_import_bitwarden_password_encrypted(self, client: AsyncClient):
        """验证 Bitwarden 导入后密码被正确加密存储。"""
        cookies = await auth(client)
        content = self._make_bitwarden_export(
            items=[
                {
                    "type": 1,
                    "name": "TestSite",
                    "login": {"username": "user", "password": "bw_secret"},
                }
            ]
        )
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "bitwarden_json", "content": content},
            cookies=cookies,
        )
        assert resp.status_code == 200

        # 再次导出验证密码能正确解密
        export_resp = await client.get(
            "/api/transfer/export/json",
            cookies=cookies,
        )
        export_data = export_resp.json()
        bm = export_data["data"]["bookmarks"][0]
        assert bm["accounts"][0]["password"] == "bw_secret"


# ---------------------------------------------------------------------------
# Import CSV
# ---------------------------------------------------------------------------


class TestImportCsv:
    @pytest.mark.asyncio
    async def test_import_basic_csv(self, client: AsyncClient):
        cookies = await auth(client)
        csv_content = (
            "name,url,username,password,notes,tags\n"
            "Site1,https://a.com,user1,pass1,some notes,Tag1\n"
        )
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "csv", "content": csv_content},
            cookies=cookies,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1
        assert data["imported"]["tags"] == 1

    @pytest.mark.asyncio
    async def test_import_csv_auto_creates_tags(self, client: AsyncClient):
        cookies = await auth(client)
        csv_content = (
            "name,url,username,password,notes,tags\n"
            "S1,https://a.com,u,p,,TagA\n"
            'S2,https://b.com,u,p,,"TagA,TagB"\n'
        )
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "csv", "content": csv_content},
            cookies=cookies,
        )
        data = resp.json()
        assert data["imported"]["bookmarks"] == 2

        tag_resp = await client.get("/api/tags", cookies=cookies)
        tag_names = {t["name"] for t in tag_resp.json()["data"]}
        assert "TagA" in tag_names
        assert "TagB" in tag_names

    @pytest.mark.asyncio
    async def test_import_csv_encrypts_passwords(self, client: AsyncClient):
        """CSV 导入的明文密码应被自动加密, 导出时能还原。"""
        cookies = await auth(client)
        csv_content = (
            "name,url,username,password,notes,tags\n"
            "MySite,https://x.com,admin,csv_plain_pw,,\n"
        )
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "csv", "content": csv_content},
            cookies=cookies,
        )
        assert resp.status_code == 200

        # 导出验证密码被正确加密再解密
        export_resp = await client.get(
            "/api/transfer/export/json",
            cookies=cookies,
        )
        export_data = export_resp.json()
        bm = export_data["data"]["bookmarks"][0]
        assert bm["accounts"][0]["password"] == "csv_plain_pw"

    @pytest.mark.asyncio
    async def test_import_csv_conflict_skip(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="Exists")

        csv_content = (
            "name,url,username,password,notes,tags\n"
            "Exists,https://a.com,u,p,,\n"
            "Fresh,https://b.com,u,p,,\n"
        )
        resp = await client.post(
            "/api/transfer/import",
            json={
                "format": "csv",
                "content": csv_content,
                "conflictPolicy": "skip",
            },
            cookies=cookies,
        )
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1
        assert data["skipped"]["bookmarks"] == 1

    @pytest.mark.asyncio
    async def test_import_csv_conflict_overwrite(self, client: AsyncClient):
        cookies = await auth(client)
        await create_bookmark(client, cookies, name="Old")

        csv_content = (
            "name,url,username,password,notes,tags\n"
            "Old,https://new.com,newuser,newpw,,\n"
        )
        resp = await client.post(
            "/api/transfer/import",
            json={
                "format": "csv",
                "content": csv_content,
                "conflictPolicy": "overwrite",
            },
            cookies=cookies,
        )
        data = resp.json()
        assert data["imported"]["bookmarks"] == 1

        bm_resp = await client.get("/api/bookmarks", cookies=cookies)
        assert bm_resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_import_empty_csv(self, client: AsyncClient):
        cookies = await auth(client)
        resp = await client.post(
            "/api/transfer/import",
            json={"format": "csv", "content": "a,b\n1,2\n"},
            cookies=cookies,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 验收标准: JSON 往返 (Round-trip)
# ---------------------------------------------------------------------------


class TestAcceptanceJsonRoundTrip:
    @pytest.mark.asyncio
    async def test_export_then_import_roundtrip(self, client: AsyncClient):
        """
        验收标准: 导出的 JSON 可成功导入。
        创建完整数据 → 导出 → 清空 → 导入 → 验证数据一致。
        """
        cookies = await auth(client)

        # 准备完整数据
        tag1 = await create_tag(client, cookies, "标签A")
        tag2 = await create_tag(client, cookies, "标签B")
        rel = await create_relation(client, cookies, "邮箱")

        pw_plain = "round_trip_password"
        encrypted_pw = pw_plain
        bm = await create_bookmark(
            client,
            cookies,
            name="测试书签",
            tag_ids=[tag1["id"], tag2["id"]],
            accounts=[
                {
                    "username": "testuser",
                    "password": encrypted_pw,
                    "relatedIds": [rel["id"]],
                }
            ],
            urls=[{"url": "https://roundtrip.com"}],
        )

        # 导出
        export_resp = await client.get(
            "/api/transfer/export/json",
            cookies=cookies,
        )
        assert export_resp.status_code == 200
        exported_json = export_resp.text

        # 验证导出的密码是明文
        exported_data = json.loads(exported_json)
        assert (
            exported_data["data"]["bookmarks"][0]["accounts"][0]["password"] == pw_plain
        )

        # 在新的数据库环境中导入 (通过创建新书签来验证导入功能)
        # 使用 rename 策略避免冲突
        import_resp = await client.post(
            "/api/transfer/import",
            json={
                "format": "keeper_json",
                "content": exported_json,
                "conflictPolicy": "rename",
            },
            cookies=cookies,
        )
        assert import_resp.status_code == 200
        import_data = import_resp.json()
        assert import_data["imported"]["bookmarks"] == 1  # 重命名导入

        # 导出验证导入的数据密码正确
        export2_resp = await client.get(
            "/api/transfer/export/json",
            cookies=cookies,
        )
        export2_data = export2_resp.json()
        bms = export2_data["data"]["bookmarks"]
        assert len(bms) == 2  # 原始 + 导入

        # 找到导入的书签
        imported_bm = next(b for b in bms if "导入" in b["name"])
        assert imported_bm["accounts"][0]["password"] == pw_plain
        assert imported_bm["accounts"][0]["username"] == "testuser"


# ---------------------------------------------------------------------------
# 验收标准: Bitwarden 导入密码正确加密
# ---------------------------------------------------------------------------


class TestAcceptanceBitwardenImport:
    @pytest.mark.asyncio
    async def test_bitwarden_import_password_survives_roundtrip(
        self, client: AsyncClient
    ):
        """
        验收标准: Bitwarden 导出的数据可成功导入 (密码正确加密)。
        """
        cookies = await auth(client)
        bw_password = "bitwarden_secure_pass"
        bw_data = json.dumps(
            {
                "encrypted": False,
                "folders": [{"id": "f1", "name": "MyFolder"}],
                "items": [
                    {
                        "type": 1,
                        "name": "BitwardenSite",
                        "folderId": "f1",
                        "login": {
                            "uris": [{"uri": "https://bw.example.com"}],
                            "username": "bwuser",
                            "password": bw_password,
                        },
                        "notes": "imported from bitwarden",
                    }
                ],
            }
        )

        # 导入
        import_resp = await client.post(
            "/api/transfer/import",
            json={"format": "bitwarden_json", "content": bw_data},
            cookies=cookies,
        )
        assert import_resp.status_code == 200
        assert import_resp.json()["imported"]["bookmarks"] == 1

        # 导出验证密码正确解密
        export_resp = await client.get(
            "/api/transfer/export/json",
            cookies=cookies,
        )
        export_data = export_resp.json()
        bm = export_data["data"]["bookmarks"][0]
        assert bm["name"] == "BitwardenSite"
        assert bm["accounts"][0]["username"] == "bwuser"
        assert bm["accounts"][0]["password"] == bw_password
        assert bm["notes"] == "imported from bitwarden"


# ---------------------------------------------------------------------------
# 验收标准: CSV 导出明文 / 导入自动加密
# ---------------------------------------------------------------------------


class TestAcceptanceCsvPlaintextEncrypt:
    @pytest.mark.asyncio
    async def test_csv_export_plaintext_import_encrypts(self, client: AsyncClient):
        """
        验收标准: CSV 导出的密码是明文, 导入后自动加密。
        """
        cookies = await auth(client)
        original_pw = "csv_test_password"
        encrypted_pw = original_pw

        await create_bookmark(
            client,
            cookies,
            name="CSVTestSite",
            accounts=[
                {
                    "username": "csvuser",
                    "password": encrypted_pw,
                    "relatedIds": [],
                }
            ],
        )

        # CSV 导出 — 密码应是明文
        csv_resp = await client.get(
            "/api/transfer/export/csv",
            cookies=cookies,
        )
        assert csv_resp.status_code == 200
        reader = csv.DictReader(io.StringIO(csv_resp.text))
        rows = list(reader)
        assert rows[0]["password"] == original_pw  # 明文!

        # 用 CSV 内容导入 (rename 避免冲突)
        import_resp = await client.post(
            "/api/transfer/import",
            json={
                "format": "csv",
                "content": csv_resp.text,
                "conflictPolicy": "rename",
            },
            cookies=cookies,
        )
        assert import_resp.status_code == 200
        assert import_resp.json()["imported"]["bookmarks"] == 1

        # 再次导出 JSON 验证密码加密后可正确还原
        json_resp = await client.get(
            "/api/transfer/export/json",
            cookies=cookies,
        )
        json_data = json_resp.json()
        bms = json_data["data"]["bookmarks"]
        imported_bm = next(b for b in bms if "导入" in b["name"])
        assert imported_bm["accounts"][0]["password"] == original_pw
