import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.api.schemas import (
    RelationCreate,
    RelationListResponse,
    RelationResponse,
    RelationUpdate,
)
from src.db.models import Bookmark, Relation

router = APIRouter(prefix="/api/relations", tags=["relations"])


def _relation_to_response(relation: Relation) -> RelationResponse:
    return RelationResponse(
        id=relation.id,
        name=relation.name,
        type=relation.type,
        createdAt=relation.created_at,
        updatedAt=relation.updated_at,
    )


@router.get("", response_model=RelationListResponse)
async def list_relations(
    request: Request,
    sort: str = Query(default="name"),
) -> RelationListResponse:
    session_factory = request.app.state.session_factory

    sort_desc = sort.startswith("-")
    sort_key = sort[1:] if sort_desc else sort
    sort_map = {
        "name": Relation.name,
        "type": Relation.type,
        "createdAt": Relation.created_at,
        "updatedAt": Relation.updated_at,
    }
    sort_col = sort_map.get(sort_key, Relation.name)
    order_col = sort_col.desc() if sort_desc else sort_col.asc()

    async with session_factory() as session:
        result = await session.execute(select(Relation).order_by(order_col))
        relations = result.scalars().all()

    return RelationListResponse(
        data=[_relation_to_response(relation) for relation in relations],
        total=len(relations),
    )


@router.get("/{relation_id}", response_model=None)
async def get_relation(
    relation_id: int, request: Request
) -> RelationResponse | Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(
            select(Relation).where(Relation.id == relation_id)
        )
        relation = result.scalar_one_or_none()

    if relation is None:
        return Response(
            content='{"type":"https://keeper.local/errors/relation-not-found","title":"关联不存在","status":404,"detail":"指定关联不存在"}',
            status_code=404,
            media_type="application/json",
        )

    return _relation_to_response(relation)


@router.post("", status_code=201, response_model=None)
async def create_relation(
    body: RelationCreate, request: Request
) -> RelationResponse | Response:
    session_factory = request.app.state.session_factory

    now = datetime.now(timezone.utc).isoformat()
    relation = Relation(
        name=body.name,
        type=body.type,
        created_at=now,
        updated_at=now,
    )

    async with session_factory() as session:
        session.add(relation)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return Response(
                content='{"type":"https://keeper.local/errors/relation-name-conflict","title":"关联冲突","status":409,"detail":"关联名称已存在"}',
                status_code=409,
                media_type="application/json",
            )
        await session.refresh(relation)

    return _relation_to_response(relation)


@router.put("/{relation_id}", response_model=None)
async def update_relation(
    relation_id: int,
    body: RelationUpdate,
    request: Request,
) -> RelationResponse | Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        result = await session.execute(
            select(Relation).where(Relation.id == relation_id)
        )
        relation = result.scalar_one_or_none()
        if relation is None:
            return Response(
                content='{"type":"https://keeper.local/errors/relation-not-found","title":"关联不存在","status":404,"detail":"指定关联不存在"}',
                status_code=404,
                media_type="application/json",
            )

        relation.name = body.name
        relation.type = body.type
        relation.updated_at = datetime.now(timezone.utc).isoformat()

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return Response(
                content='{"type":"https://keeper.local/errors/relation-name-conflict","title":"关联冲突","status":409,"detail":"关联名称已存在"}',
                status_code=409,
                media_type="application/json",
            )
        await session.refresh(relation)

    return _relation_to_response(relation)


@router.delete("/{relation_id}", status_code=204, response_model=None)
async def delete_relation(
    relation_id: int,
    request: Request,
    cascade: bool = Query(default=False),
) -> Response:
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        relation_result = await session.execute(
            select(Relation).where(Relation.id == relation_id)
        )
        relation = relation_result.scalar_one_or_none()
        if relation is None:
            return Response(
                content='{"type":"https://keeper.local/errors/relation-not-found","title":"关联不存在","status":404,"detail":"指定关联不存在"}',
                status_code=404,
                media_type="application/json",
            )

        # SQL-level pre-filter: only load bookmarks whose accounts JSON
        # contains the relation_id string (candidate set)
        candidate_r = await session.execute(
            select(Bookmark).where(Bookmark.accounts.contains(str(relation_id)))
        )
        candidates = candidate_r.scalars().all()

        # Python-level precise check on candidates only
        referenced = 0
        for bookmark in candidates:
            try:
                accounts = json.loads(bookmark.accounts)
            except (TypeError, ValueError):
                accounts = []
            if not isinstance(accounts, list):
                continue

            for account in accounts:
                if not isinstance(account, dict):
                    continue
                related_ids = account.get("relatedIds", [])
                if isinstance(related_ids, list) and relation_id in related_ids:
                    referenced += 1
                    break

        if not cascade and referenced > 0:
            return Response(
                content=(
                    "{"
                    '"type":"https://keeper.local/errors/relation-in-use",'
                    '"title":"关联被引用",'
                    '"status":409,'
                    f'"detail":"有 {referenced} 条书签仍在使用该关联"'
                    "}"
                ),
                status_code=409,
                media_type="application/json",
            )

        if cascade:
            for bookmark in candidates:
                try:
                    accounts = json.loads(bookmark.accounts)
                except (TypeError, ValueError):
                    accounts = []
                if not isinstance(accounts, list):
                    continue

                changed = False
                for account in accounts:
                    if not isinstance(account, dict):
                        continue
                    related_ids = account.get("relatedIds")
                    if isinstance(related_ids, list) and relation_id in related_ids:
                        account["relatedIds"] = [
                            item for item in related_ids if item != relation_id
                        ]
                        changed = True

                if changed:
                    bookmark.accounts = json.dumps(accounts)

        await session.delete(relation)
        await session.commit()

    return Response(status_code=204)
