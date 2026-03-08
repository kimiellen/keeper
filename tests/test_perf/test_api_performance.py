import asyncio
import time

from typing import cast

import pytest
from httpx import AsyncClient

from .conftest import ENCRYPTED_PASSWORD


async def _create_bookmarks(client: AsyncClient, count: int = 100) -> None:
    for i in range(count):
        related_ids: list[int] = []
        payload: dict[str, object] = {
            "name": f"Bookmark_{i:03d}",
            "pinyinInitials": f"bm{i:03d}",
            "urls": [{"url": f"https://example{i}.com"}],
            "notes": f"Perf test bookmark {i}",
            "accounts": [
                {
                    "username": f"user{i}",
                    "password": ENCRYPTED_PASSWORD,
                    "relatedIds": related_ids,
                }
            ],
        }
        resp = await client.post("/api/bookmarks", json=payload)
        assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_api_create_100_bookmarks_sequentially(
    authed_client: AsyncClient,
) -> None:
    start = time.perf_counter()
    await _create_bookmarks(authed_client, count=100)
    elapsed = time.perf_counter() - start

    print(f"[API PERF] create 100 bookmarks sequentially: total={elapsed * 1000:.2f}ms")
    assert elapsed < 30.0, f"Sequential create too slow: {elapsed:.3f}s >= 30.0s"


@pytest.mark.asyncio
async def test_api_list_bookmarks_after_100_inserts(authed_client: AsyncClient) -> None:
    await _create_bookmarks(authed_client, count=100)

    durations: list[float] = []
    for _ in range(50):
        start = time.perf_counter()
        resp = await authed_client.get("/api/bookmarks")
        elapsed = time.perf_counter() - start
        durations.append(elapsed)

        assert resp.status_code == 200, resp.text
        body = cast(dict[str, object], resp.json())
        total = body.get("total")
        assert isinstance(total, int)
        assert total == 100

    avg_ms = (sum(durations) / len(durations)) * 1000
    print(f"[API PERF] list bookmarks x50: avg={avg_ms:.2f}ms")
    assert avg_ms < 200.0, f"List API too slow: {avg_ms:.2f}ms >= 200ms"


@pytest.mark.asyncio
async def test_api_search_bookmarks_after_100_inserts(
    authed_client: AsyncClient,
) -> None:
    await _create_bookmarks(authed_client, count=100)

    durations: list[float] = []
    for _ in range(50):
        start = time.perf_counter()
        resp = await authed_client.get(
            "/api/bookmarks", params={"search": "Bookmark_050"}
        )
        elapsed = time.perf_counter() - start
        durations.append(elapsed)

        assert resp.status_code == 200, resp.text
        body = cast(dict[str, object], resp.json())
        total = body.get("total")
        assert isinstance(total, int)
        assert total >= 1

    avg_ms = (sum(durations) / len(durations)) * 1000
    print(f"[API PERF] search bookmarks x50: avg={avg_ms:.2f}ms")
    assert avg_ms < 200.0, f"Search API too slow: {avg_ms:.2f}ms >= 200ms"


@pytest.mark.asyncio
async def test_api_concurrent_reads(authed_client: AsyncClient) -> None:
    await _create_bookmarks(authed_client, count=100)

    start = time.perf_counter()

    async def _one_read() -> tuple[float, int]:
        req_start = time.perf_counter()
        resp = await authed_client.get("/api/bookmarks", params={"limit": 10})
        req_elapsed = time.perf_counter() - req_start
        return req_elapsed, resp.status_code

    results = await asyncio.gather(*[_one_read() for _ in range(50)])
    total_elapsed = time.perf_counter() - start

    per_request_durations = [duration for duration, _ in results]
    status_codes = [status for _, status in results]

    avg_ms = (sum(per_request_durations) / len(per_request_durations)) * 1000
    print(
        f"[API PERF] concurrent reads x50: total={total_elapsed * 1000:.2f}ms avg={avg_ms:.2f}ms"
    )

    assert all(status == 200 for status in status_codes)
    assert total_elapsed < 10.0, (
        f"Concurrent reads too slow: {total_elapsed:.3f}s >= 10.0s"
    )
    assert avg_ms < 200.0, f"Concurrent read avg too slow: {avg_ms:.2f}ms >= 200ms"
