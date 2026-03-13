import json

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from src.db.engine import create_engine, create_session_factory
from src.db.models import Authentication, Base, Bookmark, Relation, Tag

NOW = "2026-03-06T10:00:00Z"


@pytest_asyncio.fixture
async def db_session():
    engine = create_engine(":memory:")
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()


class TestTagModel:
    @pytest.mark.asyncio
    async def test_create_tag(self, db_session):
        tag = Tag(name="Work", created_at=NOW, updated_at=NOW)
        db_session.add(tag)
        await db_session.commit()

        result = await db_session.execute(select(Tag).where(Tag.name == "Work"))
        fetched = result.scalar_one()
        assert fetched.name == "Work"
        assert fetched.id is not None

    @pytest.mark.asyncio
    async def test_color_default(self, db_session):
        tag = Tag(name="Default Color", created_at=NOW, updated_at=NOW)
        db_session.add(tag)
        await db_session.commit()
        await db_session.refresh(tag)
        assert tag.color == "#3B82F6"

    @pytest.mark.asyncio
    async def test_icon_default(self, db_session):
        tag = Tag(name="No Icon", created_at=NOW, updated_at=NOW)
        db_session.add(tag)
        await db_session.commit()
        await db_session.refresh(tag)
        assert tag.icon == ""

    @pytest.mark.asyncio
    async def test_custom_color(self, db_session):
        tag = Tag(name="Custom", color="#FF0000", created_at=NOW, updated_at=NOW)
        db_session.add(tag)
        await db_session.commit()
        assert tag.color == "#FF0000"

    @pytest.mark.asyncio
    async def test_unique_name_constraint(self, db_session):
        db_session.add(Tag(name="Duplicate", created_at=NOW, updated_at=NOW))
        await db_session.commit()

        db_session.add(Tag(name="Duplicate", created_at=NOW, updated_at=NOW))
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_name_not_null(self, db_session):
        db_session.add(Tag(name=None, created_at=NOW, updated_at=NOW))
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_autoincrement_id(self, db_session):
        t1 = Tag(name="First", created_at=NOW, updated_at=NOW)
        t2 = Tag(name="Second", created_at=NOW, updated_at=NOW)
        db_session.add_all([t1, t2])
        await db_session.commit()
        assert t2.id == t1.id + 1

    @pytest.mark.asyncio
    async def test_repr(self, db_session):
        tag = Tag(name="Test", created_at=NOW, updated_at=NOW)
        db_session.add(tag)
        await db_session.commit()
        assert "Test" in repr(tag)


