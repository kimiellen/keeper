import json
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, or_, select
from xpinyin import Pinyin

_pinyin = Pinyin()


def _compute_initials(name: str) -> str:
    """Compute search initials for a bookmark name.

    Chinese characters use pinyin first letter; English segments use
    CamelCase / word-boundary uppercase letters as initials.
    Examples: "GitHub" -> "gh", "百度" -> "bd", "GitHub工作" -> "ghgz".
    """
    result: list[str] = []
    i = 0
    while i < len(name):
        ch = name[i]
        if "\u4e00" <= ch <= "\u9fff":
            result.append(_pinyin.get_initials(ch, "").lower())
            i += 1
        elif ch.isascii() and ch.isalpha():
            j = i
            while j < len(name) and name[j].isascii() and name[j].isalpha():
                j += 1
            segment = name[i:j]
            uppers = [c for c in segment if c.isupper()]
            if uppers:
                result.append("".join(uppers).lower())
            else:
                result.append(segment[0].lower())
            i = j
        else:
            i += 1
    return "".join(result)[:50]


from src.api.schemas import (
    AccountCreate,
    AccountResponse,
    BookmarkCreate,
    BookmarkListResponse,
    BookmarkPatch,
    BookmarkResponse,
    BookmarkUpdate,
    BookmarkUseRequest,
    BookmarkUseResponse,
    SearchHighlight,
    UrlItem,
)
from src.db.models import Bookmark, Relation, Tag

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])


def _safe_json_load_list(value: str) -> list[object]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, list):
        return parsed
    return []


def _negate_timestamp(ts: str) -> str:
    """Invert ISO 8601 timestamp string for descending sort within ascending tuple."""
    return "".join(chr(0x10FFFF - ord(c)) for c in ts)


def _search_rank(bm: Bookmark, search: str) -> int:
    """Return match priority: 0=exact, 1=prefix, 2=contains. Lower is better."""
    s = search.lower()
    name_lower = bm.name.lower()
    if name_lower == s:
        return 0
    if (
        name_lower.startswith(s)
        or bm.pinyin_full.startswith(s)
        or bm.pinyin_initials.startswith(s)
    ):
        return 1
    return 2


def _compute_highlights(name: str, search: str) -> list[SearchHighlight]:
    highlights: list[SearchHighlight] = []
    lower_name = name.lower()
    lower_search = search.lower()
    positions: list[list[int]] = []
    start = 0
    while True:
        idx = lower_name.find(lower_search, start)
        if idx == -1:
            break
        positions.append([idx, len(lower_search)])
        start = idx + 1
    if positions:
        highlights.append(SearchHighlight(field="name", positions=positions))
    return highlights


def _bookmark_to_response(bm: Bookmark, search: str | None = None) -> BookmarkResponse:
    tag_ids = [
        item for item in _safe_json_load_list(bm.tag_ids) if isinstance(item, int)
    ]

    urls_raw = _safe_json_load_list(bm.urls)
    urls: list[UrlItem] = []
    for item in urls_raw:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str):
            continue
        last_used = item.get("lastUsed")
        urls.append(
            UrlItem(url=url, lastUsed=last_used if isinstance(last_used, str) else None)
        )

    accounts_raw = _safe_json_load_list(bm.accounts)
    accounts: list[AccountResponse] = []
    for item in accounts_raw:
        if not isinstance(item, dict):
            continue
        related_ids_raw = item.get("relatedIds", [])
        related_ids = (
            [rel for rel in related_ids_raw if isinstance(rel, int)]
            if isinstance(related_ids_raw, list)
            else []
        )
        account_id = item.get("id")
        username = item.get("username")
        password = item.get("password")
        created_at = item.get("createdAt")
        last_used = item.get("lastUsed")
        if not isinstance(account_id, int):
            continue
        if not isinstance(username, str):
            continue
        if not isinstance(password, str):
            continue
        if not isinstance(created_at, str):
            continue
        if not isinstance(last_used, str):
            continue
        accounts.append(
            AccountResponse(
                id=account_id,
                username=username,
                password=password,
                relatedIds=related_ids,
                createdAt=created_at,
                lastUsed=last_used,
            )
        )

    highlights = _compute_highlights(bm.name, search) if search else None

    return BookmarkResponse(
        id=bm.id,
        name=bm.name,
        pinyinInitials=bm.pinyin_initials,
        tagIds=tag_ids,
        urls=urls,
        notes=bm.notes,
        accounts=accounts,
        createdAt=bm.created_at,
        updatedAt=bm.updated_at,
        lastUsedAt=bm.last_used_at,
        highlights=highlights if highlights else None,
    )


