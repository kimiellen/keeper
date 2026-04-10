//! 导入导出 API 集成测试

use std::time::Duration;

use axum::{
    body::Body,
    http::{header, Method, Request, StatusCode},
    middleware,
    Router,
};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::sync::Arc;
use tower::util::ServiceExt;

use keeper::{
    db::connection::connect_in_memory,
    handlers::auth::{info, initialize, lock, status, unlock},
    handlers::bookmarks::{create_bookmark, list_bookmarks},
    handlers::relations::{create_relation, list_relations},
    handlers::tags::{create_tag, list_tags},
    handlers::transfer::{export_data, import_data},
    middleware::auth::auth_middleware,
    session::manager::SessionManager,
    state::AppState,
};

/// 创建测试应用（包含所有路由和中间件）
async fn create_test_app() -> Router {
    let conn = connect_in_memory().unwrap();
    let session_manager = Arc::new(SessionManager::new(Duration::from_secs(3600)));
    let state = AppState::new(conn, session_manager);

    Router::new()
        // 认证路由（公开）
        .route("/api/auth/initialize", axum::routing::post(initialize))
        .route("/api/auth/unlock", axum::routing::post(unlock))
        .route("/api/auth/lock", axum::routing::post(lock))
        .route("/api/auth/status", axum::routing::get(status))
        .route("/api/auth/info", axum::routing::get(info))
        // 标签路由（受保护）
        .route("/api/tags", axum::routing::get(list_tags).post(create_tag))
        // 关联路由（受保护）
        .route("/api/relations", axum::routing::get(list_relations).post(create_relation))
        // 书签路由（受保护）
        .route("/api/bookmarks", axum::routing::get(list_bookmarks).post(create_bookmark))
        // 导入导出路由（受保护）
        .route("/api/export", axum::routing::get(export_data))
        .route("/api/import", axum::routing::post(import_data))
        // 认证中间件
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ))
        .with_state(state)
}

/// 辅助函数：初始化并解锁应用，返回 Token
async fn setup_authenticated_session(app: &Router) -> String {
    // 初始化
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/initialize")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({
                "email": "test@example.com",
                "password": "test_password_123"
            })
            .to_string(),
        ))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    // 解锁获取 Token
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/unlock")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({"password": "test_password_123"}).to_string(),
        ))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    // 从响应体中提取 Token
    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    body["token"].as_str().unwrap().to_string()
}

#[tokio::test]
async fn test_export_empty_database() {
    let app = create_test_app().await;
    let token = setup_authenticated_session(&app).await;

    // 导出空数据库
    let request = Request::builder()
        .uri("/api/export")
        .header(header::AUTHORIZATION, format!("Bearer {}", token))
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();

    // 验证导出结构
    assert_eq!(body["version"], "keeper-1.0");
    assert!(body["exportedAt"].is_string());
    assert!(body["tags"].as_array().unwrap().is_empty());
    assert!(body["relations"].as_array().unwrap().is_empty());
    assert!(body["bookmarks"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_export_with_data() {
    let app = create_test_app().await;
    let token = setup_authenticated_session(&app).await;

    // 创建标签
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/tags")
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::AUTHORIZATION, format!("Bearer {}", &token))
        .body(Body::from(json!({"name": "工作标签"}).to_string()))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let status = response.status();
    if status != StatusCode::CREATED {
        let body = response.into_body().collect().await.unwrap().to_bytes();
        let body_str = String::from_utf8_lossy(&body);
        panic!("创建标签失败: {} - {}", status, body_str);
    }

    // 创建关联
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/relations")
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::AUTHORIZATION, format!("Bearer {}", &token))
        .body(Body::from(
            json!({"name": "测试手机", "type": "phone"}).to_string(),
        ))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::CREATED);

    // 导出数据
    let request = Request::builder()
        .uri("/api/export")
        .header(header::AUTHORIZATION, format!("Bearer {}", token))
        .body(Body::empty())
        .unwrap();

    let response = app.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body_str = String::from_utf8_lossy(&body);
    let body: Value = serde_json::from_slice(&body).unwrap();

    // 验证导出数据
    let tags_len = body["tags"].as_array().unwrap().len();
    let relations_len = body["relations"].as_array().unwrap().len();
    if tags_len != 1 || relations_len != 1 {
        panic!("导出数据数量不对: tags={}, relations={}. 响应: {}", 
               tags_len, relations_len, body_str);
    }

    // 验证标签数据
    let tag = &body["tags"][0];
    assert_eq!(tag["name"], "工作标签");
    assert!(tag["color"].as_str().unwrap().starts_with('#'));

    // 验证关联数据
    let relation = &body["relations"][0];
    assert_eq!(relation["name"], "测试手机");
    assert_eq!(relation["type"], "phone");
}

