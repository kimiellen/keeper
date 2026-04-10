//! 导入导出 API
//!
//! 提供数据备份和恢复功能，支持 JSON 格式。
//! 导出时密码为明文，导入时自动加密明文密码。

use axum::{
    extract::{Extension, State},
    Json,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::{
    crypto::encryption::EncryptionService,
    crypto::kdf::verify_password,
    db::models::{AccountEntry, Authentication, UrlEntry},
    error::{AppError, Result},
    session::manager::Session,
    state::AppState,
    utils::pinyin::{compute_full_pinyin, compute_initials},
};

// ==================== 导出数据结构 ====================

/// 导出数据根结构
#[derive(Debug, Serialize, Deserialize)]
pub struct ExportData {
    pub version: String,
    #[serde(rename = "exportedAt")]
    pub exported_at: DateTime<Utc>,
    pub tags: Vec<ExportTag>,
    pub relations: Vec<ExportRelation>,
    pub bookmarks: Vec<ExportBookmark>,
}

/// 导出标签
#[derive(Debug, Serialize, Deserialize)]
pub struct ExportTag {
    pub id: i64,
    pub name: String,
    pub color: String,
    pub icon: String,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "updatedAt")]
    pub updated_at: DateTime<Utc>,
}

/// 导出关联关系
#[derive(Debug, Serialize, Deserialize)]
pub struct ExportRelation {
    pub id: i64,
    pub name: String,
    #[serde(rename = "type")]
    pub r#type: String,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "updatedAt")]
    pub updated_at: DateTime<Utc>,
}

/// 导出书签
#[derive(Debug, Serialize, Deserialize)]
pub struct ExportBookmark {
    pub id: String,
    pub name: String,
    #[serde(rename = "pinyinInitials")]
    pub pinyin_initials: String,
    #[serde(rename = "pinyinFull")]
    pub pinyin_full: String,
    #[serde(rename = "tagIds")]
    pub tag_ids: Vec<i64>,
    pub urls: Vec<ExportUrl>,
    pub notes: String,
    pub accounts: Vec<ExportAccount>,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "updatedAt")]
    pub updated_at: DateTime<Utc>,
    #[serde(rename = "lastUsedAt")]
    pub last_used_at: DateTime<Utc>,
}

/// 导出 URL
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExportUrl {
    pub url: String,
    #[serde(rename = "lastUsed", skip_serializing_if = "Option::is_none")]
    pub last_used: Option<DateTime<Utc>>,
}

/// 导出账户（密码为明文）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExportAccount {
    pub id: i64,
    pub username: String,
    pub password: String, // ⚠️ 明文密码
    #[serde(rename = "relatedIds")]
    pub related_ids: Vec<i64>,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "lastUsed")]
    pub last_used: DateTime<Utc>,
}

// ==================== 导入请求/响应 ====================

/// 导出请求（带密码认证）
#[derive(Debug, Deserialize)]
pub struct ExportRequest {
    pub password: String,  // 主密码验证
}

/// 导入请求（带密码认证）
#[derive(Debug, Deserialize)]
pub struct ImportRequest {
    pub password: String,              // 主密码验证
    pub data: ExportData,              // 导入的数据
    pub conflict_policy: Option<String>, // 冲突处理策略: skip/rename/overwrite
}

/// 导入统计
#[derive(Debug, Serialize)]
pub struct ImportCounts {
    pub tags: usize,
    pub relations: usize,
    pub bookmarks: usize,
}

/// 导入响应
#[derive(Debug, Serialize)]
pub struct ImportResponse {
    pub success: bool,
    pub imported: ImportCounts,
    pub errors: Vec<String>,
}

// ==================== 导出处理器 ====================

