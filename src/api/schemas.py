"""认证请求/响应 Pydantic 模型 — 对齐 docs/api.md 认证与会话管理章节。"""

from typing import Literal

from pydantic import BaseModel, Field


class InitializeRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class InitializeResponse(BaseModel):
    message: str = "初始化成功"


class UnlockRequest(BaseModel):
    password: str = Field(min_length=1)


class UnlockResponse(BaseModel):
    message: str = "解锁成功"


class AuthInfoResponse(BaseModel):
    email: str


class StatusResponseUnlocked(BaseModel):
    locked: bool = False
    sessionExpiresAt: str


class StatusResponseLocked(BaseModel):
    locked: bool = True


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(default=None, max_length=50)


class TagUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(default=None, max_length=50)


class TagResponse(BaseModel):
    id: int
    name: str
    color: str
    icon: str
    createdAt: str
    updatedAt: str


class TagListResponse(BaseModel):
    data: list[TagResponse]
    total: int


class RelationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    type: Literal["phone", "email", "idcard", "other"]


class RelationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    type: Literal["phone", "email", "idcard", "other"]


class RelationResponse(BaseModel):
    id: int
    name: str
    type: str
    createdAt: str
    updatedAt: str


class RelationListResponse(BaseModel):
    data: list[RelationResponse]
    total: int


class UrlItem(BaseModel):
    url: str
    lastUsed: str | None = None


class AccountCreate(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=1000)
    relatedIds: list[int] | None = None


class AccountResponse(BaseModel):
    id: int
    username: str
    password: str
    relatedIds: list[int]
    createdAt: str
    lastUsed: str


class BookmarkCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    pinyinInitials: str | None = Field(default=None, max_length=50)
    tagIds: list[int] | None = None
    urls: list[UrlItem] | None = None
    notes: str | None = Field(default=None, max_length=5000)
    accounts: list[AccountCreate] | None = None


class BookmarkUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    pinyinInitials: str | None = Field(default=None, max_length=50)
    tagIds: list[int] | None = None
    urls: list[UrlItem] | None = None
    notes: str | None = Field(default=None, max_length=5000)
    accounts: list[AccountCreate] | None = None


class BookmarkPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    pinyinInitials: str | None = Field(default=None, max_length=50)
    tagIds: list[int] | None = None
    urls: list[UrlItem] | None = None
    notes: str | None = Field(default=None, max_length=5000)
    accounts: list[AccountCreate] | None = None


class SearchHighlight(BaseModel):
    field: str
    positions: list[list[int]]


class BookmarkResponse(BaseModel):
    id: str
    name: str
    pinyinInitials: str
    tagIds: list[int]
    urls: list[UrlItem]
    notes: str
    accounts: list[AccountResponse]
    createdAt: str
    updatedAt: str
    lastUsedAt: str
    highlights: list[SearchHighlight] | None = None


class BookmarkListResponse(BaseModel):
    data: list[BookmarkResponse]
    total: int
    limit: int
    offset: int


class BookmarkUseRequest(BaseModel):
    url: str | None = None
    accountId: int | None = None


class BookmarkUseResponse(BaseModel):
    message: str
    lastUsedAt: str


class TagCount(BaseModel):
    id: int
    name: str
    count: int


class RecentBookmark(BaseModel):
    id: str
    name: str
    lastUsedAt: str


class StatsResponse(BaseModel):
    totalBookmarks: int
    totalTags: int
    totalRelations: int
    totalAccounts: int
    mostUsedTags: list[TagCount]
    recentlyUsed: list[RecentBookmark]


class ImportPreviewRequest(BaseModel):
    format: Literal["keeper_json", "bitwarden_json", "csv"]
    content: str = Field(min_length=1)


class ImportConflict(BaseModel):
    name: str
    type: str


class ImportPreviewResponse(BaseModel):
    format: str
    totalBookmarks: int
    totalTags: int
    totalRelations: int
    conflicts: list[ImportConflict]
    warnings: list[str]


class ImportRequest(BaseModel):
    format: Literal["keeper_json", "bitwarden_json", "csv"]
    content: str = Field(min_length=1)
    conflictPolicy: Literal["skip", "rename", "overwrite"] = "skip"


class ImportCounts(BaseModel):
    bookmarks: int
    tags: int
    relations: int


class ImportSkipped(BaseModel):
    bookmarks: int
    reason: str


class ImportResponse(BaseModel):
    message: str
    imported: ImportCounts
    skipped: ImportSkipped
    warnings: list[str]


# ── 数据库管理 ────────────────────────────────────────────────


class DatabaseInfo(BaseModel):
    path: str
    name: str


class DatabaseListResponse(BaseModel):
    databases: list[DatabaseInfo]
    current: str | None = None


class DatabaseOpenRequest(BaseModel):
    path: str = Field(min_length=1)


class DatabaseOpenResponse(BaseModel):
    message: str = "数据库已切换"
    name: str


class DatabaseCreateRequest(BaseModel):
    path: str = Field(min_length=1)
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class DatabaseRemoveRequest(BaseModel):
    path: str = Field(min_length=1)


class DatabaseCreateResponse(BaseModel):
    message: str = "数据库已创建"
    name: str