#[tokio::test]
async fn test_import_data() {
    let app = create_test_app().await;
    let token = setup_authenticated_session(&app).await;

    // 准备导入数据
    let import_data = json!({
        "version": "keeper-1.0",
        "exportedAt": "2024-01-15T10:30:00Z",
        "tags": [
            {"id": 1, "name": "导入标签", "color": "#FF0000", "icon": "", "createdAt": "2024-01-01T00:00:00Z", "updatedAt": "2024-01-01T00:00:00Z"}
        ],
        "relations": [
            {"id": 1, "name": "导入手机", "type": "phone", "createdAt": "2024-01-01T00:00:00Z", "updatedAt": "2024-01-01T00:00:00Z"}
        ],
        "bookmarks": []
    });

    // 导入数据
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/import")
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::AUTHORIZATION, format!("Bearer {}", &token))
        .body(Body::from(
            json!({"data": import_data}).to_string(),
        ))
        .unwrap();

    let response = app.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();

    // 验证导入结果
    assert_eq!(body["success"], true);
    assert_eq!(body["imported"]["tags"], 1);
    assert_eq!(body["imported"]["relations"], 1);
    assert!(body["errors"].as_array().unwrap().is_empty());

    // 验证标签已写入数据库
    let request = Request::builder()
        .uri("/api/tags")
        .header(header::AUTHORIZATION, format!("Bearer {}", token))
        .body(Body::empty())
        .unwrap();

    let response = app.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(body["data"].as_array().unwrap().len(), 1);
    let tag = &body["data"][0];
    assert_eq!(tag["name"], "导入标签");
}

#[tokio::test]
async fn test_export_import_round_trip() {
    let app = create_test_app().await;
    let token = setup_authenticated_session(&app).await;

    // 1. 创建初始数据
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/tags")
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::AUTHORIZATION, format!("Bearer {}", &token))
        .body(Body::from(json!({"name": "往返测试"}).to_string()))
        .unwrap();
    let _response = app.clone().oneshot(request).await.unwrap();

    // 2. 导出数据
    let request = Request::builder()
        .uri("/api/export")
        .header(header::AUTHORIZATION, format!("Bearer {}", &token))
        .body(Body::empty())
        .unwrap();

    let response = app.clone().oneshot(request).await.unwrap();
    let body = response.into_body().collect().await.unwrap().to_bytes();
    let export_data: Value = serde_json::from_slice(&body).unwrap();

    // 3. 锁定并清除会话
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/lock")
        .header(header::AUTHORIZATION, format!("Bearer {}", &token))
        .body(Body::empty())
        .unwrap();
    let _response = app.clone().oneshot(request).await.unwrap();

    // 4. 重新解锁
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/auth/unlock")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({"password": "test_password_123"}).to_string(),
        ))
        .unwrap();
    let response = app.clone().oneshot(request).await.unwrap();
    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();
    let new_token = body["token"].as_str().unwrap().to_string();

    // 5. 导入刚才导出的数据
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/import")
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::AUTHORIZATION, format!("Bearer {}", &new_token))
        .body(Body::from(json!({"data": export_data}).to_string()))
        .unwrap();

    let response = app.clone().oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();

    // 验证导入成功
    assert_eq!(body["success"], true);

    // 6. 验证标签已恢复
    let request = Request::builder()
        .uri("/api/tags")
        .header(header::AUTHORIZATION, format!("Bearer {}", new_token))
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();

    // 应该有 1 个标签
    assert_eq!(body["data"].as_array().unwrap().len(), 1);
}

#[tokio::test]
async fn test_import_duplicate_handling() {
    let app = create_test_app().await;
    let token = setup_authenticated_session(&app).await;

    // 先创建一些数据
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/tags")
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::AUTHORIZATION, format!("Bearer {}", &token))
        .body(Body::from(json!({"name": "重复标签"}).to_string()))
        .unwrap();
    let _response = app.clone().oneshot(request).await.unwrap();

    // 尝试导入同名标签
    let import_data = json!({
        "version": "keeper-1.0",
        "exportedAt": "2024-01-15T10:30:00Z",
        "tags": [
            {"id": 999, "name": "重复标签", "color": "#FF0000", "icon": "", "createdAt": "2024-01-01T00:00:00Z", "updatedAt": "2024-01-01T00:00:00Z"}
        ],
        "relations": [],
        "bookmarks": []
    });

    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/import")
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::AUTHORIZATION, format!("Bearer {}", &token))
        .body(Body::from(json!({"data": import_data}).to_string()))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&body).unwrap();

    // 应该成功，但标签数不会增加（重复被忽略）
    assert_eq!(body["success"], true);
    assert_eq!(body["imported"]["tags"], 0); // 重复被跳过
    // 错误列表应该是空的（重复不算错误）
    assert!(body["errors"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_export_requires_auth() {
    let app = create_test_app().await;

    // 未认证请求导出
    let request = Request::builder()
        .uri("/api/export")
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_import_requires_auth() {
    let app = create_test_app().await;

    // 未认证请求导入
    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/import")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            json!({"data": {"version": "keeper-1.0", "tags": [], "relations": [], "bookmarks": []}})
                .to_string(),
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}
