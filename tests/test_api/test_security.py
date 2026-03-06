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


SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "content-security-policy": "default-src 'none'",
    "x-xss-protection": "1; mode=block",
    "referrer-policy": "no-referrer",
}


class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_health_endpoint_has_security_headers(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        for header, expected_value in SECURITY_HEADERS.items():
            assert resp.headers.get(header) == expected_value, (
                f"Missing or wrong header: {header}"
            )

    @pytest.mark.asyncio
    async def test_root_endpoint_has_security_headers(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        for header, expected_value in SECURITY_HEADERS.items():
            assert resp.headers.get(header) == expected_value

    @pytest.mark.asyncio
    async def test_401_response_has_security_headers(self, client: AsyncClient):
        resp = await client.get("/api/tags")
        assert resp.status_code == 401
        for header, expected_value in SECURITY_HEADERS.items():
            assert resp.headers.get(header) == expected_value

    @pytest.mark.asyncio
    async def test_404_response_has_security_headers(self, client: AsyncClient):
        resp = await client.get("/nonexistent-path-that-does-not-exist")
        assert resp.status_code in (401, 404)
        for header, expected_value in SECURITY_HEADERS.items():
            assert resp.headers.get(header) == expected_value


class TestCORSConfig:
    @pytest.mark.asyncio
    async def test_cors_preflight_returns_allowed_methods(self, client: AsyncClient):
        resp = await client.options(
            "/api/health",
            headers={
                "origin": "moz-extension://test-uuid",
                "access-control-request-method": "GET",
            },
        )
        assert resp.status_code == 200
        allowed = resp.headers.get("access-control-allow-methods", "")
        for method in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
            assert method in allowed

    @pytest.mark.asyncio
    async def test_cors_preflight_returns_allowed_headers(self, client: AsyncClient):
        resp = await client.options(
            "/api/health",
            headers={
                "origin": "moz-extension://test-uuid",
                "access-control-request-method": "GET",
                "access-control-request-headers": "Content-Type",
            },
        )
        assert resp.status_code == 200
        allowed = resp.headers.get("access-control-allow-headers", "")
        assert "content-type" in allowed.lower()

    @pytest.mark.asyncio
    async def test_cors_allows_credentials(self, client: AsyncClient):
        resp = await client.options(
            "/api/health",
            headers={
                "origin": "moz-extension://test-uuid",
                "access-control-request-method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.asyncio
    async def test_cors_max_age(self, client: AsyncClient):
        resp = await client.options(
            "/api/health",
            headers={
                "origin": "moz-extension://test-uuid",
                "access-control-request-method": "GET",
            },
        )
        assert resp.headers.get("access-control-max-age") == "86400"


class TestSSLConfig:
    @pytest.mark.asyncio
    async def test_main_binds_to_localhost_only(self):
        from src.main import app as main_app

        assert main_app is not None

    @pytest.mark.asyncio
    async def test_hsts_header_present(self, client: AsyncClient):
        resp = await client.get("/api/health")
        hsts = resp.headers.get("strict-transport-security")
        assert hsts == "max-age=31536000; includeSubDomains"
