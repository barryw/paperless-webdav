# tests/test_encryption.py
"""Tests for token encryption service."""

import base64

import pytest

from paperless_webdav.encryption import TokenEncryption


@pytest.fixture
def encryption() -> TokenEncryption:
    """Create encryption instance with test key."""
    key = base64.b64encode(b"testkey_for_aes256_encryption!!!").decode()
    return TokenEncryption(key)


def test_encrypt_decrypt_roundtrip(encryption: TokenEncryption) -> None:
    """Encrypted token should decrypt to original value."""
    original = "paperless-api-token-abc123"
    encrypted = encryption.encrypt(original)
    decrypted = encryption.decrypt(encrypted)
    assert decrypted == original
    assert encrypted != original.encode()


def test_encrypted_output_is_bytes(encryption: TokenEncryption) -> None:
    """Encryption should return bytes."""
    encrypted = encryption.encrypt("test")
    assert isinstance(encrypted, bytes)


def test_decrypt_invalid_data_raises(encryption: TokenEncryption) -> None:
    """Decrypting garbage should raise an error."""
    with pytest.raises(Exception):
        encryption.decrypt(b"not-valid-encrypted-data")


def test_same_plaintext_different_ciphertext(encryption: TokenEncryption) -> None:
    """Same input should produce different output (random nonce)."""
    plaintext = "test-token"
    encrypted1 = encryption.encrypt(plaintext)
    encrypted2 = encryption.encrypt(plaintext)
    assert encrypted1 != encrypted2
    assert encryption.decrypt(encrypted1) == encryption.decrypt(encrypted2)
