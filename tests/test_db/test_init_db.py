import pytest
from sqlalchemy import text

from src.db.engine import create_engine
from src.db.models import Base
from src.init_db import init_database


class TestInitDatabase:
    @pytest.mark.asyncio
    async def test_creates_all_four_tables(self, tmp_path):
        db_path = tmp_path / "test_init.db"
        await init_database(db_path=str(db_path))

        engine = create_engine(str(db_path))
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            )
            tables = [row[0] for row in result]

        await engine.dispose()
        assert sorted(tables) == ["authentication", "bookmarks", "relations", "tags"]

    @pytest.mark.asyncio
    async def test_wal_mode_enabled(self, tmp_path):
        db_path = tmp_path / "test_wal.db"
        await init_database(db_path=str(db_path))

        engine = create_engine(str(db_path))
        async with engine.connect() as conn:
            result = await conn.execute(text("PRAGMA journal_mode"))
            mode = result.scalar()

        await engine.dispose()
        assert mode == "wal"

    @pytest.mark.asyncio
    async def test_idempotent(self, tmp_path):
        db_path = tmp_path / "test_idempotent.db"
        await init_database(db_path=str(db_path))
        await init_database(db_path=str(db_path))

        engine = create_engine(str(db_path))
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            )
            tables = [row[0] for row in result]

        await engine.dispose()
        assert sorted(tables) == ["authentication", "bookmarks", "relations", "tags"]

    @pytest.mark.asyncio
    async def test_indexes_created(self, tmp_path):
        db_path = tmp_path / "test_indexes.db"
        await init_database(db_path=str(db_path))

        engine = create_engine(str(db_path))
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name"
                )
            )
            indexes = [row[0] for row in result]

        await engine.dispose()
        expected = [
            "idx_bookmarks_last_used",
            "idx_bookmarks_name",
            "idx_bookmarks_pinyin",
            "idx_relations_type",
            "idx_tags_name",
        ]
        assert sorted(indexes) == expected

    @pytest.mark.asyncio
    async def test_check_constraints_present(self, tmp_path):
        db_path = tmp_path / "test_constraints.db"
        await init_database(db_path=str(db_path))

        engine = create_engine(str(db_path))
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT sql FROM sqlite_master WHERE name='relations'")
            )
            schema = result.scalar()

        await engine.dispose()
        assert "ck_relations_type" in schema

    @pytest.mark.asyncio
    async def test_table_metadata_matches(self):
        expected_tables = {"tags", "relations", "bookmarks", "authentication"}
        actual_tables = set(Base.metadata.tables.keys())
        assert actual_tables == expected_tables
