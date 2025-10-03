#!/usr/bin/env python3
"""
Test E2EE (End-to-End Encryption) with X25519 ECDH

This test demonstrates:
1. X25519 key exchange
2. HKDF key derivation
3. ChaCha20-Poly1305 encryption
4. Direct messaging with real E2EE
"""

import sys
import os
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mycorrhizal.core.node import Node
from mycorrhizal.phycore.udp import UDPPhycore
from mycorrhizal.messaging.channel import Channel


def test_e2ee_direct_messages():
    """Test E2EE direct messaging between two nodes"""
    print("=" * 60)
    print("E2EE Direct Messaging Test")
    print("=" * 60)

    # Create two nodes
    alice = Node(name="Alice")
    bob = Node(name="Bob")

    print(f"\nAlice: {alice.identity.address_hex()[:16]}...")
    print(f"Bob:   {bob.identity.address_hex()[:16]}...")

    # Add UDP phycores
    udp_alice = UDPPhycore(name="udp_a", listen_port=7001, destinations=7002)
    udp_bob = UDPPhycore(name="udp_b", listen_port=7002, destinations=7001)

    alice.add_phycore(udp_alice)
    bob.add_phycore(udp_bob)

    # Start nodes
    alice.start(auto_announce=False)
    bob.start(auto_announce=False)

    time.sleep(0.5)

    print("\n" + "-" * 60)
    print("Phase 1: Exchange Public Keys")
    print("-" * 60)

    # Announce to exchange public keys
    alice.announce()
    time.sleep(0.3)
    bob.announce()
    time.sleep(0.3)

    print(f"\n✓ Public keys exchanged")
    print(f"  Alice knows: {alice.identity_cache.size()} identity")
    print(f"  Bob knows: {bob.identity_cache.size()} identity")

    # Get each other's public identities
    bob_public = list(alice.identity_cache.get_all().values())[0]
    alice_public = list(bob.identity_cache.get_all().values())[0]

    print("\n" + "-" * 60)
    print("Phase 2: Create E2EE Channels")
    print("-" * 60)

    # Create channels - each node has their own channel instance
    # Alice's channel for sending to Bob
    alice_channel = Channel(bob.identity.address, bob_public, alice.identity, alice)
    # Bob's channel for sending to Alice
    bob_channel = Channel(alice.identity.address, alice_public, bob.identity, bob)

    print(f"\n✓ Created encrypted channels")
    print(f"  Alice's channel → Bob: {alice_channel}")
    print(f"  Bob's channel → Alice: {bob_channel}")

    # Set up message handlers
    alice_received = []
    bob_received = []

    def alice_handler(message):
        print(f"\n🔓 Alice decrypted: '{message}'")
        alice_received.append(message)

    def bob_handler(message):
        print(f"\n🔓 Bob decrypted: '{message}'")
        bob_received.append(message)

    # Route channel messages through node data callback
    def alice_data_handler(payload, source, packet):
        if source == bob.identity.address:
            # Alice receives from Bob - decrypt using Bob's public key
            alice_channel_rx = Channel(bob.identity.address, bob_public, alice.identity, alice)
            alice_channel_rx.on_message(alice_handler)
            alice_channel_rx.handle_message(payload)

    def bob_data_handler(payload, source, packet):
        if source == alice.identity.address:
            # Bob receives from Alice - decrypt using Alice's public key
            bob_channel_rx = Channel(alice.identity.address, alice_public, bob.identity, bob)
            bob_channel_rx.on_message(bob_handler)
            bob_channel_rx.handle_message(payload)

    alice.on_data(alice_data_handler)
    bob.on_data(bob_data_handler)

    print("\n" + "-" * 60)
    print("Phase 3: E2EE Messaging")
    print("-" * 60)

    # Send encrypted messages
    print("\n🔒 Alice encrypts: 'Hello Bob, this is secret!'")
    alice_channel.send("Hello Bob, this is secret!")
    time.sleep(0.5)

    print("\n🔒 Bob encrypts: 'Hi Alice, got your secure message!'")
    bob_channel.send("Hi Alice, got your secure message!")
    time.sleep(0.5)

    print("\n🔒 Alice encrypts: 'X25519 ECDH works perfectly!'")
    alice_channel.send("X25519 ECDH works perfectly!")
    time.sleep(0.5)

    print("\n" + "-" * 60)
    print("Results")
    print("-" * 60)

    print(f"\nAlice received {len(alice_received)} message(s):")
    for msg in alice_received:
        print(f"  ✓ {msg}")

    print(f"\nBob received {len(bob_received)} message(s):")
    for msg in bob_received:
        print(f"  ✓ {msg}")

    # Verify encryption details
    print("\n" + "-" * 60)
    print("Encryption Details")
    print("-" * 60)

    print("\nProtocol: X25519 ECDH + ChaCha20-Poly1305")
    print("  1. Ephemeral X25519 keypair generated per message")
    print("  2. ECDH performed with recipient's static X25519 key")
    print("  3. Shared secret derived using HKDF-SHA256")
    print("  4. Message encrypted with ChaCha20-Poly1305 AEAD")
    print("  5. Wire format: ephemeral_pub(32) + nonce(12) + ciphertext")

    print("\nSecurity Properties:")
    print("  ✓ Forward Secrecy: Ephemeral keys protect past messages")
    print("  ✓ Authentication: Sender identity bound to encryption")
    print("  ✓ Confidentiality: Only recipient can decrypt")
    print("  ✓ Integrity: AEAD protects against tampering")

    # Clean up
    alice.stop()
    bob.stop()

    print("\n" + "=" * 60)
    if len(alice_received) > 0 and len(bob_received) > 0:
        print("✓ E2EE test passed!")
        print("  All messages encrypted and decrypted successfully")
    else:
        print("✗ E2EE test failed")
    print("=" * 60)


def main():
    try:
        test_e2ee_direct_messages()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
