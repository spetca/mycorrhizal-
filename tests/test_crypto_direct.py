#!/usr/bin/env python3
"""
Direct test of E2EE crypto without Node/Packet overhead
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mycorrhizal.crypto.identity import Identity
from mycorrhizal.crypto.encryption import encrypt_to_identity, decrypt_from_identity


def test_crypto():
    print("Testing X25519 ECDH + ChaCha20-Poly1305 directly...")

    # Create two identities
    alice = Identity()
    bob = Identity()

    print(f"Alice: {alice.address_hex()[:16]}...")
    print(f"Bob:   {bob.address_hex()[:16]}...")

    # Get public identities
    alice_public = alice.get_public_identity()
    bob_public = bob.get_public_identity()

    # Convert to PublicIdentity objects
    from mycorrhizal.crypto.identity import PublicIdentity
    alice_pub_obj = PublicIdentity(
        alice_public['signing_public_key'],
        alice_public['encryption_public_key']
    )
    bob_pub_obj = PublicIdentity(
        bob_public['signing_public_key'],
        bob_public['encryption_public_key']
    )

    # Test 1: Alice encrypts to Bob
    message1 = b"Hello Bob, this is Alice!"
    print(f"\n1. Alice encrypts: {message1}")
    encrypted1 = encrypt_to_identity(message1, bob_pub_obj, alice)
    print(f"   Encrypted: {len(encrypted1)} bytes")

    # Bob decrypts from Alice
    decrypted1 = decrypt_from_identity(encrypted1, alice_pub_obj, bob)
    print(f"   Bob decrypts: {decrypted1}")
    assert decrypted1 == message1, "Decryption failed!"
    print("   ✓ Success!")

    # Test 2: Bob encrypts to Alice
    message2 = b"Hi Alice, got your message!"
    print(f"\n2. Bob encrypts: {message2}")
    encrypted2 = encrypt_to_identity(message2, alice_pub_obj, bob)
    print(f"   Encrypted: {len(encrypted2)} bytes")

    # Alice decrypts from Bob
    decrypted2 = decrypt_from_identity(encrypted2, bob_pub_obj, alice)
    print(f"   Alice decrypts: {decrypted2}")
    assert decrypted2 == message2, "Decryption failed!"
    print("   ✓ Success!")

    print("\n✓ All crypto tests passed!")


if __name__ == "__main__":
    test_crypto()
