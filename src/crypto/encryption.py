"""
数据加密模块

使用 AES-256-GCM 进行认证加密，密文格式为版本化的 Base64 编码。
格式：v1.AES_GCM.<nonce_b64>.<ciphertext_b64>.<tag_b64>
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 常量
NONCE_SIZE = 12  # 96-bit nonce（GCM 推荐值）
TAG_SIZE = 16  # 128-bit 认证标签
KEY_SIZE = 32  # 256-bit 密钥
VERSION = "v1"
ALGORITHM = "AES_GCM"


def _b64encode(data: bytes) -> str:
    """URL-safe Base64 编码，去掉 padding。"""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(s: str) -> bytes:
    """URL-safe Base64 解码，自动补齐 padding。"""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


class EncryptionService:
    """
    AES-256-GCM 加密服务。

    每次加密使用密码学安全的随机 Nonce，密文包含版本信息以支持未来算法升级。
    """

    def __init__(self, key: bytes) -> None:
        """
        初始化加密服务。

        Args:
            key: 256-bit (32 字节) 加密密钥

        Raises:
            ValueError: 密钥长度不是 32 字节
        """
        if len(key) != KEY_SIZE:
            raise ValueError(f"Key must be {KEY_SIZE} bytes, got {len(key)}")
        self._cipher = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        """
        加密明文字符串，返回版本化的密文格式。

        格式：v1.AES_GCM.<nonce_b64>.<ciphertext_b64>.<tag_b64>

        Args:
            plaintext: 待加密的明文

        Returns:
            版本化的 Base64 编码密文

        Raises:
            ValueError: 明文为空
        """
        if not plaintext:
            raise ValueError("Plaintext must not be empty")

        nonce = os.urandom(NONCE_SIZE)
        plaintext_bytes = plaintext.encode("utf-8")

        # AESGCM.encrypt 返回 ciphertext + 16-byte tag
        ciphertext_with_tag = self._cipher.encrypt(nonce, plaintext_bytes, None)

        ciphertext = ciphertext_with_tag[:-TAG_SIZE]
        tag = ciphertext_with_tag[-TAG_SIZE:]

        nonce_b64 = _b64encode(nonce)
        ciphertext_b64 = _b64encode(ciphertext)
        tag_b64 = _b64encode(tag)

        return f"{VERSION}.{ALGORITHM}.{nonce_b64}.{ciphertext_b64}.{tag_b64}"

    def decrypt(self, encrypted: str) -> str:
        """
        解密版本化的密文，自动验证完整性。

        Args:
            encrypted: 版本化的密文字符串

        Returns:
            解密后的明文

        Raises:
            ValueError: 密文格式无效
            cryptography.exceptions.InvalidTag: 认证标签验证失败（数据被篡改）
        """
        parts = encrypted.split(".")
        if len(parts) != 5:
            raise ValueError(
                f"Invalid encrypted format: expected 5 parts, got {len(parts)}"
            )

        version, algorithm, nonce_b64, ciphertext_b64, tag_b64 = parts

        if version != VERSION:
            raise ValueError(f"Unsupported version: {version}")
        if algorithm != ALGORITHM:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        nonce = _b64decode(nonce_b64)
        ciphertext = _b64decode(ciphertext_b64)
        tag = _b64decode(tag_b64)

        if len(nonce) != NONCE_SIZE:
            raise ValueError(
                f"Invalid nonce size: expected {NONCE_SIZE}, got {len(nonce)}"
            )
        if len(tag) != TAG_SIZE:
            raise ValueError(f"Invalid tag size: expected {TAG_SIZE}, got {len(tag)}")

        # AESGCM.decrypt 期望 ciphertext + tag
        ciphertext_with_tag = ciphertext + tag
        plaintext_bytes = self._cipher.decrypt(nonce, ciphertext_with_tag, None)

        return plaintext_bytes.decode("utf-8")
