"""
Identity System - Cryptographic identities with 128-bit addresses

Each identity consists of:
- Ed25519 signing keypair (for authentication)
- X25519 encryption keypair (for E2EE)
- 128-bit address derived from public key
"""

from ..platform.crypto_adapter import CryptoBackend


class Identity:
    """
    Cryptographic identity with signing and encryption capabilities.

    Address generation:
    - Take Ed25519 public key (32 bytes)
    - Hash with SHA-256 (32 bytes)
    - Truncate to first 16 bytes (128 bits)
    - This gives a globally unique cryptographic address
    """

    def __init__(self, signing_private_key=None, signing_public_key=None,
                 encryption_private_key=None, encryption_public_key=None):
        """
        Create identity from existing keys or generate new ones.

        Args:
            signing_private_key: Ed25519 private key (32 bytes)
            signing_public_key: Ed25519 public key (32 bytes)
            encryption_private_key: X25519 private key (32 bytes)
            encryption_public_key: X25519 public key (32 bytes)
        """
        if signing_private_key is None:
            # Generate new identity
            self.signing_private_key, self.signing_public_key = \
                CryptoBackend.generate_ed25519_keypair()

            self.encryption_private_key, self.encryption_public_key = \
                CryptoBackend.derive_x25519_keypair(self.signing_private_key)
        else:
            # Load existing identity
            self.signing_private_key = signing_private_key
            self.signing_public_key = signing_public_key
            self.encryption_private_key = encryption_private_key
            self.encryption_public_key = encryption_public_key

        # Generate 128-bit address from public key
        self.address = self._generate_address()

    def _generate_address(self):
        """
        Generate 128-bit address from signing public key.

        Returns:
            bytes: 16-byte (128-bit) address
        """
        # Hash the public key
        hash_digest = CryptoBackend.hash_sha256(self.signing_public_key)

        # Take first 16 bytes (128 bits)
        address = hash_digest[:16]

        return address

    def sign(self, message):
        """
        Sign a message with this identity.

        Args:
            message: bytes to sign

        Returns:
            bytes: Ed25519 signature (64 bytes)
        """
        return CryptoBackend.sign(self.signing_private_key, message)

    def verify(self, message, signature):
        """
        Verify a signature against this identity's public key.

        Args:
            message: bytes that were signed
            signature: signature to verify

        Returns:
            bool: True if signature is valid
        """
        return CryptoBackend.verify(self.signing_public_key, message, signature)

    def get_public_identity(self):
        """
        Get public identity information for sharing.

        Returns:
            dict: Public keys and address
        """
        return {
            'address': self.address,
            'signing_public_key': self.signing_public_key,
            'encryption_public_key': self.encryption_public_key
        }

    def to_bytes(self):
        """
        Serialize identity to bytes for storage.

        Format:
        - 32 bytes: Ed25519 private key
        - 32 bytes: Ed25519 public key
        - 32 bytes: X25519 private key
        - 32 bytes: X25519 public key
        Total: 128 bytes

        Returns:
            bytes: Serialized identity
        """
        return (self.signing_private_key +
                self.signing_public_key +
                self.encryption_private_key +
                self.encryption_public_key)

    @staticmethod
    def from_bytes(data):
        """
        Deserialize identity from bytes.

        Args:
            data: 128 bytes of serialized identity

        Returns:
            Identity: Reconstructed identity
        """
        if len(data) != 128:
            raise ValueError(f"Invalid identity data length: {len(data)} (expected 128)")

        signing_private_key = data[0:32]
        signing_public_key = data[32:64]
        encryption_private_key = data[64:96]
        encryption_public_key = data[96:128]

        return Identity(
            signing_private_key=signing_private_key,
            signing_public_key=signing_public_key,
            encryption_private_key=encryption_private_key,
            encryption_public_key=encryption_public_key
        )

    def address_hex(self):
        """Get address as hex string"""
        return self.address.hex()

    def __repr__(self):
        return f"Identity(address={self.address_hex()})"


class PublicIdentity:
    """
    Public identity of another node (no private keys).
    Used for verifying signatures and encrypting to remote nodes.
    """

    def __init__(self, signing_public_key, encryption_public_key):
        """
        Create public identity from public keys.

        Args:
            signing_public_key: Ed25519 public key (32 bytes)
            encryption_public_key: X25519 public key (32 bytes)
        """
        self.signing_public_key = signing_public_key
        self.encryption_public_key = encryption_public_key
        self.address = self._generate_address()

    def _generate_address(self):
        """Generate address from public key"""
        hash_digest = CryptoBackend.hash_sha256(self.signing_public_key)
        return hash_digest[:16]

    def verify(self, message, signature):
        """Verify signature from this identity"""
        return CryptoBackend.verify(self.signing_public_key, message, signature)

    def address_hex(self):
        """Get address as hex string"""
        return self.address.hex()

    def __repr__(self):
        return f"PublicIdentity(address={self.address_hex()})"
