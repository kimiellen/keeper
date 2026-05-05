//! 关联 API 集成测试

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
    handlers::relations::{
        create_relation, delete_relation, get_relation, list_relations, update_relation,
    },
    session::manager::SessionManager,
    state::AppState,
};

async fn create_test_app() -> Router {
    let conn = connect_in_memory().unwrap();
    let session_manager = Arc::new(SessionManager::new(Duration::from_secs(3600)));
    let state = AppState::new(conn, session_manager, None);

    Router::new()
        .route(
            "/api/relations",
            axum::routing::get(list_relations).post(create_relation),
        )
        .route(
            "/api/relations/:id",
            axum::routing::get(get_relation)
                .put(update_relation)
                .delete(delete_relation),
        )
        .with_state(state)
}

#[tokio::test]
async fn test_create_relation_success() {
    let app = create_test_app().await;

    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/relations")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({"name": "手机号", "type": "phone"}).to_string(),
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::CREATED);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(body["name"], "手机号");
    assert_eq!(body["type"], "phone");
}

#[tokio::test]
async fn test_create_social_relation_success() {
    let app = create_test_app().await;

    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/relations")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({"name": "GitHub", "type": "social"}).to_string(),
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::CREATED);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(body["type"], "social");
}

#[tokio::test]
async fn test_create_relation_invalid_type() {
    let app = create_test_app().await;

    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/relations")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({"name": "测试", "type": "invalid"}).to_string(),
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_list_relations() {
    let app = create_test_app().await;

    // 创建关联
    for (name, rtype) in [("手机", "phone"), ("邮箱", "email")] {
        let request = Request::builder()
            .method(Method::POST)
            .uri("/api/relations")
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(json!({"name": name, "type": rtype}).to_string()))
            .unwrap();
        let _response = app.clone().oneshot(request).await.unwrap();
    }

    let request = Request::builder()
        .uri("/api/relations")
        .body(Body::empty())
        .unwrap();
    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(body["total"], 2);
}

#[tokio::test]
async fn test_update_relation() {
    let app = create_test_app().await;

    // 创建
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/relations")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({"name": "原名", "type": "other"}).to_string(),
        ))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    let id = body["id"].as_i64().unwrap();

    // 更新
    let request = Request::builder()
        .method(Method::PUT)
        .uri(&format!("/api/relations/{}", id))
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({"name": "新名", "type": "email"}).to_string(),
        ))
        .unwrap();
    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(body["name"], "新名");
    assert_eq!(body["type"], "email");
}

#[tokio::test]
async fn test_delete_relation() {
    let app = create_test_app().await;

    // 创建
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/relations")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({"name": "待删除", "type": "other"}).to_string(),
        ))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    let id = body["id"].as_i64().unwrap();

    // 删除
    let request = Request::builder()
        .method(Method::DELETE)
        .uri(&format!("/api/relations/{}", id))
        .body(Body::empty())
        .unwrap();
    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::NO_CONTENT);
}
