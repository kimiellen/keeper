//! 关联 API 处理器

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
    db::models::{Relation, RelationType},
    error::{AppError, Result},
    handlers::schemas::{
        RelationCreateRequest, RelationListResponse, RelationResponse, RelationUpdateRequest,
    },
    state::AppState,
};

/// 关联列表查询参数
#[derive(Debug, Deserialize)]
pub struct ListRelationsQuery {
    #[serde(default = "default_sort")]
    sort: String,
}

fn default_sort() -> String {
    "name".to_string()
}

/// GET /api/relations
///
/// 获取关联列表，支持排序。
pub async fn list_relations(
    State(state): State<AppState>,
    Query(query): Query<ListRelationsQuery>,
) -> Result<Json<RelationListResponse>> {
    let sort = query.sort.clone();

    let db = state.db.clone();
    let relations: Vec<Relation> = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        // 解析排序参数
        let sort_desc = sort.starts_with('-');
        let sort_key = if sort_desc { &sort[1..] } else { &sort };

        let order_by = match sort_key {
            "name" => "name",
            "type" => "type",
            "createdAt" => "created_at",
            "updatedAt" => "updated_at",
            _ => "name",
        };

        let sort_dir = if sort_desc { "DESC" } else { "ASC" };
        let sql = format!("SELECT * FROM relations ORDER BY {} {}", order_by, sort_dir);

        let mut stmt = conn.prepare(&sql).unwrap();
        let relation_iter = stmt.query_map([], |row| Relation::from_row(row)).unwrap();

        let mut result = Vec::new();
        for relation in relation_iter {
            result.push(relation.unwrap());
        }
        Ok::<Vec<Relation>, rusqlite::Error>(result)
    })
    .await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    let total = relations.len() as i64;
    let data: Vec<RelationResponse> = relations.into_iter().map(relation_to_response).collect();

    Ok(Json(RelationListResponse { data, total }))
}

/// GET /api/relations/{id}
///
/// 获取单个关联。
pub async fn get_relation(
    State(state): State<AppState>,
    Path(relation_id): Path<i64>,
) -> Result<Json<RelationResponse>> {
    let db = state.db.clone();
    let relation = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn
            .prepare("SELECT * FROM relations WHERE id = ?")
            .unwrap();
        stmt.query_row([relation_id], |row| Relation::from_row(row))
    })
    .await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|_| AppError::NotFound("关联不存在".to_string()))?;

    Ok(Json(relation_to_response(relation)))
}

/// POST /api/relations
///
/// 创建关联。
pub async fn create_relation(
    State(state): State<AppState>,
    Json(req): Json<RelationCreateRequest>,
) -> Result<impl IntoResponse> {
    // 验证名称
    if req.name.is_empty() {
        return Err(AppError::BadRequest("关联名称不能为空".to_string()));
    }

    // 验证类型
    let relation_type = match RelationType::from_str(&req.r#type) {
        Some(t) => t,
        None => {
            return Err(AppError::BadRequest(
                "关联类型必须是 phone, email, idcard, social 或 other".to_string(),
            ));
        }
    };

    let now = Utc::now();
    let name = req.name.clone();
    let value = req.value.clone();
    let type_str = relation_type.as_str().to_string();

    // 插入关联
    let db = state.db.clone();
    let result = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            "INSERT INTO relations (name, value, type, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![name, value, type_str, now, now],
        )
    }).await;

    match result {
        Ok(Ok(_)) => {
            // 获取刚创建的关联
            let db = state.db.clone();
            let relation = tokio::task::spawn_blocking(move || {
                let conn = db.lock().unwrap();
                let mut stmt = conn
                    .prepare("SELECT * FROM relations WHERE name = ?")
                    .unwrap();
                stmt.query_row([&req.name], |row| Relation::from_row(row))
            })
            .await
            .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
            .map_err(|e| AppError::Internal(format!("查询关联失败: {}", e)))?;

            Ok((StatusCode::CREATED, Json(relation_to_response(relation))))
        }
        Ok(Err(e)) => {
            // 检查错误类型
            let err_msg = e.to_string().to_lowercase();
            if err_msg.contains("unique") || err_msg.contains("constraint failed: relations.name") {
                Err(AppError::Conflict("关联名称已存在".to_string()))
            } else if err_msg.contains("check constraint failed") {
                Err(AppError::BadRequest("关联类型无效".to_string()))
            } else {
                Err(AppError::Internal(format!("创建关联失败: {}", e)))
            }
        }
        Err(e) => Err(AppError::Internal(format!("任务执行失败: {}", e))),
    }
}

/// PUT /api/relations/{id}
///
/// 更新关联。
pub async fn update_relation(
    State(state): State<AppState>,
    Path(relation_id): Path<i64>,
    Json(req): Json<RelationUpdateRequest>,
) -> Result<Json<RelationResponse>> {
    // 检查关联是否存在
    let db = state.db.clone();
    let exists: bool = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM relations WHERE id = ?",
                [relation_id],
                |row| row.get(0),
            )
            .unwrap();
        Ok::<bool, rusqlite::Error>(count > 0)
    })
    .await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    if !exists {
        return Err(AppError::NotFound("关联不存在".to_string()));
    }

    // 验证类型
    let relation_type = match RelationType::from_str(&req.r#type) {
        Some(t) => t,
        None => {
            return Err(AppError::BadRequest(
                "关联类型必须是 phone, email, idcard, social 或 other".to_string(),
            ));
        }
    };

    let now = Utc::now();
    let name = req.name.clone();
    let value = req.value.clone();
    let type_str = relation_type.as_str().to_string();

    // 更新关联
    let db = state.db.clone();
    let result = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            "UPDATE relations SET name = ?1, value = ?2, type = ?3, updated_at = ?4 WHERE id = ?5",
            params![name, value, type_str, now, relation_id],
        )
    })
    .await;

    match result {
        Ok(Ok(_)) => {
            // 获取更新后的关联
            let db = state.db.clone();
            let relation = tokio::task::spawn_blocking(move || {
                let conn = db.lock().unwrap();
                let mut stmt = conn
                    .prepare("SELECT * FROM relations WHERE id = ?")
                    .unwrap();
                stmt.query_row([relation_id], |row| Relation::from_row(row))
            })
            .await
            .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
            .map_err(|_| AppError::NotFound("关联不存在".to_string()))?;

            Ok(Json(relation_to_response(relation)))
        }
        _ => Err(AppError::Conflict("关联名称已存在".to_string())),
    }
}

