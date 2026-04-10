//! 数据加密模块
//!
//! 使用 AES-256-GCM 进行认证加密，密文格式为版本化的 Base64 编码。
//! 格式：v1.AES_GCM.<nonce_b64>.<ciphertext_b64>.<tag_b64>

use aes_gcm::{
    aead::{Aead, KeyInit},
    Aes256Gcm, Nonce,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::Rng;

use crate::error::{AppError, Result};

// 常量
const NONCE_SIZE: usize = 12; // 96-bit nonce（GCM 推荐值）
const TAG_SIZE: usize = 16; // 128-bit 认证标签
const VERSION: &str = "v1";
const ALGORITHM: &str = "AES_GCM";

/// AES-256-GCM 加密服务
pub struct EncryptionService {
    cipher: Aes256Gcm,
}

impl EncryptionService {
    /// 初始化加密服务
    ///
    /// # Arguments
    /// * `key` - 256-bit (32 字节) 加密密钥
    ///
    /// # Errors
    /// 密钥长度不是 32 字节时返回错误
    pub fn new(key: &[u8; 32]) -> Self {
        let cipher = Aes256Gcm::new_from_slice(key).expect("key length is 32 bytes");
        Self { cipher }
    }

    /// 加密明文字符串，返回版本化的密文格式
    ///
    /// 格式：v1.AES_GCM.<nonce_b64>.<ciphertext_b64>.<tag_b64>
    ///
    /// # Arguments
    /// * `plaintext` - 待加密的明文
    ///
    /// # Returns
    /// 版本化的 Base64 编码密文
    ///
    /// # Errors
    /// 明文为空或加密失败时返回错误
    pub fn encrypt(&self, plaintext: &str) -> Result<String> {
        if plaintext.is_empty() {
            return Err(AppError::Crypto("明文不能为空".to_string()));
        }

        let nonce_bytes: [u8; NONCE_SIZE] = rand::thread_rng().gen();
        let nonce = Nonce::from_slice(&nonce_bytes);

        let ciphertext_with_tag = self
            .cipher
            .encrypt(nonce, plaintext.as_bytes())
            .map_err(|e| AppError::Crypto(format!("加密失败: {}", e)))?;

        // AES-GCM 返回 ciphertext + tag（最后 16 字节）
        let ciphertext = &ciphertext_with_tag[..ciphertext_with_tag.len() - TAG_SIZE];
        let tag = &ciphertext_with_tag[ciphertext_with_tag.len() - TAG_SIZE..];

        let nonce_b64 = URL_SAFE_NO_PAD.encode(&nonce_bytes);
        let ciphertext_b64 = URL_SAFE_NO_PAD.encode(ciphertext);
        let tag_b64 = URL_SAFE_NO_PAD.encode(tag);

        Ok(format!(
            "{}.{}.{}.{}.{}",
            VERSION, ALGORITHM, nonce_b64, ciphertext_b64, tag_b64
        ))
    }

    /// 解密版本化的密文，自动验证完整性
    ///
    /// # Arguments
    /// * `encrypted` - 版本化的密文字符串
    ///
    /// # Returns
    /// 解密后的明文
    ///
    /// # Errors
    /// 密文格式无效、版本不支持、或认证失败时返回错误
    pub fn decrypt(&self, encrypted: &str) -> Result<String> {
        let parts: Vec<&str> = encrypted.split('.').collect();
        if parts.len() != 5 {
            return Err(AppError::Crypto(format!(
                "无效的密文格式：期望 5 部分，实际 {} 部分",
                parts.len()
            )));
        }

        let (version, algorithm, nonce_b64, ciphertext_b64, tag_b64) =
            (parts[0], parts[1], parts[2], parts[3], parts[4]);

        if version != VERSION {
            return Err(AppError::Crypto(format!("不支持的版本: {}", version)));
        }
        if algorithm != ALGORITHM {
            return Err(AppError::Crypto(format!("不支持的算法: {}", algorithm)));
        }

        let nonce_bytes = URL_SAFE_NO_PAD
            .decode(nonce_b64)
            .map_err(|e| AppError::Crypto(format!("nonce 解码失败: {}", e)))?;
        let ciphertext = URL_SAFE_NO_PAD
            .decode(ciphertext_b64)
            .map_err(|e| AppError::Crypto(format!("密文解码失败: {}", e)))?;
        let tag = URL_SAFE_NO_PAD
            .decode(tag_b64)
            .map_err(|e| AppError::Crypto(format!("tag 解码失败: {}", e)))?;

        if nonce_bytes.len() != NONCE_SIZE {
            return Err(AppError::Crypto(format!(
                "无效的 nonce 长度：期望 {}，实际 {}",
                NONCE_SIZE,
                nonce_bytes.len()
            )));
        }
        if tag.len() != TAG_SIZE {
            return Err(AppError::Crypto(format!(
                "无效的 tag 长度：期望 {}，实际 {}",
                TAG_SIZE,
                tag.len()
            )));
        }

        // AES-GCM 解密需要 ciphertext + tag
        let mut ciphertext_with_tag = ciphertext;
        ciphertext_with_tag.extend_from_slice(&tag);

        let nonce = Nonce::from_slice(&nonce_bytes);
        let plaintext_bytes = self
            .cipher
            .decrypt(nonce, ciphertext_with_tag.as_ref())
            .map_err(|e| AppError::Crypto(format!("解密失败（可能密文被篡改）: {}", e)))?;

        String::from_utf8(plaintext_bytes)
            .map_err(|e| AppError::Crypto(format!("UTF-8 解码失败: {}", e)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_key() -> [u8; 32] {
        [0u8; 32]
    }

    #[test]
    fn test_encrypt_decrypt() {
        let service = EncryptionService::new(&test_key());
        let plaintext = "my_secret_password";

        let encrypted = service.encrypt(plaintext).unwrap();
        let decrypted = service.decrypt(&encrypted).unwrap();

        assert_eq!(decrypted, plaintext);
    }

    #[test]
    fn test_encrypt_empty_fails() {
        let service = EncryptionService::new(&test_key());
        let result = service.encrypt("");
        assert!(result.is_err());
    }

    #[test]
    fn test_decrypt_tampered_fails() {
        let service = EncryptionService::new(&test_key());
        let plaintext = "my_secret_password";
        let encrypted = service.encrypt(plaintext).unwrap();

        // 篡改密文
        let mut tampered = encrypted.clone();
        tampered.pop();
        tampered.push('x');

        let result = service.decrypt(&tampered);
        assert!(result.is_err());
    }

    #[test]
    fn test_ciphertext_format() {
        let service = EncryptionService::new(&test_key());
        let encrypted = service.encrypt("test").unwrap();

        let parts: Vec<&str> = encrypted.split('.').collect();
        assert_eq!(parts.len(), 5);
        assert_eq!(parts[0], "v1");
        assert_eq!(parts[1], "AES_GCM");
    }

    #[test]
    fn test_different_keys() {
        let key1 = [0u8; 32];
        let key2 = [1u8; 32];

        let service1 = EncryptionService::new(&key1);
        let service2 = EncryptionService::new(&key2);

        let plaintext = "secret";
        let encrypted = service1.encrypt(plaintext).unwrap();

        // 用错误的密钥解密应该失败
        let result = service2.decrypt(&encrypted);
        assert!(result.is_err());
    }
}
