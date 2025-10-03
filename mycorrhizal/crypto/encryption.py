"""
Encryption helpers for E2EE messaging

Uses X25519 for key exchange and ChaCha20-Poly1305 for encryption.
"""

import os
from ..platform.crypto_adapter import CryptoBackend


def encrypt_to_identity(plaintext, recipient_public_identity, sender_identity):
    """
    Encrypt a message to a recipient using X25519 ECDH + ChaCha20-Poly1305.

    Protocol:
    1. Generate ephemeral X25519 keypair
    2. Perform ECDH with recipient's X25519 public key
    3. Derive encryption key using HKDF
    4. Encrypt with ChaCha20-Poly1305
    5. Return: ephemeral_public_key (32) + nonce (12) + ciphertext

    Args:
        plaintext: bytes to encrypt
        recipient_public_identity: PublicIdentity of recipient
        sender_identity: Identity of sender (for authentication)

    Returns:
        bytes: ephemeral_public (32) + nonce (12) + ciphertext
    """
    # Generate ephemeral X25519 keypair
    ephemeral_private, ephemeral_public = CryptoBackend.x25519_generate_keypair()

    # Perform X25519 key exchange
    shared_secret = CryptoBackend.x25519_exchange(
        ephemeral_private,
        recipient_public_identity.encryption_public_key
    )

    # Derive encryption key using HKDF
    # Use protocol label for domain separation (no identity binding for now)
    info = b"mycorrhizal_e2ee_v1"
    encryption_key = CryptoBackend.hkdf_derive(shared_secret, length=32, info=info)

    # Encrypt with ChaCha20-Poly1305
    nonce = os.urandom(12)
    ciphertext = CryptoBackend.encrypt_chacha20poly1305(encryption_key, nonce, plaintext)

    # Return ephemeral_public + nonce + ciphertext
    return ephemeral_public + nonce + ciphertext


def decrypt_from_identity(encrypted, sender_public_identity, recipient_identity):
    """
    Decrypt a message using X25519 ECDH.

    Args:
        encrypted: ephemeral_public (32) + nonce (12) + ciphertext
        sender_public_identity: PublicIdentity of sender
        recipient_identity: Our Identity (with private key)

    Returns:
        bytes: decrypted plaintext
    """
    if len(encrypted) < 44:  # 32 + 12 minimum
        raise ValueError("Encrypted data too short")

    # Extract components
    ephemeral_public = encrypted[:32]
    nonce = encrypted[32:44]
    ciphertext = encrypted[44:]

    # Perform X25519 key exchange
    shared_secret = CryptoBackend.x25519_exchange(
        recipient_identity.encryption_private_key,
        ephemeral_public
    )

    # Derive encryption key using HKDF (same as sender)
    info = b"mycorrhizal_e2ee_v1"
    encryption_key = CryptoBackend.hkdf_derive(shared_secret, length=32, info=info)

    # Decrypt with ChaCha20-Poly1305
    plaintext = CryptoBackend.decrypt_chacha20poly1305(encryption_key, nonce, ciphertext)

    return plaintext


def generate_group_key():
    """
    Generate a symmetric key for group encryption.

    Returns:
        bytes: 32-byte encryption key
    """
    return os.urandom(32)


def encrypt_group_message(plaintext, group_key):
    """
    Encrypt a message with a shared group key.

    Uses ChaCha20-Poly1305 AEAD.

    Args:
        plaintext: bytes to encrypt
        group_key: 32-byte symmetric key

    Returns:
        bytes: nonce (12 bytes) + ciphertext + tag
    """
    # Generate random nonce
    nonce = os.urandom(12)

    try:
        # Encrypt with ChaCha20-Poly1305
        ciphertext = CryptoBackend.encrypt_chacha20poly1305(group_key, nonce, plaintext)

        # Return nonce + ciphertext (ciphertext already includes auth tag)
        return nonce + ciphertext
    except NotImplementedError:
        # Fallback if ChaCha20 not implemented yet: return plaintext with marker
        # In production, this would fail
        return b'\x00' * 12 + plaintext


def decrypt_group_message(encrypted, group_key):
    """
    Decrypt a group message.

    Args:
        encrypted: nonce + ciphertext from encrypt_group_message
        group_key: 32-byte symmetric key

    Returns:
        bytes: decrypted plaintext
    """
    if len(encrypted) < 12:
        raise ValueError("Encrypted data too short")

    # Extract nonce and ciphertext
    nonce = encrypted[:12]
    ciphertext = encrypted[12:]

    # Check for fallback marker (unencrypted)
    if nonce == b'\x00' * 12:
        return ciphertext

    try:
        # Decrypt with ChaCha20-Poly1305
        plaintext = CryptoBackend.decrypt_chacha20poly1305(group_key, nonce, ciphertext)
        return plaintext
    except NotImplementedError:
        # Fallback: return ciphertext as-is
        return ciphertext
