"""
密钥管理模块（Stub）

管理 User Key 的生成、加密存储和加载。
DB 层就绪前使用内存存储，后续将对接 authentication 表。
"""

import os

from src.crypto.encryption import EncryptionService

USER_KEY_SIZE = 32


def generate_user_key() -> bytes:
    """
    生成随机 User Key。

    Returns:
        32 字节的密码学安全随机密钥
    """
    return os.urandom(USER_KEY_SIZE)


class KeyManager:
    """
    User Key 管理器。

    负责 User Key 的生成、用 Master Key 加密/解密、以及存取。
    当前使用内存存储（Stub），DB 层就绪后替换为持久化存储。
    """

    def __init__(self) -> None:
        self._encrypted_user_key: str | None = None

    def create_user_key(self, enc_key: bytes) -> bytes:
        """
        生成新的 User Key 并加密存储。

        Args:
            enc_key: 32 字节加密密钥（由 HKDF 从 Master Key 派生）

        Returns:
            原始 User Key（明文，调用方使用后应清零）
        """
        user_key = generate_user_key()
        service = EncryptionService(enc_key)

        self._encrypted_user_key = service.encrypt(user_key.hex())
        return user_key

    def load_user_key(self, enc_key: bytes) -> bytes:
        """
        解密并返回 User Key。

        Args:
            enc_key: 32 字节加密密钥（由 HKDF 从 Master Key 派生）

        Returns:
            解密后的 User Key（32 字节）

        Raises:
            RuntimeError: 尚未创建 User Key
            cryptography.exceptions.InvalidTag: 密钥不匹配（认证失败）
        """
        if self._encrypted_user_key is None:
            raise RuntimeError("No user key found. Call create_user_key first.")

        service = EncryptionService(enc_key)
        user_key_hex = service.decrypt(self._encrypted_user_key)
        return bytes.fromhex(user_key_hex)

    @property
    def has_user_key(self) -> bool:
        """是否已存储 User Key。"""
        return self._encrypted_user_key is not None

    def get_encrypted_user_key(self) -> str | None:
        """获取加密后的 User Key 字符串（用于持久化）。"""
        return self._encrypted_user_key

    def set_encrypted_user_key(self, encrypted: str) -> None:
        """
        设置加密后的 User Key（从持久化存储加载时使用）。

        Args:
            encrypted: 版本化的加密 User Key 字符串
        """
        self._encrypted_user_key = encrypted
