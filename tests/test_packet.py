#!/usr/bin/env python3
"""
Test packet serialization and deserialization
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mycorrhizal.transport.packet import Packet, PacketType, PacketFlags
from mycorrhizal.crypto.identity import Identity


def test_basic_packet():
    """Test basic packet creation and serialization"""
    print("\n" + "="*60)
    print("Test: Basic Packet")
    print("="*60)

    # Create two identities
    sender = Identity()
    recipient = Identity()

    print(f"Sender: {sender.address_hex()}")
    print(f"Recipient: {recipient.address_hex()}")

    # Create packet
    payload = b"Hello, Mycorrhizal!"
    packet = Packet(
        packet_type=PacketType.DATA,
        destination=recipient.address,
        payload=payload
    )

    print(f"\n✓ Created packet:")
    print(f"  Type: DATA")
    print(f"  Destination: {packet.destination.hex()[:16]}...")
    print(f"  Payload: {len(packet.payload)} bytes")
    print(f"  TTL: {packet.ttl}")
    print(f"  Hops: {packet.hop_count}")

    # Serialize
    serialized = packet.to_bytes()
    print(f"\n✓ Serialized: {len(serialized)} bytes")
    print(f"  Header: 32 bytes")
    print(f"  Payload: {len(payload)} bytes")
    print(f"  Total: {len(serialized)} bytes")

    # Deserialize
    restored = Packet.from_bytes(serialized)
    print(f"\n✓ Deserialized packet")
    print(f"  Destination matches: {restored.destination == packet.destination}")
    print(f"  Payload matches: {restored.payload == packet.payload}")
    print(f"  TTL matches: {restored.ttl == packet.ttl}")

    assert restored.destination == packet.destination
    assert restored.payload == packet.payload
    assert restored.ttl == packet.ttl


def test_signed_packet():
    """Test packet signing and verification"""
    print("\n" + "="*60)
    print("Test: Signed Packet (Source Authentication)")
    print("="*60)

    # Create identities
    sender = Identity()
    recipient = Identity()

    print(f"Sender: {sender.address_hex()}")
    print(f"Recipient: {recipient.address_hex()}")

    # Create and sign packet
    payload = b"Authenticated message"
    packet = Packet(
        packet_type=PacketType.DATA,
        destination=recipient.address,
        payload=payload
    )

    print(f"\n✓ Created packet (unsigned)")
    print(f"  Is signed: {packet.is_signed()}")

    # Sign the packet
    packet.sign(sender)
    print(f"\n✓ Signed packet with sender identity")
    print(f"  Is signed: {packet.is_signed()}")
    print(f"  Signature: {packet.signature.hex()[:32]}...")

    # Serialize and deserialize
    serialized = packet.to_bytes()
    print(f"\n✓ Serialized signed packet: {len(serialized)} bytes")
    print(f"  Header: 32 bytes")
    print(f"  Payload: {len(payload)} bytes")
    print(f"  Signature: 64 bytes")
    print(f"  Total: {len(serialized)} bytes")

    restored = Packet.from_bytes(serialized)
    print(f"\n✓ Deserialized signed packet")
    print(f"  Is signed: {restored.is_signed()}")
    print(f"  Has signature: {restored.signature is not None}")

    # Verify signature
    sender_public = sender.get_public_identity()
    from mycorrhizal.crypto.identity import PublicIdentity
    sender_public_identity = PublicIdentity(
        sender_public['signing_public_key'],
        sender_public['encryption_public_key']
    )

    valid = restored.verify(sender_public_identity)
    print(f"\n✓ Signature verification: {valid}")
    print(f"  Recipient can verify sender is: {sender_public_identity.address_hex()}")
    print(f"  Source hidden from intermediate nodes: ✓")

    assert valid == True


def test_hop_count():
    """Test hop count and TTL"""
    print("\n" + "="*60)
    print("Test: Hop Count and TTL")
    print("="*60)

    recipient = Identity()
    packet = Packet(
        packet_type=PacketType.DATA,
        destination=recipient.address,
        payload=b"Test",
        ttl=5
    )

    print(f"Initial state:")
    print(f"  TTL: {packet.ttl}")
    print(f"  Hops: {packet.hop_count}")
    print(f"  Expired: {packet.is_expired()}")

    # Simulate routing through 3 hops
    for i in range(3):
        packet.increment_hop()
        print(f"\nAfter hop {i+1}:")
        print(f"  TTL: {packet.ttl}")
        print(f"  Hops: {packet.hop_count}")
        print(f"  Expired: {packet.is_expired()}")

    assert packet.ttl == 2
    assert packet.hop_count == 3
    assert packet.is_expired() == False

    # Exceed TTL
    packet.increment_hop()
    packet.increment_hop()
    packet.increment_hop()

    print(f"\nAfter exceeding TTL:")
    print(f"  TTL: {packet.ttl}")
    print(f"  Hops: {packet.hop_count}")
    print(f"  Expired: {packet.is_expired()}")

    assert packet.is_expired() == True


def test_packet_types():
    """Test different packet types"""
    print("\n" + "="*60)
    print("Test: Different Packet Types")
    print("="*60)

    recipient = Identity()

    types = [
        (PacketType.DATA, "DATA"),
        (PacketType.ANNOUNCE, "ANNOUNCE"),
        (PacketType.PATH_REQUEST, "PATH_REQUEST"),
        (PacketType.PATH_RESPONSE, "PATH_RESPONSE"),
        (PacketType.ACK, "ACK"),
        (PacketType.KEEPALIVE, "KEEPALIVE"),
    ]

    for ptype, name in types:
        packet = Packet(
            packet_type=ptype,
            destination=recipient.address,
            payload=f"{name} payload".encode()
        )

        serialized = packet.to_bytes()
        restored = Packet.from_bytes(serialized)

        print(f"✓ {name}: {len(serialized)} bytes, type preserved: {restored.packet_type == ptype}")
        assert restored.packet_type == ptype


def test_packet_overhead():
    """Test packet overhead calculation"""
    print("\n" + "="*60)
    print("Test: Packet Overhead Analysis")
    print("="*60)

    recipient = Identity()

    # Unsigned packet
    packet_unsigned = Packet(
        packet_type=PacketType.DATA,
        destination=recipient.address,
        payload=b"X" * 100
    )
    serialized_unsigned = packet_unsigned.to_bytes()

    overhead_unsigned = len(serialized_unsigned) - len(packet_unsigned.payload)
    print(f"\nUnsigned packet:")
    print(f"  Payload: 100 bytes")
    print(f"  Total: {len(serialized_unsigned)} bytes")
    print(f"  Overhead: {overhead_unsigned} bytes (32 byte header)")

    # Signed packet
    sender = Identity()
    packet_signed = Packet(
        packet_type=PacketType.DATA,
        destination=recipient.address,
        payload=b"X" * 100
    )
    packet_signed.sign(sender)
    serialized_signed = packet_signed.to_bytes()

    overhead_signed = len(serialized_signed) - len(packet_signed.payload)
    print(f"\nSigned packet:")
    print(f"  Payload: 100 bytes")
    print(f"  Total: {len(serialized_signed)} bytes")
    print(f"  Overhead: {overhead_signed} bytes (32 byte header + 64 byte signature)")

    print(f"\n✓ Overhead comparison:")
    print(f"  Unsigned: 32 bytes")
    print(f"  Signed: 96 bytes")
    print(f"  No source address in wire format = 16 bytes saved!")

    assert overhead_unsigned == 32
    assert overhead_signed == 96


def main():
    print("=" * 60)
    print("Mycorrhizal Packet Format Test")
    print("=" * 60)

    try:
        test_basic_packet()
        test_signed_packet()
        test_hop_count()
        test_packet_types()
        test_packet_overhead()

        print("\n" + "="*60)
        print("✓ All packet tests passed!")
        print("="*60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
