//! 会话管理模块
//!
//! 内存 Session 管理，支持创建、验证和撤销会话。

use std::sync::atomic::{AtomicU64, Ordering};
use std::{
    sync::Mutex,
    time::{Duration, Instant},
};

use base64::Engine;
use rand::Rng;

/// 会话信息
#[derive(Debug, Clone)]
pub struct Session {
    /// 会话令牌
    pub token: String,
    /// 加密密钥（32 字节，用于 AES-256-GCM）
    pub encryption_key: [u8; 32],
    /// 创建时间
    pub created_at: Instant,
    /// 最后活动时间
    pub last_activity_at: Instant,
    /// 过期时间
    pub expires_at: Instant,
}

impl Session {
    /// 创建新会话
    pub fn new(token: String, encryption_key: [u8; 32], ttl: Duration) -> Self {
        let now = Instant::now();
        Self {
            token,
            encryption_key,
            created_at: now,
            last_activity_at: now,
            expires_at: now + ttl,
        }
    }

    /// 检查会话是否过期
    pub fn is_expired(&self) -> bool {
        Instant::now() > self.expires_at
    }

    /// 获取剩余有效时间
    pub fn remaining_ttl(&self) -> Duration {
        if self.is_expired() {
            Duration::ZERO
        } else {
            self.expires_at - Instant::now()
        }
    }
}

/// 会话管理器
///
/// 单用户系统，同一时间只有一个活跃会话。
pub struct SessionManager {
    /// 当前会话（单用户，所以用 Option）
    session: Mutex<Option<Session>>,
    /// 会话有效期（毫秒）
    ttl_millis: AtomicU64,
}

impl SessionManager {
    /// 创建新的会话管理器
    pub fn new(ttl: Duration) -> Self {
        Self {
            session: Mutex::new(None),
            ttl_millis: AtomicU64::new(ttl.as_millis() as u64),
        }
    }

    /// 设置会话有效期
    pub fn set_ttl(&self, ttl: Duration) {
        self.ttl_millis.store(ttl.as_millis() as u64, Ordering::Relaxed);
    }

    /// 获取当前会话有效期
    pub fn ttl(&self) -> Duration {
        Duration::from_millis(self.ttl_millis.load(Ordering::Relaxed))
    }

    /// 创建新会话
    ///
    /// # Arguments
    /// * `encryption_key` - 加密密钥（32 字节）
    ///
    /// # Returns
    /// 会话令牌（URL-safe Base64，256-bit 熵）
    pub fn create(&self, encryption_key: [u8; 32]) -> String {
        // 生成随机令牌：32 字节 = 256-bit 熵
        let token_bytes: [u8; 32] = rand::thread_rng().gen();
        let token = base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(token_bytes);

        let session = Session::new(token.clone(), encryption_key, self.ttl());

        let mut guard = self.session.lock().unwrap();
        *guard = Some(session);

        token
    }

    /// 验证会话令牌
    ///
    /// # Arguments
    /// * `token` - 会话令牌
    ///
    /// # Returns
    /// 验证通过返回 Session 的克隆，失败返回 None
    pub fn validate(&self, token: &str) -> Option<Session> {
        let mut guard = self.session.lock().unwrap();

        if let Some(ref mut session) = *guard {
            if session.is_expired() {
                return None;
            }

            // 常量时间比较，防止时序攻击
            if constant_time_eq(session.token.as_bytes(), token.as_bytes()) {
                // 滑动窗口：更新最后活动时间和过期时间
                let now = Instant::now();
                session.last_activity_at = now;
                session.expires_at = now + self.ttl();
                return Some(session.clone());
            }
        }

        None
    }

    /// 验证会话令牌，如果过期则清除
    ///
    /// 与 `validate` 不同，此方法会在会话过期时自动清除会话。
    pub fn validate_and_clean(&self, token: &str) -> Option<Session> {
        let mut guard = self.session.lock().unwrap();

        tracing::info!("validate_and_clean called with token: {}", &token[..10.min(token.len())]);
        
        if let Some(ref mut session) = *guard {
            tracing::info!("Stored session token: {}", &session.token[..10.min(session.token.len())]);
            tracing::info!("Session expired: {}", session.is_expired());
            
            if session.is_expired() {
                // 会话过期，清除
                tracing::warn!("Session expired, clearing");
                *guard = None;
                return None;
            }

            // 常量时间比较
            let matches = constant_time_eq(session.token.as_bytes(), token.as_bytes());
            tracing::info!("Token matches: {}", matches);
            
            if matches {
                // 滑动窗口：更新最后活动时间和过期时间
                let now = Instant::now();
                session.last_activity_at = now;
                session.expires_at = now + self.ttl();
                return Some(session.clone());
            }
        } else {
            tracing::warn!("No session stored");
        }

        None
    }

