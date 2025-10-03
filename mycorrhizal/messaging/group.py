"""
Group Chat (Colony) - Multi-party messaging with shared key

A "Colony" is Mycorrhizal's term for a group chat.
Uses a shared symmetric key for efficient group encryption on MCUs.
"""

import time
from ..crypto.encryption import generate_group_key, encrypt_group_message, decrypt_group_message
from ..transport.packet import Packet, PacketType


class Colony:
    """
    A group chat with shared encryption key.

    The colony creator generates a symmetric key and distributes it
    to members. All messages are encrypted with this shared key.
    """

    def __init__(self, name, group_key=None, creator_identity=None, node=None):
        """
        Create or join a colony.

        Args:
            name: Human-readable group name
            group_key: 32-byte symmetric key (generates new if None)
            creator_identity: Identity of group creator
            node: Node instance for sending messages
        """
        self.name = name
        self.group_key = group_key if group_key else generate_group_key()
        self.creator_identity = creator_identity
        self.node = node

        # Generate colony ID from key hash
        from ..platform.crypto_adapter import CryptoBackend
        self.colony_id = CryptoBackend.hash_sha256(self.group_key)[:16]

        # Member tracking
        self.members = {}  # address -> PublicIdentity
        self.member_names = {}  # address -> name

        # Message callback
        self.message_callback = None

        # Add creator as first member
        if creator_identity:
            self.add_member(creator_identity.address, creator_identity, "Creator")

    def add_member(self, address, public_identity, name=None):
        """Add a member to the colony"""
        self.members[address.hex()] = public_identity
        if name:
            self.member_names[address.hex()] = name

    def send(self, message):
        """
        Send a message to the colony.

        Args:
            message: string or bytes to send

        Returns:
            bool: True if sent successfully
        """
        if not self.node:
            raise RuntimeError("Colony not attached to a node")

        # Convert to bytes
        if isinstance(message, str):
            message = message.encode('utf-8')

        # Encrypt with group key
        encrypted = encrypt_group_message(message, self.group_key)

        # Build payload: colony_id + encrypted_message
        payload = self.colony_id + encrypted

        # Send to all members (broadcast)
        # For now, send as DATA packets to each member
        success = False
        for member_addr_hex in self.members.keys():
            if member_addr_hex == self.node.identity.address.hex():
                continue  # Don't send to ourselves

            member_addr = bytes.fromhex(member_addr_hex)
            if self.node.send_data(member_addr, payload, sign=True):
                success = True

        return success

    def handle_message(self, encrypted_payload, sender_address):
        """
        Handle incoming colony message.

        Args:
            encrypted_payload: colony_id + encrypted message
            sender_address: Address of sender
        """
        if len(encrypted_payload) < 16:
            return

        # Verify colony ID
        colony_id = encrypted_payload[:16]
        if colony_id != self.colony_id:
            return  # Not for this colony

        # Decrypt message
        encrypted = encrypted_payload[16:]
        try:
            plaintext = decrypt_group_message(encrypted, self.group_key)

            # Try to decode as UTF-8
            try:
                message = plaintext.decode('utf-8')
            except UnicodeDecodeError:
                message = plaintext

            # Auto-add sender to members if not already present
            sender_hex = sender_address.hex() if sender_address else None
            if sender_hex and sender_hex not in self.members:
                # Get identity from cache if available
                identity = None
                if self.node and hasattr(self.node, 'identity_cache'):
                    identity = self.node.identity_cache.get(sender_address)
                self.add_member(sender_address, identity, sender_hex[:8] + "...")
                print(f"[COLONY] Auto-added new member {sender_hex[:8]}... to {self.name}")

            # Get sender name
            sender_name = self.member_names.get(sender_hex, sender_hex[:8] + "..." if sender_hex else "unknown")

            # Call callback
            if self.message_callback:
                self.message_callback(sender_address, sender_name, message)

        except Exception as e:
            print(f"Error decrypting colony message: {e}")

    def on_message(self, callback):
        """
        Set callback for incoming messages.

        Args:
            callback: function(sender_address, sender_name, message)
        """
        self.message_callback = callback

    def get_key_material(self):
        """
        Get key material for sharing with new members.

        Returns:
            dict: colony_id, group_key, name
        """
        return {
            'colony_id': self.colony_id,
            'group_key': self.group_key,
            'name': self.name
        }

    @staticmethod
    def from_key_material(key_material, node=None):
        """
        Join a colony using shared key material.

        Args:
            key_material: dict with colony_id, group_key, name
            node: Node instance

        Returns:
            Colony: New colony instance
        """
        return Colony(
            name=key_material['name'],
            group_key=key_material['group_key'],
            node=node
        )

    def __repr__(self):
        return f"Colony(name='{self.name}', id={self.colony_id.hex()[:8]}..., members={len(self.members)})"
