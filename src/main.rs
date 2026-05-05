use std::sync::Arc;
use std::time::Duration;

use axum::{
    middleware,
    routing::{get, post, Router},
};
use tower_http::cors::{AllowOrigin, CorsLayer};
use tracing::{info, Level};
use tracing_subscriber::FmtSubscriber;

use keeper::{
    config::Config,
    db::config::DatabaseConfig,
    db::connection::{connect, connect_in_memory},
    handlers::auth::{info, initialize, lock, set_session_timeout, status, unlock},
    handlers::bookmarks::{
        create_bookmark, delete_bookmark, get_bookmark, list_bookmarks, patch_bookmark,
        update_bookmark, use_bookmark,
    },
    handlers::database::{
        add_database, create_database, list_databases, open_database, remove_database,
    },
    handlers::relations::{
        create_relation, delete_relation, get_relation, list_relations, update_relation,
    },
    handlers::stats::get_stats,
    handlers::tags::{create_tag, delete_tag, get_tag, list_tags, update_tag},
    handlers::transfer::{export_data, import_data},
    middleware::auth::auth_middleware,
    session::manager::SessionManager,
    state::AppState,
};

/// 会话有效期：60 分钟
const SESSION_TTL: Duration = Duration::from_secs(3600);

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // 初始化日志
    let subscriber = FmtSubscriber::builder()
        .with_max_level(Level::INFO)
        .finish();
    tracing::subscriber::set_global_default(subscriber)?;

    // 解析命令行配置
    let config = Config::from_args();
    info!("配置: {:?}", config);

    // 加载数据库配置
    let db_config = DatabaseConfig::load_from_config_dir(config.config_dir.as_deref());
    info!(
        "数据库配置加载完成，当前数据库: {:?}",
        db_config.get_current()
    );

    // 根据配置决定是否连接数据库
    // 如果有当前数据库，连接它；否则使用内存数据库等待前端创建/选择
    let conn = if let Some(current_path) = db_config.get_current() {
        let db_path = std::path::PathBuf::from(&current_path);
        info!("使用已配置的数据库: {}", db_path.display());

        if db_path.to_string_lossy() == ":memory:" {
            connect_in_memory()?
        } else {
            connect(&db_path)?
        }
    } else {
        info!("没有配置的数据库，使用内存数据库等待前端创建/选择");
        connect_in_memory()?
    };
    info!("数据库连接成功");

    // 创建共享状态
    let session_manager = Arc::new(SessionManager::new(SESSION_TTL));
    info!("会话管理器初始化完成，TTL: {:?}", SESSION_TTL);

    // 创建应用状态
    let state = AppState::new(conn, session_manager, config.config_dir.clone());

    // 构建路由
    let app = Router::new()
        .route("/", get(root))
        .route("/api/health", get(health))
        // 认证路由（公开）
        .route("/api/auth/initialize", post(initialize))
        .route("/api/auth/unlock", post(unlock))
        .route("/api/auth/lock", post(lock))
        .route("/api/auth/status", get(status))
        .route("/api/auth/info", get(info))
        .route("/api/auth/session-timeout", post(set_session_timeout))
        // 数据库管理路由（公开）
        .route("/api/db/list", get(list_databases))
        .route("/api/db/add", post(add_database))
        .route("/api/db/open", post(open_database))
        .route("/api/db/create", post(create_database))
        .route("/api/db/remove", post(remove_database))
        // 标签路由（受保护）
        .route("/api/tags", get(list_tags).post(create_tag))
        .route(
            "/api/tags/:id",
            get(get_tag).put(update_tag).delete(delete_tag),
        )
        // 关联路由（受保护）
        .route("/api/relations", get(list_relations).post(create_relation))
        .route(
            "/api/relations/:id",
            get(get_relation)
                .put(update_relation)
                .delete(delete_relation),
        )
        // 书签路由（受保护）
        .route("/api/bookmarks", get(list_bookmarks).post(create_bookmark))
        .route(
            "/api/bookmarks/:id",
            get(get_bookmark)
                .put(update_bookmark)
                .patch(patch_bookmark)
                .delete(delete_bookmark),
        )
        .route("/api/bookmarks/:id/use", post(use_bookmark))
        // 统计路由（受保护）
        .route("/api/stats", get(get_stats))
        // 导入导出路由（受保护）
        .route("/api/export", post(export_data))
        .route("/api/import", post(import_data))
        // 认证中间件
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ))
        // CORS 配置
        .layer(create_cors_layer())
        // 共享状态
        .with_state(state.clone());

    // 启动服务器
    let addr = format!("{}:{}", config.host, config.port);
    info!("启动服务器: http://{}", addr);

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    let server = axum::serve(listener, app).with_graceful_shutdown(async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
        info!("收到退出信号，正在优雅关闭服务器...");
    });

    server.await?;
    info!("服务器已关闭");

    // 等待所有 spawn_blocking 任务完成
    tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;

    // 显式关闭数据库连接
    if let Ok(db_lock) = Arc::try_unwrap(state.db) {
        let _conn = db_lock.into_inner();
        info!("正在显式关闭数据库连接...");
        // 同步 rusqlite 连接在 drop 时自动关闭
        info!("数据库连接已安全关闭");
    }

    Ok(())
}

/// 创建 CORS 配置层
///
/// 允许浏览器扩展（moz-extension://* 和 chrome-extension://*）访问
fn create_cors_layer() -> CorsLayer {
    CorsLayer::new()
        // 允许浏览器扩展 origin
        .allow_origin(AllowOrigin::predicate(|origin, _request_head| {
            let origin_str = origin.to_str().unwrap_or("");
            // 允许 localhost（开发环境）
            if origin_str.starts_with("http://localhost")
                || origin_str.starts_with("http://127.0.0.1")
            {
                return true;
            }
            // 允许浏览器扩展
            if origin_str.starts_with("moz-extension://")
                || origin_str.starts_with("chrome-extension://")
                || origin_str.starts_with("safari-extension://")
            {
                return true;
            }
            false
        }))
        .allow_methods([
            axum::http::Method::GET,
            axum::http::Method::POST,
            axum::http::Method::PUT,
            axum::http::Method::PATCH,
            axum::http::Method::DELETE,
        ])
        .allow_headers([
            axum::http::header::AUTHORIZATION,
            axum::http::header::CONTENT_TYPE,
            axum::http::header::ACCEPT,
            axum::http::header::COOKIE,
        ])
        .expose_headers([axum::http::header::SET_COOKIE])
        .allow_credentials(true)
}

async fn root() -> &'static str {
    "Keeper API v1.0.0"
}

async fn health() -> &'static str {
    "{\"status\":\"healthy\"}"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cors_allows_browser_extensions() {
        // 测试 CORS 配置允许浏览器扩展 origin
        let _layer = create_cors_layer();
        // 实际测试需要通过 HTTP 请求验证
    }
}
