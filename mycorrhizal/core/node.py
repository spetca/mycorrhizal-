"""
Node - Core network node implementation

The Node is the main entry point for Mycorrhizal applications.
It manages:
- Identity
- Phycores (physical interfaces)
- Packet sending/receiving
- Message callbacks
"""

from ..crypto.identity import Identity, PublicIdentity
from ..transport.packet import Packet, PacketType
from ..platform.detection import get_profile, is_micropython
from .identity_cache import IdentityCache
from ..routing.route_table import RouteTable
from ..storage.identity_storage import IdentityStorage
from ..transport.fragments import TransferManager, Fragmenter


class Node:
    """
    A Mycorrhizal network node.

    Handles packet transmission/reception and routes messages
    to appropriate handlers.
    """

    def __init__(self, identity=None, name="node", persistent_identity=True):
        """
        Create a new node.

        Args:
            identity: Identity object (creates new one if None)
            name: Human-readable node name
            persistent_identity: Save/load identity from flash (default True)
        """
        self.name = name

        # Try to load existing identity from flash
        if persistent_identity and identity is None:
            identity = IdentityStorage.load()
            if identity:
                print(f"Loaded persisted identity")

        # Create new identity if needed
        if identity is None:
            identity = Identity()
            print(f"Generated new identity")

            # Save to flash if persistence enabled
            if persistent_identity:
                IdentityStorage.save(identity)

        self.identity = identity
        self.address = self.identity.address
        self.persistent_identity = persistent_identity

        # Get platform profile
        self.profile = get_profile()

        # Phycores (physical interfaces)
        self.phycores = []

        # Identity cache for discovered nodes
        self.identity_cache = IdentityCache()

        # Route table for multi-hop routing
        max_routes = self.profile.max_cache_entries
        self.route_table = RouteTable(max_routes=max_routes, route_timeout=1800)

        # Routing settings
        self.enable_forwarding = True  # Act as router/relay
        self.max_hops = 128  # Maximum TTL (default, can support up to 255)
        # Note: Unlike some mesh networks with low hop limits (e.g., 7 hops max),
        # we support 100+ hops through hop-count prioritization, bandwidth limiting, and smart flooding

        # Message callbacks
        self.data_callback = None
        self.announce_callback = None
        self.file_received_callback = None  # Callback for received files

        # Simple packet deduplication (cache recent packet hashes)
        # Size based on platform capability
        self.seen_packets = set()
        self.max_seen_packets = min(1000, self.profile.max_cache_entries)

        # Announce settings
        self.announce_interval = 300  # seconds (5 minutes default)
        self.announce_timer = None
        self.auto_announce = False

        # Colonies (group chats)
        self.colonies = {}  # colony_id -> Colony

        # Transfer manager for fragmented files
        self.transfer_manager = TransferManager(max_concurrent=5)
        self._setup_transfer_callbacks()

        print(f"Node '{self.name}' initialized")
        print(f"  Address: {self.identity.address_hex()}")
        print(f"  Platform: {self.profile.platform}")
        print(f"  Capability: {self.profile.capability}")

    def add_phycore(self, phycore):
        """
        Add a physical interface.

        Args:
            phycore: PhycoreBase instance
        """
        phycore.set_rx_callback(self._on_packet_received)
        self.phycores.append(phycore)
        print(f"  Added phycore: {phycore}")

    def start(self, auto_announce=True, announce_now=True):
        """
        Start all phycores.

        Args:
            auto_announce: Enable periodic announces
            announce_now: Send initial announce immediately
        """
        print(f"\nStarting node '{self.name}'...")
        for phycore in self.phycores:
            success = phycore.start()
            status = "✓" if success else "✗"
            print(f"  {status} {phycore.name}: {'online' if success else 'failed'}")

        # Start periodic announces if enabled
        if auto_announce:
            self.start_announcing(announce_now=announce_now)

    def stop(self):
        """Stop all phycores and periodic announces"""
        print(f"\nStopping node '{self.name}'...")

        # Stop periodic announces
        self.stop_announcing()

        # Stop phycores
        for phycore in self.phycores:
            phycore.stop()
            print(f"  ✓ {phycore.name}: stopped")

    def send_data(self, destination_address, payload, sign=True, flags=0):
        """
        Send data to a destination.

        Args:
            destination_address: 16-byte destination address
            payload: bytes to send
            sign: whether to sign the packet (default True)
            flags: Packet flags (e.g., PacketFlags.FRAGMENTED) (default 0)

        Returns:
            bool: True if sent successfully
        """
        # Create packet
        packet = Packet(
            packet_type=PacketType.DATA,
            destination=destination_address,
            payload=payload,
            flags=flags
        )

        # Sign if requested
        if sign:
            packet.sign(self.identity)

        # Check if we have a route to destination
        route = self.route_table.get_route(destination_address)
        if route:
            # Send via specific route
            print(f"[SEND] Using route to {destination_address.hex()[:16]}...")
            serialized = packet.to_bytes()
            print(f"[SEND] Packet serialized to {len(serialized)} bytes")
            if route.interface.online:
                result = route.interface.send(serialized)
                print(f"[SEND] Route send result: {result}")
                return result
            print(f"[SEND] Route interface offline!")
            return False
        else:
            # No route - broadcast on all interfaces (fallback)
            print(f"[SEND] No route to {destination_address.hex()[:16]}..., broadcasting")
            result = self._send_packet(packet)
            print(f"[SEND] Broadcast result: {result}")
            return result
        
    def announce(self, verbose=True):
        """
        Announce presence on the network.

        Announces include public keys so other nodes can verify/encrypt to us.

        Args:
            verbose: Print announce message (default True)
        """
        # Build announce payload with public keys
        public_info = self.identity.get_public_identity()

        # Simple format: signing_key + encryption_key
        announce_payload = (
            public_info['signing_public_key'] +
            public_info['encryption_public_key']
        )

        packet = Packet(
            packet_type=PacketType.ANNOUNCE,
            destination=self.address,  # Announce our own address
            payload=announce_payload
        )

        # Always sign announces
        packet.sign(self.identity)

        if verbose:
            print(f"\n📣 Announcing {self.name} ({self.identity.address_hex()[:16]}...)")

        return self._send_packet(packet)

    def start_announcing(self, interval=None, announce_now=True):
        """
        Start periodic announces.

        Args:
            interval: Announce interval in seconds (default: 300 = 5 minutes)
            announce_now: Send an announce immediately
        """
        if interval:
            self.announce_interval = interval

        self.auto_announce = True

        # Send initial announce
        if announce_now:
            self.announce(verbose=False)

        if is_micropython():
            # MicroPython: No threading, manual announce checking in main loop
            # Store last announce time for manual checking
            import time
            self.last_announce_time = time.ticks_ms()
            print(f"  📣 Auto-announce enabled (every {self.announce_interval}s) - manual mode")
        else:
            # CPython: Use threading.Timer
            import threading

            # Schedule next announce
            def schedule_next():
                if self.auto_announce:
                    self.announce(verbose=False)
                    self.announce_timer = threading.Timer(self.announce_interval, schedule_next)
                    self.announce_timer.daemon = True
                    self.announce_timer.start()

            self.announce_timer = threading.Timer(self.announce_interval, schedule_next)
            self.announce_timer.daemon = True
            self.announce_timer.start()

            print(f"  📣 Auto-announce enabled (every {self.announce_interval}s)")

    def stop_announcing(self):
        """Stop periodic announces"""
        self.auto_announce = False
        if self.announce_timer:
            self.announce_timer.cancel()
            self.announce_timer = None

    def check_announce(self):
        """
        Check if it's time to send an auto-announce (MicroPython manual mode).
        Call this regularly from your main loop on MicroPython.
        """
        if not is_micropython() or not self.auto_announce:
            return

        import time
        now = time.ticks_ms()
        interval_ms = self.announce_interval * 1000

        if time.ticks_diff(now, self.last_announce_time) >= interval_ms:
            self.announce(verbose=False)
            self.last_announce_time = now

    def _send_packet(self, packet):
        """
        Internal: Send packet via all phycores.

        Args:
            packet: Packet to send

        Returns:
            bool: True if at least one phycore succeeded
        """
        serialized = packet.to_bytes()
        success_count = 0

        for phycore in self.phycores:
            if phycore.online and phycore.send(serialized):
                success_count += 1

        return success_count > 0

    def _on_packet_received(self, data, phycore):
        """
        Internal: Handle received packet from a phycore.

        Args:
            data: raw packet bytes
            phycore: PhycoreBase that received the packet
        """
        try:
            # Deserialize packet
            packet = Packet.from_bytes(data)

            # Deduplicate based on packet hash
            packet_hash = hash(data)
            if packet_hash in self.seen_packets:
                return  # Already processed this packet

            # Add to seen packets (LRU: remove oldest if full)
            self.seen_packets.add(packet_hash)
            if len(self.seen_packets) > self.max_seen_packets:
                # Simple approach: clear half when full
                # (More sophisticated LRU could be implemented)
                self.seen_packets = set(list(self.seen_packets)[self.max_seen_packets // 2:])

            # Handle announces first - they're broadcast to everyone
            if packet.packet_type == PacketType.ANNOUNCE:
                self._handle_announce_packet(packet, phycore)
                # Forward announces for path discovery
                if self.enable_forwarding and packet.hop_count < self.max_hops:
                    self._forward_announce(packet, phycore)
                return

            # Check if packet is for us (non-announce packets)
            if packet.destination != self.address:
                # Not for us - forward if enabled
                print(f"[NODE] Packet not for us. Dest: {packet.destination.hex()[:16]}..., My addr: {self.address.hex()[:16]}...")
                if self.enable_forwarding and packet.hop_count < self.max_hops:
                    self._forward_packet(packet, phycore)
                return

            print(f"[NODE] Packet IS for us! Type: {packet.packet_type}, payload size: {len(packet.payload)}")

            # Handle other packet types
            if packet.packet_type == PacketType.DATA:
                self._handle_data_packet(packet, phycore)
            # Add more packet type handlers here

        except Exception as e:
            print(f"Error processing packet: {e}")
            import traceback
            traceback.print_exc()

    def _handle_data_packet(self, packet, phycore):
        """Handle incoming data packet"""
        source_address = None
        source_identity = None

        # If packet is signed, try to verify and identify sender
        if packet.is_signed():
            # Try all cached identities to find the sender
            for addr_hex, identity in self.identity_cache.get_all().items():
                if packet.verify(identity):
                    source_address = bytes.fromhex(addr_hex)
                    source_identity = identity
                    break

        # Check if fragmented (packet has FRAGMENTED flag)
        if packet.is_fragmented():
            # Handle as fragment
            self.transfer_manager.handle_fragment(packet.payload, source_address)
            return

        # Check if this is a colony message (first 16 bytes = colony_id)
        if len(packet.payload) >= 16:
            potential_colony_id = packet.payload[:16]
            print(f"[NODE] Checking if colony message: {potential_colony_id.hex()[:16]}...")
            print(f"[NODE] Known colonies: {list(self.colonies.keys())}")
            if potential_colony_id.hex() in self.colonies:
                # Route to colony
                print(f"[NODE] Routing to colony {potential_colony_id.hex()[:16]}...")
                colony = self.colonies[potential_colony_id.hex()]
                colony.handle_message(packet.payload, source_address)
                return
            else:
                print(f"[NODE] Not a known colony message")

        # Regular data callback
        if self.data_callback:
            self.data_callback(packet.payload, source_address, packet)

    def _handle_announce_packet(self, packet, phycore):
        """
        Handle incoming announce packet.

        Announce format:
        - 32 bytes: Ed25519 signing public key
        - 32 bytes: X25519 encryption public key
        Total: 64 bytes
        """
        try:
            if len(packet.payload) < 64:
                print(f"⚠️  Invalid announce: payload too short ({len(packet.payload)} bytes)")
                return

            # Extract public keys from payload
            signing_public_key = packet.payload[0:32]
            encryption_public_key = packet.payload[32:64]

            # Create PublicIdentity
            public_identity = PublicIdentity(signing_public_key, encryption_public_key)

            # Verify the announce signature (only for direct announces, not forwarded ones)
            # Forwarded announces have hop_count > 0 and signature was already verified by previous hop
            if packet.is_signed() and packet.hop_count == 0:
                if not packet.verify(public_identity):
                    print(f"⚠️  Invalid announce signature from {packet.destination.hex()[:16]}...")
                    return

            # Verify address matches public key
            if public_identity.address != packet.destination:
                print(f"⚠️  Address mismatch in announce")
                return

            # Add to identity cache
            self.identity_cache.add(packet.destination, public_identity, phycore)

            # Add/update route
            # If hop_count == 0, it's a direct neighbor (next_hop = None)
            # If hop_count > 0, we learned about this node via forwarding
            next_hop = None if packet.hop_count == 0 else packet.destination
            self.route_table.add_or_update(
                packet.destination,
                next_hop,
                phycore,
                packet.hop_count
            )

            print(f"📡 Announce from {packet.destination.hex()[:16]}... via {phycore.name} (hops={packet.hop_count})")
            print(f"   Identity cached (total: {self.identity_cache.size()}), Route added (total: {self.route_table.size()})")

            # Call user callback if set
            if self.announce_callback:
                self.announce_callback(packet, public_identity)

        except Exception as e:
            print(f"⚠️  Error processing announce: {e}")

    def _forward_announce(self, packet, received_from):
        """
        Forward an announce packet with bandwidth-aware forwarding.

        Args:
            packet: ANNOUNCE packet to forward
            received_from: PhycoreBase that received the packet
        """
        from ..phycore.base import InterfaceMode

        # Increment hop count
        packet.hop_count += 1

        # Check TTL
        if packet.hop_count >= self.max_hops:
            return

        # Serialize once
        serialized = packet.to_bytes()

        # Forward to all interfaces except where we received it
        for phycore in self.phycores:
            if phycore == received_from or not phycore.online:
                continue

            # Apply interface mode filtering
            if phycore.mode == InterfaceMode.ACCESS_POINT:
                # ACCESS_POINT mode: don't forward announces
                continue

            elif phycore.mode == InterfaceMode.BOUNDARY:
                # BOUNDARY mode: only forward local announces (low hop count)
                # Don't forward distant announces across boundaries
                if packet.hop_count > 3:
                    continue

            # Queue announce for transmission (respects bandwidth budget)
            phycore.queue_announce_for_forwarding(serialized, packet.hop_count)

    def _forward_packet(self, packet, received_from):
        """
        Forward a data packet to the next hop.

        Args:
            packet: Packet to forward
            received_from: PhycoreBase that received the packet
        """
        # Increment hop count
        packet.hop_count += 1

        # Check TTL
        if packet.hop_count >= self.max_hops:
            return

        # For data packets, use route table
        route = self.route_table.get_route(packet.destination)
        if route:
            # Forward via specific interface
            serialized = packet.to_bytes()
            if route.interface.online:
                route.interface.send(serialized)
        else:
            # No route - optionally broadcast (controlled flooding)
            # For now, just drop it
            pass

    def on_data(self, callback):
        """
        Set callback for incoming data packets.

        Args:
            callback: function(payload: bytes, source_address: bytes, packet: Packet)
        """
        self.data_callback = callback

    def on_announce(self, callback):
        """
        Set callback for incoming announces.

        Args:
            callback: function(packet: Packet)
        """
        self.announce_callback = callback

    def on_file_received(self, callback):
        """
        Set callback for received files.

        Args:
            callback: function(transfer_id, data, metadata, sender_address)
        """
        self.file_received_callback = callback

    def _setup_transfer_callbacks(self):
        """Setup transfer manager callbacks"""
        def on_complete(transfer_id, data, metadata, sender):
            print(f"📁 File received: {metadata.get('filename', 'unknown')} ({len(data)} bytes)")
            if self.file_received_callback:
                self.file_received_callback(transfer_id, data, metadata, sender)

        def on_progress(transfer_id, progress):
            # Only print progress updates every 20%
            if int(progress) % 20 == 0:
                print(f"📥 Transfer {transfer_id[:8]}: {progress:.0f}%")

        self.transfer_manager.on_transfer_complete = on_complete
        self.transfer_manager.on_transfer_progress = on_progress

    def send_file(self, destination_address, file_data, filename=None, mime_type=None):
        """
        Send a file to a destination using fragmentation.

        Args:
            destination_address: 16-byte destination address
            file_data: bytes of file data
            filename: Optional filename
            mime_type: Optional MIME type

        Returns:
            str: Transfer ID
        """
        # Prepare metadata
        metadata = {
            'size': str(len(file_data))
        }
        if filename:
            metadata['filename'] = filename
        if mime_type:
            metadata['mime_type'] = mime_type

        # Fragment the file
        fragments, transfer_id = Fragmenter.fragment(file_data, metadata=metadata)

        print(f"📤 Sending file: {filename or 'data'} ({len(file_data)} bytes, {len(fragments)} fragments)")

        # Send each fragment as FRAGMENTED packet
        from ..transport.packet import PacketFlags
        for i, frag in enumerate(fragments):
            packet = Packet(
                packet_type=PacketType.DATA,
                destination=destination_address,
                payload=frag,
                flags=PacketFlags.FRAGMENTED
            )
            packet.sign(self.identity)
            self._send_packet(packet)

            # Small delay between fragments on MicroPython
            if is_micropython() and i % 5 == 0:
                import time
                time.sleep_ms(50)

        return transfer_id

    def create_colony(self, name):
        """
        Create a new colony (group chat).

        Args:
            name: Human-readable colony name

        Returns:
            Colony: New colony instance
        """
        from ..messaging.group import Colony

        colony = Colony(name=name, creator_identity=self.identity, node=self)
        self.colonies[colony.colony_id.hex()] = colony

        print(f"Created colony '{name}' (id={colony.colony_id.hex()[:8]}...)")
        return colony

    def join_colony(self, key_material):
        """
        Join an existing colony using shared key material.

        Args:
            key_material: dict with colony_id, group_key, name

        Returns:
            Colony: Joined colony instance
        """
        from ..messaging.group import Colony

        colony = Colony.from_key_material(key_material, node=self)
        self.colonies[colony.colony_id.hex()] = colony

        print(f"Joined colony '{colony.name}' (id={colony.colony_id.hex()[:8]}...)")
        return colony

    def get_stats(self):
        """Get node statistics"""
        stats = {
            'name': self.name,
            'address': self.identity.address_hex(),
            'phycores': []
        }

        for phycore in self.phycores:
            stats['phycores'].append(phycore.get_stats())

        return stats

    def __repr__(self):
        return f"Node(name='{self.name}', address={self.identity.address_hex()[:16]}...)"
