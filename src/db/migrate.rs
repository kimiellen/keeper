//! 数据库迁移模块
//!
//! 创建与 Python 版本完全一致的表结构。

use rusqlite::Connection;

use crate::error::Result;

/// 创建所有表和索引
pub fn migrate(conn: &mut Connection) -> Result<()> {

    // 创建 tags 表
    conn.execute(
        r#"
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT NOT NULL DEFAULT '#3B82F6',
            icon TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        "#,
        [],
    )?;

    // tags 索引
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)",
        [],
    )?;

    // 创建 relations 表
    conn.execute(
        r#"
        CREATE TABLE IF NOT EXISTS relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            value TEXT,
            type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (type IN ('phone', 'email', 'idcard', 'social', 'other'))
        )
        "#,
        [],
    )?;

    // relations 索引
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(type)",
        [],
    )?;

    // 创建 bookmarks 表
    conn.execute(
        r#"
        CREATE TABLE IF NOT EXISTS bookmarks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            pinyin_initials TEXT NOT NULL,
            pinyin_full TEXT NOT NULL DEFAULT '',
            tag_ids TEXT NOT NULL DEFAULT '[]',
            urls TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            accounts TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL
        )
        "#,
        [],
    )?;

    // bookmarks 索引
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookmarks_name ON bookmarks(name)",
        [],
    )?;
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookmarks_pinyin ON bookmarks(pinyin_initials)",
        [],
    )?;
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookmarks_pinyin_full ON bookmarks(pinyin_full)",
        [],
    )?;
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookmarks_last_used ON bookmarks(last_used_at DESC)",
        [],
    )?;

    // 创建 authentication 表
    conn.execute(
        r#"
        CREATE TABLE IF NOT EXISTS authentication (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT NOT NULL,
            CHECK (id = 1)
        )
        "#,
        [],
    )?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;

    #[test]
    fn test_migrate_creates_tables() {
        let mut conn = Connection::open_in_memory().unwrap();
        migrate(&mut conn).unwrap();

        // 验证表存在
        let mut stmt = conn.prepare("SELECT name FROM sqlite_master WHERE type='table'").unwrap();
        let rows = stmt.query_map([], |row| row.get::<_, String>(0)).unwrap();
        let tables: Vec<String> = rows.collect::<std::result::Result<Vec<_>, _>>().unwrap();

        assert!(tables.contains(&"tags".to_string()));
        assert!(tables.contains(&"relations".to_string()));
        assert!(tables.contains(&"bookmarks".to_string()));
        assert!(tables.contains(&"authentication".to_string()));
    }

    #[test]
    fn test_migrate_creates_indexes() {
        let mut conn = Connection::open_in_memory().unwrap();
        migrate(&mut conn).unwrap();

        // 验证索引存在
        let mut stmt = conn.prepare("SELECT name FROM sqlite_master WHERE type='index'").unwrap();
        let rows = stmt.query_map([], |row| row.get::<_, String>(0)).unwrap();
        let indexes: Vec<String> = rows.collect::<std::result::Result<Vec<_>, _>>().unwrap();

        assert!(indexes.contains(&"idx_tags_name".to_string()));
        assert!(indexes.contains(&"idx_relations_type".to_string()));
        assert!(indexes.contains(&"idx_bookmarks_name".to_string()));
        assert!(indexes.contains(&"idx_bookmarks_pinyin".to_string()));
        assert!(indexes.contains(&"idx_bookmarks_pinyin_full".to_string()));
        assert!(indexes.contains(&"idx_bookmarks_last_used".to_string()));
    }
}
