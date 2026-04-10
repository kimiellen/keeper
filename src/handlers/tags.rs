//! 标签 API 处理器

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use chrono::Utc;
use rusqlite::params;
use serde::Deserialize;

use crate::{
    db::models::Tag,
    error::{AppError, Result},
    handlers::schemas::{
        TagCreateRequest, TagListResponse, TagResponse, TagUpdateRequest,
    },
    state::AppState,
};

/// 10 种亮色系标签颜色，按创建顺序循环分配
const TAG_COLORS: &[&str] = &[
    "#3B82F6", // 蓝
    "#10B981", // 翠绿
    "#F59E0B", // 琥珀
    "#EF4444", // 红
    "#8B5CF6", // 紫
    "#EC4899", // 粉
    "#06B6D4", // 青
    "#F97316", // 橙
    "#14B8A6", // 蓝绿
    "#6366F1", // 靛蓝
];

/// 标签列表查询参数
#[derive(Debug, Deserialize)]
pub struct ListTagsQuery {
    #[serde(default = "default_sort")]
    sort: String,
}

fn default_sort() -> String {
    "name".to_string()
}

/// GET /api/tags
///
/// 获取标签列表，支持排序。
pub async fn list_tags(
    State(state): State<AppState>,
    Query(query): Query<ListTagsQuery>,
) -> Result<Json<TagListResponse>> {
    let sort = query.sort.clone();
    
    let db = state.db.clone();
    let tags: Vec<Tag> = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        // 解析排序参数
        let sort_desc = sort.starts_with('-');
        let sort_key = if sort_desc {
            &sort[1..]
        } else {
            &sort
        };

        let order_by = match sort_key {
            "name" => "name",
            "color" => "color",
            "createdAt" => "created_at",
            "updatedAt" => "updated_at",
            _ => "name",
        };

        let sort_dir = if sort_desc { "DESC" } else { "ASC" };
        let sql = format!("SELECT * FROM tags ORDER BY {} {}", order_by, sort_dir);

        let mut stmt = conn.prepare(&sql).unwrap();
        let tag_iter = stmt.query_map([], |row| Tag::from_row(row)).unwrap();

        let mut result = Vec::new();
        for tag in tag_iter {
            result.push(tag.unwrap());
        }
        Ok::<Vec<Tag>, rusqlite::Error>(result)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    let total = tags.len() as i64;
    let data: Vec<TagResponse> = tags.into_iter().map(tag_to_response).collect();

    Ok(Json(TagListResponse { data, total }))
}

/// GET /api/tags/{id}
///
/// 获取单个标签。
pub async fn get_tag(
    State(state): State<AppState>,
    Path(tag_id): Path<i64>,
) -> Result<Json<TagResponse>> {
    let db = state.db.clone();
    let tag = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT * FROM tags WHERE id = ?").unwrap();
        stmt.query_row([tag_id], |row| Tag::from_row(row))
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|_| AppError::NotFound("标签不存在".to_string()))?;

    Ok(Json(tag_to_response(tag)))
}

/// POST /api/tags
///
/// 创建标签，自动分配颜色。
pub async fn create_tag(
    State(state): State<AppState>,
    Json(req): Json<TagCreateRequest>,
) -> Result<impl IntoResponse> {
    // 验证名称
    if req.name.is_empty() {
        return Err(AppError::BadRequest("标签名称不能为空".to_string()));
    }

    // 获取当前标签数量用于颜色分配
    let db = state.db.clone();
    let count: i64 = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.query_row("SELECT COUNT(*) FROM tags", [], |row| row.get(0))
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    // 自动分配颜色
    let color = req.color.unwrap_or_else(|| {
        TAG_COLORS[count as usize % TAG_COLORS.len()].to_string()
    });

    let now = Utc::now();
    let icon = req.icon.unwrap_or_default();
    let name = req.name.clone();

    // 插入标签
    let db = state.db.clone();
    let result = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            "INSERT INTO tags (name, color, icon, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![name, color, icon, now, now],
        )
    }).await;

    match result {
        Ok(Ok(_)) => {
            // 获取刚创建的标签
            let db = state.db.clone();
            let tag = tokio::task::spawn_blocking(move || {
                let conn = db.lock().unwrap();
                let mut stmt = conn.prepare("SELECT * FROM tags WHERE name = ?").unwrap();
                stmt.query_row([&req.name], |row| Tag::from_row(row))
            }).await
            .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
            .map_err(|e| AppError::Internal(format!("查询标签失败: {}", e)))?;

            Ok((StatusCode::CREATED, Json(tag_to_response(tag))))
        }
        _ => Err(AppError::Conflict("标签名称已存在".to_string())),
    }
}

