import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select
from xpinyin import Pinyin

from src.api.bookmarks import _compute_initials
from src.api.schemas import (
    ImportConflict,
    ImportCounts,
    ImportPreviewRequest,
    ImportPreviewResponse,
    ImportRequest,
    ImportResponse,
    ImportSkipped,
)
from src.api.tags import TAG_COLORS
from src.api.session import SessionManager
from src.crypto.encryption import EncryptionService
from src.db.models import Bookmark, Relation, Tag

router = APIRouter(prefix="/api/transfer", tags=["transfer"])

_pinyin = Pinyin()

_CSV_COLUMNS = ["name", "url", "username", "password", "notes", "tags"]


def _get_enc(request: Request) -> EncryptionService | None:
    session_manager: SessionManager = request.app.state.session_manager
    key = session_manager.encryption_key
    if key is None:
        return None
    return EncryptionService(key)


def _decrypt_password(enc_service: EncryptionService, password: str) -> str:
    try:
        return enc_service.decrypt(password)
    except Exception:
        return password


def _parse_keeper_json(content: str) -> dict[str, Any] | None:
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    inner = data.get("data")
    if not isinstance(inner, dict):
        return None
    return data


def _parse_bitwarden_json(content: str) -> dict[str, Any] | None:
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("encrypted") is True:
        return None
    if "items" not in data:
        return None
    return data


def _parse_csv_content(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content))
    rows: list[dict[str, str]] = []
    for row in reader:
        if "name" in row:
            rows.append(row)
    return rows


def _extract_bookmark_names_keeper(data: dict[str, Any]) -> list[str]:
    inner: dict[str, Any] = data.get("data", {})
    bookmarks: list[Any] = inner.get("bookmarks", [])
    return [b["name"] for b in bookmarks if isinstance(b, dict) and "name" in b]


def _extract_bookmark_names_bitwarden(data: dict[str, Any]) -> list[str]:
    items: list[Any] = data.get("items", [])
    return [
        item["name"]
        for item in items
        if isinstance(item, dict) and item.get("type") == 1 and "name" in item
    ]


def _extract_bookmark_names_csv(rows: list[dict[str, str]]) -> list[str]:
    return [row["name"] for row in rows if row.get("name")]


def _extract_tag_names_keeper(data: dict[str, Any]) -> list[str]:
    inner: dict[str, Any] = data.get("data", {})
    tags: list[Any] = inner.get("tags", [])
    return [t["name"] for t in tags if isinstance(t, dict) and "name" in t]


def _extract_relation_names_keeper(data: dict[str, Any]) -> list[str]:
    inner: dict[str, Any] = data.get("data", {})
    relations: list[Any] = inner.get("relations", [])
    return [r["name"] for r in relations if isinstance(r, dict) and "name" in r]


def _extract_tag_names_bitwarden(data: dict[str, Any]) -> list[str]:
    folders: list[Any] = data.get("folders", [])
    return [f["name"] for f in folders if isinstance(f, dict) and f.get("name")]


def _extract_tag_names_csv(rows: list[dict[str, str]]) -> list[str]:
    names: set[str] = set()
    for row in rows:
        tags_str = row.get("tags", "")
        for tag_name in tags_str.split(","):
            tag_name = tag_name.strip()
            if tag_name:
                names.add(tag_name)
    return list(names)


def _resolve_conflict_name(
    base_name: str, existing_names: set[str], suffix: str = "导入"
) -> str:
    candidate = f"{base_name} ({suffix})"
    if candidate not in existing_names:
        return candidate
    counter = 2
    while True:
        candidate = f"{base_name} ({suffix} {counter})"
        if candidate not in existing_names:
            return candidate
        counter += 1


async def _ensure_tags_by_name(session, tag_names: list[str]) -> dict[str, int]:
    if not tag_names:
        return {}
    result = await session.execute(select(Tag))
    existing_tags = {tag.name: tag.id for tag in result.scalars().all()}

    count_r = await session.execute(select(func.count()).select_from(Tag))
    current_count: int = count_r.scalar_one()

    name_to_id: dict[str, int] = {}
    now = datetime.now(timezone.utc).isoformat()
    for name in tag_names:
        if name in existing_tags:
            name_to_id[name] = existing_tags[name]
        else:
            color = TAG_COLORS[current_count % len(TAG_COLORS)]
            tag = Tag(name=name, color=color, created_at=now, updated_at=now)
            session.add(tag)
            await session.flush()
            name_to_id[name] = tag.id
            existing_tags[name] = tag.id
            current_count += 1
    return name_to_id


