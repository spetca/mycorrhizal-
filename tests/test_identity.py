#!/usr/bin/env python3
"""
Test identity and cryptographic operations
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mycorrhizal.crypto.identity import Identity, PublicIdentity


def test_identity_generation():
    """Test generating new identities"""
    print("\n" + "="*60)
    print("Test: Identity Generation")
    print("="*60)

    identity = Identity()
    print(f"✓ Generated new identity: {identity.address_hex()}")
    print(f"  Signing public key: {identity.signing_public_key.hex()[:32]}...")
    print(f"  Encryption public key: {identity.encryption_public_key.hex()[:32]}...")
    return identity


def test_signing(identity):
    """Test signing and verification"""
    print("\n" + "="*60)
    print("Test: Signing and Verification")
    print("="*60)

    message = b"Hello, Mycorrhizal!"
    signature = identity.sign(message)

    print(f"✓ Signed message: {message}")
    print(f"  Signature: {signature.hex()[:32]}...")

    # Verify with own identity
    valid = identity.verify(message, signature)
    print(f"✓ Self-verification: {valid}")

    # Verify with wrong message
    wrong_valid = identity.verify(b"Different message", signature)
    print(f"✓ Wrong message verification: {wrong_valid} (should be False)")

    assert valid == True
    assert wrong_valid == False


def test_public_identity(identity):
    """Test public identity creation"""
    print("\n" + "="*60)
    print("Test: Public Identity")
    print("="*60)

    public_info = identity.get_public_identity()
    public_identity = PublicIdentity(
        public_info['signing_public_key'],
        public_info['encryption_public_key']
    )

    print(f"✓ Created public identity: {public_identity.address_hex()}")
    print(f"  Address matches: {public_identity.address == identity.address}")

    # Test signature verification with public identity
    message = b"Test message"
    signature = identity.sign(message)
    valid = public_identity.verify(message, signature)

    print(f"✓ Signature verification via public identity: {valid}")

    assert public_identity.address == identity.address
    assert valid == True


def test_serialization(identity):
    """Test identity serialization and deserialization"""
    print("\n" + "="*60)
    print("Test: Serialization")
    print("="*60)

    # Serialize
    serialized = identity.to_bytes()
    print(f"✓ Serialized identity: {len(serialized)} bytes")

    # Deserialize
    restored = Identity.from_bytes(serialized)
    print(f"✓ Restored identity: {restored.address_hex()}")

    # Verify addresses match
    print(f"  Addresses match: {restored.address == identity.address}")
    print(f"  Keys match: {restored.signing_private_key == identity.signing_private_key}")

    # Test signing with restored identity
    message = b"Test after restore"
    signature = restored.sign(message)
    valid = identity.verify(message, signature)
    print(f"✓ Signature from restored identity verifies: {valid}")

    assert restored.address == identity.address
    assert valid == True


def test_multiple_identities():
    """Test multiple identities with different addresses"""
    print("\n" + "="*60)
    print("Test: Multiple Identities")
    print("="*60)

    identity1 = Identity()
    identity2 = Identity()
    identity3 = Identity()

    print(f"✓ Identity 1: {identity1.address_hex()}")
    print(f"✓ Identity 2: {identity2.address_hex()}")
    print(f"✓ Identity 3: {identity3.address_hex()}")

    # Verify all addresses are different
    assert identity1.address != identity2.address
    assert identity1.address != identity3.address
    assert identity2.address != identity3.address

    print(f"\n  All addresses are unique: ✓")


def main():
    print("=" * 60)
    print("Mycorrhizal Identity System Test")
    print("=" * 60)

    try:
        identity = test_identity_generation()
        test_signing(identity)
        test_public_identity(identity)
        test_serialization(identity)
        test_multiple_identities()

        print("\n" + "="*60)
        print("✓ All tests passed!")
        print("="*60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
