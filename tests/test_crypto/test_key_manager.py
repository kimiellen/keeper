import pytest
from cryptography.exceptions import InvalidTag

from src.crypto.encryption import EncryptionService
from src.crypto.kdf import derive_master_key, expand_master_key
from src.crypto.key_manager import KeyManager, generate_user_key, USER_KEY_SIZE


class TestGenerateUserKey:
    def test_returns_32_bytes(self):
        key = generate_user_key()
        assert len(key) == USER_KEY_SIZE

    def test_generates_unique_keys(self):
        keys = {generate_user_key() for _ in range(10)}
        assert len(keys) == 10


class TestKeyManager:
    @pytest.fixture
    def enc_key(self) -> bytes:
        master_key = derive_master_key("password123", "user@example.com")
        enc_key, _ = expand_master_key(master_key)
        return enc_key

    def test_create_and_load_user_key(self, enc_key: bytes):
        km = KeyManager()
        user_key = km.create_user_key(enc_key)
        assert len(user_key) == USER_KEY_SIZE

        loaded = km.load_user_key(enc_key)
        assert loaded == user_key

    def test_has_user_key_false_initially(self):
        km = KeyManager()
        assert km.has_user_key is False

    def test_has_user_key_true_after_create(self, enc_key: bytes):
        km = KeyManager()
        km.create_user_key(enc_key)
        assert km.has_user_key is True

    def test_load_without_create_raises(self, enc_key: bytes):
        km = KeyManager()
        with pytest.raises(RuntimeError, match="No user key found"):
            km.load_user_key(enc_key)

    def test_wrong_key_raises_invalid_tag(self, enc_key: bytes):
        km = KeyManager()
        km.create_user_key(enc_key)

        wrong_master = derive_master_key("wrong_password", "user@example.com")
        wrong_enc, _ = expand_master_key(wrong_master)
        with pytest.raises(InvalidTag):
            km.load_user_key(wrong_enc)

    def test_get_and_set_encrypted_user_key(self, enc_key: bytes):
        km1 = KeyManager()
        user_key = km1.create_user_key(enc_key)
        encrypted = km1.get_encrypted_user_key()
        assert encrypted is not None

        km2 = KeyManager()
        km2.set_encrypted_user_key(encrypted)
        assert km2.has_user_key is True
        loaded = km2.load_user_key(enc_key)
        assert loaded == user_key


class TestEndToEndFlow:
    def test_full_flow(self):
        password = "MyStr0ng!P@ssword"
        email = "keeper-test@example.com"

        master_key = derive_master_key(password, email)
        enc_key, _ = expand_master_key(master_key)

        km = KeyManager()
        user_key = km.create_user_key(enc_key)

        data_service = EncryptionService(user_key)
        secret = "https://example.com | admin | s3cret!"
        encrypted = data_service.encrypt(secret)
        assert data_service.decrypt(encrypted) == secret

        loaded_user_key = km.load_user_key(enc_key)
        data_service2 = EncryptionService(loaded_user_key)
        assert data_service2.decrypt(encrypted) == secret
