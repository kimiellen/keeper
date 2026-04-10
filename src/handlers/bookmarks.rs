//! 书签 API 处理器

use axum::{
    extract::{Extension, Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use chrono::Utc;
use rusqlite::params;
use serde::Deserialize;
use uuid::Uuid;

use crate::{
    crypto::encryption::EncryptionService,
    db::models::{AccountEntry, Bookmark},
    error::{AppError, Result},
    handlers::schemas::{
        AccountEntryDto, BookmarkCreateRequest, BookmarkListResponse, BookmarkPatchRequest,
        BookmarkResponse, BookmarkUpdateRequest, BookmarkUseRequest, BookmarkUseResponse,
        UrlEntryDto,
    },
    session::manager::Session,
    state::AppState,
    utils::pinyin::{compute_full_pinyin, compute_initials},
};

/// 书签列表查询参数
#[derive(Debug, Deserialize)]
pub struct ListBookmarksQuery {
    #[serde(default = "default_limit")]
    limit: i64,
    #[serde(default = "default_offset")]
    offset: i64,
}

/// 单个书签查询参数
#[derive(Debug, Deserialize)]
pub struct GetBookmarkQuery {
    /// 是否解密密码，默认 true（保持向后兼容）
    #[serde(default = "default_decrypt")]
    decrypt: bool,
}

fn default_limit() -> i64 {
    50
}

fn default_offset() -> i64 {
    0
}

fn default_decrypt() -> bool {
    true
}

/// GET /api/bookmarks
///
/// 获取书签列表，支持分页。
pub async fn list_bookmarks(
    State(state): State<AppState>,
    Extension(session): Extension<Session>,
    axum::extract::Query(query): axum::extract::Query<ListBookmarksQuery>,
) -> Result<Json<BookmarkListResponse>> {
    let db = state.db.clone();
    let limit = query.limit;
    let offset = query.offset;
    
    let bookmarks: Vec<Bookmark> = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn
            .prepare("SELECT * FROM bookmarks ORDER BY created_at DESC LIMIT ? OFFSET ?")
            .unwrap();
        let bookmark_iter = stmt
            .query_map([limit, offset], |row| Bookmark::from_row(row))
            .unwrap();

        let mut result = Vec::new();
        for bookmark in bookmark_iter {
            result.push(bookmark.unwrap());
        }
        Ok::<Vec<Bookmark>, rusqlite::Error>(result)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    // 获取总数
    let db = state.db.clone();
    let total: i64 = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.query_row("SELECT COUNT(*) FROM bookmarks", [], |row| row.get(0))
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    // 创建加密服务，列表查询不解密密码（返回加密格式 v1.xxx...）
    let encryption_service = EncryptionService::new(&session.encryption_key);
    let data: Vec<BookmarkResponse> = bookmarks
        .into_iter()
        .map(|bm| bookmark_to_response(bm, &encryption_service, false))
        .collect();

    Ok(Json(BookmarkListResponse {
        data,
        total,
        limit: query.limit,
        offset: query.offset,
    }))
}

/// GET /api/bookmarks/{id}
///
/// 获取单个书签。支持 decrypt 参数控制是否解密密码。
/// 
/// # Query Parameters
/// * `decrypt` - 是否解密密码，默认 true。false 则返回加密格式 "v1.xxx..."
pub async fn get_bookmark(
    State(state): State<AppState>,
    Extension(session): Extension<Session>,
    Path(bookmark_id): Path<String>,
    axum::extract::Query(query): axum::extract::Query<GetBookmarkQuery>,
) -> Result<Json<BookmarkResponse>> {
    let db = state.db.clone();
    let bookmark = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT * FROM bookmarks WHERE id = ?").unwrap();
        stmt.query_row([&bookmark_id], |row| Bookmark::from_row(row))
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|_| AppError::NotFound("书签不存在".to_string()))?;

    // 根据查询参数决定是否解密密码
    let encryption_service = EncryptionService::new(&session.encryption_key);
    Ok(Json(bookmark_to_response(bookmark, &encryption_service, query.decrypt)))
}

/// POST /api/bookmarks
///
/// 创建新书签。
pub async fn create_bookmark(
    State(state): State<AppState>,
    Extension(session): Extension<Session>,
    Json(req): Json<BookmarkCreateRequest>,
) -> Result<impl IntoResponse> {
    // 验证名称
    if req.name.is_empty() {
        return Err(AppError::BadRequest("书签名称不能为空".to_string()));
    }

    let id = Uuid::new_v4().to_string();
    let notes = req.notes.unwrap_or_default();
    let pinyin_initials = compute_initials(&req.name) + &compute_initials(&notes);
    let pinyin_full = compute_full_pinyin(&req.name) + &compute_full_pinyin(&notes);
    let now = Utc::now();

    let tag_ids = req.tag_ids.unwrap_or_default();
    let urls = req.urls.unwrap_or_default();
    
    // 创建加密服务
    let encryption_service = EncryptionService::new(&session.encryption_key);
    
    // 转换 accounts 并分配 id，加密密码
    let accounts: Vec<AccountEntry> = req.accounts
        .unwrap_or_default()
        .into_iter()
        .enumerate()
        .map(|(idx, a)| {
            // 如果密码不是加密格式，则加密
            let encrypted_password = if a.password.starts_with("v1.") {
                a.password  // 已经是加密格式
            } else {
                encryption_service
                    .encrypt(&a.password)
                    .unwrap_or_else(|_| a.password)
            };
            
            AccountEntry {
                id: (idx + 1) as i64,
                username: a.username,
                password: encrypted_password,
                related_ids: a.related_ids,
                created_at: now,
                last_used: now,
            }
        })
        .collect();

    // 序列化 JSON 字段
    let tag_ids_json = serde_json::to_string(&tag_ids).unwrap_or_else(|_| "[]".to_string());
    let urls_json = serde_json::to_string(&urls).unwrap_or_else(|_| "[]".to_string());
    let accounts_json = serde_json::to_string(&accounts).unwrap_or_else(|_| "[]".to_string());

    let id_clone = id.clone();
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            r#"INSERT INTO bookmarks 
                (id, name, pinyin_initials, pinyin_full, tag_ids, urls, notes, accounts, created_at, updated_at, last_used_at) 
                VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)"#,
            params![
                id_clone,
                req.name,
                pinyin_initials,
                pinyin_full,
                tag_ids_json,
                urls_json,
                notes,
                accounts_json,
                now,
                now,
                now,
            ],
        )
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("创建书签失败: {}", e)))?;

    // 获取刚创建的书签
    let db = state.db.clone();
    let bookmark = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT * FROM bookmarks WHERE id = ?").unwrap();
        stmt.query_row([&id], |row| Bookmark::from_row(row))
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("查询书签失败: {}", e)))?;

    // 解密密码后返回（创建后需要显示明文密码给用户）
    let encryption_service = EncryptionService::new(&session.encryption_key);
    Ok((StatusCode::CREATED, Json(bookmark_to_response(bookmark, &encryption_service, true))))
}