/// PUT /api/tags/{id}
///
/// 更新标签。
pub async fn update_tag(
    State(state): State<AppState>,
    Path(tag_id): Path<i64>,
    Json(req): Json<TagUpdateRequest>,
) -> Result<Json<TagResponse>> {
    // 检查标签是否存在
    let db = state.db.clone();
    let exists: bool = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM tags WHERE id = ?",
            [tag_id],
            |row| row.get(0),
        ).unwrap();
        Ok::<bool, rusqlite::Error>(count > 0)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    if !exists {
        return Err(AppError::NotFound("标签不存在".to_string()));
    }

    let now = Utc::now();

    // 更新标签 - 空字符串表示不更新该字段
    let db = state.db.clone();
    let update_result = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            "UPDATE tags SET 
                name = COALESCE(NULLIF(?1, ''), name), 
                color = COALESCE(NULLIF(?2, ''), color), 
                icon = COALESCE(NULLIF(?3, ''), icon), 
                updated_at = ?4 
             WHERE id = ?5",
            params![req.name, req.color, req.icon, now, tag_id],
        )
    }).await;

    match update_result {
        Ok(Ok(_)) => {
            // 获取更新后的标签
            let db = state.db.clone();
            let tag = tokio::task::spawn_blocking(move || {
                let conn = db.lock().unwrap();
                let mut stmt = conn.prepare("SELECT * FROM tags WHERE id = ?").unwrap();
                stmt.query_row([tag_id], |row| Tag::from_row(row))
            }).await
            .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
            .map_err(|_| AppError::NotFound("标签不存在".to_string()))?;

            Ok(Json(tag_to_response(tag)))
        }
        _ => Err(AppError::Conflict("标签名称已存在".to_string())),
    }
}

/// DELETE /api/tags/{id}
///
/// 删除标签。
/// Query 参数: cascade (默认 false)
#[derive(Debug, Deserialize)]
pub struct DeleteTagQuery {
    #[serde(default)]
    cascade: bool,
}

pub async fn delete_tag(
    State(state): State<AppState>,
    Path(tag_id): Path<i64>,
    Query(query): Query<DeleteTagQuery>,
) -> Result<StatusCode> {
    // 检查标签是否存在
    let db = state.db.clone();
    let tag_exists: bool = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM tags WHERE id = ?",
            [tag_id],
            |row| row.get(0),
        ).unwrap();
        Ok::<bool, rusqlite::Error>(count > 0)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    if !tag_exists {
        return Err(AppError::NotFound("标签不存在".to_string()));
    }

    // 检查书签引用
    if !query.cascade {
        let db = state.db.clone();
        let referenced: i64 = tokio::task::spawn_blocking(move || {
            let conn = db.lock().unwrap();
            let mut count = 0i64;
            let mut stmt = conn.prepare("SELECT tag_ids FROM bookmarks").unwrap();
            let rows = stmt.query_map([], |row| {
                let tag_ids_json: String = row.get(0)?;
                Ok(tag_ids_json)
            }).unwrap();

            for tag_ids_json in rows {
                let tag_ids_json = tag_ids_json.unwrap();
                let tag_ids: Vec<i64> = serde_json::from_str(&tag_ids_json).unwrap_or_default();
                if tag_ids.contains(&tag_id) {
                    count += 1;
                }
            }
            Ok::<i64, rusqlite::Error>(count)
        }).await
        .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
        .map_err(|e| AppError::Internal(format!("检查引用失败: {}", e)))?;

        if referenced > 0 {
            return Err(AppError::Conflict(format!(
                "有 {} 条书签仍在使用该标签",
                referenced
            )));
        }
    } else {
        // 级联删除：从所有书签中移除该标签
        let db = state.db.clone();
        tokio::task::spawn_blocking(move || {
            let conn = db.lock().unwrap();
            let mut stmt = conn.prepare("SELECT id, tag_ids FROM bookmarks").unwrap();
            let rows = stmt.query_map([], |row| {
                let id: String = row.get(0)?;
                let tag_ids_json: String = row.get(1)?;
                Ok((id, tag_ids_json))
            }).unwrap();

            for row in rows {
                let (id, tag_ids_json) = row.unwrap();
                let mut tag_ids: Vec<i64> = serde_json::from_str(&tag_ids_json).unwrap_or_default();
                if tag_ids.contains(&tag_id) {
                    tag_ids.retain(|&x| x != tag_id);
                    let new_tag_ids = serde_json::to_string(&tag_ids).unwrap();
                    conn.execute(
                        "UPDATE bookmarks SET tag_ids = ? WHERE id = ?",
                        [&new_tag_ids, &id],
                    ).unwrap();
                }
            }
            Ok::<(), rusqlite::Error>(())
        }).await
        .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
        .map_err(|e| AppError::Internal(format!("级联删除失败: {}", e)))?;
    }

    // 删除标签
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute("DELETE FROM tags WHERE id = ?", [tag_id])
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("删除标签失败: {}", e)))?;

    Ok(StatusCode::NO_CONTENT)
}

/// 将 Tag 转换为 TagResponse
fn tag_to_response(tag: Tag) -> TagResponse {
    TagResponse {
        id: tag.id,
        name: tag.name,
        color: tag.color,
        icon: tag.icon,
        created_at: tag.created_at,
        updated_at: tag.updated_at,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tag_colors() {
        assert_eq!(TAG_COLORS.len(), 10);
        assert_eq!(TAG_COLORS[0], "#3B82F6");
    }

    #[test]
    fn test_default_sort() {
        assert_eq!(default_sort(), "name");
    }
}
