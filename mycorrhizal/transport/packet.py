"""
Compact Binary Packet Format

Wire format designed for minimal overhead on MCU devices.
Privacy-focused design with no explicit source address.

Key Design:
- Source is implicit (proven by encryption/signature)
- Only destination address in header
- Return path learned from routing layer
- Intermediate nodes can't see source identity

Packet Structure:
┌─────────────────────────────────────────────────────────────┐
│ Header (fixed 32 bytes)                                     │
├─────────────────────────────────────────────────────────────┤
│ Flags (1 byte) | TTL (1 byte) | Hop Count (1 byte)         │
│ Packet Type (1 byte)                                        │
│ Destination Address (16 bytes)                              │
│ Payload Length (2 bytes)                                    │
│ Payload Hash (8 bytes)                                      │
│ Reserved (2 bytes)                                          │
├─────────────────────────────────────────────────────────────┤
│ Payload (variable length, possibly encrypted)              │
└─────────────────────────────────────────────────────────────┘

Total overhead: 32 bytes (vs 48 with source field)

Flags byte format:
  Bit 7: Encrypted
  Bit 6: Signed
  Bit 5: Priority
  Bit 4: Fragmented
  Bit 3-0: Reserved
"""

import struct
from ..platform.crypto_adapter import CryptoBackend


# Protocol version embedded in packet type byte
PROTOCOL_VERSION = 1

# Packet types
class PacketType:
    DATA = 0x01          # Regular data packet
    ANNOUNCE = 0x02      # Node announcement (includes public key)
    PATH_REQUEST = 0x03  # Request path to destination
    PATH_RESPONSE = 0x04 # Response with path information
    ACK = 0x05          # Acknowledgment
    KEEPALIVE = 0x06    # Keep connection alive

# Packet flags (bit flags)
class PacketFlags:
    NONE = 0x00
    ENCRYPTED = 0x80    # Bit 7: Payload is encrypted
    SIGNED = 0x40       # Bit 6: Packet includes signature
    PRIORITY = 0x20     # Bit 5: High priority packet
    FRAGMENTED = 0x10   # Bit 4: Part of fragmented message
    # Bits 3-0: Reserved for future use

# Constants
HEADER_SIZE = 32
SIGNATURE_SIZE = 64
MAX_PAYLOAD_SIZE = 65535  # 2^16 - 1