/// POST /api/export
///
/// 导出所有数据为 JSON 格式（密码解密为明文），需要主密码认证
pub async fn export_data(
    State(state): State<AppState>,
    Extension(session): Extension<Session>,
    Json(req): Json<ExportRequest>,
) -> Result<Json<ExportData>> {
    // 验证主密码
    let password_valid = tokio::task::spawn_blocking({
        let db = state.db.clone();
        let password = req.password.clone();
        move || {
            let conn = db.lock().unwrap();
            let auth: Authentication = conn
                .query_row(
                    "SELECT id, email, password_hash, created_at, last_login FROM authentication WHERE id = 1",
                    [],
                    |row| Authentication::from_row(row),
                )
                .map_err(|_| AppError::Auth("未初始化".to_string()))?;
            Ok::<bool, AppError>(verify_password(&password, &auth.password_hash))
        }
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Auth(format!("密码验证失败: {}", e)))?;

    if !password_valid {
        return Err(AppError::Auth("密码错误".to_string()));
    }

    // 导出标签
    let tags = export_tags(&state).await?;

    // 导出关联关系
    let relations = export_relations(&state).await?;

    // 导出书签（解密密码）
    let bookmarks = export_bookmarks(&state, &session.encryption_key).await?;

    Ok(Json(ExportData {
        version: "keeper-1.0".to_string(),
        exported_at: Utc::now(),
        tags,
        relations,
        bookmarks,
    }))
}

/// 导出所有标签
async fn export_tags(state: &AppState) -> Result<Vec<ExportTag>> {
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT * FROM tags ORDER BY id")?;
        let mut rows = stmt.query([])?;
        let mut tags = Vec::new();
        
        while let Some(row) = rows.next()? {
            tags.push(ExportTag {
                id: row.get("id")?,
                name: row.get("name")?,
                color: row.get("color")?,
                icon: row.get("icon")?,
                created_at: row.get("created_at")?,
                updated_at: row.get("updated_at")?,
            });
        }
        Ok::<Vec<ExportTag>, rusqlite::Error>(tags)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))
}

/// 导出所有关联关系
async fn export_relations(state: &AppState) -> Result<Vec<ExportRelation>> {
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT * FROM relations ORDER BY id")?;
        let mut rows = stmt.query([])?;
        let mut relations = Vec::new();
        
        while let Some(row) = rows.next()? {
            let type_str: String = row.get("type")?;
            relations.push(ExportRelation {
                id: row.get("id")?,
                name: row.get("name")?,
                r#type: type_str,
                created_at: row.get("created_at")?,
                updated_at: row.get("updated_at")?,
            });
        }
        Ok::<Vec<ExportRelation>, rusqlite::Error>(relations)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))
}

/// 书签查询结果类型
struct BookmarkRow {
    id: String,
    name: String,
    pinyin_initials: String,
    pinyin_full: String,
    tag_ids_json: String,
    urls_json: String,
    accounts_json: String,
    notes: String,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
    last_used_at: DateTime<Utc>,
}

/// 导出所有书签（解密密码）
async fn export_bookmarks(state: &AppState, key: &[u8; 32]) -> Result<Vec<ExportBookmark>> {
    let encryption_service = EncryptionService::new(key);

    let db = state.db.clone();
    let bookmarks: Vec<BookmarkRow> = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT * FROM bookmarks ORDER BY id")?;
        let mut rows = stmt.query([])?;
        let mut bookmarks = Vec::new();
        
        while let Some(row) = rows.next()? {
            bookmarks.push(BookmarkRow {
                id: row.get("id")?,
                name: row.get("name")?,
                pinyin_initials: row.get("pinyin_initials")?,
                pinyin_full: row.get("pinyin_full")?,
                tag_ids_json: row.get("tag_ids")?,
                urls_json: row.get("urls")?,
                accounts_json: row.get("accounts")?,
                notes: row.get("notes")?,
                created_at: row.get("created_at")?,
                updated_at: row.get("updated_at")?,
                last_used_at: row.get("last_used_at")?,
            });
        }
        Ok::<Vec<BookmarkRow>, rusqlite::Error>(bookmarks)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    // 处理并解密密码
    let export_bookmarks: Vec<ExportBookmark> = bookmarks
        .into_iter()
        .map(|bm| {
            // 解析标签 ID
            let tag_ids: Vec<i64> =
                serde_json::from_str(&bm.tag_ids_json).unwrap_or_default();

            // 解析 URL
            let urls: Vec<UrlEntry> =
                serde_json::from_str(&bm.urls_json).unwrap_or_default();
            let export_urls: Vec<ExportUrl> = urls
                .into_iter()
                .map(|u| ExportUrl {
                    url: u.url,
                    last_used: u.last_used,
                })
                .collect();

            // 解析并解密账户
            let accounts: Vec<AccountEntry> =
                serde_json::from_str(&bm.accounts_json).unwrap_or_default();
            let export_accounts: Vec<ExportAccount> = accounts
                .into_iter()
                .map(|acc| {
                    let password = if acc.password.starts_with("v1.") {
                        // 解密密码
                        encryption_service
                            .decrypt(&acc.password)
                            .unwrap_or_else(|_| "[解密失败]".to_string())
                    } else {
                        acc.password // 已经是明文
                    };

                    ExportAccount {
                        id: acc.id,
                        username: acc.username,
                        password,
                        related_ids: acc.related_ids,
                        created_at: acc.created_at,
                        last_used: acc.last_used,
                    }
                })
                .collect();

            ExportBookmark {
                id: bm.id,
                name: bm.name,
                pinyin_initials: bm.pinyin_initials,
                pinyin_full: bm.pinyin_full,
                tag_ids,
                urls: export_urls,
                notes: bm.notes,
                accounts: export_accounts,
                created_at: bm.created_at,
                updated_at: bm.updated_at,
                last_used_at: bm.last_used_at,
            }
        })
        .collect();

    Ok(export_bookmarks)
}