async def _ensure_relations_by_name(
    session,
    relations_data: list[dict[str, Any]],
) -> dict[str, int]:
    if not relations_data:
        return {}
    result = await session.execute(select(Relation))
    existing = {r.name: r.id for r in result.scalars().all()}

    name_to_id: dict[str, int] = {}
    now = datetime.now(timezone.utc).isoformat()
    for rel in relations_data:
        name = rel.get("name", "")
        rel_type = rel.get("type", "other")
        if rel_type not in ("phone", "email", "idcard", "other"):
            rel_type = "other"
        if not name:
            continue
        if name in existing:
            name_to_id[name] = existing[name]
        else:
            relation = Relation(
                name=name, type=rel_type, created_at=now, updated_at=now
            )
            session.add(relation)
            await session.flush()
            name_to_id[name] = relation.id
            existing[name] = relation.id
    return name_to_id


@router.get("/export/json", response_model=None)
async def export_json(request: Request) -> Response:
    enc_service = _get_enc(request)
    if enc_service is None:
        return Response(
            content='{"type":"https://keeper.local/errors/unauthorized","title":"未认证","status":401,"detail":"请先解锁"}',
            status_code=401,
            media_type="application/json",
        )

    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        tags_r = await session.execute(select(Tag))
        tags = tags_r.scalars().all()

        relations_r = await session.execute(select(Relation))
        relations = relations_r.scalars().all()

        bookmarks_r = await session.execute(select(Bookmark))
        bookmarks = bookmarks_r.scalars().all()

    tags_data = [
        {"id": t.id, "name": t.name, "color": t.color, "icon": t.icon} for t in tags
    ]

    relations_data = [{"id": r.id, "name": r.name, "type": r.type} for r in relations]

    bookmarks_data = []
    for bm in bookmarks:
        try:
            tag_ids = json.loads(bm.tag_ids)
        except (TypeError, ValueError):
            tag_ids = []
        try:
            urls = json.loads(bm.urls)
        except (TypeError, ValueError):
            urls = []
        try:
            accounts = json.loads(bm.accounts)
        except (TypeError, ValueError):
            accounts = []

        decrypted_accounts = []
        for acc in accounts:
            if not isinstance(acc, dict):
                continue
            password = acc.get("password", "")
            decrypted_accounts.append(
                {
                    "id": acc.get("id"),
                    "username": acc.get("username", ""),
                    "password": _decrypt_password(enc_service, password),
                    "relatedIds": acc.get("relatedIds", []),
                    "createdAt": acc.get("createdAt", ""),
                    "lastUsed": acc.get("lastUsed", ""),
                }
            )

        bookmarks_data.append(
            {
                "id": bm.id,
                "name": bm.name,
                "pinyinInitials": bm.pinyin_initials,
                "tagIds": tag_ids if isinstance(tag_ids, list) else [],
                "urls": urls if isinstance(urls, list) else [],
                "notes": bm.notes,
                "accounts": decrypted_accounts,
                "createdAt": bm.created_at,
                "updatedAt": bm.updated_at,
                "lastUsedAt": bm.last_used_at,
            }
        )

    now = datetime.now(timezone.utc)
    export_data = {
        "version": "1.0",
        "exportedAt": now.isoformat(),
        "data": {
            "tags": tags_data,
            "relations": relations_data,
            "bookmarks": bookmarks_data,
        },
    }

    date_str = now.strftime("%Y%m%d")
    return Response(
        content=json.dumps(export_data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="keeper-export-{date_str}.json"',
            "X-Export-Warning": "Contains plaintext passwords",
        },
    )


