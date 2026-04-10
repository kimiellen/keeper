//! 标签 API 集成测试

use std::time::Duration;

use axum::{
    body::Body,
    http::{header, Method, Request, StatusCode},
    Router,
};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::sync::Arc;
use tower::util::ServiceExt;

use keeper::{
    db::connection::connect_in_memory,
    handlers::tags::{create_tag, delete_tag, get_tag, list_tags, update_tag},
    session::manager::SessionManager,
    state::AppState,
};

async fn create_test_app() -> Router {
    let conn = connect_in_memory().unwrap();
    let session_manager = Arc::new(SessionManager::new(Duration::from_secs(3600)));
    let state = AppState::new(conn, session_manager);

    Router::new()
        .route("/api/tags", axum::routing::get(list_tags).post(create_tag))
        .route("/api/tags/:id", axum::routing::get(get_tag).put(update_tag).delete(delete_tag))
        .with_state(state)
}

#[tokio::test]
async fn test_create_tag_success() {
    let app = create_test_app().await;

    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/tags")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({"name": "工作"}).to_string(),
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::CREATED);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(body["name"], "工作");
    assert!(body["color"].as_str().unwrap().starts_with('#'));
}

#[tokio::test]
async fn test_create_tag_duplicate() {
    let app = create_test_app().await;

    // 创建第一个标签
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/tags")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(json!({"name": "测试"}).to_string()))
        .unwrap();
    let _response = app.clone().oneshot(request).await.unwrap();

    // 创建同名标签应该失败
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/tags")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(json!({"name": "测试"}).to_string()))
        .unwrap();
    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::CONFLICT);
}

#[tokio::test]
async fn test_list_tags() {
    let app = create_test_app().await;

    // 创建两个标签
    for name in ["标签1", "标签2"] {
        let request = Request::builder()
            .method(Method::POST)
            .uri("/api/tags")
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(json!({"name": name}).to_string()))
            .unwrap();
        let _response = app.clone().oneshot(request).await.unwrap();
    }

    // 获取列表
    let request = Request::builder()
        .uri("/api/tags")
        .body(Body::empty())
        .unwrap();
    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(body["total"], 2);
    assert_eq!(body["data"].as_array().unwrap().len(), 2);
}

#[tokio::test]
async fn test_get_tag_not_found() {
    let app = create_test_app().await;

    let request = Request::builder()
        .uri("/api/tags/999")
        .body(Body::empty())
        .unwrap();
    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_update_tag() {
    let app = create_test_app().await;

    // 创建标签
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/tags")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(json!({"name": "更新测试原名"}).to_string()))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    let tag_id = body["id"].as_i64().unwrap();

    // 更新标签
    let request = Request::builder()
        .method(Method::PUT)
        .uri(&format!("/api/tags/{}", tag_id))
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({"name": "更新测试新名", "color": "#FF0000"}).to_string(),
        ))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    
    // 检查响应状态
    assert_eq!(response.status(), StatusCode::OK, "Update should return 200");

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(body["name"], "更新测试新名");
    assert_eq!(body["color"], "#FF0000");
}

#[tokio::test]
async fn test_delete_tag() {
    let app = create_test_app().await;

    // 创建标签
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/tags")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(json!({"name": "待删除"}).to_string()))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    let tag_id = body["id"].as_i64().unwrap();

    // 删除标签
    let request = Request::builder()
        .method(Method::DELETE)
        .uri(&format!("/api/tags/{}", tag_id))
        .body(Body::empty())
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::NO_CONTENT);

    // 再次获取应该失败
    let request = Request::builder()
        .uri(&format!("/api/tags/{}", tag_id))
        .body(Body::empty())
        .unwrap();
    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
}