async def _validate_tag_ids(session, tag_ids: list[int]) -> bool:
    if not tag_ids:
        return True
    result = await session.execute(select(Tag.id).where(Tag.id.in_(set(tag_ids))))
    existing_ids = {item for item in result.scalars().all()}
    return all(tag_id in existing_ids for tag_id in tag_ids)


async def _validate_related_ids(session, accounts: list[AccountCreate]) -> bool:
    related_ids: list[int] = []
    for account in accounts:
        if account.relatedIds:
            related_ids.extend(account.relatedIds)
    if not related_ids:
        return True

    result = await session.execute(
        select(Relation.id).where(Relation.id.in_(set(related_ids)))
    )
    existing_ids = {item for item in result.scalars().all()}
    return all(related_id in existing_ids for related_id in related_ids)


def _build_accounts(accounts: list[AccountCreate], now: str) -> list[dict[str, object]]:
    built: list[dict[str, object]] = []
    for index, account in enumerate(accounts, start=1):
        built.append(
            {
                "id": index,
                "username": account.username,
                "password": account.password,
                "relatedIds": account.relatedIds or [],
                "createdAt": now,
                "lastUsed": now,
            }
        )
    return built


@router.get("", response_model=None)
async def list_bookmarks(
    request: Request,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="-lastUsedAt"),
    tagIds: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> BookmarkListResponse | Response:
    session_factory = request.app.state.session_factory

    sort_desc = sort.startswith("-")
    sort_key = sort[1:] if sort_desc else sort
    sort_map = {
        "name": Bookmark.name,
        "pinyinInitials": Bookmark.pinyin_initials,
        "createdAt": Bookmark.created_at,
        "updatedAt": Bookmark.updated_at,
        "lastUsedAt": Bookmark.last_used_at,
    }
    sort_col = sort_map.get(sort_key, Bookmark.last_used_at)
    order_col = sort_col.desc() if sort_desc else sort_col.asc()

    filter_tag_ids: list[int] = []
    if tagIds:
        parts = [part.strip() for part in tagIds.split(",") if part.strip()]
        try:
            filter_tag_ids = [int(part) for part in parts]
        except ValueError:
            return Response(
                content='{"type":"https://keeper.local/errors/invalid-tag-ids","title":"参数错误","status":422,"detail":"tagIds 必须是逗号分隔的整数"}',
                status_code=422,
                media_type="application/json",
            )

    async with session_factory() as session:
        base_filter = []
        search_lower = search.lower() if search else None
        if search_lower:
            base_filter.append(
                or_(
                    Bookmark.name.contains(search),
                    Bookmark.pinyin_initials.contains(search_lower),
                    Bookmark.pinyin_full.contains(search_lower),
                )
            )

        if filter_tag_ids:
            tag_conditions = []
            for tid in filter_tag_ids:
                tag_conditions.append(Bookmark.tag_ids.contains(str(tid)))
            base_filter.append(or_(*tag_conditions))

        count_query = select(func.count()).select_from(Bookmark)
        for condition in base_filter:
            count_query = count_query.where(condition)

        total_result = await session.execute(count_query)
        total = total_result.scalar_one()

        if search_lower:
            data_query = select(Bookmark)
            for condition in base_filter:
                data_query = data_query.where(condition)
            result = await session.execute(data_query)
            all_matches = list(result.scalars().all())
            all_matches.sort(
                key=lambda bm: (
                    _search_rank(bm, search_lower),
                    _negate_timestamp(bm.last_used_at),
                ),
            )
            bookmarks = all_matches[offset : offset + limit]
        else:
            data_query = select(Bookmark).order_by(order_col)
            for condition in base_filter:
                data_query = data_query.where(condition)
            data_query = data_query.limit(limit).offset(offset)
            result = await session.execute(data_query)
            bookmarks = list(result.scalars().all())

    data = [_bookmark_to_response(bookmark, search) for bookmark in bookmarks]

    response.headers["X-Total-Count"] = str(total)
    if offset + limit < total:
        next_offset = offset + limit
        next_params: dict[str, str] = {
            "limit": str(limit),
            "offset": str(next_offset),
            "sort": sort,
        }
        if tagIds:
            next_params["tagIds"] = tagIds
        if search:
            next_params["search"] = search
        response.headers["Link"] = (
            f'</api/bookmarks?{urlencode(next_params)}>; rel="next"'
        )

    return BookmarkListResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/{bookmark_id}", response_model=None)
