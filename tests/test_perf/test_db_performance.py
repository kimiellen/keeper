import json
import time
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Bookmark

ENCRYPTED_PW = "v1.AES_GCM.dGVzdG5vbmNl.Y2lwaGVydGV4dA.dGFn"


async def _bulk_insert_bookmarks(
    session_factory: async_sessionmaker[AsyncSession], count: int = 10_000
) -> float:
    now = datetime.now(timezone.utc).isoformat()
    bookmarks_data: list[dict[str, str]] = []
    for i in range(count):
        bookmarks_data.append(
            {
                "id": str(uuid.uuid4()),
                "name": f"Bookmark_{i:05d}",
                "pinyin_initials": f"bm{i:05d}",
                "tag_ids": json.dumps([i % 10 + 1]),
                "urls": json.dumps(
                    [{"url": f"https://example{i}.com", "lastUsed": now}]
                ),
                "notes": f"Notes for bookmark {i}",
                "accounts": json.dumps(
                    [
                        {
                            "id": 1,
                            "username": f"user{i}",
                            "password": ENCRYPTED_PW,
                            "relatedIds": [],
                            "createdAt": now,
                            "lastUsed": now,
                        }
                    ]
                ),
                "created_at": now,
                "updated_at": now,
                "last_used_at": now,
            }
        )

    async with session_factory() as session:
        start = time.perf_counter()
        _ = await session.execute(insert(Bookmark), bookmarks_data)
        await session.commit()
        elapsed = time.perf_counter() - start
    return elapsed


@pytest.mark.asyncio
async def test_bulk_insert_10000_bookmarks(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    elapsed = await _bulk_insert_bookmarks(session_factory)

    print(f"[DB PERF] bulk insert 10000 bookmarks: total={elapsed * 1000:.2f}ms")
    assert elapsed < 30.0, f"Bulk insert too slow: {elapsed:.3f}s >= 30.0s"


@pytest.mark.asyncio
async def test_paginated_query_with_10000_bookmarks(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _ = await _bulk_insert_bookmarks(session_factory)

    offsets = [0, 5000, 9950]
    threshold_seconds = 0.1

    async with session_factory() as session:
        for offset in offsets:
            durations: list[float] = []
            for _ in range(10):
                start = time.perf_counter()
                result = await session.execute(
                    select(Bookmark).limit(50).offset(offset)
                )
                rows = result.scalars().all()
                elapsed = time.perf_counter() - start
                durations.append(elapsed)
                assert len(rows) == 50

            avg = sum(durations) / len(durations)
            print(
                f"[DB PERF] paginated query limit=50 offset={offset}: avg={avg * 1000:.2f}ms"
            )
            assert avg < threshold_seconds, (
                f"Paginated query too slow at offset {offset}: {avg * 1000:.2f}ms >= 100ms"
            )


@pytest.mark.asyncio
async def test_search_query_with_10000_bookmarks(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _ = await _bulk_insert_bookmarks(session_factory)

    searches = ["Bookmark_050", "bm050", "9999"]
    threshold_seconds = 0.1

    async with session_factory() as session:
        for search in searches:
            durations: list[float] = []
            for _ in range(10):
                start = time.perf_counter()
                result = await session.execute(
                    select(Bookmark).where(
                        or_(
                            Bookmark.name.contains(search),
                            Bookmark.pinyin_initials.contains(search),
                        )
                    )
                )
                _ = result.scalars().all()
                durations.append(time.perf_counter() - start)

            avg = sum(durations) / len(durations)
            print(f"[DB PERF] search query search={search!r}: avg={avg * 1000:.2f}ms")
            assert avg < threshold_seconds, (
                f"Search query too slow for {search!r}: {avg * 1000:.2f}ms >= 100ms"
            )


@pytest.mark.asyncio
async def test_tag_filter_with_10000_bookmarks(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _ = await _bulk_insert_bookmarks(session_factory)

    async with session_factory() as session:
        result = await session.execute(select(Bookmark))
        bookmarks = result.scalars().all()

    target_tag_id = 5
    durations: list[float] = []
    filtered_count = 0
    for _ in range(10):
        start = time.perf_counter()
        filtered = [
            bookmark
            for bookmark in bookmarks
            if target_tag_id in json.loads(bookmark.tag_ids)
        ]
        durations.append(time.perf_counter() - start)
        filtered_count = len(filtered)

    avg = sum(durations) / len(durations)
    print(
        f"[DB PERF] python tag filter over 10000 records: avg={avg * 1000:.2f}ms matched={filtered_count}"
    )

    assert filtered_count > 0
    assert avg < 0.2, f"Tag filter too slow: {avg * 1000:.2f}ms >= 200ms"
