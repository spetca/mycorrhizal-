#!/usr/bin/env python3
"""
Group Chat Example

Demonstrates colony (group chat) functionality:
- Creating a colony
- Sharing keys with members
- Encrypted group messaging
"""

import sys
import os
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mycorrhizal.core.node import Node
from mycorrhizal.phycore.udp import UDPPhycore


def main():
    print("=" * 60)
    print("Mycorrhizal Group Chat Example")
    print("=" * 60)

    # Create three nodes
    alice = Node(name="Alice")
    bob = Node(name="Bob")
    charlie = Node(name="Charlie")

    print(f"\nAlice:   {alice.identity.address_hex()[:16]}...")
    print(f"Bob:     {bob.identity.address_hex()[:16]}...")
    print(f"Charlie: {charlie.identity.address_hex()[:16]}...")

    # Add UDP phycores (broadcast mode for local testing)
    udp_alice = UDPPhycore(name="udp_a", listen_port=6001, destinations=[6002, 6003])
    udp_bob = UDPPhycore(name="udp_b", listen_port=6002, destinations=[6001, 6003])
    udp_charlie = UDPPhycore(name="udp_c", listen_port=6003, destinations=[6001, 6002])

    alice.add_phycore(udp_alice)
    bob.add_phycore(udp_bob)
    charlie.add_phycore(udp_charlie)

    # Start nodes
    alice.start(auto_announce=False)
    bob.start(auto_announce=False)
    charlie.start(auto_announce=False)

    time.sleep(0.5)

    print("\n" + "-" * 60)
    print("Phase 1: Announce & Discovery")
    print("-" * 60)

    # Everyone announces
    alice.announce()
    time.sleep(0.3)
    bob.announce()
    time.sleep(0.3)
    charlie.announce()
    time.sleep(0.3)

    print(f"\n✓ All nodes discovered each other")
    print(f"  Alice knows: {alice.identity_cache.size()} nodes")
    print(f"  Bob knows: {bob.identity_cache.size()} nodes")
    print(f"  Charlie knows: {charlie.identity_cache.size()} nodes")

    print("\n" + "-" * 60)
    print("Phase 2: Create Colony")
    print("-" * 60)

    # Alice creates a colony
    print("\nAlice creates 'Dev Team' colony...")
    colony_alice = alice.create_colony("Dev Team")

    # Get key material for sharing
    key_material = colony_alice.get_key_material()
    print(f"Colony ID: {key_material['colony_id'].hex()[:16]}...")
    print(f"Group key: {key_material['group_key'].hex()[:16]}...")

    # Bob and Charlie join using the key material
    print("\nBob joins colony...")
    colony_bob = bob.join_colony(key_material)

    print("\nCharlie joins colony...")
    colony_charlie = charlie.join_colony(key_material)

    # Add members to Alice's colony (for name tracking)
    colony_alice.add_member(bob.identity.address,
                           bob_identity := list(alice.identity_cache.get_all().values())[0],
                           "Bob")
    colony_alice.add_member(charlie.identity.address,
                           charlie_identity := list(alice.identity_cache.get_all().values())[1],
                           "Charlie")

    # Add members to Bob's colony
    colony_bob.add_member(alice.identity.address,
                         alice_identity_bob := list(bob.identity_cache.get_all().values())[0],
                         "Alice")
    colony_bob.add_member(charlie.identity.address,
                         charlie_identity_bob := list(bob.identity_cache.get_all().values())[1],
                         "Charlie")

    # Add members to Charlie's colony
    colony_charlie.add_member(alice.identity.address,
                             alice_identity_charlie := list(charlie.identity_cache.get_all().values())[0],
                             "Alice")
    colony_charlie.add_member(bob.identity.address,
                             bob_identity_charlie := list(charlie.identity_cache.get_all().values())[1],
                             "Bob")

    print("\n" + "-" * 60)
    print("Phase 3: Group Chat")
    print("-" * 60)

    # Set up message handlers
    alice_messages = []
    bob_messages = []
    charlie_messages = []

    def alice_handler(sender_addr, sender_name, message):
        print(f"\n💬 [Dev Team] {sender_name}: {message}")
        alice_messages.append((sender_name, message))

    def bob_handler(sender_addr, sender_name, message):
        print(f"\n💬 [Dev Team] {sender_name}: {message}")
        bob_messages.append((sender_name, message))

    def charlie_handler(sender_addr, sender_name, message):
        print(f"\n💬 [Dev Team] {sender_name}: {message}")
        charlie_messages.append((sender_name, message))

    colony_alice.on_message(alice_handler)
    colony_bob.on_message(bob_handler)
    colony_charlie.on_message(charlie_handler)

    # Send some messages
    print("\nAlice: 'Hey team!'")
    colony_alice.send("Hey team!")
    time.sleep(0.5)

    print("\nBob: 'Hi Alice!'")
    colony_bob.send("Hi Alice!")
    time.sleep(0.5)

    print("\nCharlie: 'Hello everyone!'")
    colony_charlie.send("Hello everyone!")
    time.sleep(0.5)

    print("\nAlice: 'Let's build something cool'")
    colony_alice.send("Let's build something cool")
    time.sleep(0.5)

    print("\n" + "-" * 60)
    print("Results")
    print("-" * 60)

    print(f"\nAlice received {len(alice_messages)} messages:")
    for sender, msg in alice_messages:
        print(f"  - {sender}: {msg}")

    print(f"\nBob received {len(bob_messages)} messages:")
    for sender, msg in bob_messages:
        print(f"  - {sender}: {msg}")

    print(f"\nCharlie received {len(charlie_messages)} messages:")
    for sender, msg in charlie_messages:
        print(f"  - {sender}: {msg}")

    # Clean up
    alice.stop()
    bob.stop()
    charlie.stop()

    print("\n" + "=" * 60)
    total_messages = len(alice_messages) + len(bob_messages) + len(charlie_messages)
    if total_messages > 0:
        print("✓ Group chat working!")
        print(f"  {total_messages} messages delivered")
    else:
        print("✗ No messages received")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
