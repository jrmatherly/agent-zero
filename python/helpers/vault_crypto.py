"""AES-256-GCM encryption with HKDF key derivation for the API key vault.

Provides envelope encryption for secrets stored in the ``api_key_vault``
database table. A single ``VAULT_MASTER_KEY`` environment variable (64-char
hex string = 256 bits) is expanded via HKDF-SHA256 into purpose-specific
subkeys so that a compromise of one derived key does not expose values
encrypted under a different purpose.

Purpose keys used across the system:

    "api_key_vault"           -- User/team/org API key encryption (Phase 0)
    "mcp_service_credentials" -- MCP service registry client secrets (Phase 4)
    "msal_token_cache"        -- MSAL persistent token cache (Phase 1)

Key rotation workflow:
    1. Decrypt all rows with the old master key.
    2. Set the new ``VAULT_MASTER_KEY``.
    3. Re-encrypt all rows.
    4. Provide ``mise run vault:rotate`` task for automation.
"""

import base64
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Module-level master key cache (lazy loaded on first use).
_master_key: bytes | None = None


def _get_master_key() -> bytes:
    """Read and validate ``VAULT_MASTER_KEY`` from the environment.

    The key must be a 64-character hexadecimal string representing 256 bits.
    The parsed bytes are cached at module level so the environment is read at
    most once per process.

    Raises:
        RuntimeError: If the variable is missing, empty, not 64 hex chars, or
            contains non-hex characters.
    """
    global _master_key  # noqa: PLW0603
    if _master_key is not None:
        return _master_key

    key_hex = os.environ.get("VAULT_MASTER_KEY")
    if not key_hex or len(key_hex) != 64:
        raise RuntimeError(
            "VAULT_MASTER_KEY must be a 64-character hex string (256 bits). "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )

    try:
        _master_key = bytes.fromhex(key_hex)
    except ValueError as exc:
        raise RuntimeError(
            "VAULT_MASTER_KEY contains non-hexadecimal characters. "
            "It must be exactly 64 hex digits [0-9a-fA-F]."
        ) from exc

    return _master_key


def _derive_key(purpose: str) -> bytes:
    """Derive a 256-bit purpose-specific key via HKDF-SHA256.

    Args:
        purpose: An ASCII label identifying the encryption domain (e.g.
            ``"api_key_vault"``). Different purpose strings yield
            cryptographically independent keys from the same master key.

    Returns:
        32-byte derived key suitable for AES-256-GCM.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=purpose.encode(),
    )
    return hkdf.derive(_get_master_key())


def encrypt(plaintext: str, purpose: str = "api_key_vault") -> str:
    """Encrypt *plaintext* with AES-256-GCM under the given *purpose* key.

    A fresh 12-byte random nonce is generated for every call and prepended to
    the ciphertext. The result is Base64-encoded for safe storage in text
    columns.

    Args:
        plaintext: The secret value to encrypt (UTF-8 string).
        purpose: HKDF info label selecting the derived key.

    Returns:
        Base64-encoded string of ``nonce (12 bytes) || ciphertext+tag``.
    """
    key = _derive_key(purpose)
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(encrypted: str, purpose: str = "api_key_vault") -> str:
    """Decrypt a value previously produced by :func:`encrypt`.

    Args:
        encrypted: Base64-encoded string containing ``nonce || ciphertext+tag``.
        purpose: Must match the purpose used during encryption.

    Returns:
        The original plaintext as a UTF-8 string.

    Raises:
        cryptography.exceptions.InvalidTag: If the key or purpose is wrong, or
            the data has been tampered with.
        ValueError: If *encrypted* is not valid Base64.
    """
    key = _derive_key(purpose)
    raw = base64.b64decode(encrypted)
    nonce = raw[:12]
    ciphertext = raw[12:]
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode()