async def get_bookmark(
    bookmark_id: str, request: Request
) -> BookmarkResponse | Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(
            select(Bookmark).where(Bookmark.id == bookmark_id)
        )
        bookmark = result.scalar_one_or_none()

    if bookmark is None:
        return Response(
            content='{"type":"https://keeper.local/errors/bookmark-not-found","title":"书签不存在","status":404,"detail":"指定书签不存在"}',
            status_code=404,
            media_type="application/json",
        )

    return _bookmark_to_response(bookmark)


@router.post("", status_code=201, response_model=None)
async def create_bookmark(
    body: BookmarkCreate,
    request: Request,
    response: Response,
) -> BookmarkResponse | Response:
    session_factory = request.app.state.session_factory

    now = datetime.now(timezone.utc).isoformat()
    pinyin_initials = body.pinyinInitials
    if pinyin_initials is None:
        pinyin_initials = _compute_initials(body.name)

    tag_ids = body.tagIds or []
    urls = [item.model_dump() for item in (body.urls or [])]
    accounts = body.accounts or []

    async with session_factory() as session:
        if not await _validate_tag_ids(session, tag_ids):
            return Response(
                content='{"type":"https://keeper.local/errors/tag-not-found","title":"标签不存在","status":422,"detail":"包含不存在的标签 ID"}',
                status_code=422,
                media_type="application/json",
            )

        if not await _validate_related_ids(session, accounts):
            return Response(
                content='{"type":"https://keeper.local/errors/relation-not-found","title":"关联不存在","status":422,"detail":"账户中包含不存在的关联 ID"}',
                status_code=422,
                media_type="application/json",
            )

        pinyin_full = _pinyin.get_pinyin(body.name, "").lower()

        bookmark = Bookmark(
            id=str(uuid.uuid4()),
            name=body.name,
            pinyin_initials=pinyin_initials,
            pinyin_full=pinyin_full,
            tag_ids=json.dumps(tag_ids),
            urls=json.dumps(urls),
            notes=body.notes or "",
            accounts=json.dumps(_build_accounts(accounts, now)),
            created_at=now,
            updated_at=now,
            last_used_at=now,
        )

        session.add(bookmark)
        await session.commit()
        await session.refresh(bookmark)

    response.headers["Location"] = f"/api/bookmarks/{bookmark.id}"
    return _bookmark_to_response(bookmark)


@router.put("/{bookmark_id}", response_model=None)
async def update_bookmark(
    bookmark_id: str,
    body: BookmarkUpdate,
    request: Request,
) -> BookmarkResponse | Response:
    session_factory = request.app.state.session_factory

    now = datetime.now(timezone.utc).isoformat()
    pinyin_initials = body.pinyinInitials
    if pinyin_initials is None:
        pinyin_initials = _compute_initials(body.name)

    tag_ids = body.tagIds or []
    urls = [item.model_dump() for item in (body.urls or [])]
    accounts = body.accounts or []

    async with session_factory() as session:
        result = await session.execute(
            select(Bookmark).where(Bookmark.id == bookmark_id)
        )
        bookmark = result.scalar_one_or_none()
        if bookmark is None:
            return Response(
                content='{"type":"https://keeper.local/errors/bookmark-not-found","title":"书签不存在","status":404,"detail":"指定书签不存在"}',
                status_code=404,
                media_type="application/json",
            )

        if not await _validate_tag_ids(session, tag_ids):
            return Response(
                content='{"type":"https://keeper.local/errors/tag-not-found","title":"标签不存在","status":422,"detail":"包含不存在的标签 ID"}',
                status_code=422,
                media_type="application/json",
            )

        if not await _validate_related_ids(session, accounts):
            return Response(
                content='{"type":"https://keeper.local/errors/relation-not-found","title":"关联不存在","status":422,"detail":"账户中包含不存在的关联 ID"}',
                status_code=422,
                media_type="application/json",
            )

        bookmark.name = body.name
        bookmark.pinyin_initials = pinyin_initials
        bookmark.pinyin_full = _pinyin.get_pinyin(body.name, "").lower()
        bookmark.tag_ids = json.dumps(tag_ids)
        bookmark.urls = json.dumps(urls)
        bookmark.notes = body.notes or ""
        bookmark.accounts = json.dumps(_build_accounts(accounts, now))
        bookmark.updated_at = now

        await session.commit()
        await session.refresh(bookmark)

    return _bookmark_to_response(bookmark)


