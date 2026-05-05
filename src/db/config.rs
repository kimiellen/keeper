//! 数据库配置管理
//!
//! 管理已知数据库列表和当前选中数据库的配置文件。
//! 配置文件默认位于 ~/.local/share/keeper/databases.json

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// 数据库信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DatabaseInfo {
    pub path: String,
    pub name: String,
}

/// 数据库配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DatabaseConfig {
    pub databases: Vec<DatabaseInfo>,
    pub current: Option<String>,
    #[serde(skip)]
    config_dir: Option<PathBuf>,
}

impl Default for DatabaseConfig {
    fn default() -> Self {
        Self {
            databases: Vec::new(),
            current: None,
            config_dir: None,
        }
    }
}

impl DatabaseConfig {
    /// 获取默认配置文件路径
    fn default_config_path() -> PathBuf {
        dirs::data_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("keeper")
            .join("databases.json")
    }

    /// 获取配置文件路径
    fn config_path(&self) -> PathBuf {
        match self.config_dir.as_deref() {
            Some(dir) => Self::config_path_with_dir(dir),
            None => Self::default_config_path(),
        }
    }

    /// 从指定目录获取配置文件路径
    fn config_path_with_dir(config_dir: &Path) -> PathBuf {
        config_dir.join("databases.json")
    }

    /// 加载配置（使用默认路径）
    pub fn load() -> Self {
        Self::load_from_path(Self::default_config_path())
    }

    /// 从指定配置目录加载
    pub fn load_from_config_dir(config_dir: Option<&Path>) -> Self {
        Self::load_from_path_with_config_dir(
            match config_dir {
                Some(dir) => Self::config_path_with_dir(dir),
                None => Self::default_config_path(),
            },
            config_dir.map(Path::to_path_buf),
        )
    }

    /// 从指定路径加载配置
    fn load_from_path(path: PathBuf) -> Self {
        Self::load_from_path_with_config_dir(path, None)
    }

    /// 从指定路径加载配置，并记录配置目录
    fn load_from_path_with_config_dir(path: PathBuf, config_dir: Option<PathBuf>) -> Self {
        eprintln!("[Keeper] 尝试加载配置: {}", path.display());
        if !path.exists() {
            eprintln!("[Keeper] 配置文件不存在，使用默认配置");
            let mut config = Self::default();
            config.config_dir = config_dir;
            return config;
        }

        match std::fs::read_to_string(&path) {
            Ok(content) => {
                let mut config = serde_json::from_str::<Self>(&content).unwrap_or_default();
                config.config_dir = config_dir;
                config
            }
            Err(_) => {
                let mut config = Self::default();
                config.config_dir = config_dir;
                config
            }
        }
    }

    /// 保存配置
    fn save(&self) -> Result<(), String> {
        let path = self.config_path();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| format!("创建配置目录失败: {}", e))?;
        }

        let content =
            serde_json::to_string_pretty(self).map_err(|e| format!("序列化配置失败: {}", e))?;

        std::fs::write(&path, content).map_err(|e| format!("写入配置失败: {}", e))
    }

    /// 获取数据库列表
    pub fn get_databases(&self) -> Vec<DatabaseInfo> {
        self.databases.clone()
    }

    /// 获取当前数据库路径
    pub fn get_current(&self) -> Option<String> {
        self.current.clone()
    }

    /// 添加数据库到列表
    pub fn add_database(&mut self, path: &str) -> Result<(), String> {
        let path = shellexpand::tilde(path).to_string();

        // 检查是否已存在
        if self.databases.iter().any(|db| db.path == path) {
            return Ok(());
        }

        let name = Path::new(&path)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown.db")
            .to_string();

        self.databases.push(DatabaseInfo { path, name });
        self.save()
    }

    /// 设置当前数据库
    pub fn set_current(&mut self, path: &str) -> Result<(), String> {
        let path = shellexpand::tilde(path).to_string();

        // 确保在列表中
        self.add_database(&path)?;

        self.current = Some(path);
        self.save()
    }

    /// 从列表中移除数据库
    pub fn remove_database(&mut self, path: &str) -> Result<(), String> {
        let path = shellexpand::tilde(path).to_string();

        // 不能移除当前正在使用的数据库
        if self.current.as_ref() == Some(&path) {
            return Err("不能移除当前正在使用的数据库".to_string());
        }

        self.databases.retain(|db| db.path != path);
        self.save()
    }

    /// 清理不存在的数据库文件
    pub fn cleanup(&mut self) -> Result<(), String> {
        self.databases.retain(|db| Path::new(&db.path).exists());

        if let Some(ref current) = self.current {
            if !Path::new(current).exists() {
                self.current = None;
            }
        }

        self.save()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_database_config_default() {
        let config = DatabaseConfig::default();
        assert!(config.databases.is_empty());
        assert!(config.current.is_none());
    }

    #[test]
    fn test_save_uses_custom_config_dir() {
        let temp_dir = tempdir().unwrap();
        let config_dir = temp_dir.path();
        let db_path = config_dir.join("vault.db");

        let mut config = DatabaseConfig::load_from_config_dir(Some(config_dir));
        assert!(config.get_databases().is_empty());

        config.add_database(db_path.to_str().unwrap()).unwrap();

        let config_path = config_dir.join("databases.json");
        assert!(config_path.exists());

        let content = std::fs::read_to_string(config_path).unwrap();
        assert!(content.contains("vault.db"));
    }
}
