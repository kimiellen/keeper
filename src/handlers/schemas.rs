//! API 请求/响应 Schema
//!
//! 与 Python 版本 API 兼容的数据结构定义。

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

// ==================== 认证相关 ====================

/// POST /api/auth/initialize 请求
#[derive(Debug, Deserialize)]
pub struct AuthInitializeRequest {
    pub email: String,
    pub password: String,
}

/// POST /api/auth/initialize 响应
#[derive(Debug, Serialize)]
pub struct AuthInitializeResponse {
    pub message: String,
}

/// GET /api/auth/info 响应
#[derive(Debug, Serialize)]
pub struct AuthInfoResponse {
    pub email: String,
}

/// POST /api/auth/unlock 请求
#[derive(Debug, Deserialize)]
pub struct AuthUnlockRequest {
    pub password: String,
}

/// POST /api/auth/unlock 响应
#[derive(Debug, Serialize)]
pub struct AuthUnlockResponse {
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub token: Option<String>,
}

/// GET /api/auth/status 响应
#[derive(Debug, Serialize)]
pub struct AuthStatusResponse {
    pub locked: bool,
}

/// POST /api/auth/session-timeout 请求
#[derive(Debug, Deserialize)]
pub struct AuthSessionTimeoutRequest {
    pub timeout: u64, // 分钟
}

/// POST /api/auth/session-timeout 响应
#[derive(Debug, Serialize)]
pub struct AuthSessionTimeoutResponse {
    pub message: String,
}

// ==================== 标签相关 ====================

/// 标签响应
#[derive(Debug, Serialize)]
pub struct TagResponse {
    pub id: i64,
    pub name: String,
    pub color: String,
    pub icon: String,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "updatedAt")]
    pub updated_at: DateTime<Utc>,
}

/// 标签列表响应
#[derive(Debug, Serialize)]
pub struct TagListResponse {
    pub data: Vec<TagResponse>,
    pub total: i64,
}

/// POST /api/tags 请求
#[derive(Debug, Deserialize)]
pub struct TagCreateRequest {
    pub name: String,
    pub color: Option<String>,
    pub icon: Option<String>,
}

/// PUT /api/tags/{id} 请求
#[derive(Debug, Deserialize)]
pub struct TagUpdateRequest {
    pub name: String,
    pub color: Option<String>,
    pub icon: Option<String>,
}

// ==================== 关联相关 ====================

/// 关联关系响应
#[derive(Debug, Serialize)]
pub struct RelationResponse {
    pub id: i64,
    pub name: String,
    pub value: Option<String>,
    #[serde(rename = "type")]
    pub r#type: String,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "updatedAt")]
    pub updated_at: DateTime<Utc>,
}

/// 关联关系列表响应
#[derive(Debug, Serialize)]
pub struct RelationListResponse {
    pub data: Vec<RelationResponse>,
    pub total: i64,
}

/// POST /api/relations 请求
#[derive(Debug, Deserialize)]
pub struct RelationCreateRequest {
    pub name: String,
    pub value: Option<String>,
    #[serde(rename = "type")]
    pub r#type: String,
}

/// PUT /api/relations/{id} 请求
#[derive(Debug, Deserialize)]
pub struct RelationUpdateRequest {
    pub name: String,
    pub value: Option<String>,
    #[serde(rename = "type")]
    pub r#type: String,
}

// ==================== 书签相关 ====================

/// URL 条目
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UrlEntryDto {
    pub url: String,
    #[serde(rename = "lastUsed", skip_serializing_if = "Option::is_none")]
    pub last_used: Option<DateTime<Utc>>,
}

/// 账户条目（解密后）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccountEntryDto {
    pub id: i64,
    pub username: String,
    pub password: String, // 解密后的明文密码
    #[serde(rename = "relatedIds")]
    pub related_ids: Vec<i64>,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "lastUsed")]
    pub last_used: DateTime<Utc>,
}

/// 书签响应
#[derive(Debug, Serialize)]
pub struct BookmarkResponse {
    pub id: String,
    pub name: String,
    #[serde(rename = "pinyinInitials")]
    pub pinyin_initials: String,
    #[serde(rename = "pinyinFull")]
    pub pinyin_full: String,
    #[serde(rename = "tagIds")]
    pub tag_ids: Vec<i64>,
    pub urls: Vec<UrlEntryDto>,
    pub notes: String,
    pub accounts: Vec<AccountEntryDto>,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "updatedAt")]
    pub updated_at: DateTime<Utc>,
    #[serde(rename = "lastUsedAt")]
    pub last_used_at: DateTime<Utc>,
}

