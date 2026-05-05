//! 数据模型定义
//!
//! 与 Python SQLAlchemy 模型完全对齐，确保数据兼容性。

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// 标签
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tag {
    pub id: i64,
    pub name: String,
    pub color: String,
    pub icon: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Tag {
    pub fn new(id: i64, name: String) -> Self {
        let now = Utc::now();
        Self {
            id,
            name,
            color: "#3B82F6".to_string(), // 默认蓝色
            icon: String::new(),
            created_at: now,
            updated_at: now,
        }
    }
}

/// 关联关系类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RelationType {
    Phone,
    Email,
    Idcard,
    Social,
    Other,
}

impl RelationType {
    pub fn as_str(&self) -> &'static str {
        match self {
            RelationType::Phone => "phone",
            RelationType::Email => "email",
            RelationType::Idcard => "idcard",
            RelationType::Social => "social",
            RelationType::Other => "other",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "phone" => Some(RelationType::Phone),
            "email" => Some(RelationType::Email),
            "idcard" => Some(RelationType::Idcard),
            "social" => Some(RelationType::Social),
            "other" => Some(RelationType::Other),
            _ => None,
        }
    }
}

/// 关联关系
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Relation {
    pub id: i64,
    pub name: String,
    pub value: Option<String>,
    pub r#type: RelationType,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Relation {
    pub fn new(id: i64, name: String, r#type: RelationType) -> Self {
        let now = Utc::now();
        Self {
            id,
            name,
            value: None,
            r#type,
            created_at: now,
            updated_at: now,
        }
    }
}

/// URL 条目
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UrlEntry {
    pub url: String,
    #[serde(rename = "lastUsed")]
    pub last_used: Option<DateTime<Utc>>,
}

/// 账户条目
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccountEntry {
    pub id: i64,
    pub username: String,
    pub password: String, // 加密后的密文
    #[serde(rename = "relatedIds")]
    pub related_ids: Vec<i64>,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "lastUsed")]
    pub last_used: DateTime<Utc>,
}

/// 书签/密码条目
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Bookmark {
    pub id: String, // UUID v4
    pub name: String,
    #[serde(rename = "pinyinInitials")]
    pub pinyin_initials: String,
    #[serde(rename = "pinyinFull")]
    pub pinyin_full: String,
    #[serde(rename = "tagIds")]
    pub tag_ids: Vec<i64>,
    pub urls: Vec<UrlEntry>,
    pub notes: String,
    pub accounts: Vec<AccountEntry>,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "updatedAt")]
    pub updated_at: DateTime<Utc>,
    #[serde(rename = "lastUsedAt")]
    pub last_used_at: DateTime<Utc>,
}

impl Bookmark {
    pub fn new(id: String, name: String) -> Self {
        let now = Utc::now();
        Self {
            id,
            name,
            pinyin_initials: String::new(),
            pinyin_full: String::new(),
            tag_ids: Vec::new(),
            urls: Vec::new(),
            notes: String::new(),
            accounts: Vec::new(),
            created_at: now,
            updated_at: now,
            last_used_at: now,
        }
    }
}

/// 认证信息（单用户）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Authentication {
    pub id: i64, // 固定为 1
    pub email: String,
    #[serde(rename = "passwordHash")]
    pub password_hash: String,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "lastLogin")]
    pub last_login: DateTime<Utc>,
}

impl Authentication {
    pub fn new(email: String, password_hash: String) -> Self {
        let now = Utc::now();
        Self {
            id: 1,
            email,
            password_hash,
            created_at: now,
            last_login: now,
        }
    }
}

// 数据库行转换实现
use rusqlite::{Result as SqliteResult, Row};

impl Tag {
    pub fn from_row(row: &Row) -> SqliteResult<Self> {
        Ok(Self {
            id: row.get("id")?,
            name: row.get("name")?,
            color: row.get("color")?,
            icon: row.get("icon")?,
            created_at: row.get("created_at")?,
            updated_at: row.get("updated_at")?,
        })
    }
}

impl Relation {
    pub fn from_row(row: &Row) -> SqliteResult<Self> {
        let type_str: String = row.get("type")?;
        Ok(Self {
            id: row.get("id")?,
            name: row.get("name")?,
            value: row.get("value")?,
            r#type: RelationType::from_str(&type_str).unwrap_or(RelationType::Other),
            created_at: row.get("created_at")?,
            updated_at: row.get("updated_at")?,
        })
    }
}

impl Bookmark {
    pub fn from_row(row: &Row) -> SqliteResult<Self> {
        let tag_ids_json: String = row.get("tag_ids")?;
        let urls_json: String = row.get("urls")?;
        let accounts_json: String = row.get("accounts")?;

        Ok(Self {
            id: row.get("id")?,
            name: row.get("name")?,
            pinyin_initials: row.get("pinyin_initials")?,
            pinyin_full: row.get("pinyin_full")?,
            tag_ids: serde_json::from_str(&tag_ids_json).unwrap_or_default(),
            urls: serde_json::from_str(&urls_json).unwrap_or_default(),
            notes: row.get("notes")?,
            accounts: serde_json::from_str(&accounts_json).unwrap_or_default(),
            created_at: row.get("created_at")?,
            updated_at: row.get("updated_at")?,
            last_used_at: row.get("last_used_at")?,
        })
    }
}

impl Authentication {
    pub fn from_row(row: &Row) -> SqliteResult<Self> {
        Ok(Self {
            id: row.get("id")?,
            email: row.get("email")?,
            password_hash: row.get("password_hash")?,
            created_at: row.get("created_at")?,
            last_login: row.get("last_login")?,
        })
    }
}
