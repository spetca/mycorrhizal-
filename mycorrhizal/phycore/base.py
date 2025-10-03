"""
Phycore Base - Abstract interface for physical layer transport

A "Phycore" (Physical Core) is an abstraction over any physical transport:
- TCP/UDP sockets
- Serial ports
- LoRa radios
- Bluetooth
- I2C/SPI buses

All phycores implement the same interface for sending/receiving packets.
"""


class InterfaceMode:
    """
    Interface operation modes control forwarding and announce behavior.

    Modes enable flexible mesh network topologies and bandwidth management.
    """
    FULL = 0x01           # Full mesh participation, forward all announces
    GATEWAY = 0x02        # Discover paths across segments (e.g., LoRa ↔ Internet)
    BOUNDARY = 0x03       # Connect different networks, selective forwarding
    ACCESS_POINT = 0x04   # Quiet mode, don't announce automatically
    ROAMING = 0x05        # Mobile node, fast path expiry


class PhycoreBase:
    """
    Abstract base class for all physical layer interfaces.

    Phycores are callback-based (not async) for MicroPython compatibility.
    """

    def __init__(self, name, bandwidth_bps=None, mode=InterfaceMode.FULL,
                 announce_budget_percent=2.0):
        """
        Initialize phycore.

        Args:
            name: Human-readable name for this interface
            bandwidth_bps: Interface bandwidth in bits per second (None = auto-detect)
            mode: InterfaceMode (FULL, GATEWAY, BOUNDARY, etc.)
            announce_budget_percent: Percentage of bandwidth for announces (default 2.0%)
        """
        self.name = name
        self.online = False
        self.rx_callback = None

        # Bandwidth management
        self.bandwidth_bps = bandwidth_bps or self._estimate_bandwidth()
        self.mode = mode
        self.announce_budget_percent = announce_budget_percent
        self.announce_budget_bps = self.bandwidth_bps * (announce_budget_percent / 100.0)

        # Announce queue (prioritized by hop count - lower hops = higher priority)
        # Format: [(hop_count, timestamp, packet_bytes), ...]
        self.announce_queue = []
        self.last_announce_time = 0

        # Statistics
        self.tx_count = 0
        self.rx_count = 0
        self.tx_bytes = 0
        self.rx_bytes = 0

    def start(self):
        """
        Start the phycore (open ports, connect, etc).
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclass must implement start()")

    def stop(self):
        """
        Stop the phycore (close ports, disconnect, etc).
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclass must implement stop()")

    def send(self, data):
        """
        Send raw bytes over this phycore.

        Args:
            data: bytes to send

        Returns:
            bool: True if send succeeded
        """
        raise NotImplementedError("Subclass must implement send()")

    def set_rx_callback(self, callback):
        """
        Set callback for received data.

        Args:
            callback: function(data: bytes, phycore: PhycoreBase)
        """
        self.rx_callback = callback

    def _on_receive(self, data):
        """
        Internal method called when data is received.
        Triggers the rx_callback if set.

        Args:
            data: received bytes
        """
        self.rx_count += 1
        self.rx_bytes += len(data)

        if self.rx_callback:
            self.rx_callback(data, self)

    def _estimate_bandwidth(self):
        """
        Estimate interface bandwidth.
        Subclasses should override this.

        Returns:
            int: Estimated bandwidth in bits per second
        """
        # Default: assume high bandwidth
        return 100_000_000  # 100 Mbps

    def queue_announce_for_forwarding(self, packet_bytes, hop_count):
        """
        Queue an announce for forwarding (if bandwidth allows).

        Announces are queued and prioritized by hop count.
        Lower hop count = higher priority (local nodes first).

        Args:
            packet_bytes: Serialized packet to forward
            hop_count: Number of hops from originating node
        """
        import time
        # Add to queue with priority
        self.announce_queue.append((hop_count, time.time(), packet_bytes))
        # Sort by hop count (lower = higher priority), then timestamp
        self.announce_queue.sort(key=lambda x: (x[0], x[1]))

    def process_announce_queue(self):
        """
        Process queued announces if bandwidth allows.

        Called periodically by phycore implementation.
        Sends announces in priority order (lowest hop count first).
        """
        import time

        if not self.announce_queue:
            return

        current_time = time.time()
        elapsed = current_time - self.last_announce_time

        # Calculate available bandwidth (token bucket)
        available_bits = elapsed * self.announce_budget_bps

        # Process queue while we have bandwidth
        while self.announce_queue and available_bits > 0:
            hop_count, timestamp, packet_bytes = self.announce_queue[0]

            packet_bits = len(packet_bytes) * 8

            if packet_bits <= available_bits:
                # Send it
                if self.send(packet_bytes):
                    available_bits -= packet_bits
                    self.last_announce_time = current_time

                # Remove from queue
                self.announce_queue.pop(0)
            else:
                # Not enough bandwidth, wait for next cycle
                break

    def get_stats(self):
        """Get interface statistics"""
        return {
            'name': self.name,
            'online': self.online,
            'bandwidth_bps': self.bandwidth_bps,
            'mode': self.mode,
            'announce_budget_bps': self.announce_budget_bps,
            'announce_queue_size': len(self.announce_queue),
            'tx_count': self.tx_count,
            'rx_count': self.rx_count,
            'tx_bytes': self.tx_bytes,
            'rx_bytes': self.rx_bytes
        }

    def __repr__(self):
        mode_names = {
            InterfaceMode.FULL: "FULL",
            InterfaceMode.GATEWAY: "GATEWAY",
            InterfaceMode.BOUNDARY: "BOUNDARY",
            InterfaceMode.ACCESS_POINT: "ACCESS_POINT",
            InterfaceMode.ROAMING: "ROAMING"
        }
        return (f"{self.__class__.__name__}(name='{self.name}', "
                f"mode={mode_names.get(self.mode, 'UNKNOWN')}, "
                f"online={self.online})")
