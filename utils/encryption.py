"""
encryption.py - AES-256-CBC encryption / decryption helpers.

The 256-bit AES key is read from the AES_KEY environment variable as a
64-character hex string (32 bytes).  Never store the raw key in source code.

Generate a fresh key once (run in Python):
    import os; print(os.urandom(32).hex())
Then add it to your .env:
    AES_KEY=<64-char hex string>
"""

import os
import hashlib
import hmac
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


# ---------------------------------------------------------------------------
# Key loading
# ---------------------------------------------------------------------------

def _load_aes_key() -> bytes:
    """
    Load the AES-256 key from the AES_KEY environment variable.
    Raises RuntimeError if the variable is missing or has wrong length.
    """
    hex_key = os.getenv("AES_KEY", "")
    if len(hex_key) != 64:
        raise RuntimeError(
            "AES_KEY environment variable must be a 64-character hex string "
            "(32 bytes = 256 bits).  Generate one with: "
            "python -c \"import os; print(os.urandom(32).hex())\""
        )
    return bytes.fromhex(hex_key)


# ---------------------------------------------------------------------------
# SHA-256 integrity hash
# ---------------------------------------------------------------------------

def compute_sha256(data: bytes) -> str:
    """Return the hex-encoded SHA-256 hash of raw binary data."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# AES-256-CBC encryption
# ---------------------------------------------------------------------------

def encrypt_image(plaintext: bytes) -> tuple[bytes, bytes]:
    """
    Encrypt binary data with AES-256-CBC.

    Args:
        plaintext: Raw image bytes.

    Returns:
        (ciphertext, iv) — both as raw bytes.
            • ciphertext: PKCS7-padded, AES-256-CBC encrypted blob.
            • iv        : 16 random bytes used for this encryption.
    """
    key = _load_aes_key()
    iv = os.urandom(16)  # Fresh IV per upload — never reuse

    # PKCS7 padding to make plaintext a multiple of 16 bytes
    pad_len = 16 - (len(plaintext) % 16)
    padded = plaintext + bytes([pad_len] * pad_len)

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    return ciphertext, iv


# ---------------------------------------------------------------------------
# AES-256-CBC decryption
# ---------------------------------------------------------------------------

def decrypt_image(ciphertext: bytes, iv: bytes) -> bytes:
    """
    Decrypt an AES-256-CBC ciphertext.

    Args:
        ciphertext: Encrypted blob (from encrypt_image).
        iv        : The 16-byte IV used during encryption.

    Returns:
        Original plaintext bytes (padding stripped).
    """
    key = _load_aes_key()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    # Strip PKCS7 padding
    pad_len = padded[-1]
    return padded[:-pad_len]


# ---------------------------------------------------------------------------
# Integrity verification helper
# ---------------------------------------------------------------------------

def verify_integrity(original_hash: str, plaintext: bytes) -> bool:
    """
    Constant-time comparison of the stored SHA-256 hash against a freshly
    computed hash of the given bytes.  Returns True if they match.
    """
    computed = compute_sha256(plaintext)
    return hmac.compare_digest(original_hash, computed)
