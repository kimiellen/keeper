use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("SQLite 错误: {0}")]
    Database(#[from] rusqlite::Error),

    #[error("加密错误: {0}")]
    Crypto(String),

    #[error("认证错误: {0}")]
    Auth(String),

    #[error("未找到: {0}")]
    NotFound(String),

    #[error("冲突: {0}")]
    Conflict(String),

    #[error("参数错误: {0}")]
    BadRequest(String),

    #[error("内部错误: {0}")]
    Internal(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, error_type, detail) = match &self {
            AppError::NotFound(msg) => (
                StatusCode::NOT_FOUND,
                "not-found",
                msg.clone(),
            ),
            AppError::Conflict(msg) => (
                StatusCode::CONFLICT,
                "conflict",
                msg.clone(),
            ),
            AppError::Auth(msg) => (
                StatusCode::UNAUTHORIZED,
                "unauthorized",
                msg.clone(),
            ),
            AppError::BadRequest(msg) => (
                StatusCode::BAD_REQUEST,
                "bad-request",
                msg.clone(),
            ),
            _ => (
                StatusCode::INTERNAL_SERVER_ERROR,
                "internal-error",
                self.to_string(),
            ),
        };

        let body = Json(json!({
            "type": format!("https://keeper.local/errors/{}", error_type),
            "title": match status {
                StatusCode::NOT_FOUND => "未找到",
                StatusCode::CONFLICT => "冲突",
                StatusCode::UNAUTHORIZED => "未授权",
                StatusCode::BAD_REQUEST => "参数错误",
                _ => "服务器错误",
            },
            "status": status.as_u16(),
            "detail": detail,
        }));

        (status, body).into_response()
    }
}

pub type Result<T> = std::result::Result<T, AppError>;
