#!/usr/bin/env python3
"""
Test announce system and identity discovery

This test demonstrates:
1. Nodes announcing their presence
2. Other nodes caching the announced identities
3. Using cached identities to verify signatures
4. Identifying message senders
"""

import sys
import os
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mycorrhizal.core.node import Node
from mycorrhizal.phycore.udp import UDPPhycore


def test_announce_discovery():
    """Test nodes discovering each other through announces"""
    print("=" * 60)
    print("Announce System Test")
    print("=" * 60)

    # Create three nodes
    node_a = Node(name="Alice")
    node_b = Node(name="Bob")
    node_c = Node(name="Charlie")

    print(f"\nAlice:   {node_a.identity.address_hex()}")
    print(f"Bob:     {node_b.identity.address_hex()}")
    print(f"Charlie: {node_c.identity.address_hex()}")

    # Add UDP phycores - each listens on own port, broadcasts to others
    # Alice: listens on 5001, sends to 5002 and 5003
    # Bob: listens on 5002, sends to 5001 and 5003
    # Charlie: listens on 5003, sends to 5001 and 5002
    udp_a = UDPPhycore(name="udp_a", listen_port=5001, destinations=[5002, 5003])
    udp_b = UDPPhycore(name="udp_b", listen_port=5002, destinations=[5001, 5003])
    udp_c = UDPPhycore(name="udp_c", listen_port=5003, destinations=[5001, 5002])

    node_a.add_phycore(udp_a)
    node_b.add_phycore(udp_b)
    node_c.add_phycore(udp_c)

    # Track messages
    received_by_a = []
    received_by_b = []
    received_by_c = []

    def on_data_a(payload, source, packet):
        print(f"\n💬 Alice received from {source.hex()[:16] if source else 'unknown'}...")
        print(f"   Message: {payload.decode()}")
        received_by_a.append((payload, source))

    def on_data_b(payload, source, packet):
        print(f"\n💬 Bob received from {source.hex()[:16] if source else 'unknown'}...")
        print(f"   Message: {payload.decode()}")
        received_by_b.append((payload, source))

    def on_data_c(payload, source, packet):
        print(f"\n💬 Charlie received from {source.hex()[:16] if source else 'unknown'}...")
        print(f"   Message: {payload.decode()}")
        received_by_c.append((payload, source))

    node_a.on_data(on_data_a)
    node_b.on_data(on_data_b)
    node_c.on_data(on_data_c)

    # Start nodes (without auto-announce for manual control)
    node_a.start(auto_announce=False)
    node_b.start(auto_announce=False)
    node_c.start(auto_announce=False)

    time.sleep(0.5)

    print("\n" + "-" * 60)
    print("Phase 1: Announces")
    print("-" * 60)

    # Each node announces
    print("\n1. Alice announces...")
    result_a = node_a.announce()
    print(f"   Announce sent: {result_a}")
    time.sleep(0.5)

    print("\n2. Bob announces...")
    result_b = node_b.announce()
    print(f"   Announce sent: {result_b}")
    time.sleep(0.5)

    print("\n3. Charlie announces...")
    result_c = node_c.announce()
    print(f"   Announce sent: {result_c}")
    time.sleep(0.5)

    # Check identity caches
    print("\n" + "-" * 60)
    print("Identity Cache Status")
    print("-" * 60)
    print(f"Alice knows about: {node_a.identity_cache.size()} node(s)")
    print(f"Bob knows about: {node_b.identity_cache.size()} node(s)")
    print(f"Charlie knows about: {node_c.identity_cache.size()} node(s)")

    print("\n" + "-" * 60)
    print("Phase 2: Authenticated Messages")
    print("-" * 60)

    # Now send messages - they should be verified using cached identities
    print("\n4. Alice -> Bob: 'Hello Bob!'")
    node_a.send_data(node_b.address, b"Hello Bob!", sign=True)
    time.sleep(0.3)

    print("\n5. Bob -> Charlie: 'Hey Charlie!'")
    node_b.send_data(node_c.address, b"Hey Charlie!", sign=True)
    time.sleep(0.3)

    print("\n6. Charlie -> Alice: 'Hi Alice!'")
    node_c.send_data(node_a.address, b"Hi Alice!", sign=True)
    time.sleep(0.3)

    # Verify results
    print("\n" + "-" * 60)
    print("Results")
    print("-" * 60)

    print(f"\nAlice received {len(received_by_a)} message(s):")
    for payload, source in received_by_a:
        if source:
            print(f"  ✓ From {source.hex()[:16]}...: {payload.decode()}")
        else:
            print(f"  ⚠️  From unknown: {payload.decode()}")

    print(f"\nBob received {len(received_by_b)} message(s):")
    for payload, source in received_by_b:
        if source:
            print(f"  ✓ From {source.hex()[:16]}...: {payload.decode()}")
        else:
            print(f"  ⚠️  From unknown: {payload.decode()}")

    print(f"\nCharlie received {len(received_by_c)} message(s):")
    for payload, source in received_by_c:
        if source:
            print(f"  ✓ From {source.hex()[:16]}...: {payload.decode()}")
        else:
            print(f"  ⚠️  From unknown: {payload.decode()}")

    # Stop nodes
    node_a.stop()
    node_b.stop()
    node_c.stop()

    # Verify all messages were authenticated
    print("\n" + "=" * 60)
    all_authenticated = True

    # Check if all received messages have identified senders
    for payload, source in received_by_a + received_by_b + received_by_c:
        if source is None:
            all_authenticated = False
            break

    if all_authenticated and len(received_by_a) == 1 and len(received_by_b) == 1 and len(received_by_c) == 1:
        print("✓ Announce system test passed!")
        print("  - All nodes discovered each other")
        print("  - All messages were authenticated")
        print("  - Senders were correctly identified")
    else:
        print("✗ Announce system test failed")
        if not all_authenticated:
            print("  - Some messages could not be authenticated")
        if len(received_by_a) != 1 or len(received_by_b) != 1 or len(received_by_c) != 1:
            print("  - Not all messages were received")

    print("=" * 60)


def main():
    try:
        test_announce_discovery()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