/// PUT /api/bookmarks/{id}
///
/// 完整更新书签。
pub async fn update_bookmark(
    State(state): State<AppState>,
    Extension(session): Extension<Session>,
    Path(bookmark_id): Path<String>,
    Json(req): Json<BookmarkUpdateRequest>,
) -> Result<Json<BookmarkResponse>> {
    // 验证名称
    if req.name.is_empty() {
        return Err(AppError::BadRequest("书签名称不能为空".to_string()));
    }

    // 检查书签是否存在
    let bookmark_id_clone = bookmark_id.clone();
    let db = state.db.clone();
    let exists: bool = tokio::task::block_in_place(move || {
        let conn = db.lock().unwrap();
        let count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM bookmarks WHERE id = ?",
                [&bookmark_id_clone],
                |row| row.get(0),
            )
            .unwrap();
        count > 0
    });

    if !exists {
        return Err(AppError::NotFound("书签不存在".to_string()));
    }

    let notes = req.notes.unwrap_or_default();
    let pinyin_initials = compute_initials(&req.name) + &compute_initials(&notes);
    let pinyin_full = compute_full_pinyin(&req.name) + &compute_full_pinyin(&notes);
    let now = Utc::now();

    let tag_ids = req.tag_ids.unwrap_or_default();
    let urls = req.urls.unwrap_or_default();
    
    // 创建加密服务
    let encryption_service = EncryptionService::new(&session.encryption_key);
    
    // 转换 accounts 并分配 id，加密密码
    let accounts: Vec<AccountEntry> = req.accounts
        .unwrap_or_default()
        .into_iter()
        .enumerate()
        .map(|(idx, a)| {
            // 如果密码不是加密格式，则加密
            let encrypted_password = if a.password.starts_with("v1.") {
                a.password  // 已经是加密格式
            } else {
                encryption_service
                    .encrypt(&a.password)
                    .unwrap_or_else(|_| a.password)
            };
            
            AccountEntry {
                id: (idx + 1) as i64,
                username: a.username,
                password: encrypted_password,
                related_ids: a.related_ids,
                created_at: now,
                last_used: now,
            }
        })
        .collect();

    // 序列化 JSON 字段
    let tag_ids_json = serde_json::to_string(&tag_ids).unwrap_or_else(|_| "[]".to_string());
    let urls_json = serde_json::to_string(&urls).unwrap_or_else(|_| "[]".to_string());
    let accounts_json = serde_json::to_string(&accounts).unwrap_or_else(|_| "[]".to_string());

    let bookmark_id_clone = bookmark_id.clone();
    let db = state.db.clone();
    let rows_affected = tokio::task::block_in_place(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            r#"UPDATE bookmarks SET 
                name = ?1, 
                pinyin_initials = ?2, 
                pinyin_full = ?3, 
                tag_ids = ?4, 
                urls = ?5, 
                notes = ?6, 
                accounts = ?7, 
                updated_at = ?8 
             WHERE id = ?9"#,
            params![
                req.name,
                pinyin_initials,
                pinyin_full,
                tag_ids_json,
                urls_json,
                notes,
                accounts_json,
                now,
                bookmark_id_clone,
            ],
        ).unwrap()
    });
    
    tracing::info!("更新书签 {} 成功，影响 {} 行", bookmark_id, rows_affected);

    // 获取更新后的书签
    let db = state.db.clone();
    let bookmark = tokio::task::block_in_place(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT * FROM bookmarks WHERE id = ?").unwrap();
        stmt.query_row([&bookmark_id], |row| Bookmark::from_row(row)).unwrap()
    });

    // 解密密码后返回（更新后需要显示明文密码给用户）
    let encryption_service = EncryptionService::new(&session.encryption_key);
    Ok(Json(bookmark_to_response(bookmark, &encryption_service, true)))
}

