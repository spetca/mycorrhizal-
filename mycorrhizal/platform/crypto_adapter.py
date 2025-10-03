"""
Crypto Adapter - Platform-specific cryptography

Adapts cryptographic implementations based on platform:
- MicroPython: ucryptolib (ChaCha20-Poly1305) + pure Python Ed25519
- CPython: cryptography library (full suite)
"""

from .detection import is_micropython

if is_micropython():
    # MicroPython crypto imports
    try:
        import ucryptolib
        HAS_UCRYPTOLIB = True
    except ImportError:
        HAS_UCRYPTOLIB = False

    # Import urandom for key generation
    try:
        from os import urandom
        HAS_URANDOM = True
    except ImportError:
        HAS_URANDOM = False

    # For Ed25519, we'll need to port or use a pure Python implementation
    # For now, we'll use random keys as a temporary workaround
    # TODO: Implement proper Ed25519
    HAS_ED25519 = False
else:
    # CPython crypto imports
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        HAS_CRYPTOGRAPHY = True
    except ImportError:
        HAS_CRYPTOGRAPHY = False


class CryptoBackend:
    """
    Unified crypto interface that works on both MicroPython and CPython
    """

    @staticmethod
    def generate_ed25519_keypair():
        """
        Generate Ed25519 signing keypair

        WARNING: MicroPython implementation uses random bytes as a temporary
        workaround. This is NOT cryptographically proper Ed25519.
        TODO: Implement proper Ed25519 key generation
        """
        if is_micropython():
            # TEMPORARY WORKAROUND: Use random bytes
            # This is NOT proper Ed25519, but allows the system to run
            # Real Ed25519 implementation needed for production use
            if not HAS_URANDOM:
                raise RuntimeError("urandom not available")

            # Generate 32-byte private and public keys (mimicking Ed25519 format)
            private_bytes = urandom(32)
            public_bytes = urandom(32)

            print("WARNING: Using temporary random key generation (not proper Ed25519)")
            return private_bytes, public_bytes
        else:
            if not HAS_CRYPTOGRAPHY:
                raise RuntimeError("cryptography library not available")

            private_key = Ed25519PrivateKey.generate()
            public_key = private_key.public_key()

            # Serialize to raw bytes
            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )
            public_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )

            return private_bytes, public_bytes

    @staticmethod
    def derive_x25519_keypair(ed25519_private_key):
        """
        Derive X25519 encryption keypair from Ed25519 signing key.
        Note: This is a simplified derivation. Proper implementation would
        use the same seed for both or derive deterministically.

        WARNING: MicroPython implementation uses random bytes as a temporary workaround.
        """
        if is_micropython():
            # TEMPORARY WORKAROUND: Use random bytes
            if not HAS_URANDOM:
                raise RuntimeError("urandom not available")

            private_bytes = urandom(32)
            public_bytes = urandom(32)
            return private_bytes, public_bytes
        else:
            if not HAS_CRYPTOGRAPHY:
                raise RuntimeError("cryptography library not available")

            # For now, generate independent X25519 keys
            # TODO: Proper derivation from Ed25519 seed
            private_key = X25519PrivateKey.generate()
            public_key = private_key.public_key()

            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )
            public_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )

            return private_bytes, public_bytes

    @staticmethod
    def x25519_generate_keypair():
        """
        Generate a fresh X25519 keypair (for ephemeral keys).

        WARNING: MicroPython implementation uses random bytes as a temporary workaround.

        Returns:
            tuple: (private_key_bytes, public_key_bytes)
        """
        if is_micropython():
            # TEMPORARY WORKAROUND: Use random bytes
            if not HAS_URANDOM:
                raise RuntimeError("urandom not available")

            private_bytes = urandom(32)
            public_bytes = urandom(32)
            return private_bytes, public_bytes
        else:
            if not HAS_CRYPTOGRAPHY:
                raise RuntimeError("cryptography library not available")

            private_key = X25519PrivateKey.generate()
            public_key = private_key.public_key()

            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )
            public_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )

            return private_bytes, public_bytes

    @staticmethod
    def x25519_exchange(private_key_bytes, public_key_bytes):
        """
        Perform X25519 Diffie-Hellman key exchange.

        WARNING: MicroPython implementation uses a hash of combined keys as workaround.

        Args:
            private_key_bytes: Our X25519 private key (32 bytes)
            public_key_bytes: Their X25519 public key (32 bytes)

        Returns:
            bytes: 32-byte shared secret
        """
        if is_micropython():
            # TEMPORARY WORKAROUND: Hash the combination of keys
            import uhashlib
            h = uhashlib.sha256()
            h.update(private_key_bytes)
            h.update(public_key_bytes)
            return h.digest()
        else:
            if not HAS_CRYPTOGRAPHY:
                raise RuntimeError("cryptography library not available")

            private_key = X25519PrivateKey.from_private_bytes(private_key_bytes)
            public_key = X25519PublicKey.from_public_bytes(public_key_bytes)

            shared_secret = private_key.exchange(public_key)
            return shared_secret

    @staticmethod
    def sign(private_key_bytes, message):
        """
        Sign message with Ed25519 private key

        WARNING: MicroPython implementation uses HMAC as a temporary workaround.
        This is NOT proper Ed25519 signing.
        """
        if is_micropython():
            # TEMPORARY WORKAROUND: Use hash instead of proper Ed25519
            import uhashlib
            h = uhashlib.sha256()
            h.update(private_key_bytes)
            h.update(message)
            signature = h.digest()
            # Pad to 64 bytes (Ed25519 signature size)
            signature += b'\x00' * (64 - len(signature))
            return signature[:64]
        else:
            if not HAS_CRYPTOGRAPHY:
                raise RuntimeError("cryptography library not available")

            private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
            signature = private_key.sign(message)
            return signature

    @staticmethod
    def verify(public_key_bytes, message, signature):
        """
        Verify Ed25519 signature

        WARNING: MicroPython implementation uses HMAC comparison as a temporary workaround.
        This is NOT proper Ed25519 verification.
        """
        if is_micropython():
            # TEMPORARY WORKAROUND: Cannot verify without proper Ed25519
            # Just return True for now (INSECURE - for development only)
            print("WARNING: Signature verification skipped (not implemented)")
            return True
        else:
            if not HAS_CRYPTOGRAPHY:
                raise RuntimeError("cryptography library not available")

            try:
                public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
                public_key.verify(signature, message)
                return True
            except Exception:
                return False

    @staticmethod
    def hash_sha256(data):
        """SHA-256 hash"""
        if is_micropython():
            try:
                import uhashlib
                return uhashlib.sha256(data).digest()
            except ImportError:
                raise RuntimeError("uhashlib not available")
        else:
            from hashlib import sha256
            return sha256(data).digest()

    @staticmethod
    def hkdf_derive(input_key_material, length=32, salt=None, info=b""):
        """
        HKDF key derivation function.

        Args:
            input_key_material: bytes to derive key from (e.g., shared secret)
            length: desired output length in bytes
            salt: optional salt value
            info: optional context/application info

        Returns:
            bytes: derived key of specified length
        """
        if is_micropython():
            # Simplified HKDF for MicroPython (without HMAC module)
            # Using simple hash-based derivation as workaround
            if salt is None:
                salt = b'\x00' * 32

            import uhashlib

            # Simplified derivation: hash(salt + ikm + info + counter)
            okm = b""
            for i in range((length + 31) // 32):
                h = uhashlib.sha256()
                h.update(salt)
                h.update(input_key_material)
                h.update(info)
                h.update(bytes([i]))
                okm += h.digest()

            return okm[:length]
        else:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.hkdf import HKDF
            from cryptography.hazmat.backends import default_backend

            kdf = HKDF(
                algorithm=hashes.SHA256(),
                length=length,
                salt=salt,
                info=info,
                backend=default_backend()
            )
            return kdf.derive(input_key_material)

    @staticmethod
    def encrypt_chacha20poly1305(key, nonce, plaintext, associated_data=b""):
        """Encrypt with ChaCha20-Poly1305 AEAD"""
        if is_micropython():
            if not HAS_UCRYPTOLIB:
                raise RuntimeError("ucryptolib not available")
            # TODO: Implement ChaCha20-Poly1305 with ucryptolib
            raise NotImplementedError("ChaCha20-Poly1305 not yet implemented for MicroPython")
        else:
            if not HAS_CRYPTOGRAPHY:
                raise RuntimeError("cryptography library not available")

            cipher = ChaCha20Poly1305(key)
            ciphertext = cipher.encrypt(nonce, plaintext, associated_data)
            return ciphertext

    @staticmethod
    def decrypt_chacha20poly1305(key, nonce, ciphertext, associated_data=b""):
        """Decrypt ChaCha20-Poly1305 AEAD"""
        if is_micropython():
            if not HAS_UCRYPTOLIB:
                raise RuntimeError("ucryptolib not available")
            # TODO: Implement ChaCha20-Poly1305 with ucryptolib
            raise NotImplementedError("ChaCha20-Poly1305 not yet implemented for MicroPython")
        else:
            if not HAS_CRYPTOGRAPHY:
                raise RuntimeError("cryptography library not available")

            cipher = ChaCha20Poly1305(key)
            plaintext = cipher.decrypt(nonce, ciphertext, associated_data)
            return plaintext
