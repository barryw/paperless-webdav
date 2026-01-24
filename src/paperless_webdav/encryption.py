# src/paperless_webdav/encryption.py
"""AES-256-GCM encryption for Paperless API tokens."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TokenEncryption:
    """Encrypt and decrypt Paperless API tokens using AES-256-GCM."""

    NONCE_SIZE = 12  # 96 bits, standard for GCM

    def __init__(self, key_base64: str) -> None:
        """Initialize with a base64-encoded 32-byte key."""
        key = base64.b64decode(key_base64)
        if len(key) != 32:
            raise ValueError(f"Key must be 32 bytes, got {len(key)}")
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a plaintext string."""
        nonce = os.urandom(self.NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ciphertext

    def decrypt(self, encrypted: bytes) -> str:
        """Decrypt encrypted bytes back to plaintext."""
        nonce = encrypted[: self.NONCE_SIZE]
        ciphertext = encrypted[self.NONCE_SIZE :]
        plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
