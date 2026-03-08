import json

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from src.api.schemas import RecentBookmark, StatsResponse, TagCount
from src.db.models import Bookmark, Relation, Tag

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
async def get_stats(request: Request) -> StatsResponse:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        total_bookmarks_r = await session.execute(
            select(func.count()).select_from(Bookmark)
        )
        total_bookmarks: int = total_bookmarks_r.scalar_one()

        total_tags_r = await session.execute(select(func.count()).select_from(Tag))
        total_tags: int = total_tags_r.scalar_one()

        total_relations_r = await session.execute(
            select(func.count()).select_from(Relation)
        )
        total_relations: int = total_relations_r.scalar_one()

        accounts_r = await session.execute(select(Bookmark.accounts))
        accounts_col = accounts_r.scalars().all()

        tags_r = await session.execute(select(Tag.id, Tag.name))
        tags = tags_r.all()

        recent_r = await session.execute(
            select(Bookmark.id, Bookmark.name, Bookmark.last_used_at)
            .order_by(Bookmark.last_used_at.desc())
            .limit(10)
        )
        recent_rows = recent_r.all()

        tag_usage: list[TagCount] = []
        for tag_id, tag_name in tags:
            count_r = await session.execute(
                select(func.count())
                .select_from(Bookmark)
                .where(Bookmark.tag_ids.contains(str(tag_id)))
            )
            tag_usage.append(
                TagCount(id=tag_id, name=tag_name, count=count_r.scalar_one())
            )

    total_accounts = 0
    for raw in accounts_col:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, list):
            total_accounts += len(parsed)

    most_used_tags = sorted(tag_usage, key=lambda item: item.count, reverse=True)[:10]

    recently_used = [
        RecentBookmark(id=row[0], name=row[1], lastUsedAt=row[2]) for row in recent_rows
    ]

    return StatsResponse(
        totalBookmarks=total_bookmarks,
        totalTags=total_tags,
        totalRelations=total_relations,
        totalAccounts=total_accounts,
        mostUsedTags=most_used_tags,
        recentlyUsed=recently_used,
    )
