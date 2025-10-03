#!/usr/bin/env python3
"""
Simple Desktop Node (Linux/Mac)

This example shows how to create a Mycorrhizal node on a desktop computer
using UDP for local testing or internet communication.

Platform: Linux, macOS, Windows (CPython 3.8+)
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
    print("Mycorrhizal Desktop Node")
    print("=" * 60)

    # Create node
    node = Node(name="Desktop Node")

    print(f"\nNode created:")
    print(f"  Name: {node.name}")
    print(f"  Address: {node.identity.address_hex()}")
    print(f"  Platform: {node.profile.platform}")
    print(f"  Capability: {node.profile.capability}")

    # Add UDP phycore for local network communication
    # This creates a broadcast interface on port 7000
    udp = UDPPhycore(
        name="udp0",
        listen_port=7000,           # Port to listen on
        destinations=[7001, 7002]   # Ports to broadcast to (other local nodes)
    )

    node.add_phycore(udp)

    # Set up message handler
    def on_data(payload, source_address, packet):
        print(f"\n📨 Received message:")
        print(f"   From: {source_address.hex() if source_address else 'unknown'}")
        print(f"   Message: {payload.decode('utf-8', errors='replace')}")

    node.on_data(on_data)

    # Set up announce handler
    def on_announce(packet, public_identity):
        print(f"   Found peer: {packet.destination.hex()[:16]}...")

    node.on_announce(on_announce)

    # Start node
    print("\nStarting node...")
    node.start(auto_announce=True, announce_now=True)

    print("\n" + "-" * 60)
    print("Node is running. Commands:")
    print("  'm <message>'  - Send message to all known peers")
    print("  'a'            - Send announce")
    print("  's'            - Show stats")
    print("  'q'            - Quit")
    print("-" * 60)

    try:
        while True:
            cmd = input("\n> ").strip()

            if cmd.lower() == 'q':
                break
            elif cmd.lower() == 'a':
                node.announce()
            elif cmd.lower() == 's':
                print(f"\nNode stats:")
                print(f"  Known identities: {node.identity_cache.size()}")
                print(f"  Routes: {node.route_table.size()}")
                for phycore in node.phycores:
                    print(f"  {phycore.name}:")
                    print(f"    TX: {phycore.tx_count} packets, {phycore.tx_bytes} bytes")
                    print(f"    RX: {phycore.rx_count} packets, {phycore.rx_bytes} bytes")
            elif cmd.startswith('m '):
                message = cmd[2:].strip()
                if not message:
                    print("No message provided")
                    continue

                # Send to all known identities
                peers = node.identity_cache.get_all()
                if not peers:
                    print("No known peers yet. Wait for announces or send one with 'a'")
                else:
                    for addr_hex, identity in peers.items():
                        dest_addr = bytes.fromhex(addr_hex)
                        print(f"Sending to {addr_hex[:16]}...")
                        node.send_data(dest_addr, message.encode('utf-8'))
            else:
                print("Unknown command")

    except KeyboardInterrupt:
        print("\nShutting down...")

    finally:
        node.stop()
        print("Node stopped")


if __name__ == "__main__":
    main()
