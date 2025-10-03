#!/usr/bin/env python3
"""
Test Multi-Hop Routing

Tests routing and forwarding with 3 nodes in a chain:
Alice ↔ Bob ↔ Charlie

Alice cannot directly reach Charlie, so Bob must forward.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mycorrhizal.core.node import Node
from mycorrhizal.phycore.udp import UDPPhycore


def test_three_node_routing():
    print("=" * 70)
    print("Multi-Hop Routing Test (3 Nodes)")
    print("=" * 70)

    # Create three nodes
    alice = Node(name="Alice")
    bob = Node(name="Bob (Relay)")
    charlie = Node(name="Charlie")

    print(f"\nAlice:   {alice.identity.address_hex()[:16]}...")
    print(f"Bob:     {bob.identity.address_hex()[:16]}...")
    print(f"Charlie: {charlie.identity.address_hex()[:16]}...")

    # Setup network topology: Alice ↔ Bob ↔ Charlie
    # Alice can only talk to Bob (port 7001 ↔ 7002)
    # Bob can talk to Alice (7002 ↔ 7001) and Charlie (7002 ↔ 7003)
    # Charlie can only talk to Bob (7003 ↔ 7002)

    print("\n" + "-" * 70)
    print("Network Topology:")
    print("  Alice (7001) ↔ Bob (7002) ↔ Charlie (7003)")
    print("  Alice cannot directly reach Charlie - Bob must forward")
    print("-" * 70)

    # Alice: talks to Bob only
    udp_alice = UDPPhycore(name="udp_a", listen_port=7001, destinations=7002)
    alice.add_phycore(udp_alice)

    # Bob: needs separate phycores for each link to track forwarding properly
    udp_bob_to_alice = UDPPhycore(name="udp_b_alice", listen_port=7002, destinations=7001)
    udp_bob_to_charlie = UDPPhycore(name="udp_b_charlie", listen_port=7004, destinations=7003)
    bob.add_phycore(udp_bob_to_alice)
    bob.add_phycore(udp_bob_to_charlie)

    # Charlie: talks to Bob only (update to use Bob's new port)
    udp_charlie = UDPPhycore(name="udp_c", listen_port=7003, destinations=7004)
    charlie.add_phycore(udp_charlie)

    # Start nodes
    alice.start(auto_announce=False)
    bob.start(auto_announce=False)
    charlie.start(auto_announce=False)

    time.sleep(0.5)

    print("\n" + "-" * 70)
    print("Phase 1: Path Discovery via Announces")
    print("-" * 70)

    # Alice announces (Bob hears, Charlie doesn't)
    print("\n1. Alice announces...")
    alice.announce(verbose=False)
    time.sleep(0.5)

    print(f"   Bob's routes: {bob.route_table.size()}")
    print(f"   Charlie's routes: {charlie.route_table.size()}")

    # Bob announces (Alice and Charlie both hear)
    print("\n2. Bob announces...")
    bob.announce(verbose=False)
    time.sleep(0.5)

    print(f"   Alice's routes: {alice.route_table.size()}")
    print(f"   Charlie's routes: {charlie.route_table.size()}")

    # Charlie announces (Bob hears, Bob forwards to Alice)
    print("\n3. Charlie announces...")
    charlie.announce(verbose=False)
    time.sleep(1.0)  # Give time for forwarding

    print(f"\n✓ Path discovery complete")
    print(f"   Alice's routes: {alice.route_table.size()}")
    for route in alice.route_table.get_all_routes():
        print(f"     - {route}")

    print(f"   Bob's routes: {bob.route_table.size()}")
    for route in bob.route_table.get_all_routes():
        print(f"     - {route}")

    print(f"   Charlie's routes: {charlie.route_table.size()}")
    for route in charlie.route_table.get_all_routes():
        print(f"     - {route}")

    print("\n" + "-" * 70)
    print("Phase 2: Multi-Hop Messaging")
    print("-" * 70)

    # Set up message receivers
    alice_received = []
    charlie_received = []

    def alice_handler(payload, source, packet):
        msg = payload.decode('utf-8')
        print(f"\n✓ Alice received: '{msg}' (hops={packet.hop_count})")
        alice_received.append(msg)

    def charlie_handler(payload, source, packet):
        msg = payload.decode('utf-8')
        print(f"\n✓ Charlie received: '{msg}' (hops={packet.hop_count})")
        charlie_received.append(msg)

    alice.on_data(alice_handler)
    charlie.on_data(charlie_handler)

    # Alice sends to Charlie (should be forwarded by Bob)
    print("\n1. Alice → Charlie: 'Hello from Alice!'")
    alice.send_data(charlie.identity.address, b"Hello from Alice!")
    time.sleep(0.5)

    # Charlie sends to Alice (should be forwarded by Bob)
    print("\n2. Charlie → Alice: 'Hi Alice, got your message!'")
    charlie.send_data(alice.identity.address, b"Hi Alice, got your message!")
    time.sleep(0.5)

    # Another message from Alice to Charlie
    print("\n3. Alice → Charlie: 'Multi-hop routing works!'")
    alice.send_data(charlie.identity.address, b"Multi-hop routing works!")
    time.sleep(0.5)

    print("\n" + "-" * 70)
    print("Results")
    print("-" * 70)

    print(f"\nAlice received {len(alice_received)} message(s):")
    for msg in alice_received:
        print(f"  ✓ {msg}")

    print(f"\nCharlie received {len(charlie_received)} message(s):")
    for msg in charlie_received:
        print(f"  ✓ {msg}")

    # Clean up
    alice.stop()
    bob.stop()
    charlie.stop()

    print("\n" + "=" * 70)
    if len(alice_received) > 0 and len(charlie_received) > 0:
        print("✓ Multi-hop routing test PASSED!")
        print(f"  {len(alice_received) + len(charlie_received)} messages delivered via Bob")
    else:
        print("✗ Multi-hop routing test FAILED")
        print(f"  Expected messages but got: Alice={len(alice_received)}, Charlie={len(charlie_received)}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        test_three_node_routing()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
