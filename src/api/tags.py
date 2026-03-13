import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.api.schemas import TagCreate, TagListResponse, TagResponse, TagUpdate
from src.db.models import Bookmark, Tag

router = APIRouter(prefix="/api/tags", tags=["tags"])

# 10 种亮色系标签颜色，按创建顺序循环分配
TAG_COLORS: list[str] = [
    "#3B82F6",  # 蓝
    "#10B981",  # 翠绿
    "#F59E0B",  # 琥珀
    "#EF4444",  # 红
    "#8B5CF6",  # 紫
    "#EC4899",  # 粉
    "#06B6D4",  # 青
    "#F97316",  # 橙
    "#14B8A6",  # 蓝绿
    "#6366F1",  # 靛蓝
]


async def _next_tag_color(session) -> str:
    """根据当前标签总数，返回下一个循环颜色。"""
    result = await session.execute(select(func.count()).select_from(Tag))
    count: int = result.scalar_one()
    return TAG_COLORS[count % len(TAG_COLORS)]


def _tag_to_response(tag: Tag) -> TagResponse:
    return TagResponse(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        icon=tag.icon,
        createdAt=tag.created_at,
        updatedAt=tag.updated_at,
    )


@router.get("", response_model=TagListResponse)
async def list_tags(
    request: Request,
    sort: str = Query(default="name"),
) -> TagListResponse:
    session_factory = request.app.state.session_factory

    sort_desc = sort.startswith("-")
    sort_key = sort[1:] if sort_desc else sort
    sort_map = {
        "name": Tag.name,
        "color": Tag.color,
        "createdAt": Tag.created_at,
        "updatedAt": Tag.updated_at,
    }
    sort_col = sort_map.get(sort_key, Tag.name)
    order_col = sort_col.desc() if sort_desc else sort_col.asc()

    async with session_factory() as session:
        result = await session.execute(select(Tag).order_by(order_col))
        tags = result.scalars().all()

    return TagListResponse(
        data=[_tag_to_response(tag) for tag in tags], total=len(tags)
    )


@router.get("/{tag_id}", response_model=None)
async def get_tag(tag_id: int, request: Request) -> TagResponse | Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(select(Tag).where(Tag.id == tag_id))
        tag = result.scalar_one_or_none()

    if tag is None:
        return Response(
            content='{"type":"https://keeper.local/errors/tag-not-found","title":"标签不存在","status":404,"detail":"指定标签不存在"}',
            status_code=404,
            media_type="application/json",
        )

    return _tag_to_response(tag)


@router.post("", status_code=201, response_model=None)
async def create_tag(body: TagCreate, request: Request) -> TagResponse | Response:
    session_factory = request.app.state.session_factory

    now = datetime.now(timezone.utc).isoformat()

    async with session_factory() as session:
        color = body.color if body.color is not None else await _next_tag_color(session)
        tag = Tag(name=body.name, color=color, created_at=now, updated_at=now)
        if body.icon is not None:
            tag.icon = body.icon

        session.add(tag)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return Response(
                content='{"type":"https://keeper.local/errors/tag-name-conflict","title":"标签冲突","status":409,"detail":"标签名称已存在"}',
                status_code=409,
                media_type="application/json",
            )
        await session.refresh(tag)

    return _tag_to_response(tag)


@router.put("/{tag_id}", response_model=None)
async def update_tag(
    tag_id: int, body: TagUpdate, request: Request
) -> TagResponse | Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(select(Tag).where(Tag.id == tag_id))
        tag = result.scalar_one_or_none()
        if tag is None:
            return Response(
                content='{"type":"https://keeper.local/errors/tag-not-found","title":"标签不存在","status":404,"detail":"指定标签不存在"}',
                status_code=404,
                media_type="application/json",
            )

        tag.name = body.name
        if body.color is not None:
            tag.color = body.color
        if body.icon is not None:
            tag.icon = body.icon
        tag.updated_at = datetime.now(timezone.utc).isoformat()

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return Response(
                content='{"type":"https://keeper.local/errors/tag-name-conflict","title":"标签冲突","status":409,"detail":"标签名称已存在"}',
                status_code=409,
                media_type="application/json",
            )
        await session.refresh(tag)

    return _tag_to_response(tag)


@router.delete("/{tag_id}", status_code=204, response_model=None)
async def delete_tag(
    tag_id: int,
    request: Request,
    cascade: bool = Query(default=False),
) -> Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        tag_result = await session.execute(select(Tag).where(Tag.id == tag_id))
        tag = tag_result.scalar_one_or_none()
        if tag is None:
            return Response(
                content='{"type":"https://keeper.local/errors/tag-not-found","title":"标签不存在","status":404,"detail":"指定标签不存在"}',
                status_code=404,
                media_type="application/json",
            )

        ref_count_r = await session.execute(
            select(func.count())
            .select_from(Bookmark)
            .where(Bookmark.tag_ids.contains(str(tag_id)))
        )
        referenced: int = ref_count_r.scalar_one()

        if not cascade and referenced > 0:
            return Response(
                content=(
                    "{"
                    '"type":"https://keeper.local/errors/tag-in-use",'
                    '"title":"标签被引用",'
                    '"status":409,'
                    f'"detail":"有 {referenced} 条书签仍在使用该标签"'
                    "}"
                ),
                status_code=409,
                media_type="application/json",
            )

        if cascade:
            affected_r = await session.execute(
                select(Bookmark).where(Bookmark.tag_ids.contains(str(tag_id)))
            )
            affected_bookmarks = affected_r.scalars().all()
            for bookmark in affected_bookmarks:
                try:
                    tag_ids_list = json.loads(bookmark.tag_ids)
                except (TypeError, ValueError):
                    tag_ids_list = []
                if isinstance(tag_ids_list, list) and tag_id in tag_ids_list:
                    bookmark.tag_ids = json.dumps(
                        [item for item in tag_ids_list if item != tag_id]
                    )

        await session.delete(tag)
        await session.commit()

    return Response(status_code=204)
