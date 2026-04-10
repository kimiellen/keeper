//! 认证 API 处理器
//!
//! 实现初始化、解锁、锁定、状态查询等认证相关接口。


use axum::{
    extract::{Json, State},
    http::{header, StatusCode},

};

use chrono::Utc;
use rusqlite::params;

use std::time::Duration;

use crate::{
    crypto::kdf::{derive_key, hash_password, verify_password},
    db::models::Authentication,
    error::{AppError, Result},
    handlers::schemas::{
        AuthInfoResponse, AuthInitializeRequest, AuthInitializeResponse,
        AuthSessionTimeoutRequest, AuthSessionTimeoutResponse,
        AuthStatusResponse, AuthUnlockRequest, AuthUnlockResponse,
    },
    state::AppState,
};

/// POST /api/auth/initialize
///
/// 初始化认证信息（单用户系统）。
/// 如果已存在认证信息，返回错误。
pub async fn initialize(
    State(state): State<AppState>,
    Json(req): Json<AuthInitializeRequest>,
) -> Result<Json<AuthInitializeResponse>> {
    // 检查是否已存在认证信息
    let db = state.db.clone();
    let exists = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT COUNT(*) FROM authentication WHERE id = 1")?;
        let count: i64 = stmt.query_row([], |row| row.get(0))?;
        Ok::<bool, rusqlite::Error>(count > 0)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    if exists {
        return Err(AppError::Conflict("认证信息已存在".to_string()));
    }

    // 验证输入
    if req.email.is_empty() {
        return Err(AppError::BadRequest("邮箱不能为空".to_string()));
    }
    if req.password.len() < 6 {
        return Err(AppError::BadRequest("密码长度至少6位".to_string()));
    }

    // 哈希密码
    let password_hash = hash_password(&req.password);
    let now = Utc::now().to_rfc3339();
    let email = req.email.clone();

    // 插入认证信息
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            "INSERT INTO authentication (id, email, password_hash, created_at, last_login) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![1, email, password_hash, now, now],
        )?;
        Ok::<(), rusqlite::Error>(())
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("创建认证信息失败: {}", e)))?;

    Ok(Json(AuthInitializeResponse {
        message: "初始化成功".to_string(),
    }))
}

/// GET /api/auth/info
///
/// 获取当前认证信息（邮箱）。
pub async fn info(State(state): State<AppState>) -> Result<Json<AuthInfoResponse>> {
    let db = state.db.clone();
    let auth = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT id, email, password_hash, created_at, last_login FROM authentication WHERE id = 1")?;
        let result = stmt.query_row([], |row| Authentication::from_row(row))?;
        Ok::<Authentication, rusqlite::Error>(result)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("数据库错误: {}", e)))?;

    Ok(Json(AuthInfoResponse {
        email: auth.email,
    }))
}

/// POST /api/auth/unlock
///
/// 解锁（登录）。
/// 验证密码，创建会话，返回 token。
pub async fn unlock(
    State(state): State<AppState>,
    Json(req): Json<AuthUnlockRequest>,
) -> Result<Json<AuthUnlockResponse>> {
    // 查询认证信息
    let db = state.db.clone();
    let auth = tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        let mut stmt = conn.prepare("SELECT id, email, password_hash, created_at, last_login FROM authentication WHERE id = 1")?;
        let result = stmt.query_row([], |row| Authentication::from_row(row))?;
        Ok::<Authentication, rusqlite::Error>(result)
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|_| AppError::Auth("未初始化".to_string()))?;

    // 验证密码
    if !verify_password(&req.password, &auth.password_hash) {
        return Err(AppError::Auth("密码错误".to_string()));
    }

    // 派生加密密钥
    let encryption_key = derive_key(&req.password);

    // 创建会话
    let token = state.session_manager.create(encryption_key);
    tracing::info!("Created session with token: {}", &token[..10.min(token.len())]);

    // 更新最后登录时间
    let now = Utc::now().to_rfc3339();
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        conn.execute(
            "UPDATE authentication SET last_login = ?1 WHERE id = 1",
            params![now],
        )?;
        Ok::<(), rusqlite::Error>(())
    }).await
    .map_err(|e| AppError::Internal(format!("任务执行失败: {}", e)))?
    .map_err(|e| AppError::Internal(format!("更新登录时间失败: {}", e)))?;

    // 返回 token（不再使用 cookie）
    Ok(Json(AuthUnlockResponse {
        token: Some(token),
        message: "解锁成功".to_string(),
    }))
}

/// POST /api/auth/lock
///
/// 锁定（登出）。
/// 清除会话。
pub async fn lock(State(state): State<AppState>) -> StatusCode {
    // 撤销会话
    state.session_manager.revoke();

    StatusCode::NO_CONTENT
}

/// GET /api/auth/status
///
/// 获取认证状态。
/// 验证 Authorization header 中的令牌，返回是否锁定。
pub async fn status(
    State(state): State<AppState>,
    headers: header::HeaderMap,
) -> Result<Json<AuthStatusResponse>> {
    // 从 Authorization header 提取令牌
    let token = extract_token_from_auth_header(&headers);

    let locked = match token {
        Some(token) => {
            // 验证会话
            state.session_manager.validate(&token).is_none()
        }
        None => true,
    };

    Ok(Json(AuthStatusResponse { locked }))
}

/// POST /api/auth/session-timeout
///
/// 设置会话超时时间（分钟）。
pub async fn set_session_timeout(
    State(state): State<AppState>,
    Json(req): Json<AuthSessionTimeoutRequest>,
) -> Result<Json<AuthSessionTimeoutResponse>> {
    let ttl = Duration::from_secs(req.timeout * 60);
    state.session_manager.set_ttl(ttl);
    Ok(Json(AuthSessionTimeoutResponse {
        message: "会话超时设置已更新".to_string(),
    }))
}

/// 从 Authorization header 提取令牌（Bearer token）
fn extract_token_from_auth_header(headers: &header::HeaderMap) -> Option<String> {
    let auth_header = headers.get(header::AUTHORIZATION)?;
    let auth_str = auth_header.to_str().ok()?;
    
    // 支持 "Bearer <token>" 格式
    if auth_str.starts_with("Bearer ") {
        Some(auth_str[7..].to_string())
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_token_from_auth_header() {
        let mut headers = header::HeaderMap::new();
        headers.insert(
            header::AUTHORIZATION,
            header::HeaderValue::from_static("Bearer abc123"),
        );

        let token = extract_token_from_auth_header(&headers);
        assert_eq!(token, Some("abc123".to_string()));
    }

    #[test]
    fn test_extract_token_no_auth_header() {
        let headers = header::HeaderMap::new();
        let token = extract_token_from_auth_header(&headers);
        assert_eq!(token, None);
    }

    #[test]
    fn test_extract_token_invalid_format() {
        let mut headers = header::HeaderMap::new();
        headers.insert(
            header::AUTHORIZATION,
            header::HeaderValue::from_static("Basic abc123"),
        );

        let token = extract_token_from_auth_header(&headers);
        assert_eq!(token, None);
    }
}
