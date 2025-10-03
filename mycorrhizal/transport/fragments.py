"""
Packet Fragmentation & Reassembly

Allows sending large payloads (up to 64KB) by splitting into smaller packets.
See MYCORRHIZAL_GUIDE.md for complete documentation.
"""

import struct
import time
from ..platform.crypto_adapter import CryptoBackend


# Constants
FRAGMENT_HEADER_SIZE = 18  # 16 (transfer_id) + 1 (index) + 1 (flags)
# Fragment data size must account for:
# - LoRa max: 255 bytes
# - Packet header: 32 bytes
# - Signature: 64 bytes
# - Fragment header: 18 bytes
# - Total overhead: 114 bytes
# - Safe data size: 255 - 114 = 141 bytes
FRAGMENT_DATA_SIZE = 140   # Safe size for signed LoRa packets
MAX_FRAGMENTS = 256
MAX_TRANSFER_SIZE = 64 * 1024  # 64KB
TRANSFER_TIMEOUT = 60

# Fragment flags
FRAGMENT_FLAG_FINAL = 0x01  # Last fragment in transfer


class FragmentedTransfer:
    """Manages reassembly of a fragmented transfer"""

    def __init__(self, transfer_id, sender_address=None):
        self.transfer_id = transfer_id
        self.sender_address = sender_address
        self.fragments = {}
        self.start_time = time.time()
        self.is_final_received = False
        self.expected_fragments = None  # Will be set when final fragment arrives

    def add_fragment(self, index, data, is_final=False):
        """Add fragment. Returns True if complete."""
        # Don't store empty FINAL markers as fragments - they're just metadata
        if is_final and len(data) == 0:
            # This is just a FINAL flag marker, not actual data
            self.is_final_received = True
            self.expected_fragments = index + 1
            print(f"[FRAG] FINAL marker received: index={index}, expected={self.expected_fragments}, received={len(self.fragments)}")
        else:
            # Store actual data
            if index not in self.fragments:
                self.fragments[index] = data
            else:
                # Update with new data (in case of retransmission with better quality)
                self.fragments[index] = data

            if is_final:
                self.is_final_received = True
                self.expected_fragments = index + 1
                print(f"[FRAG] FINAL flag set: index={index}, expected={self.expected_fragments}, received={len(self.fragments)}")

        is_complete = self.is_complete()
        if not is_complete and self.is_final_received:
            missing = self.get_missing_fragments()
            print(f"[FRAG] Transfer incomplete: have {len(self.fragments)}/{self.expected_fragments}, missing: {missing}")

        return is_complete

    def is_complete(self):
        if not self.is_final_received:
            return False
        return len(self.fragments) == self.expected_fragments

    def is_expired(self):
        return (time.time() - self.start_time) > TRANSFER_TIMEOUT

    def reassemble(self):
        if not self.is_complete():
            raise ValueError("Transfer incomplete")
        result = bytearray()
        for i in range(self.expected_fragments):
            if i not in self.fragments:
                raise ValueError(f"Missing fragment {i}")
            result.extend(self.fragments[i])
        return bytes(result)

    def get_progress(self):
        if not self.is_final_received:
            return (len(self.fragments) * 20.0)  # Unknown total, estimate
        return (len(self.fragments) / self.expected_fragments) * 100.0

    def get_missing_fragments(self):
        if not self.is_final_received:
            return []  # Don't know what's missing yet
        return [i for i in range(self.expected_fragments) if i not in self.fragments]