class Packet:
    """
    Binary packet with no explicit source address for enhanced privacy.

    Source identity is proven through:
    - Encryption (only sender can encrypt to destination's public key)
    - Signature (verifies sender's identity)
    - Return path cached by transport layer
    """

    def __init__(self, packet_type, destination, payload=b"",
                 ttl=32, flags=PacketFlags.NONE):
        """
        Create a new packet.

        Args:
            packet_type: PacketType value
            destination: 16-byte destination address
            payload: bytes payload data
            ttl: Time-to-live (hops remaining)
            flags: PacketFlags bitmask
        """
        self.packet_type = packet_type
        self.flags = flags
        self.ttl = ttl
        self.hop_count = 0
        self.destination = destination
        self.payload = payload
        self.signature = None

        # For tracking received packets (filled by transport layer)
        self.source_address = None  # Learned from announce/signature
        self.receiving_interface = None
        self.rssi = None
        self.snr = None

        # Validate
        if len(destination) != 16:
            raise ValueError(f"Destination address must be 16 bytes, got {len(destination)}")
        if len(payload) > MAX_PAYLOAD_SIZE:
            raise ValueError(f"Payload too large: {len(payload)} > {MAX_PAYLOAD_SIZE}")

    def increment_hop(self):
        """Increment hop count and decrement TTL"""
        self.hop_count += 1
        self.ttl -= 1
        if self.ttl < 0:
            self.ttl = 0

    def is_expired(self):
        """Check if packet has exceeded TTL"""
        return self.ttl <= 0

    def is_signed(self):
        """Check if packet includes signature"""
        return (self.flags & PacketFlags.SIGNED) != 0

    def is_encrypted(self):
        """Check if payload is encrypted"""
        return (self.flags & PacketFlags.ENCRYPTED) != 0

    def is_priority(self):
        """Check if packet is high priority"""
        return (self.flags & PacketFlags.PRIORITY) != 0

    def is_fragmented(self):
        """Check if packet is part of fragmented message"""
        return (self.flags & PacketFlags.FRAGMENTED) != 0

    def sign(self, identity):
        """
        Sign the packet with an identity.
        This proves the sender's identity to the recipient.

        Args:
            identity: Identity object with signing capability
        """
        # Add signed flag
        self.flags |= PacketFlags.SIGNED

        # Sign the header + payload
        data_to_sign = self._get_signing_data()
        self.signature = identity.sign(data_to_sign)

    def verify(self, public_identity):
        """
        Verify packet signature against a public identity.
        This proves the packet came from the claimed sender.

        Args:
            public_identity: PublicIdentity to verify against

        Returns:
            bool: True if signature is valid
        """
        if not self.is_signed() or self.signature is None:
            return False

        data_to_verify = self._get_signing_data()
        return public_identity.verify(data_to_verify, self.signature)

    def _get_signing_data(self):
        """Get the data that should be signed/verified"""
        # Sign everything except the signature itself
        return self._serialize_header() + self.payload

    def _serialize_header(self):
        """
        Serialize packet header to bytes (32 bytes).

        Format:
        - 1 byte: flags (encryption, signature, priority, fragmentation)
        - 1 byte: ttl
        - 1 byte: hop_count
        - 1 byte: packet_type
        - 16 bytes: destination address
        - 2 bytes: payload_length (uint16, big-endian)
        - 8 bytes: payload_hash (truncated SHA-256 for integrity check)
        - 2 bytes: reserved (future use)
        Total: 32 bytes
        """
        payload_length = len(self.payload)

        # Hash the payload (take first 8 bytes for integrity check)
        payload_hash = CryptoBackend.hash_sha256(self.payload)[:8]

        # Pack header (32 bytes total)
        header = struct.pack(
            '!BBBB16sH8sH',
            self.flags,            # 1 byte
            self.ttl,             # 1 byte
            self.hop_count,       # 1 byte
            self.packet_type,     # 1 byte
            self.destination,     # 16 bytes
            payload_length,       # 2 bytes
            payload_hash,         # 8 bytes
            0                     # 2 bytes reserved
        )

        return header

    def to_bytes(self):
        """
        Serialize complete packet to bytes for transmission.

        Returns:
            bytes: Serialized packet
        """
        data = bytearray()

        # Add header
        data.extend(self._serialize_header())

        # Add payload
        data.extend(self.payload)

        # Add signature if signed
        if self.is_signed() and self.signature:
            data.extend(self.signature)

        return bytes(data)

    @staticmethod
    def from_bytes(data):
        """
        Deserialize packet from bytes.

        Args:
            data: bytes to deserialize

        Returns:
            Packet: Reconstructed packet
        """
        if len(data) < HEADER_SIZE:
            raise ValueError(f"Data too short for packet header: {len(data)} < {HEADER_SIZE}")

        # Unpack header
        header = struct.unpack('!BBBB16sH8sH', data[:HEADER_SIZE])

        flags = header[0]
        ttl = header[1]
        hop_count = header[2]
        packet_type = header[3]
        destination = header[4]
        payload_length = header[5]
        payload_hash = header[6]
        # reserved = header[7]

        # Extract payload
        payload_start = HEADER_SIZE
        payload_end = payload_start + payload_length

        if len(data) < payload_end:
            raise ValueError(f"Data too short for payload: {len(data)} < {payload_end}")

        payload = data[payload_start:payload_end]

        # Verify payload hash (integrity check)
        actual_hash = CryptoBackend.hash_sha256(payload)[:8]
        if actual_hash != payload_hash:
            raise ValueError("Payload hash mismatch - corrupted packet")

        # Create packet
        packet = Packet(
            packet_type=packet_type,
            destination=destination,
            payload=payload,
            ttl=ttl,
            flags=flags
        )
        packet.hop_count = hop_count

        # Extract signature if present
        if packet.is_signed():
            signature_start = payload_end
            signature_end = signature_start + SIGNATURE_SIZE

            if len(data) < signature_end:
                raise ValueError(f"Data too short for signature: {len(data)} < {signature_end}")

            packet.signature = data[signature_start:signature_end]

        return packet

    def __repr__(self):
        type_name = {
            PacketType.DATA: 'DATA',
            PacketType.ANNOUNCE: 'ANNOUNCE',
            PacketType.PATH_REQUEST: 'PATH_REQUEST',
            PacketType.PATH_RESPONSE: 'PATH_RESPONSE',
            PacketType.ACK: 'ACK',
            PacketType.KEEPALIVE: 'KEEPALIVE',
        }.get(self.packet_type, f'UNKNOWN({self.packet_type})')

        flags_str = []
        if self.is_encrypted():
            flags_str.append('ENC')
        if self.is_signed():
            flags_str.append('SIG')
        if self.is_priority():
            flags_str.append('PRI')
        if self.is_fragmented():
            flags_str.append('FRAG')
        flags_display = ','.join(flags_str) if flags_str else 'NONE'

        src_display = f"src={self.source_address.hex()[:8]}..." if self.source_address else "src=unknown"

        return (f"Packet(type={type_name}, "
                f"{src_display}, "
                f"dst={self.destination.hex()[:8]}..., "
                f"ttl={self.ttl}, hops={self.hop_count}, "
                f"payload={len(self.payload)}B, "
                f"flags=[{flags_display}])")