@router.get("/export/csv", response_model=None)
async def export_csv(request: Request) -> Response:
    enc_service = _get_enc(request)
    if enc_service is None:
        return Response(
            content='{"type":"https://keeper.local/errors/unauthorized","title":"未认证","status":401,"detail":"请先解锁"}',
            status_code=401,
            media_type="application/json",
        )

    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        tags_r = await session.execute(select(Tag))
        tag_map = {t.id: t.name for t in tags_r.scalars().all()}

        bookmarks_r = await session.execute(select(Bookmark))
        bookmarks = bookmarks_r.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_CSV_COLUMNS)

    for bm in bookmarks:
        try:
            tag_ids = json.loads(bm.tag_ids)
        except (TypeError, ValueError):
            tag_ids = []
        try:
            urls = json.loads(bm.urls)
        except (TypeError, ValueError):
            urls = []
        try:
            accounts = json.loads(bm.accounts)
        except (TypeError, ValueError):
            accounts = []

        first_url = ""
        if isinstance(urls, list) and urls:
            first_item = urls[0]
            if isinstance(first_item, dict):
                first_url = first_item.get("url", "")

        tag_names = []
        if isinstance(tag_ids, list):
            for tid in tag_ids:
                if isinstance(tid, int) and tid in tag_map:
                    tag_names.append(tag_map[tid])
        tags_str = ",".join(tag_names)

        if isinstance(accounts, list) and accounts:
            for acc in accounts:
                if not isinstance(acc, dict):
                    continue
                password = _decrypt_password(enc_service, acc.get("password", ""))
                writer.writerow(
                    [
                        bm.name,
                        first_url,
                        acc.get("username", ""),
                        password,
                        bm.notes,
                        tags_str,
                    ]
                )
        else:
            writer.writerow([bm.name, first_url, "", "", bm.notes, tags_str])

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="keeper-export-{date_str}.csv"',
            "X-Export-Warning": "Contains plaintext passwords",
        },
    )


@router.post("/import/preview", response_model=None)
async def import_preview(
    body: ImportPreviewRequest, request: Request
) -> ImportPreviewResponse | Response:
    session_factory = request.app.state.session_factory
    fmt = body.format
    content = body.content

    bookmark_names: list[str] = []
    tag_names: list[str] = []
    total_relations = 0
    warnings: list[str] = []

    if fmt == "keeper_json":
        parsed = _parse_keeper_json(content)
        if parsed is None:
            return Response(
                content='{"type":"https://keeper.local/errors/invalid-format","title":"格式错误","status":422,"detail":"无法解析 Keeper JSON 格式"}',
                status_code=422,
                media_type="application/json",
            )
        bookmark_names = _extract_bookmark_names_keeper(parsed)
        tag_names = _extract_tag_names_keeper(parsed)
        total_relations = len(_extract_relation_names_keeper(parsed))

    elif fmt == "bitwarden_json":
        parsed = _parse_bitwarden_json(content)
        if parsed is None:
            return Response(
                content='{"type":"https://keeper.local/errors/invalid-format","title":"格式错误","status":422,"detail":"无法解析 Bitwarden JSON 格式（仅支持非加密导出）"}',
                status_code=422,
                media_type="application/json",
            )
        bookmark_names = _extract_bookmark_names_bitwarden(parsed)
        tag_names = _extract_tag_names_bitwarden(parsed)
        warnings.append("Bitwarden 导入仅处理 Login 类型的条目")

    elif fmt == "csv":
        rows = _parse_csv_content(content)
        if not rows:
            return Response(
                content='{"type":"https://keeper.local/errors/invalid-format","title":"格式错误","status":422,"detail":"CSV 内容为空或缺少 name 列"}',
                status_code=422,
                media_type="application/json",
            )
        bookmark_names = _extract_bookmark_names_csv(rows)
        tag_names = _extract_tag_names_csv(rows)
        warnings.append("CSV 文件中的密码将被自动加密")

    conflicts: list[ImportConflict] = []
    async with session_factory() as session:
        if bookmark_names:
            result = await session.execute(select(Bookmark.name))
            existing_names = {row[0] for row in result.all()}
            for name in bookmark_names:
                if name in existing_names:
                    conflicts.append(ImportConflict(name=name, type="duplicate_name"))

    return ImportPreviewResponse(
        format=fmt,
        totalBookmarks=len(bookmark_names),
        totalTags=len(tag_names),
        totalRelations=total_relations,
        conflicts=conflicts,
        warnings=warnings,
    )