/// PATCH /api/bookmarks/{id}
///
/// 部分更新书签。
pub async fn patch_bookmark(
    State(state): State<AppState>,
    Extension(session): Extension<Session>,
    Path(bookmark_id): Path<String>,
    Json(req): Json<BookmarkPatchRequest>,
) -> Result<Json<BookmarkResponse>> {
    // 获取现有书签
    let bookmark_id_clone = bookmark_id.clone();
    let db = state.db.clone();
    let existing = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT * FROM bookmarks WHERE id = ?").unwrap();
        stmt.query_row([&bookmark_id_clone], |row| Bookmark::from_row(row))
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|_| AppError::NotFound("书签不存在".to_string()))?;

    // 确定更新值
    let name = req.name.unwrap_or(existing.name);
    let notes = req.notes.unwrap_or(existing.notes);
    let pinyin_initials = compute_initials(&name) + &compute_initials(&notes);
    let pinyin_full = compute_full_pinyin(&name) + &compute_full_pinyin(&notes);
    let now = Utc::now();

    let tag_ids = req.tag_ids.unwrap_or(existing.tag_ids);

    // 转换 urls: 如果请求中有则用请求的，否则用现有的
    let urls: Vec<UrlEntryDto> = req.urls.unwrap_or_else(|| {
        existing
            .urls
            .into_iter()
            .map(|u| UrlEntryDto {
                url: u.url,
                last_used: u.last_used,
            })
            .collect()
    });

    // 创建加密服务
    let encryption_service = EncryptionService::new(&session.encryption_key);

    // 转换 accounts: 如果请求中有则用请求的（分配新id，加密密码），否则用现有的
    let accounts: Vec<AccountEntry> = if let Some(req_accounts) = req.accounts {
        req_accounts
            .into_iter()
            .enumerate()
            .map(|(idx, a)| {
                // 如果密码不是加密格式，则加密
                let encrypted_password = if a.password.starts_with("v1.") {
                    a.password  // 已经是加密格式
                } else {
                    encryption_service
                        .encrypt(&a.password)
                        .unwrap_or_else(|_| a.password)
                };
                
                AccountEntry {
                    id: (idx + 1) as i64,
                    username: a.username,
                    password: encrypted_password,
                    related_ids: a.related_ids,
                    created_at: now,
                    last_used: now,
                }
            })
            .collect()
    } else {
        existing.accounts
    };

    // 序列化 JSON 字段
    let tag_ids_json = serde_json::to_string(&tag_ids).unwrap_or_else(|_| "[]".to_string());
    let urls_json = serde_json::to_string(&urls).unwrap_or_else(|_| "[]".to_string());
    let accounts_json = serde_json::to_string(&accounts).unwrap_or_else(|_| "[]".to_string());

    let bookmark_id_clone = bookmark_id.clone();
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            r#"UPDATE bookmarks SET 
                name = ?1, 
                pinyin_initials = ?2, 
                pinyin_full = ?3, 
                tag_ids = ?4, 
                urls = ?5, 
                notes = ?6, 
                accounts = ?7, 
                updated_at = ?8 
             WHERE id = ?9"#,
            params![
                name,
                pinyin_initials,
                pinyin_full,
                tag_ids_json,
                urls_json,
                notes,
                accounts_json,
                now,
                bookmark_id_clone,
            ],
        )
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("更新书签失败: {}", e)))?;

    // 获取更新后的书签
    let db = state.db.clone();
    let bookmark = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT * FROM bookmarks WHERE id = ?").unwrap();
        stmt.query_row([&bookmark_id], |row| Bookmark::from_row(row))
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|_| AppError::NotFound("书签不存在".to_string()))?;

    // 解密密码后返回（更新后需要显示明文密码给用户）
    let encryption_service = EncryptionService::new(&session.encryption_key);
    Ok(Json(bookmark_to_response(bookmark, &encryption_service, true)))
}