/// DELETE /api/relations/{id}
///
/// 删除关联。
/// Query 参数: cascade (默认 false)
#[derive(Debug, Deserialize)]
pub struct DeleteRelationQuery {
    #[serde(default)]
    cascade: bool,
}

pub async fn delete_relation(
    State(state): State<AppState>,
    Path(relation_id): Path<i64>,
    Query(query): Query<DeleteRelationQuery>,
) -> Result<StatusCode> {
    // 检查关联是否存在
    let db = state.db.clone();
    let relation_exists: bool = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM relations WHERE id = ?",
                [relation_id],
                |row| row.get(0),
            )
            .unwrap();
        Ok::<bool, rusqlite::Error>(count > 0)
    })
    .await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    if !relation_exists {
        return Err(AppError::NotFound("关联不存在".to_string()));
    }

    // 检查书签中的账户引用
    if !query.cascade {
        let db = state.db.clone();
        let referenced: i64 = tokio::task::spawn_blocking(move || {
            let conn = db.lock().unwrap();
            let mut count = 0i64;
            let mut stmt = conn.prepare("SELECT accounts FROM bookmarks").unwrap();
            let rows = stmt
                .query_map([], |row| {
                    let accounts_json: String = row.get(0)?;
                    Ok(accounts_json)
                })
                .unwrap();

            for accounts_json in rows {
                let accounts_json = accounts_json.unwrap();
                let accounts: Vec<serde_json::Value> =
                    serde_json::from_str(&accounts_json).unwrap_or_default();

                for account in accounts {
                    if let Some(related_ids) = account.get("relatedIds").and_then(|v| v.as_array())
                    {
                        if related_ids
                            .iter()
                            .any(|id| id.as_i64() == Some(relation_id))
                        {
                            count += 1;
                            break;
                        }
                    }
                }
            }
            Ok::<i64, rusqlite::Error>(count)
        })
        .await
        .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
        .map_err(|e| AppError::Internal(format!("检查引用失败: {}", e)))?;

        if referenced > 0 {
            return Err(AppError::Conflict(format!(
                "有 {} 条书签仍在使用该关联",
                referenced
            )));
        }
    } else {
        // 级联删除：从所有账户的 relatedIds 中移除该关联
        let db = state.db.clone();
        tokio::task::spawn_blocking(move || {
            let conn = db.lock().unwrap();
            let mut stmt = conn.prepare("SELECT id, accounts FROM bookmarks").unwrap();
            let rows = stmt
                .query_map([], |row| {
                    let id: String = row.get(0)?;
                    let accounts_json: String = row.get(1)?;
                    Ok((id, accounts_json))
                })
                .unwrap();

            for row in rows {
                let (id, accounts_json) = row.unwrap();
                let mut accounts: Vec<serde_json::Map<String, serde_json::Value>> =
                    serde_json::from_str(&accounts_json).unwrap_or_default();

                let mut changed = false;
                for account in &mut accounts {
                    if let Some(related_ids_val) = account.get_mut("relatedIds") {
                        if let Some(related_ids) = related_ids_val.as_array_mut() {
                            let original_len = related_ids.len();
                            related_ids.retain(|id| id.as_i64() != Some(relation_id));
                            if related_ids.len() != original_len {
                                changed = true;
                            }
                        }
                    }
                }

                if changed {
                    let new_accounts = serde_json::to_string(&accounts).unwrap();
                    conn.execute(
                        "UPDATE bookmarks SET accounts = ? WHERE id = ?",
                        [&new_accounts, &id],
                    )
                    .unwrap();
                }
            }
            Ok::<(), rusqlite::Error>(())
        })
        .await
        .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
        .map_err(|e| AppError::Internal(format!("级联删除失败: {}", e)))?;
    }

    // 删除关联
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute("DELETE FROM relations WHERE id = ?", [relation_id])
    })
    .await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("删除关联失败: {}", e)))?;

    Ok(StatusCode::NO_CONTENT)
}

/// 将 Relation 转换为 RelationResponse
fn relation_to_response(relation: Relation) -> RelationResponse {
    RelationResponse {
        id: relation.id,
        name: relation.name,
        value: relation.value,
        r#type: relation.r#type.as_str().to_string(),
        created_at: relation.created_at,
        updated_at: relation.updated_at,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_sort() {
        assert_eq!(default_sort(), "name");
    }

    #[test]
    fn test_relation_type_validation() {
        assert!(RelationType::from_str("phone").is_some());
        assert!(RelationType::from_str("email").is_some());
        assert!(RelationType::from_str("idcard").is_some());
        assert!(RelationType::from_str("social").is_some());
        assert!(RelationType::from_str("other").is_some());
        assert!(RelationType::from_str("invalid").is_none());
    }
}
