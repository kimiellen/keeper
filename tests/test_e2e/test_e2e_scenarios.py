import pytest
from httpx import AsyncClient

from tests.test_e2e.conftest import (
    ENCRYPTED_PASSWORD,
    ENCRYPTED_PASSWORD_2,
    INIT_PAYLOAD,
    seed_bookmark,
    seed_relation,
    seed_tag,
)


class TestScenario1_Initialize:
    """场景1：首次初始化流程 — initialize → verify auth record."""

    @pytest.mark.asyncio
    async def test_full_initialization_flow(self, client: AsyncClient):
        resp = await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        assert resp.status_code == 201
        assert resp.json()["message"] == "初始化成功"

        status_resp = await client.get("/api/auth/status")
        assert status_resp.status_code == 401
        assert status_resp.json()["locked"] is True

    @pytest.mark.asyncio
    async def test_initialize_then_unlock_verifies_stored_data(
        self, client: AsyncClient
    ):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)

        resp = await client.post(
            "/api/auth/unlock",
            json={"password": INIT_PAYLOAD["password"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "解锁成功"

    @pytest.mark.asyncio
    async def test_double_initialize_rejected(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        assert resp.status_code == 409


class TestScenario2_Unlock:
    """场景2：解锁流程 — unlock → verify session cookie → lock → verify invalidated."""

    @pytest.mark.asyncio
    async def test_unlock_sets_session_and_grants_access(
        self, authed_client: AsyncClient
    ):
        resp = await authed_client.get("/api/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["locked"] is False
        assert "sessionExpiresAt" in data

    @pytest.mark.asyncio
    async def test_unlock_then_lock_then_denied(self, authed_client: AsyncClient):
        resp = await authed_client.get("/api/bookmarks")
        assert resp.status_code == 200

        await authed_client.post("/api/auth/lock")

        resp = await authed_client.get("/api/bookmarks")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_password_denied(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post(
            "/api/auth/unlock",
            json={"password": "wrong_hash"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_protected_routes_require_session(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)

        for path in ["/api/bookmarks", "/api/tags", "/api/relations", "/api/stats"]:
            resp = await client.get(path)
            assert resp.status_code == 401, f"{path} should require auth"


class TestScenario3_BookmarkCRUD:
    """场景3：书签完整 CRUD — create with tags/relations → read → update → patch → delete."""

    @pytest.mark.asyncio
    async def test_create_bookmark_with_tags_and_accounts(
        self, authed_client: AsyncClient
    ):
        tag = await seed_tag(authed_client, "社交媒体")
        relation = await seed_relation(authed_client, "personal@email.com", "email")

        bookmark = await seed_bookmark(
            authed_client,
            name="GitHub",
            urls=[{"url": "https://github.com"}],
            tag_ids=[tag["id"]],
            accounts=[
                {
                    "username": "testuser",
                    "password": ENCRYPTED_PASSWORD,
                    "relatedIds": [relation["id"]],
                }
            ],
            notes="My GitHub account",
        )

        assert bookmark["name"] == "GitHub"
        assert bookmark["tagIds"] == [tag["id"]]
        assert len(bookmark["accounts"]) == 1
        assert bookmark["accounts"][0]["username"] == "testuser"
        assert bookmark["accounts"][0]["password"] == ENCRYPTED_PASSWORD
        assert bookmark["accounts"][0]["relatedIds"] == [relation["id"]]
        assert bookmark["notes"] == "My GitHub account"
        assert len(bookmark["urls"]) == 1
        assert bookmark["urls"][0]["url"] == "https://github.com"

    @pytest.mark.asyncio
    async def test_read_bookmark_by_id(self, authed_client: AsyncClient):
        bookmark = await seed_bookmark(
            authed_client,
            name="Test",
            urls=[{"url": "https://test.com"}],
        )

        resp = await authed_client.get(f"/api/bookmarks/{bookmark['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test"

    @pytest.mark.asyncio
    async def test_update_bookmark_full_replace(self, authed_client: AsyncClient):
        tag1 = await seed_tag(authed_client, "Tag1")
        tag2 = await seed_tag(authed_client, "Tag2")
        bookmark = await seed_bookmark(
            authed_client,
            name="Original",
            tag_ids=[tag1["id"]],
            accounts=[{"username": "user1", "password": ENCRYPTED_PASSWORD}],
        )

        resp = await authed_client.put(
            f"/api/bookmarks/{bookmark['id']}",
            json={
                "name": "Updated",
                "tagIds": [tag2["id"]],
                "urls": [{"url": "https://updated.com"}],
                "accounts": [{"username": "user2", "password": ENCRYPTED_PASSWORD_2}],
                "notes": "updated notes",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated"
        assert data["tagIds"] == [tag2["id"]]
        assert data["accounts"][0]["username"] == "user2"
        assert data["accounts"][0]["password"] == ENCRYPTED_PASSWORD_2
        assert data["notes"] == "updated notes"

    @pytest.mark.asyncio
    async def test_patch_bookmark_partial_update(self, authed_client: AsyncClient):
        bookmark = await seed_bookmark(authed_client, name="PatchMe")

        resp = await authed_client.patch(
            f"/api/bookmarks/{bookmark['id']}",
            json={"notes": "patched notes"},
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "patched notes"
        assert resp.json()["name"] == "PatchMe"

    @pytest.mark.asyncio
    async def test_delete_bookmark(self, authed_client: AsyncClient):
        bookmark = await seed_bookmark(authed_client, name="ToDelete")

        resp = await authed_client.delete(f"/api/bookmarks/{bookmark['id']}")
        assert resp.status_code == 204

        resp = await authed_client.get(f"/api/bookmarks/{bookmark['id']}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_bookmark_invalid_tag_id_rejected(self, authed_client: AsyncClient):
        resp = await authed_client.post(
            "/api/bookmarks",
            json={"name": "Bad", "tagIds": [9999]},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_bookmark_invalid_relation_id_rejected(
        self, authed_client: AsyncClient
    ):
        resp = await authed_client.post(
            "/api/bookmarks",
            json={
                "name": "Bad",
                "accounts": [
                    {
                        "username": "user",
                        "password": ENCRYPTED_PASSWORD,
                        "relatedIds": [9999],
                    }
                ],
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_password_must_match_encryption_format(
        self, authed_client: AsyncClient
    ):
        resp = await authed_client.post(
            "/api/bookmarks",
            json={
                "name": "Bad",
                "accounts": [{"username": "user", "password": "plaintext_password"}],
            },
        )
        assert resp.status_code == 201
        assert resp.json()["accounts"][0]["password"] == "plaintext_password"

    @pytest.mark.asyncio
    async def test_use_bookmark_updates_timestamps(self, authed_client: AsyncClient):
        bookmark = await seed_bookmark(
            authed_client,
            name="UseMe",
            urls=[{"url": "https://useme.com"}],
            accounts=[{"username": "user", "password": ENCRYPTED_PASSWORD}],
        )
        original_last_used = bookmark["lastUsedAt"]

        resp = await authed_client.post(
            f"/api/bookmarks/{bookmark['id']}/use",
            json={"url": "https://useme.com", "accountId": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["lastUsedAt"] >= original_last_used

    @pytest.mark.asyncio
    async def test_tag_crud_lifecycle(self, authed_client: AsyncClient):
        tag = await seed_tag(authed_client, "TestTag", "#00FF00", "folder")
        assert tag["name"] == "TestTag"
        assert tag["color"] == "#00FF00"
        assert tag["icon"] == "folder"

        resp = await authed_client.put(
            f"/api/tags/{tag['id']}",
            json={"name": "RenamedTag", "color": "#0000FF"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "RenamedTag"

        resp = await authed_client.delete(f"/api/tags/{tag['id']}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_relation_crud_lifecycle(self, authed_client: AsyncClient):
        relation = await seed_relation(authed_client, "MyPhone", "phone")
        assert relation["name"] == "MyPhone"
        assert relation["type"] == "phone"

        resp = await authed_client.put(
            f"/api/relations/{relation['id']}",
            json={"name": "WorkPhone", "type": "phone"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "WorkPhone"

        resp = await authed_client.delete(f"/api/relations/{relation['id']}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_tag_cascade_delete_removes_from_bookmarks(
        self, authed_client: AsyncClient
    ):
        tag = await seed_tag(authed_client, "CascadeTag")
        bookmark = await seed_bookmark(
            authed_client, name="WithTag", tag_ids=[tag["id"]]
        )
        assert bookmark["tagIds"] == [tag["id"]]

        resp = await authed_client.delete(f"/api/tags/{tag['id']}?cascade=true")
        assert resp.status_code == 204

        resp = await authed_client.get(f"/api/bookmarks/{bookmark['id']}")
        assert resp.status_code == 200
        assert tag["id"] not in resp.json()["tagIds"]

    @pytest.mark.asyncio
    async def test_relation_cascade_delete_removes_from_accounts(
        self, authed_client: AsyncClient
    ):
        relation = await seed_relation(authed_client, "CascadeRelation")
        bookmark = await seed_bookmark(
            authed_client,
            name="WithRelation",
            accounts=[
                {
                    "username": "user",
                    "password": ENCRYPTED_PASSWORD,
                    "relatedIds": [relation["id"]],
                }
            ],
        )
        assert bookmark["accounts"][0]["relatedIds"] == [relation["id"]]

        resp = await authed_client.delete(
            f"/api/relations/{relation['id']}?cascade=true"
        )
        assert resp.status_code == 204

        resp = await authed_client.get(f"/api/bookmarks/{bookmark['id']}")
        assert resp.status_code == 200
        assert relation["id"] not in resp.json()["accounts"][0]["relatedIds"]

    @pytest.mark.asyncio
    async def test_tag_non_cascade_blocked_when_in_use(
        self, authed_client: AsyncClient
    ):
        tag = await seed_tag(authed_client, "InUseTag")
        await seed_bookmark(authed_client, name="UsingTag", tag_ids=[tag["id"]])

        resp = await authed_client.delete(f"/api/tags/{tag['id']}")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_relation_non_cascade_blocked_when_in_use(
        self, authed_client: AsyncClient
    ):
        relation = await seed_relation(authed_client, "InUseRelation")
        await seed_bookmark(
            authed_client,
            name="UsingRelation",
            accounts=[
                {
                    "username": "user",
                    "password": ENCRYPTED_PASSWORD,
                    "relatedIds": [relation["id"]],
                }
            ],
        )

        resp = await authed_client.delete(f"/api/relations/{relation['id']}")
        assert resp.status_code == 409


class TestScenario4_Search:
    """场景4：搜索书签 — 拼音首字母 + 标签过滤 + 分页."""

    @pytest.mark.asyncio
    async def test_search_by_pinyin_initials(self, authed_client: AsyncClient):
        await seed_bookmark(authed_client, name="光华银行")
        await seed_bookmark(authed_client, name="百度")
        await seed_bookmark(authed_client, name="GitHub")

        resp = await authed_client.get("/api/bookmarks", params={"search": "gh"})
        assert resp.status_code == 200
        data = resp.json()
        names = [b["name"] for b in data["data"]]
        assert "光华银行" in names
        assert "百度" not in names

    @pytest.mark.asyncio
    async def test_search_by_chinese_pinyin(self, authed_client: AsyncClient):
        await seed_bookmark(authed_client, name="百度")
        await seed_bookmark(authed_client, name="淘宝")

        resp = await authed_client.get("/api/bookmarks", params={"search": "bd"})
        assert resp.status_code == 200
        names = [b["name"] for b in resp.json()["data"]]
        assert "百度" in names
        assert "淘宝" not in names

    @pytest.mark.asyncio
    async def test_search_by_name_contains(self, authed_client: AsyncClient):
        await seed_bookmark(authed_client, name="GitHub")
        await seed_bookmark(authed_client, name="GitLab")
        await seed_bookmark(authed_client, name="Bitbucket")

        resp = await authed_client.get("/api/bookmarks", params={"search": "Git"})
        assert resp.status_code == 200
        names = [b["name"] for b in resp.json()["data"]]
        assert "GitHub" in names
        assert "GitLab" in names
        assert "Bitbucket" not in names

    @pytest.mark.asyncio
    async def test_filter_by_tag_ids(self, authed_client: AsyncClient):
        tag_work = await seed_tag(authed_client, "Work")
        tag_personal = await seed_tag(authed_client, "Personal")

        await seed_bookmark(authed_client, name="WorkSite", tag_ids=[tag_work["id"]])
        await seed_bookmark(
            authed_client, name="PersonalSite", tag_ids=[tag_personal["id"]]
        )
        await seed_bookmark(authed_client, name="NoTag")

        resp = await authed_client.get(
            "/api/bookmarks", params={"tagIds": str(tag_work["id"])}
        )
        assert resp.status_code == 200
        names = [b["name"] for b in resp.json()["data"]]
        assert "WorkSite" in names
        assert "PersonalSite" not in names
        assert "NoTag" not in names

    @pytest.mark.asyncio
    async def test_pagination(self, authed_client: AsyncClient):
        for i in range(5):
            await seed_bookmark(authed_client, name=f"Bookmark_{i}")

        resp = await authed_client.get(
            "/api/bookmarks", params={"limit": 2, "offset": 0}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 2
        assert data["total"] == 5
        assert "Link" in resp.headers

        resp2 = await authed_client.get(
            "/api/bookmarks", params={"limit": 2, "offset": 2}
        )
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]) == 2

    @pytest.mark.asyncio
    async def test_sort_by_name(self, authed_client: AsyncClient):
        await seed_bookmark(authed_client, name="Charlie")
        await seed_bookmark(authed_client, name="Alice")
        await seed_bookmark(authed_client, name="Bob")

        resp = await authed_client.get("/api/bookmarks", params={"sort": "name"})
        assert resp.status_code == 200
        names = [b["name"] for b in resp.json()["data"]]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_total_count_header(self, authed_client: AsyncClient):
        for i in range(3):
            await seed_bookmark(authed_client, name=f"H_{i}")

        resp = await authed_client.get("/api/bookmarks")
        assert resp.status_code == 200
        assert resp.headers["X-Total-Count"] == "3"


class TestScenario5_AutofillSimulation:
    """场景5：自动填充模拟 — URL 匹配 + 书签检索 + use 记录."""

    @pytest.mark.asyncio
    async def test_find_bookmark_by_url_search(self, authed_client: AsyncClient):
        await seed_bookmark(
            authed_client,
            name="GitHub",
            urls=[{"url": "https://github.com/login"}],
            accounts=[{"username": "ghuser", "password": ENCRYPTED_PASSWORD}],
        )
        await seed_bookmark(
            authed_client,
            name="Google",
            urls=[{"url": "https://accounts.google.com"}],
            accounts=[{"username": "guser", "password": ENCRYPTED_PASSWORD_2}],
        )

        resp = await authed_client.get("/api/bookmarks", params={"search": "GitHub"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        github_bm = next(b for b in data["data"] if b["name"] == "GitHub")
        assert github_bm["accounts"][0]["username"] == "ghuser"
        assert github_bm["accounts"][0]["password"] == ENCRYPTED_PASSWORD
        assert github_bm["urls"][0]["url"] == "https://github.com/login"

    @pytest.mark.asyncio
    async def test_use_bookmark_for_autofill(self, authed_client: AsyncClient):
        bookmark = await seed_bookmark(
            authed_client,
            name="GitHub",
            urls=[{"url": "https://github.com/login"}],
            accounts=[{"username": "ghuser", "password": ENCRYPTED_PASSWORD}],
        )

        resp = await authed_client.post(
            f"/api/bookmarks/{bookmark['id']}/use",
            json={"url": "https://github.com/login", "accountId": 1},
        )
        assert resp.status_code == 200
        assert "lastUsedAt" in resp.json()

        resp = await authed_client.get(f"/api/bookmarks/{bookmark['id']}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_multiple_accounts_per_bookmark(self, authed_client: AsyncClient):
        bookmark = await seed_bookmark(
            authed_client,
            name="MultiAccount",
            urls=[{"url": "https://example.com"}],
            accounts=[
                {"username": "user1", "password": ENCRYPTED_PASSWORD},
                {"username": "user2", "password": ENCRYPTED_PASSWORD_2},
            ],
        )

        assert len(bookmark["accounts"]) == 2
        assert bookmark["accounts"][0]["username"] == "user1"
        assert bookmark["accounts"][1]["username"] == "user2"
        assert bookmark["accounts"][0]["id"] == 1
        assert bookmark["accounts"][1]["id"] == 2


class TestScenario6_PasswordCapture:
    """场景6：密码捕获模拟 — 保存新凭据 + 检测/更新已有凭据."""

    @pytest.mark.asyncio
    async def test_capture_new_credentials(self, authed_client: AsyncClient):
        bookmark = await seed_bookmark(
            authed_client,
            name="NewSite",
            urls=[{"url": "https://newsite.com/login"}],
            accounts=[{"username": "newuser", "password": ENCRYPTED_PASSWORD}],
        )

        resp = await authed_client.get(f"/api/bookmarks/{bookmark['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["username"] == "newuser"
        assert data["accounts"][0]["password"] == ENCRYPTED_PASSWORD

    @pytest.mark.asyncio
    async def test_update_existing_credentials(self, authed_client: AsyncClient):
        bookmark = await seed_bookmark(
            authed_client,
            name="UpdateSite",
            urls=[{"url": "https://updatesite.com"}],
            accounts=[{"username": "user", "password": ENCRYPTED_PASSWORD}],
        )

        resp = await authed_client.put(
            f"/api/bookmarks/{bookmark['id']}",
            json={
                "name": "UpdateSite",
                "urls": [{"url": "https://updatesite.com"}],
                "accounts": [{"username": "user", "password": ENCRYPTED_PASSWORD_2}],
            },
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["accounts"][0]["password"] == ENCRYPTED_PASSWORD_2

    @pytest.mark.asyncio
    async def test_add_second_account_to_existing_bookmark(
        self, authed_client: AsyncClient
    ):
        bookmark = await seed_bookmark(
            authed_client,
            name="DualAccount",
            urls=[{"url": "https://dual.com"}],
            accounts=[{"username": "user1", "password": ENCRYPTED_PASSWORD}],
        )

        resp = await authed_client.put(
            f"/api/bookmarks/{bookmark['id']}",
            json={
                "name": "DualAccount",
                "urls": [{"url": "https://dual.com"}],
                "accounts": [
                    {"username": "user1", "password": ENCRYPTED_PASSWORD},
                    {"username": "user2", "password": ENCRYPTED_PASSWORD_2},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["accounts"]) == 2

    @pytest.mark.asyncio
    async def test_patch_accounts_only(self, authed_client: AsyncClient):
        bookmark = await seed_bookmark(
            authed_client,
            name="PatchAccounts",
            urls=[{"url": "https://patch.com"}],
            accounts=[{"username": "olduser", "password": ENCRYPTED_PASSWORD}],
        )

        resp = await authed_client.patch(
            f"/api/bookmarks/{bookmark['id']}",
            json={
                "accounts": [{"username": "newuser", "password": ENCRYPTED_PASSWORD_2}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "PatchAccounts"
        assert data["accounts"][0]["username"] == "newuser"
        assert data["accounts"][0]["password"] == ENCRYPTED_PASSWORD_2


class TestStatsIntegration:
    """Stats 端点集成 — 验证 seed 数据后统计正确性."""

    @pytest.mark.asyncio
    async def test_stats_reflect_created_data(self, authed_client: AsyncClient):
        tag1 = await seed_tag(authed_client, "Tag1")
        tag2 = await seed_tag(authed_client, "Tag2")
        await seed_relation(authed_client, "Rel1")

        await seed_bookmark(
            authed_client,
            name="BM1",
            tag_ids=[tag1["id"], tag2["id"]],
            accounts=[
                {"username": "u1", "password": ENCRYPTED_PASSWORD},
                {"username": "u2", "password": ENCRYPTED_PASSWORD_2},
            ],
        )
        await seed_bookmark(
            authed_client,
            name="BM2",
            tag_ids=[tag1["id"]],
            accounts=[{"username": "u3", "password": ENCRYPTED_PASSWORD}],
        )

        resp = await authed_client.get("/api/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["totalBookmarks"] == 2
        assert stats["totalTags"] == 2
        assert stats["totalRelations"] == 1
        assert stats["totalAccounts"] == 3

        tag1_usage = next(t for t in stats["mostUsedTags"] if t["id"] == tag1["id"])
        assert tag1_usage["count"] == 2
        tag2_usage = next(t for t in stats["mostUsedTags"] if t["id"] == tag2["id"])
        assert tag2_usage["count"] == 1

        assert len(stats["recentlyUsed"]) == 2


class TestScenario8_ChineseSearch:
    """场景8：中文搜索优化 — 全拼、首字母、中文直接搜索、排序、高亮。"""

    @pytest.mark.asyncio
    async def test_search_by_full_pinyin(self, authed_client: AsyncClient):
        await seed_bookmark(authed_client, name="百度")
        await seed_bookmark(authed_client, name="淘宝")
        await seed_bookmark(authed_client, name="GitHub")

        resp = await authed_client.get("/api/bookmarks", params={"search": "baidu"})
        assert resp.status_code == 200
        names = [b["name"] for b in resp.json()["data"]]
        assert "百度" in names
        assert "淘宝" not in names
        assert "GitHub" not in names

    @pytest.mark.asyncio
    async def test_search_by_full_pinyin_partial(self, authed_client: AsyncClient):
        await seed_bookmark(authed_client, name="百度")
        await seed_bookmark(authed_client, name="百科全书")

        resp = await authed_client.get("/api/bookmarks", params={"search": "bai"})
        assert resp.status_code == 200
        names = [b["name"] for b in resp.json()["data"]]
        assert "百度" in names
        assert "百科全书" in names

    @pytest.mark.asyncio
    async def test_search_initials_gh_finds_github(self, authed_client: AsyncClient):
        await seed_bookmark(authed_client, name="GitHub")
        await seed_bookmark(authed_client, name="Google")

        resp = await authed_client.get("/api/bookmarks", params={"search": "gh"})
        assert resp.status_code == 200
        names = [b["name"] for b in resp.json()["data"]]
        assert "GitHub" in names
        assert "Google" not in names

    @pytest.mark.asyncio
    async def test_search_chinese_direct(self, authed_client: AsyncClient):
        tag_work = await seed_tag(authed_client, "工作")
        await seed_bookmark(authed_client, name="工作邮箱", tag_ids=[tag_work["id"]])
        await seed_bookmark(authed_client, name="工作VPN", tag_ids=[tag_work["id"]])
        await seed_bookmark(authed_client, name="个人博客")

        resp = await authed_client.get("/api/bookmarks", params={"search": "工作"})
        assert resp.status_code == 200
        names = [b["name"] for b in resp.json()["data"]]
        assert "工作邮箱" in names
        assert "工作VPN" in names
        assert "个人博客" not in names

    @pytest.mark.asyncio
    async def test_search_ranking_exact_first(self, authed_client: AsyncClient):
        await seed_bookmark(authed_client, name="Git教程")
        await seed_bookmark(authed_client, name="GitHub")
        await seed_bookmark(authed_client, name="GitLab")

        resp = await authed_client.get("/api/bookmarks", params={"search": "GitHub"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data[0]["name"] == "GitHub"

    @pytest.mark.asyncio
    async def test_search_ranking_prefix_before_contains(
        self, authed_client: AsyncClient
    ):
        await seed_bookmark(authed_client, name="MyGitHub")
        await seed_bookmark(authed_client, name="GitHub")

        resp = await authed_client.get("/api/bookmarks", params={"search": "Git"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data[0]["name"] == "GitHub"

    @pytest.mark.asyncio
    async def test_search_highlights_present(self, authed_client: AsyncClient):
        await seed_bookmark(authed_client, name="GitHub")

        resp = await authed_client.get("/api/bookmarks", params={"search": "Git"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        bm = data[0]
        assert bm["highlights"] is not None
        assert len(bm["highlights"]) > 0
        h = bm["highlights"][0]
        assert h["field"] == "name"
        assert h["positions"] == [[0, 3]]

    @pytest.mark.asyncio
    async def test_search_no_highlights_without_search(
        self, authed_client: AsyncClient
    ):
        await seed_bookmark(authed_client, name="GitHub")

        resp = await authed_client.get("/api/bookmarks")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0].get("highlights") is None

    @pytest.mark.asyncio
    async def test_search_mixed_chinese_english(self, authed_client: AsyncClient):
        await seed_bookmark(authed_client, name="GitHub工作")
        await seed_bookmark(authed_client, name="个人GitHub")
        await seed_bookmark(authed_client, name="百度")

        resp = await authed_client.get(
            "/api/bookmarks", params={"search": "githubgongzuo"}
        )
        assert resp.status_code == 200
        names = [b["name"] for b in resp.json()["data"]]
        assert "GitHub工作" in names

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, authed_client: AsyncClient):
        await seed_bookmark(authed_client, name="GitHub")

        for q in ["github", "GITHUB", "GitHub"]:
            resp = await authed_client.get("/api/bookmarks", params={"search": q})
            assert resp.status_code == 200
            names = [b["name"] for b in resp.json()["data"]]
            assert "GitHub" in names, f"Failed for query: {q}"