@router.patch("/{bookmark_id}", response_model=None)
async def patch_bookmark(
    bookmark_id: str,
    body: BookmarkPatch,
    request: Request,
) -> BookmarkResponse | Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(
            select(Bookmark).where(Bookmark.id == bookmark_id)
        )
        bookmark = result.scalar_one_or_none()
        if bookmark is None:
            return Response(
                content='{"type":"https://keeper.local/errors/bookmark-not-found","title":"书签不存在","status":404,"detail":"指定书签不存在"}',
                status_code=404,
                media_type="application/json",
            )

        updates = body.model_dump(exclude_unset=True)

        if updates.get("name") is not None:
            bookmark.name = updates["name"]
            bookmark.pinyin_full = _pinyin.get_pinyin(bookmark.name, "").lower()

        if updates.get("pinyinInitials") is not None:
            bookmark.pinyin_initials = updates["pinyinInitials"]
        elif updates.get("name") is not None:
            bookmark.pinyin_initials = _compute_initials(bookmark.name)

        if updates.get("tagIds") is not None:
            tag_ids = updates["tagIds"]
            if not await _validate_tag_ids(session, tag_ids):
                return Response(
                    content='{"type":"https://keeper.local/errors/tag-not-found","title":"标签不存在","status":422,"detail":"包含不存在的标签 ID"}',
                    status_code=422,
                    media_type="application/json",
                )
            bookmark.tag_ids = json.dumps(tag_ids)

        if updates.get("urls") is not None:
            bookmark.urls = json.dumps(updates["urls"])

        if updates.get("notes") is not None:
            bookmark.notes = updates["notes"]

        if updates.get("accounts") is not None:
            accounts = updates["accounts"]
            account_models = [AccountCreate.model_validate(item) for item in accounts]
            if not await _validate_related_ids(session, account_models):
                return Response(
                    content='{"type":"https://keeper.local/errors/relation-not-found","title":"关联不存在","status":422,"detail":"账户中包含不存在的关联 ID"}',
                    status_code=422,
                    media_type="application/json",
                )
            now = datetime.now(timezone.utc).isoformat()
            bookmark.accounts = json.dumps(_build_accounts(account_models, now))

        bookmark.updated_at = datetime.now(timezone.utc).isoformat()

        await session.commit()
        await session.refresh(bookmark)

    return _bookmark_to_response(bookmark)


@router.delete("/{bookmark_id}", status_code=204, response_model=None)
async def delete_bookmark(bookmark_id: str, request: Request) -> Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(
            select(Bookmark).where(Bookmark.id == bookmark_id)
        )
        bookmark = result.scalar_one_or_none()
        if bookmark is None:
            return Response(
                content='{"type":"https://keeper.local/errors/bookmark-not-found","title":"书签不存在","status":404,"detail":"指定书签不存在"}',
                status_code=404,
                media_type="application/json",
            )

        await session.delete(bookmark)
        await session.commit()

    return Response(status_code=204)


@router.post("/{bookmark_id}/use", response_model=None)
async def use_bookmark(
    bookmark_id: str,
    body: BookmarkUseRequest,
    request: Request,
) -> BookmarkUseResponse | Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(
            select(Bookmark).where(Bookmark.id == bookmark_id)
        )
        bookmark = result.scalar_one_or_none()
        if bookmark is None:
            return Response(
                content='{"type":"https://keeper.local/errors/bookmark-not-found","title":"书签不存在","status":404,"detail":"指定书签不存在"}',
                status_code=404,
                media_type="application/json",
            )

        now = datetime.now(timezone.utc).isoformat()
        bookmark.last_used_at = now
        bookmark.updated_at = now

        urls = _safe_json_load_list(bookmark.urls)
        if body.url is not None:
            for item in urls:
                if isinstance(item, dict) and item.get("url") == body.url:
                    item["lastUsed"] = now
                    break
            bookmark.urls = json.dumps(urls)

        accounts = _safe_json_load_list(bookmark.accounts)
        if body.accountId is not None:
            for item in accounts:
                if isinstance(item, dict) and item.get("id") == body.accountId:
                    item["lastUsed"] = now
                    break
            bookmark.accounts = json.dumps(accounts)

        await session.commit()

    return BookmarkUseResponse(message="更新使用时间成功", lastUsedAt=now)
