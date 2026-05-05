//! 应用状态
//!
//! 包含所有需要在处理器之间共享的状态。

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use rusqlite::Connection;

use crate::session::manager::SessionManager;

/// 应用状态
#[derive(Clone)]
pub struct AppState {
    /// 数据库连接（使用 Arc<Mutex> 包装以支持动态切换）
    pub db: Arc<Mutex<Connection>>,
    /// 会话管理器
    pub session_manager: Arc<SessionManager>,
    /// 配置目录路径（存放 databases.json）
    pub config_dir: Option<PathBuf>,
}

impl AppState {
    /// 创建新的应用状态
    pub fn new(
        db: Connection,
        session_manager: Arc<SessionManager>,
        config_dir: Option<PathBuf>,
    ) -> Self {
        Self {
            db: Arc::new(Mutex::new(db)),
            session_manager,
            config_dir,
        }
    }

    /// 切换数据库连接
    pub fn switch_db(&self, new_db: Connection) {
        let mut db = self.db.lock().unwrap();
        *db = new_db;
    }
}
