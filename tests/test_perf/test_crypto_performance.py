import os
import time

import pytest

from src.crypto.encryption import EncryptionService
from src.crypto.kdf import derive_master_key, expand_master_key


@pytest.mark.asyncio
async def test_encrypt_1000_passwords() -> None:
    service = EncryptionService(os.urandom(32))
    plaintexts = [f"password-{i}" for i in range(1000)]

    start = time.perf_counter()
    encrypted = [service.encrypt(plaintext) for plaintext in plaintexts]
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / len(plaintexts)) * 1000

    print(
        f"[CRYPTO PERF] encrypt 1000 passwords: total={elapsed * 1000:.2f}ms avg={avg_ms:.4f}ms/op"
    )
    assert len(encrypted) == 1000
    assert avg_ms < 5.0, f"Encryption too slow: {avg_ms:.4f}ms/op >= 5ms/op"


@pytest.mark.asyncio
async def test_decrypt_1000_passwords() -> None:
    service = EncryptionService(os.urandom(32))
    plaintexts = [f"password-{i}" for i in range(1000)]
    encrypted = [service.encrypt(plaintext) for plaintext in plaintexts]

    start = time.perf_counter()
    decrypted = [service.decrypt(ciphertext) for ciphertext in encrypted]
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / len(encrypted)) * 1000

    print(
        f"[CRYPTO PERF] decrypt 1000 passwords: total={elapsed * 1000:.2f}ms avg={avg_ms:.4f}ms/op"
    )
    assert decrypted == plaintexts
    assert avg_ms < 5.0, f"Decryption too slow: {avg_ms:.4f}ms/op >= 5ms/op"


@pytest.mark.asyncio
async def test_encrypt_decrypt_round_trip() -> None:
    service = EncryptionService(os.urandom(32))
    plaintexts = [f"roundtrip-{i}" for i in range(1000)]

    durations: list[float] = []
    for plaintext in plaintexts:
        start = time.perf_counter()
        decrypted = service.decrypt(service.encrypt(plaintext))
        durations.append(time.perf_counter() - start)
        assert decrypted == plaintext

    avg_ms = (sum(durations) / len(durations)) * 1000
    max_ms = max(durations) * 1000
    print(
        f"[CRYPTO PERF] encrypt+decrypt round-trip x1000: avg={avg_ms:.4f}ms/op max={max_ms:.4f}ms"
    )

    assert max_ms < 10.0, f"Round-trip too slow: max {max_ms:.4f}ms >= 10ms"


@pytest.mark.asyncio
async def test_kdf_derive_master_key() -> None:
    durations: list[float] = []
    derived_keys: list[bytes] = []

    for _ in range(5):
        start = time.perf_counter()
        derived_keys.append(derive_master_key("test_password", "test@example.com"))
        durations.append(time.perf_counter() - start)

    avg_seconds = sum(durations) / len(durations)
    max_seconds = max(durations)
    print(
        f"[CRYPTO PERF] derive_master_key x5: avg={avg_seconds * 1000:.2f}ms max={max_seconds * 1000:.2f}ms"
    )

    assert all(len(key) == 32 for key in derived_keys)
    assert max_seconds < 5.0, f"derive_master_key too slow: {max_seconds:.3f}s >= 5.0s"


@pytest.mark.asyncio
async def test_hkdf_expand_1000_times() -> None:
    master_key = derive_master_key("test_password", "test@example.com")

    start = time.perf_counter()
    expanded = [expand_master_key(master_key) for _ in range(1000)]
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / 1000) * 1000

    print(
        f"[CRYPTO PERF] expand_master_key x1000: total={elapsed * 1000:.2f}ms avg={avg_ms:.4f}ms/op"
    )

    assert len(expanded) == 1000
    assert all(
        len(enc_key) == 32 and len(mac_key) == 32 for enc_key, mac_key in expanded
    )
    assert avg_ms < 1.0, f"HKDF expand too slow: {avg_ms:.4f}ms/op >= 1ms/op"
