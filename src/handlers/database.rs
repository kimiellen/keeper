//! 数据库管理 API 处理器
//!
//! 实现数据库列表、添加、切换、创建、移除等管理功能。

use axum::{
    extract::State,
    Json,
};
use std::path::Path;

use crate::{
    db::config::DatabaseConfig,
    error::{AppError, Result},
    handlers::schemas::{
        DatabaseAddRequest, DatabaseAddResponse,
        DatabaseCreateRequest, DatabaseCreateResponse,
        DatabaseInfoResponse, DatabaseListResponse,
        DatabaseOpenRequest, DatabaseOpenResponse,
        DatabaseRemoveRequest,
    },
    state::AppState,
};

/// GET /api/db/list
///
/// 获取已连接的数据库列表和当前选中的数据库。
pub async fn list_databases() -> Result<Json<DatabaseListResponse>> {
    let mut config = DatabaseConfig::load();
    
    // 清理不存在的数据库
    config.cleanup().map_err(|e| AppError::Internal(e))?;
    
    let databases: Vec<DatabaseInfoResponse> = config
        .get_databases()
        .into_iter()
        .map(|db| DatabaseInfoResponse {
            path: db.path,
            name: db.name,
        })
        .collect();

    Ok(Json(DatabaseListResponse {
        databases,
        current: config.get_current(),
    }))
}

