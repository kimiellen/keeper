//! 统计 API 处理器

use axum::{extract::State, Json};

use crate::{
    error::{AppError, Result},
    handlers::schemas::{RecentBookmark, StatsResponse, TagCount},
    state::AppState,
};

/// GET /api/stats
///
/// 获取统计数据。
pub async fn get_stats(State(state): State<AppState>) -> Result<Json<StatsResponse>> {
    // 统计书签总数
    let db = state.db.clone();
    let total_bookmarks: i64 = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.query_row("SELECT COUNT(*) FROM bookmarks", [], |row| row.get(0))
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    // 统计标签总数
    let db = state.db.clone();
    let total_tags: i64 = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.query_row("SELECT COUNT(*) FROM tags", [], |row| row.get(0))
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    // 统计关联总数
    let db = state.db.clone();
    let total_relations: i64 = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.query_row("SELECT COUNT(*) FROM relations", [], |row| row.get(0))
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    // 统计账户总数（所有书签的 accounts 数组中的条目数）
    let db = state.db.clone();
    let total_accounts: i64 = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut count = 0i64;
        let mut stmt = conn.prepare("SELECT accounts FROM bookmarks")?;
        let rows = stmt.query_map([], |row| {
            let accounts_json: String = row.get(0)?;
            Ok(accounts_json)
        })?;

        for accounts_json in rows {
            let accounts_json = accounts_json?;
            let accounts: Vec<serde_json::Value> =
                serde_json::from_str(&accounts_json).unwrap_or_default();
            count += accounts.len() as i64;
        }
        Ok::<i64, rusqlite::Error>(count)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("统计账户失败: {}", e)))?;

    // 获取使用最多的 5 个标签
    let db = state.db.clone();
    let most_used_tags: Vec<TagCount> = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        // 统计每个标签被引用的次数
        let mut tag_counts: Vec<(i64, i64)> = Vec::new();
        let mut stmt = conn.prepare("SELECT id FROM tags")?;
        let tag_rows = stmt.query_map([], |row| row.get::<_, i64>(0))?;

        for tag_id in tag_rows {
            let tag_id = tag_id?;
            let mut count = 0i64;

            // 统计引用该标签的书签数量
            let mut stmt2 = conn.prepare("SELECT tag_ids FROM bookmarks")?;
            let bookmark_rows = stmt2.query_map([], |row| {
                let tag_ids_json: String = row.get(0)?;
                Ok(tag_ids_json)
            })?;

            for tag_ids_json in bookmark_rows {
                let tag_ids_json = tag_ids_json?;
                let tag_ids: Vec<i64> =
                    serde_json::from_str(&tag_ids_json).unwrap_or_default();
                if tag_ids.contains(&tag_id) {
                    count += 1;
                }
            }

            if count > 0 {
                tag_counts.push((tag_id, count));
            }
        }

        // 按使用次数排序，取前 5
        tag_counts.sort_by(|a, b| b.1.cmp(&a.1));
        tag_counts.truncate(5);

        // 获取标签名称并转换为 TagCount
        let mut result = Vec::new();
        for (tag_id, count) in tag_counts {
            let name: String = conn.query_row(
                "SELECT name FROM tags WHERE id = ?",
                [tag_id],
                |row| row.get(0),
            )?;
            result.push(TagCount {
                tag_id,
                tag_name: name,
                count,
            });
        }

        Ok::<Vec<TagCount>, rusqlite::Error>(result)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("统计标签使用失败: {}", e)))?;

    // 获取最近使用的 5 个书签
    let db = state.db.clone();
    let recently_used: Vec<RecentBookmark> = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, name, last_used_at FROM bookmarks ORDER BY last_used_at DESC LIMIT 5",
        )?;
        let rows = stmt.query_map([], |row| {
            let id: String = row.get(0)?;
            let name: String = row.get(1)?;
            let last_used_at: chrono::DateTime<chrono::Utc> = row.get(2)?;
            Ok(RecentBookmark {
                id,
                name,
                last_used_at,
            })
        })?;

        let mut result = Vec::new();
        for row in rows {
            result.push(row?);
        }
        Ok::<Vec<RecentBookmark>, rusqlite::Error>(result)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("查询最近使用失败: {}", e)))?;

    Ok(Json(StatsResponse {
        total_bookmarks,
        total_tags,
        total_relations,
        total_accounts,
        most_used_tags,
        recently_used,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stats_response_structure() {
        // 验证响应结构
        let stats = StatsResponse {
            total_bookmarks: 10,
            total_tags: 5,
            total_relations: 3,
            total_accounts: 20,
            most_used_tags: vec![
                TagCount {
                    tag_id: 1,
                    tag_name: "工作".to_string(),
                    count: 5,
                },
            ],
            recently_used: vec![
                RecentBookmark {
                    id: "uuid".to_string(),
                    name: "GitHub".to_string(),
                    last_used_at: chrono::Utc::now(),
                },
            ],
        };

        assert_eq!(stats.total_bookmarks, 10);
        assert_eq!(stats.most_used_tags[0].tag_name, "工作");
    }
}
