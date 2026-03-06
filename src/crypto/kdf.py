"""
密钥派生模块

使用 Argon2id 从主密码派生 Master Key，再通过 HKDF-SHA256 扩展为加密密钥和 MAC 密钥。
"""

from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

# Argon2id 参数（与交互记录最终确认值一致）
ARGON2_MEMORY_COST = 65536  # 64MB（单位：KB）
ARGON2_TIME_COST = 3  # 迭代次数
ARGON2_PARALLELISM = 1  # 并行度（本地单用户优化）
ARGON2_HASH_LEN = 32  # 输出 256-bit
ARGON2_SALT_LEN = 16  # 盐长度（字节）

# HKDF 参数
HKDF_OUTPUT_LEN = 64  # 扩展为 64 字节（enc_key + mac_key）
HKDF_INFO = b"keeper-v1-key-expansion"


def derive_master_key(password: str, email: str) -> bytes:
    """
    从主密码和邮箱派生 Master Key。

    使用 Argon2id（内存困难型 KDF），以用户邮箱前 16 字节作为盐。

    Args:
        password: 用户主密码
        email: 用户邮箱（用作盐，保证唯一性）

    Returns:
        32 字节的 Master Key

    Raises:
        ValueError: 密码或邮箱为空
    """
    if not password:
        raise ValueError("Password must not be empty")
    if not email:
        raise ValueError("Email must not be empty")

    salt = email.encode("utf-8")[:ARGON2_SALT_LEN].ljust(ARGON2_SALT_LEN, b"\x00")

    master_key = hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN,
        type=Type.ID,
    )

    return master_key


def expand_master_key(master_key: bytes) -> tuple[bytes, bytes]:
    """
    使用 HKDF-SHA256 将 Master Key 扩展为加密密钥和 MAC 密钥。

    Args:
        master_key: 32 字节的 Master Key（由 derive_master_key 生成）

    Returns:
        (enc_key, mac_key) 元组，各 32 字节
            - enc_key: AES-256-GCM 加密密钥
            - mac_key: 预留 MAC 密钥（AES-GCM 自带认证，保留以便未来扩展）

    Raises:
        ValueError: master_key 长度不是 32 字节
    """
    if len(master_key) != ARGON2_HASH_LEN:
        raise ValueError(
            f"Master key must be {ARGON2_HASH_LEN} bytes, got {len(master_key)}"
        )

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=HKDF_OUTPUT_LEN,
        salt=None,
        info=HKDF_INFO,
    )

    expanded = hkdf.derive(master_key)
    enc_key = expanded[:32]
    mac_key = expanded[32:]

    return enc_key, mac_key