    /// 撤销当前会话
    pub fn revoke(&self) {
        let mut guard = self.session.lock().unwrap();
        *guard = None;
    }

    /// 获取当前会话（不验证）
    pub fn get_session(&self) -> Option<Session> {
        let guard = self.session.lock().unwrap();
        guard.clone()
    }
}

/// 常量时间比较两个字节切片
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut result = 0u8;
    for (x, y) in a.iter().zip(b.iter()) {
        result |= x ^ y;
    }
    result == 0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_key() -> [u8; 32] {
        [0u8; 32]
    }

    #[test]
    fn test_create_and_validate() {
        let manager = SessionManager::new(Duration::from_secs(3600));
        let key = test_key();

        let token = manager.create(key);
        assert!(!token.is_empty());
        assert_eq!(token.len(), 43); // 32 字节 base64 URL-safe 无 padding = 43 字符

        let session = manager.validate(&token).unwrap();
        assert_eq!(session.token, token);
        assert_eq!(session.encryption_key, key);
    }

    #[test]
    fn test_validate_invalid_token() {
        let manager = SessionManager::new(Duration::from_secs(3600));
        let key = test_key();

        let valid_token = manager.create(key);

        // 验证无效令牌失败
        let result = manager.validate("invalid_token");
        assert!(result.is_none());

        // 有效令牌仍然可以验证（验证失败不清除会话）
        assert!(manager.validate(&valid_token).is_some());
    }

    #[test]
    fn test_validate_and_clean_expired() {
        let manager = SessionManager::new(Duration::from_millis(10));
        let key = test_key();

        let token = manager.create(key);

        // 立即验证应该成功
        assert!(manager.validate_and_clean(&token).is_some());

        // 等待过期
        std::thread::sleep(Duration::from_millis(20));

        // 过期后 validate_and_clean 应该失败并清除会话
        assert!(manager.validate_and_clean(&token).is_none());
        // 会话已被清除
        assert!(manager.get_session().is_none());
    }

    #[test]
    fn test_session_expires() {
        let manager = SessionManager::new(Duration::from_millis(10));
        let key = test_key();

        let token = manager.create(key);

        // 立即验证应该成功
        assert!(manager.validate(&token).is_some());

        // 等待过期
        std::thread::sleep(Duration::from_millis(20));

        // 过期后验证应该失败
        assert!(manager.validate(&token).is_none());
    }

    #[test]
    fn test_revoke() {
        let manager = SessionManager::new(Duration::from_secs(3600));
        let key = test_key();

        let token = manager.create(key);
        assert!(manager.validate(&token).is_some());

        manager.revoke();

        assert!(manager.validate(&token).is_none());
    }

    #[test]
    fn test_session_remaining_ttl() {
        let ttl = Duration::from_secs(3600);
        let session = Session::new("token".to_string(), test_key(), ttl);

        let remaining = session.remaining_ttl();
        // 应该接近 3600 秒
        assert!(remaining > Duration::from_secs(3599));
        assert!(remaining <= ttl);
    }

    #[test]
    fn test_constant_time_eq() {
        let a = b"hello";
        let b = b"hello";
        let c = b"world";
        let d = b"hell";

        assert!(constant_time_eq(a, b));
        assert!(!constant_time_eq(a, c));
        assert!(!constant_time_eq(a, d));
        assert!(!constant_time_eq(d, a));
    }

    #[test]
    fn test_multiple_create_replaces_session() {
        let manager = SessionManager::new(Duration::from_secs(3600));
        let key1 = [1u8; 32];
        let key2 = [2u8; 32];

        let token1 = manager.create(key1);
        let token2 = manager.create(key2);

        // 新会话替换旧会话
        assert!(manager.validate(&token1).is_none());
        assert!(manager.validate(&token2).is_some());
    }

    #[test]
    fn test_sliding_window() {
        let manager = SessionManager::new(Duration::from_millis(50));
        let key = test_key();

        let token = manager.create(key);

        // 第一次验证刷新过期时间
        assert!(manager.validate(&token).is_some());

        // 等待接近原始 TTL 但还没过期
        std::thread::sleep(Duration::from_millis(40));
        // 由于滑动窗口，验证会再次刷新时间，仍然有效
        assert!(manager.validate(&token).is_some());

        // 再等待接近原始 TTL
        std::thread::sleep(Duration::from_millis(40));
        // 仍然有效
        assert!(manager.validate(&token).is_some());
    }

    #[test]
    fn test_set_ttl() {
        let manager = SessionManager::new(Duration::from_secs(600));
        assert_eq!(manager.ttl(), Duration::from_secs(600));

        manager.set_ttl(Duration::from_secs(1200));
        assert_eq!(manager.ttl(), Duration::from_secs(1200));
    }
}