/// POST /api/db/add
///
/// 将已有数据库添加到列表（不切换）。
/// 验证数据库文件存在后添加到配置。
pub async fn add_database(
    Json(req): Json<DatabaseAddRequest>,
) -> Result<Json<DatabaseAddResponse>> {
    let path = req.path.trim();
    
    if path.is_empty() {
        return Err(AppError::BadRequest("数据库路径不能为空".to_string()));
    }

    let expanded_path = shellexpand::tilde(path).to_string();
    
    // 验证文件存在
    if !Path::new(&expanded_path).exists() {
        return Err(AppError::NotFound("数据库文件不存在".to_string()));
    }

    let name = Path::new(&expanded_path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("unknown.db")
        .to_string();

    // 添加到配置
    let mut config = DatabaseConfig::load();
    config.add_database(&expanded_path)
        .map_err(|e| AppError::Internal(e))?;

    Ok(Json(DatabaseAddResponse {
        message: "数据库已添加".to_string(),
        name,
    }))
}

/// POST /api/db/open
///
/// 切换到指定的数据库。
/// 动态切换数据库连接，无需重启服务。
pub async fn open_database(
    State(state): State<AppState>,
    Json(req): Json<DatabaseOpenRequest>,
) -> Result<Json<DatabaseOpenResponse>> {
    use crate::db::connection::connect;

    let path = req.path.trim();
    
    if path.is_empty() {
        return Err(AppError::BadRequest("数据库路径不能为空".to_string()));
    }

    let expanded_path = shellexpand::tilde(path).to_string();
    
    // 验证文件存在
    if !Path::new(&expanded_path).exists() {
        return Err(AppError::NotFound("数据库文件不存在".to_string()));
    }

    let name = Path::new(&expanded_path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("unknown.db")
        .to_string();

    // 设置为当前数据库
    let mut config = DatabaseConfig::load();
    
    // 确保在列表中
    config.add_database(&expanded_path)
        .map_err(|e| AppError::Internal(e))?;
    
    // 设置为当前
    config.set_current(&expanded_path)
        .map_err(|e| AppError::Internal(e))?;

    // 动态切换数据库连接
    let new_conn = tokio::task::spawn_blocking(move || {
        connect(&expanded_path)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("连接数据库失败: {}", e)))?;
    
    state.switch_db(new_conn);

    // 使当前会话失效（需要重新解锁）
    state.session_manager.revoke();

    Ok(Json(DatabaseOpenResponse {
        message: "数据库已切换".to_string(),
        name,
    }))
}

/// POST /api/db/create
///
/// 创建新数据库并初始化。
/// 创建数据库文件、初始化表结构、设置认证信息。
pub async fn create_database(
    State(state): State<AppState>,
    Json(req): Json<DatabaseCreateRequest>,
) -> Result<Json<DatabaseCreateResponse>> {
    use crate::crypto::kdf::hash_password;
    use chrono::Utc;
    use rusqlite::params;

    let path = req.path.trim();
    
    if path.is_empty() {
        return Err(AppError::BadRequest("数据库路径不能为空".to_string()));
    }
    if req.email.is_empty() {
        return Err(AppError::BadRequest("邮箱不能为空".to_string()));
    }
    if req.password.len() < 6 {
        return Err(AppError::BadRequest("密码长度至少6位".to_string()));
    }

    let expanded_path = shellexpand::tilde(path).to_string();
    let path_obj = Path::new(&expanded_path);
    
    // 检查文件是否已存在
    if path_obj.exists() {
        return Err(AppError::Conflict("数据库文件已存在".to_string()));
    }
    
    // 检查父目录是否存在
    if let Some(parent) = path_obj.parent() {
        if !parent.exists() {
            return Err(AppError::BadRequest("目标目录不存在".to_string()));
        }
    }

    let name = path_obj
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("unknown.db")
        .to_string();

    // 创建新数据库连接并初始化
    let expanded_path_clone = expanded_path.clone();
    let expanded_path_clone2 = expanded_path.clone();
    let email = req.email.clone();
    let password_hash = hash_password(&req.password);
    let now = Utc::now().to_rfc3339();
    
    tokio::task::spawn_blocking(move || {
        // 创建新数据库连接
        let mut new_conn = rusqlite::Connection::open(&expanded_path_clone)
            .map_err(|e| AppError::Internal(format!("创建数据库失败: {}", e)))?;
        
        // 设置 PRAGMA
        new_conn.execute_batch(
            r#"
            PRAGMA busy_timeout = 5000;
            PRAGMA journal_mode = DELETE;
            PRAGMA synchronous = FULL;
            PRAGMA foreign_keys = ON;
            PRAGMA cache_size = -8000;
            "#,
        ).map_err(|e| AppError::Internal(format!("设置 PRAGMA 失败: {}", e)))?;
        
        // 初始化表结构
        crate::db::migrate::migrate(&mut new_conn)
            .map_err(|e| AppError::Internal(format!("初始化数据库失败: {}", e)))?;
        
        // 创建认证记录
        new_conn.execute(
            "INSERT INTO authentication (id, email, password_hash, created_at, last_login) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![1, email, password_hash, now.clone(), now],
        ).map_err(|e| AppError::Internal(format!("创建认证信息失败: {}", e)))?;
        
        // 关闭连接
        drop(new_conn);
        
        Ok::<(), AppError>(())
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))??;

    // 添加到配置并设置为当前
    let mut config = DatabaseConfig::load();
    config.add_database(&expanded_path)
        .map_err(|e| AppError::Internal(e))?;
    config.set_current(&expanded_path)
        .map_err(|e| AppError::Internal(e))?;

    // 切换到新创建的数据库连接
    let new_conn = tokio::task::spawn_blocking(move || {
        crate::db::connection::connect(&expanded_path_clone2)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("连接新数据库失败: {}", e)))?;
    
    state.switch_db(new_conn);

    // 使当前会话失效（需要重新解锁）
    state.session_manager.revoke();

    Ok(Json(DatabaseCreateResponse {
        message: "数据库已创建".to_string(),
        name,
    }))
}

/// POST /api/db/remove
///
/// 从列表中移除数据库关联（不删除文件）。
pub async fn remove_database(
    Json(req): Json<DatabaseRemoveRequest>,
) -> Result<()> {
    let path = req.path.trim();
    
    if path.is_empty() {
        return Err(AppError::BadRequest("数据库路径不能为空".to_string()));
    }

    let expanded_path = shellexpand::tilde(path).to_string();
    
    let mut config = DatabaseConfig::load();
    
    // 检查是否在列表中
    let exists = config.get_databases().iter().any(|db| db.path == expanded_path);
    if !exists {
        return Err(AppError::NotFound("数据库不在列表中".to_string()));
    }

    // 移除
    config.remove_database(&expanded_path)
        .map_err(|e| AppError::BadRequest(e))?;

    Ok(())
}
