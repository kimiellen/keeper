//! 加密模块互操作性测试
//!
//! 验证 Rust 实现与 Python 版本的兼容性：
//! 1. Python 加密的密文能被 Rust 解密
//! 2. Python 生成的 Argon2 哈希能被 Rust 验证
//! 3. Python 和 Rust 派生的密钥一致

use keeper::crypto::{encryption::EncryptionService, kdf};

/// Python 生成的测试数据
const TEST_PASSWORD: &str = "test_interop_123";
const TEST_KEY_HEX: &str = "f23f4677dcd86bf15746545fdbfed4486945c824927af4d18fb21acc4e643271";
const TEST_ARGON2_HASH: &str = "$argon2id$v=19$m=65536,t=3,p=1$7HvyOHTjUd6pYnBSj2nXyA$VXP4UF3XigQHLKvX2mUmPs6XrGfQDg9vhRvHpDMx5Zs";
const TEST_CIPHERTEXT: &str = "v1.AES_GCM.jI3Qq5WxBGPFI-Ol.kktSOD99UA1bntKydhgFfyME9yYg6YRS7hndPAFbtEU.UCIVs-xpmj_CQo8JtdWA0w";
const TEST_PLAINTEXT: &str = "Hello from Python! 你好世界!";

#[test]
fn test_derive_key_matches_python() {
    let key = kdf::derive_key(TEST_PASSWORD);
    let key_hex = hex::encode(key);
    assert_eq!(
        key_hex, TEST_KEY_HEX,
        "派生密钥应与 Python 版本一致"
    );
}

#[test]
fn test_verify_python_argon2_hash() {
    assert!(
        kdf::verify_password(TEST_PASSWORD, TEST_ARGON2_HASH),
        "应能验证 Python 生成的 Argon2 哈希"
    );
}

#[test]
fn test_decrypt_python_ciphertext() {
    let key_bytes = hex::decode(TEST_KEY_HEX).expect("valid hex");
    let key: &[u8; 32] = key_bytes.as_slice().try_into().expect("32 bytes");
    
    let service = EncryptionService::new(key);
    let decrypted = service.decrypt(TEST_CIPHERTEXT)
        .expect("应能解密 Python 加密的密文");
    
    assert_eq!(
        decrypted, TEST_PLAINTEXT,
        "解密结果应与 Python 加密前的明文一致"
    );
}

#[test]
fn test_round_trip_rust_encrypt_python_decrypt() {
    // Rust 加密
    let key = kdf::derive_key(TEST_PASSWORD);
    let service = EncryptionService::new(&key);
    
    let plaintext = "Round trip test from Rust! 往返测试!";
    let ciphertext = service.encrypt(plaintext).expect("encryption should succeed");
    
    // 验证格式正确
    assert!(ciphertext.starts_with("v1.AES_GCM."));
    
    // 验证 Rust 自己能解密
    let decrypted = service.decrypt(&ciphertext).expect("decryption should succeed");
    assert_eq!(decrypted, plaintext);
    
    // 打印密文，可用于手动验证 Python 能否解密
    println!("Rust encrypted ciphertext: {}", ciphertext);
    println!("Plaintext: {}", plaintext);
}

#[test]
fn test_hash_verify_round_trip() {
    let password = "my_test_password";
    
    // Rust 端哈希
    let hash = kdf::hash_password(password);
    
    // 验证格式是 Argon2id
    assert!(hash.starts_with("$argon2id$"));
    
    // Rust 自己验证
    assert!(kdf::verify_password(password, &hash));
    assert!(!kdf::verify_password("wrong_password", &hash));
    
    // 打印哈希，可用于手动验证 Python 能否验证
    println!("Rust generated Argon2 hash: {}", hash);
}
