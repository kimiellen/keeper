import pytest
from cryptography.exceptions import InvalidTag

from src.crypto.encryption import (
    ALGORITHM,
    KEY_SIZE,
    NONCE_SIZE,
    TAG_SIZE,
    VERSION,
    EncryptionService,
    _b64decode,
    _b64encode,
)


@pytest.fixture
def key() -> bytes:
    return b"\x01" * KEY_SIZE


@pytest.fixture
def service(key: bytes) -> EncryptionService:
    return EncryptionService(key)


class TestEncryptionServiceInit:
    def test_valid_key(self, key: bytes):
        svc = EncryptionService(key)
        assert svc is not None

    def test_short_key_raises(self):
        with pytest.raises(ValueError, match="Key must be 32 bytes"):
            EncryptionService(b"short")

    def test_long_key_raises(self):
        with pytest.raises(ValueError, match="Key must be 32 bytes"):
            EncryptionService(b"\x00" * 64)


class TestEncrypt:
    def test_format_has_five_parts(self, service: EncryptionService):
        result = service.encrypt("hello")
        parts = result.split(".")
        assert len(parts) == 5

    def test_version_prefix(self, service: EncryptionService):
        result = service.encrypt("hello")
        assert result.startswith(f"{VERSION}.{ALGORITHM}.")

    def test_empty_plaintext_raises(self, service: EncryptionService):
        with pytest.raises(ValueError, match="Plaintext must not be empty"):
            service.encrypt("")

    def test_different_nonces_each_call(self, service: EncryptionService):
        c1 = service.encrypt("hello")
        c2 = service.encrypt("hello")
        assert c1 != c2

    def test_unicode_plaintext(self, service: EncryptionService):
        result = service.encrypt("密码パスワード🔑")
        assert result.startswith(f"{VERSION}.{ALGORITHM}.")


class TestDecrypt:
    def test_roundtrip(self, service: EncryptionService):
        plaintext = "MySecret123!"
        encrypted = service.encrypt(plaintext)
        assert service.decrypt(encrypted) == plaintext

    def test_roundtrip_unicode(self, service: EncryptionService):
        plaintext = "密码パスワード🔑"
        encrypted = service.encrypt(plaintext)
        assert service.decrypt(encrypted) == plaintext

    def test_roundtrip_long_text(self, service: EncryptionService):
        plaintext = "A" * 10000
        encrypted = service.encrypt(plaintext)
        assert service.decrypt(encrypted) == plaintext

    def test_wrong_key_raises_invalid_tag(self, service: EncryptionService):
        encrypted = service.encrypt("secret")
        wrong_service = EncryptionService(b"\x02" * KEY_SIZE)
        with pytest.raises(InvalidTag):
            wrong_service.decrypt(encrypted)

    def test_invalid_format_too_few_parts(self, service: EncryptionService):
        with pytest.raises(ValueError, match="expected 5 parts"):
            service.decrypt("v1.AES_GCM.abc")

    def test_invalid_version(self, service: EncryptionService):
        encrypted = service.encrypt("test")
        tampered = "v2" + encrypted[2:]
        with pytest.raises(ValueError, match="Unsupported version"):
            service.decrypt(tampered)

    def test_invalid_algorithm(self, service: EncryptionService):
        encrypted = service.encrypt("test")
        parts = encrypted.split(".")
        parts[1] = "AES_CBC"
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            service.decrypt(".".join(parts))

    def test_tampered_ciphertext_raises_invalid_tag(self, service: EncryptionService):
        encrypted = service.encrypt("secret")
        parts = encrypted.split(".")
        ct_bytes = bytearray(_b64decode(parts[3]))
        ct_bytes[0] ^= 0xFF
        parts[3] = _b64encode(bytes(ct_bytes))
        tampered = ".".join(parts)
        with pytest.raises(InvalidTag):
            service.decrypt(tampered)

    def test_tampered_tag_raises_invalid_tag(self, service: EncryptionService):
        encrypted = service.encrypt("secret")
        parts = encrypted.split(".")
        tag_bytes = bytearray(_b64decode(parts[4]))
        tag_bytes[0] ^= 0xFF
        parts[4] = _b64encode(bytes(tag_bytes))
        tampered = ".".join(parts)
        with pytest.raises(InvalidTag):
            service.decrypt(tampered)
