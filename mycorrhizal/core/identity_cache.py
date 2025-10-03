"""
Identity Cache - Store discovered public identities

This cache stores public identities learned from announces.
Size is adaptive based on platform capability.
"""

import time
from ..crypto.identity import PublicIdentity
from ..platform.detection import get_profile


class IdentityCache:
    """
    Cache of discovered public identities.

    When we receive an announce, we store the sender's public keys
    so we can:
    - Verify signatures from that sender
    - Encrypt messages to that sender
    - Know the return path
    """

    def __init__(self):
        """Initialize identity cache"""
        self.profile = get_profile()

        # Cache: address -> (PublicIdentity, timestamp, interface)
        self.identities = {}

        # Max entries based on platform capability
        self.max_entries = self.profile.max_cache_entries

    def add(self, address, public_identity, receiving_interface=None):
        """
        Add or update a public identity in the cache.

        Args:
            address: 16-byte address
            public_identity: PublicIdentity object
            receiving_interface: Phycore that received the announce (for return path)
        """
        address_key = address.hex()

        # If cache is full, remove oldest entry
        if len(self.identities) >= self.max_entries and address_key not in self.identities:
            self._evict_oldest()

        # Store identity with timestamp
        self.identities[address_key] = {
            'identity': public_identity,
            'timestamp': time.time(),
            'interface': receiving_interface
        }

    def get(self, address):
        """
        Get a public identity from the cache.

        Args:
            address: 16-byte address or hex string

        Returns:
            PublicIdentity or None if not found
        """
        if isinstance(address, bytes):
            address_key = address.hex()
        else:
            address_key = address

        entry = self.identities.get(address_key)
        if entry:
            return entry['identity']
        return None

    def get_interface(self, address):
        """
        Get the interface where we last saw this identity.
        Useful for return path routing.

        Args:
            address: 16-byte address or hex string

        Returns:
            Phycore or None
        """
        if isinstance(address, bytes):
            address_key = address.hex()
        else:
            address_key = address

        entry = self.identities.get(address_key)
        if entry:
            return entry['interface']
        return None

    def has(self, address):
        """Check if we have an identity for this address"""
        if isinstance(address, bytes):
            address_key = address.hex()
        else:
            address_key = address
        return address_key in self.identities

    def _evict_oldest(self):
        """Remove the oldest entry from cache (simple LRU)"""
        if not self.identities:
            return

        oldest_key = min(self.identities.keys(),
                        key=lambda k: self.identities[k]['timestamp'])
        del self.identities[oldest_key]

    def get_all(self):
        """Get all cached identities"""
        return {k: v['identity'] for k, v in self.identities.items()}

    def size(self):
        """Get current cache size"""
        return len(self.identities)

    def clear(self):
        """Clear all cached identities"""
        self.identities.clear()

    def __repr__(self):
        return f"IdentityCache(size={len(self.identities)}, max={self.max_entries})"
