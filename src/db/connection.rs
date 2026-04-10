//! 数据库连接管理
//!
//! 管理 SQLite 连接和 PRAGMA 设置。

use std::path::Path;

use rusqlite::Connection;

use crate::db::migrate::migrate;
use crate::error::{AppError, Result};

/// 连接到指定路径的 SQLite 数据库
///
/// 设置以下 PRAGMA：
/// - journal_mode = DELETE
/// - synchronous = FULL
/// - foreign_keys = ON
/// - cache_size = -8000 (8 MB)
pub fn connect<P: AsRef<Path>>(path: P) -> Result<Connection> {
    let path = path.as_ref();
    let mut conn = Connection::open(path).map_err(AppError::Database)?;

    // 设置 PRAGMA
    conn.pragma_update(None, "busy_timeout", 5000)?;
    
    conn.execute_batch(
        r#"
        PRAGMA journal_mode = DELETE;
        PRAGMA synchronous = FULL;
        PRAGMA foreign_keys = ON;
        PRAGMA cache_size = -8000;
        "#,
    )?;

    // 执行迁移
    migrate(&mut conn)?;

    Ok(conn)
}

/// 创建内存数据库连接（用于测试）
pub fn connect_in_memory() -> Result<Connection> {
    let mut conn = Connection::open_in_memory()
        .map_err(AppError::Database)?;

    // 设置 PRAGMA（内存数据库不支持 WAL，会报错）
    conn.execute_batch(
        r#"
        PRAGMA foreign_keys = ON;
        PRAGMA cache_size = -8000;
        "#,
    )?;

    // 执行迁移
    migrate(&mut conn)?;

    Ok(conn)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_connect_in_memory() {
        let conn = connect_in_memory().unwrap();

        // 验证外键开启
        let fk_enabled: bool = {
            let mut stmt = conn.prepare("PRAGMA foreign_keys").unwrap();
            stmt.query_row([], |row| row.get(0)).unwrap()
        };

        assert!(fk_enabled);
    }

    #[test]
    fn test_migrate_runs_on_connect() {
        let conn = connect_in_memory().unwrap();

        // 验证表已创建
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tags'",
            [],
            |row| row.get(0),
        ).unwrap();

        assert_eq!(count, 1);
    }
}
