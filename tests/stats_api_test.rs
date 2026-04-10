//! 统计 API 集成测试

use std::time::Duration;

use axum::{
    body::Body,
    http::{Request, StatusCode},
    Router,
};
use http_body_util::BodyExt;
use serde_json::Value;
use std::sync::Arc;
use tower::util::ServiceExt;

use keeper::{
    db::connection::connect_in_memory,
    handlers::stats::get_stats,
    session::manager::SessionManager,
    state::AppState,
};

async fn create_test_app() -> Router {
    let conn = connect_in_memory().unwrap();
    let session_manager = Arc::new(SessionManager::new(Duration::from_secs(3600)));
    let state = AppState::new(conn, session_manager);

    Router::new()
        .route("/api/stats", axum::routing::get(get_stats))
        .with_state(state)
}

#[tokio::test]
async fn test_get_stats_empty() {
    let app = create_test_app().await;

    let request = Request::builder()
        .uri("/api/stats")
        .body(Body::empty())
        .unwrap();
    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    
    assert_eq!(body["totalBookmarks"], 0);
    assert_eq!(body["totalTags"], 0);
    assert_eq!(body["totalRelations"], 0);
    assert_eq!(body["totalAccounts"], 0);
    assert!(body["mostUsedTags"].as_array().unwrap().is_empty());
    assert!(body["recentlyUsed"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_get_stats_structure() {
    let app = create_test_app().await;

    let request = Request::builder()
        .uri("/api/stats")
        .body(Body::empty())
        .unwrap();
    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    
    // 验证所有字段存在
    assert!(body.get("totalBookmarks").is_some());
    assert!(body.get("totalTags").is_some());
    assert!(body.get("totalRelations").is_some());
    assert!(body.get("totalAccounts").is_some());
    assert!(body.get("mostUsedTags").is_some());
    assert!(body.get("recentlyUsed").is_some());
}