class TestRelationModel:
    @pytest.mark.asyncio
    async def test_create_relation(self, db_session):
        rel = Relation(
            name="Personal Email", type="email", created_at=NOW, updated_at=NOW
        )
        db_session.add(rel)
        await db_session.commit()

        result = await db_session.execute(select(Relation))
        fetched = result.scalar_one()
        assert fetched.name == "Personal Email"
        assert fetched.type == "email"
        assert fetched.id is not None

    @pytest.mark.asyncio
    async def test_unique_name_constraint(self, db_session):
        db_session.add(
            Relation(name="Dup", type="phone", created_at=NOW, updated_at=NOW)
        )
        await db_session.commit()

        db_session.add(
            Relation(name="Dup", type="email", created_at=NOW, updated_at=NOW)
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_valid_types(self, db_session):
        for i, t in enumerate(("phone", "email", "idcard", "other")):
            db_session.add(
                Relation(name=f"rel_{t}", type=t, created_at=NOW, updated_at=NOW)
            )
        await db_session.commit()

        result = await db_session.execute(select(Relation))
        assert len(result.scalars().all()) == 4

    @pytest.mark.asyncio
    async def test_invalid_type_check_constraint(self, db_session):
        db_session.add(
            Relation(name="bad", type="invalid", created_at=NOW, updated_at=NOW)
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_autoincrement_id(self, db_session):
        r1 = Relation(name="First", type="phone", created_at=NOW, updated_at=NOW)
        r2 = Relation(name="Second", type="email", created_at=NOW, updated_at=NOW)
        db_session.add_all([r1, r2])
        await db_session.commit()
        assert r2.id == r1.id + 1

    @pytest.mark.asyncio
    async def test_repr(self, db_session):
        rel = Relation(name="Work Phone", type="phone", created_at=NOW, updated_at=NOW)
        db_session.add(rel)
        await db_session.commit()
        r = repr(rel)
        assert "Work Phone" in r
        assert "phone" in r


class TestBookmarkModel:
    @pytest.mark.asyncio
    async def test_create_bookmark(self, db_session):
        urls = json.dumps([{"url": "https://example.com", "lastUsed": NOW}])
        bm = Bookmark(
            id="uuid-001",
            name="Example",
            pinyin_initials="ex",
            urls=urls,
            created_at=NOW,
            updated_at=NOW,
            last_used_at=NOW,
        )
        db_session.add(bm)
        await db_session.commit()

        result = await db_session.execute(
            select(Bookmark).where(Bookmark.id == "uuid-001")
        )
        fetched = result.scalar_one()
        assert fetched.name == "Example"
        assert json.loads(fetched.urls)[0]["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_tag_ids_default(self, db_session):
        bm = Bookmark(
            id="uuid-002",
            name="NoTags",
            pinyin_initials="nt",
            urls="[]",
            created_at=NOW,
            updated_at=NOW,
            last_used_at=NOW,
        )
        db_session.add(bm)
        await db_session.commit()
        await db_session.refresh(bm)
        assert bm.tag_ids == "[]"

    @pytest.mark.asyncio
    async def test_accounts_default(self, db_session):
        bm = Bookmark(
            id="uuid-003",
            name="NoAccounts",
            pinyin_initials="na",
            urls="[]",
            created_at=NOW,
            updated_at=NOW,
            last_used_at=NOW,
        )
        db_session.add(bm)
        await db_session.commit()
        await db_session.refresh(bm)
        assert bm.accounts == "[]"

    @pytest.mark.asyncio
    async def test_notes_default(self, db_session):
        bm = Bookmark(
            id="uuid-004",
            name="NoNotes",
            pinyin_initials="nn",
            urls="[]",
            created_at=NOW,
            updated_at=NOW,
            last_used_at=NOW,
        )
        db_session.add(bm)
        await db_session.commit()
        await db_session.refresh(bm)
        assert bm.notes == ""

    @pytest.mark.asyncio
    async def test_text_primary_key(self, db_session):
        bm = Bookmark(
            id="550e8400-e29b-41d4-a716-446655440000",
            name="UUID PK",
            pinyin_initials="up",
            urls="[]",
            created_at=NOW,
            updated_at=NOW,
            last_used_at=NOW,
        )
        db_session.add(bm)
        await db_session.commit()
        assert bm.id == "550e8400-e29b-41d4-a716-446655440000"

    @pytest.mark.asyncio
    async def test_duplicate_id_fails(self, db_session):
        bm1 = Bookmark(
            id="uuid-dup",
            name="First",
            pinyin_initials="f",
            urls="[]",
            created_at=NOW,
            updated_at=NOW,
            last_used_at=NOW,
        )
        db_session.add(bm1)
        await db_session.commit()

        bm2 = Bookmark(
            id="uuid-dup",
            name="Second",
            pinyin_initials="s",
            urls="[]",
            created_at=NOW,
            updated_at=NOW,
            last_used_at=NOW,
        )
        db_session.add(bm2)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_json_tag_ids_storage(self, db_session):
        tag_ids = json.dumps([1, 3, 5])
        bm = Bookmark(
            id="uuid-json",
            name="Tagged",
            pinyin_initials="tg",
            tag_ids=tag_ids,
            urls="[]",
            created_at=NOW,
            updated_at=NOW,
            last_used_at=NOW,
        )
        db_session.add(bm)
        await db_session.commit()

        result = await db_session.execute(
            select(Bookmark).where(Bookmark.id == "uuid-json")
        )
        fetched = result.scalar_one()
        assert json.loads(fetched.tag_ids) == [1, 3, 5]

    @pytest.mark.asyncio
    async def test_json_accounts_storage(self, db_session):
        accounts = json.dumps(
            [
                {
                    "id": 1,
                    "username": "user1",
                    "password": "v1.AES_GCM.nonce.ct.tag",
                    "relatedIds": [1],
                    "createdAt": NOW,
                    "lastUsed": NOW,
                }
            ]
        )
        bm = Bookmark(
            id="uuid-acct",
            name="WithAccounts",
            pinyin_initials="wa",
            urls="[]",
            accounts=accounts,
            created_at=NOW,
            updated_at=NOW,
            last_used_at=NOW,
        )
        db_session.add(bm)
        await db_session.commit()

        result = await db_session.execute(
            select(Bookmark).where(Bookmark.id == "uuid-acct")
        )
        fetched = result.scalar_one()
        parsed = json.loads(fetched.accounts)
        assert parsed[0]["username"] == "user1"
        assert parsed[0]["password"] == "v1.AES_GCM.nonce.ct.tag"

    @pytest.mark.asyncio
    async def test_repr(self, db_session):
        bm = Bookmark(
            id="uuid-repr",
            name="ReprTest",
            pinyin_initials="rt",
            urls="[]",
            created_at=NOW,
            updated_at=NOW,
            last_used_at=NOW,
        )
        db_session.add(bm)
        await db_session.commit()
        assert "ReprTest" in repr(bm)


class TestAuthenticationModel:
    @pytest.mark.asyncio
    async def test_create_authentication(self, db_session):
        auth = Authentication(
            id=1,
            email="user@example.com",
            password_hash="$argon2id$hash",
            created_at=NOW,
            last_login=NOW,
        )
        db_session.add(auth)
        await db_session.commit()

        result = await db_session.execute(select(Authentication))
        fetched = result.scalar_one()
        assert fetched.email == "user@example.com"
        assert fetched.id == 1

    @pytest.mark.asyncio
    async def test_single_user_constraint_id_2(self, db_session):
        auth = Authentication(
            id=2,
            email="bad@example.com",
            password_hash="hash",
            created_at=NOW,
            last_login=NOW,
        )
        db_session.add(auth)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_single_user_constraint_id_0(self, db_session):
        auth = Authentication(
            id=0,
            email="zero@example.com",
            password_hash="hash",
            created_at=NOW,
            last_login=NOW,
        )
        db_session.add(auth)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_email_unique_constraint(self, db_session):
        auth1 = Authentication(
            id=1,
            email="dup@example.com",
            password_hash="hash",
            created_at=NOW,
            last_login=NOW,
        )
        db_session.add(auth1)
        await db_session.commit()

        await db_session.rollback()
        auth2 = Authentication(
            id=1,
            email="dup@example.com",
            password_hash="hash2",
            created_at=NOW,
            last_login=NOW,
        )
        db_session.add(auth2)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_repr(self, db_session):
        auth = Authentication(
            id=1,
            email="repr@example.com",
            password_hash="h",
            created_at=NOW,
            last_login=NOW,
        )
        db_session.add(auth)
        await db_session.commit()
        r = repr(auth)
        assert "repr@example.com" in r
        assert "1" in r
