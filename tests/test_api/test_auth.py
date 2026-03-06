import time

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
    """Reset database and session state between tests."""
    from sqlalchemy import text as sql_text

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


class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_success(self, client: AsyncClient):
        resp = await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert data["message"] == "初始化成功"

    @pytest.mark.asyncio
    async def test_initialize_duplicate_returns_409(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        assert resp.status_code == 409
        assert resp.json()["status"] == 409

    @pytest.mark.asyncio
    async def test_initialize_missing_email_returns_422(self, client: AsyncClient):
        bad = {**INIT_PAYLOAD, "email": ""}
        resp = await client.post("/api/auth/initialize", json=bad)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_initialize_missing_password_hash_returns_422(
        self, client: AsyncClient
    ):
        bad = {**INIT_PAYLOAD, "masterPasswordHash": ""}
        resp = await client.post("/api/auth/initialize", json=bad)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_initialize_stores_kdf_params(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        assert resp.status_code == 200
        kdf = resp.json()["kdfParams"]
        assert kdf["algorithm"] == "Argon2id"
        assert kdf["memory"] == 65536
        assert kdf["iterations"] == 3
        assert kdf["parallelism"] == 1


class TestUnlock:
    @pytest.mark.asyncio
    async def test_unlock_success(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "解锁成功"
        assert data["encryptedUserKey"] == INIT_PAYLOAD["encryptedUserKey"]

    @pytest.mark.asyncio
    async def test_unlock_sets_session_cookie(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        assert "keeper_session" in resp.cookies

    @pytest.mark.asyncio
    async def test_unlock_wrong_password_returns_403(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": "wrong_hash_value"},
        )
        assert resp.status_code == 403
        assert resp.json()["status"] == 403

    @pytest.mark.asyncio
    async def test_unlock_not_initialized_returns_400(self, client: AsyncClient):
        resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": "anything"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_unlock_returns_kdf_params(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        data = resp.json()
        assert "kdfParams" in data
        assert data["kdfParams"]["salt"] == INIT_PAYLOAD["email"]

    @pytest.mark.asyncio
    async def test_unlock_empty_password_hash_returns_422(self, client: AsyncClient):
        resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": ""},
        )
        assert resp.status_code == 422


class TestLock:
    @pytest.mark.asyncio
    async def test_lock_returns_204(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        resp = await client.post("/api/auth/lock")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_lock_invalidates_session(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        unlock_resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        session_cookie = unlock_resp.cookies.get("keeper_session")
        assert session_cookie is not None

        await client.post("/api/auth/lock")

        resp = await client.get(
            "/api/auth/status",
            cookies={"keeper_session": session_cookie},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_lock_clears_cookie(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        resp = await client.post("/api/auth/lock")
        cookie_header = resp.headers.get("set-cookie", "")
        assert "keeper_session" in cookie_header


class TestStatus:
    @pytest.mark.asyncio
    async def test_status_locked_without_session(self, client: AsyncClient):
        resp = await client.get("/api/auth/status")
        assert resp.status_code == 401
        assert resp.json()["locked"] is True

    @pytest.mark.asyncio
    async def test_status_unlocked_with_valid_session(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        unlock_resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        session_cookie = unlock_resp.cookies.get("keeper_session")
        assert session_cookie is not None

        resp = await client.get(
            "/api/auth/status",
            cookies={"keeper_session": session_cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["locked"] is False
        assert "sessionExpiresAt" in data

    @pytest.mark.asyncio
    async def test_status_locked_with_invalid_token(self, client: AsyncClient):
        resp = await client.get(
            "/api/auth/status",
            cookies={"keeper_session": "invalid_token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_status_locked_after_session_expires(self, client: AsyncClient):
        app.state.session_manager = SessionManager(ttl_seconds=1)
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        unlock_resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        session_cookie = unlock_resp.cookies.get("keeper_session")
        assert session_cookie is not None
        time.sleep(1.1)

        resp = await client.get(
            "/api/auth/status",
            cookies={"keeper_session": session_cookie},
        )
        assert resp.status_code == 401
        assert resp.json()["locked"] is True


class TestAuthMiddleware:
    @pytest.mark.asyncio
    async def test_health_exempt_from_auth(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_root_exempt_from_auth(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_protected_route_returns_401_without_session(
        self, client: AsyncClient
    ):
        resp = await client.get("/api/bookmarks")
        assert resp.status_code in (401, 404)

    @pytest.mark.asyncio
    async def test_initialize_exempt_from_auth(self, client: AsyncClient):
        resp = await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_unlock_exempt_from_auth(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        assert resp.status_code == 200


class TestSessionManager:
    def test_create_session(self):
        mgr = SessionManager()
        session = mgr.create()
        assert session.token
        assert session.expires_at > session.created_at

    def test_validate_valid_token(self):
        mgr = SessionManager()
        session = mgr.create()
        assert mgr.validate(session.token) is not None

    def test_validate_invalid_token(self):
        mgr = SessionManager()
        mgr.create()
        assert mgr.validate("wrong_token") is None

    def test_validate_no_session(self):
        mgr = SessionManager()
        assert mgr.validate("any_token") is None

    def test_revoke_clears_session(self):
        mgr = SessionManager()
        session = mgr.create()
        mgr.revoke()
        assert mgr.validate(session.token) is None

    def test_expired_session_returns_none(self):
        mgr = SessionManager(ttl_seconds=0)
        session = mgr.create()
        time.sleep(0.01)
        assert mgr.validate(session.token) is None

    def test_active_session_property(self):
        mgr = SessionManager()
        assert mgr.active_session is None
        session = mgr.create()
        assert mgr.active_session is not None
        assert mgr.active_session.token == session.token

    def test_active_session_expired(self):
        mgr = SessionManager(ttl_seconds=0)
        mgr.create()
        time.sleep(0.01)
        assert mgr.active_session is None

    def test_create_replaces_previous_session(self):
        mgr = SessionManager()
        s1 = mgr.create()
        s2 = mgr.create()
        assert s1.token != s2.token
        assert mgr.validate(s1.token) is None
        assert mgr.validate(s2.token) is not None


class TestCookieAttributes:
    @pytest.mark.asyncio
    async def test_unlock_cookie_httponly(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        cookie_header = resp.headers.get("set-cookie", "")
        assert "httponly" in cookie_header.lower()

    @pytest.mark.asyncio
    async def test_unlock_cookie_secure(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        cookie_header = resp.headers.get("set-cookie", "")
        assert "secure" in cookie_header.lower()

    @pytest.mark.asyncio
    async def test_unlock_cookie_samesite_strict(self, client: AsyncClient):
        await client.post("/api/auth/initialize", json=INIT_PAYLOAD)
        resp = await client.post(
            "/api/auth/unlock",
            json={"masterPasswordHash": INIT_PAYLOAD["masterPasswordHash"]},
        )
        cookie_header = resp.headers.get("set-cookie", "")
        assert "samesite=strict" in cookie_header.lower()
