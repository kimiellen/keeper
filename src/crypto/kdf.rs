//! 密钥派生模块
//!
//! 使用 Argon2id 进行：
//! 1. 主密码哈希存储（用于验证）
//! 2. 加密密钥派生（用于 AES-256-GCM 加解密）

use argon2::{
    password_hash::{
        rand_core::OsRng,
        PasswordHash, PasswordHasher, PasswordVerifier, SaltString,
    },
    Argon2, Params,
};
use ring::pbkdf2;
use ring::pbkdf2::PBKDF2_HMAC_SHA256;
use std::num::NonZeroU32;

/// Argon2id 参数（与 Python 版本一致）
/// time_cost=3, memory_cost=65536 (64 MiB), parallelism=1
fn argon2_instance() -> Argon2<'static> {
    let params = Params::new(65536, 3, 1, Some(32))
        .expect("valid argon2 params");
    Argon2::new(argon2::Algorithm::Argon2id, argon2::Version::V0x13, params)
}

/// 派生加密密钥时使用的固定上下文标识（与 Python 版本一致）
const KEY_DERIVE_INFO: &[u8] = b"keeper-encryption-key-v1";

/// 对主密码进行 Argon2id 哈希，用于存储和后续验证。
///
/// 每次调用生成不同的随机盐，返回的哈希字符串包含所有参数信息。
///
/// # Arguments
/// * `password` - 明文主密码
///
/// # Returns
/// Argon2id 哈希字符串（含算法参数和盐）
pub fn hash_password(password: &str) -> String {
    let argon2 = argon2_instance();
    let salt = SaltString::generate(&mut OsRng);
    argon2
        .hash_password(password.as_bytes(), &salt)
        .expect("argon2 hash should not fail")
        .to_string()
}

/// 验证明文密码是否与存储的 Argon2id 哈希匹配。
///
/// # Arguments
/// * `password` - 待验证的明文密码
/// * `password_hash` - 存储的 Argon2id 哈希字符串
///
/// # Returns
/// 验证通过返回 true，否则返回 false
pub fn verify_password(password: &str, password_hash: &str) -> bool {
    let argon2 = argon2_instance();
    let parsed_hash = match PasswordHash::new(password_hash) {
        Ok(h) => h,
        Err(_) => return false,
    };
    argon2
        .verify_password(password.as_bytes(), &parsed_hash)
        .is_ok()
}

/// 从主密码确定性派生 32 字节加密密钥（AES-256 用）。
///
/// 使用 PBKDF2-HMAC-SHA256 配合固定的上下文盐，确保相同密码始终生成相同密钥。
///
/// # Arguments
/// * `password` - 明文主密码
///
/// # Returns
/// 32 字节加密密钥
pub fn derive_key(password: &str) -> [u8; 32] {
    let mut key = [0u8; 32];
    pbkdf2::derive(
        PBKDF2_HMAC_SHA256,
        NonZeroU32::new(100_000).unwrap(),
        KEY_DERIVE_INFO,
        password.as_bytes(),
        &mut key,
    );
    key
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hash_and_verify_password() {
        let password = "test_password_123";
        let hash = hash_password(password);
        
        // 验证正确密码
        assert!(verify_password(password, &hash));
        
        // 验证错误密码
        assert!(!verify_password("wrong_password", &hash));
        
        // 每次哈希结果不同（随机盐）
        let hash2 = hash_password(password);
        assert_ne!(hash, hash2);
        assert!(verify_password(password, &hash2));
    }

    #[test]
    fn test_derive_key_deterministic() {
        let password = "my_master_password";
        
        let key1 = derive_key(password);
        let key2 = derive_key(password);
        
        // 相同密码派生相同密钥
        assert_eq!(key1, key2);
        
        // 不同密码派生不同密钥
        let key3 = derive_key("different_password");
        assert_ne!(key1, key3);
    }

    #[test]
    fn test_derive_key_length() {
        let key = derive_key("any_password");
        assert_eq!(key.len(), 32);
    }
}