@router.post("/import", response_model=None)
async def import_data(
    body: ImportRequest, request: Request
) -> ImportResponse | Response:
    enc_service = _get_enc(request)
    if enc_service is None:
        return Response(
            content='{"type":"https://keeper.local/errors/unauthorized","title":"未认证","status":401,"detail":"请先解锁"}',
            status_code=401,
            media_type="application/json",
        )

    fmt = body.format
    content = body.content
    policy = body.conflictPolicy

    if fmt == "keeper_json":
        return await _import_keeper_json(request, enc_service, content, policy)
    elif fmt == "bitwarden_json":
        return await _import_bitwarden_json(request, enc_service, content, policy)
    elif fmt == "csv":
        return await _import_csv(request, enc_service, content, policy)

    return Response(
        content='{"type":"https://keeper.local/errors/invalid-format","title":"格式错误","status":422,"detail":"不支持的导入格式"}',
        status_code=422,
        media_type="application/json",
    )


async def _import_keeper_json(
    request: Request,
    enc_service: EncryptionService,
    content: str,
    policy: str,
) -> ImportResponse | Response:
    parsed = _parse_keeper_json(content)
    if parsed is None:
        return Response(
            content='{"type":"https://keeper.local/errors/invalid-format","title":"格式错误","status":422,"detail":"无法解析 Keeper JSON 格式"}',
            status_code=422,
            media_type="application/json",
        )

    inner: dict[str, Any] = parsed["data"]
    raw_tags: list[Any] = inner.get("tags", [])
    raw_relations: list[Any] = inner.get("relations", [])
    raw_bookmarks: list[Any] = inner.get("bookmarks", [])

    session_factory = request.app.state.session_factory
    now = datetime.now(timezone.utc).isoformat()
    imported_bookmarks = 0
    skipped_bookmarks = 0
    warnings: list[str] = []

    async with session_factory() as session:
        tag_name_to_id = await _ensure_tags_by_name(
            session,
            [t["name"] for t in raw_tags if isinstance(t, dict) and "name" in t],
        )

        old_tag_id_to_name: dict[int, str] = {}
        for t in raw_tags:
            if isinstance(t, dict) and "id" in t and "name" in t:
                old_tag_id_to_name[t["id"]] = t["name"]

        relation_name_to_id = await _ensure_relations_by_name(session, raw_relations)

        old_relation_id_to_name: dict[int, str] = {}
        for r in raw_relations:
            if isinstance(r, dict) and "id" in r and "name" in r:
                old_relation_id_to_name[r["id"]] = r["name"]

        existing_r = await session.execute(select(Bookmark.name))
        existing_names = {row[0] for row in existing_r.all()}

        for bm_data in raw_bookmarks:
            if not isinstance(bm_data, dict) or "name" not in bm_data:
                continue

            name = bm_data["name"]
            if name in existing_names:
                if policy == "skip":
                    skipped_bookmarks += 1
                    continue
                elif policy == "rename":
                    name = _resolve_conflict_name(name, existing_names)
                elif policy == "overwrite":
                    del_r = await session.execute(
                        select(Bookmark).where(Bookmark.name == bm_data["name"])
                    )
                    old_bm = del_r.scalar_one_or_none()
                    if old_bm:
                        await session.delete(old_bm)

            old_tag_ids = bm_data.get("tagIds", [])
            new_tag_ids: list[int] = []
            if isinstance(old_tag_ids, list):
                for old_id in old_tag_ids:
                    tag_name = old_tag_id_to_name.get(old_id)
                    if tag_name and tag_name in tag_name_to_id:
                        new_tag_ids.append(tag_name_to_id[tag_name])

            raw_accounts = bm_data.get("accounts", [])
            accounts: list[dict[str, Any]] = []
            for idx, acc in enumerate(
                raw_accounts if isinstance(raw_accounts, list) else [], start=1
            ):
                if not isinstance(acc, dict):
                    continue
                plaintext_pw = acc.get("password", "")
                try:
                    encrypted_pw = (
                        enc_service.encrypt(plaintext_pw) if plaintext_pw else ""
                    )
                except Exception:
                    encrypted_pw = plaintext_pw
                    warnings.append(f"书签 '{name}' 的账户密码加密失败")

                old_related_ids = acc.get("relatedIds", [])
                new_related_ids: list[int] = []
                if isinstance(old_related_ids, list):
                    for old_rid in old_related_ids:
                        rel_name = old_relation_id_to_name.get(old_rid)
                        if rel_name and rel_name in relation_name_to_id:
                            new_related_ids.append(relation_name_to_id[rel_name])

                accounts.append(
                    {
                        "id": idx,
                        "username": acc.get("username", ""),
                        "password": encrypted_pw,
                        "relatedIds": new_related_ids,
                        "createdAt": now,
                        "lastUsed": now,
                    }
                )

            urls = bm_data.get("urls", [])
            if not isinstance(urls, list):
                urls = []

            bookmark = Bookmark(
                id=str(uuid.uuid4()),
                name=name,
                pinyin_initials=_compute_initials(name),
                pinyin_full=_pinyin.get_pinyin(name, "").lower(),
                tag_ids=json.dumps(new_tag_ids),
                urls=json.dumps(urls),
                notes=bm_data.get("notes", ""),
                accounts=json.dumps(accounts),
                created_at=now,
                updated_at=now,
                last_used_at=now,
            )
            session.add(bookmark)
            existing_names.add(name)
            imported_bookmarks += 1

        await session.commit()

    return ImportResponse(
        message="导入完成",
        imported=ImportCounts(
            bookmarks=imported_bookmarks,
            tags=len(tag_name_to_id),
            relations=len(relation_name_to_id),
        ),
        skipped=ImportSkipped(
            bookmarks=skipped_bookmarks,
            reason="名称重复,已跳过" if skipped_bookmarks > 0 else "",
        ),
        warnings=warnings,
    )


