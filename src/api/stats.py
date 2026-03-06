import json

from fastapi import APIRouter, Request
from sqlalchemy import select

from src.api.schemas import RecentBookmark, StatsResponse, TagCount
from src.db.models import Bookmark, Relation, Tag

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
async def get_stats(request: Request) -> StatsResponse:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        tags_result = await session.execute(select(Tag))
        tags = tags_result.scalars().all()

        relations_result = await session.execute(select(Relation))
        relations = relations_result.scalars().all()

        bookmarks_result = await session.execute(select(Bookmark))
        bookmarks = bookmarks_result.scalars().all()

    total_accounts = 0
    for bookmark in bookmarks:
        try:
            accounts = json.loads(bookmark.accounts)
        except (TypeError, ValueError):
            accounts = []
        if isinstance(accounts, list):
            total_accounts += len(accounts)

    tag_usage: list[TagCount] = []
    for tag in tags:
        count = 0
        for bookmark in bookmarks:
            try:
                tag_ids = json.loads(bookmark.tag_ids)
            except (TypeError, ValueError):
                tag_ids = []
            if isinstance(tag_ids, list) and tag.id in tag_ids:
                count += 1
        tag_usage.append(TagCount(id=tag.id, name=tag.name, count=count))

    most_used_tags = sorted(tag_usage, key=lambda item: item.count, reverse=True)[:10]

    recently_used = [
        RecentBookmark(id=bookmark.id, name=bookmark.name, lastUsedAt=bookmark.last_used_at)
        for bookmark in sorted(bookmarks, key=lambda item: item.last_used_at, reverse=True)[:10]
    ]

    return StatsResponse(
        totalBookmarks=len(bookmarks),
        totalTags=len(tags),
        totalRelations=len(relations),
        totalAccounts=total_accounts,
        mostUsedTags=most_used_tags,
        recentlyUsed=recently_used,
    )
