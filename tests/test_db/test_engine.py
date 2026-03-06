import pytest

from src.db.engine import create_engine, get_database_url, DEFAULT_DB_PATH


class TestGetDatabaseUrl:
    def test_memory_database(self):
        assert get_database_url(":memory:") == "sqlite+aiosqlite://"

    def test_explicit_path(self, tmp_path):
        db_file = tmp_path / "test.db"
        url = get_database_url(db_file)
        assert url == f"sqlite+aiosqlite:///{db_file}"

    def test_default_path(self, monkeypatch):
        monkeypatch.delenv("KEEPER_DB_PATH", raising=False)
        url = get_database_url()
        assert url == f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("KEEPER_DB_PATH", "/tmp/custom.db")
        url = get_database_url()
        assert url == "sqlite+aiosqlite:////tmp/custom.db"

    def test_string_path(self):
        url = get_database_url("/some/path/keeper.db")
        assert url == "sqlite+aiosqlite:////some/path/keeper.db"


class TestCreateEngine:
    def test_returns_async_engine(self):
        engine = create_engine(":memory:")
        assert engine is not None
        assert "aiosqlite" in str(engine.url)

    def test_echo_mode(self):
        engine = create_engine(":memory:", echo=True)
        assert engine.echo is True

    def test_no_echo_by_default(self):
        engine = create_engine(":memory:")
        assert engine.echo is False


class TestCreateSessionFactory:
    def test_returns_sessionmaker(self):
        from src.db.engine import create_session_factory

        engine = create_engine(":memory:")
        factory = create_session_factory(engine)
        assert factory is not None

    @pytest.mark.asyncio
    async def test_session_produces_async_session(self):
        from sqlalchemy.ext.asyncio import AsyncSession

        from src.db.engine import create_session_factory

        engine = create_engine(":memory:")
        factory = create_session_factory(engine)
        async with factory() as session:
            assert isinstance(session, AsyncSession)
        await engine.dispose()