// ==================== 导入处理器 ====================

/// POST /api/import
///
/// 从 JSON 导入数据，自动加密明文密码，需要主密码认证
pub async fn import_data(
    State(state): State<AppState>,
    Extension(session): Extension<Session>,
    Json(req): Json<ImportRequest>,
) -> Result<Json<ImportResponse>> {
    // 验证主密码
    let password_valid = tokio::task::spawn_blocking({
        let db = state.db.clone();
        let password = req.password.clone();
        move || {
            let conn = db.lock().unwrap();
            let auth: Authentication = conn
                .query_row(
                    "SELECT id, email, password_hash, created_at, last_login FROM authentication WHERE id = 1",
                    [],
                    |row| Authentication::from_row(row),
                )
                .map_err(|_| AppError::Auth("未初始化".to_string()))?;
            Ok::<bool, AppError>(verify_password(&password, &auth.password_hash))
        }
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Auth(format!("密码验证失败: {}", e)))?;

    if !password_valid {
        return Err(AppError::Auth("密码错误".to_string()));
    }

    let mut counts = ImportCounts {
        tags: 0,
        relations: 0,
        bookmarks: 0,
    };
    let mut errors = Vec::new();

    // 导入标签
    for tag in req.data.tags {
        let tag_name = tag.name.clone();
        match import_tag(&state, tag).await {
            Ok(_) => counts.tags += 1,
            Err(e) if is_duplicate_error(&e) => {
                // 忽略重复标签
            }
            Err(e) => errors.push(format!("标签 '{}': {}", tag_name, e)),
        }
    }

    // 导入关联关系
    for relation in req.data.relations {
        let relation_name = relation.name.clone();
        match import_relation(&state, relation).await {
            Ok(_) => counts.relations += 1,
            Err(e) if is_duplicate_error(&e) => {
                // 忽略重复关联
            }
            Err(e) => errors.push(format!("关联 '{}': {}", relation_name, e)),
        }
    }

    // 导入书签（加密密码）
    let conflict_policy = req.conflict_policy.as_deref().unwrap_or("skip");
    for bookmark in req.data.bookmarks {
        let bookmark_name = bookmark.name.clone();
        match import_bookmark(&state, &session.encryption_key, bookmark, conflict_policy).await {
            Ok(_) => counts.bookmarks += 1,
            Err(e) if e.to_string().contains("跳过") => {
                // 跳过冲突的书签，不计入错误
            }
            Err(e) => errors.push(format!("书签 '{}': {}", bookmark_name, e)),
        }
    }

    Ok(Json(ImportResponse {
        success: errors.is_empty(),
        imported: counts,
        errors,
    }))
}

/// 导入单个标签
async fn import_tag(state: &AppState, tag: ExportTag) -> Result<()> {
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            "INSERT INTO tags (id, name, color, icon, created_at, updated_at) 
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            [
                &tag.id.to_string(),
                &tag.name,
                &tag.color,
                &tag.icon,
                &tag.created_at.to_rfc3339(),
                &tag.updated_at.to_rfc3339(),
            ],
        )?;
        Ok::<(), rusqlite::Error>(())
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))
}