/// 书签列表响应
#[derive(Debug, Serialize)]
pub struct BookmarkListResponse {
    pub data: Vec<BookmarkResponse>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

/// 创建账户条目（无 id）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccountCreateDto {
    pub username: String,
    pub password: String,
    #[serde(rename = "relatedIds", default)]
    pub related_ids: Vec<i64>,
}

/// POST /api/bookmarks 请求
#[derive(Debug, Deserialize)]
pub struct BookmarkCreateRequest {
    pub name: String,
    #[serde(rename = "tagIds")]
    pub tag_ids: Option<Vec<i64>>,
    pub urls: Option<Vec<UrlEntryDto>>,
    pub notes: Option<String>,
    pub accounts: Option<Vec<AccountCreateDto>>,
}

/// PUT /api/bookmarks/{id} 请求
#[derive(Debug, Deserialize)]
pub struct BookmarkUpdateRequest {
    pub name: String,
    #[serde(rename = "tagIds")]
    pub tag_ids: Option<Vec<i64>>,
    pub urls: Option<Vec<UrlEntryDto>>,
    pub notes: Option<String>,
    pub accounts: Option<Vec<AccountCreateDto>>,
}

/// POST /api/bookmarks/{id}/use 请求
#[derive(Debug, Deserialize)]
pub struct BookmarkUseRequest {
    pub url: Option<String>,
    #[serde(rename = "accountId")]
    pub account_id: Option<i64>,
}

/// POST /api/bookmarks/{id}/use 响应
#[derive(Debug, Serialize)]
pub struct BookmarkUseResponse {
    pub message: String,
    #[serde(rename = "lastUsedAt")]
    pub last_used_at: DateTime<Utc>,
}

/// PATCH /api/bookmarks/{id} 请求
#[derive(Debug, Deserialize)]
pub struct BookmarkPatchRequest {
    pub name: Option<String>,
    #[serde(rename = "tagIds")]
    pub tag_ids: Option<Vec<i64>>,
    pub urls: Option<Vec<UrlEntryDto>>,
    pub notes: Option<String>,
    pub accounts: Option<Vec<AccountCreateDto>>,
}

// ==================== 统计相关 ====================

/// 标签计数
#[derive(Debug, Serialize)]
pub struct TagCount {
    #[serde(rename = "tagId")]
    pub tag_id: i64,
    #[serde(rename = "tagName")]
    pub tag_name: String,
    pub count: i64,
}

/// 最近使用书签
#[derive(Debug, Serialize)]
pub struct RecentBookmark {
    pub id: String,
    pub name: String,
    #[serde(rename = "lastUsedAt")]
    pub last_used_at: DateTime<Utc>,
}

/// GET /api/stats 响应
#[derive(Debug, Serialize)]
pub struct StatsResponse {
    #[serde(rename = "totalBookmarks")]
    pub total_bookmarks: i64,
    #[serde(rename = "totalTags")]
    pub total_tags: i64,
    #[serde(rename = "totalRelations")]
    pub total_relations: i64,
    #[serde(rename = "totalAccounts")]
    pub total_accounts: i64,
    #[serde(rename = "mostUsedTags")]
    pub most_used_tags: Vec<TagCount>,
    #[serde(rename = "recentlyUsed")]
    pub recently_used: Vec<RecentBookmark>,
}

// ==================== 数据库管理相关 ====================

/// 数据库信息响应
#[derive(Debug, Serialize)]
pub struct DatabaseInfoResponse {
    pub path: String,
    pub name: String,
}

/// GET /api/db/list 响应
#[derive(Debug, Serialize)]
pub struct DatabaseListResponse {
    pub databases: Vec<DatabaseInfoResponse>,
    pub current: Option<String>,
}

/// POST /api/db/add 请求
#[derive(Debug, Deserialize)]
pub struct DatabaseAddRequest {
    pub path: String,
}

/// POST /api/db/add 响应
#[derive(Debug, Serialize)]
pub struct DatabaseAddResponse {
    pub message: String,
    pub name: String,
}

/// POST /api/db/open 请求
#[derive(Debug, Deserialize)]
pub struct DatabaseOpenRequest {
    pub path: String,
}

/// POST /api/db/open 响应
#[derive(Debug, Serialize)]
pub struct DatabaseOpenResponse {
    pub message: String,
    pub name: String,
}

/// POST /api/db/create 请求
#[derive(Debug, Deserialize)]
pub struct DatabaseCreateRequest {
    pub path: String,
    pub email: String,
    pub password: String,
}

/// POST /api/db/create 响应
#[derive(Debug, Serialize)]
pub struct DatabaseCreateResponse {
    pub message: String,
    pub name: String,
}

/// POST /api/db/remove 请求
#[derive(Debug, Deserialize)]
pub struct DatabaseRemoveRequest {
    pub path: String,
}
