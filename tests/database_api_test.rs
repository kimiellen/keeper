//! 数据库管理 API 集成测试

use std::{sync::Arc, time::Duration};

use axum::{
    body::Body,
    http::{header, Method, Request, StatusCode},
    routing::{get, post},
    Router,
};
use keeper::{
    db::connection::connect_in_memory,
    handlers::database::{
        add_database, create_database, list_databases, open_database, remove_database,
    },
    session::manager::SessionManager,
    state::AppState,
};
use tempfile::tempdir;
use tower::util::ServiceExt;

async fn create_test_app(config_dir: std::path::PathBuf) -> Router {
    let conn = connect_in_memory().unwrap();
    let session_manager = Arc::new(SessionManager::new(Duration::from_secs(3600)));
    let state = AppState::new(conn, session_manager, Some(config_dir));

    Router::new()
        .route("/api/db/list", get(list_databases))
        .route("/api/db/add", post(add_database))
        .route("/api/db/open", post(open_database))
        .route("/api/db/create", post(create_database))
        .route("/api/db/remove", post(remove_database))
        .with_state(state)
}

#[tokio::test]
async fn test_create_database_writes_config_to_custom_dir() {
    let temp_dir = tempdir().unwrap();
    let config_dir = temp_dir.path().join("config");
    let app = create_test_app(config_dir.clone()).await;
    let db_path = temp_dir.path().join("keeper.db");

    let request = Request::builder()
        .method(Method::POST)
        .uri("/api/db/create")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            serde_json::json!({
                "path": db_path,
                "email": "test@example.com",
                "password": "password123"
            })
            .to_string(),
        ))
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let config_path = config_dir.join("databases.json");
    assert!(config_path.exists());

    let content = std::fs::read_to_string(config_path).unwrap();
    assert!(content.contains(db_path.to_str().unwrap()));
}

#[tokio::test]
async fn test_list_databases_reads_existing_custom_config() {
    let temp_dir = tempdir().unwrap();
    let config_dir = temp_dir.path().join("config");
    std::fs::create_dir_all(&config_dir).unwrap();

    let db_path = temp_dir.path().join("existing.db");
    std::fs::write(&db_path, []).unwrap();
    std::fs::write(
        config_dir.join("databases.json"),
        serde_json::json!({
            "databases": [
                {
                    "path": db_path,
                    "name": "existing.db"
                }
            ],
            "current": db_path,
        })
        .to_string(),
    )
    .unwrap();

    let app = create_test_app(config_dir).await;
    let request = Request::builder()
        .method(Method::GET)
        .uri("/api/db/list")
        .body(Body::empty())
        .unwrap();

    let response = app.oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let body = http_body_util::BodyExt::collect(response.into_body())
        .await
        .unwrap()
        .to_bytes();
    let body: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(body["current"], db_path.to_str().unwrap());
    assert_eq!(body["databases"][0]["name"], "existing.db");
}