/// 导入单个关联关系
async fn import_relation(state: &AppState, relation: ExportRelation) -> Result<()> {
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            "INSERT INTO relations (id, name, type, created_at, updated_at) 
             VALUES (?1, ?2, ?3, ?4, ?5)",
            [
                &relation.id.to_string(),
                &relation.name,
                &relation.r#type,
                &relation.created_at.to_rfc3339(),
                &relation.updated_at.to_rfc3339(),
            ],
        )?;
        Ok::<(), rusqlite::Error>(())
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))
}

/// 导入单个书签（加密明文密码）
async fn import_bookmark(
    state: &AppState,
    key: &[u8; 32],
    bookmark: ExportBookmark,
    conflict_policy: &str,
) -> Result<()> {
    let encryption_service = EncryptionService::new(key);

    // 检查书签名称是否已存在
    let bookmark_name = bookmark.name.clone();
    let db = state.db.clone();
    let existing_id: Option<String> = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let result: std::result::Result<String, rusqlite::Error> = conn.query_row(
            "SELECT id FROM bookmarks WHERE name = ?",
            [&bookmark_name],
            |row| row.get(0),
        );
        Ok::<Option<String>, rusqlite::Error>(result.ok())
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    // 根据冲突处理策略处理
    if let Some(existing_id) = existing_id {
        match conflict_policy {
            "skip" => {
                return Err(AppError::BadRequest(format!("书签 '{}' 已存在，跳过", bookmark.name)));
            }
            "overwrite" => {
                // 删除旧书签
                let db = state.db.clone();
                let id_clone = existing_id.clone();
                tokio::task::spawn_blocking(move || {
                    let conn = db.lock().unwrap();
                    conn.execute("DELETE FROM bookmarks WHERE id = ?", [&id_clone])
                }).await
                .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
                .map_err(|e| AppError::Internal(format!("删除旧书签失败: {}", e)))?;
            }
            "rename" | _ => {
                // 重命名：在名称后添加数字后缀
                let mut counter = 1;
                let new_name;
                loop {
                    let candidate = format!("{} ({})", bookmark.name, counter);
                    let db = state.db.clone();
                    let exists: bool = tokio::task::spawn_blocking({
                        let candidate = candidate.clone();
                        move || {
                            let conn = db.lock().unwrap();
                            let count: i64 = conn.query_row(
                                "SELECT COUNT(*) FROM bookmarks WHERE name = ?",
                                [&candidate],
                                |row| row.get(0),
                            ).unwrap_or(0);
                            Ok::<bool, rusqlite::Error>(count > 0)
                        }
                    }).await
                    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
                    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;
                    
                    if !exists {
                        new_name = candidate;
                        break;
                    }
                    counter += 1;
                }
                // 使用新的名称继续导入
                return import_bookmark_with_name(state, key, bookmark, &new_name).await;
            }
        }
    }

    // 重新计算拼音（确保与当前名称匹配）
    let pinyin_initials = compute_initials(&bookmark.name);
    let pinyin_full = compute_full_pinyin(&bookmark.name);

    // 加密账户密码
    let encrypted_accounts: Vec<AccountEntry> = bookmark
        .accounts
        .into_iter()
        .map(|acc| {
            // 如果密码不是加密格式，则加密
            let encrypted_password = if acc.password.starts_with("v1.") {
                acc.password // 已经是加密格式
            } else {
                // 需要加密
                encryption_service
                    .encrypt(&acc.password)
                    .unwrap_or_else(|_| acc.password)
            };

            AccountEntry {
                id: acc.id,
                username: acc.username,
                password: encrypted_password,
                related_ids: acc.related_ids,
                created_at: acc.created_at,
                last_used: acc.last_used,
            }
        })
        .collect();

    // 转换 URL
    let urls: Vec<UrlEntry> = bookmark
        .urls
        .into_iter()
        .map(|u| UrlEntry {
            url: u.url,
            last_used: u.last_used,
        })
        .collect();

    // 序列化 JSON 字段
    let tag_ids_json = serde_json::to_string(&bookmark.tag_ids).unwrap_or_default();
    let urls_json = serde_json::to_string(&urls).unwrap_or_default();
    let accounts_json = serde_json::to_string(&encrypted_accounts).unwrap_or_default();

    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            "INSERT INTO bookmarks 
             (id, name, pinyin_initials, pinyin_full, tag_ids, urls, notes, accounts, created_at, updated_at, last_used_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
            [
                &bookmark.id,
                &bookmark.name,
                &pinyin_initials,
                &pinyin_full,
                &tag_ids_json,
                &urls_json,
                &bookmark.notes,
                &accounts_json,
                &bookmark.created_at.to_rfc3339(),
                &bookmark.updated_at.to_rfc3339(),
                &bookmark.last_used_at.to_rfc3339(),
            ],
        )?;
        Ok::<(), rusqlite::Error>(())
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))
}

