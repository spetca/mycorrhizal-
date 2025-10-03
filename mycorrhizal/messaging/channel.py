"""
Channel - Direct messaging abstraction

A Channel represents a 1-to-1 encrypted conversation with another node.
"""

from ..crypto.encryption import encrypt_to_identity, decrypt_from_identity


class Channel:
    """
    A direct message channel between two nodes.
    """

    def __init__(self, remote_address, remote_identity, local_identity, node=None):
        """
        Create a channel to a remote node.

        Args:
            remote_address: 16-byte address of remote node
            remote_identity: PublicIdentity of remote node
            local_identity: Our Identity
            node: Node instance for sending
        """
        self.remote_address = remote_address
        self.remote_identity = remote_identity
        self.local_identity = local_identity
        self.node = node

        # Message callback
        self.message_callback = None

    def send(self, message):
        """
        Send a message to the remote node.

        Args:
            message: string or bytes to send

        Returns:
            bool: True if sent successfully
        """
        if not self.node:
            raise RuntimeError("Channel not attached to a node")

        # Convert to bytes
        if isinstance(message, str):
            message = message.encode('utf-8')

        # Encrypt to recipient (currently passthrough until X25519 implemented)
        encrypted = encrypt_to_identity(message, self.remote_identity, self.local_identity)

        # Send as signed DATA packet
        return self.node.send_data(self.remote_address, encrypted, sign=True)

    def handle_message(self, encrypted_payload):
        """
        Handle incoming message from remote node.

        Args:
            encrypted_payload: encrypted message bytes
        """
        # Decrypt (currently passthrough)
        plaintext = decrypt_from_identity(encrypted_payload, self.remote_identity, self.local_identity)

        # Try to decode as UTF-8
        try:
            message = plaintext.decode('utf-8')
        except UnicodeDecodeError:
            message = plaintext

        # Call callback
        if self.message_callback:
            self.message_callback(message)

    def on_message(self, callback):
        """
        Set callback for incoming messages.

        Args:
            callback: function(message)
        """
        self.message_callback = callback

    def __repr__(self):
        return f"Channel(remote={self.remote_address.hex()[:8]}...)"