async def _import_bitwarden_json(
    request: Request,
    enc_service: EncryptionService,
    content: str,
    policy: str,
) -> ImportResponse | Response:
    parsed = _parse_bitwarden_json(content)
    if parsed is None:
        return Response(
            content='{"type":"https://keeper.local/errors/invalid-format","title":"格式错误","status":422,"detail":"无法解析 Bitwarden JSON 格式（仅支持非加密导出）"}',
            status_code=422,
            media_type="application/json",
        )

    folders: list[Any] = parsed.get("folders", [])
    folder_map: dict[str, str] = {}
    for f in folders:
        if isinstance(f, dict) and "id" in f and "name" in f:
            folder_map[f["id"]] = f["name"]

    items: list[dict[str, Any]] = [
        item
        for item in parsed.get("items", [])
        if isinstance(item, dict) and item.get("type") == 1
    ]

    folder_names = list(set(folder_map.values()))

    session_factory = request.app.state.session_factory
    now = datetime.now(timezone.utc).isoformat()
    imported_bookmarks = 0
    skipped_bookmarks = 0
    warnings: list[str] = []

    async with session_factory() as session:
        tag_name_to_id = await _ensure_tags_by_name(session, folder_names)

        existing_r = await session.execute(select(Bookmark.name))
        existing_names = {row[0] for row in existing_r.all()}

        for item in items:
            name = item.get("name", "")
            if not name:
                continue

            if name in existing_names:
                if policy == "skip":
                    skipped_bookmarks += 1
                    continue
                elif policy == "rename":
                    name = _resolve_conflict_name(name, existing_names)
                elif policy == "overwrite":
                    del_r = await session.execute(
                        select(Bookmark).where(Bookmark.name == item["name"])
                    )
                    old_bm = del_r.scalar_one_or_none()
                    if old_bm:
                        await session.delete(old_bm)

            login = item.get("login", {}) or {}
            uris = login.get("uris", []) or []
            first_url = ""
            if uris and isinstance(uris, list) and isinstance(uris[0], dict):
                first_url = uris[0].get("uri", "")

            username = login.get("username", "") or ""
            password = login.get("password", "") or ""

            encrypted_pw = ""
            if password:
                try:
                    encrypted_pw = enc_service.encrypt(password)
                except Exception:
                    encrypted_pw = password
                    warnings.append(f"书签 '{name}' 的密码加密失败")

            tag_ids: list[int] = []
            folder_id = item.get("folderId")
            if folder_id and folder_id in folder_map:
                folder_name = folder_map[folder_id]
                if folder_name in tag_name_to_id:
                    tag_ids.append(tag_name_to_id[folder_name])

            urls = [{"url": first_url, "lastUsed": now}] if first_url else []
            accounts: list[dict[str, Any]] = []
            if username or encrypted_pw:
                accounts.append(
                    {
                        "id": 1,
                        "username": username,
                        "password": encrypted_pw,
                        "relatedIds": [],
                        "createdAt": now,
                        "lastUsed": now,
                    }
                )

            notes = item.get("notes", "") or ""

            bookmark = Bookmark(
                id=str(uuid.uuid4()),
                name=name,
                pinyin_initials=_compute_initials(name),
                pinyin_full=_pinyin.get_pinyin(name, "").lower(),
                tag_ids=json.dumps(tag_ids),
                urls=json.dumps(urls),
                notes=notes,
                accounts=json.dumps(accounts),
                created_at=now,
                updated_at=now,
                last_used_at=now,
            )
            session.add(bookmark)
            existing_names.add(name)
            imported_bookmarks += 1

        await session.commit()

    return ImportResponse(
        message="导入完成",
        imported=ImportCounts(
            bookmarks=imported_bookmarks,
            tags=len(tag_name_to_id),
            relations=0,
        ),
        skipped=ImportSkipped(
            bookmarks=skipped_bookmarks,
            reason="名称重复,已跳过" if skipped_bookmarks > 0 else "",
        ),
        warnings=warnings,
    )