class Fragmenter:
    """Handles fragmentation of large payloads"""

    @staticmethod
    def fragment(data, metadata=None):
        """
        Fragment data into packets.

        Returns: (fragments list, transfer_id_hex)
        """
        if len(data) > MAX_TRANSFER_SIZE:
            raise ValueError(f"Data too large: {len(data)} > {MAX_TRANSFER_SIZE}")

        # Generate unique transfer ID with random component
        import os
        random_bytes = os.urandom(8)  # 8 bytes of randomness
        transfer_id = CryptoBackend.hash_sha256(
            data + struct.pack('!Q', int(time.time() * 1000)) + random_bytes
        )[:16]

        # Add metadata header if provided
        if metadata:
            meta_str = '\n'.join([f"{k}={v}" for k, v in metadata.items()])
            meta_bytes = meta_str.encode('utf-8')
            data = struct.pack('!H', len(meta_bytes)) + meta_bytes + data

        # Calculate fragments
        total_fragments = (len(data) + FRAGMENT_DATA_SIZE - 1) // FRAGMENT_DATA_SIZE

        if total_fragments > MAX_FRAGMENTS:
            raise ValueError(f"Too many fragments: {total_fragments} > {MAX_FRAGMENTS}")

        fragments = []
        for i in range(total_fragments):
            start = i * FRAGMENT_DATA_SIZE
            end = min(start + FRAGMENT_DATA_SIZE, len(data))
            chunk = data[start:end]

            # Determine if this is the final fragment
            is_final = (i == total_fragments - 1)
            flags = FRAGMENT_FLAG_FINAL if is_final else 0x00

            # Build fragment: transfer_id (16) + index (1) + flags (1) + data
            fragment = struct.pack('!16sBB', transfer_id, i, flags) + chunk
            fragments.append(fragment)

        return fragments, transfer_id.hex()

    @staticmethod
    def parse_fragment(fragment_payload):
        """Parse fragment payload"""
        if len(fragment_payload) < FRAGMENT_HEADER_SIZE:
            raise ValueError(f"Fragment too small: {len(fragment_payload)}")

        transfer_id, index, flags = struct.unpack('!16sBB', fragment_payload[:FRAGMENT_HEADER_SIZE])
        data = fragment_payload[FRAGMENT_HEADER_SIZE:]

        is_final = bool(flags & FRAGMENT_FLAG_FINAL)

        return {
            'transfer_id': transfer_id,
            'index': index,
            'flags': flags,
            'is_final': is_final,
            'data': data
        }

    @staticmethod
    def extract_metadata(reassembled_data):
        """Extract metadata from reassembled data"""
        if len(reassembled_data) < 2:
            return {}, reassembled_data

        meta_len = struct.unpack('!H', reassembled_data[:2])[0]

        if meta_len == 0 or len(reassembled_data) < 2 + meta_len:
            return {}, reassembled_data

        meta_bytes = reassembled_data[2:2+meta_len]
        actual_data = reassembled_data[2+meta_len:]

        try:
            meta_str = meta_bytes.decode('utf-8')
            metadata = {}
            for line in meta_str.split('\n'):
                if '=' in line:
                    k, v = line.split('=', 1)
                    metadata[k.strip()] = v.strip()
            return metadata, actual_data
        except:
            return {}, reassembled_data


class TransferManager:
    """Manages multiple active fragmented transfers"""

    def __init__(self, max_concurrent=10):
        self.transfers = {}
        self.max_concurrent = max_concurrent
        self.on_transfer_complete = None
        self.on_transfer_progress = None

    def handle_fragment(self, fragment_payload, sender_address=None):
        """Handle incoming fragment"""
        frag = Fragmenter.parse_fragment(fragment_payload)
        transfer_id = frag['transfer_id']
        transfer_id_hex = transfer_id.hex()

        # Get or create transfer
        if transfer_id not in self.transfers:
            self._cleanup_expired()

            if len(self.transfers) >= self.max_concurrent:
                oldest = min(self.transfers.items(), key=lambda x: x[1].start_time)
                del self.transfers[oldest[0]]

            self.transfers[transfer_id] = FragmentedTransfer(
                transfer_id, sender_address
            )

        transfer = self.transfers[transfer_id]
        transfer.add_fragment(frag['index'], frag['data'], frag['is_final'])

        # Check if complete
        if transfer.is_complete():
            data = transfer.reassemble()
            metadata, actual_data = Fragmenter.extract_metadata(data)

            if self.on_transfer_complete:
                self.on_transfer_complete(transfer_id_hex, actual_data, metadata, sender_address)

            del self.transfers[transfer_id]

            return {
                'complete': True,
                'progress': 100.0,
                'transfer_id': transfer_id_hex,
                'size': len(actual_data)
            }
        else:
            progress = transfer.get_progress()
            if self.on_transfer_progress:
                self.on_transfer_progress(transfer_id_hex, progress)

            return {
                'complete': False,
                'progress': progress,
                'transfer_id': transfer_id_hex,
                'received': len(transfer.fragments),
                'total': transfer.expected_fragments if transfer.is_final_received else '?'
            }

    def _cleanup_expired(self):
        expired = [tid for tid, transfer in self.transfers.items() if transfer.is_expired()]
        for tid in expired:
            print(f"Transfer {tid.hex()[:8]} expired")
            del self.transfers[tid]

    def get_active_transfers(self):
        return {
            tid.hex(): {
                'progress': transfer.get_progress(),
                'received': len(transfer.fragments),
                'total': transfer.expected_fragments if transfer.is_final_received else '?',
                'sender': transfer.sender_address.hex() if transfer.sender_address else None
            }
            for tid, transfer in self.transfers.items()
        }
