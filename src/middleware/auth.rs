//! 认证中间件
//!
//! 验证 Authorization header 或 Cookie 中的会话令牌，将 Session 附加到请求扩展。

use axum::{
    extract::{Request, State},
    http::{header, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;

use crate::{session::manager::Session, state::AppState};

/// 白名单路径（无需认证）
const PUBLIC_PATHS: &[&str] = &[
    "/api/auth/initialize",
    "/api/auth/unlock",
    "/api/auth/lock",
    "/api/auth/status",
    "/api/auth/info",
    "/api/health",
    "/",
    // 数据库管理（公开）
    "/api/db/list",
    "/api/db/add",
    "/api/db/open",
    "/api/db/create",
    "/api/db/remove",
];

/// Cookie 名称（向后兼容）
const SESSION_COOKIE_NAME: &str = "keeper_session";

/// 认证中间件
///
/// 检查请求路径是否在白名单中，如果不是则验证 Authorization header 或 Cookie 中的会话令牌。
/// 验证成功将 Session 附加到请求扩展，失败返回 401。
pub async fn auth_middleware(
    State(state): State<AppState>,
    mut request: Request,
    next: Next,
) -> Response {
    let path = request.uri().path();
    tracing::info!("Auth middleware for path: {}", path);

    // 检查是否在白名单中
    if PUBLIC_PATHS.contains(&path) {
        tracing::info!("Path {} is public, skipping auth", path);
        return next.run(request).await;
    }

    // 优先从 Authorization header 提取令牌，其次从 Cookie
    let token = match extract_token_from_header(&request) {
        Some(t) => {
            tracing::info!("Found token in Authorization header");
            t
        }
        None => match extract_token_from_cookies(&request) {
            Some(t) => {
                tracing::info!("Found token in Cookie");
                t
            }
            None => {
                tracing::warn!("No token found in request");
                return auth_error_response();
            }
        }
    };

    // 验证会话（使用 validate_and_clean 自动清理过期会话）
    tracing::info!("Validating token with session manager");
    match state.session_manager.validate_and_clean(&token) {
        Some(session) => {
            tracing::info!("Token validated successfully");
            // 将 Session 附加到请求扩展
            request.extensions_mut().insert(session);
            next.run(request).await
        }
        None => {
            tracing::warn!("Token validation failed");
            auth_error_response()
        }
    }
}

/// 从 Authorization header 提取令牌（Bearer token）
fn extract_token_from_header(request: &Request) -> Option<String> {
    let auth_header = request.headers().get(header::AUTHORIZATION)?;
    tracing::info!("Authorization header: {:?}", auth_header);
    
    let auth_str = auth_header.to_str().ok()?;
    tracing::info!("Authorization string: {}", auth_str);
    
    // 支持 "Bearer <token>" 格式
    if auth_str.starts_with("Bearer ") {
        let token = auth_str[7..].to_string();
        tracing::info!("Extracted token: {}...", &token[..10.min(token.len())]);
        Some(token)
    } else {
        tracing::warn!("Invalid Authorization format");
        None
    }
}

/// 从请求的 Cookie 中提取会话令牌（向后兼容）
fn extract_token_from_cookies(request: &Request) -> Option<String> {
    let cookie_header = request.headers().get(header::COOKIE)?.to_str().ok()?;

    for cookie in cookie_header.split(';') {
        let cookie = cookie.trim();
        if let Some((name, value)) = cookie.split_once('=') {
            if name.trim() == SESSION_COOKIE_NAME {
                return Some(value.trim().to_string());
            }
        }
    }

    None
}

/// 认证错误响应
fn auth_error_response() -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({
            "locked": true
        })),
    )
        .into_response()
}

/// 从请求扩展中获取 Session
///
/// 用于处理器中获取当前会话信息
pub fn get_session_from_request(request: &Request) -> Option<&Session> {
    request.extensions().get::<Session>()
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;

    #[test]
    fn test_extract_token_from_cookies() {
        let request = Request::builder()
            .header(header::COOKIE, "keeper_session=abc123; other=value")
            .body(Body::empty())
            .unwrap();

        let token = extract_token_from_cookies(&request);
        assert_eq!(token, Some("abc123".to_string()));
    }

    #[test]
    fn test_extract_token_no_cookie() {
        let request = Request::builder().body(Body::empty()).unwrap();

        let token = extract_token_from_cookies(&request);
        assert_eq!(token, None);
    }

    #[test]
    fn test_extract_token_wrong_cookie() {
        let request = Request::builder()
            .header(header::COOKIE, "other=value")
            .body(Body::empty())
            .unwrap();

        let token = extract_token_from_cookies(&request);
        assert_eq!(token, None);
    }

    #[test]
    fn test_public_paths() {
        for path in PUBLIC_PATHS {
            assert!(PUBLIC_PATHS.contains(path));
        }
    }
}
