"""
密钥派生模块

使用 Argon2id 进行：
1. 主密码哈希存储（用于验证）
2. 加密密钥派生（用于 AES-256-GCM 加解密）

设计原则：
- hash_password()：每次生成随机盐，结果可用于 verify_password()
- derive_key()：使用固定盐（PBKDF2 风格），从相同密码始终派生出相同的 32 字节密钥
"""

import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Argon2id 参数（平衡安全性与性能）
_ph = PasswordHasher(
    time_cost=3,  # 迭代次数
    memory_cost=65536,  # 64 MiB 内存
    parallelism=1,  # 并行度
    hash_len=32,  # 输出长度 256-bit
    salt_len=16,  # 盐长度 128-bit
)

# 派生加密密钥时使用的固定上下文标识（不作为安全盐，仅用于域隔离）
_KEY_DERIVE_INFO = b"keeper-encryption-key-v1"


def hash_password(password: str) -> str:
    """
    对主密码进行 Argon2id 哈希，用于存储和后续验证。

    每次调用生成不同的随机盐，返回的哈希字符串包含所有参数信息。

    Args:
        password: 明文主密码

    Returns:
        Argon2id 哈希字符串（含算法参数和盐）
    """
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """
    验证明文密码是否与存储的 Argon2id 哈希匹配。

    Args:
        password: 待验证的明文密码
        password_hash: 存储的 Argon2id 哈希字符串

    Returns:
        验证通过返回 True，否则返回 False
    """
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def derive_key(password: str) -> bytes:
    """
    从主密码确定性派生 32 字节加密密钥（AES-256 用）。

    使用 PBKDF2-HMAC-SHA256 配合固定的上下文盐，确保相同密码始终生成相同密钥。
    注意：此函数不替代 hash_password()，两者用途不同：
    - hash_password() 用于验证密码（随机盐，不可逆推密钥）
    - derive_key() 用于派生加密密钥（固定盐，可重现）

    Args:
        password: 明文主密码

    Returns:
        32 字节加密密钥（bytes）
    """
    return hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=password.encode("utf-8"),
        salt=_KEY_DERIVE_INFO,
        iterations=100_000,
        dklen=32,
    )
