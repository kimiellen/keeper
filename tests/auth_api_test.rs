//! 认证 API 集成测试

use std::time::Duration;

use axum::{
    body::Body,
    http::{header, Method, Request, StatusCode},
    routing::{get, post},
    Router,
};
use http_body_util::BodyExt;
use rusqlite::Connection;
use serde_json::{json, Value};
use std::sync::Arc;
use tower::util::ServiceExt;

use keeper::{
    db::connection::connect_in_memory,
    handlers::auth::{info, initialize, lock, status, unlock},
    session::manager::SessionManager,
    state::AppState,
};

async fn setup_test_app() -> (Router, Connection, Arc<SessionManager>) {
    let conn = connect_in_memory().unwrap();
    let session_manager = Arc::new(SessionManager::new(Duration::from_secs(3600)));
    let state = AppState::new(conn, session_manager.clone(), None);

    let app = Router::new()
        .route("/api/auth/initialize", post(initialize))
        .route("/api/auth/unlock", post(unlock))
        .route("/api/auth/lock", post(lock))
        .route("/api/auth/status", get(status))
        .route("/api/auth/info", get(info))
        .with_state(state);

    (app, connect_in_memory().unwrap(), session_manager)
}

#[tokio::test]
async fn test_initialize_success() {
    let (app, _conn, _sm) = setup_test_app().await;

    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/initialize")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({
                "email": "test@example.com",
                "password": "password123"
            })
            .to_string(),
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(body["message"], "初始化成功");
}

#[tokio::test]
async fn test_initialize_duplicate() {
    let (app, _conn, _sm) = setup_test_app().await;

    // 第一次初始化
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/initialize")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({
                "email": "test@example.com",
                "password": "password123"
            })
            .to_string(),
        ))
        .unwrap();

    let response = app.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    // 第二次初始化应该失败
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/initialize")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({
                "email": "test2@example.com",
                "password": "password456"
            })
            .to_string(),
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::CONFLICT);
}

#[tokio::test]
async fn test_unlock_success() {
    let (app, _conn, _sm) = setup_test_app().await;

    // 先初始化
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/initialize")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({
                "email": "test@example.com",
                "password": "password123"
            })
            .to_string(),
        ))
        .unwrap();
    let _response = app.clone().oneshot(request).await.unwrap();

    // 解锁
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/unlock")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({
                "password": "password123"
            })
            .to_string(),
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    // 检查 token 返回
    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    assert!(body["token"].is_string());
}

#[tokio::test]
async fn test_unlock_wrong_password() {
    let (app, _conn, _sm) = setup_test_app().await;

    // 先初始化
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/initialize")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({
                "email": "test@example.com",
                "password": "password123"
            })
            .to_string(),
        ))
        .unwrap();
    let _response = app.clone().oneshot(request).await.unwrap();

    // 使用错误密码解锁
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/unlock")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({
                "password": "wrongpassword"
            })
            .to_string(),
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_status_locked() {
    let (app, _conn, _sm) = setup_test_app().await;

    let request = Request::builder()
        .uri("/api/auth/status")
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(body["locked"], true);
}

#[tokio::test]
async fn test_info_before_initialize() {
    let (app, _conn, _sm) = setup_test_app().await;

    let request = Request::builder()
        .uri("/api/auth/info")
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    // 应该返回错误，因为没有初始化
    assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
}

#[tokio::test]
async fn test_lock() {
    let (app, _conn, _sm) = setup_test_app().await;

    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/lock")
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::NO_CONTENT);
}
