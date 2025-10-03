#!/usr/bin/env python3
"""
Test node-to-node communication via UDP

This test creates two nodes on the same machine and has them
communicate via UDP broadcast.
"""

import sys
import os
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mycorrhizal.core.node import Node
from mycorrhizal.phycore.udp import UDPPhycore


def test_two_nodes():
    """Test two nodes communicating via UDP"""
    print("=" * 60)
    print("Two-Node Communication Test")
    print("=" * 60)

    # Create two nodes
    node_a = Node(name="NodeA")
    node_b = Node(name="NodeB")

    print(f"\nNode A address: {node_a.identity.address_hex()}")
    print(f"Node B address: {node_b.identity.address_hex()}")

    # Add UDP phycores
    # Node A listens on 4242, sends to 4243
    # Node B listens on 4243, sends to 4242
    udp_a = UDPPhycore(name="udp_a", listen_port=4242, destinations=4243)
    udp_b = UDPPhycore(name="udp_b", listen_port=4243, destinations=4242)

    node_a.add_phycore(udp_a)
    node_b.add_phycore(udp_b)

    # Track received messages
    received_by_a = []
    received_by_b = []

    def on_data_a(payload, source, packet):
        print(f"\n📨 Node A received: {payload}")
        received_by_a.append(payload)

    def on_data_b(payload, source, packet):
        print(f"\n📨 Node B received: {payload}")
        received_by_b.append(payload)

    node_a.on_data(on_data_a)
    node_b.on_data(on_data_b)

    # Start nodes
    node_a.start()
    node_b.start()

    print("\n" + "-" * 60)
    print("Testing Communication")
    print("-" * 60)

    # Give interfaces time to come up and start receiving
    time.sleep(1.0)

    # Node A announces
    print("\n1. Node A announces...")
    node_a.announce()
    time.sleep(0.2)

    # Node B announces
    print("\n2. Node B announces...")
    node_b.announce()
    time.sleep(0.2)

    # Node A sends to Node B
    print(f"\n3. Node A -> Node B: 'Hello from A'")
    message_a_to_b = b"Hello from A"
    node_a.send_data(node_b.address, message_a_to_b)
    time.sleep(0.2)

    # Node B sends to Node A
    print(f"\n4. Node B -> Node A: 'Hello from B'")
    message_b_to_a = b"Hello from B"
    node_b.send_data(node_a.address, message_b_to_a)
    time.sleep(0.2)

    # Check results
    print("\n" + "-" * 60)
    print("Results")
    print("-" * 60)

    print(f"\nNode A received {len(received_by_a)} message(s):")
    for msg in received_by_a:
        print(f"  - {msg}")

    print(f"\nNode B received {len(received_by_b)} message(s):")
    for msg in received_by_b:
        print(f"  - {msg}")

    # Print stats
    print("\n" + "-" * 60)
    print("Statistics")
    print("-" * 60)

    stats_a = node_a.get_stats()
    stats_b = node_b.get_stats()

    print(f"\nNode A ({stats_a['address'][:16]}...):")
    for phycore_stats in stats_a['phycores']:
        print(f"  {phycore_stats['name']}:")
        print(f"    TX: {phycore_stats['tx_count']} packets, {phycore_stats['tx_bytes']} bytes")
        print(f"    RX: {phycore_stats['rx_count']} packets, {phycore_stats['rx_bytes']} bytes")

    print(f"\nNode B ({stats_b['address'][:16]}...):")
    for phycore_stats in stats_b['phycores']:
        print(f"  {phycore_stats['name']}:")
        print(f"    TX: {phycore_stats['tx_count']} packets, {phycore_stats['tx_bytes']} bytes")
        print(f"    RX: {phycore_stats['rx_count']} packets, {phycore_stats['rx_bytes']} bytes")

    # Stop nodes
    node_a.stop()
    node_b.stop()

    print("\n" + "=" * 60)
    if message_b_to_a in received_by_a and message_a_to_b in received_by_b:
        print("✓ Communication test passed!")
    else:
        print("✗ Communication test failed - messages not received")
        if message_b_to_a not in received_by_a:
            print("  Node A did not receive message from B")
        if message_a_to_b not in received_by_b:
            print("  Node B did not receive message from A")
    print("=" * 60)


def main():
    try:
        test_two_nodes()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