/// 导入书签（使用指定名称，用于重命名冲突处理）
async fn import_bookmark_with_name(
    state: &AppState,
    key: &[u8; 32],
    bookmark: ExportBookmark,
    new_name: &str,
) -> Result<()> {
    let encryption_service = EncryptionService::new(key);

    // 重新计算拼音（使用新名称）
    let pinyin_initials = compute_initials(new_name);
    let pinyin_full = compute_full_pinyin(new_name);

    // 加密账户密码
    let encrypted_accounts: Vec<AccountEntry> = bookmark
        .accounts
        .into_iter()
        .map(|acc| {
            let encrypted_password = if acc.password.starts_with("v1.") {
                acc.password
            } else {
                encryption_service
                    .encrypt(&acc.password)
                    .unwrap_or_else(|_| acc.password)
            };

            AccountEntry {
                id: acc.id,
                username: acc.username,
                password: encrypted_password,
                related_ids: acc.related_ids,
                created_at: acc.created_at,
                last_used: acc.last_used,
            }
        })
        .collect();

    // 转换 URL
    let urls: Vec<UrlEntry> = bookmark
        .urls
        .into_iter()
        .map(|u| UrlEntry {
            url: u.url,
            last_used: u.last_used,
        })
        .collect();

    // 序列化 JSON 字段
    let tag_ids_json = serde_json::to_string(&bookmark.tag_ids).unwrap_or_default();
    let urls_json = serde_json::to_string(&urls).unwrap_or_default();
    let accounts_json = serde_json::to_string(&encrypted_accounts).unwrap_or_default();

    let new_name = new_name.to_string();
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            "INSERT INTO bookmarks 
             (id, name, pinyin_initials, pinyin_full, tag_ids, urls, notes, accounts, created_at, updated_at, last_used_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
            [
                &bookmark.id,
                &new_name,
                &pinyin_initials,
                &pinyin_full,
                &tag_ids_json,
                &urls_json,
                &bookmark.notes,
                &accounts_json,
                &bookmark.created_at.to_rfc3339(),
                &bookmark.updated_at.to_rfc3339(),
                &bookmark.last_used_at.to_rfc3339(),
            ],
        )?;
        Ok::<(), rusqlite::Error>(())
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))
}

/// 检查错误是否为重复键错误
fn is_duplicate_error(e: &AppError) -> bool {
    e.to_string().to_lowercase().contains("duplicate")
        || e.to_string().to_lowercase().contains("unique")
}

// ==================== 测试 ====================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_export_data_structure() {
        // 验证导出数据结构序列化
        let data = ExportData {
            version: "keeper-1.0".to_string(),
            exported_at: Utc::now(),
            tags: vec![],
            relations: vec![],
            bookmarks: vec![],
        };

        let json = serde_json::to_string(&data).unwrap();
        assert!(json.contains("keeper-1.0"));
        assert!(json.contains("exportedAt"));
    }

    #[test]
    fn test_is_duplicate_error() {
        assert!(is_duplicate_error(&AppError::Internal(
            "UNIQUE constraint failed".to_string()
        )));
        assert!(is_duplicate_error(&AppError::Internal(
            "duplicate key value".to_string()
        )));
        assert!(!is_duplicate_error(&AppError::Internal(
            "some other error".to_string()
        )));
    }
}