/// DELETE /api/bookmarks/{id}
///
/// 删除书签。
pub async fn delete_bookmark(
    State(state): State<AppState>,
    Path(bookmark_id): Path<String>,
) -> Result<StatusCode> {
    // 检查书签是否存在
    let bookmark_id_clone = bookmark_id.clone();
    let db = state.db.clone();
    let exists: bool = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM bookmarks WHERE id = ?",
                [&bookmark_id_clone],
                |row| row.get(0),
            )
            .unwrap();
        Ok::<bool, rusqlite::Error>(count > 0)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    if !exists {
        return Err(AppError::NotFound("书签不存在".to_string()));
    }

    // 删除书签
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute("DELETE FROM bookmarks WHERE id = ?", [&bookmark_id])
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("删除书签失败: {}", e)))?;

    Ok(StatusCode::NO_CONTENT)
}

/// POST /api/bookmarks/{id}/use
///
/// 更新书签使用时间。
pub async fn use_bookmark(
    State(state): State<AppState>,
    Path(bookmark_id): Path<String>,
    Json(_req): Json<BookmarkUseRequest>,
) -> Result<Json<BookmarkUseResponse>> {
    // 检查书签是否存在
    let bookmark_id_clone = bookmark_id.clone();
    let db = state.db.clone();
    let exists: bool = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM bookmarks WHERE id = ?",
                [&bookmark_id_clone],
                |row| row.get(0),
            )
            .unwrap();
        Ok::<bool, rusqlite::Error>(count > 0)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    if !exists {
        return Err(AppError::NotFound("书签不存在".to_string()));
    }

    let now = Utc::now();
    let now_str = now.to_rfc3339();

    // 更新时间
    let bookmark_id_clone = bookmark_id.clone();
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            "UPDATE bookmarks SET last_used_at = ? WHERE id = ?",
            [&now_str, &bookmark_id_clone],
        )
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("更新时间失败: {}", e)))?;

    Ok(Json(BookmarkUseResponse {
        message: "更新使用时间成功".to_string(),
        last_used_at: now,
    }))
}

/// 将 Bookmark 转换为 BookmarkResponse
/// 
/// # Arguments
/// * `bookmark` - 数据库书签模型
/// * `encryption_service` - 加密服务
/// * `decrypt` - 是否解密密码，false 则返回加密格式 "v1.xxx..."
fn bookmark_to_response(bookmark: Bookmark, encryption_service: &EncryptionService, decrypt: bool) -> BookmarkResponse {
    BookmarkResponse {
        id: bookmark.id,
        name: bookmark.name,
        pinyin_initials: bookmark.pinyin_initials,
        pinyin_full: bookmark.pinyin_full,
        tag_ids: bookmark.tag_ids,
        urls: bookmark
            .urls
            .into_iter()
            .map(|u| UrlEntryDto {
                url: u.url,
                last_used: u.last_used,
            })
            .collect(),
        notes: bookmark.notes,
        accounts: bookmark
            .accounts
            .into_iter()
            .map(|a| {
                // 根据 decrypt 参数决定是否解密密码
                let password = if decrypt {
                    // 如果密码是加密格式，则解密
                    if a.password.starts_with("v1.") {
                        encryption_service
                            .decrypt(&a.password)
                            .unwrap_or_else(|_| a.password)
                    } else {
                        // 向后兼容：明文密码直接返回
                        a.password
                    }
                } else {
                    // 不解密，返回原始值（加密格式或明文）
                    a.password
                };
                
                AccountEntryDto {
                    id: a.id,
                    username: a.username,
                    password,
                    related_ids: a.related_ids,
                    created_at: a.created_at,
                    last_used: a.last_used,
                }
            })
            .collect(),
        created_at: bookmark.created_at,
        updated_at: bookmark.updated_at,
        last_used_at: bookmark.last_used_at,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_pagination() {
        assert_eq!(default_limit(), 50);
        assert_eq!(default_offset(), 0);
    }
}