async def _import_csv(
    request: Request,
    enc_service: EncryptionService,
    content: str,
    policy: str,
) -> ImportResponse | Response:
    rows = _parse_csv_content(content)
    if not rows:
        return Response(
            content='{"type":"https://keeper.local/errors/invalid-format","title":"格式错误","status":422,"detail":"CSV 内容为空或缺少 name 列"}',
            status_code=422,
            media_type="application/json",
        )

    all_tag_names = _extract_tag_names_csv(rows)

    session_factory = request.app.state.session_factory
    now = datetime.now(timezone.utc).isoformat()
    imported_bookmarks = 0
    skipped_bookmarks = 0
    warnings: list[str] = []

    async with session_factory() as session:
        tag_name_to_id = await _ensure_tags_by_name(session, all_tag_names)

        existing_r = await session.execute(select(Bookmark.name))
        existing_names = {row[0] for row in existing_r.all()}

        for row in rows:
            name = row.get("name", "").strip()
            if not name:
                continue

            if name in existing_names:
                if policy == "skip":
                    skipped_bookmarks += 1
                    continue
                elif policy == "rename":
                    name = _resolve_conflict_name(name, existing_names)
                elif policy == "overwrite":
                    del_r = await session.execute(
                        select(Bookmark).where(Bookmark.name == row["name"].strip())
                    )
                    old_bm = del_r.scalar_one_or_none()
                    if old_bm:
                        await session.delete(old_bm)

            url = row.get("url", "").strip()
            username = row.get("username", "").strip()
            password = row.get("password", "").strip()
            notes = row.get("notes", "").strip()
            tags_str = row.get("tags", "").strip()

            encrypted_pw = ""
            if password:
                try:
                    encrypted_pw = enc_service.encrypt(password)
                except Exception:
                    encrypted_pw = password
                    warnings.append(f"书签 '{name}' 的密码加密失败")

            tag_ids: list[int] = []
            for tag_name in tags_str.split(","):
                tag_name = tag_name.strip()
                if tag_name and tag_name in tag_name_to_id:
                    tag_ids.append(tag_name_to_id[tag_name])

            urls = [{"url": url, "lastUsed": now}] if url else []
            accounts: list[dict[str, Any]] = []
            if username or encrypted_pw:
                accounts.append(
                    {
                        "id": 1,
                        "username": username,
                        "password": encrypted_pw,
                        "relatedIds": [],
                        "createdAt": now,
                        "lastUsed": now,
                    }
                )

            bookmark = Bookmark(
                id=str(uuid.uuid4()),
                name=name,
                pinyin_initials=_compute_initials(name),
                pinyin_full=_pinyin.get_pinyin(name, "").lower(),
                tag_ids=json.dumps(tag_ids),
                urls=json.dumps(urls),
                notes=notes,
                accounts=json.dumps(accounts),
                created_at=now,
                updated_at=now,
                last_used_at=now,
            )
            session.add(bookmark)
            existing_names.add(name)
            imported_bookmarks += 1

        await session.commit()

    return ImportResponse(
        message="导入完成",
        imported=ImportCounts(
            bookmarks=imported_bookmarks,
            tags=len(tag_name_to_id),
            relations=0,
        ),
        skipped=ImportSkipped(
            bookmarks=skipped_bookmarks,
            reason="名称重复,已跳过" if skipped_bookmarks > 0 else "",
        ),
        warnings=warnings,
    )
