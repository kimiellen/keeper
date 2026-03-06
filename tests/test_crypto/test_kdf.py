import pytest

from src.crypto.kdf import (
    ARGON2_HASH_LEN,
    ARGON2_MEMORY_COST,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    derive_master_key,
    expand_master_key,
)


class TestDeriveMasterKey:
    def test_returns_32_bytes(self):
        key = derive_master_key("password123", "user@example.com")
        assert len(key) == ARGON2_HASH_LEN

    def test_deterministic_output(self):
        key1 = derive_master_key("password123", "user@example.com")
        key2 = derive_master_key("password123", "user@example.com")
        assert key1 == key2

    def test_different_passwords_produce_different_keys(self):
        key1 = derive_master_key("password1", "user@example.com")
        key2 = derive_master_key("password2", "user@example.com")
        assert key1 != key2

    def test_different_emails_produce_different_keys(self):
        key1 = derive_master_key("password123", "alice@example.com")
        key2 = derive_master_key("password123", "bob@example.com")
        assert key1 != key2

    def test_empty_password_raises(self):
        with pytest.raises(ValueError, match="Password must not be empty"):
            derive_master_key("", "user@example.com")

    def test_empty_email_raises(self):
        with pytest.raises(ValueError, match="Email must not be empty"):
            derive_master_key("password123", "")

    def test_short_email_padded_to_16_bytes(self):
        key = derive_master_key("password123", "a@b.c")
        assert len(key) == ARGON2_HASH_LEN

    def test_long_email_truncated_to_16_bytes(self):
        long_email = "a" * 100 + "@example.com"
        key = derive_master_key("password123", long_email)
        assert len(key) == ARGON2_HASH_LEN

    def test_unicode_password(self):
        key = derive_master_key("密码パスワード🔑", "user@example.com")
        assert len(key) == ARGON2_HASH_LEN

    def test_uses_argon2id_params(self):
        assert ARGON2_MEMORY_COST == 65536
        assert ARGON2_TIME_COST == 3
        assert ARGON2_PARALLELISM == 1


class TestExpandMasterKey:
    def test_returns_two_32_byte_keys(self):
        master_key = derive_master_key("password123", "user@example.com")
        enc_key, mac_key = expand_master_key(master_key)
        assert len(enc_key) == 32
        assert len(mac_key) == 32

    def test_enc_and_mac_keys_differ(self):
        master_key = derive_master_key("password123", "user@example.com")
        enc_key, mac_key = expand_master_key(master_key)
        assert enc_key != mac_key

    def test_deterministic_expansion(self):
        master_key = derive_master_key("password123", "user@example.com")
        result1 = expand_master_key(master_key)
        result2 = expand_master_key(master_key)
        assert result1 == result2

    def test_different_master_keys_produce_different_results(self):
        mk1 = derive_master_key("pass1", "user@example.com")
        mk2 = derive_master_key("pass2", "user@example.com")
        enc1, _ = expand_master_key(mk1)
        enc2, _ = expand_master_key(mk2)
        assert enc1 != enc2

    def test_invalid_key_length_raises(self):
        with pytest.raises(ValueError, match="Master key must be 32 bytes"):
            expand_master_key(b"short")

    def test_invalid_key_length_too_long_raises(self):
        with pytest.raises(ValueError, match="Master key must be 32 bytes"):
            expand_master_key(b"\x00" * 64)
